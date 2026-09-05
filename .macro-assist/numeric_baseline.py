"""
numeric_baseline.py — WP-21.A: is 5/10/20-day direction learnable at all?

Phase 21 exists because three independent metrics say the directional product
does not work ([KB-007] decisive accuracy ~36% and BSS < 0; [KB-022] an
*inverted* bias/return separation), and the one result that looked like a repair
turned out to be confounded with the market period [KB-023]. Every one of those
readings is about the LLM. None of them tests the rival hypothesis:

    that 5/10/20-day direction on liquid macro assets is close to unlearnable
    from this payload by *any* model, and the LLM is being blamed for the
    difficulty of the task.

This module is that test. It fits two deliberately small, regularised models —
an L2 logistic ("ridge") and a shallow gradient-boosted tree — walk-forward on
the numeric inputs the pipeline already collects, and scores them on **exactly
the metrics the LLM is judged on**: `score_predictions.score_call` hit-rate,
`summarize_accuracy` Brier/BSS/ECE, and the `bias_separation` bucket ordering.
The comparators are the ones already in `backtest.py` (`strategy_neutral`,
`strategy_random_walk`) plus always-Bullish, which is the drift benchmark
[KB-022] was written to defeat.

The decision value is symmetric, which is the point:

  * If ridge/GBM cannot beat neutral over a decade, the directional product is
    dead for every model class — WP-21.C and any future network die with it,
    and the report's headline moves to the fragility track [KB-017/021].
  * If they can, the result is simultaneously the upper bound on achievable
    skill, the base-rate feed for WP-21.C, and the benchmark the LLM arm has
    never had.

Why not a bigger model
----------------------
Recorded in `Project_Development.md` (Phase 21) and not re-litigated here: full-
panel coverage is bounded by the youngest inputs, giving ~150 *non-overlapping*
20-day windows across ~3 independent factors [KB-009]. [KB-002] and [KB-016]
both already found this data supports fewer, discrete weights rather than more
learned ones. Hence: two models, both regularised, both small.

Point-in-time discipline (read this before adding a feature)
------------------------------------------------------------
`point_in_time.historical_snapshot()` exists to serve ALFRED *vintages*, but it
costs one HTTP call per series per date — ~40k calls for a decade of daily
walk-forward, which is why `strategy_existing_pipeline` was never run. This
module takes the other route to the same guarantee:

  **Only inputs that are never revised are eligible.** Market prices (yfinance)
  and FRED's market-observed daily series (constant-maturity yields, BAA10Y,
  breakevens, VIX) are printed once and never restated, so today's vintage *is*
  the historical vintage and no ALFRED call is needed. Every eligible series is
  additionally shifted forward by `PUBLICATION_LAG_BDAYS` so a value is only
  ever used the business day after it was published.

  Revised or lagged-release macro (CPI, payrolls, M2, WALCL, NFCI, claims) is
  **excluded by construction** — `FRED_INPUTS` is the whole list, and anything
  added to it must satisfy the no-revision rule. Adding a revised series would
  silently reintroduce look-ahead and make a positive result unbelievable.

The second leak this guards is the label: training on a row whose forward window
has not closed by the prediction date would leak the future directly. See
`walk_forward` — it embargoes exactly `horizon` trading days plus one.

The exogenous branch (added 2026-09-04)
---------------------------------------
Phase 19's exogenous engine was deactivated because its go/no-go gate was an A/B
against the market-only LLM arm, and v1.6 cut that arm's calls [KB-024] — the
comparator froze and the gate became unreadable. This is the way back: the
branch's *anchor data* is re-pointed at the WP-21.A benchmark, so the
expectations thesis is scored on the same sample, by the same readers, against
the same pre-committed `verdict()` bar as everything else.

What crosses over is the deterministic, non-market half of the branch — the
Philadelphia Fed **SPF** economist consensus (`exogenous/spf.py`), which is
point-in-time by construction: every survey is stamped by the quarter it was
conducted and is never restated, so it satisfies the no-revision rule above with
no ALFRED call.

What deliberately does NOT cross over:

  * **The SEP dot plot.** `fred.get_series("FEDTARMD")` returns the *current*
    vintage of a projection path that each SEP release rewrites, so a
    walk-forward reading it would see the Fed's later revisions — the exact leak
    `FRED_INPUTS` excludes CPI and payrolls for. `exogenous/sep.py` says so in
    its own POINT-IN-TIME note. The SPF-vs-SEP gap therefore stays a *live-only*
    signal; here the anchor is SPF alone. `EXCLUDED_EXOGENOUS_SERIES` holds the
    exclusion as a checked fact rather than a comment.
  * **The LLM layers** (L1 extract / L2 analyst). DESIGN §6.2: those models were
    trained on the dated FOMC text they would be reading, so a historical
    backtest of them is leakage-prone by construction. Nothing here reads a
    document.

Two arms come out of it, asking two different questions:

  * `exogenous_spf` — ridge on the SPF features *alone*, no price or market
    input. Does the non-market consensus anchor carry direction on its own?
  * `market_plus_exo` — the same ridge on the market panel *plus* those columns.
    Does the anchor add anything on top of the market panel? Read against
    `ridge`: same model, same sample, same rows, minus these columns.

Where the output goes
---------------------
`results/numeric_baseline/` — the markdown report, a JSON of every metric and
diagnostic, and (with `--emit-scores`) the raw simulated calls as
`scores.json.gz`. **Never** `results/scores/`, which is the production accuracy
corpus. Keeping them apart is deliberate: these are simulated arms, and dropping
them where `summarize_accuracy.py` looks would contaminate the live A/B the
moment someone ran the weekly job.

Usage:
    # full run (needs FRED_API_KEY + network)
    python .macro-assist/numeric_baseline.py --start 2005-01-01 --save-panel panel.csv

    # re-run the analysis offline from a cached panel
    python .macro-assist/numeric_baseline.py --panel panel.csv

    # market arms only (skip the Phase-19 anchor)
    python .macro-assist/numeric_baseline.py --panel panel.csv --no-exogenous
"""
from __future__ import annotations

import gzip
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from score_predictions import (
    ASSET_TICKERS,
    SCORING_WINDOWS,
    score_call,
)

BASE_DIR    = _HERE.parent
RESULTS_DIR = BASE_DIR / "results" / "numeric_baseline"

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

# FRED series eligible under the no-revision rule above. Every one is a market
# observation published once and never restated:
#   DGS10/DGS2  constant-maturity Treasury yields (H.15)
#   BAA10Y      Moody's Baa minus 10Y — the long-history credit-stress series
#               refit_models.py already uses in place of the license-truncated
#               ICE HY OAS (see its _FRED_SERIES note)
#   T10YIE      10y breakeven inflation
#   DFII10      10y TIPS (real) yield
#   VIXCLS      CBOE VIX close
# Do NOT add CPI, payrolls, M2, WALCL, NFCI or claims here — all are revised
# and/or released with a lag, and the panel carries no vintage information.
FRED_INPUTS: dict[str, str] = {
    "treasury_10y":   "DGS10",
    "treasury_2y":    "DGS2",
    "baa_spread":     "BAA10Y",
    "breakeven_10y":  "T10YIE",
    "real_yield_10y": "DFII10",
    "vix":            "VIXCLS",
}

# A FRED daily print for day d lands after that day's close, so it is only
# usable on d+1. One business day of shift; cheap, and it removes the whole
# class of "the model saw the close it was predicting" objections.
PUBLICATION_LAG_BDAYS: int = 1

# --- The Phase-19 exogenous anchor (see the module docstring) ---------------

# Panel key -> (SPF variable code, horizon name). `current_q` is the survey's
# nowcast for its own quarter; `q4_ahead` is the same forecasters' level four
# quarters out, so the pair carries the consensus *path* — the quantity DESIGN
# §6.1 wanted and had to reach without touching futures.
SPF_INPUTS: dict[str, tuple[str, str]] = {
    "spf_10y":    ("TBOND", "current_q"),
    "spf_10y_q4": ("TBOND", "q4_ahead"),
    "spf_3m":     ("TBILL", "current_q"),
    "spf_3m_q4":  ("TBILL", "q4_ahead"),
    "spf_unemp":  ("UNEMP", "current_q"),
}

# The published median-level workbooks, committed under `exogenous/example/` as
# the `test_spf.py` real-file fixtures — so this run is offline like the rest.
SPF_WORKBOOK    = "Median_{code}_Level.xlsx"
DEFAULT_SPF_DIR = _HERE / "exogenous" / "example"

# Series the live exogenous branch uses that are NOT eligible here, with the
# reason. Asserted by the test suite so the exclusion cannot rot into a comment.
EXCLUDED_EXOGENOUS_SERIES: dict[str, str] = {
    "FEDTARMD":   "SEP dot plot — FRED serves the current vintage and every SEP "
                  "release rewrites earlier target years (see exogenous/sep.py)",
    "FEDTARMDLR": "SEP longer-run dot — same revision problem",
}

# The derived survey clock: a panel column carrying *when the current anchor
# landed*, as a date ordinal. It is not an SPF variable and never becomes a model
# feature (a raw date is the purest date proxy there is) — it exists so the
# revision and staleness features can tell a NEW survey from an unchanged number.
# Value-change detection cannot: the 3M consensus sat pinned at 0.1 through years
# of ZIRP without a single survey being missed, and reading that as a stale anchor
# would have been wrong every day of it.
SPF_ASOF_KEY: str = "spf_asof"

# Business days in a survey cycle; the scale the staleness clock is expressed in.
SPF_QUARTER_BDAYS: int = 63

# Trailing windows used by the feature builder. All strictly backward-looking.
MOMENTUM_WINDOWS: tuple[int, ...] = (5, 20, 60)
MA_WINDOWS:       tuple[int, ...] = (50, 200)
VOL_SHORT:  int = 20
VOL_LONG:   int = 60
DRAWDOWN_WINDOW: int = 252
VIX_PCTILE_WINDOW: int = 252
# BAA z-score reference window. 1260 bdays ≈ 5y, matching refit_models._HY_MEAN_WINDOW.
BAA_Z_WINDOW: int = 1260

# Walk-forward controls.
#   MIN_TRAIN_DAYS  ~3y of business days before the first prediction — below this
#                   a 20-feature fit is memorising, not learning.
#   REFIT_EVERY     refit cadence in prediction steps. Daily refits cost ~21x more
#                   for a model whose coefficients move on a monthly timescale.
MIN_TRAIN_DAYS: int = 756
REFIT_EVERY:    int = 21

# P(up) within this band of 0.5 is reported as Neutral. The pipeline's Neutral is
# an honest abstention, so the numeric arms get one too — otherwise they would be
# forced into a decisive call on every single day and the comparison to a model
# that may abstain would be unfair in the wrong direction.
NEUTRAL_DEADBAND: float = 0.05

# Fixed seed so a given panel always produces the same report.
SEED: int = 7

# Permutation / bootstrap draws for the separation section. `bias_separation`
# defaults to 2000, sized for the ~2k calls the daily accuracy report carries; a
# decade of daily simulated calls across six assets and three horizons is an
# order of magnitude larger, and the test's cost is draws x observations. 500
# draws put the p-value resolution floor at ~1/501 — far below any threshold
# worth acting on — for a quarter of the runtime.
SEPARATION_DRAWS: int = 500

# Arm labels for the emitted score files. These are the keys `calibration_by_arm`
# will show side by side.
ARM_RIDGE        = "ridge"
ARM_GBM          = "gbm"
ARM_NEUTRAL      = "neutral"
ARM_RANDOM_WALK  = "random_walk"
ARM_ALWAYS_BULL  = "always_bullish"
# Named `exogenous_spf`, not `exogenous`: the live Phase-19 notes are tagged
# `arm: exogenous` and `calibration_by_arm` keys off exactly that string. A
# simulated arm sharing the name is the [KB-023] pooling defect waiting to
# happen, and the suffix is also honest — this is the branch's SPF anchor, not
# its FOMC-text layers.
ARM_EXO          = "exogenous_spf"
ARM_MARKET_EXO   = "market_plus_exo"

# The profile tag on emitted files. Never "baseline"/"loosened" — those name the
# live LLM A/B and must not gain simulated members.
NUMERIC_PROFILE = "numeric_baseline"


# ---------------------------------------------------------------------------
# Panel construction (network — lazy imports, integration-tested only)
# ---------------------------------------------------------------------------

def fetch_price_history(start: date, end: date | None = None) -> dict[str, pd.Series]:
    """Daily close series for every scored asset, keyed by the scoring name.

    Uses the same tickers `score_predictions` scores against, so a feature and
    the label it predicts are computed from one price series.
    """
    import yfinance as yf

    end = end or date.today()
    out: dict[str, pd.Series] = {}
    for asset, ticker in ASSET_TICKERS.items():
        try:
            hist = yf.download(
                ticker,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=True,
            )
            if hist is None or hist.empty:
                continue
            close = hist["Close"].squeeze().dropna()
            close.index = pd.to_datetime(close.index).tz_localize(None)
            out[asset] = close
        except Exception as exc:  # pragma: no cover - network path
            print(f"  WARN: {asset} ({ticker}) price fetch failed: {exc}")
    return out


def fetch_fred_inputs(start: date) -> dict[str, pd.Series]:
    """The unrevised FRED daily series, via `input_testing.fetch_fred_series`.

    That helper is cache-first (CSV on disk), so a second run — and every test
    run on a machine that has already acquired the series — is fully offline.
    """
    from input_testing import fetch_fred_series

    out: dict[str, pd.Series] = {}
    for key, sid in FRED_INPUTS.items():
        try:
            s = fetch_fred_series(sid)
            out[key] = s[s.index >= pd.Timestamp(start)].dropna()
        except Exception as exc:  # pragma: no cover - network path
            print(f"  WARN: FRED {key} ({sid}) failed: {exc}")
    return out


def load_spf_inputs(spf_dir: Path | str = DEFAULT_SPF_DIR) -> dict[str, pd.Series]:
    """Point-in-time SPF consensus series, keyed by panel name.

    Reads the committed median-level workbooks through `exogenous.spf`, so the
    parse — and its workaround for the Philly Fed's malformed core.xml — has
    exactly one implementation. Each series is indexed by
    `spf.survey_release_date`: the date the survey became *available*, not the
    quarter it describes. No network; the workbooks are in the repo.

    A missing or unreadable workbook is a warning, not an error: the exogenous
    arms then drop out of the run and the market arms still reproduce [KB-024].
    """
    from exogenous.spf import load_spf_file

    spf_dir = Path(spf_dir)
    out: dict[str, pd.Series] = {}
    for key, (code, horizon) in SPF_INPUTS.items():
        path = spf_dir / SPF_WORKBOOK.format(code=code)
        if not path.exists():
            print(f"  WARN: SPF workbook for {key} not found at {path}")
            continue
        try:
            out[key] = load_spf_file(path, code, horizon).dropna()
        except Exception as exc:  # pragma: no cover - malformed workbook
            print(f"  WARN: SPF {key} ({code}/{horizon}) failed: {exc}")

    if out:
        # Two variables can miss different quarters, so the union of their survey
        # dates is the honest answer to "when did an anchor last land".
        stamps = pd.DatetimeIndex(sorted(set().union(*(set(s.index) for s in out.values()))))
        out[SPF_ASOF_KEY] = pd.Series(
            [float(ts.toordinal()) for ts in stamps], index=stamps
        )
    return out


def build_panel(
    prices: dict[str, pd.Series],
    fred: dict[str, pd.Series],
    exogenous: dict[str, pd.Series] | None = None,
    lag_bdays: int = PUBLICATION_LAG_BDAYS,
) -> pd.DataFrame:
    """Align prices, FRED inputs and the exogenous anchor onto one business-day index.

    Columns are namespaced `px:<asset>`, `macro:<key>` and `exo:<key>`. Prices are
    forward filled (a closed market carries yesterday's mark); FRED and exogenous
    series are shifted `lag_bdays` business days *before* forward filling, so a
    value published on day d cannot appear on a row dated d.

    The exogenous series arrive already stamped with their release date (SPF's
    conservative mid-quarter anchor), and the same one-day shift is applied on top
    so "published on d, readable on d+1" is uniform across every input in the
    panel rather than a per-source argument.

    Pure — no network. `fetch_price_history` / `fetch_fred_inputs` /
    `load_spf_inputs` do the I/O.
    """
    if not prices:
        return pd.DataFrame()

    first = min(s.index.min() for s in prices.values())
    last  = max(s.index.max() for s in prices.values())
    index = pd.bdate_range(start=first, end=last)

    cols: dict[str, pd.Series] = {}
    for asset, s in prices.items():
        cols[f"px:{asset}"] = s.reindex(index.union(s.index)).ffill().reindex(index)
    for prefix, source in (("macro", fred), ("exo", exogenous or {})):
        for key, s in source.items():
            shifted = s.copy()
            # Shift the *stamp*, not the values: each observation moves forward to
            # the first business day on which it was readable.
            shifted.index = pd.DatetimeIndex(shifted.index) + pd.offsets.BDay(lag_bdays)
            cols[f"{prefix}:{key}"] = (
                shifted.reindex(index.union(shifted.index)).ffill().reindex(index)
            )

    panel = pd.DataFrame(cols, index=index)
    panel.index.name = "date"
    return panel


def save_panel(panel: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(path)


def load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path, index_col=0, parse_dates=True)
    panel.index.name = "date"
    return panel


# ---------------------------------------------------------------------------
# Features — every column is a function of data at or before its own row
# ---------------------------------------------------------------------------

def _pct_change(series: pd.Series, n: int) -> pd.Series:
    return series / series.shift(n) - 1.0


def _realized_vol(series: pd.Series, window: int) -> pd.Series:
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


def macro_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-asset state shared by every asset's model.

    Each column is either a level that is already stationary enough to regress on
    (curve, VIX percentile, credit z-score) or a 20-day change. Raw levels of
    trending series (10Y, breakeven) are deliberately not included: over a decade
    they act as a date proxy and let a model 'learn' the sample's regime order.
    """
    out = pd.DataFrame(index=panel.index)

    t10 = panel.get("macro:treasury_10y")
    t2  = panel.get("macro:treasury_2y")
    if t10 is not None and t2 is not None:
        out["curve"]          = t10 - t2
        out["curve_chg_20"]   = (t10 - t2) - (t10 - t2).shift(20)
    if t10 is not None:
        out["y10_chg_20"]     = t10 - t10.shift(20)

    baa = panel.get("macro:baa_spread")
    if baa is not None:
        mean = baa.rolling(BAA_Z_WINDOW, min_periods=MIN_TRAIN_DAYS // 3).mean()
        std  = baa.rolling(BAA_Z_WINDOW, min_periods=MIN_TRAIN_DAYS // 3).std()
        out["baa_z"]          = (baa - mean) / std
        out["baa_chg_20"]     = baa - baa.shift(20)

    be = panel.get("macro:breakeven_10y")
    if be is not None:
        out["breakeven_chg_20"] = be - be.shift(20)

    ry = panel.get("macro:real_yield_10y")
    if ry is not None:
        out["real_yield_chg_20"] = ry - ry.shift(20)

    vix = panel.get("macro:vix")
    if vix is not None:
        out["vix_level"] = vix
        out["vix_chg_20"] = vix - vix.shift(20)
        out["vix_pct_252"] = vix.rolling(VIX_PCTILE_WINDOW).rank(pct=True)

    sp = panel.get("px:S&P 500")
    if sp is not None:
        out["sp_ret_20"] = _pct_change(sp, 20)
    dxy = panel.get("px:DXY")
    if dxy is not None:
        out["dxy_ret_20"] = _pct_change(dxy, 20)

    return out


def asset_features(close: pd.Series) -> pd.DataFrame:
    """Own-price state for one asset.

    `ret_20` is the 20-day reversion candidate Phase 21 asked to fold in here
    rather than chase as a standalone errand: if the effect is real, its fitted
    coefficient is negative and it survives permutation importance; if it is not,
    that is measured in the same pass as everything else instead of separately.
    """
    out = pd.DataFrame(index=close.index)
    for n in MOMENTUM_WINDOWS:
        out[f"ret_{n}"] = _pct_change(close, n)
    for n in MA_WINDOWS:
        out[f"ma_gap_{n}"] = close / close.rolling(n).mean() - 1.0
    rv_short = _realized_vol(close, VOL_SHORT)
    rv_long  = _realized_vol(close, VOL_LONG)
    out["rv_20"]     = rv_short
    out["vol_ratio"] = rv_short / rv_long
    out["drawdown"]  = close / close.rolling(DRAWDOWN_WINDOW).max() - 1.0
    return out


def _new_survey(asof: pd.Series) -> pd.Series:
    """True on the first row carrying each new survey stamp."""
    return asof.ne(asof.shift(1)) & asof.notna()


def _survey_revision(daily: pd.Series, asof: pd.Series) -> pd.Series:
    """Change from one survey to the next, held until the survey after that.

    The panel column is a quarterly survey forward-filled onto business days, so a
    plain `diff()` is zero on every day but one. This is the *revision* — the new
    survey minus the one it replaced — carried across the quarter it applies to,
    which is the form a daily model can use.

    Keyed on `asof`, not on the value: a survey that repeats the previous number
    is a real update whose revision is **0.0**, and reading it as "no update"
    would leave a months-old revision standing as if it were current. NaN until a
    second survey exists; there is no revision to report before then.
    """
    updates = daily[_new_survey(asof)].dropna()
    if updates.empty:
        return pd.Series(np.nan, index=daily.index, dtype=float)
    return updates.diff().reindex(daily.index).ffill().where(daily.notna())


def _survey_staleness(asof: pd.Series, scale: int = SPF_QUARTER_BDAYS) -> pd.Series:
    """Business days since the current survey landed, in survey cycles.

    DESIGN §6.5 calls the quarterly cadence a feature: between surveys the anchor
    is fixed and the branch is tracking drift away from it. This is that clock —
    0.0 on the day a survey lands, ~1.0 by the time the next one is due. Without
    it the arm cannot tell a fresh consensus from a stale one, which is precisely
    the distinction the branch's thesis rests on.
    """
    counter = asof.groupby(_new_survey(asof).cumsum()).cumcount()
    return (counter.astype(float) / float(scale)).where(asof.notna())


def exogenous_features(panel: pd.DataFrame) -> pd.DataFrame:
    """The Phase-19 anchor as numeric columns — non-market by construction.

    Levels are deliberately absent, for the same reason `macro_features` omits the
    10Y level: over two decades a trending level is a date proxy. What is here is
    the *shape* of the consensus (curve, expected path), how it just moved
    (revisions), and how stale it is. Every column is a function of surveys
    already released on its own row.

    An empty frame is returned for a panel with no `exo:` columns — that is the
    signal `build_features` turns into "skip this arm".
    """
    out = pd.DataFrame(index=panel.index)
    ten      = panel.get("exo:spf_10y")
    ten_q4   = panel.get("exo:spf_10y_q4")
    three    = panel.get("exo:spf_3m")
    three_q4 = panel.get("exo:spf_3m_q4")
    unemp    = panel.get("exo:spf_unemp")
    # The survey clock. A panel built without it (an older cached CSV) simply
    # gets the level-shape columns — better than a revision column that silently
    # means something different from the one the report describes.
    asof     = panel.get(f"exo:{SPF_ASOF_KEY}")

    if ten is not None and three is not None:
        # Consensus curve: economists' 10Y minus their own 3M — the non-market
        # analogue of the term structure, with no price in it.
        out["spf_curve"] = ten - three
    if ten is not None and ten_q4 is not None:
        out["spf_10y_path"] = ten_q4 - ten
    if three is not None and three_q4 is not None:
        # The consensus policy path — what §6.1 barred fed-funds futures from
        # supplying, sourced from economists instead.
        out["spf_policy_path"] = three_q4 - three
    if asof is not None:
        if ten is not None:
            out["spf_10y_revision"] = _survey_revision(ten, asof)
        if three is not None:
            out["spf_3m_revision"] = _survey_revision(three, asof)
        if unemp is not None:
            out["spf_unemp_revision"] = _survey_revision(unemp, asof)
        out["spf_staleness"] = _survey_staleness(asof)
    return out


# Feature sets. A set is a *hypothesis*, not a size knob: `exogenous` asks whether
# the non-market anchor carries direction at all, `market+exogenous` asks whether
# it adds anything to the panel that already lost to `always_bullish`.
FEATURES_MARKET   = "market"
FEATURES_EXO      = "exogenous"
FEATURES_COMBINED = "market+exogenous"

FEATURE_SETS: tuple[str, ...] = (FEATURES_MARKET, FEATURES_EXO, FEATURES_COMBINED)


def build_features(panel: pd.DataFrame, asset: str,
                   feature_set: str = FEATURES_MARKET) -> pd.DataFrame:
    """Feature frame for one asset under one feature set.

    `market` is the WP-21.A panel: own-price columns joined to the shared macro
    state. `exogenous` is the Phase-19 anchor alone — no price, no market input,
    which is what makes it a different hypothesis rather than a bigger model.
    `market+exogenous` is the union, and it exists to be read against `market`.

    An empty frame means "this arm cannot run on this panel". A panel built
    without SPF inputs returns one for both exogenous sets, and `run_models`
    skips those arms — rather than silently re-running the market arm under a
    second name, which would turn the increment read into a comparison of an arm
    with itself.
    """
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unknown feature set: {feature_set!r}")
    col = f"px:{asset}"
    if col not in panel.columns:
        return pd.DataFrame()

    market = (asset_features(panel[col]).join(macro_features(panel))
              if feature_set in (FEATURES_MARKET, FEATURES_COMBINED)
              else pd.DataFrame())
    if feature_set == FEATURES_MARKET:
        return market

    exo = exogenous_features(panel).dropna(axis=1, how="all")
    if exo.empty:
        return pd.DataFrame()
    return exo if feature_set == FEATURES_EXO else market.join(exo)


def forward_label(close: pd.Series, horizon: int) -> pd.Series:
    """1.0 if the close `horizon` business days ahead is higher, else 0.0.

    The sign convention matches `score_call` for every asset: for the yield
    series the level rises exactly when the Yahoo ^TNX 'price' rises, so 'up' is
    what a Bullish call claims in both cases.
    """
    fwd = close.shift(-horizon)
    return (fwd > close).astype(float).where(fwd.notna())


# ---------------------------------------------------------------------------
# Models — small, regularised, and lazily imported
# ---------------------------------------------------------------------------

# How to read a model's per-input weights. A linear coefficient is signed and its
# sign is a claim about direction; a tree ensemble's `feature_importances_` counts
# splits and is non-negative, so a "sign stability" column over it would report a
# constant 1.000 and mean nothing. The report renders the two differently.
WEIGHT_SIGNED   = "coefficient"
WEIGHT_UNSIGNED = "split_importance"


@dataclass
class FittedModel:
    """One fit: a probability function plus whatever it can say about inputs."""
    predict_proba: Callable[[np.ndarray], np.ndarray]
    coefficients: dict[str, float] = field(default_factory=dict)
    weight_kind: str = WEIGHT_SIGNED
    estimator: object | None = None


def fit_ridge(X: np.ndarray, y: np.ndarray, columns: Sequence[str]) -> FittedModel:
    """Standardised L2 logistic regression — the 'ridge' arm.

    Standardisation is inside the pipeline so it is fitted on the training fold
    only; scaling on the full sample would leak the future's variance into the
    past.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    # `penalty` is left at its default: scikit-learn has always defaulted to L2
    # here, and naming it explicitly is deprecated from 1.8 onward.
    pipe = Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(C=0.1, max_iter=2000,
                                   solver="lbfgs", random_state=SEED)),
    ])
    pipe.fit(X, y)
    coefs = dict(zip(columns, pipe.named_steps["clf"].coef_[0].tolist()))
    return FittedModel(
        predict_proba=lambda Z: pipe.predict_proba(Z)[:, 1],
        coefficients=coefs,
        estimator=pipe,
    )


def fit_gbm(X: np.ndarray, y: np.ndarray, columns: Sequence[str]) -> FittedModel:
    """A deliberately small gradient-boosted tree — depth 2, slow learning rate.

    Depth 2 allows pairwise interactions and nothing deeper; on ~150 independent
    windows [KB-009] anything richer fits the sample.
    """
    from sklearn.ensemble import GradientBoostingClassifier

    clf = GradientBoostingClassifier(
        n_estimators=150,
        max_depth=2,
        learning_rate=0.03,
        subsample=0.8,
        random_state=SEED,
    )
    clf.fit(X, y)
    return FittedModel(
        predict_proba=lambda Z: clf.predict_proba(Z)[:, 1],
        coefficients=dict(zip(columns, clf.feature_importances_.tolist())),
        weight_kind=WEIGHT_UNSIGNED,
        estimator=clf,
    )


@dataclass(frozen=True)
class ArmSpec:
    """One model arm: a fitter, the inputs it may see, and the question it asks.

    Splitting the feature set out of the arm is what lets the same estimator run
    twice on different information without a second copy of the fitting code —
    and it is what makes `market_plus_exo` vs `ridge` a clean read: identical
    model, identical sample, one strictly larger column set.
    """
    fitter: Callable[..., FittedModel]
    feature_set: str
    question: str


ARM_SPECS: dict[str, ArmSpec] = {
    ARM_RIDGE: ArmSpec(
        fit_ridge, FEATURES_MARKET,
        "can a regularised linear model learn direction from the market panel?"),
    ARM_GBM: ArmSpec(
        fit_gbm, FEATURES_MARKET,
        "can a shallow tree ensemble find a non-linearity the ridge misses?"),
    ARM_EXO: ArmSpec(
        fit_ridge, FEATURES_EXO,
        "does the non-market consensus anchor carry direction on its own?"),
    ARM_MARKET_EXO: ArmSpec(
        fit_ridge, FEATURES_COMBINED,
        "does the anchor add anything on top of the market panel? "
        "(read against `ridge`)"),
}

# One model class per new question, deliberately: the GBM's job was to test for a
# non-linearity in the *market* panel and [KB-024] found none, so pairing a
# second estimator with every new feature set would multiply runtime to answer a
# question that has already been asked.
MODEL_FITTERS: dict[str, Callable[..., FittedModel]] = {
    arm: spec.fitter for arm, spec in ARM_SPECS.items()
}

MARKET_ARMS: tuple[str, ...] = (ARM_RIDGE, ARM_GBM)
EXO_ARMS:    tuple[str, ...] = (ARM_EXO, ARM_MARKET_EXO)
DEFAULT_ARMS: tuple[str, ...] = MARKET_ARMS + EXO_ARMS


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardResult:
    dates: list[pd.Timestamp]
    probabilities: list[float]
    coefficients: list[dict[str, float]]
    n_fits: int
    columns: list[str]
    weight_kind: str = WEIGHT_SIGNED


def walk_forward(
    features: pd.DataFrame,
    labels: pd.Series,
    horizon: int,
    fit_fn: Callable[..., FittedModel],
    min_train: int = MIN_TRAIN_DAYS,
    refit_every: int = REFIT_EVERY,
) -> WalkForwardResult:
    """Refit forward through time, predicting one step at a time.

    The embargo is the whole point. A row dated `d` carries a label that is only
    known `horizon` business days later, so predicting on date `t` may train on
    rows with index `j <= i - horizon - 1` (i is `t`'s position). The extra day
    is a deliberate safety margin: it means a training label is *strictly* in the
    past at prediction time, not resolved on the very close being predicted from.

    Training uses an expanding window; the model is refitted every
    `refit_every` prediction steps and reused in between.
    """
    frame = features.join(labels.rename("__y__")).replace([np.inf, -np.inf], np.nan)
    usable = frame.dropna()
    if usable.empty:
        return WalkForwardResult([], [], [], 0, list(features.columns))

    columns = list(features.columns)
    X_all = usable[columns].to_numpy(dtype=float)
    y_all = usable["__y__"].to_numpy(dtype=float)
    index = usable.index

    embargo = horizon + 1
    first_i = min_train + embargo
    if first_i >= len(index):
        return WalkForwardResult([], [], [], 0, columns)

    dates: list[pd.Timestamp] = []
    probs: list[float] = []
    coefs: list[dict[str, float]] = []
    model: FittedModel | None = None
    n_fits = 0

    for step, i in enumerate(range(first_i, len(index))):
        train_end = i - embargo + 1          # exclusive; rows 0 .. i-embargo
        if train_end < min_train:
            continue
        if model is None or step % refit_every == 0:
            y_train = y_all[:train_end]
            # A single-class training fold has no decision to learn; carry the
            # previous model rather than crash or fabricate a 50/50.
            if len(np.unique(y_train)) < 2:
                if model is None:
                    continue
            else:
                model = fit_fn(X_all[:train_end], y_train, columns)
                n_fits += 1
                if model.coefficients:
                    coefs.append(model.coefficients)
        if model is None:
            continue
        p = float(model.predict_proba(X_all[i:i + 1])[0])
        dates.append(index[i])
        probs.append(p)

    kind = model.weight_kind if model is not None else WEIGHT_SIGNED
    return WalkForwardResult(dates, probs, coefs, n_fits, columns, kind)


def permutation_importance(
    model: FittedModel,
    X: np.ndarray,
    y: np.ndarray,
    columns: Sequence[str],
    n_repeats: int = 5,
    seed: int = SEED,
) -> dict[str, float]:
    """Mean drop in accuracy when one column is shuffled — measured out of sample.

    Reported alongside the ridge coefficients because a tree ensemble's built-in
    `feature_importances_` counts *splits*, which rewards high-cardinality noise;
    a shuffle test asks the question the phase actually cares about: does this
    input pay off against outcomes?
    """
    rng = np.random.default_rng(seed)
    base = float(((model.predict_proba(X) > 0.5).astype(float) == y).mean())
    out: dict[str, float] = {}
    for j, name in enumerate(columns):
        drops = []
        for _ in range(n_repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            acc = float(((model.predict_proba(Xp) > 0.5).astype(float) == y).mean())
            drops.append(base - acc)
        out[name] = float(np.mean(drops))
    return out


# ---------------------------------------------------------------------------
# Probabilities -> the pipeline's own call vocabulary
# ---------------------------------------------------------------------------

def call_from_probability(p: float, deadband: float = NEUTRAL_DEADBAND) -> tuple[str, int]:
    """(bias, confidence_pct) from P(up).

    `confidence` is P(the stated call is correct) — the same reading
    `summarize_accuracy._brier_and_reliability` applies to the LLM's number, so
    the two are Brier-comparable without any translation. Neutral is stamped 50
    because it is excluded from the decisive-only Brier anyway.
    """
    if p > 0.5 + deadband:
        return "Bullish", int(round(p * 100))
    if p < 0.5 - deadband:
        return "Bearish", int(round((1.0 - p) * 100))
    return "Neutral", 50


# ---------------------------------------------------------------------------
# Comparator arms (the ones backtest.py already defines, as call generators)
# ---------------------------------------------------------------------------

def comparator_call(arm: str, close: pd.Series, ts: pd.Timestamp) -> tuple[str, int]:
    """One comparator's call for one asset on one date.

    `random_walk` is `backtest.strategy_random_walk`'s rule — continue the prior
    day's direction — expressed against the panel instead of a live snapshot.
    """
    if arm == ARM_NEUTRAL:
        return "Neutral", 50
    if arm == ARM_ALWAYS_BULL:
        return "Bullish", 55
    if arm == ARM_RANDOM_WALK:
        pos = close.index.get_indexer([ts])[0]
        if pos < 1:
            return "Neutral", 50
        prev, cur = float(close.iloc[pos - 1]), float(close.iloc[pos])
        if cur > prev:
            return "Bullish", 55
        if cur < prev:
            return "Bearish", 55
        return "Neutral", 50
    raise ValueError(f"unknown comparator arm: {arm!r}")


COMPARATOR_ARMS: tuple[str, ...] = (ARM_NEUTRAL, ARM_RANDOM_WALK, ARM_ALWAYS_BULL)


# ---------------------------------------------------------------------------
# Score files — the shape summarize_accuracy / bias_separation already read
# ---------------------------------------------------------------------------

def _price_at(close: pd.Series, ts: pd.Timestamp) -> float | None:
    if ts in close.index:
        v = float(close.loc[ts])
        return v if np.isfinite(v) else None
    return None


def build_score_reports(
    calls: dict[str, dict[str, dict[str, tuple[str, int]]]],
    prices: dict[str, pd.Series],
    horizon_labels: dict[str, int] = SCORING_WINDOWS,
) -> list[dict]:
    """Turn per-arm calls into score files identical in shape to score_predictions.

    `calls` is {arm: {window: {(iso_date, asset): (bias, confidence)}}} flattened
    as {arm: {window: {iso_date: {asset: (bias, confidence)}}}}.

    Scoring goes through `score_call` itself — not a reimplementation — so a
    numeric arm and the LLM arm can never diverge on what counts as a hit, and
    `pct_change` reproduces `score_report`'s formula exactly (percent of entry
    for every asset, including the yield series).
    """
    by_date: dict[str, dict] = {}

    for arm, windows in calls.items():
        for window, dated in windows.items():
            n_days = horizon_labels[window]
            for iso, per_asset in dated.items():
                key = (arm, iso)
                report = by_date.setdefault(key, {
                    "report_date": iso,
                    "arm":         arm,
                    "profile":     NUMERIC_PROFILE,
                    "source":      "numeric_baseline",
                    "windows":     {},
                })
                ts = pd.Timestamp(iso)
                window_assets: dict[str, dict] = {}
                for asset, (bias, conf) in per_asset.items():
                    close = prices.get(asset)
                    if close is None:
                        continue
                    pos = close.index.get_indexer([ts])[0]
                    if pos < 0 or pos + n_days >= len(close):
                        continue
                    entry = float(close.iloc[pos])
                    evalu = float(close.iloc[pos + n_days])
                    if not (np.isfinite(entry) and np.isfinite(evalu)) or entry == 0:
                        continue
                    window_assets[asset] = {
                        "bias":        bias,
                        "confidence":  conf,
                        "entry_price": round(entry, 4),
                        "eval_price":  round(evalu, 4),
                        "eval_date":   close.index[pos + n_days].date().isoformat(),
                        "pct_change":  round((evalu - entry) / entry * 100, 3),
                        "score":       score_call(entry, evalu, bias, asset),
                    }
                if not window_assets:
                    continue
                valid = [v["score"] for v in window_assets.values() if v["score"] is not None]
                report["windows"][window] = {
                    "eval_date": next(iter(window_assets.values()))["eval_date"],
                    "assets":    window_assets,
                    "summary": {
                        "n_scored": len(valid),
                        "accuracy": round(sum(valid) / len(valid), 3) if valid else None,
                    },
                }

    return [r for r in by_date.values() if r["windows"]]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

@dataclass
class ArmRun:
    arm: str
    reports: list[dict]
    coefficients: dict[str, dict[str, float]] = field(default_factory=dict)
    importances: dict[str, dict[str, float]] = field(default_factory=dict)
    n_fits: int = 0


def run_models(
    panel: pd.DataFrame,
    horizons: dict[str, int] = SCORING_WINDOWS,
    arms: Sequence[str] = DEFAULT_ARMS,
    min_train: int = MIN_TRAIN_DAYS,
    refit_every: int = REFIT_EVERY,
    deadband: float = NEUTRAL_DEADBAND,
    with_importance: bool = True,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Walk every (arm, asset, horizon) stream and return calls + diagnostics.

    Returns (calls, diagnostics) where `calls` is the nested structure
    `build_score_reports` consumes and `diagnostics` carries per-stream
    coefficients, permutation importances and fit counts.

    An arm whose feature set is absent from the panel — the exogenous arms on a
    panel built without SPF — is dropped from `calls` with a reason recorded in
    `diagnostics[arm]["skipped"]`. It must not survive as an empty arm: it would
    empty the `shared_call_keys` intersection and take the whole table with it.
    """
    prices = {
        asset: panel[f"px:{asset}"].dropna()
        for asset in ASSET_TICKERS
        if f"px:{asset}" in panel.columns
    }

    calls: dict[str, dict] = {arm: {w: {} for w in horizons} for arm in arms}
    diagnostics: dict[str, dict] = {
        arm: {"streams": {}, "n_fits": 0,
              "feature_set": ARM_SPECS[arm].feature_set}
        for arm in arms
    }

    for asset, close in prices.items():
        # One frame per feature set, not per arm: `ridge` and `gbm` share the
        # market panel and building it twice per asset is pure cost.
        by_set = {
            fs: build_features(panel, asset, fs)
            for fs in {ARM_SPECS[arm].feature_set for arm in arms}
        }
        if all(frame.empty for frame in by_set.values()):
            continue
        for window, horizon in horizons.items():
            labels = forward_label(close.reindex(panel.index).ffill(), horizon)
            for arm in arms:
                spec = ARM_SPECS[arm]
                features = by_set[spec.feature_set]
                if features.empty:
                    diagnostics[arm]["skipped"] = (
                        f"the panel carries no `{spec.feature_set}` features"
                    )
                    continue
                res = walk_forward(
                    features, labels, horizon, spec.fitter,
                    min_train=min_train, refit_every=refit_every,
                )
                if not res.dates:
                    continue
                diagnostics[arm]["n_fits"] += res.n_fits
                stream = diagnostics[arm]["streams"].setdefault(
                    f"{asset}|{window}", {}
                )
                stream["n_predictions"] = len(res.dates)
                stream["n_fits"] = res.n_fits
                stream["weight_kind"] = res.weight_kind
                diagnostics[arm]["weight_kind"] = res.weight_kind
                if res.coefficients:
                    stream["coefficients"] = _mean_coefficients(res.coefficients)
                    if res.weight_kind == WEIGHT_SIGNED:
                        stream["sign_stability"] = _sign_stability(res.coefficients)
                if with_importance:
                    imp = _out_of_sample_importance(
                        features, labels, res, horizon, MODEL_FITTERS[arm], min_train
                    )
                    if imp:
                        stream["permutation_importance"] = imp

                for ts, p in zip(res.dates, res.probabilities):
                    bias, conf = call_from_probability(p, deadband)
                    iso = ts.date().isoformat()
                    calls[arm][window].setdefault(iso, {})[asset] = (bias, conf)

    ran = {arm for arm, windows in calls.items() if any(windows.values())}
    for arm in arms:
        if arm not in ran:
            diagnostics[arm].setdefault("skipped", "produced no calls on this panel")
    return {arm: calls[arm] for arm in arms if arm in ran}, diagnostics


def _mean_coefficients(coefs: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted({k for c in coefs for k in c})
    return {k: round(float(np.mean([c.get(k, 0.0) for c in coefs])), 4) for k in keys}


def _sign_stability(coefs: list[dict[str, float]]) -> dict[str, float]:
    """Share of refits on which a coefficient kept its modal sign.

    A big mean coefficient that flips sign every quarter is a refit artefact, not
    a finding — this is the column that says which is which.
    """
    keys = sorted({k for c in coefs for k in c})
    out: dict[str, float] = {}
    for k in keys:
        signs = [np.sign(c.get(k, 0.0)) for c in coefs]
        if not signs:
            continue
        modal = 1.0 if sum(s > 0 for s in signs) >= sum(s < 0 for s in signs) else -1.0
        out[k] = round(float(np.mean([s == modal for s in signs])), 3)
    return out


def _out_of_sample_importance(
    features: pd.DataFrame,
    labels: pd.Series,
    res: WalkForwardResult,
    horizon: int,
    fit_fn: Callable[..., FittedModel],
    min_train: int,
) -> dict[str, float]:
    """Permutation importance of the final refit, measured on its own test rows.

    Fitted on everything up to the embargo boundary and scored on the prediction
    rows the walk-forward actually produced, so the numbers describe generalisation
    rather than in-sample fit.
    """
    frame = features.join(labels.rename("__y__")).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty or not res.dates:
        return {}
    columns = res.columns
    test_idx = [ts for ts in res.dates if ts in frame.index]
    if len(test_idx) < 30:
        return {}
    # Same embargo as the walk-forward: the rows immediately before the first test
    # date carry labels that only resolve inside the test period, so fitting on
    # them would leak the very outcomes the permutation is measured against.
    train = frame.loc[frame.index < test_idx[0]].iloc[:-(horizon + 1)]
    if len(train) < min_train:
        return {}
    try:
        model = fit_fn(train[columns].to_numpy(dtype=float),
                       train["__y__"].to_numpy(dtype=float), columns)
    except Exception:
        return {}
    test = frame.loc[test_idx]
    return {
        k: round(v, 4)
        for k, v in permutation_importance(
            model,
            test[columns].to_numpy(dtype=float),
            test["__y__"].to_numpy(dtype=float),
            columns,
        ).items()
    }


CallKeys = dict[str, dict[str, frozenset[str]]]


def shared_call_keys(model_calls: dict[str, dict]) -> CallKeys:
    """The (window, date, asset) triples *every* model arm committed to.

    The unit of comparison is the call, not the date. A model cannot predict an
    asset until it has `min_train` days of that asset's own history, so on a date
    where Bitcoin is young the models call five assets and a comparator that
    keys off price availability would call six. Intersecting here — across model
    arms, and per date rather than per window — is what makes "same sample" true
    at the granularity the hit-rate is actually computed on.

    It spans feature sets too, and that matters more than it looks: the exogenous
    features carry fewer NaNs than the market panel's 252-day lookbacks, so an
    exo-only arm can start predicting earlier. Intersecting means every arm — the
    market arms and `always_bullish` included — is judged on the calls *all* of
    them made, so a feature set does not earn hit-rate by starting sooner.
    """
    if not model_calls:
        return {}
    windows = set.intersection(*(set(w) for w in model_calls.values()))
    out: CallKeys = {}
    for window in windows:
        per_arm = [calls[window] for calls in model_calls.values()]
        out[window] = {
            iso: frozenset.intersection(
                *(frozenset(dated[iso]) for dated in per_arm)
            )
            for iso in set.intersection(*(set(dated) for dated in per_arm))
        }
        out[window] = {iso: a for iso, a in out[window].items() if a}
    return out


def restrict_calls(calls: dict[str, dict], keys: CallKeys) -> dict[str, dict]:
    """Clamp every arm to `keys` so the whole table shares one sample.

    A no-op for arms that produced exactly these keys; the point is that the
    guarantee does not depend on that happening to be true.
    """
    out: dict[str, dict] = {}
    for arm, windows in calls.items():
        out[arm] = {}
        for window, dated in windows.items():
            allowed = keys.get(window, {})
            kept = {
                iso: {a: c for a, c in per_asset.items() if a in allowed.get(iso, ())}
                for iso, per_asset in dated.items()
                if iso in allowed
            }
            out[arm][window] = {iso: p for iso, p in kept.items() if p}
    return out


def comparator_calls(
    panel: pd.DataFrame,
    keys_by_window: CallKeys,
    arms: Sequence[str] = COMPARATOR_ARMS,
) -> dict[str, dict]:
    """Comparator calls on exactly the calls the models made.

    Same dates *and the same assets on each date* — otherwise the comparison
    would also be comparing two different samples, which is the error [KB-023]
    was written about. `always_bullish` is the arm this protects: it is the
    benchmark the models are judged against, and handing it a few extra years of
    a young, hard-drifting asset would flatter it for free.
    """
    prices = {
        asset: panel[f"px:{asset}"].dropna()
        for asset in ASSET_TICKERS
        if f"px:{asset}" in panel.columns
    }
    out: dict[str, dict] = {arm: {w: {} for w in keys_by_window} for arm in arms}
    for window, by_date in keys_by_window.items():
        for iso, assets in by_date.items():
            ts = pd.Timestamp(iso)
            for arm in arms:
                per_asset: dict[str, tuple[str, int]] = {}
                for asset in assets:
                    close = prices.get(asset)
                    if close is None or ts not in close.index:
                        continue
                    per_asset[asset] = comparator_call(arm, close, ts)
                if per_asset:
                    out[arm][window][iso] = per_asset
    return out


# ---------------------------------------------------------------------------
# Evaluation — the LLM's own metrics, computed by the LLM's own readers
# ---------------------------------------------------------------------------

def evaluate(reports: list[dict], arm: str, with_separation: bool = True,
             n_perm: int = SEPARATION_DRAWS, n_boot: int = SEPARATION_DRAWS) -> dict:
    """Hit-rate + Brier/BSS/ECE + separation for one arm.

    Every number here comes from the production readers: `_brier_and_reliability`
    from `summarize_accuracy`, `bias_separation` from `bias_separation`. The
    numeric arms are therefore judged on the identical yardstick, not a
    convenient re-implementation of it.

    `with_separation=False` skips the block permutation / bootstrap, which is by
    far the most expensive part of a run — useful for a quick sweep, never for a
    result that gets reported.
    """
    from summarize_accuracy import _brier_and_reliability
    from bias_separation import bias_separation

    scoped = [r for r in reports if r.get("arm") == arm]
    per_window: dict[str, dict] = {}
    all_items: list[dict] = []
    all_scores: list[float] = []

    for report in scoped:
        for window, wdata in report.get("windows", {}).items():
            bucket = per_window.setdefault(window, {"items": [], "scores": []})
            for adata in wdata.get("assets", {}).values():
                sc = adata.get("score")
                if sc is None:
                    continue
                item = {"confidence": adata.get("confidence", 50), "score": sc}
                bucket["items"].append(item)
                bucket["scores"].append(sc)
                all_items.append(item)
                all_scores.append(sc)

    windows_out: dict[str, dict] = {}
    for window, bucket in per_window.items():
        windows_out[window] = {
            "n":              len(bucket["scores"]),
            "mean_score":     round(sum(bucket["scores"]) / len(bucket["scores"]), 4)
                              if bucket["scores"] else None,
            "decisive_hit_rate": _decisive_hit_rate(bucket["scores"]),
            "calibration":    _brier_and_reliability(bucket["items"]),
        }

    return {
        "arm":       arm,
        "n_reports": len(scoped),
        "n_calls":   len(all_scores),
        "overall": {
            "mean_score":        round(sum(all_scores) / len(all_scores), 4) if all_scores else None,
            "decisive_hit_rate": _decisive_hit_rate(all_scores),
            "calibration":       _brier_and_reliability(all_items),
        },
        "windows":    windows_out,
        "separation": (bias_separation(scoped, arm=arm, n_perm=n_perm, n_boot=n_boot)
                       if with_separation else None),
    }


def _decisive_hit_rate(scores: list[float]) -> float | None:
    """Mean over decisive calls only — the number [KB-007] reports as ~36%."""
    decisive = [s for s in scores if s in (0.0, 1.0)]
    if not decisive:
        return None
    return round(sum(decisive) / len(decisive), 4)


# ---------------------------------------------------------------------------
# The verdict — written down before the numbers, per WP-21.D
# ---------------------------------------------------------------------------

# The bar a numeric arm has to clear to count as "there is an edge here".
# Mirrors the calibration bar in [KB-007] and the separation bar in [KB-022] so
# a numeric result and an LLM result are held to the same standard.
EDGE_MIN_N: int = 30
EDGE_MIN_HIT_RATE: float = 0.52
EDGE_MIN_BSS: float = 0.0


def verdict(evaluation: dict) -> str:
    """'edge' / 'no edge' / 'abstains' / 'underpowered', by the bar above."""
    overall = evaluation.get("overall", {})
    calib   = overall.get("calibration") or {}
    n       = calib.get("n", 0)
    if n == 0 and evaluation.get("n_calls"):
        # The all-Neutral comparator makes calls and never commits to one. That is
        # not a small sample — it is an arm with nothing to score, and calling it
        # "underpowered" would imply more data could change the answer.
        return "abstains"
    if n < EDGE_MIN_N:
        return "underpowered"
    hit = overall.get("decisive_hit_rate")
    bss = calib.get("brier_skill_score")
    sep = ((evaluation.get("separation") or {}).get("overall") or {}).get("ordering")
    if hit is None:
        return "underpowered"
    beats_chance = hit > EDGE_MIN_HIT_RATE
    calibrated   = bss is not None and bss > EDGE_MIN_BSS
    aligned      = sep == "aligned"
    if beats_chance and (calibrated or aligned):
        return "edge"
    return "no edge"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_md_lines(evaluations: dict[str, dict], diagnostics: dict[str, dict],
                    meta: dict) -> list[str]:
    lines: list[str] = [
        "# Numeric directional baseline — WP-21.A",
        "",
        "> **The question.** Can a small, regularised numeric model predict 5/10/20-day",
        "> direction on these assets at all? If it cannot, the directional product is dead",
        "> for every model class and the LLM was never the problem. If it can, this is the",
        "> upper bound on achievable skill and the benchmark the LLM arm has never had.",
        "",
        f"- Panel: **{meta.get('panel_start')} → {meta.get('panel_end')}** "
        f"({meta.get('panel_rows')} business days)",
        f"- Features per asset: **{meta.get('n_features')}** market "
        f"(own-price + shared macro state) + **{meta.get('n_exo_features', 0)}** "
        f"exogenous (SPF consensus); unrevised inputs only",
        f"- Walk-forward: expanding window, min train **{meta.get('min_train')}** days, "
        f"refit every **{meta.get('refit_every')}** steps, "
        f"embargo **horizon + 1** trading days",
        "",
        "## Headline",
        "",
        "| Arm | inputs | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for arm, ev in evaluations.items():
        ov    = ev.get("overall", {})
        calib = ov.get("calibration") or {}
        sep   = ((ev.get("separation") or {}).get("overall") or {}).get("ordering")
        bss   = calib.get("brier_skill_score")
        spec  = ARM_SPECS.get(arm)
        lines.append(
            f"| `{arm}` | {spec.feature_set if spec else 'comparator'} | "
            f"{calib.get('n', 0)} | "
            f"{_fmt(ov.get('decisive_hit_rate'))} | {_fmt(ov.get('mean_score'))} | "
            f"{_fmt(calib.get('brier'))} | {_fmt(bss, plus=True)} | "
            f"{_fmt(calib.get('ece'))} | {sep or 'n/a'} | **{verdict(ev)}** |"
        )

    for arm, reason in (meta.get("arms_skipped") or {}).items():
        lines.append(
            f"| `{arm}` | {ARM_SPECS[arm].feature_set if arm in ARM_SPECS else '—'} "
            f"| — | — | — | — | — | — | — | **skipped: {reason}** |"
        )

    n_calls = {ev.get("n_calls", 0) for ev in evaluations.values()}
    sample = (f"all arms scored on the same {n_calls.pop()} calls"
              if len(n_calls) == 1 else
              "⛔ **arms were scored on different samples** — the [KB-023] error; "
              "the comparison below is not valid")

    lines += [
        "",
        f"> **Sample.** {sample}. The comparators call exactly the (date, asset)",
        "> pairs the models called — a model cannot predict an asset until it has",
        "> `min_train` days of that asset's own history, and handing `always_bullish`",
        "> the difference would flatter the benchmark the verdict turns on.",
        "",
        f"> **Bar (pre-committed).** An arm shows an edge only with n ≥ {EDGE_MIN_N} decisive",
        f"> calls, decisive hit-rate > {EDGE_MIN_HIT_RATE:.2f}, and either BSS > {EDGE_MIN_BSS:.0f}",
        "> or an `aligned` separation ordering. Same standard as [KB-007] / [KB-022].",
        "",
        "> **Read the comparator rows before the model rows.** In a drifting tape",
        "> `always_bullish` collects hit-rate for free — that is why the bar also demands",
        "> BSS or an ordering, and why a model that edges past 0.520 while",
        "> `always_bullish` sits at 0.520 has shown nothing.",
        "",
    ]

    lines += _exogenous_lines(evaluations)

    lines += [
        "## Per-horizon",
        "",
        "| Arm | window | n calls | n decisive | decisive hit-rate | Brier | BSS |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, ev in evaluations.items():
        for window in SCORING_WINDOWS:
            w = ev.get("windows", {}).get(window)
            if not w:
                continue
            calib = w.get("calibration") or {}
            lines.append(
                f"| `{arm}` | {window} | {w.get('n', 0)} | {calib.get('n', 0)} | "
                f"{_fmt(w.get('decisive_hit_rate'))} | {_fmt(calib.get('brier'))} | "
                f"{_fmt(calib.get('brier_skill_score'), plus=True)} |"
            )

    lines += ["", "## What each input was worth", ""]
    lines += _importance_lines(diagnostics)
    return lines


def _exogenous_lines(evaluations: dict[str, dict]) -> list[str]:
    """The Phase-19 block: what the two exogenous arms are and what they showed.

    Rendered only when an exogenous arm actually ran, so a market-only run reads
    exactly as it did before the branch was folded in.
    """
    present = [arm for arm in EXO_ARMS if arm in evaluations]
    if not present:
        return []

    lines = [
        "## The exogenous arms (Phase 19, re-pointed)",
        "",
        "> `exogenous_spf` is fit on the Phase-19 anchor **alone** — the Philadelphia",
        "> Fed SPF economist consensus, no price and no market input. `market_plus_exo`",
        "> is the same ridge on the market panel **plus** those columns. Two questions,",
        "> not one: does the anchor carry direction by itself (row 1 against the",
        "> comparators), and does it add anything on top of the market panel",
        "> (`market_plus_exo` against `ridge` — same model, same sample, same rows).",
        "",
        "> **Why this is the whole branch's test and not a sixth arm.** Phase 19's own",
        "> gate was an A/B against the market-only LLM arm, and v1.6 cut that arm's",
        "> calls — the comparator froze. Scoring the anchor here re-points the gate at",
        "> the WP-21.A benchmark [KB-024], which is a real bar and a hard one.",
        "",
        "> **What is missing from it, deliberately.** The SEP dot plot (FRED serves the",
        "> current vintage; each release rewrites earlier years) and the branch's LLM",
        "> extraction layers (trained on the dated text they would read — DESIGN §6.2).",
        "> So this scores the branch's *deterministic, point-in-time* half. A null here",
        "> is a null for the SPF anchor as a directional input, not for the",
        "> expectations-gap mechanism, which needs the FOMC-drift layer this cannot test.",
        "",
    ]

    if ARM_MARKET_EXO in evaluations and ARM_RIDGE in evaluations:
        base = evaluations[ARM_RIDGE]["overall"]
        plus = evaluations[ARM_MARKET_EXO]["overall"]
        b_cal = base.get("calibration") or {}
        p_cal = plus.get("calibration") or {}
        lines += [
            "### Increment over the market panel",
            "",
            "| metric | `ridge` | `market_plus_exo` | Δ |",
            "|---|---|---|---|",
        ]
        for label, b, pl in (
            ("decisive hit-rate", base.get("decisive_hit_rate"), plus.get("decisive_hit_rate")),
            ("Brier",             b_cal.get("brier"),            p_cal.get("brier")),
            ("BSS",               b_cal.get("brier_skill_score"), p_cal.get("brier_skill_score")),
            ("ECE",               b_cal.get("ece"),              p_cal.get("ece")),
        ):
            delta = (pl - b) if (b is not None and pl is not None) else None
            lines.append(f"| {label} | {_fmt(b)} | {_fmt(pl)} | {_fmt(delta, plus=True)} |")
        lines += [
            "",
            "> A Δ inside the noise of a walk-forward this size is a null, not a small",
            "> gain: the two arms differ by seven columns on tens of thousands of shared",
            "> calls, so read the sign only if the pre-committed bar also moves.",
            "",
        ]
    return lines


def _importance_lines(diagnostics: dict[str, dict]) -> list[str]:
    """Pooled per-input value: mean ridge coefficient and mean permutation drop.

    Pooled across streams because a per-stream table is 36 tables nobody reads;
    the per-stream numbers are all in the JSON alongside this report.
    """
    lines: list[str] = []
    for arm, diag in diagnostics.items():
        streams = diag.get("streams", {})
        if not streams:
            continue
        coef_pool: dict[str, list[float]] = {}
        imp_pool: dict[str, list[float]] = {}
        stab_pool: dict[str, list[float]] = {}
        for stream in streams.values():
            for k, v in (stream.get("coefficients") or {}).items():
                coef_pool.setdefault(k, []).append(v)
            for k, v in (stream.get("permutation_importance") or {}).items():
                imp_pool.setdefault(k, []).append(v)
            for k, v in (stream.get("sign_stability") or {}).items():
                stab_pool.setdefault(k, []).append(v)
        if not coef_pool and not imp_pool:
            continue
        signed = diag.get("weight_kind", WEIGHT_SIGNED) == WEIGHT_SIGNED
        weight_header = "mean coefficient" if signed else "mean split importance"
        lines += [
            f"### `{arm}` — {len(streams)} streams, {diag.get('n_fits', 0)} refits",
            "",
            (f"| input | {weight_header} | sign stability | mean permutation drop |"
             if signed else
             f"| input | {weight_header} | mean permutation drop |"),
            "|---|---|---|---|" if signed else "|---|---|---|",
        ]
        keys = sorted(set(coef_pool) | set(imp_pool),
                      key=lambda k: -abs(float(np.mean(imp_pool.get(k, [0.0])))))
        for k in keys:
            coef = float(np.mean(coef_pool[k])) if k in coef_pool else None
            imp  = float(np.mean(imp_pool[k])) if k in imp_pool else None
            stab = float(np.mean(stab_pool[k])) if k in stab_pool else None
            if signed:
                lines.append(
                    f"| `{k}` | {_fmt(coef, plus=True)} | {_fmt(stab)} | "
                    f"{_fmt(imp, plus=True)} |"
                )
            else:
                lines.append(
                    f"| `{k}` | {_fmt(coef)} | {_fmt(imp, plus=True)} |"
                )
        lines += [
            "",
            "> A positive permutation drop means shuffling that input *cost* out-of-sample",
            "> accuracy — the input was load-bearing. Values at or below zero mean it was not.",
        ]
        if signed:
            lines += [
                "> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient",
                "> with high sign stability is what would confirm the effect.",
            ]
        else:
            lines += [
                "> Split importances are unsigned and count *splits*, which rewards"
                " high-cardinality",
                "> noise — read the permutation column, not this one, for what an input"
                " was worth.",
            ]
        lines.append("")
    return lines


def _fmt(v: float | None, plus: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.3f}" if plus else f"{v:.3f}"


# ---------------------------------------------------------------------------
# Backtest-harness interface (backtest.run_backtest wants strategy(snapshot))
# ---------------------------------------------------------------------------

def make_snapshot_fn(calls: dict[str, dict], window: str) -> Callable[[date], dict]:
    """A `_snapshot_fn` for `backtest.run_backtest` serving prebuilt numeric calls.

    `run_backtest` already accepts an injected snapshot function; using it here
    means the numeric arms replay through the *same* harness as every other
    strategy, without the ~40k ALFRED requests a per-date vintage snapshot would
    cost (see the module docstring).
    """
    def _fn(d: date) -> dict:
        iso = d.isoformat()
        return {
            "snapshot_date":  iso,
            "market":         {},
            "numeric_calls":  {arm: w.get(window, {}).get(iso, {}) for arm, w in calls.items()},
        }
    return _fn


def _strategy_from_snapshot(snapshot: dict, arm: str) -> dict:
    per_asset = (snapshot.get("numeric_calls") or {}).get(arm) or {}
    out: dict = {}
    for asset in ASSET_TICKERS:
        bias, conf = per_asset.get(asset, ("Neutral", 50))
        out[asset] = {
            "bias":           bias,
            "confidence":     conf,
            "target_range":   [],
            "primary_driver": f"numeric:{arm}",
        }
    return out


def strategy_ridge(snapshot: dict) -> dict:
    """`backtest.py` strategy interface — the L2 logistic arm."""
    return _strategy_from_snapshot(snapshot, ARM_RIDGE)


def strategy_gbm(snapshot: dict) -> dict:
    """`backtest.py` strategy interface — the shallow GBM arm."""
    return _strategy_from_snapshot(snapshot, ARM_GBM)


def strategy_exogenous_spf(snapshot: dict) -> dict:
    """`backtest.py` strategy interface — the SPF-anchor-only arm."""
    return _strategy_from_snapshot(snapshot, ARM_EXO)


def strategy_market_plus_exo(snapshot: dict) -> dict:
    """`backtest.py` strategy interface — the market panel plus the SPF anchor."""
    return _strategy_from_snapshot(snapshot, ARM_MARKET_EXO)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(
    panel: pd.DataFrame,
    out_dir: Path | None = RESULTS_DIR,
    arms: Sequence[str] = DEFAULT_ARMS,
    horizons: dict[str, int] = SCORING_WINDOWS,
    min_train: int = MIN_TRAIN_DAYS,
    refit_every: int = REFIT_EVERY,
    deadband: float = NEUTRAL_DEADBAND,
    with_importance: bool = True,
    with_separation: bool = True,
    separation_draws: int = SEPARATION_DRAWS,
    emit_scores: bool = False,
    write: bool = True,
) -> dict:
    """Fit, score, compare and (optionally) write the report. Pure given a panel."""
    model_calls, diagnostics = run_models(
        panel, horizons=horizons, arms=arms, min_train=min_train,
        refit_every=refit_every, deadband=deadband, with_importance=with_importance,
    )

    call_keys = shared_call_keys(model_calls)
    comp_calls = comparator_calls(panel, call_keys)

    all_calls = restrict_calls({**model_calls, **comp_calls}, call_keys)
    prices = {
        asset: panel[f"px:{asset}"].dropna()
        for asset in ASSET_TICKERS
        if f"px:{asset}" in panel.columns
    }
    reports = build_score_reports(all_calls, prices, horizon_labels=horizons)

    evaluations = {
        arm: evaluate(reports, arm, with_separation=with_separation,
                      n_perm=separation_draws, n_boot=separation_draws)
        for arm in all_calls
    }
    first_asset = next(iter(prices), None)
    n_features = len(build_features(panel, first_asset).columns) if first_asset else 0
    n_exo = (len(build_features(panel, first_asset, FEATURES_EXO).columns)
             if first_asset else 0)
    meta = {
        "panel_start": str(panel.index.min().date()) if len(panel) else None,
        "panel_end":   str(panel.index.max().date()) if len(panel) else None,
        "panel_rows":  len(panel),
        "n_features":  n_features,
        "n_exo_features": n_exo,
        "min_train":   min_train,
        "refit_every": refit_every,
        "deadband":    deadband,
        "separation_draws": separation_draws if with_separation else None,
        # An arm that could not run is named here rather than silently missing
        # from the table — a blank row and an absent row read very differently.
        "arms_skipped": {arm: diag["skipped"]
                         for arm, diag in diagnostics.items() if "skipped" in diag},
    }

    result = {
        "meta":        meta,
        "evaluations": evaluations,
        "diagnostics": diagnostics,
        "verdicts":    {arm: verdict(ev) for arm, ev in evaluations.items()},
    }

    if write:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if emit_scores:
            # One consolidated, compressed file — not one per (arm, date), the way
            # `score_predictions` writes, which suits a pipeline appending one
            # report a day and not a decade of five simulated arms (~30k reports,
            # ~100MB of indented JSON). Off by default: the report and the
            # diagnostics JSON are the deliverable; this is for re-analysing the
            # calls without refitting, and it is far too big to commit routinely.
            with gzip.open(out_dir / "scores.json.gz", "wt", encoding="utf-8") as fh:
                json.dump(reports, fh)
        (out_dir / "numeric_baseline.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        (out_dir / "numeric_baseline.md").write_text(
            "\n".join(report_md_lines(evaluations, diagnostics, meta)) + "\n",
            encoding="utf-8",
        )
        result["output_dir"] = str(out_dir)

    return result


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="WP-21.A numeric directional baseline")
    ap.add_argument("--start", default="2005-01-01",
                    help="panel start date (default 2005-01-01; the feature "
                         "lookbacks and min-train eat the first ~4 years)")
    ap.add_argument("--panel", type=Path, default=None,
                    help="read a cached panel CSV instead of fetching (offline)")
    ap.add_argument("--save-panel", type=Path, default=None,
                    help="write the fetched panel to this CSV for offline re-runs")
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    ap.add_argument("--min-train", type=int, default=MIN_TRAIN_DAYS)
    ap.add_argument("--refit-every", type=int, default=REFIT_EVERY)
    ap.add_argument("--deadband", type=float, default=NEUTRAL_DEADBAND)
    ap.add_argument("--no-importance", action="store_true",
                    help="skip permutation importance (faster)")
    ap.add_argument("--no-separation", action="store_true",
                    help="skip the bias/return separation section (much faster; "
                         "drops the KB-022 metric, so not for a reported result)")
    ap.add_argument("--separation-draws", type=int, default=SEPARATION_DRAWS,
                    help=f"permutation/bootstrap draws (default {SEPARATION_DRAWS})")
    ap.add_argument("--emit-scores", action="store_true",
                    help="also write scores.json.gz — every simulated call, for "
                         "re-analysis without refitting. Large; off by default.")
    ap.add_argument("--windows", default=None,
                    help="comma-separated subset of t5,t10,t20 (default: all)")
    ap.add_argument("--arms", default=None,
                    help="comma-separated subset of "
                         f"{','.join(ARM_SPECS)} (default: all)")
    ap.add_argument("--spf-dir", type=Path, default=DEFAULT_SPF_DIR,
                    help="directory holding the SPF median-level workbooks "
                         "(default: the committed exogenous/example/ fixtures)")
    ap.add_argument("--no-exogenous", action="store_true",
                    help="skip the Phase-19 SPF anchor entirely — market arms "
                         "only, i.e. the original WP-21.A run")
    args = ap.parse_args()

    arms = DEFAULT_ARMS
    if args.arms:
        wanted = [a.strip() for a in args.arms.split(",") if a.strip()]
        unknown = [a for a in wanted if a not in ARM_SPECS]
        if unknown:
            ap.error(f"unknown arm(s): {', '.join(unknown)}")
        arms = tuple(wanted)
    if args.no_exogenous:
        arms = tuple(a for a in arms if ARM_SPECS[a].feature_set == FEATURES_MARKET)
        if not arms:
            ap.error("--no-exogenous leaves no arms to run")

    horizons = SCORING_WINDOWS
    if args.windows:
        wanted = [w.strip() for w in args.windows.split(",") if w.strip()]
        unknown = [w for w in wanted if w not in SCORING_WINDOWS]
        if unknown:
            ap.error(f"unknown window(s): {', '.join(unknown)}")
        horizons = {w: SCORING_WINDOWS[w] for w in wanted}

    if args.panel:
        panel = load_panel(args.panel)
        print(f"Loaded cached panel: {len(panel)} rows, {len(panel.columns)} columns.")
    else:
        start = date.fromisoformat(args.start)
        print(f"Fetching prices from {start} ...")
        prices = fetch_price_history(start)
        print(f"  {len(prices)} asset series.")
        print("Fetching unrevised FRED inputs ...")
        fred = fetch_fred_inputs(start)
        print(f"  {len(fred)} macro series.")
        exo: dict[str, pd.Series] = {}
        if not args.no_exogenous:
            print("Loading the SPF consensus anchor ...")
            exo = load_spf_inputs(args.spf_dir)
            print(f"  {len(exo)} SPF series.")
        panel = build_panel(prices, fred, exo)
        print(f"Panel: {len(panel)} business days, {len(panel.columns)} columns.")
        if args.save_panel:
            save_panel(panel, args.save_panel)
            print(f"  cached → {args.save_panel}")

    if panel.empty:
        print("Empty panel — nothing to fit.")
        return

    result = run(
        panel,
        out_dir=args.out,
        arms=arms,
        horizons=horizons,
        min_train=args.min_train,
        refit_every=args.refit_every,
        deadband=args.deadband,
        with_importance=not args.no_importance,
        with_separation=not args.no_separation,
        separation_draws=args.separation_draws,
        emit_scores=args.emit_scores,
    )
    print()
    print("\n".join(report_md_lines(result["evaluations"],
                                    result["diagnostics"],
                                    result["meta"])))
    print(f"\nWritten → {result.get('output_dir')}")


if __name__ == "__main__":
    main()
