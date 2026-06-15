"""
Tests for fragility_backtest.py (WP-16.A.2 — fragility-as-early-warning validation).

Pure unit tests only: no network calls. The yfinance-driven CLI is not tested
here; only the deterministic evaluation logic.

Run:
    pytest .macro-assist/tests/test_fragility_backtest.py -v
"""
import numpy as np
import pandas as pd
import pytest

from fragility_backtest import (
    forward_worst_return,
    drawdown_label,
    walk_forward_fragility,
    auc,
    evaluate,
)


def _returns_to_close(returns: np.ndarray, start: float = 100.0) -> pd.Series:
    idx = pd.date_range("2008-01-01", periods=len(returns) + 1, freq="B")
    prices = start * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# forward_worst_return / drawdown_label
# ---------------------------------------------------------------------------

def test_forward_worst_return_detects_drop():
    # Flat, then a 10% single-day drop at index 2.
    close = pd.Series([100.0, 100.0, 90.0, 90.0, 90.0],
                      index=pd.date_range("2024-01-01", periods=5, freq="B"))
    worst = forward_worst_return(close, horizon=3)
    # From index 1 the next 3 days include the drop to 90 => -10%.
    assert worst.iloc[1] == pytest.approx(-0.1)
    # Last value has no forward window.
    assert np.isnan(worst.iloc[-1])


def test_drawdown_label_threshold():
    close = pd.Series([100.0, 100.0, 90.0, 90.0, 90.0],
                      index=pd.date_range("2024-01-01", periods=5, freq="B"))
    lab5 = drawdown_label(close, threshold=0.05, horizon=3)
    lab15 = drawdown_label(close, threshold=0.15, horizon=3)
    # The 10% drop trips a 5% threshold but not a 15% one.
    assert lab5.iloc[1] == True   # noqa: E712
    assert lab15.iloc[1] == False  # noqa: E712


# ---------------------------------------------------------------------------
# auc
# ---------------------------------------------------------------------------

def test_auc_perfect_separation():
    scores = pd.Series([1, 2, 3, 10, 11, 12])
    labels = pd.Series([False, False, False, True, True, True])
    assert auc(scores, labels) == 1.0


def test_auc_inverted():
    scores = pd.Series([10, 11, 12, 1, 2, 3])
    labels = pd.Series([False, False, False, True, True, True])
    assert auc(scores, labels) == 0.0


def test_auc_no_skill_random():
    rng = np.random.default_rng(0)
    scores = pd.Series(rng.normal(size=2000))
    labels = pd.Series(rng.random(2000) < 0.3)
    a = auc(scores, labels)
    assert 0.45 < a < 0.55


def test_auc_none_when_single_class():
    scores = pd.Series([1.0, 2.0, 3.0])
    labels = pd.Series([True, True, True])
    assert auc(scores, labels) is None


# ---------------------------------------------------------------------------
# walk_forward_fragility
# ---------------------------------------------------------------------------

def _vol_explosion(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 0.008, n)
    ramp = np.ones(n)
    tail = n // 3
    ramp[-tail:] = np.linspace(1.0, 6.0, tail)
    return base * ramp


def test_walk_forward_produces_readings():
    rng = np.random.default_rng(5)
    histories = {
        name: _returns_to_close(rng.normal(0, 0.01, 300))
        for name in ["sp500", "nasdaq", "gold", "wti_oil"]
    }
    df = walk_forward_fragility(histories)
    assert not df.empty
    assert set(["composite", "label", "trend", "variance_trend",
                "correlation", "vix_term", "autocorr"]).issubset(df.columns)
    # Composite stays in range and no reading appears before min_history.
    assert df["composite"].between(0, 100).all()
    # No reading before min_history warmup; never more than the anchor length.
    assert 0 < len(df) < len(histories["sp500"]) - 100


def test_walk_forward_rises_into_vol_explosion():
    histories = {
        name: _returns_to_close(_vol_explosion(300, seed=i))
        for i, name in enumerate(["sp500", "nasdaq", "gold", "wti_oil"])
    }
    df = walk_forward_fragility(histories)
    assert not df.empty
    # Fragility in the final (exploding) stretch should exceed the early calm.
    first_q = df["composite"].iloc[: len(df) // 4].mean()
    last_q = df["composite"].iloc[-len(df) // 4:].mean()
    assert last_q > first_q


def test_walk_forward_requires_anchor():
    try:
        walk_forward_fragility({"gold": _returns_to_close(np.zeros(200))})
    except ValueError:
        return
    raise AssertionError("expected ValueError when anchor missing")


# ---------------------------------------------------------------------------
# evaluate (end to end on synthetic data with a planted signal)
# ---------------------------------------------------------------------------

def test_evaluate_recovers_planted_signal():
    # Build histories where vol explodes in the final third, then label the
    # drawdowns on the anchor. A working harness should give composite AUC > 0.5.
    rng = np.random.default_rng(11)
    n = 400
    histories = {}
    for i, name in enumerate(["sp500", "nasdaq", "gold", "wti_oil"]):
        rets = _vol_explosion(n, seed=i)
        # Inject a downward drift into the exploding tail of the anchor so real
        # drawdowns coincide with rising fragility.
        if name == "sp500":
            rets[-n // 3:] -= 0.004
        histories[name] = _returns_to_close(rets)

    df = walk_forward_fragility(histories)
    labels = drawdown_label(histories["sp500"], threshold=0.05, horizon=10)
    report = evaluate(df, labels)

    assert report["n_days"] > 0
    assert 0.0 <= report["base_rate"] <= 1.0
    # The composite should carry positive skill on a planted signal.
    assert report["auc"]["composite"] is not None
    assert report["auc"]["composite"] > 0.5
    assert set(report["flags"].keys()) >= {"elevated_label", "rising_trend",
                                           "elevated_and_rising"}


def test_evaluate_empty_when_no_overlap():
    df = pd.DataFrame()
    assert evaluate(df, pd.Series(dtype=bool)) == {}
