"""
vol_forecast.py — HAR-RV volatility forecasting and Variance Risk Premium.

HAR-RV (Heterogeneous Autoregressive Realized Variance, Corsi 2009):
    RV_{t+1} = β₀ + β₁·RV_daily + β₂·RV_weekly + β₃·RV_monthly

VRP (Variance Risk Premium):
    VRP = VIX − annualized HAR-RV forecast

Both functions are pure numpy/pandas — no `arch` dependency at runtime.
The `arch` package is in requirements.txt for future VRP utility extensions.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Minimum returns a live consumer may fit HAR-RV on. [KB-033] read the function
# walk-forward: `degenerate` on every asset at 62/90/130 returns (a four-parameter
# OLS on a few dozen rows; zero forecasts on 1.5–7 % of readings), `parity` at
# best at 252, `skill` on SP500 / Gold / Bitcoin at 1000. This is the number the
# method asks for; the fetch periods in `market_data` and `portfolio/rebalance`
# are sized to deliver it, and `har_forecast_or_none` refuses anything shorter.
# `har_rv_forecast` itself keeps its 30-return floor so `har_backtest.py` can
# still read the short windows.
HAR_MIN_RETURNS = 1000


def har_rv_forecast(returns: pd.Series, horizon: int = 5) -> dict:
    """
    Fit HAR-RV on daily log returns and produce a 1-step-ahead realized variance forecast.

    RV components (all from squared daily returns):
      RV_daily   = r²ₜ
      RV_weekly  = mean(r²_{t-4} … r²ₜ)    (5-day mean)
      RV_monthly = mean(r²_{t-21} … r²ₜ)   (22-day mean)

    Parameters
    ----------
    returns : daily log returns (e.g. log(P_t / P_{t-1}))
    horizon : unused in the 1-step OLS formulation; retained for API consistency

    Returns
    -------
    dict
        forecast_daily_vol   : annualized daily vol, %
        forecast_horizon_vol : same annualized figure (IID scaling is identity)
        percentile_60d       : percentile of forecast vs trailing 60d daily vols (0-100)
        r_squared            : in-sample OLS R²
        params               : beta_0, beta_d, beta_w, beta_m
    """
    rv = np.asarray(returns, dtype=float) ** 2
    n = len(rv)
    if n < 30:
        raise ValueError(f"Need at least 30 returns to fit HAR-RV, got {n}")

    # Build design matrix.  Require t >= 21 so the monthly feature is well-defined;
    # target is rv[t+1], so we also need t+1 < n.
    start = 21
    T = n - start - 1
    if T < 1:
        raise ValueError(f"Insufficient data after lagging (n={n})")

    X = np.empty((T, 4))
    y = rv[start + 1: start + 1 + T]

    for i in range(T):
        t = start + i
        X[i, 0] = 1.0
        X[i, 1] = rv[t]                         # RV_daily
        X[i, 2] = rv[t - 4: t + 1].mean()       # RV_weekly
        X[i, 3] = rv[t - 21: t + 1].mean()      # RV_monthly

    params, _, _, _ = np.linalg.lstsq(X, y, rcond=None)

    y_hat = X @ params
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = float(np.clip(1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0, 0.0, 1.0))

    # One-step-ahead forecast using the most recent observations.
    t_last = n - 1
    x_new = np.array([
        1.0,
        rv[t_last],
        rv[max(0, t_last - 4): t_last + 1].mean(),
        rv[max(0, t_last - 21): t_last + 1].mean(),
    ])
    rv_forecast = max(0.0, float(params @ x_new))

    # Annualise: daily vol = sqrt(rv_forecast) * sqrt(252), expressed as %.
    # Under IID, the annualised rate is horizon-invariant, so both fields are identical.
    forecast_daily_vol   = float(np.sqrt(rv_forecast * 252) * 100)
    forecast_horizon_vol = forecast_daily_vol

    # Percentile: where does the forecast sit relative to trailing 60 daily annualised vols?
    window = rv[max(0, t_last - 59): t_last + 1]
    trailing_vols = np.sqrt(window * 252) * 100
    percentile_60d = float(np.mean(trailing_vols <= forecast_daily_vol) * 100)

    return {
        "forecast_daily_vol":   forecast_daily_vol,
        "forecast_horizon_vol": forecast_horizon_vol,
        "percentile_60d":       percentile_60d,
        "r_squared":            r_squared,
        "params": {
            "beta_0": float(params[0]),
            "beta_d": float(params[1]),
            "beta_w": float(params[2]),
            "beta_m": float(params[3]),
        },
    }


def har_forecast_or_none(returns: pd.Series) -> Optional[dict]:
    """`har_rv_forecast` under the live-consumer gates, or None.

    None when the history is shorter than `HAR_MIN_RETURNS` or when the OLS
    forecast is non-positive (the `max(0, ·)` clip inside `har_rv_forecast`
    fired). A zero forecast is an absence, not a number: before this guard the
    note printed `0.0% ann-vol` with `VRP = VIX − 0` attached, and the sizer
    floored it to a 2 %-vol instrument ([KB-033] nuance (e)). Every live caller
    — the note block, the JSONL raw block, the paper-portfolio sizer — goes
    through here; `score_distributions.logged_har_sigma` applies the same
    `≤ 0 → no forecast` rule on the logged side.
    """
    if returns is None or len(returns) < HAR_MIN_RETURNS:
        return None
    fc = har_rv_forecast(returns)
    if not fc["forecast_daily_vol"] > 0:
        return None
    return fc


def variance_risk_premium(
    vix: float,
    harrv_forecast: dict,
    history: Optional[pd.DataFrame] = None,
) -> dict:
    """
    VRP = VIX − annualized HAR-RV forecast (both in % annualised vol space).

    A positive VRP means the options market prices in more risk than the
    HAR-RV model projects (the typical long-run state).  A negative / compressed
    VRP occurs when recent realised moves have extrapolated HAR-RV above VIX —
    often at the peak of a crisis when squared returns temporarily dominate.

    Parameters
    ----------
    vix           : current VIX level (0-100 scale, already annualised %)
    harrv_forecast: output of har_rv_forecast()
    history       : DataFrame with columns 'vix' and 'realized_vol' (annualised %)
                    used to compute a 60-day trailing percentile for VRP.
                    If None or empty, percentile defaults to 50 (neutral).

    Returns
    -------
    dict
        vrp               : float
        vrp_60d_percentile: float  (0-100)
        interpretation    : 'Compressed' | 'Normal' | 'Elevated'
    """
    vrp = vix - harrv_forecast["forecast_daily_vol"]

    if history is not None and len(history) > 0:
        hist_vrp = history["vix"] - history["realized_vol"]
        recent_60 = hist_vrp.tail(60)
        vrp_percentile = float(np.mean(recent_60 <= vrp) * 100)
    else:
        vrp_percentile = 50.0

    if vrp_percentile <= 25:
        interpretation = "Compressed"
    elif vrp_percentile >= 75:
        interpretation = "Elevated"
    else:
        interpretation = "Normal"

    return {
        "vrp":                float(vrp),
        "vrp_60d_percentile": vrp_percentile,
        "interpretation":     interpretation,
    }
