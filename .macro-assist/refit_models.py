"""
refit_models.py — Weekly model refit for the quantitative context layer.

Called by macro_weekly_refit.yml every Sunday 22:00 UTC.

Steps:
    1. Fetch FRED data from conditional.TABLE_START (one call per series)
    2. Fetch yfinance price history from TABLE_START for the six registry assets
    3. (retired, KB-006) Build the 4-feature matrix and refit the HMM — only
       when REGIME_ENABLED=1
    4. Build forward-return dict and rebuild the conditional distribution table
       → data/conditional_distributions.json

The table's date range is every business day from TABLE_START on which all
three bucket inputs (NFCI, 10Y−2Y, BAA10Y) have a reading. Until 2026-09-13 it
was the HMM feature matrix's valid rows on a 5-year fetch, which capped it at
~3 years (WP-17.5).

Idempotent: re-running in the same week with the same market data produces
identical artifacts (same random_state, same training window).
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from fredapi import Fred

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from regime import fit_regime_model, DEFAULT_MODEL_PATH, regime_enabled
from conditional import (
    assign_bucket, build_distribution_table, DEFAULT_TABLE_PATH, TABLE_START,
    CREDIT_SERIES_KEY,
)
from assets import ASSETS, BY_KEY, HORIZONS, forward_change

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The asset universe and its return conventions now come from the registry
# (`assets.py`) rather than a local dict, so the build side, the render side and
# the distribution scorer cannot drift apart. Extended from three assets to six
# alongside the distribution scorer: the note's "no conditional base rate" rows
# for the 10Y, DXY and Bitcoin were a build-side limit (this dict had three
# tickers in it), not thin data.
_ASSETS: dict[str, str] = {a.key: a.ticker for a in ASSETS}

_HORIZONS: tuple[int, ...] = HORIZONS

_FRED_SERIES: dict[str, str] = {
    "nfci":         "NFCI",
    "treasury_10y": "DGS10",
    "treasury_2y":  "DGS2",
    # Credit spread, for both the bucket's credit tertile and the (retired) HMM
    # z-score feature. FRED serves the ICE BofA HY OAS (BAMLH0A0HYM2) as a
    # ~3-year rolling window — it truncated the HMM fit (WP-17.1) and then the
    # conditional table itself (WP-17.5). BAA10Y (Moody's Baa − 10Y, daily since
    # 1986) is the long-history credit-stress series; CREDIT_SERIES_KEY names
    # the snapshot key so conditional.assign_bucket reads the same one.
    CREDIT_SERIES_KEY: "BAA10Y",
}

# NFCI clipping bounds (long-run historical range, matching regime_features.py)
_NFCI_MIN: float = -0.9
_NFCI_MAX: float =  2.8

# Credit-spread typical std for the regime z-score feature (matching
# regime_features.py). BAA10Y deviations from a 5y mean run ~±0.5pp.
_BAA_STD: float = 0.5

# Minimum valid history days required before fitting
_MIN_FIT_DAYS: int = 252

# Rolling window for the credit-spread 5yr mean (252 bdays/yr × 5), HMM feature [2]
_HY_MEAN_WINDOW: int = 1260


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(section: str, msg: str) -> None:
    print(f"[{section:<12}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_fred_series(fred: Fred, start: date = TABLE_START) -> dict[str, pd.Series]:
    """Return the bucket-input FRED series from `start` (default TABLE_START)."""
    start = start.isoformat()
    series: dict[str, pd.Series] = {}
    for key, sid in _FRED_SERIES.items():
        try:
            s = fred.get_series(sid, observation_start=start)
            if s is not None and not s.empty:
                series[key] = s.dropna()
                _log("FRED", f"{key}: {len(series[key])} observations")
            else:
                _log("FRED", f"WARN: {key} ({sid}) returned empty")
        except Exception as exc:
            _log("FRED", f"WARN: {key} ({sid}) failed: {exc}")
    return series


def _fetch_price_history(start: date = TABLE_START) -> dict[str, pd.Series]:
    """Return daily Close price series from yfinance for all registry assets.

    Assets whose history begins after `start` (Bitcoin, 2014-09) simply
    contribute fewer forward-return observations; the bucket dates are the
    same for every asset.
    """
    start = start.isoformat()
    prices: dict[str, pd.Series] = {}
    for name, ticker in _ASSETS.items():
        try:
            hist = yf.download(ticker, start=start, progress=False, auto_adjust=True)
            if hist.empty:
                _log("MARKET", f"WARN: {name} ({ticker}) returned empty")
                continue
            close = hist["Close"].squeeze().ffill().dropna()
            prices[name] = close
            _log("MARKET", f"{name}: {len(close)} trading days")
        except Exception as exc:
            _log("MARKET", f"WARN: {name} ({ticker}) failed: {exc}")
    return prices


# ---------------------------------------------------------------------------
# Feature matrix
# ---------------------------------------------------------------------------

def _build_feature_matrix(
    fred_series: dict[str, pd.Series],
    sp500_close: pd.Series,
) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """
    Build (n_days, 4) feature matrix aligned to business days.

    Features (matching regime_features.py):
        [0] NFCI percentile        (0–1, clipped to long-run range)
        [1] Yield curve slope      (10Y − 2Y, raw basis points)
        [2] Credit spread z-score  BAA10Y ((value − 5yr_mean) / _BAA_STD)
        [3] SP500 60d vol pct      (0–100, trailing 252d percentile)

    Returns
    -------
    (feature_matrix, valid_dates) — rows with any NaN are dropped.
    """
    # Business-day index: start after 252d of SP500 history so vol pct is valid
    bday_start = sp500_close.index[0] + pd.offsets.BDay(252)
    bday_end   = sp500_close.index[-1]
    bdays      = pd.bdate_range(start=bday_start, end=bday_end)

    if len(bdays) == 0:
        return np.empty((0, 4)), pd.DatetimeIndex([])

    # --- Feature 0: NFCI percentile ---
    nfci_raw = fred_series.get("nfci", pd.Series(dtype=float))
    nfci_d   = nfci_raw.reindex(bdays, method="ffill")
    f0 = np.clip(
        (nfci_d.values - _NFCI_MIN) / (_NFCI_MAX - _NFCI_MIN),
        0.0, 1.0,
    )

    # --- Feature 1: Yield curve slope (bps) ---
    t10 = fred_series.get("treasury_10y", pd.Series(dtype=float))
    t2  = fred_series.get("treasury_2y",  pd.Series(dtype=float))
    if not t10.empty and not t2.empty:
        spread = (t10 - t2).reindex(bdays, method="ffill") * 100  # % → bps
    else:
        spread = pd.Series(np.nan, index=bdays)
    f1 = spread.values

    # --- Feature 2: Credit-spread z-score (BAA10Y, long history) ---
    baa      = fred_series.get("baa_spread", pd.Series(dtype=float))
    baa_d    = baa.reindex(bdays, method="ffill")
    baa_mean = baa_d.rolling(window=_HY_MEAN_WINDOW, min_periods=_MIN_FIT_DAYS).mean()
    f2       = ((baa_d - baa_mean) / _BAA_STD).values

    # --- Feature 3: SP500 60d vol percentile ---
    sp_d     = sp500_close.reindex(bdays, method="ffill")
    log_ret  = np.log(sp_d / sp_d.shift(1)).values
    rv_ser   = pd.Series(log_ret ** 2, index=bdays)
    vol_60   = (rv_ser.rolling(60).mean() ** 0.5) * np.sqrt(252) * 100
    f3       = vol_60.rolling(252).apply(
        lambda x: float(np.mean(x <= x.iloc[-1])) * 100, raw=False
    ).values

    # --- Stack and drop rows with any NaN ---
    mat   = np.column_stack([f0, f1, f2, f3])
    valid = ~np.isnan(mat).any(axis=1)
    valid_mat   = mat[valid]
    valid_dates = bdays[valid]

    _log("FEATURES", f"{valid_mat.shape[0]} valid days (of {len(bdays)} business days)")
    return valid_mat, valid_dates


# ---------------------------------------------------------------------------
# Forward returns + snapshot stubs
# ---------------------------------------------------------------------------

def _build_forward_returns(
    prices: dict[str, pd.Series],
    dates: pd.DatetimeIndex,
) -> dict[str, dict[date, dict[int, float]]]:
    """
    Compute N-trading-day forward returns for each asset on each date in `dates`.

    Only dates where the forward price exists (i.e. not at/near the tail) are
    included — the distribution table will simply have fewer observations near
    the current date.
    """
    forward_returns: dict[str, dict[date, dict[int, float]]] = {
        name: {} for name in _ASSETS
    }

    for name, close in prices.items():
        asset = BY_KEY.get(name)
        if asset is None:
            continue
        aligned = close.reindex(dates, method="ffill").ffill().dropna()
        arr     = aligned.values
        idx_map = {ts: i for i, ts in enumerate(aligned.index)}

        for ts in dates:
            if ts not in idx_map:
                continue
            i = idx_map[ts]
            d = ts.date()
            day_ret: dict[int, float] = {}
            for h in _HORIZONS:
                j = i + h
                if j >= len(arr):
                    continue
                # Per-asset convention, from the registry: a percent return for
                # price assets, an absolute basis-point change for the 10Y yield
                # level. Computing this inline as a pct return is the
                # percent-of-a-percent bug `score_predictions` documents.
                try:
                    day_ret[h] = round(forward_change(float(arr[i]), float(arr[j]), asset), 4)
                except (ValueError, ZeroDivisionError):
                    continue
            if day_ret:
                forward_returns[name][d] = day_ret

    return forward_returns


def _table_dates(
    fred_series: dict[str, pd.Series],
    prices: dict[str, pd.Series],
) -> pd.DatetimeIndex:
    """
    Business days the table is built over: TABLE_START → last SP500 close.

    Decoupled from the HMM feature matrix (whose 252-day warm-ups, not the data,
    set the old ~3-year range). Dates missing a bucket input are dropped by
    `_build_snapshot_stubs`, not here.
    """
    sp = prices.get("SP500")
    if sp is None or sp.empty:
        return pd.DatetimeIndex([])
    return pd.bdate_range(start=pd.Timestamp(TABLE_START), end=sp.index[-1])


def _build_snapshot_stubs(
    fred_series: dict[str, pd.Series],
    dates: pd.DatetimeIndex,
) -> tuple[list[tuple[date, dict]], int]:
    """
    Build minimal snapshot dicts for assign_bucket(); returns (stubs, dropped).

    A date on which any bucket input has no forward-filled reading is
    **dropped**, not labelled: `assign_bucket(strict=True)` raises and the date
    is counted in `dropped`. The live-side fallback to 'mid' is fine for
    rendering one note; a table built on it would label the unknown as the
    middle tertile, which is the WP-17.1 bug shape (KB-003).
    """
    def _ffill_to(key: str) -> pd.Series:
        s = fred_series.get(key)
        if s is None or s.empty:
            return pd.Series(np.nan, index=dates)
        return s.reindex(dates, method="ffill")

    nfci_d = _ffill_to("nfci")
    t10_d  = _ffill_to("treasury_10y")
    t2_d   = _ffill_to("treasury_2y")
    cr_d   = _ffill_to(CREDIT_SERIES_KEY)

    snapshots: list[tuple[date, dict]] = []
    dropped = 0
    for ts in dates:
        snap: dict = {}
        nv = nfci_d.get(ts, np.nan)
        if not np.isnan(nv):
            snap["nfci"] = {"value": float(nv)}

        t10v = t10_d.get(ts, np.nan)
        t2v  = t2_d.get(ts, np.nan)
        if not np.isnan(t10v) and not np.isnan(t2v):
            snap["treasury_10y"] = {"value": float(t10v)}
            snap["treasury_2y"]  = {"value": float(t2v)}

        crv = cr_d.get(ts, np.nan)
        if not np.isnan(crv):
            snap[CREDIT_SERIES_KEY] = {"value": float(crv)}

        try:
            assign_bucket(snap, strict=True)
        except ValueError:
            dropped += 1
            continue
        snapshots.append((ts.date(), snap))

    return snapshots, dropped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("refit_models.py — weekly quantitative model refit")
    print("=" * 55)

    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        _log("ABORT", "FRED_API_KEY not set")
        sys.exit(1)

    fred = Fred(api_key=fred_api_key)

    _log("STEP", "1/4  Fetching FRED series ...")
    fred_series = _fetch_fred_series(fred)

    _log("STEP", "2/4  Fetching price history ...")
    prices = _fetch_price_history()

    sp500_close = prices.get("SP500")
    if sp500_close is None or len(sp500_close) < _MIN_FIT_DAYS + 60:
        _log("ABORT", f"SP500 price history too short ({len(sp500_close) if sp500_close is not None else 0} days)")
        sys.exit(1)

    # REGIME-RETIRED (KB-006): the feature matrix and HMM fit only run when
    # explicitly re-enabled. The stale regime_model.pkl is left untouched (the
    # gate is off too). The conditional table no longer borrows the matrix's
    # valid rows for its date range — see _table_dates.
    if regime_enabled():
        _log("STEP", "3/4  Building regime feature matrix ...")
        feature_matrix, _ = _build_feature_matrix(fred_series, sp500_close)
        if len(feature_matrix) < _MIN_FIT_DAYS:
            _log("ABORT", f"Only {len(feature_matrix)} valid days — need ≥{_MIN_FIT_DAYS}")
            sys.exit(1)
        fit_regime_model(feature_matrix, model_path=DEFAULT_MODEL_PATH)
        _log("REGIME", f"HMM fitted on {len(feature_matrix)} days → {DEFAULT_MODEL_PATH.name}")
    else:
        _log("STEP", "3/4  Regime feature matrix ...")
        _log("REGIME", "HMM regime retired (KB-006) — skipping fit (set REGIME_ENABLED=1 to revive)")

    _log("STEP", "4/4  Building conditional distribution table ...")
    table_dates              = _table_dates(fred_series, prices)
    snapshot_stubs, dropped  = _build_snapshot_stubs(fred_series, table_dates)
    if not snapshot_stubs:
        _log("ABORT", "no business day has all three bucket inputs — table not rebuilt")
        sys.exit(1)
    stub_dates = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in snapshot_stubs])
    forward_returns = _build_forward_returns(prices, stub_dates)

    n_returns = sum(len(v) for v in forward_returns.values())
    _log("COND", f"{len(snapshot_stubs)} bucket dates {snapshot_stubs[0][0]} → "
                 f"{snapshot_stubs[-1][0]} ({dropped} dropped for a missing input)")
    _log("COND", f"{n_returns} forward-return observations across {len(_ASSETS)} assets")

    table = build_distribution_table(
        snapshot_stubs,
        forward_returns,
        persist_path=DEFAULT_TABLE_PATH,
    )
    _log("COND", f"{len(table)} buckets written → {DEFAULT_TABLE_PATH.name}")

    print("\nRefit complete.")
    print(f"  Regime model  : {DEFAULT_MODEL_PATH}")
    print(f"  Distributions : {DEFAULT_TABLE_PATH}")


if __name__ == "__main__":
    main()
