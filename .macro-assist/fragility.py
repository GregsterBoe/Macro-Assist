"""
fragility.py — System fragility / phase-transition monitor (WP-16.A.1 prototype).

Reframes the product from "what is the price on Friday" to "how close is the
system to a transition." It is a RISK / RESILIENCE gauge, never a directional
signal — downstream it should widen prediction ranges and flag tail risk, not
flip a Bullish/Bearish call.

Empirical grounding (see Project_Development.md, Phase 16): in equity markets
classic *critical slowing down* (rising lag-1 autocorrelation) is NOT a reliable
pre-crash signal, but RISING VARIANCE / VARIABILITY is. The WP-16.A.3 weight
ablation (de-overlapped, 2008-2026) confirmed this and went further: the
cross-asset CORRELATION component was near-chance too (it did not earn weight),
and lag-1 autocorrelation had no skill. So the composite is now VARIANCE-LED,
gives the VIX term-structure honest-but-capped weight (it is the strongest
single component but semi-circular — backwardation is itself a stress read, so
it must not dominate), keeps `correlation` at a token weight for graceful
degradation, and drops `autocorr` to zero.

Each component returns a sub-score in [0, 100] where higher = more fragile.
The composite is a weighted mean of whichever components are available.

CALIBRATION (WP-16.A.3, Done): weights chosen by de-overlapped ablation (see
Knowledge_Base.md KB-002); composite label thresholds are percentile cut-points
of this scheme's own 2008-2026 composite distribution — Elevated = 90th pct,
Resilient = 40th pct. The 90th-pct (Elevated) cut is exactly the flag whose
episode precision/recall was validated in the backtest.

Public functions
----------------
realized_variance_trend(close)          -> dict   primary
correlation_tightening(histories)       -> dict   primary
absorption_ratio(histories)             -> dict   primary (WP-16.A.6, shadow)
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
# Composite weights — recalibrated in WP-16.A.3 by de-overlapped ablation
# ("var_led_vix35"; see Knowledge_Base.md KB-002). Variance-trend leads (the
# cleanest, non-circular fragility signal); the VIX term-structure gets honest
# but capped weight (strongest component, but semi-circular); `correlation` is
# a token weight (near-chance, kept only for graceful degradation if VIX3M is
# unavailable); `autocorr` is dropped (no skill in equities, as predicted).
# `acceleration` (HY/NFCI) reserves weight for WP-16.A.4 wiring; until then it
# is simply unavailable and renormalised away. Weights renormalise over only
# the components that could be computed.
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "variance_trend": 0.45,
    "vix_term":       0.35,
    "acceleration":   0.15,   # reserved for A.4 (HY spread / NFCI); else inert
    "correlation":    0.05,   # token — near-chance, kept for degradation only
    "autocorr":       0.0,    # dropped — no skill in equities (WP-16.A.2/3)
    "absorption":     0.0,    # WP-16.A.6 SHADOW — computed + logged, zero impact
                              # on the live composite until the backtest earns it
                              # weight (see fragility_backtest WEIGHT_SCHEMES).
}

# Assets excluded from the cross-asset correlation / variance aggregate
# (volatility measures are circular to a variance-based fragility test).
_VOL_KEYS = {"vix", "vix3m"}

# Composite label cut-points — calibrated (WP-16.A.3) to percentiles of the
# var_led_vix35 composite's own 2008-2026 distribution: Elevated = 90th pct,
# Resilient = 40th pct. The Elevated cut is the validated top-decile flag.
_LABEL_ELEVATED = 56.5
_LABEL_RESILIENT = 24.0


def _to_log_returns(close: pd.Series) -> pd.Series:
    """Close-price Series -> daily log returns, NaNs dropped.

    Non-positive prices are masked to NaN first: front-month WTI futures
    printed negative on 2020-04-20, and log() of that is undefined.
    """
    close = pd.Series(close).astype(float)
    close = close.where(close > 0)
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
# Primary component (WP-16.A.6) — the peer-reviewed upgrade to correlation
# ---------------------------------------------------------------------------

def absorption_ratio(
    histories: dict,
    cov_window: int = 60,
    n_eig_frac: float = 0.2,
    short_window: int = 15,
    min_baseline: int = 40,
) -> Optional[dict]:
    """Score the standardized SHIFT in the Absorption Ratio (Kritzman, Li, Page &
    Rigobon 2011, "Principal Components as a Measure of Systemic Risk").

    The Absorption Ratio (AR) is the fraction of cross-asset return variation
    captured by the top few eigenvectors of the return co-movement structure — a
    proxy for how TIGHTLY COUPLED markets are. A high/rising AR means
    diversification is breaking down and a shock in one place propagates broadly;
    the paper found most major US drawdowns were PRECEDED by AR spikes. This is
    the peer-reviewed formalization of the near-dead `correlation_tightening`
    component (KB-002 dropped that to a token weight).

    Adaptation: Macro-Assist tracks a HETEROGENEOUS asset set (equities, gold,
    oil, FX, crypto) with wildly different vols, so we take eigenvalues of the
    CORRELATION matrix (standardized returns), not the raw covariance Kritzman
    used on a homogeneous equity universe — otherwise one high-vol asset (oil,
    BTC) would dominate the eigenstructure and the AR would just track it.

    The score is the paper's early-warning signal, the standardized shift
        shift_z = (AR_short - AR_long) / std(AR_long)
    NOT the raw level: AR stays elevated for a while AFTER a crash, so only the
    transition (a +1 sigma or greater shift) is a forward signal. Returns None if
    fewer than three assets or insufficient history for a baseline.
    """
    cols: dict = {}
    for name, close in histories.items():
        if name in _VOL_KEYS or close is None:
            continue
        rets = _to_log_returns(close)
        if len(rets) >= cov_window + min_baseline:
            cols[name] = rets
    if len(cols) < 3:                      # AR needs a cross-section to decompose
        return None
    frame = pd.DataFrame(cols).dropna()
    if len(frame) < cov_window + min_baseline:
        return None

    n_assets = frame.shape[1]
    n_eig = max(1, int(round(n_eig_frac * n_assets)))
    R = frame.to_numpy()
    T = len(R)

    def _ar_at(end: int) -> Optional[float]:
        block = R[end - cov_window:end]
        if np.any(block.std(axis=0) <= 0):          # a flat column breaks corr
            return None
        c = np.corrcoef(block, rowvar=False)
        if not np.all(np.isfinite(c)):
            return None
        eig = np.linalg.eigvalsh(c)                 # ascending; trace == n_assets
        total = float(eig.sum())
        if total <= 0:
            return None
        return float(eig[-n_eig:].sum() / total)    # top-n_eig variance fraction

    ar_series = [v for end in range(cov_window, T + 1)
                 if (v := _ar_at(end)) is not None]
    if len(ar_series) < min_baseline:
        return None

    ar = np.asarray(ar_series, dtype=float)
    ar_long = float(ar.mean())
    ar_sigma = float(ar.std())
    ar_short = float(ar[-min(short_window, len(ar)):].mean())
    shift_z = 0.0 if ar_sigma <= 1e-9 else (ar_short - ar_long) / ar_sigma

    return {
        "score":    _squash(shift_z, k=1.0),
        "ar":       float(ar[-1]),
        "ar_short": ar_short,
        "ar_long":  ar_long,
        "shift_z":  shift_z,
        "n_eig":    n_eig,
        "n_assets": n_assets,
    }


# ---------------------------------------------------------------------------
# Primary component (WP-16.A.6 / IMP-1) — turbulence, the complement to AR
# ---------------------------------------------------------------------------

def turbulence_signal(
    sliced: dict,
    cov_window: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    min_baseline: int = 252,
) -> Optional[float]:
    """Financial-turbulence score (Kritzman & Li 2010, "Skulls, Financial
    Turbulence, and Risk Management"): the Mahalanobis distance of the most
    recent return vector from the trailing cross-sectional mean, measured in the
    metric of the trailing covariance,
        d_t = (r_t - mu)' Sigma^-1 (r_t - mu).
    A large d_t means today's return pattern is statistically unusual GIVEN the
    recent volatilities AND correlations — the co-movement structure is under
    stress. Unlike the absorption ratio (which reads the eigenstructure), this
    reads the *surprise* of the latest observation against it; the two are
    complementary, which IMP-1.5/1.6 confirmed (KB-015/016) and IMP-4.2 carried
    onto the live sector-ETF panel (KB-020). It graduated here from the
    input_testing harness once validated.

    Estimation notes for a homogeneous panel (~9-30 names):
      * covariance is Ledoit-style shrunk toward its diagonal (`shrink`) so the
        inverse is stable even from a ~year window;
      * the score averages the last `smooth` daily distances (single-day
        turbulence is very spiky), all against the SAME window mu/Sigma;
      * everything uses only observations up to the anchor date (PIT-safe).
    Returns None if the panel is too short/narrow to condition on. This returns a
    RAW distance (higher = more turbulent); it is rank/threshold-scored downstream,
    not squashed to 0-100 like the composite components.
    """
    rets = {}
    for name, prices in sliced.items():
        if name in _VOL_KEYS or prices is None:
            continue
        p = pd.Series(prices).astype(float)
        p = p.where(p > 0)
        r = np.log(p / p.shift(1)).dropna()
        if len(r):
            rets[name] = r
    if len(rets) < 3:
        return None
    R = pd.DataFrame(rets).dropna()
    if R.shape[0] < min_baseline or R.shape[1] < 3:
        return None

    win = R.tail(cov_window)
    n_obs, n_assets = win.shape
    if n_obs < max(60, n_assets + 5):          # need the inverse to be sane
        return None

    mu = win.mean().to_numpy()
    X = win.to_numpy() - mu
    cov = np.cov(X, rowvar=False)
    diag = np.diag(np.diag(cov))               # shrink toward pure-variance target
    cov_s = (1.0 - shrink) * cov + shrink * diag
    try:
        inv = np.linalg.inv(cov_s)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(cov_s)

    k = min(smooth, len(X))
    dists = [float(row @ inv @ row) for row in X[-k:]]
    dists = [d for d in dists if np.isfinite(d) and d >= 0]
    if not dists:
        return None
    return float(np.mean(dists))               # rank-scored downstream; raw is fine


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

    absorp = absorption_ratio(histories)
    if absorp is not None:
        components["absorption"] = absorp

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

    # Trend: is fragility BUILDING? Driven mainly by the variance slope (the
    # lead signal); the correlation delta only nudges it, mirroring its token
    # weight in the composite after the A.3 recalibration. NOTE: the A.2/A.3
    # backtest validated the LEVEL flags (Elevated / top-decile), not this
    # Rising trend flag (which fired too often). Treat trend as informational.
    momentum = 0.0
    if "variance_trend" in components:
        momentum += 0.85 * float(np.tanh(2.5 * components["variance_trend"]["mean_norm_slope"]))
    if "correlation" in components:
        momentum += 0.15 * float(np.tanh(5.0 * components["correlation"]["delta"]))
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
