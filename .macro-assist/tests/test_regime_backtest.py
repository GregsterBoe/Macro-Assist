"""
Tests for regime_backtest.py (WP-17.1 — regime look-ahead audit harness).

Pure unit tests: no network, no FRED. Feature matrices are synthetic and
injected directly; small train windows keep the HMM fits fast.

Run:
    pytest .macro-assist/tests/test_regime_backtest.py -v
"""
import numpy as np
import pandas as pd
import pytest

from regime_backtest import (
    walk_forward_regime,
    full_sample_regime,
    label_divergence,
    _fit_robust,
    forward_metrics,
    regime_skill,
)


def _two_regime_features(n: int = 240, seed: int = 0) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Synthetic 4-feature matrix with a clear regime switch at the midpoint:
    calm/low-vol first half, stressed/high-vol second half. Shapes match the
    HMM's (nfci_pct, yc_slope, hy_z, vol_pct) layout."""
    rng = np.random.default_rng(seed)
    half = n // 2
    calm = np.column_stack([
        rng.normal(0.2, 0.03, half),   # low NFCI pct (Risk-On)
        rng.normal(120, 10, half),     # positive curve slope (bps)
        rng.normal(-0.3, 0.1, half),   # tight HY z
        rng.normal(20, 5, half),       # low vol pct
    ])
    stress = np.column_stack([
        rng.normal(0.7, 0.03, n - half),  # high NFCI pct (Risk-Off)
        rng.normal(-20, 10, n - half),    # inverted curve
        rng.normal(1.2, 0.1, n - half),   # wide HY z
        rng.normal(80, 5, n - half),      # high vol pct
    ])
    feats = np.vstack([calm, stress])
    dates = pd.bdate_range("2015-01-01", periods=n)
    return feats, dates


# Fast settings for the tiny synthetic series.
_FAST = dict(n_states=2, train_window=60, min_train=30, refit_every=5, n_iter=50)


def test_walk_forward_emits_after_min_train():
    feats, dates = _two_regime_features()
    df = walk_forward_regime(feats, dates, **_FAST)
    assert not df.empty
    # No reading before min_train warmup.
    assert df.index.min() >= dates[_FAST["min_train"]]
    assert set(["state_pit", "label", "top_posterior", "refit"]).issubset(df.columns)
    assert df["top_posterior"].between(0, 1).all()


def test_walk_forward_refits_periodically():
    feats, dates = _two_regime_features()
    df = walk_forward_regime(feats, dates, **_FAST)
    # At least one refit, and refits spaced by refit_every.
    assert df["refit"].sum() >= 2


def test_walk_forward_detects_regime_switch():
    feats, dates = _two_regime_features(n=240)
    df = walk_forward_regime(feats, dates, **_FAST)
    # The calm early stretch and the stressed late stretch should not all carry
    # the same state — the harness must react to the planted regime change.
    assert df["state_pit"].nunique() >= 2


def test_full_sample_runs_and_aligns():
    feats, dates = _two_regime_features()
    full = full_sample_regime(feats, dates, n_states=2, min_train=30, n_iter=50)
    assert not full.empty
    assert set(["state_full", "label", "top_posterior"]).issubset(full.columns)


def test_label_divergence_shape():
    feats, dates = _two_regime_features()
    pit = walk_forward_regime(feats, dates, **_FAST)
    full = full_sample_regime(feats, dates, n_states=2, min_train=30, n_iter=50)
    div = label_divergence(pit, full)
    assert div["n"] > 0
    assert 0.0 <= div["disagreement_rate"] <= 1.0


def test_label_divergence_empty_inputs():
    empty = pd.DataFrame()
    assert label_divergence(empty, empty)["n"] == 0


def test_feature_date_mismatch_raises():
    feats, dates = _two_regime_features()
    with pytest.raises(ValueError):
        walk_forward_regime(feats, dates[:-5], **_FAST)


# ---------------------------------------------------------------------------
# Robustness: singular / collinear windows must not crash (fallback ladder)
# ---------------------------------------------------------------------------

def _collinear_features(n: int = 120, seed: int = 1) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """A pathological matrix: two duplicated columns + a near-constant one, which
    drives a full-covariance HMM to a non-positive-definite covariance."""
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 0.01, n)
    feats = np.column_stack([
        base,
        base,                                  # exact duplicate → singular
        np.full(n, 0.5) + rng.normal(0, 1e-9, n),  # near-constant
        rng.normal(0, 0.01, n),
    ])
    dates = pd.bdate_range("2015-01-01", periods=n)
    return feats, dates


def test_fit_robust_falls_back_or_returns_none():
    feats, _ = _collinear_features()
    # full covariance would raise; _fit_robust must return a model (via diag) or
    # (None, None) — never propagate the LinAlgError/ValueError.
    model, cov = _fit_robust(feats, n_states=4, random_state=42, n_iter=50, prefer="full")
    assert (model is None and cov is None) or cov in ("full", "diag")


def test_walk_forward_survives_singular_windows():
    feats, dates = _collinear_features(n=120)
    # Must complete without raising despite the pathological windows.
    df = walk_forward_regime(feats, dates, n_states=4, train_window=60,
                             min_train=30, refit_every=5, n_iter=50)
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert df["fit_cov"].isin(["full", "diag", "carry"]).all()


# ---------------------------------------------------------------------------
# WP-17.2 skill gate
# ---------------------------------------------------------------------------

def test_forward_metrics_basic():
    close = pd.Series([100.0, 110.0, 99.0, 99.0, 99.0],
                      index=pd.date_range("2024-01-01", periods=5, freq="B"))
    fret, fvol = forward_metrics(close, horizon=2)
    # From index 0 over next 2 days: 100 -> 99 => -1%.
    assert fret.iloc[0] == pytest.approx(99.0 / 100.0 - 1.0)
    assert np.isnan(fret.iloc[-1])     # no forward window


def _planted_skill_inputs(n: int = 300, seed: int = 0):
    """Risk-Off labels coincide with a falling, high-vol market; Risk-On with a
    calm rising one — a regime layer with skill must recover this."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    rets = rng.normal(0.0005, 0.006, n)
    labels = ["Risk-On Low-Vol"] * n
    post = np.full(n, 0.9)
    # Two stressed windows: downward drift + high vol, labelled Risk-Off High-Vol.
    for lo, hi in [(80, 110), (200, 230)]:
        rets[lo:hi] = rng.normal(-0.004, 0.02, hi - lo)
        for k in range(lo, hi):
            labels[k] = "Risk-Off High-Vol"
    close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)
    pit = pd.DataFrame({"label": labels, "top_posterior": post}, index=idx)
    return pit, close


def test_regime_skill_recovers_planted_signal():
    pit, close = _planted_skill_inputs()
    skill = regime_skill(pit, close, horizons=(5, 10), drawdown_threshold=0.05)
    assert set(skill) == {5, 10}
    r = skill[10]
    # Risk-Off should lead drawdowns better than chance...
    assert r["auc_riskoff_drawdown"] is not None and r["auc_riskoff_drawdown"] > 0.5
    # ...and Risk-Off forward returns should be worse than Risk-On.
    sep = r["separation"]
    assert sep["Risk-Off High-Vol"]["mean_fret"] < sep["Risk-On Low-Vol"]["mean_fret"]


def test_regime_skill_keys_present():
    pit, close = _planted_skill_inputs()
    r = regime_skill(pit, close, horizons=(5,))[5]
    assert {"separation", "auc_riskoff_drawdown", "auc_highvol_fwdvol",
            "auc_riskoff_drawdown_hiconf", "n_hiconf"}.issubset(r)
