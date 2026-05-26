"""
Tests for synthetic.py generators.
All tests are pure Python/numpy — no external API or network calls.

Run:
    pytest .macro-assist/tests/test_synthetic.py -v
"""
import numpy as np
import pytest

from synthetic import (
    synthetic_garch,
    synthetic_regime_switching,
    synthetic_conditional,
)


# ---------------------------------------------------------------------------
# synthetic_garch
# ---------------------------------------------------------------------------

def test_garch_output_shape():
    returns = synthetic_garch(n=500, omega=0.01, alpha=0.05, beta=0.90)
    assert returns.shape == (500,)


def test_garch_volatility_clustering():
    """Squared returns must show autocorrelation > 0.1 at lag 1 (ARCH effect)."""
    returns = synthetic_garch(n=3000, omega=0.01, alpha=0.15, beta=0.80, seed=42)
    sq      = returns ** 2
    ac      = float(np.corrcoef(sq[:-1], sq[1:])[0, 1])
    assert ac > 0.1, f"GARCH squared-return AC={ac:.4f}, expected > 0.1"


def test_garch_reproducible():
    r1 = synthetic_garch(100, 0.01, 0.1, 0.85, seed=7)
    r2 = synthetic_garch(100, 0.01, 0.1, 0.85, seed=7)
    np.testing.assert_array_equal(r1, r2)


def test_garch_nonstationary_raises():
    with pytest.raises(ValueError, match="non-stationary"):
        synthetic_garch(100, omega=0.01, alpha=0.6, beta=0.5)


def test_garch_mean_near_zero():
    """Long GARCH series should have mean near zero (zero-mean model)."""
    returns = synthetic_garch(n=10_000, omega=0.0001, alpha=0.1, beta=0.85, seed=0)
    assert abs(float(returns.mean())) < 0.01


# ---------------------------------------------------------------------------
# synthetic_regime_switching
# ---------------------------------------------------------------------------

def test_regime_switching_output_shapes():
    P = np.array([[0.95, 0.05], [0.10, 0.90]])
    returns, states = synthetic_regime_switching(
        n=500,
        transition_matrix=P,
        state_means=np.array([0.0, -0.001]),
        state_vols=np.array([0.01, 0.03]),
    )
    assert returns.shape == (500,)
    assert states.shape  == (500,)
    assert set(np.unique(states)) <= {0, 1}


def test_regime_switching_state_proportions():
    """
    Empirical state proportions must match the stationary distribution within 5pp.
    Stationary for P=[[0.95,0.05],[0.10,0.90]]: pi_0=0.667, pi_1=0.333.
    """
    P = np.array([[0.95, 0.05], [0.10, 0.90]])
    _, states = synthetic_regime_switching(
        n=10_000,
        transition_matrix=P,
        state_means=np.array([0.0, -0.001]),
        state_vols=np.array([0.01, 0.03]),
        seed=42,
    )
    # Stationary distribution: pi_0 = p10 / (p01 + p10)
    p01, p10   = 0.05, 0.10
    expected_0 = p10 / (p01 + p10)   # 0.6667
    expected_1 = p01 / (p01 + p10)   # 0.3333

    actual_0 = float(np.mean(states == 0))
    actual_1 = float(np.mean(states == 1))

    assert abs(actual_0 - expected_0) < 0.05, (
        f"State-0 proportion {actual_0:.3f} vs expected {expected_0:.3f} (±0.05)"
    )
    assert abs(actual_1 - expected_1) < 0.05, (
        f"State-1 proportion {actual_1:.3f} vs expected {expected_1:.3f} (±0.05)"
    )


def test_regime_switching_reproducible():
    P = np.array([[0.9, 0.1], [0.2, 0.8]])
    r1, s1 = synthetic_regime_switching(200, P, np.array([0, 0]), np.array([1, 2]), seed=99)
    r2, s2 = synthetic_regime_switching(200, P, np.array([0, 0]), np.array([1, 2]), seed=99)
    np.testing.assert_array_equal(r1, r2)
    np.testing.assert_array_equal(s1, s2)


# ---------------------------------------------------------------------------
# synthetic_conditional
# ---------------------------------------------------------------------------

def test_conditional_output_shape():
    df = synthetic_conditional(
        n=200,
        state_fn=lambda t: t % 2,
        forward_means={0: 0.01, 1: -0.01},
        forward_vols={0: 0.005, 1: 0.005},
    )
    assert len(df) == 200
    assert set(df.columns) >= {"date", "macro_state", "forward_5d_return"}


def test_conditional_respects_forward_means():
    """
    Per-state sample means must be within statistical tolerance of the
    specified forward_means (3 sigma rule; sigma = vol / sqrt(n_per_state)).
    """
    forward_means = {0:  0.020, 1: -0.020}
    forward_vols  = {0:  0.010, 1:  0.010}
    n             = 4000    # ~2000 per state with alternating fn

    df = synthetic_conditional(
        n=n,
        state_fn=lambda t: t % 2,
        forward_means=forward_means,
        forward_vols=forward_vols,
        seed=42,
    )

    for state, expected_mean in forward_means.items():
        subset      = df[df["macro_state"] == state]["forward_5d_return"]
        actual_mean = float(subset.mean())
        vol         = forward_vols[state]
        n_state     = len(subset)
        std_err     = vol / (n_state ** 0.5)
        tolerance   = 3 * std_err   # 99.7% confidence

        assert abs(actual_mean - expected_mean) < tolerance, (
            f"State {state}: mean {actual_mean:.5f} vs expected {expected_mean:.5f} "
            f"(tolerance ±{tolerance:.5f})"
        )


def test_conditional_reproducible():
    df1 = synthetic_conditional(100, lambda t: 0, {0: 0.01}, {0: 0.01}, seed=5)
    df2 = synthetic_conditional(100, lambda t: 0, {0: 0.01}, {0: 0.01}, seed=5)
    assert list(df1["forward_5d_return"]) == list(df2["forward_5d_return"])
