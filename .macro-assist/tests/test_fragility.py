"""
Tests for fragility.py (WP-16.A.1 — fragility / phase-transition monitor).

Pure unit tests only: no network calls. Uses synthetic.py generators.

Run:
    pytest .macro-assist/tests/test_fragility.py -v
"""
import numpy as np
import pandas as pd
import pytest

from synthetic import synthetic_garch
from fragility import (
    realized_variance_trend,
    correlation_tightening,
    absorption_ratio,
    vix_term_backwardation,
    level_acceleration,
    lag1_autocorrelation,
    fragility_index,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _returns_to_close(returns: np.ndarray, start: float = 100.0) -> pd.Series:
    """Convert a log-return array to a Close price Series."""
    idx = pd.date_range("2024-01-01", periods=len(returns) + 1, freq="B")
    prices = start * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    return pd.Series(prices, index=idx)


def _vol_explosion(n: int = 200, seed: int = 7) -> np.ndarray:
    """Stationary returns whose volatility ramps up sharply in the final third."""
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 0.008, n)
    ramp = np.ones(n)
    tail = n // 3
    ramp[-tail:] = np.linspace(1.0, 6.0, tail)   # 6x vol blow-out
    return base * ramp


# ---------------------------------------------------------------------------
# realized_variance_trend
# ---------------------------------------------------------------------------

def test_variance_trend_rising_on_vol_explosion():
    close = _returns_to_close(_vol_explosion())
    result = realized_variance_trend(close)
    assert result is not None
    assert result["norm_slope"] > 0
    assert result["score"] > 60, f"expected fragile score, got {result['score']:.1f}"


def test_variance_trend_neutral_on_stationary():
    rng = np.random.default_rng(3)
    close = _returns_to_close(rng.normal(0, 0.01, 300))
    result = realized_variance_trend(close)
    assert result is not None
    # A stationary series should not register as strongly rising.
    assert 30 < result["score"] < 70


def test_variance_trend_insufficient_history_returns_none():
    close = _returns_to_close(np.zeros(5))
    assert realized_variance_trend(close) is None


# ---------------------------------------------------------------------------
# correlation_tightening
# ---------------------------------------------------------------------------

def test_correlation_high_when_assets_move_together():
    rng = np.random.default_rng(1)
    common = rng.normal(0, 0.01, 200)
    histories = {
        f"a{i}": _returns_to_close(common + rng.normal(0, 0.001, 200))
        for i in range(4)
    }
    result = correlation_tightening(histories)
    assert result is not None
    assert result["mean_abs_corr"] > 0.8
    assert result["score"] > 70


def test_correlation_low_when_assets_independent():
    rng = np.random.default_rng(2)
    histories = {
        f"a{i}": _returns_to_close(rng.normal(0, 0.01, 200))
        for i in range(4)
    }
    result = correlation_tightening(histories)
    assert result is not None
    assert result["mean_abs_corr"] < 0.3


def test_correlation_needs_two_assets():
    histories = {"only": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200))}
    assert correlation_tightening(histories) is None


# ---------------------------------------------------------------------------
# absorption_ratio
# ---------------------------------------------------------------------------

def _coupled_histories(n: int, rho_common: float, seed: int) -> dict:
    """Five assets, each a blend of a common factor and idiosyncratic noise.
    `rho_common` in [0,1] scales how much of each asset is the shared factor —
    higher => a more unified (tightly-coupled, high-absorption) market.
    """
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.01, n)
    histories = {}
    for i in range(5):
        idio = rng.normal(0, 0.01, n)
        rets = rho_common * common + (1 - rho_common) * idio
        histories[f"a{i}"] = _returns_to_close(rets)
    return histories


def test_absorption_needs_three_assets():
    histories = {
        "a": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200)),
        "b": _returns_to_close(np.random.default_rng(1).normal(0, 0.01, 200)),
    }
    assert absorption_ratio(histories) is None


def test_absorption_shift_rises_when_coupling_tightens():
    # First half loosely coupled, second half tightly coupled: AR_short should
    # sit above the baseline, so the standardized shift is positive.
    n = 260
    rng = np.random.default_rng(5)
    common = rng.normal(0, 0.01, n)
    histories = {}
    for i in range(5):
        idio = rng.normal(0, 0.01, n)
        rho = np.concatenate([np.full(n // 2, 0.1), np.full(n - n // 2, 0.9)])
        rets = rho * common + (1 - rho) * idio
        histories[f"a{i}"] = _returns_to_close(rets)
    result = absorption_ratio(histories)
    assert result is not None
    assert result["shift_z"] > 0
    assert result["score"] > 50
    assert 0.0 <= result["ar"] <= 1.0


def test_absorption_score_in_range():
    result = absorption_ratio(_coupled_histories(220, rho_common=0.5, seed=3))
    assert result is not None
    assert 0.0 <= result["score"] <= 100.0
    assert result["n_eig"] >= 1


# ---------------------------------------------------------------------------
# vix_term_backwardation
# ---------------------------------------------------------------------------

def test_vix_backwardation_full_persistence():
    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    vix = pd.Series(np.full(30, 30.0), index=idx)
    vix3m = pd.Series(np.full(30, 25.0), index=idx)   # ratio 1.2 > 1 every day
    result = vix_term_backwardation(vix, vix3m)
    assert result is not None
    assert result["persistence"] == 1.0
    assert result["score"] == 100.0


def test_vix_contango_zero_persistence():
    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    vix = pd.Series(np.full(30, 15.0), index=idx)
    vix3m = pd.Series(np.full(30, 18.0), index=idx)   # ratio < 1 (calm)
    result = vix_term_backwardation(vix, vix3m)
    assert result is not None
    assert result["score"] == 0.0


def test_vix_term_missing_returns_none():
    assert vix_term_backwardation(None, None) is None


# ---------------------------------------------------------------------------
# level_acceleration
# ---------------------------------------------------------------------------

def test_acceleration_positive_when_level_accelerates():
    # Quadratic ramp => positive, growing first differences => positive 2nd diff.
    series = pd.Series([float(t ** 2) * 0.01 for t in range(20)])
    result = level_acceleration(series)
    assert result is not None
    assert result["accel_z"] > 0
    assert result["score"] > 50


def test_acceleration_flat_series_returns_none():
    # Constant series => zero first-difference std => undefined => None.
    assert level_acceleration(pd.Series(np.ones(20))) is None


# ---------------------------------------------------------------------------
# lag1_autocorrelation
# ---------------------------------------------------------------------------

def test_autocorr_score_in_range():
    rng = np.random.default_rng(9)
    close = _returns_to_close(rng.normal(0, 0.01, 200))
    result = lag1_autocorrelation(close)
    assert result is not None
    assert 0.0 <= result["score"] <= 100.0


# ---------------------------------------------------------------------------
# fragility_index (composite)
# ---------------------------------------------------------------------------

def _make_histories(n: int = 250, seed: int = 0, explode: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    histories = {}
    for i, name in enumerate(["sp500", "nasdaq", "gold", "wti_oil"]):
        rets = _vol_explosion(n, seed=seed + i) if explode else rng.normal(0, 0.01, n)
        histories[name] = _returns_to_close(rets)
    return histories


def test_index_output_keys_and_ranges():
    result = fragility_index(_make_histories())
    assert result is not None
    assert set(result.keys()) == {"composite", "label", "trend", "components", "weights"}
    assert 0.0 <= result["composite"] <= 100.0
    assert result["label"] in {"Resilient", "Normal", "Elevated"}
    assert result["trend"] in {"Rising", "Stable", "Falling"}
    # Renormalised weights over available components sum to ~1.
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9


def test_index_rising_under_vol_explosion():
    calm = fragility_index(_make_histories(explode=False, seed=10))
    stressed = fragility_index(_make_histories(explode=True, seed=10))
    assert calm is not None and stressed is not None
    assert stressed["composite"] > calm["composite"]
    assert stressed["trend"] == "Rising"


def test_index_none_when_no_components():
    assert fragility_index({}) is None


def test_index_weights_renormalise_when_components_missing():
    # Only one asset => no correlation, no vix term, no acceleration.
    histories = {"sp500": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200))}
    result = fragility_index(histories)
    assert result is not None
    assert "correlation" not in result["components"]
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9


def test_index_deterministic():
    h = _make_histories(seed=42)
    assert fragility_index(h)["composite"] == fragility_index(h)["composite"]
