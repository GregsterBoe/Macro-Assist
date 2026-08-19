"""
Tests for portfolio/rebalance.py (Phase 20, WP-20.D).

Pure unit tests — no network, no model artifacts. The live layer (yfinance /
regime) is lazy-imported and not exercised here; everything below runs on
injected prices/regime and an inline note fixture, so it stays fast and offline.

Run:
    pytest .macro-assist/tests/test_rebalance.py -v
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from portfolio.book import Book
from portfolio.rebalance import (
    advance_books,
    build_asset_signals,
    conditional_sigma_annual,
    equal_vol_weights,
    format_report,
    parse_note_signals,
    v1_instruments,
)

# A trimmed but faithful predictions block (real note format, incl. unicode minus).
NOTE = """\
### 5-Day Predictions

| Asset | Bias | Primary Driver | Confidence | Target Range |
|-------|------|----------------|------------|--------------
| S&P 500 | Neutral | 5d conditional median +0.4%, P25–P75 −0.8%/+1.2% — tight. | 58% | -1.0% to +1.3% |
| Gold | Bullish | 5d conditional median +0.9%, P25–P75 −1.1%/+2.6% — skewed. | 57% | $4,380–$4,520 |
| WTI Oil | Neutral | 5d conditional median −0.4%, P25–P75 −2.9%/+3.0% — wide. | 60% | $81.50–$88.00 |
| 10Y Treasury Yield | Bullish | Directional view: yields drift higher, real yields elevated. | 51% | 4.65%–4.85% |
| Bitcoin | Neutral | No conditional base rate provided for BTC; no quant edge. | 54% | $60,500–$68,500 |

Review date: 2026-08-26
"""

PRICES = {"S&P 500": 5000.0, "Gold": 2400.0, "Bitcoin": 64000.0, "10Y (IEF)": 95.0}
HAR = {"S&P 500": 0.16, "Gold": 0.14, "Bitcoin": 0.55, "10Y (IEF)": 0.06}


# ---------------------------------------------------------------------------
# Note parsing
# ---------------------------------------------------------------------------
def test_parse_note_signals_reads_table():
    sigs = parse_note_signals(NOTE)
    assert sigs["S&P 500"].bias == "Neutral"
    assert sigs["Gold"].bias == "Bullish"
    assert sigs["Gold"].confidence_pct == 57
    assert sigs["10Y Treasury Yield"].bias == "Bullish"
    assert sigs["Bitcoin"].bias == "Neutral"


def test_parse_returns_empty_without_block():
    assert parse_note_signals("no predictions here") == {}


def test_conditional_sigma_from_band_and_annualizes():
    # Gold band −1.1%/+2.6% -> IQR 3.7% -> sigma_5d = 0.037/1.349, annualized *sqrt(252/5)
    s = conditional_sigma_annual("... P25–P75 −1.1%/+2.6% ...")
    expected = (0.026 - (-0.011)) / 1.349 * math.sqrt(252 / 5)
    assert s == pytest.approx(expected, rel=1e-6)


def test_conditional_sigma_none_without_band():
    assert conditional_sigma_annual("Directional view: yields drift higher.") is None


# ---------------------------------------------------------------------------
# Signal assembly
# ---------------------------------------------------------------------------
def test_build_asset_signals_maps_universe_and_inverts_10y():
    note_signals = parse_note_signals(NOTE)
    signals = build_asset_signals(note_signals, HAR)
    by = {s.asset: s for s in signals}
    # WTI / DXY are not in the v1 universe -> excluded
    assert set(by) == {"S&P 500", "Gold", "Bitcoin", "10Y (IEF)"}
    assert by["10Y (IEF)"].invert_sign is True
    assert by["Gold"].confidence == pytest.approx(0.57)
    assert by["Gold"].har_sigma_annual == pytest.approx(0.14)
    # 10Y row has no conditional band -> cond σ is None (⇒ sizer abstains by default)
    assert by["10Y (IEF)"].cond_sigma_annual is None
    # BTC row explicitly has no base rate -> None
    assert by["Bitcoin"].cond_sigma_annual is None


def test_equal_vol_weights_are_inverse_vol_and_sum_to_one():
    w = equal_vol_weights({"A": 0.10, "B": 0.20})
    assert w["A"] == pytest.approx(2 / 3)   # lower vol -> larger weight
    assert w["B"] == pytest.approx(1 / 3)
    assert sum(w.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Orchestration (injected prices/regime)
# ---------------------------------------------------------------------------
def _fresh_books():
    book, bench = Book(arm="market"), Book(arm="market-benchmark")
    for inst in v1_instruments():
        book.register(inst)
        bench.register(inst)
    return book, bench


def test_advance_books_sizes_only_actionable_names():
    note_signals = parse_note_signals(NOTE)
    signals = build_asset_signals(note_signals, HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    # Only Gold is both directional (Bullish) AND has a conditional band -> sized.
    # S&P/WTI/BTC are Neutral or band-less; 10Y is band-less -> all abstain.
    assert "Gold" in book.positions and book.positions["Gold"].shares > 0
    assert rec["targets"]["Gold"]["abstained"] is False
    assert rec["targets"]["10Y (IEF)"]["reason"] == "no-distribution"
    assert rec["targets"]["S&P 500"]["reason"] == "neutral/no-view"


def test_advance_books_no_live_regime_notes_gate_one():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench,
                        regime=None, har_sigmas=HAR)
    assert rec["gate"] == 1.0


def test_benchmark_inits_then_marks_forward():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    assert bench.positions  # initialized equal-vol on first advance
    nav0 = bench.nav(PRICES)
    # a week later, SPX +10%, no rebalance of the benchmark -> it just marks up
    later = dict(PRICES, **{"S&P 500": 5500.0})
    advance_books(date(2026, 8, 26), "market", signals, later, book, bench, har_sigmas=HAR)
    assert bench.nav(later) > nav0
    # benchmark did not re-trade (still the same as its init close-out set)
    assert bench.decision_log[-1]["as_of"] == "2026-08-19"  # only one rebalance record


def test_live_regime_degrades_to_none_without_fred_key(monkeypatch):
    # No FRED_API_KEY -> point-in-time snapshot can't be built -> gate defaults to 1.0.
    from portfolio import rebalance as R

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert R.live_regime(date(2026, 8, 19)) is None


def test_format_report_renders_table():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    md = format_report(rec)
    assert "# Paper Portfolio — market — 2026-08-19" in md
    assert "| Gold |" in md
    assert "Regime gate" in md
