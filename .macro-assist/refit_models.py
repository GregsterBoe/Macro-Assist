"""
refit_models.py — Weekly model refit for the quantitative context layer.

Called by macro_weekly_refit.yml every Sunday 22:00 UTC.

Steps:
    1. Fetch 5yr FRED data (one API call per series via fredapi)
    2. Fetch 5yr yfinance price history (SP500, Gold, WTI Oil)
    3. Build daily 4-feature matrix for the HMM
    4. Refit GaussianHMM → data/regime_model.pkl
    5. Build forward-return dict and rebuild conditional distribution table
       → data/conditional_distributions.json

Idempotent: re-running in the same week with the same market data produces
identical artifacts (same random_state, same training window).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from fredapi import Fred

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from regime import fit_regime_model, DEFAULT_MODEL_PATH
from conditional import build_distribution_table, DEFAULT_TABLE_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASSETS: dict[str, str] = {
    "SP500":   "^GSPC",
    "Gold":    "GC=F",
    "WTI Oil": "CL=F",
}

_HORIZONS: tuple[int, ...] = (5, 10, 20)

_FRED_SERIES: dict[str, str] = {
    "nfci":         "NFCI",
    "treasury_10y": "DGS10",
    "treasury_2y":  "DGS2",
    "hy_spread":    "BAMLH0A0HYM2",
}

# NFCI clipping bounds (long-run historical range, matching regime_features.py)
_NFCI_MIN: float = -0.9
_NFCI_MAX: float =  2.8

# HY spread typical std (matching regime_features.py)
_HY_STD: float = 1.5

# Minimum valid history days required before fitting
_MIN_FIT_DAYS: int = 252

# Rolling window for HY 5yr mean (252 bdays/yr × 5)
_HY_MEAN_WINDOW: int = 1260


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(section: str, msg: str) -> None:
    print(f"[{section:<12}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_fred_series(fred: Fred, years: int = 5) -> dict[str, pd.Series]:
    """Return FRED series needed for feature computation (5yr history)."""
    start = (date.today() - timedelta(days=365 * years + 60)).isoformat()
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


def _fetch_price_history(years: int = 5) -> dict[str, pd.Series]:
    """Return daily Close price series from yfinance for all assets."""
    # Extra 60 days so the last date in the feature window has full horizon data
    start = (date.today() - timedelta(days=365 * years + 60)).isoformat()
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
        [2] HY spread z-score      ((value − 5yr_mean) / _HY_STD)
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

    # --- Feature 2: HY z-score ---
    hy       = fred_series.get("hy_spread", pd.Series(dtype=float))
    hy_d     = hy.reindex(bdays, method="ffill")
    hy_mean  = hy_d.rolling(window=_HY_MEAN_WINDOW, min_periods=_MIN_FIT_DAYS).mean()
    f2       = ((hy_d - hy_mean) / _HY_STD).values

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
        if name not in _ASSETS:
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
                if j < len(arr):
                    day_ret[h] = round(float((arr[j] / arr[i] - 1) * 100), 4)
            if day_ret:
                forward_returns[name][d] = day_ret

    return forward_returns


def _build_snapshot_stubs(
    fred_series: dict[str, pd.Series],
    dates: pd.DatetimeIndex,
) -> list[tuple[date, dict]]:
    """
    Build minimal snapshot dicts for assign_bucket().

    Only three FRED fields are needed: nfci.value, treasury_10y.value,
    treasury_2y.value, hy_spread.value + five_yr_mean.
    """
    nfci_d  = fred_series.get("nfci", pd.Series(dtype=float)).reindex(
        dates, method="ffill"
    )
    t10_d   = fred_series.get("treasury_10y", pd.Series(dtype=float)).reindex(
        dates, method="ffill"
    )
    t2_d    = fred_series.get("treasury_2y", pd.Series(dtype=float)).reindex(
        dates, method="ffill"
    )
    hy_d    = fred_series.get("hy_spread", pd.Series(dtype=float)).reindex(
        dates, method="ffill"
    )
    hy_mean = hy_d.rolling(_HY_MEAN_WINDOW, min_periods=_MIN_FIT_DAYS).mean()

    snapshots: list[tuple[date, dict]] = []
    for ts in dates:
        snap: dict = {}
        nv = nfci_d[ts] if ts in nfci_d.index else np.nan
        if not np.isnan(nv):
            snap["nfci"] = {"value": float(nv)}

        t10v = t10_d[ts] if ts in t10_d.index else np.nan
        t2v  = t2_d[ts]  if ts in t2_d.index  else np.nan
        if not np.isnan(t10v) and not np.isnan(t2v):
            snap["treasury_10y"] = {"value": float(t10v)}
            snap["treasury_2y"]  = {"value": float(t2v)}

        hyv  = hy_d[ts]   if ts in hy_d.index   else np.nan
        hmv  = hy_mean[ts] if ts in hy_mean.index else np.nan
        if not np.isnan(hyv):
            snap["hy_spread"] = {
                "value":       float(hyv),
                "five_yr_mean": float(hmv) if not np.isnan(hmv) else float(hyv),
            }

        snapshots.append((ts.date(), snap))

    return snapshots


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

    _log("STEP", "3/4  Fitting regime model ...")
    feature_matrix, valid_dates = _build_feature_matrix(fred_series, sp500_close)

    if len(feature_matrix) < _MIN_FIT_DAYS:
        _log("ABORT", f"Only {len(feature_matrix)} valid days — need ≥{_MIN_FIT_DAYS}")
        sys.exit(1)

    model = fit_regime_model(feature_matrix, model_path=DEFAULT_MODEL_PATH)
    _log("REGIME", f"HMM fitted on {len(feature_matrix)} days → {DEFAULT_MODEL_PATH.name}")

    _log("STEP", "4/4  Building conditional distribution table ...")
    forward_returns = _build_forward_returns(prices, valid_dates)
    snapshot_stubs  = _build_snapshot_stubs(fred_series, valid_dates)

    n_returns = sum(len(v) for v in forward_returns.values())
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
