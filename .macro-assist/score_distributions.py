"""
score_distributions.py — Score the v1.6 conditional-distribution product.

What replaced what
------------------
`score_predictions.py` scored a directional call. v1.6 cut that call (WP-21.D,
[KB-024]) and published the empirical conditional distribution — median, P25,
P75, n — in its place. This module scores *that*: it is the successor scorer, not
a companion. The old one keeps running until the last v1.5 note's T+20 window
resolves (~2026-10-02) and then retires; it is deliberately left untouched so
[KB-007]/[KB-011]/[KB-022] stay reproducible.

The input is already point-in-time, and that is the whole reason this is cheap
--------------------------------------------------------------------------------
`results/quant_context_log/YYYY-MM-DD.jsonl` carries the exact distribution the
note published that day. The table it was drawn from was fit at the prior weekly
refit, so a logged quantile is knowable at *t* by construction — there is no
vintage to reconstruct and no look-ahead to argue about. The realization is
simply what happened after. Every comparator below is held to the same standard:
it may only see prices dated **strictly on or before the report date**.

The comparator is the test, not a footnote
------------------------------------------
[KB-024] scored two model classes as skilled-looking until a constant beat them.
[KB-026] and [KB-027] then found two feature families that made a panel *worse*
while looking like additions. The lesson those three paid for is that a scoring
system without a trivial rival measures nothing. So the published distribution is
scored against:

  ``unconditional``  the same asset's full-history forward-return quantiles, no
                     macro bucket at all. **This is the benchmark.** The entire
                     claim of the conditional layer is that conditioning on
                     ``NFCI|YC|HY`` beats not conditioning. If it does not beat
                     this, the bucket machinery is decoration and should be said
                     to be decoration.
  ``trailing_250``   the same, over the last 250 trading days only — a "recent
                     regime" rival that needs no macro state either.
  ``har_gaussian``   zero-mean Normal scaled by the HAR-RV forecast already in
                     the log. Optional: only some assets carry a vol forecast, so
                     it is scored on its own subsample and never silently pooled
                     (WP-21.A.2: comparators must not be handed free sample).

Units do not pool
-----------------
Pinball loss is in the asset's own unit — percent for prices, basis points for
the 10Y yield level (see `assets.py`). A mean pinball loss across assets would be
adding bp to %, so per-asset is the primary read and any pooled figure is an
equal-weighted mean of per-asset *skill scores*, which are unit-free. Coverage
and PIT bins are unit-free and pool directly.

Overlap
-------
Daily notes at a 5-day horizon overlap 80%; at 20 days, 95%. Raw n is not
evidence. Interval estimates use a block bootstrap over whole 21-report-date
blocks, the same block definition `bias_separation.py` uses, so no two
observations in different blocks share an evaluation window.

Usage
-----
    python .macro-assist/score_distributions.py            # score what resolved
    python .macro-assist/score_distributions.py --rebuild  # rescore everything
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
import sys
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from assets import ASSETS, BY_KEY, ORIGINAL_KEYS, Asset, forward_change

try:
    yf.set_tz_cache_location(tempfile.mkdtemp(prefix="yf_tz_"))
except Exception:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "results"
QUANT_LOG_DIR = Path(os.environ.get("MACRO_QUANT_LOG_DIR", RESULTS_DIR / "quant_context_log"))
DIST_SCORES_DIR = RESULTS_DIR / "dist_scores"

# The quantiles the note publishes. The table holds p10/p90 too, but the
# *claim* is these three, and a scorer must score the claim that was made.
QUANTILES: tuple[float, ...] = (0.25, 0.50, 0.75)
_Q_KEYS = {0.25: "p25", 0.50: "p50", 0.75: "p75"}

# Horizons present in the log. Only 5d is published in the note's outlook table;
# 20d is logged and unpublished, so it is scored and tagged rather than dropped —
# it is free out-of-sample evidence about the same mechanism.
HORIZONS: tuple[int, ...] = (5, 20)
PUBLISHED_HORIZON = 5

# Extra calendar days after the evaluation date before scoring, so the market has
# closed and yfinance has the bar. Same convention as score_predictions.
BUFFER_DAYS = 1

# Minimum history a comparator needs before it is allowed to quote a quantile.
# Below this the empirical quantiles are noise dressed as a benchmark.
MIN_COMPARATOR_N = 100
TRAILING_WINDOW = 250

# Block length in report-dates. 21 matches bias_separation.BLOCK_DAYS and the
# 20-day horizon: two observations in different blocks share no eval window.
BLOCK_DAYS = 21
N_BOOT = 2000
SEED = 7

# Minimum independent blocks an asset needs before it is allowed a vote in a
# pooled skill number. An asset below this has no bootstrap CI of its own (the
# block bootstrap needs >=2 blocks), so pooling it would let a point estimate
# with no measurable spread move the headline. The universe goes from three
# assets to six on the 2026-09-13 refit, and without this gate an asset five
# report dates old would carry the same weight as one with a year of record.
# Excluded assets are named in the report rather than silently dropped.
MIN_POOL_BLOCKS = 2

# Years of price history to pull. Needs to cover the deepest comparator window
# plus the earliest report date in the log.
HISTORY_YEARS = 12

ARMS = ("published", "unconditional", "trailing_250", "har_gaussian")
# Arms every scored observation must carry. `har_gaussian` is deliberately
# absent: it depends on a logged vol forecast that not every asset has, and
# requiring it would drop whole assets rather than one comparator.
REQUIRED_ARMS = ("published", "unconditional", "trailing_250")

# Maps the log's vol_forecast keys onto asset keys. The vol block is keyed by
# note-ish display names that predate the registry.
_VOL_LOG_KEYS: dict[str, str] = {
    "SP500": "SP500", "Gold": "Gold", "WTI Oil": "WTI Oil", "Bitcoin": "Bitcoin",
}

TRADING_DAYS_PER_YEAR = 252


def _log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}")


# ---------------------------------------------------------------------------
# Reading the published record
# ---------------------------------------------------------------------------

def load_quant_log(log_dir: Path | None = None) -> list[dict]:
    """Return every daily quant-context record, sorted by date.

    One JSONL file per day, normally one line. A malformed line is skipped with a
    warning rather than aborting the run: a single bad day must not be able to
    stop the forward record from being scored.
    """
    log_dir = log_dir or QUANT_LOG_DIR
    records: list[dict] = []
    if not log_dir.exists():
        return records

    for path in sorted(log_dir.glob("*.jsonl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                _log("WARN", f"{path.name}:{lineno} is not valid JSON — skipped")
                continue
            if rec.get("date"):
                records.append(rec)
    records.sort(key=lambda r: r["date"])
    return records


def published_claims(record: dict) -> list[dict]:
    """Flatten one daily record into the distribution claims it published.

    Returns dicts of {asset_key, horizon, p25, p50, p75, n, bucket}. A row with a
    missing or non-numeric quantile is dropped — an incomplete distribution is
    not a claim, and inventing the missing leg would be scoring something the
    note never said.
    """
    cond = (record or {}).get("conditional") or {}
    dists = cond.get("distributions") or {}
    bucket = cond.get("bucket") or ""
    out: list[dict] = []

    for label, d in dists.items():
        if not isinstance(d, dict) or not label.endswith("d"):
            continue
        key, _, horizon_str = label.rpartition("_")
        try:
            horizon = int(horizon_str[:-1])
        except ValueError:
            continue
        if key not in BY_KEY or horizon not in HORIZONS:
            continue

        # The log's shape changed when the distribution became the published
        # product: before 2026-09-07 only `p50` was written, from then on the
        # full p25/p50/p75 triple. Both are real claims of different strength,
        # so score whatever was actually claimed and tag it, rather than
        # discarding 71 days of median record for want of an interval that was
        # never logged. The median is the floor: a claim without it is not one.
        quantiles: dict[float, float] = {}
        for q, qk in _Q_KEYS.items():
            v = d.get(qk)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(v):
                quantiles[q] = float(v)
        if 0.50 not in quantiles:
            continue

        out.append({
            "asset_key": key,
            "horizon": horizon,
            "quantiles": quantiles,
            "n": d.get("n", 0),
            "bucket": bucket,
        })
    return out


def logged_har_sigma(record: dict, asset_key: str) -> float | None:
    """Annualised HAR-RV vol (percent) logged for `asset_key`, or None.

    The log stores `forecast_daily_vol` under a display key; despite the name the
    value is the annualised forecast in percent (a 16.96 next to a VIX of 15.3 is
    not a daily number). Read it as annualised and convert once, here.
    """
    vol_key = _VOL_LOG_KEYS.get(asset_key)
    if not vol_key:
        return None
    block = ((record or {}).get("vol_forecasts") or {}).get(vol_key) or {}
    v = block.get("forecast_daily_vol")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        return None
    return float(v)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

def fetch_history(years: int = HISTORY_YEARS) -> dict[str, pd.Series]:
    """Daily closes per asset key, indexed by naive date, sorted and deduped."""
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    out: dict[str, pd.Series] = {}
    for a in ASSETS:
        try:
            raw = yf.download(a.ticker, start=start, progress=False, auto_adjust=True)
            if raw is None or raw.empty:
                _log("WARN", f"{a.key} ({a.ticker}): empty history — asset skipped")
                continue
            close = raw["Close"].squeeze().dropna()
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            close = close[~close.index.duplicated(keep="last")].sort_index()
            out[a.key] = close
            _log("PRICES", f"{a.key}: {len(close)} trading days")
        except Exception as exc:
            _log("WARN", f"{a.key} ({a.ticker}) fetch failed: {exc}")
    return out


def _entry_index(series: pd.Series, report_date: date) -> int | None:
    """Position of the last close at or before `report_date`.

    The note is generated pre-open from the prior close, so the entry is the last
    bar the pipeline could actually have seen. Returns None when the report
    predates the series.
    """
    idx = series.index.searchsorted(pd.Timestamp(report_date), side="right") - 1
    return int(idx) if idx >= 0 else None


def realized_change(series: pd.Series, report_date: date, horizon: int,
                    asset: Asset) -> tuple[float, date, float, float] | None:
    """(change, eval_date, entry, exit) `horizon` *trading days* after the entry.

    Trading days are counted off the actual price index rather than by counting
    weekdays, so market holidays do not quietly shorten the window. Returns None
    when the window has not closed yet.
    """
    i = _entry_index(series, report_date)
    if i is None:
        return None
    j = i + horizon
    if j >= len(series):
        return None
    entry, exit_ = float(series.iloc[i]), float(series.iloc[j])
    try:
        change = forward_change(entry, exit_, asset)
    except (ValueError, KeyError):
        return None
    return change, series.index[j].date(), entry, exit_


# ---------------------------------------------------------------------------
# Comparators — each may see only prices dated <= report_date
# ---------------------------------------------------------------------------

def _historical_changes(series: pd.Series, upto: date, horizon: int,
                        asset: Asset, window: int | None = None) -> list[float]:
    """Forward changes over `horizon` that were fully observable by `upto`.

    The last usable entry is `horizon` bars before the cutoff — a later one has
    an unobserved exit, and including it is exactly the look-ahead this whole
    module exists to avoid. `window` limits how far back to look (in entries).
    """
    cut = _entry_index(series, upto)
    if cut is None:
        return []
    last_entry = cut - horizon
    if last_entry < 0:
        return []

    first_entry = 0 if window is None else max(0, last_entry - window + 1)
    vals = series.values
    changes: list[float] = []
    for i in range(first_entry, last_entry + 1):
        try:
            changes.append(forward_change(float(vals[i]), float(vals[i + horizon]), asset))
        except (ValueError, KeyError):
            continue
    return changes


def _empirical_quantiles(changes: list[float],
                         quantiles: tuple[float, ...] = QUANTILES) -> dict[float, float] | None:
    if len(changes) < MIN_COMPARATOR_N:
        return None
    s = sorted(changes)
    return {q: float(_quantile(s, q)) for q in quantiles}


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation quantile on an already-sorted list."""
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# Normal quantiles at 0.25 / 0.50 / 0.75.
_Z = {0.25: -0.6744897501960817, 0.50: 0.0, 0.75: 0.6744897501960817}


def _gaussian_quantiles(sigma_annual_pct: float, horizon: int, asset: Asset,
                        quantiles: tuple[float, ...] = QUANTILES) -> dict[float, float] | None:
    """Zero-mean Normal quantiles from an annualised vol, scaled to `horizon`.

    Returns None for a level asset: the HAR forecast is a percent-return vol and
    converting it into a basis-point yield move needs the yield level, which
    would make this comparator a different model. Better to have no comparator
    than a wrong one.
    """
    if asset.is_level or sigma_annual_pct <= 0:
        return None
    sigma_h = sigma_annual_pct * math.sqrt(horizon / TRADING_DAYS_PER_YEAR)
    return {q: _Z[q] * sigma_h for q in quantiles}


# ---------------------------------------------------------------------------
# Scoring rules
# ---------------------------------------------------------------------------

def pinball_loss(realized: float, forecast: float, q: float) -> float:
    """Quantile (pinball) loss — the proper scoring rule for a quantile forecast.

    This is the distribution product's Brier score: minimised in expectation only
    by the true q-quantile, so a forecaster cannot improve it by shading the
    interval wider or narrower.
    """
    diff = realized - forecast
    return q * diff if diff >= 0 else (q - 1.0) * diff


def score_quantiles(realized: float, quantiles: dict[float, float]) -> dict:
    """Pinball losses at each quantile plus their mean."""
    per_q = {str(q): round(pinball_loss(realized, f, q), 6)
             for q, f in sorted(quantiles.items())}
    return {"pinball": per_q,
            "pinball_mean": round(st.mean(per_q.values()), 6)}


def pit_bin(realized: float, quantiles: dict[float, float]) -> int:
    """Which quarter of the published distribution the realization landed in.

    0: below P25 · 1: P25–P50 · 2: P50–P75 · 3: above P75.
    A calibrated distribution puts 25% of realizations in each. With only three
    published quantiles this four-bin histogram is the whole PIT that can be
    honestly computed — it is not coarse by choice.
    """
    if realized < quantiles[0.25]:
        return 0
    if realized < quantiles[0.50]:
        return 1
    if realized < quantiles[0.75]:
        return 2
    return 3


# ---------------------------------------------------------------------------
# Building observations
# ---------------------------------------------------------------------------

def build_observations(records: list[dict], prices: dict[str, pd.Series],
                       today: date | None = None) -> list[dict]:
    """One observation per (report_date, asset, horizon) whose window has closed.

    Sample alignment (WP-21.A.2): an observation is emitted only when every arm
    in REQUIRED_ARMS could quote a distribution for it. A comparator that cannot
    score a day must not be compared on a *different* set of days than the arm it
    is being measured against — that is precisely how `always_bullish` was
    handed 3,000 free calls.
    """
    today = today or date.today()
    observations: list[dict] = []

    for record in records:
        try:
            report_date = date.fromisoformat(record["date"])
        except (KeyError, ValueError):
            continue

        for claim in published_claims(record):
            asset = BY_KEY[claim["asset_key"]]
            horizon = claim["horizon"]
            series = prices.get(asset.key)
            if series is None:
                continue

            realized = realized_change(series, report_date, horizon, asset)
            if realized is None:
                continue
            change, eval_date, entry, exit_ = realized
            if eval_date + timedelta(days=BUFFER_DAYS) > today:
                continue

            # Every arm quotes exactly the quantiles the note claimed that day,
            # so a mean pinball loss compares like with like. Scoring a
            # comparator on three quantiles against a median-only claim would
            # hand it a different loss scale and call the difference skill.
            claimed = tuple(sorted(claim["quantiles"]))

            arms: dict[str, dict] = {}
            arms["published"] = {"quantiles": claim["quantiles"], "n": claim["n"]}

            full = _historical_changes(series, report_date, horizon, asset)
            uncond = _empirical_quantiles(full, claimed)
            if uncond:
                arms["unconditional"] = {"quantiles": uncond, "n": len(full)}

            recent = _historical_changes(series, report_date, horizon, asset,
                                         window=TRAILING_WINDOW)
            trailing = _empirical_quantiles(recent, claimed)
            if trailing:
                arms["trailing_250"] = {"quantiles": trailing, "n": len(recent)}

            sigma = logged_har_sigma(record, asset.key)
            if sigma is not None:
                gq = _gaussian_quantiles(sigma, horizon, asset, claimed)
                if gq:
                    arms["har_gaussian"] = {"quantiles": gq, "sigma_annual_pct": sigma}

            if any(a not in arms for a in REQUIRED_ARMS):
                continue

            scored = {name: {**score_quantiles(change, arm["quantiles"]),
                             "quantiles": {str(q): round(v, 4)
                                           for q, v in sorted(arm["quantiles"].items())}}
                      for name, arm in arms.items()}

            pq = claim["quantiles"]
            has_interval = 0.25 in pq and 0.75 in pq
            observations.append({
                "date": report_date.isoformat(),
                "asset": asset.key,
                "note_name": asset.note_name,
                "unit": asset.unit,
                "horizon": horizon,
                "published_in_note": horizon == PUBLISHED_HORIZON,
                # "iqr" = the full P25/P50/P75 claim the note publishes since
                # v1.6; "median" = the median-only record the log carried before
                # p25/p75 were added on 2026-09-07. Coverage and PIT are only
                # defined for the former, which is why this tag exists at all.
                "claim": "iqr" if has_interval else "median",
                "bucket": claim["bucket"],
                "bucket_n": claim["n"],
                "eval_date": eval_date.isoformat(),
                "entry": round(entry, 4),
                "exit": round(exit_, 4),
                "realized": round(change, 4),
                "pit_bin": pit_bin(change, pq) if has_interval else None,
                "inside_iqr": bool(pq[0.25] <= change <= pq[0.75]) if has_interval else None,
                "above_median": bool(change > pq[0.50]),
                "arms": scored,
            })

    return observations


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _blocks_of_dates(dates: list[str]) -> list[list[str]]:
    return [dates[i:i + BLOCK_DAYS] for i in range(0, len(dates), BLOCK_DAYS)]


def block_bootstrap(obs: list[dict], statistic, n_boot: int = N_BOOT,
                    seed: int = SEED, alpha: float = 0.05) -> dict | None:
    """Block-bootstrap CI for any statistic of a set of observations.

    Resamples whole 21-report-date blocks with replacement, so the within-block
    overlap that makes daily 5- and 20-day observations dependent is preserved.
    An iid interval on this data would be roughly sqrt(5) to sqrt(20) too narrow,
    which is the difference between "calibrated" and "not established".
    """
    by_date: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        by_date[o["date"]].append(o)
    dates = sorted(by_date)
    blocks = _blocks_of_dates(dates)
    if len(blocks) < 2:
        return None

    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_boot):
        flat = [o for blk in (rng.choice(blocks) for _ in blocks)
                for d in blk for o in by_date[d]]
        v = statistic(flat)
        if v is not None:
            draws.append(v)
    if len(draws) < n_boot // 2:
        return None

    draws.sort()
    lo = draws[int((alpha / 2) * len(draws))]
    hi = draws[min(int((1 - alpha / 2) * len(draws)), len(draws) - 1)]
    return {"lo": round(lo, 4), "hi": round(hi, 4), "n_boot": len(draws),
            "n_blocks": len(blocks)}


def _mean_pinball(obs: list[dict], arm: str) -> float | None:
    vals = [o["arms"][arm]["pinball_mean"] for o in obs if arm in o["arms"]]
    return st.mean(vals) if vals else None


def skill_vs(obs: list[dict], arm: str, benchmark: str = "unconditional") -> float | None:
    """1 - mean_pinball(arm) / mean_pinball(benchmark), on the shared subsample.

    Positive means the arm beats the benchmark. Computed only over observations
    where *both* arms scored, so a comparator is never credited for days its
    rival could not see.
    """
    paired = [o for o in obs if arm in o["arms"] and benchmark in o["arms"]]
    if not paired:
        return None
    num = _mean_pinball(paired, arm)
    den = _mean_pinball(paired, benchmark)
    if num is None or den is None or den <= 0:
        return None
    return 1.0 - num / den


def pooled_skill(obs: list[dict], arm: str = "published",
                 keys: set[str] | frozenset[str] | None = None,
                 benchmark: str = "unconditional") -> dict | None:
    """Equal-weighted skill across assets, with the short records held out.

    Why not just call `skill_vs` on the pooled observations: that is a ratio of
    *pooled* mean pinball losses, and pinball loss carries the asset's unit. The
    10Y is scored in basis points, where a typical loss is an order of magnitude
    larger than a percent-scale loss on the S&P. Pooling the losses first would
    hand the 10Y most of both the numerator and the denominator, and the number
    would be a 10Y skill score wearing the product's name. So skill is computed
    *within* each asset — where it is unit-free — and only then averaged.

    Equal weighting is what stops the longest record speaking for the product,
    but on its own it creates the opposite failure: an asset five report dates
    old getting the same vote as one with a year. Hence `MIN_POOL_BLOCKS`. The
    qualifying set is fixed once, on the real sample, and the bootstrap then
    re-pools exactly those assets — a resample's own block structure is
    degenerate and must not re-decide who is in the pool.

    Returns None when no asset qualifies. `excluded` maps each held-out asset to
    its block count, so a thin universe reads as thin rather than as absent.
    """
    wanted = set(keys) if keys is not None else {a.key for a in ASSETS}
    qualifying: list[str] = []
    excluded: dict[str, int] = {}

    for a in ASSETS:
        if a.key not in wanted:
            continue
        sub = [o for o in obs if o["asset"] == a.key]
        if not sub:
            continue
        n_blocks = len(_blocks_of_dates(sorted({o["date"] for o in sub})))
        if n_blocks < MIN_POOL_BLOCKS or skill_vs(sub, arm, benchmark) is None:
            excluded[a.key] = n_blocks
            continue
        qualifying.append(a.key)

    if not qualifying:
        return None

    def _stat(x: list[dict], _q: tuple[str, ...] = tuple(qualifying)) -> float | None:
        vals = [v for k in _q
                if (v := skill_vs([o for o in x if o["asset"] == k], arm,
                                  benchmark)) is not None]
        return st.mean(vals) if vals else None

    in_pool = [o for o in obs if o["asset"] in set(qualifying)]
    point = _stat(in_pool)
    return {
        "skill": round(point, 4) if point is not None else None,
        "arm": arm,
        "benchmark": benchmark,
        "weighting": "equal per asset",
        "assets": qualifying,
        "excluded": excluded,
        "min_pool_blocks": MIN_POOL_BLOCKS,
        "ci": block_bootstrap(in_pool, _stat),
    }


def _coverage(obs: list[dict]) -> float | None:
    """P25-P75 containment rate over the observations that made an interval claim."""
    vals = [1.0 if o["inside_iqr"] else 0.0 for o in obs if o.get("claim") == "iqr"]
    return st.mean(vals) if vals else None


def _above_median(obs: list[dict]) -> float | None:
    return st.mean([1.0 if o["above_median"] else 0.0 for o in obs]) if obs else None


def _pit_histogram(obs: list[dict]) -> dict[str, float]:
    sub = [o for o in obs if o.get("claim") == "iqr"]
    if not sub:
        return {}
    counts: dict[int, int] = defaultdict(int)
    for o in sub:
        counts[o["pit_bin"]] += 1
    return {str(b): round(counts[b] / len(sub), 4) for b in range(4)}


def summarize(obs: list[dict], horizon: int | None = None,
              asset: str | None = None) -> dict | None:
    """Calibration + skill for one slice of the record.

    Coverage and PIT are unit-free and pool across assets. Mean pinball loss is
    NOT pooled across assets — percent and basis points do not add — so it is
    reported only when the slice is a single asset. The same rule now governs
    skill: `skill_vs_unconditional` is a ratio of mean pinball losses, so it
    only appears on a single-asset slice. A multi-asset slice carries
    `pooled_skill` instead, which averages the per-asset skills.
    """
    sub = [o for o in obs
           if (horizon is None or o["horizon"] == horizon)
           and (asset is None or o["asset"] == asset)]
    if not sub:
        return None

    dates = sorted({o["date"] for o in sub})
    iqr_sub = [o for o in sub if o.get("claim") == "iqr"]
    cov = _coverage(sub)
    out: dict = {
        "n": len(sub),
        "n_report_dates": len(dates),
        "n_blocks": len(_blocks_of_dates(dates)),
        "first_date": dates[0],
        "last_date": dates[-1],
        # The interval record is younger than the median record: p25/p75 only
        # entered the log on 2026-09-07. Reporting one n for both would read as
        # a 73-day coverage measurement that does not exist.
        "n_interval_claims": len(iqr_sub),
        "interval_record_starts": min((o["date"] for o in iqr_sub), default=None),
        "coverage_iqr": round(cov, 4) if cov is not None else None,
        "coverage_ci": block_bootstrap(iqr_sub, _coverage) if iqr_sub else None,
        "above_median": round(_above_median(sub), 4),
        "above_median_ci": block_bootstrap(sub, _above_median),
        "pit_histogram": _pit_histogram(sub),
    }

    if asset is not None:
        out["unit"] = BY_KEY[asset].unit
        out["mean_pinball"] = {
            arm: round(v, 4) for arm in ARMS
            if (v := _mean_pinball(sub, arm)) is not None
        }
        out["skill_vs_unconditional"] = {}
        for arm in ARMS:
            if arm == "unconditional":
                continue
            sk = skill_vs(sub, arm)
            if sk is None:
                continue
            paired = [o for o in sub
                      if arm in o["arms"] and "unconditional" in o["arms"]]
            out["skill_vs_unconditional"][arm] = {
                "skill": round(sk, 4),
                "n": len(paired),
                "ci": block_bootstrap(paired, lambda x, a=arm: skill_vs(x, a)),
            }
    else:
        # `pooled_skill` is the headline the bar is applied to; the stable
        # universe is the three assets the seal was written over on 2026-09-08,
        # before the 10Y/DXY/Bitcoin rows existed. `pooled_skill_all_assets` is
        # the same statistic over whatever the universe currently is — reported
        # for orientation, judged separately once it has a record of its own.
        out["pooled_skill"] = pooled_skill(sub, "published", keys=ORIGINAL_KEYS)
        out["pooled_skill_all_assets"] = pooled_skill(sub, "published")
        out["pooled_universe"] = sorted(ORIGINAL_KEYS)

    return out


def build_report(obs: list[dict]) -> dict:
    """The full aggregation: per horizon, and per asset within each horizon.

    Two populations are reported side by side and never merged: the **sealed**
    interval record (from SEAL_START, the bar applies) and the **exploratory**
    median-only backfill (seen before the bar was written, so it is reported for
    orientation and cannot pass). `verdict()` is applied to each with the
    appropriate `sealed` flag.
    """
    sealed_obs, explore_obs = split_by_seal(obs)
    report: dict = {
        "generated": date.today().isoformat(),
        "n_observations": len(obs),
        "n_sealed": len(sealed_obs),
        "n_exploratory": len(explore_obs),
        "seal_start": SEAL_START,
        "benchmark": "unconditional",
        "block_days": BLOCK_DAYS,
        "min_blocks": MIN_BLOCKS,
        "min_skill": MIN_SKILL,
        "horizons": {},
        "sealed": {},
        "record_start_by_asset": {},
    }

    for a in ASSETS:
        sub = [o for o in obs if o["asset"] == a.key]
        if sub:
            report["record_start_by_asset"][a.key] = min(o["date"] for o in sub)

    for h in HORIZONS:
        overall = summarize(obs, horizon=h)
        if overall is None:
            continue
        per_asset = {}
        for a in ASSETS:
            s = summarize(obs, horizon=h, asset=a.key)
            if s:
                per_asset[a.key] = s
        overall["per_asset"] = per_asset
        overall["verdict"] = verdict(overall, sealed=False)
        report["horizons"][f"t{h}"] = overall

        sealed_h = summarize(sealed_obs, horizon=h)
        if sealed_h is not None:
            sealed_h["verdict"] = verdict(sealed_h, sealed=True)
            report["sealed"][f"t{h}"] = sealed_h
        else:
            report["sealed"][f"t{h}"] = {
                "n": 0,
                "verdict": {"verdict": "underpowered",
                            "reason": "no resolved observations in the sealed "
                                      f"interval record (starts {SEAL_START})"},
            }

    return report


# ---------------------------------------------------------------------------
# The pre-committed bar
#
# Written 2026-09-08, BEFORE any interval claim had resolved. p25/p75 entered the
# quant log on 2026-09-07, so at the time this was written the interval record
# was empty: n=0. That is what makes it a pre-registration rather than a
# rationalisation, and it is the only window in which it could honestly be
# written. The full statement is Project_Development.md -> Phase 22 -> WP-22.C.
#
# The median-only backfill (2026-05-29 -> 2026-08-28) had ALREADY been computed
# when this was written and is therefore EXPLORATORY, not sealed. It is reported
# under `median_exploratory` and can never produce a `pass` verdict. Mixing a
# seen sample into a sealed read is the failure `split_reports_by_seal` exists to
# prevent in the numeric harness; the same rule applies here.
#
# Structure follows [KB-027] literally. That finding was that the pre-committed
# `verdict()` returned "edge" for an arm its own pre-registration had
# disqualified, because the pass clause was reachable without ever consulting the
# disqualifier. So here every disqualifier is evaluated FIRST, returns its own
# named verdict, and the pass clause is not reachable until all of them have been
# checked. If you edit this function, keep that order.
#
# AMENDMENT, 2026-09-08 (same day, still n_sealed = 0)
# ----------------------------------------------------
# The bar as first written applied to `skill_vs_unconditional["published"]` on
# the multi-asset slice, which is a ratio of mean pinball losses POOLED ACROSS
# ASSETS. That was defensible only while every asset was percent-scale. The
# 2026-09-13 refit adds the 10Y in basis points, whose losses are an order of
# magnitude larger, and the pooled ratio would then have been a 10Y skill score
# reported as the product's. The bar now applies to `pooled_skill`: per-asset
# skill, averaged equally, over the STABLE universe (`assets.ORIGINAL_KEYS`) the
# seal was written over — with `MIN_POOL_BLOCKS` holding out any asset too short
# to have a CI. Thresholds are unchanged; only the statistic they read is.
#
# This is a pre-data amendment, which is the only honest kind: p25/p75 entered
# the quant log 2026-09-07, the first 5d interval window resolves ~2026-09-14,
# and at the time of writing the sealed record holds zero resolved observations.
# After that date this block is frozen. Recorded in Project_Development.md ->
# Phase 22 -> WP-22.C.
# ---------------------------------------------------------------------------

# Minimum independent 21-day blocks before a skill claim is allowed at all.
# Eight blocks is ~168 report dates ~ 8 months of daily notes, which puts the
# earliest possible sealed read around 2027-05. Anything less is underpowered,
# and [KB-023] is the standing reminder that a wide interval means "cannot see",
# not "nothing there".
MIN_BLOCKS = 8

# Nominal coverage of the published P25-P75 interval.
NOMINAL_COVERAGE = 0.50

# The skill margin over the unconditional benchmark. NOT zero, deliberately:
# [KB-027] found the previous bar handing out "edge" for a BSS of +0.003 on
# heavily overlapping calls, and recorded that a floor of literally zero is not
# a skill threshold. This is the same decision as the open EDGE_MIN_BSS one, and
# it is settled HERE, in writing, before the data exists rather than after.
MIN_SKILL = 0.02


def _skill_for_verdict(summary: dict) -> tuple[float | None, dict | None]:
    """The skill estimate the bar is applied to, and its CI.

    A multi-asset summary carries `pooled_skill` — per-asset skills averaged
    equally, which is the only form that survives a universe holding both
    percent and basis-point assets. A single-asset summary carries the direct
    ratio. Preferring the pooled field means the bar can never be applied to a
    unit-mixed number, whatever the universe grows to.
    """
    pooled = summary.get("pooled_skill")
    if pooled and pooled.get("skill") is not None:
        return pooled["skill"], pooled.get("ci")
    direct = (summary.get("skill_vs_unconditional") or {}).get("published") or {}
    return direct.get("skill"), direct.get("ci")


def verdict(summary: dict, sealed: bool = True) -> dict:
    """Apply the pre-committed bar to one horizon's summary.

    Returns {"verdict": str, "reason": str, ...}. Verdicts:

      ``exploratory``    the slice is not sealed (the median-only backfill was
                         seen before the bar was written) - reported, never passed
      ``underpowered``   fewer than MIN_BLOCKS independent blocks
      ``miscalibrated``  the coverage CI excludes nominal - a miscalibrated
                         interval is not an edge whatever its pinball loss says
      ``inverted``       the conditional layer is reliably WORSE than not
                         conditioning at all - a distinct negative finding
      ``no_edge``        cleared every disqualifier, did not clear the bar
      ``edge``           cleared every disqualifier AND the bar

    The disqualifiers are evaluated in that order and each returns immediately.
    The skill it reads is `_skill_for_verdict` — the equal-weighted pooled
    number on a multi-asset slice, never the unit-mixed pooled ratio.
    """
    if not sealed:
        return {"verdict": "exploratory",
                "reason": "sample was observed before the bar was written; "
                          "reported for orientation, cannot pass"}

    # --- Disqualifier 1: power -------------------------------------------
    n_blocks = summary.get("n_blocks", 0)
    if n_blocks < MIN_BLOCKS:
        return {"verdict": "underpowered",
                "reason": f"{n_blocks} independent blocks < {MIN_BLOCKS} required",
                "n_blocks": n_blocks}

    # --- Disqualifier 2: calibration -------------------------------------
    if not summary.get("n_interval_claims"):
        return {"verdict": "underpowered",
                "reason": "no resolved interval claims — coverage is undefined"}
    cov_ci = summary.get("coverage_ci")
    cov = summary.get("coverage_iqr")
    if cov_ci and not (cov_ci["lo"] <= NOMINAL_COVERAGE <= cov_ci["hi"]):
        return {"verdict": "miscalibrated",
                "reason": f"coverage {cov} CI [{cov_ci['lo']}, {cov_ci['hi']}] "
                          f"excludes nominal {NOMINAL_COVERAGE}",
                "coverage": cov}

    # --- Disqualifier 3: inversion ---------------------------------------
    skill, skill_ci = _skill_for_verdict(summary)
    if skill is None:
        return {"verdict": "underpowered",
                "reason": "no skill estimate against the unconditional benchmark"}
    if skill_ci and skill_ci["hi"] < 0:
        return {"verdict": "inverted",
                "reason": f"skill {skill} CI [{skill_ci['lo']}, {skill_ci['hi']}] "
                          f"lies entirely below zero — conditioning is worse "
                          f"than not conditioning",
                "skill": skill}

    # --- Only now, the pass clause ---------------------------------------
    if skill > MIN_SKILL and skill_ci and skill_ci["lo"] > 0:
        return {"verdict": "edge",
                "reason": f"skill {skill} > {MIN_SKILL} and CI "
                          f"[{skill_ci['lo']}, {skill_ci['hi']}] excludes zero",
                "skill": skill, "coverage": cov}

    return {"verdict": "no_edge",
            "reason": f"skill {skill} did not clear {MIN_SKILL} with a "
                      f"zero-excluding CI",
            "skill": skill, "coverage": cov}


# The date p25/p75 entered the quant log. Observations on or after this made a
# full interval claim and belong to the sealed forward record; everything before
# it is the median-only backfill, which was seen.
SEAL_START = "2026-09-07"


def _is_sealed(o: dict) -> bool:
    return o.get("claim") == "iqr" and o["date"] >= SEAL_START


def split_by_seal(obs: list[dict]) -> tuple[list[dict], list[dict]]:
    """(sealed, exploratory) — the interval record vs the seen median backfill."""
    sealed = [o for o in obs if _is_sealed(o)]
    explore = [o for o in obs if not _is_sealed(o)]
    return sealed, explore


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def write_observations(obs: list[dict], out_dir: Path | None = None) -> int:
    """Persist observations grouped by report date, one JSON per date."""
    out_dir = out_dir or DIST_SCORES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    by_date: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        by_date[o["date"]].append(o)

    for d, items in by_date.items():
        payload = {
            "report_date": d,
            "scored_at": date.today().isoformat(),
            "observations": sorted(items, key=lambda o: (o["asset"], o["horizon"])),
        }
        (out_dir / f"{d}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    return len(by_date)


def already_scored(out_dir: Path | None = None) -> set[str]:
    out_dir = out_dir or DIST_SCORES_DIR
    if not out_dir.exists():
        return set()
    return {p.stem for p in out_dir.glob("*.json")}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true",
                        help="rescore every report date, ignoring existing files")
    args = parser.parse_args()

    records = load_quant_log()
    if not records:
        _log("ABORT", f"no quant-context records under {QUANT_LOG_DIR}")
        return
    _log("LOG", f"{len(records)} daily records, {records[0]['date']} → {records[-1]['date']}")

    if not args.rebuild:
        done = already_scored()
        pending = [r for r in records if r["date"] not in done]
        _log("LOG", f"{len(done)} dates already scored, {len(pending)} to consider")
        records = pending if pending else records

    prices = fetch_history()
    if not prices:
        _log("ABORT", "no price history — cannot score")
        return

    obs = build_observations(records, prices)
    if not obs:
        _log("DONE", "no windows have resolved since the last run")
        return

    n_dates = write_observations(obs)
    _log("SCORED", f"{len(obs)} observations across {n_dates} report dates "
                   f"→ {DIST_SCORES_DIR}")

    all_obs = load_all_observations()
    report = build_report(all_obs)
    (RESULTS_DIR / "dist_scores_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    _log("SUMMARY", f"{report['n_observations']} observations → dist_scores_summary.json")

    for h in HORIZONS:
        s = report["horizons"].get(f"t{h}")
        if not s:
            continue
        _log(f"T+{h}",
             f"n={s['n']} ({s['n_blocks']} blocks, {s['n_report_dates']} dates) · "
             f"median record {s['first_date']} → {s['last_date']}")
        _log(f"T+{h}",
             f"  above-median {s['above_median']:.3f} (nominal 0.500) "
             f"{_fmt_ci(s.get('above_median_ci'))}")
        for label, key in (("stable", "pooled_skill"),
                           ("all", "pooled_skill_all_assets")):
            ps = s.get(key)
            if not ps or ps.get("skill") is None:
                _log(f"T+{h}", f"  skill vs unconditional ({label}): no asset "
                               f"has {MIN_POOL_BLOCKS}+ blocks yet")
                continue
            held = (f" · held out {sorted(ps['excluded'])}"
                    if ps.get("excluded") else "")
            _log(f"T+{h}",
                 f"  skill vs unconditional ({label}, equal-weight over "
                 f"{len(ps['assets'])}) {ps['skill']:+.4f} "
                 f"{_fmt_ci(ps.get('ci'))}{held}")
        if s["n_interval_claims"]:
            _log(f"T+{h}",
                 f"  IQR coverage {s['coverage_iqr']:.3f} (nominal 0.500) "
                 f"{_fmt_ci(s.get('coverage_ci'))} on {s['n_interval_claims']} "
                 f"interval claims from {s['interval_record_starts']}")
        else:
            _log(f"T+{h}",
                 "  IQR coverage: no resolved interval claims yet — p25/p75 "
                 "entered the log 2026-09-07, so the first 5d window resolves "
                 "~2026-09-14 and the first 20d ~2026-10-05")


def _fmt_ci(ci: dict | None) -> str:
    if not ci:
        return "[CI needs >=2 blocks]"
    return f"[{ci['lo']:+.3f}, {ci['hi']:+.3f}]"


def load_all_observations(out_dir: Path | None = None) -> list[dict]:
    """Read back every persisted observation, for aggregation."""
    out_dir = out_dir or DIST_SCORES_DIR
    obs: list[dict] = []
    if not out_dir.exists():
        return obs
    for path in sorted(out_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            _log("WARN", f"{path.name} is not valid JSON — skipped")
            continue
        obs.extend(payload.get("observations", []))
    return obs


if __name__ == "__main__":
    main()
