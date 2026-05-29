"""
Tests for regime.py (HMM fitting, inference, labelling, anti-flicker).

Pure unit tests: no network calls; some require hmmlearn.
Integration tests: marked @pytest.mark.integration (require yfinance + API keys).

Run unit tests only:
    pytest .macro-assist/tests/test_regime.py -v -m "not integration"
"""
import numpy as np
import pandas as pd
import pytest

from synthetic import synthetic_regime_switching
from regime import (
    fit_regime_model,
    predict_regime,
    label_states,
    stable_regime_label,
)
from regime_features import regime_features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_4d_regime_data(
    n: int = 2000,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a 4-state, 4-feature synthetic dataset.

    States (indexed 0-3):
        0: Risk-On  Low-Vol  — low NFCI, positive YC, tight spread, low vol
        1: Risk-On  High-Vol — low NFCI, positive YC, slightly wide spread, mod vol
        2: Risk-Off Low-Vol  — high NFCI, flat YC, wide spread, moderate vol
        3: Risk-Off High-Vol — high NFCI, inverted YC, very wide spread, high vol

    Feature order matches regime_features: [nfci_pct, yc_bps, hy_z, vol_pct]
    """
    P = np.array([
        [0.92, 0.05, 0.02, 0.01],
        [0.06, 0.88, 0.04, 0.02],
        [0.03, 0.04, 0.88, 0.05],
        [0.01, 0.02, 0.07, 0.90],
    ])
    state_means = np.array([
        [0.10,  150.0, -0.8, 20.0],   # Risk-On  Low-Vol
        [0.20,  100.0, -0.2, 55.0],   # Risk-On  High-Vol
        [0.70,   20.0,  0.8, 40.0],   # Risk-Off Low-Vol
        [0.85, -150.0,  2.5, 80.0],   # Risk-Off High-Vol
    ])
    state_stds = np.array([
        [0.05, 30.0, 0.3, 8.0],
        [0.05, 30.0, 0.3, 12.0],
        [0.05, 40.0, 0.4, 10.0],
        [0.05, 40.0, 0.5, 15.0],
    ])

    rng = np.random.default_rng(seed)

    # Stationary distribution
    vals, vecs = np.linalg.eig(P.T)
    stationary = np.real(vecs[:, np.isclose(vals, 1.0)].flatten())
    stationary = np.abs(stationary) / np.abs(stationary).sum()

    state = int(rng.choice(4, p=stationary))
    X      = np.empty((n, 4))
    states = np.empty(n, dtype=int)

    for t in range(n):
        states[t] = state
        X[t] = rng.normal(state_means[state], state_stds[state])
        state = int(rng.choice(4, p=P[state]))

    return X, states


# ---------------------------------------------------------------------------
# label_states — pure unit tests (only need a mock model)
# ---------------------------------------------------------------------------

class _MockHMM:
    """Minimal GaussianHMM-like object for label_states tests."""
    def __init__(self, means):
        self.means_      = np.asarray(means, dtype=float)
        self.n_components = len(means)


def test_label_states_four_distinct_labels():
    model = _MockHMM([
        [0.10,  150.0, -0.8, 20.0],
        [0.20,  100.0, -0.2, 55.0],
        [0.70,   20.0,  0.8, 40.0],
        [0.85, -150.0,  2.5, 80.0],
    ])
    labels = label_states(model)
    assert len(set(labels.values())) == 4, "Expected 4 distinct state labels"
    expected = {"Risk-On Low-Vol", "Risk-On High-Vol", "Risk-Off Low-Vol", "Risk-Off High-Vol"}
    assert set(labels.values()) == expected


def test_label_states_risk_off_has_high_nfci():
    model = _MockHMM([
        [0.10,  150.0, -0.8, 20.0],
        [0.20,  100.0, -0.2, 55.0],
        [0.70,   20.0,  0.8, 40.0],
        [0.85, -150.0,  2.5, 80.0],
    ])
    labels = label_states(model)
    # States 2 and 3 (high NFCI means) should be Risk-Off
    assert "Risk-Off" in labels[2]
    assert "Risk-Off" in labels[3]


def test_label_states_non_four_returns_generic():
    model = _MockHMM([[0.1, 0.2], [0.8, 0.9], [0.5, 0.5]])
    labels = label_states(model)
    for i in range(3):
        assert labels[i] == f"State {i}"


# ---------------------------------------------------------------------------
# stable_regime_label — pure unit tests
# ---------------------------------------------------------------------------

def test_stable_regime_empty_history():
    assert stable_regime_label([]) == -1


def test_stable_regime_too_short_for_dwell():
    # 2 observations, min_dwell=3 → no stable label
    posteriors = [np.array([0.9, 0.1]), np.array([0.85, 0.15])]
    assert stable_regime_label(posteriors, min_posterior=0.7, min_dwell=3) == -1


def test_stable_regime_transitions_after_dwell():
    # State 0 dominant for 4 days with high confidence → stable = 0
    p0 = np.array([0.9, 0.1])
    p1 = np.array([0.1, 0.9])
    posteriors = [p0] * 4
    assert stable_regime_label(posteriors, min_posterior=0.7, min_dwell=3) == 0


def test_stable_regime_ignores_brief_spike():
    # State 0 for 4 days, then state 1 for 2 days → still state 0 (dwell not met)
    p0 = np.array([0.9, 0.1])
    p1 = np.array([0.1, 0.9])
    posteriors = [p0] * 4 + [p1] * 2
    assert stable_regime_label(posteriors, min_posterior=0.7, min_dwell=3) == 0


def test_stable_regime_switches_after_sufficient_dwell():
    # State 0 for 4 days, then state 1 for 3 days → switches to state 1
    p0 = np.array([0.9, 0.1])
    p1 = np.array([0.1, 0.9])
    posteriors = [p0] * 4 + [p1] * 3
    assert stable_regime_label(posteriors, min_posterior=0.7, min_dwell=3) == 1


def test_stable_regime_requires_min_posterior():
    # State 0 for 5 days but posterior only 0.6 (< min 0.7) → no stable label
    p_low = np.array([0.6, 0.4])
    posteriors = [p_low] * 5
    assert stable_regime_label(posteriors, min_posterior=0.7, min_dwell=3) == -1


def test_stable_regime_switch_count_low():
    """
    A brief 2-day noise spike (< min_dwell=3) should be filtered out.
    Only the genuine persistent regime change (100 days) should be counted.
    """
    p0 = np.array([0.9, 0.05, 0.05])
    p1 = np.array([0.05, 0.9, 0.05])   # noise spike for only 2 days
    p2 = np.array([0.05, 0.05, 0.9])

    # 100 days state 0 → 2-day spike to state 1 → 100 days state 0 → 100 days state 2
    posteriors_hist = [p0] * 100 + [p1] * 2 + [p0] * 100 + [p2] * 100

    stable_seq = []
    for t in range(1, len(posteriors_hist) + 1):
        stable_seq.append(stable_regime_label(posteriors_hist[:t]))

    # Count transitions, excluding the initial -1 → first_state establishment
    switches = sum(
        1 for i in range(1, len(stable_seq))
        if stable_seq[i] != stable_seq[i - 1]
        and stable_seq[i] != -1
        and stable_seq[i - 1] != -1
    )
    # Only 1 genuine switch: 0 → 2  (the 2-day spike to state 1 is filtered)
    assert switches == 1, (
        f"Expected 1 switch (2-day noise spike filtered), got {switches}"
    )


# ---------------------------------------------------------------------------
# HMM fitting + predict_regime — pure (require hmmlearn, no network)
# ---------------------------------------------------------------------------

def test_fit_regime_model_returns_fitted_hmm():
    X, _ = _generate_4d_regime_data(n=500, seed=0)
    model = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    assert hasattr(model, "transmat_")
    assert model.transmat_.shape == (4, 4)
    # Rows must sum to 1
    np.testing.assert_allclose(model.transmat_.sum(axis=1), 1.0, atol=1e-9)


def test_fit_1d_data_auto_reshape():
    """fit_regime_model should accept 1D arrays (reshapes internally)."""
    returns, _ = synthetic_regime_switching(
        400, np.array([[0.9, 0.1], [0.1, 0.9]]),
        np.array([0.005, -0.005]), np.array([0.01, 0.02]), seed=0,
    )
    model = fit_regime_model(returns, n_states=2, random_state=42, model_path=None)
    assert model.n_components == 2


def test_predict_regime_output_keys():
    X, _ = _generate_4d_regime_data(n=500, seed=1)
    model = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    result = predict_regime(model, X[-1])
    assert {"state", "state_label", "posterior", "transition_probs_from_current"} <= set(result)
    assert len(result["posterior"]) == 4
    assert abs(sum(result["posterior"]) - 1.0) < 1e-6


def test_predict_regime_state_in_range():
    X, _ = _generate_4d_regime_data(n=300, seed=2)
    model = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    result = predict_regime(model, X[-10:])
    assert 0 <= result["state"] < 4


def test_recover_synthetic_regimes():
    """
    GaussianHMM fitted on 4-state synthetic data should recover 4 persistent
    states: all diagonal entries of the fitted transition matrix > 0.70.
    """
    X, _ = _generate_4d_regime_data(n=2000, seed=42)
    model = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    diag  = np.diag(model.transmat_)
    assert np.all(diag > 0.70), (
        f"All diagonal transition probs should be > 0.70; got {np.round(diag, 3)}"
    )


# ---------------------------------------------------------------------------
# Integration tests — require yfinance + API keys
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_historical_alignment():
    """
    A GaussianHMM fitted on 2019-2025 SP500 + macro features should classify
    March–May 2020 predominantly as 'Risk-Off High-Vol'.
    """
    import yfinance as yf

    # Fetch ~6 years of SP500 data for feature computation
    sp500   = yf.download("^GSPC", start="2019-01-01", end="2025-12-31",
                           progress=False, auto_adjust=True)
    prices  = sp500["Close"].squeeze().dropna()
    returns = pd.Series(np.log(prices.values[1:] / prices.values[:-1]),
                        index=prices.index[1:])

    # Build simplified feature matrix from SP500 data only (no FRED needed here):
    # Use HAR-RV style rolling vols as a stand-in for the full feature vector.
    # Feature [3] (realized_vol_pct) drives the labelling test.
    rv     = pd.Series(returns.values ** 2, index=returns.index)
    vol_60 = (rv.rolling(60).mean() ** 0.5 * np.sqrt(252) * 100).dropna()

    # For a minimal 4-feature proxy use vol at multiple horizons + lagged vol
    vol_22  = (rv.rolling(22).mean() ** 0.5 * np.sqrt(252) * 100).reindex(vol_60.index)
    vol_5   = (rv.rolling(5).mean()  ** 0.5 * np.sqrt(252) * 100).reindex(vol_60.index)
    ret_22  = returns.rolling(22).mean().reindex(vol_60.index) * 100

    X = np.column_stack([
        ret_22.fillna(0).values,
        vol_5.fillna(vol_5.mean()).values,
        vol_22.fillna(vol_22.mean()).values,
        vol_60.values,
    ])

    model  = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    labels = label_states(model)

    # Predict states for full history
    states = model.predict(X)
    state_labels_series = pd.Series(
        [labels.get(s, f"State {s}") for s in states],
        index=vol_60.index,
    )

    crisis_mask = (state_labels_series.index >= "2020-03-01") & \
                  (state_labels_series.index <= "2020-05-31")
    crisis_labels = state_labels_series[crisis_mask]

    if len(crisis_labels) == 0:
        pytest.skip("No data in 2020-03 to 2020-05 window")

    pct_risk_off_hv = float(
        (crisis_labels == "Risk-Off High-Vol").sum() / len(crisis_labels)
    )
    assert pct_risk_off_hv >= 0.5, (
        f"March-May 2020: only {pct_risk_off_hv:.0%} 'Risk-Off High-Vol', expected ≥ 50%"
    )


@pytest.mark.integration
def test_regime_persistence():
    """
    Median dwell time on 2020-2025 SP500 vol features should be 10-60 trading days.
    """
    import yfinance as yf

    sp500   = yf.download("^GSPC", start="2019-01-01", end="2025-12-31",
                           progress=False, auto_adjust=True)
    prices  = sp500["Close"].squeeze().dropna()
    returns = pd.Series(np.log(prices.values[1:] / prices.values[:-1]))

    rv    = pd.Series(returns.values ** 2)
    vol60 = (rv.rolling(60).mean() ** 0.5 * np.sqrt(252) * 100).dropna()
    vol22 = (rv.rolling(22).mean() ** 0.5 * np.sqrt(252) * 100).reindex(vol60.index)
    vol5  = (rv.rolling(5).mean()  ** 0.5 * np.sqrt(252) * 100).reindex(vol60.index)
    ret22 = returns.rolling(22).mean().reindex(vol60.index) * 100
    X     = np.column_stack([ret22.fillna(0), vol5.fillna(vol5.mean()),
                             vol22.fillna(vol22.mean()), vol60])

    model  = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    states = model.predict(X)

    # Compute dwell times
    dwells = []
    if len(states) > 0:
        run_len = 1
        for i in range(1, len(states)):
            if states[i] == states[i - 1]:
                run_len += 1
            else:
                dwells.append(run_len)
                run_len = 1
        dwells.append(run_len)

    median_dwell = float(np.median(dwells)) if dwells else 0.0
    assert 10 <= median_dwell <= 60, (
        f"Median dwell time = {median_dwell:.1f} trading days, expected [10, 60]"
    )


@pytest.mark.integration
def test_switch_count_reasonable():
    """
    Anti-flicker applied over 2020-2025 should produce 4–12 total regime switches.
    """
    import yfinance as yf

    sp500   = yf.download("^GSPC", start="2019-01-01", end="2025-12-31",
                           progress=False, auto_adjust=True)
    prices  = sp500["Close"].squeeze().dropna()
    returns = pd.Series(np.log(prices.values[1:] / prices.values[:-1]))

    rv    = pd.Series(returns.values ** 2)
    vol60 = (rv.rolling(60).mean() ** 0.5 * np.sqrt(252) * 100).dropna()
    vol22 = (rv.rolling(22).mean() ** 0.5 * np.sqrt(252) * 100).reindex(vol60.index)
    vol5  = (rv.rolling(5).mean()  ** 0.5 * np.sqrt(252) * 100).reindex(vol60.index)
    ret22 = returns.rolling(22).mean().reindex(vol60.index) * 100
    X     = np.column_stack([ret22.fillna(0), vol5.fillna(vol5.mean()),
                             vol22.fillna(vol22.mean()), vol60])

    model      = fit_regime_model(X, n_states=4, random_state=42, model_path=None)
    posteriors = [np.array(p) for p in model.predict_proba(X)]

    stable_seq = []
    for t in range(1, len(posteriors) + 1):
        stable_seq.append(stable_regime_label(posteriors[:t]))

    # Count transitions (ignore -1 periods)
    valid  = [(i, s) for i, s in enumerate(stable_seq) if s != -1]
    switches = sum(
        1 for i in range(1, len(valid))
        if valid[i][1] != valid[i - 1][1]
    )
    assert 4 <= switches <= 12, (
        f"Anti-flicker produced {switches} regime switches, expected [4, 12]"
    )
