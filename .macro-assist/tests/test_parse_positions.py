"""
Tests for parse_positions.py cost-basis accounting.

Pure unit tests — no network. Exercise _aggregate_positions directly with
synthetic TRADING rows. The focus is the moving-average cost basis: sold lots
must leave the cost basis, so a sell-then-rebuy at a different price does not
blend the old lot's price into the current holding (the pre-fix bug that
misstated NVIDIA cost basis by ~36% on the live portfolio).

Run:
    pytest .macro-assist/tests/test_parse_positions.py -v
"""
from __future__ import annotations

from parse_positions import _aggregate_positions, _open_positions


def _tx(dt: str, tx_type: str, shares: float, amount: float, symbol="X", name="Asset"):
    """One TRADING row. amount is negative for BUY, positive for SELL (TR convention);
    shares is signed (+buy, -sell)."""
    return {
        "datetime": dt, "category": "TRADING", "type": tx_type,
        "symbol": symbol, "name": name,
        "shares": str(shares), "amount": str(amount),
    }


def test_simple_buys_average():
    rows = [
        _tx("2025-01-01T10:00:00Z", "BUY", 10, -1000),   # €100/sh
        _tx("2025-01-02T10:00:00Z", "BUY", 10, -500),    # €50/sh
    ]
    pos = _aggregate_positions(rows)["X"]
    assert pos["net_shares"] == 20
    assert pos["cost_basis_eur"] == 1500
    assert pos["cost_basis_eur"] / pos["net_shares"] == 75  # avg cost


def test_sell_removes_at_average_not_all_time():
    """The core regression: BUY, SELL all, BUY again at a new price. The current
    holding's cost must reflect ONLY the last lot, not the all-time average."""
    rows = [
        _tx("2025-01-01T10:00:00Z", "BUY",  10, -1000),   # €100/sh
        _tx("2025-01-02T10:00:00Z", "SELL", -10, 1200),   # exit fully
        _tx("2025-01-03T10:00:00Z", "BUY",  10, -2000),   # rebuy €200/sh
    ]
    pos = _aggregate_positions(rows)["X"]
    assert pos["net_shares"] == 10
    # Correct = 2000 (the rebuy lot). The old all-time-average bug gave 1500.
    assert pos["cost_basis_eur"] == 2000
    assert pos["cost_basis_eur"] / pos["net_shares"] == 200


def test_partial_sell_keeps_average():
    rows = [
        _tx("2025-01-01T10:00:00Z", "BUY",  10, -1000),  # €100/sh
        _tx("2025-01-02T10:00:00Z", "BUY",  10, -2000),  # €200/sh → avg €150
        _tx("2025-01-03T10:00:00Z", "SELL", -5, 900),    # sell 5 at €150 avg
    ]
    pos = _aggregate_positions(rows)["X"]
    assert pos["net_shares"] == 15
    assert abs(pos["cost_basis_eur"] - 2250) < 1e-9   # 15 × €150
    assert abs(pos["cost_basis_eur"] / pos["net_shares"] - 150) < 1e-9


def test_full_exit_is_closed():
    rows = [
        _tx("2025-01-01T10:00:00Z", "BUY",  10, -1000),
        _tx("2025-01-02T10:00:00Z", "SELL", -10, 1100),
    ]
    agg = _aggregate_positions(rows)
    assert agg["X"]["net_shares"] == 0
    assert agg["X"]["cost_basis_eur"] == 0
    assert "X" not in _open_positions(agg)   # filtered out as closed


def test_chronological_replay_regardless_of_file_order():
    """Rows out of order in the file must still replay chronologically."""
    ordered = [
        _tx("2025-01-01T10:00:00Z", "BUY",  10, -1000),
        _tx("2025-01-02T10:00:00Z", "SELL", -10, 1200),
        _tx("2025-01-03T10:00:00Z", "BUY",  10, -2000),
    ]
    shuffled = [ordered[2], ordered[0], ordered[1]]  # reverse-ish, as TR often exports
    assert (
        _aggregate_positions(shuffled)["X"]["cost_basis_eur"]
        == _aggregate_positions(ordered)["X"]["cost_basis_eur"]
        == 2000
    )


def test_lifetime_reference_fields_preserved():
    rows = [
        _tx("2025-01-01T10:00:00Z", "BUY",  10, -1000),
        _tx("2025-01-02T10:00:00Z", "SELL", -10, 1200),
        _tx("2025-01-03T10:00:00Z", "BUY",  10, -2000),
    ]
    pos = _aggregate_positions(rows)["X"]
    assert pos["total_shares_bought"] == 20      # lifetime, not current
    assert pos["total_invested_eur"] == 3000
