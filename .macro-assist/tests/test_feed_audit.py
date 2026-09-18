"""
Tests for feed_audit.py (IMP-5.4) — the fragility monitor's feed gate.

The thing under test is a detector, so the tests are mostly about when it goes
red and when it must not. The fixture that matters is the one copied out of the
real quant log: `test_the_september_2026_outage_goes_red_on_day_three` replays
2026-09-14 → 09-18 exactly as `results/quant_context_log/` recorded it — two
healthy readings, then three degraded ones — and asserts the gate would have
fired on the 18th. That run is the reason this file exists.

Pure unit tests — the log directory is a tmp_path, nothing touches the network.

Run:
    pytest .macro-assist/tests/test_feed_audit.py -v
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from feed_audit import audit, degraded_streak, read_log


def _write(log_dir, day: str, *, degraded=(), label="Normal", detail=None, feed=None,
           extra_lines=0):
    """One day's quant-log file, in the shape collect_and_analyze.py writes."""
    log_dir.mkdir(parents=True, exist_ok=True)
    frag = {"composite": 24.0, "label": label, "trend": "Falling",
            "components": {"variance_trend": 23.0}, "weights": {"variance_trend": 0.9},
            "degraded": list(degraded), "mode": "log"}
    if detail:
        frag["degraded_detail"] = detail
    if feed:
        frag["feed"] = feed
    rec = {"date": day, "time": "06:04:00", "fragility": frag}
    path = log_dir / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for _ in range(extra_lines):
            fh.write(json.dumps({"date": day, "fragility": {**frag, "label": "STALE-RERUN",
                                                            "degraded": []}}) + "\n")
        fh.write(json.dumps(rec) + "\n")
    return path


# ---------------------------------------------------------------------------
# Reading the log back
# ---------------------------------------------------------------------------

def test_read_log_is_empty_when_there_is_no_log(tmp_path):
    assert read_log(tmp_path / "nothing") == []
    assert audit(tmp_path / "nothing")[0] == 0


def test_read_log_orders_oldest_first_and_skips_junk(tmp_path):
    log = tmp_path / "quant_context_log"
    _write(log, "2026-09-16")
    _write(log, "2026-09-14")
    (log / "not-a-date.jsonl").write_text("{}\n", encoding="utf-8")
    (log / "2026-09-15.jsonl").write_text("{not json}\n", encoding="utf-8")
    assert [r.day for r in read_log(log)] == [date(2026, 9, 14), date(2026, 9, 16)]


def test_a_rerun_days_last_line_is_that_days_reading(tmp_path):
    # The pipeline appends; a day run twice has two lines and the later one is
    # the reading that stands.
    log = tmp_path / "quant_context_log"
    _write(log, "2026-09-18", degraded=["vix_term"], label="Unavailable", extra_lines=1)
    (reading,) = read_log(log)
    assert reading.label == "Unavailable" and reading.degraded == ["vix_term"]


def test_asof_ignores_later_readings(tmp_path):
    # The pipeline pins the run's date (ADR-0013); a late run must not audit a
    # day it is not for.
    log = tmp_path / "quant_context_log"
    _write(log, "2026-09-17", degraded=["vix_term"], label="Unavailable")
    _write(log, "2026-09-18", degraded=["vix_term"], label="Unavailable")
    assert len(read_log(log, asof=date(2026, 9, 17))) == 1
    assert audit(log, asof=date(2026, 9, 17), max_streak=2)[0] == 0
    assert audit(log, asof=date(2026, 9, 18), max_streak=1)[0] == 1


# ---------------------------------------------------------------------------
# The streak, and where it goes red
# ---------------------------------------------------------------------------

def test_a_healed_streak_is_history_not_a_failure(tmp_path):
    log = tmp_path / "quant_context_log"
    for day in ("2026-09-14", "2026-09-15", "2026-09-16"):
        _write(log, day, degraded=["vix_term"], label="Unavailable")
    _write(log, "2026-09-17")                      # feed came back
    assert degraded_streak(read_log(log)) == []
    code, lines = audit(log)
    assert code == 0
    assert any("healthy" in msg for _, _, msg in lines)


def test_one_degraded_day_is_a_warn_not_a_failure(tmp_path):
    log = tmp_path / "quant_context_log"
    _write(log, "2026-09-15")
    _write(log, "2026-09-16", degraded=["vix_term"], label="Unavailable")
    code, lines = audit(log, max_streak=2)
    assert code == 0
    assert [lvl for _, lvl, _ in lines][0] == "WARN"
    assert any("within tolerance" in msg for _, _, msg in lines)


def test_the_streak_goes_red_once_it_passes_the_threshold(tmp_path):
    log = tmp_path / "quant_context_log"
    for day in ("2026-09-16", "2026-09-17", "2026-09-18"):
        _write(log, day, degraded=["vix_term"], label="Unavailable")
    assert audit(log, max_streak=3)[0] == 0        # exactly at tolerance
    code, lines = audit(log, max_streak=2)
    assert code == 1
    assert any(lvl == "FAIL" for _, lvl, _ in lines)
    # The failure says since when, so the fix does not start with a log dig.
    assert any("2026-09-16" in msg for _, _, msg in lines)


def test_the_september_2026_outage_goes_red_on_day_three(tmp_path):
    """Replay of results/quant_context_log/2026-09-14 → 09-18 as it happened:
    Resilient, Resilient, then three Unavailable readings with `vix_term`
    missing. Every check was green at the time and a human caught it on the
    third day. At the shipped threshold the 18th is red."""
    log = tmp_path / "quant_context_log"
    _write(log, "2026-09-14", label="Resilient")
    _write(log, "2026-09-15", label="Resilient")
    for day in ("2026-09-16", "2026-09-17", "2026-09-18"):
        _write(log, day, degraded=["vix_term"], label="Unavailable")

    assert audit(log, asof=date(2026, 9, 15))[0] == 0    # nothing wrong yet
    assert audit(log, asof=date(2026, 9, 16))[0] == 0    # one bad day — WARN only
    assert audit(log, asof=date(2026, 9, 17))[0] == 0    # two — still tolerated
    assert audit(log, asof=date(2026, 9, 18))[0] == 1    # three — red


# ---------------------------------------------------------------------------
# What the failure tells you
# ---------------------------------------------------------------------------

def test_the_report_carries_the_recorded_cause(tmp_path):
    log = tmp_path / "quant_context_log"
    for day in ("2026-09-16", "2026-09-17", "2026-09-18"):
        _write(log, day, degraded=["vix_term"], label="Unavailable",
               detail={"vix_term": "vix3m series absent"},
               feed={"vix3m": {"source": "none", "stale_obs": None, "last": None,
                               "error": "HTTPError: 403"}})
    code, lines = audit(log, max_streak=2)
    assert code == 1
    blob = " ".join(msg for _, _, msg in lines)
    assert "vix3m series absent" in blob and "403" in blob


def test_a_reading_from_before_the_cause_was_recorded_says_so(tmp_path):
    log = tmp_path / "quant_context_log"
    for day in ("2026-09-16", "2026-09-17", "2026-09-18"):
        _write(log, day, degraded=["vix_term"], label="Unavailable")
    _code, lines = audit(log, max_streak=2)
    assert any("cause not recorded" in msg for _, _, msg in lines)


@pytest.mark.parametrize("bad", ["", "[]\n", '{"fragility": "not a dict"}\n'])
def test_a_detector_that_crashes_detects_nothing(tmp_path, bad):
    log = tmp_path / "quant_context_log"
    log.mkdir(parents=True)
    (log / "2026-09-18.jsonl").write_text(bad, encoding="utf-8")
    assert read_log(log) == []
    assert audit(log)[0] == 0


# ---------------------------------------------------------------------------
# --probe: the same diagnosis, live, without waiting for tomorrow's run.
# Network is monkeypatched out — what is under test is the report, not yfinance.
# ---------------------------------------------------------------------------

def _patch_probe(monkeypatch, histories, report):
    import quant_context
    monkeypatch.setattr(quant_context, "_fetch_fragility_histories",
                        lambda *a, **k: histories)
    monkeypatch.setattr(quant_context, "vol_feed_report", lambda: report)


def test_probe_is_green_when_the_term_structure_computes(monkeypatch):
    import pandas as pd
    from feed_audit import probe

    idx = pd.date_range("2026-08-01", periods=40, freq="B")
    histories = {"sp500": pd.Series(1.0, index=idx), "vix": pd.Series(20.0, index=idx),
                 "vix3m": pd.Series(21.0, index=idx)}
    _patch_probe(monkeypatch, histories,
                 {"vix3m": {"source": "yfinance", "stale_obs": 0,
                            "last": str(idx[-1].date()), "error": None}})
    code, lines = probe()
    assert code == 0
    assert any("vix_term computes" in msg for _, _, msg in lines)


def test_probe_names_the_dead_leg_and_the_fallbacks_error(monkeypatch):
    import pandas as pd
    from feed_audit import probe

    idx = pd.date_range("2026-08-01", periods=40, freq="B")
    histories = {"sp500": pd.Series(1.0, index=idx), "vix": pd.Series(20.0, index=idx)}
    _patch_probe(monkeypatch, histories,
                 {"vix3m": {"source": "none", "stale_obs": None, "last": None,
                            "error": "HTTPError: HTTP Error 403: Forbidden"}})
    code, lines = probe()
    assert code == 1
    blob = " ".join(msg for _, _, msg in lines)
    assert "403" in blob                      # why the fallback did not fill it
    assert "vix3m series absent" in blob      # and what that cost


def test_probe_reports_a_dead_fetch_rather_than_crashing(monkeypatch):
    from feed_audit import probe
    _patch_probe(monkeypatch, {}, {})
    code, lines = probe()
    assert code == 1
    assert any(lvl == "FAIL" for _, lvl, _ in lines)
