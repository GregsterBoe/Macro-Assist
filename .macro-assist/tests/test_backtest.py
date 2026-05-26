"""
Tests for backtest.run_backtest, score_backtest, and baseline strategies.

test_neutral_strategy_scores_random: integration test — downloads yfinance prices
to score ~50% directional accuracy for the neutral strategy. Skip if no internet.

test_existing_pipeline_reproduces_history: marked xfail — requires Phase 13.2.

Run:
    pytest .macro-assist/tests/test_backtest.py -v
"""
from datetime import date
from pathlib import Path

import pytest

from backtest import (
    run_backtest,
    score_backtest,
    strategy_neutral,
    strategy_random_walk,
    strategy_existing_pipeline,
)
from score_predictions import ASSET_TICKERS


# ---------------------------------------------------------------------------
# Unit tests (no external API calls)
# ---------------------------------------------------------------------------

def test_strategy_neutral_returns_all_assets():
    preds = strategy_neutral({})
    assert set(preds.keys()) == set(ASSET_TICKERS.keys())
    for asset, p in preds.items():
        assert p["bias"] == "Neutral"
        assert p["confidence"] == 50


def test_strategy_random_walk_returns_all_assets():
    fake_snapshot = {
        "market": {
            "sp500":   {"price": 5000, "change_pct": 0.5,  "date": "2024-06-03"},
            "gold":    {"price": 2300, "change_pct": -0.3, "date": "2024-06-03"},
            "wti_oil": {"price": 78.0, "change_pct": 0.0,  "date": "2024-06-03"},
            "dxy":     {"price": 104,  "change_pct": 0.1,  "date": "2024-06-03"},
            "bitcoin": {"price": 67000,"change_pct": 1.2,  "date": "2024-06-03"},
        }
    }
    preds = strategy_random_walk(fake_snapshot)
    assert set(preds.keys()) == set(ASSET_TICKERS.keys())
    assert preds["S&P 500"]["bias"]  == "Bullish"
    assert preds["Gold"]["bias"]     == "Bearish"
    assert preds["WTI Oil"]["bias"]  == "Neutral"
    assert preds["Bitcoin"]["bias"]  == "Bullish"


def test_strategy_random_walk_no_market_data():
    """Falls back to Neutral when market data absent."""
    preds = strategy_random_walk({})
    for asset, p in preds.items():
        assert p["bias"] == "Neutral", f"{asset}: expected Neutral, got {p['bias']}"


def test_run_backtest_writes_files(tmp_path):
    """run_backtest with a stub snapshot_fn should write one JSON per weekday."""
    start = date(2024, 6, 3)   # Monday
    end   = date(2024, 6, 7)   # Friday (5 weekdays)

    result = run_backtest(
        start, end,
        strategy_neutral,
        tmp_path / "neutral",
        _snapshot_fn=lambda d: {},
    )
    assert result["dates_processed"] == 5
    assert result["errors"] == []
    files = list((tmp_path / "neutral").glob("*.json"))
    assert len(files) == 5


def test_run_backtest_skips_weekends(tmp_path):
    """Weekends must be skipped by default."""
    start = date(2024, 6, 1)   # Saturday
    end   = date(2024, 6, 2)   # Sunday
    result = run_backtest(
        start, end, strategy_neutral, tmp_path / "wknd",
        _snapshot_fn=lambda d: {},
    )
    assert result["dates_processed"] == 0


def test_run_backtest_records_errors(tmp_path):
    """Errors from a failing strategy should be captured, not propagate."""
    def bad_strategy(snapshot):
        raise RuntimeError("deliberate failure")

    result = run_backtest(
        date(2024, 6, 3), date(2024, 6, 5),
        bad_strategy,
        tmp_path / "bad",
        _snapshot_fn=lambda d: {},
    )
    assert result["dates_processed"] == 0
    assert len(result["errors"]) == 3


def test_existing_pipeline_raises():
    with pytest.raises(NotImplementedError):
        strategy_existing_pipeline({})


# ---------------------------------------------------------------------------
# Integration test — requires yfinance network access
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_neutral_strategy_scores_random(tmp_path):
    """
    Neutral strategy over 6 months must score ~50% directional accuracy (±5pp).
    Downloads real yfinance prices to score — requires internet access.
    """
    start = date(2024, 1, 2)
    end   = date(2024, 6, 28)

    result = run_backtest(
        start, end,
        strategy_neutral,
        tmp_path / "neutral",
        _snapshot_fn=lambda d: {},   # neutral ignores snapshot
    )
    assert result["dates_processed"] > 100, "Expected >100 trading days in 6-month window"

    stats = score_backtest(tmp_path / "neutral")
    assert "t5" in stats, "No t5 scores available — check that the eval window has closed"

    for asset, s in stats["t5"].items():
        acc = s["accuracy"]
        assert 0.40 <= acc <= 0.60, (
            f"Neutral strategy t5 accuracy for {asset} is {acc:.1%} — "
            "expected within 50% ± 10pp (Neutral calls score 0.5 exactly)"
        )


# ---------------------------------------------------------------------------
# Placeholder — Phase 13.2
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="strategy_existing_pipeline is a stub until Phase 13.2", strict=True)
def test_existing_pipeline_reproduces_history(tmp_path):
    """
    Running the existing pipeline as a strategy over the past 30 scored days
    should reproduce accuracy_summary.json within ±2pp per asset.
    Full implementation deferred to Phase 13.2.
    """
    strategy_existing_pipeline({})   # currently raises NotImplementedError
