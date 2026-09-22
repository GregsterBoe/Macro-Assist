"""
On 2026-09-22 the 06:00 UTC run published no note because `fed_funds_rate` —
a MONTHLY series, dated month-start — could not be downloaded. Its value could
not have changed between that failure and the 12:48 rerun that used it.
`validate_data` aborted anyway, because "critical" meant "not fetched today"
and the fetched dict is built from scratch each run.

These tests pin todo #28's three decisions:

  * monthly series carry, for seven days; `treasury_10y` never does, at any
    window, because yesterday's 10Y published as today's is a different claim;
  * a carried value is marked (`carried_forward`, `carried_from`) and its
    `days_stale` is recomputed against the run's date, so a scored history can
    always be split later — the [KB-029] failure otherwise returns in a new
    costume;
  * the abort survives, for a series with no value available at all.

A carried entry is never snapshotted, so a carry cannot chain past its window.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

import collect_and_analyze as ca
import fred_data


def _entry(value: float, observed: str, frequency: str) -> dict:
    return {"value": value, "prev": value, "date": observed,
            "days_stale": 0, "frequency": frequency}


@pytest.fixture
def snaps(tmp_path):
    """A snapshot directory, and a helper that writes one."""
    def write(day: str, series: dict) -> None:
        (tmp_path / f"{day}.json").write_text(
            json.dumps({"asof": day, "series": series}), encoding="utf-8")
    write.dir = tmp_path
    return write


# ---------------------------------------------------------------------------
# Which, and for how long
# ---------------------------------------------------------------------------

def test_a_monthly_series_is_carried(snaps):
    snaps("2026-09-21", {"fed_funds_rate": _entry(4.33, "2026-09-01", "monthly")})
    data: dict = {}

    carried = fred_data.carry_forward(data, ["fed_funds_rate"], date(2026, 9, 22),
                                      directory=snaps.dir)
    assert carried == ["fed_funds_rate"]
    assert data["fed_funds_rate"]["value"] == 4.33


def test_a_daily_series_is_never_carried(snaps):
    """The item's own line: a stale 10Y is a different claim."""
    snaps("2026-09-21", {"treasury_10y": _entry(4.11, "2026-09-19", "daily")})
    data: dict = {}

    assert fred_data.carry_forward(data, ["treasury_10y"], date(2026, 9, 22),
                                   directory=snaps.dir) == []
    assert data == {}


def test_the_window_is_seven_days(snaps):
    snaps("2026-09-14", {"cpi": _entry(315.0, "2026-08-01", "monthly")})

    inside: dict = {}
    assert fred_data.carry_forward(inside, ["cpi"], date(2026, 9, 21),
                                   directory=snaps.dir) == ["cpi"]
    outside: dict = {}
    assert fred_data.carry_forward(outside, ["cpi"], date(2026, 9, 22),
                                   directory=snaps.dir) == []


def test_the_newest_snapshot_in_the_window_wins(snaps):
    snaps("2026-09-18", {"cpi": _entry(314.0, "2026-07-01", "monthly")})
    snaps("2026-09-21", {"cpi": _entry(315.0, "2026-08-01", "monthly")})
    data: dict = {}

    fred_data.carry_forward(data, ["cpi"], date(2026, 9, 22), directory=snaps.dir)
    assert data["cpi"]["carried_from"] == "2026-09-21"


def test_a_future_snapshot_is_never_read(snaps):
    """No look-ahead: a carried value is strictly backward-looking, which is
    why `test_point_in_time.py` is unaffected by any of this."""
    snaps("2026-09-23", {"cpi": _entry(316.0, "2026-09-01", "monthly")})
    data: dict = {}

    assert fred_data.carry_forward(data, ["cpi"], date(2026, 9, 22),
                                   directory=snaps.dir) == []


def test_a_present_series_is_left_alone(snaps):
    snaps("2026-09-21", {"cpi": _entry(315.0, "2026-08-01", "monthly")})
    data = {"cpi": _entry(316.0, "2026-09-01", "monthly")}

    assert fred_data.carry_forward(data, ["cpi"], date(2026, 9, 22),
                                   directory=snaps.dir) == []
    assert data["cpi"]["value"] == 316.0
    assert "carried_forward" not in data["cpi"]


def test_the_frequency_comes_from_the_snapshot_not_todays_map(snaps):
    """Reclassifying a series later must not retroactively license a carry
    that was not allowed when the snapshot was written."""
    snaps("2026-09-21", {"treasury_10y": _entry(4.11, "2026-09-19", "daily")})
    data: dict = {}

    assert fred_data.carry_forward(data, ["treasury_10y"], date(2026, 9, 22),
                                   directory=snaps.dir) == []


# ---------------------------------------------------------------------------
# How it is marked
# ---------------------------------------------------------------------------

def test_a_carried_value_is_marked_and_restaled(snaps):
    snaps("2026-09-21", {"fed_funds_rate": _entry(4.33, "2026-09-01", "monthly")})
    data: dict = {}

    fred_data.carry_forward(data, ["fed_funds_rate"], date(2026, 9, 22),
                            directory=snaps.dir)
    e = data["fed_funds_rate"]
    assert e["carried_forward"] is True
    assert e["carried_from"] == "2026-09-21"
    # staleness is against the RUN's date and the observation, not the snapshot
    assert e["days_stale"] == (date(2026, 9, 22) - date(2026, 9, 1)).days


def test_the_snapshot_never_records_a_carried_entry(tmp_path):
    """The window has to be measured from a value that was really fetched —
    otherwise a week-long outage carries indefinitely, one day at a time."""
    data = {
        "cpi": _entry(315.0, "2026-08-01", "monthly"),
        "fed_funds_rate": {**_entry(4.33, "2026-09-01", "monthly"),
                           "carried_forward": True, "carried_from": "2026-09-21"},
    }
    path = fred_data.write_fred_snapshot(data, date(2026, 9, 22), directory=tmp_path)
    written = json.loads(path.read_text())["series"]

    assert set(written) == {"cpi"}


def test_a_carry_cannot_chain_past_the_window(snaps):
    """Day 1 carries from a real snapshot; each later day re-reads that same
    real snapshot, so the window bites on schedule rather than sliding."""
    snaps("2026-09-21", {"cpi": _entry(315.0, "2026-08-01", "monthly")})
    for day, expected in ((date(2026, 9, 28), ["cpi"]), (date(2026, 9, 29), [])):
        data: dict = {}
        carried = fred_data.carry_forward(data, ["cpi"], day, directory=snaps.dir)
        assert carried == expected, day
        if carried:
            fred_data.write_fred_snapshot(data, day, directory=snaps.dir)


def test_a_corrupt_snapshot_is_skipped_not_fatal(snaps):
    (snaps.dir / "2026-09-21.json").write_text("{not json", encoding="utf-8")
    snaps("2026-09-18", {"cpi": _entry(315.0, "2026-08-01", "monthly")})
    data: dict = {}

    assert fred_data.carry_forward(data, ["cpi"], date(2026, 9, 22),
                                   directory=snaps.dir) == ["cpi"]


def test_no_snapshot_directory_is_not_an_error(tmp_path):
    data: dict = {}
    assert fred_data.carry_forward(data, ["cpi"], date(2026, 9, 22),
                                   directory=tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# validate_data — what "critical" now means
# ---------------------------------------------------------------------------

@pytest.fixture
def market():
    return {"sp500": {}, "vix": {}, "gold": {}}


@pytest.fixture
def _snapshot_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(fred_data, "FRED_SNAPSHOT_DIR", tmp_path)
    return tmp_path


def test_validate_carries_rather_than_aborting(_snapshot_dir, market, capsys):
    """The 2026-09-22 failure, replayed: `fed_funds_rate` absent, everything
    else present, a snapshot from the day before."""
    (_snapshot_dir / "2026-09-21.json").write_text(json.dumps({
        "asof": "2026-09-21",
        "series": {"fed_funds_rate": _entry(4.33, "2026-09-01", "monthly")},
    }), encoding="utf-8")
    data = {"treasury_10y": _entry(4.11, "2026-09-19", "daily"),
            "cpi": _entry(315.0, "2026-08-01", "monthly")}

    ca.validate_data(data, market, asof=date(2026, 9, 22))   # must not SystemExit

    assert data["fed_funds_rate"]["carried_forward"] is True
    out = capsys.readouterr().out
    assert "carried forward" in out


def test_validate_still_aborts_when_there_is_nothing_to_carry(_snapshot_dir, market):
    data = {"treasury_10y": _entry(4.11, "2026-09-19", "daily"),
            "cpi": _entry(315.0, "2026-08-01", "monthly")}

    with pytest.raises(SystemExit):
        ca.validate_data(data, market, asof=date(2026, 9, 22))


def test_validate_still_aborts_on_a_missing_daily_critical(_snapshot_dir, market):
    """`treasury_10y` is critical and uncarryable — its absence still costs the
    note, deliberately."""
    (_snapshot_dir / "2026-09-21.json").write_text(json.dumps({
        "asof": "2026-09-21",
        "series": {"treasury_10y": _entry(4.11, "2026-09-19", "daily")},
    }), encoding="utf-8")
    data = {"fed_funds_rate": _entry(4.33, "2026-09-01", "monthly"),
            "cpi": _entry(315.0, "2026-08-01", "monthly")}

    with pytest.raises(SystemExit):
        ca.validate_data(data, market, asof=date(2026, 9, 22))


def test_validate_still_aborts_on_missing_market_data(_snapshot_dir):
    data = {k: _entry(1.0, "2026-09-01", "monthly") for k in ca._CRITICAL_FRED}
    with pytest.raises(SystemExit):
        ca.validate_data(data, {"sp500": {}}, asof=date(2026, 9, 22))


def test_a_clean_day_is_unchanged(_snapshot_dir, market, capsys):
    data = {k: _entry(1.0, "2026-09-22", "monthly") for k in ca._CRITICAL_FRED}
    ca.validate_data(data, market, asof=date(2026, 9, 22))

    assert not any(v.get("carried_forward") for v in data.values())
    assert "core data integrity check passed" in capsys.readouterr().out


def test_validate_takes_the_runs_date_and_never_the_clock(_snapshot_dir, market):
    """ADR-0013: the date is resolved once by `plan` and passed down. A carry
    window read off the wall clock would drift on a late run."""
    (_snapshot_dir / "2026-09-14.json").write_text(json.dumps({
        "asof": "2026-09-14",
        "series": {"fed_funds_rate": _entry(4.33, "2026-09-01", "monthly")},
    }), encoding="utf-8")
    data = {"treasury_10y": _entry(4.11, "2026-09-19", "daily"),
            "cpi": _entry(315.0, "2026-08-01", "monthly")}

    # 2026-09-21 is inside the window from 09-14; today (09-22) is not
    ca.validate_data(data, market, asof=date(2026, 9, 21))
    assert data["fed_funds_rate"]["carried_from"] == "2026-09-14"
