"""
quant_context.py — Build the ## Quantitative Context markdown block (Phase 12).

Combines outputs from three quantitative modules:
  - vol_forecast  (Phase 9): HAR-RV vol forecasts + Variance Risk Premium
  - regime        (Phase 10): HMM macro regime classification
  - conditional   (Phase 11): empirical forward-return distributions

build_quant_context() is called from collect_and_analyze.py after data fetch
and its output is prepended to the Claude user message after the Notable Moves block.

Graceful degradation: if any subsection fails (missing model file, insufficient
data, any exception), that subsection is silently omitted. The block is omitted
entirely if all three subsections fail.
"""
from __future__ import annotations

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

    regime_block = _build_regime_block(snapshot, histories, regime_model)
    if regime_block:
        sections.append(regime_block)

    cond_block = _build_conditional_block(snapshot, distribution_table)
    if cond_block:
        sections.append(cond_block)

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
