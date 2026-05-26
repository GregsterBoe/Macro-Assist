"""
synthetic.py — Synthetic financial time-series generators for backtesting.

Three generators, each seeded for reproducibility:

  synthetic_garch(n, omega, alpha, beta, seed)
      GARCH(1,1) return series with known parameters.

  synthetic_regime_switching(n, transition_matrix, state_means, state_vols, seed)
      Markov regime-switching return series + true state labels.

  synthetic_conditional(n, state_fn, forward_means, forward_vols, seed)
      DataFrame mapping macro state to forward 5-day returns.

All functions use numpy.random.default_rng (seeded) for reproducibility.
No external dependencies beyond numpy and pandas.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def synthetic_garch(
    n: int,
    omega: float,
    alpha: float,
    beta: float,
    seed: int = 42,
) -> np.ndarray:
    """
    Simulate n returns from a GARCH(1,1) process:
      r_t   = sigma_t * z_t,   z_t ~ N(0,1)
      h_t   = omega + alpha * r_{t-1}^2 + beta * h_{t-1}

    Initialised at the unconditional variance omega / (1 - alpha - beta).
    Raises ValueError if alpha + beta >= 1 (non-stationary).
    """
    if alpha + beta >= 1.0:
        raise ValueError(
            f"GARCH(1,1) is non-stationary: alpha ({alpha}) + beta ({beta}) >= 1"
        )

    rng     = np.random.default_rng(seed)
    returns = np.empty(n)
    h       = omega / (1.0 - alpha - beta)   # unconditional variance

    for t in range(n):
        z          = rng.standard_normal()
        returns[t] = np.sqrt(h) * z
        h          = omega + alpha * returns[t] ** 2 + beta * h

    return returns


def synthetic_regime_switching(
    n: int,
    transition_matrix: np.ndarray,
    state_means: np.ndarray,
    state_vols: np.ndarray,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simulate n returns from a Markov regime-switching model.

    Parameters
    ----------
    transition_matrix : shape (k, k), rows must sum to 1
    state_means       : shape (k,) — mean return per regime
    state_vols        : shape (k,) — volatility per regime

    Returns
    -------
    returns : np.ndarray of length n
    states  : np.ndarray of int labels (0..k-1) of length n
    """
    transition_matrix = np.asarray(transition_matrix, dtype=float)
    state_means       = np.asarray(state_means, dtype=float)
    state_vols        = np.asarray(state_vols, dtype=float)
    k                 = len(state_means)

    rng = np.random.default_rng(seed)

    # Stationary distribution: left eigenvector of P^T for eigenvalue 1
    vals, vecs = np.linalg.eig(transition_matrix.T)
    stationary = np.real(vecs[:, np.isclose(vals, 1.0)].flatten())
    stationary = np.abs(stationary)
    stationary /= stationary.sum()

    state   = int(rng.choice(k, p=stationary))
    returns = np.empty(n)
    states  = np.empty(n, dtype=int)

    for t in range(n):
        states[t]  = state
        returns[t] = rng.normal(state_means[state], state_vols[state])
        state      = int(rng.choice(k, p=transition_matrix[state]))

    return returns, states


def synthetic_conditional(
    n: int,
    state_fn: Callable[[int], int],
    forward_means: dict[int, float],
    forward_vols: dict[int, float],
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate n observations where each period's macro state is determined by
    state_fn(t) and forward returns are drawn from state-specific Gaussians.

    Returns a DataFrame with columns:
      date              — daily dates starting 2020-01-01
      macro_state       — int state label
      forward_5d_return — simulated 5-day forward return
    """
    rng       = np.random.default_rng(seed)
    base_date = pd.Timestamp("2020-01-01")
    rows: list[dict] = []

    for t in range(n):
        state = state_fn(t)
        mean  = forward_means.get(state, 0.0)
        vol   = forward_vols.get(state, 0.01)
        ret   = float(rng.normal(mean, vol))
        rows.append({
            "date":              base_date + pd.Timedelta(days=t),
            "macro_state":       state,
            "forward_5d_return": ret,
        })

    return pd.DataFrame(rows)
