"""
regime.py — HMM-based macro regime classification.

Functions
---------
fit_regime_model   : Fit GaussianHMM, optionally persist to .pkl
predict_regime     : Predict current state + posterior + transition probs
label_states       : Map state indices to human-readable 2×2 regime labels
stable_regime_label: Anti-flicker layer — only relabels after min_dwell confident days
"""
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

DATA_DIR           = _HERE / "data"
DEFAULT_MODEL_PATH = DATA_DIR / "regime_model.pkl"


# ---------------------------------------------------------------------------
# Retirement switch  (grep: REGIME-RETIRED)
# ---------------------------------------------------------------------------
# The HMM regime layer was found REDUNDANT (WP-17.4 / KB-006): a 4-feature
# stress rule beats it on drawdown AUC and adds nothing within stress strata,
# and its macro-stress dimension is already covered by the Phase-16 fragility
# monitor. The code is intentionally kept (we may revive it later), but it is
# RETIRED — it must not run in production. Every consumer (the portfolio-book
# regime gate, the weekly model refit, and the payload-preview block) checks
# `regime_enabled()` and degrades gracefully when it is off.
#
# Default OFF. To re-enable every consumer at once — for an experiment or a
# revival — set the env var:  REGIME_ENABLED=1
_REGIME_ENABLED_OFF_VALUES = {"", "0", "false", "no", "off"}


def regime_enabled() -> bool:
    """Whether the retired HMM regime layer is active. Default False (KB-006)."""
    return os.environ.get("REGIME_ENABLED", "0").strip().lower() not in _REGIME_ENABLED_OFF_VALUES

# Feature-vector column indices (matching regime_features.py)
_NFCI_IDX = 0
_YC_IDX   = 1
_HY_IDX   = 2
_VOL_IDX  = 3


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def fit_regime_model(
    historical_features: np.ndarray,
    n_states: int = 4,
    random_state: int = 42,
    model_path: Optional[Path] = DEFAULT_MODEL_PATH,
):
    """
    Fit a GaussianHMM (full covariance) on historical feature matrix.

    Parameters
    ----------
    historical_features : shape (n_days, n_features)
    n_states            : number of hidden states (default 4)
    random_state        : random seed for reproducibility
    model_path          : if not None, pickle the fitted model here

    Returns
    -------
    Fitted hmmlearn.hmm.GaussianHMM
    """
    from hmmlearn.hmm import GaussianHMM

    X = np.asarray(historical_features, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)

    model = GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=200,
        random_state=random_state,
        tol=1e-4,
    )
    model.fit(X)

    if model_path is not None:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(model_path, "wb") as fh:
            pickle.dump(model, fh)

    return model


def load_regime_model(model_path: Path = DEFAULT_MODEL_PATH):
    """Load a previously persisted model from disk."""
    with open(model_path, "rb") as fh:
        return pickle.load(fh)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def predict_regime(model, current_features: np.ndarray) -> dict:
    """
    Predict the current macro regime from a feature vector.

    Parameters
    ----------
    model            : fitted GaussianHMM (from fit_regime_model)
    current_features : shape (n_features,) or (n_obs, n_features)

    Returns
    -------
    dict
        state                        : int — most likely state index
        state_label                  : str — human-readable label
        posterior                    : list[float] — length n_states
        transition_probs_from_current: dict[int, float]
    """
    X = np.atleast_2d(current_features).astype(float)

    state_seq  = model.predict(X)
    state      = int(state_seq[-1])
    posteriors = model.predict_proba(X)[-1]

    trans_probs = {
        i: float(model.transmat_[state, i])
        for i in range(model.n_components)
    }

    labels = label_states(model)

    return {
        "state":                        state,
        "state_label":                  labels.get(state, f"State {state}"),
        "posterior":                    [float(p) for p in posteriors],
        "transition_probs_from_current": trans_probs,
    }


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------

def label_states(model) -> dict[int, str]:
    """
    Assign 'Risk-On / Risk-Off × Low-Vol / High-Vol' labels to 4 HMM states.

    Split criterion
    ---------------
    Risk axis  : NFCI percentile (feature [0]) — low = Risk-On
    Vol axis   : realized_vol_pct (feature [3]) — low = Low-Vol

    For n_states != 4 (or fewer than 2 features), returns generic "State N" labels.
    """
    means = model.means_           # shape (n_states, n_features)
    n     = model.n_components

    if n != 4 or means.shape[1] < max(_NFCI_IDX, _VOL_IDX) + 1:
        return {i: f"State {i}" for i in range(n)}

    nfci_vals = means[:, _NFCI_IDX]
    vol_vals  = means[:, _VOL_IDX]

    # Split each axis at its median across states
    nfci_med = float(np.median(nfci_vals))
    vol_med  = float(np.median(vol_vals))

    labels: dict[int, str] = {}
    for i in range(n):
        risk_str = "Risk-Off" if nfci_vals[i] >= nfci_med else "Risk-On"
        vol_str  = "High-Vol" if vol_vals[i]  >= vol_med  else "Low-Vol"
        labels[i] = f"{risk_str} {vol_str}"

    return labels


# ---------------------------------------------------------------------------
# Anti-flicker layer
# ---------------------------------------------------------------------------

def stable_regime_label(
    posteriors_history: list,
    min_posterior: float = 0.7,
    min_dwell: int = 3,
) -> int:
    """
    Return the current stable regime, suppressing day-to-day label flipping.

    Scans posteriors_history forward.  The stable label updates only when:
      (a) the top-posterior state has been the top state for >= min_dwell
          consecutive periods, AND
      (b) its posterior exceeds min_posterior in the most recent of those periods.

    Returns the most-recently-confirmed stable state, or -1 if none found.

    Parameters
    ----------
    posteriors_history : list of 1-D arrays, each of length n_states
    min_posterior      : confidence threshold (default 0.7)
    min_dwell          : consecutive-periods requirement (default 3)
    """
    if not posteriors_history:
        return -1

    top_states = [int(np.argmax(p)) for p in posteriors_history]
    top_posts  = [float(np.max(p))  for p in posteriors_history]

    stable     = -1
    run_state  = -1
    run_length = 0

    for t, (s, post) in enumerate(zip(top_states, top_posts)):
        if s == run_state:
            run_length += 1
        else:
            run_state  = s
            run_length = 1

        if run_length >= min_dwell and post >= min_posterior:
            stable = s

    return stable
