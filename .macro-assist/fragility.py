"""
fragility.py — System fragility / phase-transition monitor (WP-16.A.1 prototype).

Reframes the product from "what is the price on Friday" to "how close is the
system to a transition." It is a RISK / RESILIENCE gauge, never a directional
signal — downstream it should widen prediction ranges and flag tail risk, not
flip a Bullish/Bearish call.

Empirical grounding (see Project_Development.md, Phase 16): in equity markets
classic *critical slowing down* (rising lag-1 autocorrelation) is NOT a reliable
pre-crash signal, but RISING VARIANCE / VARIABILITY is. So the composite weights
variance- and correlation-based components heavily and treats autocorrelation as
an experimental, low-weight component kept for transparency and ablation.

Each component returns a sub-score in [0, 100] where higher = more fragile.
The composite is a weighted mean of whichever components are available.

PROTOTYPE STATUS: the composite label thresholds here are provisional. WP-16.A.3
will replace them with percentile cut-points calibrated against the index's own
history; WP-16.A.2 must first show (in backtest) that the index leads drawdowns.

Public functions
----------------
realized_variance_trend(close)          -> dict   primary
correlation_tightening(histories)       -> dict   primary
vix_term_backwardation(vix, vix3m)      -> dict   primary
level_acceleration(series)              -> dict   secondary (HY / NFCI)
lag1_autocorrelation(close)             -> dict   experimental
fragility_index(histories, ...)         -> dict   composite
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Composite weights. Primary components (strongest empirical basis) dominate;
# the experimental autocorrelation component is deliberately near-zero.
# Only the available components are used; weights are renormalised over them.
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "variance_trend": 0.35,
    "correlation":    0.30,
    "vix_term":       0.20,
    "acceleration":   0.10,
    "autocorr":       0.05,   # experimental — see module docstring
}

# Assets excluded from the cross-asset correlation / variance aggregate
# (volatility measures are circular to a variance-based fragility test).
_VOL_KEYS = {"vix", "vix3m"}

# Provisional composite labels (WP-16.A.3 will calibrate these to history).
_LABEL_ELEVATED = 65.0
_LABEL_RESILIENT = 40.0


def _to_log_returns(close: pd.Series) -> pd.Series:
    """Close-price Series -> daily log returns, NaNs dropped."""
    close = pd.Series(close).astype(float)
    return np.log(close / close.shift(1)).dropna()


def _squash(x: float, k: float = 1.0) -> float:
    """Map a signed, roughly-standardised quantity to a 0-100 fragility score.

    0 -> 50 (neutral); large positive -> 100; large negative -> 0.
    """
    return float(50.0 * (1.0 + np.tanh(k * x)))


# ---------------------------------------------------------------------------
# Primary components
# ---------------------------------------------------------------------------

def realized_variance_trend(
    close: pd.Series,
    vol_window: int = 20,
    trend_window: int = 60,
) -> Optional[dict]:
    """Score the TREND in realized volatility (rising variance = fragility).

    Fits a least-squares slope to the trailing `trend_window` of a rolling
    `vol_window` realized-vol series, normalised by the mean vol over that
    window so the slope is a dimensionless fractional change.

    Returns None if there is insufficient history.
    """
    rets = _to_log_returns(close)
    rv = rets.rolling(vol_window).std().dropna()
    if len(rv) < 10:
        return None

    window = rv.iloc[-min(trend_window, len(rv)):]
    y = window.to_numpy()
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])

    mean_vol = float(y.mean())
    if mean_vol <= 0:
        return None
    # Fractional change in vol over the whole window (slope * span / level).
    norm_slope = slope * len(y) / mean_vol

    return {
        "score":      _squash(norm_slope, k=2.5),
        "norm_slope": norm_slope,
        "current_vol": float(y[-1]),
        "mean_vol":    mean_vol,
        "n":           int(len(y)),
    }


def correlation_tightening(
    histories: dict,
    window: int = 60,
) -> Optional[dict]:
    """Score cross-asset correlation tightening (diversification breaking down).

    Computes the mean pairwise |correlation| of daily returns across non-vol
    assets over the trailing `window`, and the change vs the prior `window`.
    A high current correlation that is also RISING is the fragility signal.

    Returns None if fewer than two assets have enough overlapping history.
    """
    cols = {}
    for name, close in histories.items():
        if name in _VOL_KEYS or close is None:
            continue
        rets = _to_log_returns(close)
        if len(rets) >= window + 5:
            cols[name] = rets
    if len(cols) < 2:
        return None

    frame = pd.DataFrame(cols).dropna()
    if len(frame) < window + 5:
        return None

    def _mean_abs_corr(block: pd.DataFrame) -> float:
        corr = block.corr().to_numpy()
        iu = np.triu_indices_from(corr, k=1)
        return float(np.nanmean(np.abs(corr[iu])))

    current = _mean_abs_corr(frame.iloc[-window:])
    prior = _mean_abs_corr(frame.iloc[-2 * window:-window]) if len(frame) >= 2 * window else current
    delta = current - prior

    # Level drives the score (high |corr| = fragile); rising level nudges it up.
    score = float(np.clip(100.0 * current + 50.0 * delta, 0.0, 100.0))

    return {
        "score":            score,
        "mean_abs_corr":    current,
        "prior_abs_corr":   prior,
        "delta":            delta,
        "n_assets":         frame.shape[1],
    }


def vix_term_backwardation(
    vix: pd.Series,
    vix3m: pd.Series,
    window: int = 20,
) -> Optional[dict]:
    """Score persistence of VIX-term backwardation (acute near-term stress).

    ratio = VIX / VIX3M; ratio > 1 = backwardation. Score is the fraction of
    the trailing `window` days spent in backwardation, scaled to 0-100.

    Returns None if either series is missing or too short.
    """
    if vix is None or vix3m is None:
        return None
    ratio = (pd.Series(vix).astype(float) / pd.Series(vix3m).astype(float)).dropna()
    if len(ratio) < 5:
        return None
    tail = ratio.iloc[-min(window, len(ratio)):]
    persistence = float((tail > 1.0).mean())
    return {
        "score":         100.0 * persistence,
        "persistence":   persistence,
        "current_ratio": float(ratio.iloc[-1]),
        "n":             int(len(tail)),
    }


# ---------------------------------------------------------------------------
# Secondary component
# ---------------------------------------------------------------------------

def level_acceleration(series: pd.Series, window: int = 8) -> Optional[dict]:
    """Score the ACCELERATION of a slow level series (HY spread, NFCI).

    Uses the second difference (rate-of-change of the rate-of-change),
    standardised by the std of first differences over the window. Rising
    acceleration in a stress level = the system deteriorating faster.

    Returns None if there is insufficient history.
    """
    s = pd.Series(series).astype(float).dropna()
    if len(s) < window + 2:
        return None
    d1 = s.diff()
    d2 = d1.diff().dropna()
    scale = float(d1.tail(window).std())
    if scale <= 0:
        return None
    accel_z = float(d2.iloc[-1]) / scale
    return {
        "score":   _squash(accel_z, k=1.0),
        "accel_z": accel_z,
    }


# ---------------------------------------------------------------------------
# Experimental component (weak in equities — kept for transparency / ablation)
# ---------------------------------------------------------------------------

def lag1_autocorrelation(close: pd.Series, window: int = 60) -> Optional[dict]:
    """Score lag-1 autocorrelation of returns (classic critical slowing down).

    EXPERIMENTAL: the literature finds this is NOT a reliable pre-crash signal
    in equities. Low default weight; retained for ablation studies.
    """
    rets = _to_log_returns(close)
    if len(rets) < window + 1:
        return None
    tail = rets.iloc[-window:]
    acorr = float(tail.autocorr(lag=1))
    if np.isnan(acorr):
        return None
    return {
        "score":  _squash(acorr, k=3.0),
        "acorr":  acorr,
    }


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

def _label(composite: float) -> str:
    if composite >= _LABEL_ELEVATED:
        return "Elevated"
    if composite < _LABEL_RESILIENT:
        return "Resilient"
    return "Normal"


def fragility_index(
    histories: dict,
    hy_spread: Optional[pd.Series] = None,
    nfci: Optional[pd.Series] = None,
    weights: Optional[dict] = None,
) -> Optional[dict]:
    """Composite fragility index from already-fetched data.

    Parameters
    ----------
    histories : dict name -> Close price Series (same shape as
                fetch_market_data()'s second return value). May include 'vix'
                and 'vix3m' for the term-structure component.
    hy_spread : optional FRED HY OAS spread Series (for acceleration).
    nfci      : optional FRED NFCI Series (for acceleration).
    weights   : optional override of DEFAULT_WEIGHTS.

    Returns
    -------
    dict with:
        composite  : 0-100 (higher = more fragile)
        label      : 'Resilient' | 'Normal' | 'Elevated'  (provisional)
        trend      : 'Rising' | 'Stable' | 'Falling'      (is fragility building?)
        components : {name: component dict}  (only those that were computable)
        weights    : the renormalised weights actually applied
    None if no component could be computed.
    """
    w = dict(weights or DEFAULT_WEIGHTS)
    components: dict[str, dict] = {}

    # Variance trend: average the per-asset trend across non-vol assets.
    vt_scores, vt_slopes = [], []
    for name, close in histories.items():
        if name in _VOL_KEYS or close is None:
            continue
        vt = realized_variance_trend(close)
        if vt is not None:
            vt_scores.append(vt["score"])
            vt_slopes.append(vt["norm_slope"])
    if vt_scores:
        components["variance_trend"] = {
            "score":          float(np.mean(vt_scores)),
            "mean_norm_slope": float(np.mean(vt_slopes)),
            "n_assets":       len(vt_scores),
        }

    corr = correlation_tightening(histories)
    if corr is not None:
        components["correlation"] = corr

    vix_term = vix_term_backwardation(histories.get("vix"), histories.get("vix3m"))
    if vix_term is not None:
        components["vix_term"] = vix_term

    accel_scores = []
    for series in (hy_spread, nfci):
        acc = level_acceleration(series) if series is not None else None
        if acc is not None:
            accel_scores.append(acc["score"])
    if accel_scores:
        components["acceleration"] = {"score": float(np.mean(accel_scores)),
                                      "n": len(accel_scores)}

    # Experimental autocorrelation: average across non-vol assets.
    ac_scores = []
    for name, close in histories.items():
        if name in _VOL_KEYS or close is None:
            continue
        ac = lag1_autocorrelation(close)
        if ac is not None:
            ac_scores.append(ac["score"])
    if ac_scores:
        components["autocorr"] = {"score": float(np.mean(ac_scores)),
                                  "n_assets": len(ac_scores)}

    if not components:
        return None

    # Renormalise weights over available components.
    avail = {k: w.get(k, 0.0) for k in components}
    total_w = sum(avail.values())
    if total_w <= 0:
        # Fall back to equal weighting if the override zeroed everything available.
        avail = {k: 1.0 for k in components}
        total_w = float(len(components))
    norm_w = {k: avail[k] / total_w for k in avail}

    composite = float(sum(components[k]["score"] * norm_w[k] for k in components))

    # Trend: is fragility BUILDING? Combine the variance-slope sign with the
    # correlation delta. Both are forward-looking pieces of the composite.
    momentum = 0.0
    if "variance_trend" in components:
        momentum += 0.6 * float(np.tanh(2.5 * components["variance_trend"]["mean_norm_slope"]))
    if "correlation" in components:
        momentum += 0.4 * float(np.tanh(5.0 * components["correlation"]["delta"]))
    if momentum > 0.10:
        trend = "Rising"
    elif momentum < -0.10:
        trend = "Falling"
    else:
        trend = "Stable"

    return {
        "composite":  composite,
        "label":      _label(composite),
        "trend":      trend,
        "components": components,
        "weights":    norm_w,
    }


# ---------------------------------------------------------------------------
# Standalone CLI (manual inspection — not wired into the daily pipeline yet)
# ---------------------------------------------------------------------------

def _cli() -> None:
    import yfinance as yf

    tickers = {
        "sp500": "^GSPC", "nasdaq": "^IXIC", "gold": "GC=F",
        "wti_oil": "CL=F", "dxy": "DX-Y.NYB", "bitcoin": "BTC-USD",
        "vix": "^VIX", "vix3m": "^VIX3M",
    }
    histories: dict = {}
    for name, tk in tickers.items():
        try:
            hist = yf.Ticker(tk).history(period="120d")
            if not hist.empty:
                histories[name] = hist["Close"]
        except Exception as e:   # noqa: BLE001 — CLI convenience only
            print(f"  warn: {tk} failed: {e}")

    result = fragility_index(histories)
    if result is None:
        print("No fragility components could be computed.")
        return

    print(f"\nFragility Index: {result['composite']:.1f}/100  "
          f"[{result['label']}]  trend={result['trend']}\n")
    for name, comp in result["components"].items():
        print(f"  {name:<15} score={comp['score']:6.1f}  weight={result['weights'][name]:.2f}")


if __name__ == "__main__":
    _cli()
