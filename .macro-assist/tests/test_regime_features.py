"""
Tests for regime_features.py.

Pure unit tests: all use synthetic snapshots / synthetic SP500 returns.
Integration tests: marked @pytest.mark.integration (require FRED_API_KEY + network).

Run unit tests only:
    pytest .macro-assist/tests/test_regime_features.py -v -m "not integration"
"""
import numpy as np
import pandas as pd
import pytest

from regime_features import regime_features, _NFCI_MIN, _NFCI_MAX, _HY_STD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    nfci_val: float = 0.0,
    t10: float = 4.5,
    t2: float = 4.0,
    hy_val: float = 4.5,
    hy_mean: float = 4.5,
    snap_date: str = "2024-06-01",
) -> dict:
    return {
        "nfci":         {"value": nfci_val, "five_yr_mean": 0.1, "vs_mean": nfci_val - 0.1},
        "treasury_10y": {"value": t10},
        "treasury_2y":  {"value": t2},
        "hy_spread":    {"value": hy_val, "five_yr_mean": hy_mean, "vs_mean": hy_val - hy_mean},
        "snapshot_date": snap_date,
    }


def _make_sp500_returns(n: int = 300, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.0003, 0.01, n))


# ---------------------------------------------------------------------------
# Pure unit tests
# ---------------------------------------------------------------------------

def test_feature_shape():
    snap = _make_snapshot()
    rets = _make_sp500_returns()
    feat = regime_features(snap, sp500_returns=rets)
    assert feat.shape == (4,)
    assert feat.dtype == float


def test_yield_curve_in_bps():
    snap = _make_snapshot(t10=4.5, t2=2.5)
    rets = _make_sp500_returns()
    feat = regime_features(snap, sp500_returns=rets)
    assert abs(feat[1] - 200.0) < 1e-9, f"Expected 200 bps, got {feat[1]}"


def test_yield_curve_inverted_negative():
    snap = _make_snapshot(t10=4.0, t2=5.0)
    rets = _make_sp500_returns()
    feat = regime_features(snap, sp500_returns=rets)
    assert feat[1] < 0.0, "Inverted yield curve should give negative slope feature"


def test_nfci_at_min_gives_zero():
    snap = _make_snapshot(nfci_val=_NFCI_MIN)
    rets = _make_sp500_returns()
    feat = regime_features(snap, sp500_returns=rets)
    assert abs(feat[0]) < 1e-9, f"NFCI at historical min should give 0, got {feat[0]}"


def test_nfci_at_max_gives_one():
    snap = _make_snapshot(nfci_val=_NFCI_MAX)
    rets = _make_sp500_returns()
    feat = regime_features(snap, sp500_returns=rets)
    assert abs(feat[0] - 1.0) < 1e-9, f"NFCI at historical max should give 1, got {feat[0]}"


def test_nfci_clipped_below():
    snap = _make_snapshot(nfci_val=_NFCI_MIN - 1.0)
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert feat[0] == 0.0, "NFCI below historical min should clip to 0"


def test_nfci_clipped_above():
    snap = _make_snapshot(nfci_val=_NFCI_MAX + 1.0)
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert feat[0] == 1.0, "NFCI above historical max should clip to 1"


def test_hy_zscore_at_mean_is_zero():
    snap = _make_snapshot(hy_val=4.5, hy_mean=4.5)
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert abs(feat[2]) < 1e-9, f"HY spread at 5yr mean should give z-score 0, got {feat[2]}"


def test_hy_zscore_above_mean_positive():
    snap = _make_snapshot(hy_val=6.0, hy_mean=4.5)
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert feat[2] > 0.0, "HY spread above mean should give positive z-score"


def test_hy_zscore_correct_value():
    snap = _make_snapshot(hy_val=6.0, hy_mean=4.5)
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    expected = (6.0 - 4.5) / _HY_STD
    assert abs(feat[2] - expected) < 1e-9


def test_realized_vol_pct_in_range():
    snap = _make_snapshot()
    rets = _make_sp500_returns(n=300)
    feat = regime_features(snap, sp500_returns=rets)
    assert 0.0 <= feat[3] <= 100.0, f"Realized vol pct = {feat[3]}, expected [0, 100]"


def test_realized_vol_pct_nan_on_too_short_series():
    snap = _make_snapshot()
    rets = _make_sp500_returns(n=30)   # too short for 60d rolling
    feat = regime_features(snap, sp500_returns=rets)
    assert np.isnan(feat[3]), "Should be NaN when returns series is too short"


def test_missing_nfci_gives_nan():
    snap = {}   # no keys at all
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert np.isnan(feat[0])


def test_missing_yields_gives_nan():
    snap = {}
    feat = regime_features(snap, sp500_returns=_make_sp500_returns())
    assert np.isnan(feat[1])


def test_feature_distributions_synthetic():
    """
    Feature distributions over 1000 synthetic snapshots should be in expected ranges.
    Validates normalization without API calls.
    """
    rng = np.random.default_rng(7)
    n   = 1000

    nfci_vals = rng.normal(0.1, 0.5, n)          # realistic NFCI range
    t10_vals  = rng.normal(3.5, 1.2, n)           # 10Y yield
    t2_vals   = rng.normal(3.0, 1.2, n)           # 2Y yield
    hy_vals   = rng.normal(4.5, 1.5, n)           # HY spread
    hy_mean   = 4.5                                # fixed 5yr mean

    # 20 different SP500 return series so vol_pct varies across snapshots
    sp500_batch = [_make_sp500_returns(n=300, seed=s) for s in range(20)]

    features = np.empty((n, 4))
    for i in range(n):
        snap = _make_snapshot(
            nfci_val=nfci_vals[i],
            t10=t10_vals[i],
            t2=t2_vals[i],
            hy_val=hy_vals[i],
            hy_mean=hy_mean,
        )
        features[i] = regime_features(snap, sp500_returns=sp500_batch[i % 20])

    # Per-feature reasonable mean bounds (vary by scale)
    mean_bounds = {
        "nfci_pct":  (-0.1,  1.1),    # normalized [0, 1]
        "yc_bps":    (-300.0, 300.0), # raw basis points
        "hy_zscore": (-4.0,   4.0),   # z-score
        "vol_pct":   (  0.0, 100.0),  # percentile [0, 100]
    }

    for col_idx, name in enumerate(["nfci_pct", "yc_bps", "hy_zscore", "vol_pct"]):
        col = features[:, col_idx]
        col = col[~np.isnan(col)]
        mean = float(col.mean())
        std  = float(col.std())
        lo, hi = mean_bounds[name]
        assert lo <= mean <= hi, f"Feature {name}: mean {mean:.3f} outside [{lo}, {hi}]"
        assert std >= 0.01, f"Feature {name}: std {std:.3f} near zero"
