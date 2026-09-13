"""
conditional.py — Empirical conditional return distribution lookup.

Provides a macro-state bucket system and empirical forward-return distributions
for use in the quantitative context layer (Phase 12). Given the current macro
state, returns the historical distribution of forward returns per asset.

Bucket dimensions (18 total = 3 × 2 × 3):
    NFCI tertile          : low / mid / high
    Yield curve sign      : positive / inverted
    Credit-spread tertile : tight / mid / wide   (BAA10Y — see below)

Bucket label format: 'NFCI:low|YC:positive|CREDIT:tight'

Collapse hierarchy (when n < min_n):
    Full 3D  → drop credit tertile (6 parent buckets)
             → drop YC sign       (3 grandparent buckets)
             → global fallback ('all')

Functions
---------
assign_bucket(snapshot, strict=False) -> str
    Map a macro snapshot to its bucket label. `strict=True` raises on a
    missing input instead of falling back — the build side uses it so an
    absent series drops the date rather than mislabelling it.

build_bucket_index(historical_snapshots) -> dict[str, list[date]]
    Inverted index: bucket label -> list of snapshot dates.

build_distribution_table(historical_snapshots, forward_returns, min_n=10,
                          persist_path=None) -> dict
    Build nested distribution table; optionally persist to JSON.

load_distribution_table(path) -> dict
    Load a previously persisted table (restores int horizon keys).

lookup_distribution(current_bucket, asset, horizon, table) -> dict | None
    Return distribution dict with parent-bucket fallback, or None.

build_distribution_table_for_backtest(historical_snapshots, forward_returns,
                                       as_of_date, max_horizon=20, min_n=10) -> dict
    Lookahead-safe version: only uses observations whose forward return
    was knowable by as_of_date (snapshot_date + max_horizon <= as_of_date).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
DATA_DIR = _HERE / "data"

DEFAULT_TABLE_PATH = DATA_DIR / "conditional_distributions.json"

# ---------------------------------------------------------------------------
# The credit dimension is BAA10Y, not HY OAS  (WP-17.5, 2026-09-13)
#
# The bucket's credit tertile was keyed on the ICE BofA HY OAS (BAMLH0A0HYM2)
# from Phase 11 until 2026-09-13. Free FRED serves that series as a ~3-year
# ROLLING window (2023-08-28 when KB-021 measured it; 2023-09-12 today), which
# capped the whole table at ~780 dates of one regime and — because a missing
# input fell back to "mid" — would have silently mislabelled every earlier date
# had the fetch been widened. BAA10Y (Moody's Baa − 10Y, daily, 1986+, unrevised)
# is the deep substitute the regime feature and the fragility gate already use
# (KB-003, KB-021). The two are not the same spread (IG vs HY; daily-level
# correlation 0.54 on the overlap), so the tertile is renamed CREDIT and the
# cut-points below are BAA10Y's, not a rescaling of the old HY ones.
#
# Empirical tertile cut-points, computed ONCE on the build sample and fixed:
#
#   sample: business days from TABLE_START (2000-08-01, where GC=F and CL=F
#           begin) to 2026-09-11, FRED series forward-filled to the bday index
#   NFCI   (weekly, Chicago Fed):  p33 = -0.57   p67 = -0.40
#   BAA10Y (daily, pp):            p33 =  2.03   p67 =  2.72
#
# To refresh: np.percentile(series.reindex(bdays, method="ffill").dropna(),
# [33, 67]) on the same sample, then update the four constants. Do not move
# them with the sample's end date — the label a date received must not change
# because time passed.
# ---------------------------------------------------------------------------
TABLE_START: date = date(2000, 8, 1)

_NFCI_LOW_MID: float     = -0.57   # p33 of NFCI,   2000-08 → 2026-09
_NFCI_MID_HIGH: float    = -0.40   # p67 of NFCI,   2000-08 → 2026-09
_CREDIT_LOW_MID: float   =  2.03   # p33 of BAA10Y, 2000-08 → 2026-09 (pp)
_CREDIT_MID_HIGH: float  =  2.72   # p67 of BAA10Y, 2000-08 → 2026-09 (pp)

# The snapshot key the credit tertile reads. Live: fred_data.fetch_quant_inputs;
# build: refit_models._FRED_SERIES. Named once so the two cannot drift.
CREDIT_SERIES_KEY: str = "baa_spread"

# Buckets flagged as sparse from historical analysis (n < 20 on 2010-2025 data).
# These are automatically collapsed to their parent in lookup_distribution.
# Re-compute by calling _identify_sparse_buckets() after a table rebuild.
SPARSE_BUCKETS: frozenset[str] = frozenset()

# JSON horizon keys are strings; these are the canonical integer horizons.
_HORIZONS: tuple[int, ...] = (5, 10, 20)

# ---------------------------------------------------------------------------
# Phase 11.1 — State bucketing
# ---------------------------------------------------------------------------

def assign_bucket(snapshot: dict, strict: bool = False) -> str:
    """
    Return the bucket label for a macro snapshot.

    Returns a string like 'NFCI:low|YC:inverted|CREDIT:wide'.

    Parameters
    ----------
    snapshot : output of fetch_fred_data() merged with fetch_quant_inputs(),
               or a refit_models snapshot stub
    strict   : False (live) — a missing input falls back to 'mid' / 'positive'
               / 'mid' so a note can still render.
               True (build) — a missing input raises ValueError naming it, so
               the caller drops the date. Building a table on the fallback was
               the WP-17.1 bug shape: a date with no credit reading is not a
               'mid' date, it is an unknown one.
    """
    missing: list[str] = []

    # --- NFCI tertile ---
    nfci_entry = snapshot.get("nfci", {})
    nfci_val   = nfci_entry.get("value")
    if nfci_val is None:
        missing.append("nfci")
        nfci_tier = "mid"
    else:
        v = float(nfci_val)
        if v < _NFCI_LOW_MID:
            nfci_tier = "low"
        elif v < _NFCI_MID_HIGH:
            nfci_tier = "mid"
        else:
            nfci_tier = "high"

    # --- Yield curve sign (10Y − 2Y) ---
    yc = snapshot.get("yield_curve_spread")
    if yc is None:
        t10 = snapshot.get("treasury_10y", {}).get("value")
        t2  = snapshot.get("treasury_2y",  {}).get("value")
        if t10 is not None and t2 is not None:
            yc = float(t10) - float(t2)
    if yc is not None:
        yc_label = "positive" if float(yc) >= 0 else "inverted"
    else:
        missing.append("yield_curve")
        yc_label = "positive"

    # --- Credit-spread tertile (BAA10Y) ---
    credit_val = snapshot.get(CREDIT_SERIES_KEY, {}).get("value")
    if credit_val is None:
        missing.append(CREDIT_SERIES_KEY)
        credit_tier = "mid"
    else:
        v = float(credit_val)
        if v < _CREDIT_LOW_MID:
            credit_tier = "tight"
        elif v < _CREDIT_MID_HIGH:
            credit_tier = "mid"
        else:
            credit_tier = "wide"

    if strict and missing:
        raise ValueError(f"bucket input(s) missing: {', '.join(missing)}")

    return f"NFCI:{nfci_tier}|YC:{yc_label}|CREDIT:{credit_tier}"


def build_bucket_index(
    historical_snapshots: list[tuple[date, dict]],
) -> dict[str, list[date]]:
    """
    Label every historical snapshot with its bucket; return the inverted index.

    Parameters
    ----------
    historical_snapshots : list of (snapshot_date, snapshot_dict) pairs

    Returns
    -------
    dict mapping bucket_label -> sorted list of dates in that bucket
    """
    index: dict[str, list[date]] = {}
    for snap_date, snapshot in historical_snapshots:
        bucket = assign_bucket(snapshot)
        index.setdefault(bucket, []).append(snap_date)
    for dates in index.values():
        dates.sort()
    return index


# ---------------------------------------------------------------------------
# Phase 11.2 — Lookup engine
# ---------------------------------------------------------------------------

def _bucket_drop_credit(bucket: str) -> str | None:
    """Drop the credit dimension: 'NFCI:X|YC:Y|CREDIT:Z' -> 'NFCI:X|YC:Y'."""
    parts     = bucket.split("|")
    filtered  = [p for p in parts if not p.startswith("CREDIT:")]
    if len(filtered) < len(parts) and filtered:
        return "|".join(filtered)
    return None


def _bucket_drop_yc(bucket: str) -> str | None:
    """Drop YC dimension: 'NFCI:X|YC:Y' -> 'NFCI:X'."""
    parts    = bucket.split("|")
    filtered = [p for p in parts if not p.startswith("YC:")]
    if len(filtered) < len(parts) and filtered:
        return "|".join(filtered)
    return None


def _compute_percentiles(returns: list[float]) -> dict:
    """Return p10/p25/p50/p75/p90 + n for a list of returns."""
    arr = np.array(returns, dtype=float)
    return {
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "n":   len(returns),
    }


def build_distribution_table(
    historical_snapshots: list[tuple[date, dict]],
    forward_returns: dict[str, dict[date, dict[int, float]]],
    min_n: int = 10,
    persist_path: Optional[Path] = None,
) -> dict:
    """
    Build empirical forward-return distribution table.

    For every bucket at every dimension level (full 3D, 2D parent, 1D
    grandparent), computes p10/p25/p50/p75/p90 + n per asset per horizon.
    Buckets with n < min_n are omitted from the table (lookup_distribution
    will naturally fall back to the pre-computed parent level).

    Parameters
    ----------
    historical_snapshots : list of (date, snapshot) pairs
    forward_returns : { asset: { date: { horizon_int: pct_return } } }
        pct_return is a decimal percentage (e.g. 2.3 for +2.3%)
    min_n : minimum observations required to include a bucket/asset/horizon
    persist_path : if not None, write table JSON here

    Returns
    -------
    Nested dict: { bucket_label: { asset: { horizon_int: {p10,...,n} } } }

    Schema example::

        {
          "NFCI:low|YC:positive|CREDIT:tight": {
            "S&P 500": {
              5: {"p10": -1.2, "p25": -0.3, "p50": 0.8, "p75": 1.9, "p90": 3.1, "n": 42}
            }
          }
        }
    """
    # Step 1: collect dates per bucket at every level
    # level_dates[bucket_label] = list of snapshot dates
    level_dates: dict[str, list[date]] = {}

    for snap_date, snapshot in historical_snapshots:
        full = assign_bucket(snapshot)
        level_dates.setdefault(full, []).append(snap_date)

        parent = _bucket_drop_credit(full)
        if parent:
            level_dates.setdefault(parent, []).append(snap_date)
            grandparent = _bucket_drop_yc(parent)
            if grandparent:
                level_dates.setdefault(grandparent, []).append(snap_date)

    # Also build a global "all" bucket
    all_dates = [d for d, _ in historical_snapshots]
    if all_dates:
        level_dates["all"] = all_dates

    # Step 2: compute distributions per bucket level
    table: dict = {}

    for bucket_label, dates in level_dates.items():
        bucket_dist: dict[str, dict[int, dict]] = {}

        for asset, date_returns in forward_returns.items():
            asset_dist: dict[int, dict] = {}
            for horizon in _HORIZONS:
                returns = [
                    date_returns[d][horizon]
                    for d in dates
                    if d in date_returns and horizon in date_returns[d]
                ]
                if len(returns) >= min_n:
                    asset_dist[horizon] = _compute_percentiles(returns)

            if asset_dist:
                bucket_dist[asset] = asset_dist

        if bucket_dist:
            table[bucket_label] = bucket_dist

    if persist_path is not None:
        _save_distribution_table(table, persist_path)

    return table


def _save_distribution_table(table: dict, path: Path) -> None:
    """Persist table to JSON, converting int horizon keys to strings."""
    def _convert(obj):
        if isinstance(obj, dict):
            return {str(k): _convert(v) for k, v in obj.items()}
        return obj

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_convert(table), fh, indent=2)


def load_distribution_table(path: Path = DEFAULT_TABLE_PATH) -> dict:
    """
    Load a persisted distribution table, restoring int horizon keys.

    Parameters
    ----------
    path : JSON file written by build_distribution_table(persist_path=...)
    """
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    def _restore(obj, depth: int):
        if not isinstance(obj, dict):
            return obj
        result = {}
        for k, v in obj.items():
            new_k: int | str
            if depth == 2:
                try:
                    new_k = int(k)
                except ValueError:
                    new_k = k
            else:
                new_k = k
            result[new_k] = _restore(v, depth + 1)
        return result

    return _restore(raw, 0)


def lookup_distribution(
    current_bucket: str,
    asset: str,
    horizon: int,
    table: dict,
) -> dict | None:
    """
    Return the distribution dict for (bucket, asset, horizon) with fallback.

    Fallback order:
      1. Exact bucket: 'NFCI:X|YC:Y|CREDIT:Z'
      2. Drop CREDIT:  'NFCI:X|YC:Y'
      3. Drop YC:      'NFCI:X'
      4. Global:       'all'

    Returns None if no data exists even after all fallbacks.

    Parameters
    ----------
    current_bucket : output of assign_bucket()
    asset          : asset name, e.g. 'S&P 500'
    horizon        : integer, one of 5 / 10 / 20
    table          : output of build_distribution_table()
    """
    def _try(bucket: str) -> dict | None:
        if bucket in table and asset in table[bucket]:
            return table[bucket][asset].get(horizon)
        return None

    result = _try(current_bucket)
    if result is not None:
        return result

    parent = _bucket_drop_credit(current_bucket)
    if parent:
        result = _try(parent)
        if result is not None:
            return result
        grandparent = _bucket_drop_yc(parent)
        if grandparent:
            result = _try(grandparent)
            if result is not None:
                return result

    return _try("all")


def _identify_sparse_buckets(table: dict, min_n: int = 20) -> frozenset[str]:
    """
    Return the set of full 3D bucket labels whose distributions are sparse
    (any asset at any horizon has n < min_n, or the bucket is absent).

    Used to update the SPARSE_BUCKETS module constant after a table rebuild.
    """
    all_full_buckets: set[str] = set()
    for nfci in ("low", "mid", "high"):
        for yc in ("positive", "inverted"):
            for credit in ("tight", "mid", "wide"):
                all_full_buckets.add(f"NFCI:{nfci}|YC:{yc}|CREDIT:{credit}")

    sparse: set[str] = set()
    for bucket in all_full_buckets:
        if bucket not in table:
            sparse.add(bucket)
            continue
        for asset_dist in table[bucket].values():
            for horizon_dist in asset_dist.values():
                if horizon_dist.get("n", 0) < min_n:
                    sparse.add(bucket)
                    break
            if bucket in sparse:
                break

    return frozenset(sparse)


# ---------------------------------------------------------------------------
# Phase 11.3 — Lookahead-safe computation for backtesting
# ---------------------------------------------------------------------------

def build_distribution_table_for_backtest(
    historical_snapshots: list[tuple[date, dict]],
    forward_returns: dict[str, dict[date, dict[int, float]]],
    as_of_date: date,
    max_horizon: int = 20,
    min_n: int = 10,
) -> dict:
    """
    Build distribution table using only observations knowable by as_of_date.

    A forward return for snapshot_date at horizon h is "known" when the price
    on snapshot_date + h calendar days has been observed.  This function filters
    to observations where snapshot_date + max_horizon <= as_of_date, preventing
    any look-ahead bias in the backtest harness.

    Parameters
    ----------
    historical_snapshots : list of (date, snapshot) pairs
    forward_returns : { asset: { date: { horizon_int: pct_return } } }
    as_of_date : the date from which the table is being computed
    max_horizon : maximum horizon in calendar days (default 20)
    min_n : minimum observations per bucket/asset/horizon
    """
    cutoff = as_of_date - timedelta(days=max_horizon)
    filtered = [
        (snap_date, snapshot)
        for snap_date, snapshot in historical_snapshots
        if snap_date <= cutoff
    ]
    return build_distribution_table(filtered, forward_returns, min_n=min_n)
