"""
Tests for portfolio/book.py (Phase 20, WP-20.B).

Pure unit tests — no network. The accounting core is the risky-to-get-wrong
part, so these cover valuation, rebalancing (long/short/close), costs, leverage,
sleeve attribution, marking, benchmark buy-and-hold, and JSON round-trip.

Run:
    pytest .macro-assist/tests/test_book.py -v
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from portfolio.book import Book, Instrument, Position, buy_and_hold


def _spx() -> Instrument:
    return Instrument("S&P 500", "^GSPC", "equity", cost_bps=10.0)


def _gold() -> Instrument:
    return Instrument("Gold", "GC=F", "commodity", cost_bps=10.0)


def _book_two() -> Book:
    b = Book(arm="market", starting_nav=100_000.0)
    b.register(_spx())
    b.register(_gold())
    return b


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------
def test_empty_book_nav_is_starting_nav():
    b = _book_two()
    assert b.nav({"S&P 500": 100.0, "Gold": 50.0}) == 100_000.0
    assert b.market_value({"S&P 500": 100.0, "Gold": 50.0}) == 0.0
    assert b.gross_exposure({"S&P 500": 100.0, "Gold": 50.0}) == 0.0


def test_register_required_for_rebalance():
    b = Book()
    with pytest.raises(KeyError):
        b.rebalance({"S&P 500": 0.5}, {"S&P 500": 100.0}, date(2026, 8, 19))


# ---------------------------------------------------------------------------
# Rebalance mechanics
# ---------------------------------------------------------------------------
def test_rebalance_long_no_cost():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    rec = b.rebalance({"S&P 500": 0.5}, {"S&P 500": 100.0}, date(2026, 8, 19))
    # 50% of 100k = 50k / 100 = 500 shares; cash = 50k
    assert b.positions["S&P 500"].shares == pytest.approx(500.0)
    assert b.cash == pytest.approx(50_000.0)
    # NAV unchanged by a costless rebalance
    assert b.nav({"S&P 500": 100.0}) == pytest.approx(100_000.0)
    assert rec["trades"]["S&P 500"]["traded_notional"] == pytest.approx(50_000.0)


def test_rebalance_cost_reduces_nav():
    b = _book_two()  # 10 bps
    b.rebalance({"S&P 500": 0.5}, {"S&P 500": 100.0}, date(2026, 8, 19))
    # cost = 50_000 * 10/1e4 = 50
    assert b.nav({"S&P 500": 100.0}) == pytest.approx(99_950.0)
    assert b.cash == pytest.approx(49_950.0)


def test_short_position_negative_shares_and_value():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.rebalance({"S&P 500": -0.3}, {"S&P 500": 100.0}, date(2026, 8, 19))
    assert b.positions["S&P 500"].shares == pytest.approx(-300.0)
    # short raises cash above NAV
    assert b.cash == pytest.approx(130_000.0)
    assert b.net_exposure({"S&P 500": 100.0}) == pytest.approx(-0.3)
    assert b.gross_exposure({"S&P 500": 100.0}) == pytest.approx(0.3)


def test_omitted_instrument_is_closed():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.instruments["Gold"].cost_bps = 0.0
    b.rebalance({"S&P 500": 0.5, "Gold": 0.5}, {"S&P 500": 100.0, "Gold": 50.0}, date(2026, 8, 19))
    assert b.positions["Gold"].shares == pytest.approx(1000.0)
    # Second rebalance omits Gold -> closed to 0
    b.rebalance({"S&P 500": 0.5}, {"S&P 500": 100.0, "Gold": 50.0}, date(2026, 8, 20))
    assert b.positions["Gold"].shares == pytest.approx(0.0)


def test_leverage_shows_as_negative_cash():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.instruments["Gold"].cost_bps = 0.0
    # gross 1.5 => cash goes negative (margin), NAV still ~100k
    b.rebalance({"S&P 500": 1.0, "Gold": 0.5}, {"S&P 500": 100.0, "Gold": 50.0}, date(2026, 8, 19))
    assert b.cash == pytest.approx(-50_000.0)
    assert b.gross_exposure({"S&P 500": 100.0, "Gold": 50.0}) == pytest.approx(1.5)
    assert b.nav({"S&P 500": 100.0, "Gold": 50.0}) == pytest.approx(100_000.0)


def test_rebalance_missing_price_for_target_raises():
    b = _book_two()
    with pytest.raises(KeyError):
        b.rebalance({"S&P 500": 0.5}, {"Gold": 50.0}, date(2026, 8, 19))


# ---------------------------------------------------------------------------
# PnL / marking
# ---------------------------------------------------------------------------
def test_price_move_moves_nav():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.rebalance({"S&P 500": 1.0}, {"S&P 500": 100.0}, date(2026, 8, 19))
    # fully invested; +10% price -> +10% NAV
    b.mark({"S&P 500": 110.0}, date(2026, 8, 20))
    assert b.nav({"S&P 500": 110.0}) == pytest.approx(110_000.0)
    assert b.nav_history[-1]["nav"] == pytest.approx(110_000.0)


def test_short_profits_when_price_falls():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.rebalance({"S&P 500": -1.0}, {"S&P 500": 100.0}, date(2026, 8, 19))
    b.mark({"S&P 500": 90.0}, date(2026, 8, 20))
    # short 1000 sh, cash 200k, position value -90k -> NAV 110k
    assert b.nav({"S&P 500": 90.0}) == pytest.approx(110_000.0)


# ---------------------------------------------------------------------------
# Sleeve attribution
# ---------------------------------------------------------------------------
def test_exposure_by_sleeve():
    b = _book_two()
    b.instruments["S&P 500"].cost_bps = 0.0
    b.instruments["Gold"].cost_bps = 0.0
    b.rebalance(
        {"S&P 500": 0.5, "Gold": 0.3},
        {"S&P 500": 100.0, "Gold": 50.0},
        date(2026, 8, 19),
        sleeve_of={"S&P 500": "macro", "Gold": "sector"},
    )
    exp = b.exposure_by_sleeve({"S&P 500": 100.0, "Gold": 50.0})
    assert exp["macro"] == pytest.approx(50_000.0)
    assert exp["sector"] == pytest.approx(30_000.0)


# ---------------------------------------------------------------------------
# Benchmark buy-and-hold
# ---------------------------------------------------------------------------
def test_buy_and_hold_drifts_and_tracks():
    hist = [
        (date(2026, 8, 19), {"S&P 500": 100.0, "Gold": 50.0}),
        (date(2026, 8, 20), {"S&P 500": 110.0, "Gold": 50.0}),
    ]
    insts = [Instrument("S&P 500", "^GSPC", cost_bps=0.0), Instrument("Gold", "GC=F", cost_bps=0.0)]
    bench = buy_and_hold({"S&P 500": 0.5, "Gold": 0.5}, insts, hist)
    # 50k SPX + 50k gold; SPX +10% -> 55k+50k = 105k, no rebalance back
    assert bench.nav_history[-1]["nav"] == pytest.approx(105_000.0)
    assert bench.weights({"S&P 500": 110.0, "Gold": 50.0})["S&P 500"] == pytest.approx(55_000.0 / 105_000.0)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def test_json_round_trip(tmp_path):
    b = _book_two()
    b.rebalance({"S&P 500": 0.5, "Gold": 0.3}, {"S&P 500": 100.0, "Gold": 50.0}, date(2026, 8, 19))
    b.mark({"S&P 500": 105.0, "Gold": 51.0}, date(2026, 8, 20))
    p = tmp_path / "book__market.json"
    b.save(p)
    loaded = Book.load(p)
    assert loaded.arm == b.arm
    assert loaded.cash == pytest.approx(b.cash)
    assert loaded.positions["S&P 500"].shares == pytest.approx(b.positions["S&P 500"].shares)
    assert loaded.decision_log == b.decision_log
    assert loaded.nav({"S&P 500": 105.0, "Gold": 51.0}) == pytest.approx(
        b.nav({"S&P 500": 105.0, "Gold": 51.0})
    )
    # file is valid JSON
    json.loads(p.read_text())
