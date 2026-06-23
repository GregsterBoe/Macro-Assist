"""
quant_context.py — Build the ## Quantitative Context markdown block (Phase 12).

Combines outputs from these quantitative modules:
  - vol_forecast  (Phase 9): HAR-RV vol forecasts + Variance Risk Premium
  - conditional   (Phase 11): empirical forward-return distributions
  - fragility     (Phase 16): system fragility / phase-transition monitor
                   (SHADOW — FRAGILITY_MODE ladder log/show/active, default
                   'log': computed + logged only, not shown, zero note impact)
  - regime        (Phase 10): HMM macro regime — RETIRED (WP-17.4 / KB-006:
                   validated as redundant dead weight; a 4-feature rule beat it).
                   _build_regime_block is kept but no longer wired into the note.

build_quant_context() is called from collect_and_analyze.py after data fetch
and its output is prepended to the Claude user message after the Notable Moves block.

Graceful degradation: if any subsection fails (missing model file, insufficient
data, any exception), that subsection is silently omitted. The block is omitted
entirely if all subsections fail.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from vol_forecast import har_rv_forecast, variance_risk_premium
from regime import predict_regime, load_regime_model, label_states, DEFAULT_MODEL_PATH
from regime_features import regime_features
from conditional import (
    assign_bucket,
    lookup_distribution,
    load_distribution_table,
    DEFAULT_TABLE_PATH,
)
from fragility import fragility_index

# ---------------------------------------------------------------------------
# Fragility monitor (Phase 16, WP-16.A.4) — wired in SHADOW mode via a 3-level
# ladder, controlled by the FRAGILITY_MODE env var (default "log"):
#
#   log    — computed and written to the JSONL log ONLY; NOT shown in the
#            prompt. Zero effect on the note. The safe default for running on
#            main: accumulate >=20 trading days of readings with no influence.
#   show   — the reading is rendered into the context (informational); no
#            behavioural directive. The model sees it and may use it.
#   active — + the behavioural directive: when Elevated, widen Target Ranges
#            and add a tail-risk bullet. NEVER flips the Bias direction.
#
# Escalate log -> show -> active only after each level looks sane. The monitor
# is a RISK gauge, never a directional signal.
# ---------------------------------------------------------------------------
_FRAGILITY_MODE_ENV = "FRAGILITY_MODE"
_VALID_FRAGILITY_MODES = ("log", "show", "active")

# Validated on a 180-day trailing window; the daily pipeline's `histories` is
# only ~90 calendar days, so fetch a proper window when what we're handed is
# too short. Below this many anchor rows we fetch our own history.
_MIN_FRAG_HISTORY = 150

# Tickers for the self-contained fragility fetch (mirror fragility_backtest).
_FRAG_TICKERS: dict[str, str] = {
    "sp500": "^GSPC", "nasdaq": "^IXIC", "gold": "GC=F",
    "wti_oil": "CL=F", "dxy": "DX-Y.NYB", "vix": "^VIX", "vix3m": "^VIX3M",
}


def _fragility_mode() -> str:
    """Resolve the active fragility mode from the environment (default 'log')."""
    mode = os.getenv(_FRAGILITY_MODE_ENV, "").strip().lower()
    if mode in _VALID_FRAGILITY_MODES:
        return mode
    return "log"


def _fetch_fragility_histories(period: str = "1y") -> dict:
    """Pull ~1y of daily Close for the tracked tickers (yfinance, free). Returns
    {} on any failure so the caller can degrade gracefully."""
    try:
        import yfinance as yf
    except Exception:
        return {}
    out: dict = {}
    for name, tk in _FRAG_TICKERS.items():
        try:
            hist = yf.Ticker(tk).history(period=period)
            if hist.empty:
                continue
            close = hist["Close"]
            try:
                close.index = close.index.tz_localize(None)
            except (TypeError, AttributeError):
                pass
            out[name] = close
        except Exception:
            continue
    return out


def _compute_fragility(histories: Optional[dict], allow_fetch: bool = True) -> Optional[dict]:
    """Compute the fragility index for the live context.

    Uses the supplied `histories` if its anchor is long enough; otherwise (the
    normal pipeline case — only ~90d on hand) fetches a proper window. Returns
    None if no usable data, or if `histories` is absent entirely (so callers
    with no data trigger no network). Never raises.
    """
    if not histories:
        return None
    frag_hist: Optional[dict] = None
    anchor = histories.get("sp500")
    if anchor is not None and len(anchor) >= _MIN_FRAG_HISTORY:
        frag_hist = histories
    elif allow_fetch:
        fetched = _fetch_fragility_histories()
        if fetched:
            frag_hist = fetched
    if not frag_hist:
        return None
    try:
        return fragility_index(frag_hist)
    except Exception:
        return None

# Asset mapping: histories key → display name for the Volatility block
_VOL_ASSETS: list[tuple[str, str]] = [
    ("sp500",   "SP500"),
    ("gold",    "Gold"),
    ("wti_oil", "WTI Oil"),
    ("bitcoin", "Bitcoin"),
]

# Rows for the conditional return distribution table: (display_name, horizon_days)
_COND_ROWS: list[tuple[str, int]] = [
    ("SP500",    5),
    ("SP500",   20),
    ("Gold",     5),
    ("Gold",    20),
    ("WTI Oil",  5),
    ("WTI Oil", 20),
]


def collect_quant_raw(
    snapshot: dict,
    snapshot_date: date,
    market_data: Optional[dict] = None,
    histories: Optional[dict] = None,
    regime_model=None,
    distribution_table: Optional[dict] = None,
) -> dict:
    """
    Return raw subsection outputs as a plain dict for JSONL logging (Phase 14.3).

    Mirrors build_quant_context() but emits a structured dict instead of markdown.
    Keys present only when the corresponding module succeeds.
    """
    raw: dict = {}

    # --- Vol forecasts ---
    if histories:
        vix_value: Optional[float] = None
        if market_data:
            try:
                vix_value = float(market_data["vix"]["price"])
            except (KeyError, TypeError, ValueError):
                pass

        vol_raw: dict = {}
        for key, display in _VOL_ASSETS:
            close = histories.get(key)
            if close is None or len(close) < 32:
                continue
            try:
                returns = pd.Series(np.log(close.values[1:] / close.values[:-1]))
                fc      = har_rv_forecast(returns)
                entry: dict = {
                    "forecast_daily_vol": round(fc["forecast_daily_vol"], 2),
                    "percentile_60d":     round(fc["percentile_60d"], 1),
                }
                if key == "sp500" and vix_value is not None:
                    vrp = variance_risk_premium(vix_value, fc)
                    entry["vix"]              = round(vix_value, 2)
                    entry["vrp"]              = round(vrp["vrp"], 2)
                    entry["vrp_interpretation"] = vrp["interpretation"]
                vol_raw[display] = entry
            except Exception:
                continue
        if vol_raw:
            raw["vol_forecasts"] = vol_raw

    # --- Regime: RETIRED (WP-17.4 / KB-006) ---
    # The HMM regime layer was validated as redundant dead weight: a 4-feature
    # rule beat it (drawdown AUC 0.70 vs 0.55) and it added nothing within stress
    # strata. Dropped from the daily note + log. regime.py / refit_models are
    # left in place (model still fit weekly, now unconsumed) pending cleanup.

    # --- Conditional distribution ---
    try:
        _table = distribution_table
        if _table is None:
            if not DEFAULT_TABLE_PATH.exists():
                raise FileNotFoundError(DEFAULT_TABLE_PATH)
            _table = load_distribution_table()

        if _table:
            bucket = assign_bucket(snapshot)
            cond_raw: dict = {"bucket": bucket, "distributions": {}}
            for asset, horizon in _COND_ROWS:
                dist = lookup_distribution(bucket, asset, horizon, _table)
                if dist is not None:
                    cond_raw["distributions"][f"{asset}_{horizon}d"] = {
                        "p50": round(dist.get("p50", float("nan")), 2),
                        "n":   dist.get("n", 0),
                    }
            raw["conditional"] = cond_raw
    except Exception:
        pass

    # --- Fragility monitor (Phase 16, shadow) ---
    # Always computed and logged regardless of mode — this is the log-only
    # observation path that accumulates the shadow record on main.
    try:
        frag = _compute_fragility(histories)
        if frag:
            raw["fragility"] = {
                "composite":  round(frag["composite"], 2),
                "label":      frag["label"],
                "trend":      frag["trend"],
                "components": {k: round(v["score"], 2) for k, v in frag["components"].items()},
                "weights":    {k: round(w, 3) for k, w in frag.get("weights", {}).items()},
                "mode":       _fragility_mode(),
            }
    except Exception:
        pass

    return raw


def build_quant_context(
    snapshot: dict,
    snapshot_date: date,
    market_data: Optional[dict] = None,
    histories: Optional[dict] = None,
    regime_model=None,
    distribution_table: Optional[dict] = None,
) -> str:
    """
    Build the ## Quantitative Context markdown block.

    Parameters
    ----------
    snapshot          : FRED data dict (output of fetch_fred_data())
    snapshot_date     : the date of the snapshot (unused internally, kept for API consistency)
    market_data       : market price dict (output of fetch_market_data()[0])
                        Used for VIX level in the VRP calculation.
    histories         : close price series dict (output of fetch_market_data()[1])
                        Used for HAR-RV log-return computation.
    regime_model      : pre-loaded GaussianHMM model; if None, loaded from disk.
    distribution_table: pre-loaded conditional distribution table; if None, loaded from disk.

    Returns
    -------
    str — markdown block starting with '## Quantitative Context', or '' if all
    subsections fail or no data is available.
    """
    sections: list[str] = []

    vol_block = _build_vol_block(snapshot, market_data, histories)
    if vol_block:
        sections.append(vol_block)

    # Regime (HMM) subsection retired — WP-17.4 / KB-006 (redundant dead weight).

    cond_block = _build_conditional_block(snapshot, distribution_table)
    if cond_block:
        sections.append(cond_block)

    frag_block = _build_fragility_block(histories)
    if frag_block:
        sections.append(frag_block)

    if not sections:
        return ""

    return "## Quantitative Context\n\n" + "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Subsection builders
# ---------------------------------------------------------------------------

def _build_vol_block(
    snapshot: dict,
    market_data: Optional[dict],
    histories: Optional[dict],
) -> str:
    """Build the Volatility (HAR-RV) subsection."""
    if not histories:
        return ""

    vix_value: Optional[float] = None
    if market_data:
        try:
            vix_value = float(market_data["vix"]["price"])
        except (KeyError, TypeError, ValueError):
            pass

    lines: list[str] = []
    for key, display in _VOL_ASSETS:
        close = histories.get(key)
        if close is None or len(close) < 32:
            continue
        try:
            returns = pd.Series(np.log(close.values[1:] / close.values[:-1]))
            fc      = har_rv_forecast(returns)
            vol     = fc["forecast_daily_vol"]
            pct     = fc["percentile_60d"]
            line    = f"- {display}: {vol:.1f}% ann-vol (60d pct {pct:.0f})"
            if key == "sp500" and vix_value is not None:
                vrp      = variance_risk_premium(vix_value, fc)
                vrp_val  = vrp["vrp"]
                vrp_sign = "+" if vrp_val >= 0 else ""
                line += (
                    f"; VIX {vix_value:.1f}%"
                    f" → VRP {vrp_sign}{vrp_val:.1f}"
                    f" ({vrp['interpretation']})"
                )
            lines.append(line)
        except Exception:
            continue

    if not lines:
        return ""
    return "**Volatility (HAR-RV, 5d ahead):**\n" + "\n".join(lines)


def _build_regime_block(
    snapshot: dict,
    histories: Optional[dict],
    regime_model=None,
) -> str:
    """Build the Regime (HMM) subsection."""
    try:
        if regime_model is None:
            if not DEFAULT_MODEL_PATH.exists():
                return ""
            regime_model = load_regime_model()

        sp500_returns: Optional[pd.Series] = None
        if histories and "sp500" in histories:
            close = histories["sp500"]
            if len(close) >= 2:
                sp500_returns = pd.Series(
                    np.log(close.values[1:] / close.values[:-1])
                )

        features = regime_features(snapshot, sp500_returns)
        # Replace NaN features with neutral defaults so HMM doesn't crash on
        # missing data (e.g. no SP500 history for vol feature).
        features = np.where(np.isnan(features), 0.0, features)
        result   = predict_regime(regime_model, features)

        state       = result["state"]
        state_label = result["state_label"]
        posterior   = result["posterior"]
        trans       = result["transition_probs_from_current"]
        max_post    = float(posterior[state])

        all_labels = label_states(regime_model)

        # Build transition probability string: stay + top-2 others (> 1% prob)
        stay_p = trans[state]
        others = sorted(
            [(i, p) for i, p in trans.items() if i != state],
            key=lambda x: x[1],
            reverse=True,
        )[:2]
        trans_parts = [f"stay {stay_p:.2f}"]
        for i, p in others:
            if p > 0.01:
                lbl = all_labels.get(i, f"State {i}")
                trans_parts.append(f"{lbl} {p:.2f}")

        lines = [
            f"Current: {state_label} (posterior {max_post:.2f})",
            f"Transition probabilities: {' | '.join(trans_parts)}",
        ]
        return "**Regime (HMM, 4-state):**\n" + "\n".join(lines)

    except Exception:
        return ""


def _build_fragility_block(
    histories: Optional[dict] = None,
    allow_fetch: bool = True,
    _result: Optional[dict] = None,
    mode: Optional[str] = None,
) -> str:
    """Build the Fragility Monitor subsection (Phase 16, shadow).

    Returns "" in 'log' mode (the reading is logged elsewhere, never shown).
    In 'show'/'active' it renders the composite, label, trend, and weighted
    drivers; in 'active' an Elevated reading also carries the behavioural
    directive. `_result` lets tests inject a precomputed fragility dict to
    avoid any network fetch; `mode` overrides the env for tests.
    """
    mode = mode or _fragility_mode()
    if mode == "log":
        return ""

    result = _result if _result is not None else _compute_fragility(histories, allow_fetch)
    if not result:
        return ""

    composite = result["composite"]
    label     = result["label"]
    trend     = result["trend"]
    comps     = result.get("components", {})
    weights   = result.get("weights", {})

    # Only show components that actually carry weight (e.g. autocorr is w0).
    drivers = sorted(
        ((n, c) for n, c in comps.items() if weights.get(n, 0.0) > 0.0),
        key=lambda kv: weights.get(kv[0], 0.0), reverse=True,
    )
    driver_strs = [
        f"{name} {c['score']:.0f} (w{weights.get(name, 0.0):.2f})"
        for name, c in drivers
    ]

    lines = [
        "**Fragility Monitor (experimental — Phase 16; risk gauge, not directional):**",
        f"- Composite: {composite:.0f}/100 [{label}], trend {trend}",
    ]
    if driver_strs:
        lines.append(f"- Drivers: {', '.join(driver_strs)}")

    if label == "Elevated":
        rising = " and Rising" if trend == "Rising" else ""
        if mode == "active":
            lines.append(
                f"- → **Action:** fragility is Elevated{rising}. Widen your Target Ranges and "
                "add an explicit tail-risk bullet to Key Risks. Do NOT change the Bias "
                "direction on this basis."
            )
        else:  # show
            lines.append(
                "- → _(monitoring — directive inactive; "
                f"set {_FRAGILITY_MODE_ENV}=active to enable range-widening.)_"
            )

    return "\n".join(lines)


def _build_conditional_block(
    snapshot: dict,
    distribution_table: Optional[dict],
) -> str:
    """Build the Conditional return distribution subsection."""
    try:
        if distribution_table is None:
            if not DEFAULT_TABLE_PATH.exists():
                return ""
            distribution_table = load_distribution_table()

        if not distribution_table:
            return ""

        bucket = assign_bucket(snapshot)

        rows: list[tuple[str, int, dict]] = []
        for asset, horizon in _COND_ROWS:
            dist = lookup_distribution(bucket, asset, horizon, distribution_table)
            if dist is not None:
                rows.append((asset, horizon, dist))

        if not rows:
            return ""

        # Use n from the first resolved lookup for the header
        sample_n = rows[0][2].get("n", "?")

        table_lines = [
            f"**Conditional return distribution (bucket: {bucket}, n={sample_n}):**",
            "| Asset | Horizon | P25 | Median | P75 |",
            "|-------|---------|-----|--------|-----|",
        ]
        for asset, horizon, dist in rows:
            p25 = dist.get("p25", float("nan"))
            p50 = dist.get("p50", float("nan"))
            p75 = dist.get("p75", float("nan"))
            table_lines.append(
                f"| {asset} | {horizon}d"
                f" | {p25:+.1f}% | {p50:+.1f}% | {p75:+.1f}% |"
            )

        return "\n".join(table_lines)

    except Exception:
        return ""
