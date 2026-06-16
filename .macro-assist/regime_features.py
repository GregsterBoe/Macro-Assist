"""
regime_features.py — Extract 4-feature vectors from macro snapshots for HMM fitting.

Feature vector layout (shape 4,):
    [0] nfci_percentile      0-1, NFCI clipped to long-run historical range
    [1] yield_curve_slope    10Y − 2Y in basis points (raw, per spec)
    [2] credit_zscore        BAA10Y (value − 5yr_mean) / typical_std  ≈ z-score
    [3] realized_vol_pct     60d annualised SP500 vol percentile vs trailing 252d (0-100)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# NFCI historical range (1971-2025 approx; loose = -0.9, tight/crisis = 2.8)
_NFCI_MIN: float = -0.9
_NFCI_MAX: float =  2.8

# Approximate 5-year std of the credit-spread feature (percentage points).
# Regime feature [2] uses BAA10Y (Moody's Baa − 10Y) for long history — FRED
# serves the ICE BofA HY OAS with only ~3y, which truncated training (WP-17.1).
# Must match refit_models._BAA_STD (train/live feature transform consistency).
_BAA_STD: float = 0.5


def regime_features(
    snapshot: dict,
    sp500_returns: Optional[pd.Series] = None,
) -> np.ndarray:
    """
    Extract a 4-feature vector from a FRED+market snapshot.

    Parameters
    ----------
    snapshot       : output of fetch_fred_data() or historical_snapshot()
    sp500_returns  : pre-computed SP500 daily log-return series.
                     When None, the function fetches 400d of history from yfinance
                     using snapshot['snapshot_date'] if present.

    Returns
    -------
    np.ndarray shape (4,) — NaN for any unavailable feature.
    """
    features = np.full(4, np.nan)

    # ------------------------------------------------------------------
    # [0] NFCI percentile  (0–1, clipped to long-run historical range)
    # ------------------------------------------------------------------
    nfci_entry = snapshot.get("nfci", {})
    if "value" in nfci_entry:
        raw = float(nfci_entry["value"])
        features[0] = float(np.clip(
            (raw - _NFCI_MIN) / (_NFCI_MAX - _NFCI_MIN),
            0.0, 1.0,
        ))

    # ------------------------------------------------------------------
    # [1] Yield curve slope  (10Y − 2Y, raw basis points)
    # ------------------------------------------------------------------
    t10 = snapshot.get("treasury_10y", {}).get("value")
    t2  = snapshot.get("treasury_2y",  {}).get("value")
    if t10 is not None and t2 is not None:
        features[1] = (float(t10) - float(t2)) * 100        # % → bps
    elif "yield_curve_spread" in snapshot:
        features[1] = float(snapshot["yield_curve_spread"]) * 100

    # ------------------------------------------------------------------
    # [2] Credit-spread z-score  (BAA10Y deviation from 5yr mean / typical std)
    # ------------------------------------------------------------------
    credit = snapshot.get("baa_spread", {})
    if "value" in credit and "five_yr_mean" in credit:
        deviation  = float(credit["value"]) - float(credit["five_yr_mean"])
        features[2] = deviation / _BAA_STD
    elif "vs_mean" in credit:
        features[2] = float(credit["vs_mean"]) / _BAA_STD

    # ------------------------------------------------------------------
    # [3] 60d realized SP500 vol percentile  (0–100)
    # ------------------------------------------------------------------
    features[3] = _sp500_vol_percentile(snapshot, sp500_returns)

    return features


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sp500_vol_percentile(
    snapshot: dict,
    sp500_returns: Optional[pd.Series],
) -> float:
    """60d annualised SP500 vol percentile vs trailing 252d window (0-100)."""
    if sp500_returns is None:
        snap_date = snapshot.get("snapshot_date")
        if snap_date is None:
            return float("nan")
        try:
            import yfinance as yf
            end_dt   = date.fromisoformat(snap_date)
            start_dt = end_dt - timedelta(days=400)
            hist     = yf.download(
                "^GSPC",
                start=start_dt.isoformat(),
                end=(end_dt + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=True,
            )
            prices        = hist["Close"].squeeze().dropna()
            sp500_returns = pd.Series(
                np.log(prices.values[1:] / prices.values[:-1])
            )
        except Exception:
            return float("nan")

    if len(sp500_returns) < 60:
        return float("nan")

    rv     = pd.Series(sp500_returns.values ** 2)
    vol_60 = (rv.rolling(60).mean().dropna() ** 0.5) * np.sqrt(252) * 100

    if len(vol_60) < 2:
        return float("nan")

    current_vol  = float(vol_60.iloc[-1])
    trailing_252 = vol_60.tail(252)
    return float(np.mean(trailing_252 <= current_vol) * 100)
