"""
Tests for point_in_time.historical_snapshot.

All tests are integration tests that call the FRED ALFRED API and yfinance.
They are skipped automatically when FRED_API_KEY is not set.

Run:
    pytest .macro-assist/tests/test_point_in_time.py -v
"""
import os
from datetime import date

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("FRED_API_KEY"),
    reason="FRED_API_KEY not set — skipping ALFRED integration tests",
)

from point_in_time import historical_snapshot, ALFRED_MIN_DATE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def snapshot_2024():
    """Single ALFRED snapshot; fetched once per test session."""
    return historical_snapshot(date(2024, 6, 3))   # Monday, well inside coverage


@pytest.fixture(scope="module")
def live_fred_keys():
    """Key set from a live fetch_fred_data() call for schema comparison."""
    from fredapi import Fred
    from collect_and_analyze import fetch_fred_data, FRED_SERIES
    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    data = fetch_fred_data(fred)
    # Return only the per-series keys (exclude derived scalar keys)
    return {k for k in data if k not in ("yield_curve_spread", "net_liquidity")}


# ---------------------------------------------------------------------------
# test_pre_alfred_raises
# ---------------------------------------------------------------------------

def test_pre_alfred_raises():
    """Dates before ALFRED coverage must raise ValueError."""
    with pytest.raises(ValueError, match="ALFRED"):
        historical_snapshot(date(1990, 6, 1))


def test_pre_alfred_boundary():
    """Date exactly at the minimum should NOT raise."""
    # Just verify no exception; we don't assert on data content here
    # (this is the oldest ALFRED date — data may be sparse)
    try:
        historical_snapshot(ALFRED_MIN_DATE)
    except ValueError:
        pytest.fail("historical_snapshot raised ValueError at ALFRED_MIN_DATE boundary")


# ---------------------------------------------------------------------------
# test_schema_matches_current
# ---------------------------------------------------------------------------

def test_schema_matches_current(snapshot_2024, live_fred_keys):
    """
    Every FRED series key present in the live pipeline should also appear in
    the historical snapshot (market and snapshot_date are permitted extras).
    """
    extra_keys     = {"market", "snapshot_date", "yield_curve_spread", "net_liquidity"}
    snap_fred_keys = {k for k in snapshot_2024 if k not in extra_keys}

    missing = live_fred_keys - snap_fred_keys
    assert not missing, (
        f"Historical snapshot is missing FRED keys present in live data: {missing}"
    )

    # Each per-series entry should be a dict with the required sub-keys
    required_sub = {"value", "prev", "date", "days_stale", "frequency"}
    for key in snap_fred_keys:
        entry = snapshot_2024[key]
        assert isinstance(entry, dict), f"{key}: expected dict, got {type(entry)}"
        assert required_sub <= entry.keys(), (
            f"{key}: missing sub-keys {required_sub - entry.keys()}"
        )


# ---------------------------------------------------------------------------
# test_no_future_leakage
# ---------------------------------------------------------------------------

def test_no_future_leakage():
    """
    For 10 fixed historical dates, no series entry may have a release date
    after the snapshot_date (look-ahead bias check).
    """
    # Fixed dates to keep test deterministic across runs
    test_dates = [
        date(2020, 3, 15),
        date(2020, 9, 1),
        date(2021, 2, 1),
        date(2021, 8, 16),
        date(2022, 1, 3),
        date(2022, 6, 1),
        date(2022, 11, 14),
        date(2023, 3, 1),
        date(2023, 9, 18),
        date(2024, 1, 2),
    ]

    for snap_date in test_dates:
        snap = historical_snapshot(snap_date)
        for key, val in snap.items():
            if key in ("snapshot_date", "yield_curve_spread"):
                continue
            if isinstance(val, dict) and "date" in val:
                series_date = date.fromisoformat(val["date"])
                assert series_date <= snap_date, (
                    f"Future leakage: {key}.date={series_date} > snapshot={snap_date}"
                )
            # Market sub-entries
            if key == "market":
                for mname, mdata in val.items():
                    if isinstance(mdata, dict) and "date" in mdata:
                        mdate = date.fromisoformat(mdata["date"])
                        assert mdate <= snap_date, (
                            f"Market future leakage: market.{mname}.date={mdate} > snapshot={snap_date}"
                        )


# ---------------------------------------------------------------------------
# test_market_data_present
# ---------------------------------------------------------------------------

def test_market_data_present(snapshot_2024):
    """Market data must be present, non-empty, and dated on or before snapshot_date."""
    snap      = snapshot_2024
    snap_date = date.fromisoformat(snap["snapshot_date"])

    assert "market" in snap, "snapshot missing 'market' key"
    market = snap["market"]
    assert len(market) > 0, "market dict is empty"

    # Core assets that must be present
    for required in ("sp500", "gold"):
        assert required in market, f"'{required}' missing from market snapshot"

    for name, mdata in market.items():
        assert isinstance(mdata, dict), f"market.{name} is not a dict"
        assert "price" in mdata,      f"market.{name} missing 'price'"
        assert "date" in mdata,       f"market.{name} missing 'date'"
        mdate = date.fromisoformat(mdata["date"])
        assert mdate <= snap_date, (
            f"market.{name}.date={mdate} is after snapshot_date={snap_date}"
        )
