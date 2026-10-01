"""The explore-tier risk-rule harness (ADR-0023, H-009). What it must never do:
read a day on the sealed side, tune anything, or return more than
`exploratory`. What it must do: the member exactly as the entry fixes it, and
a receipt for every look."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

import class_bars as cb
import explore_rules as er
import fragility_or as fo


def test_the_member_is_the_entrys():
    assert (er.CUT, er.HOLD) == (0.5, 20)
    assert er.CHANNELS == ("AR", "TURB")                          # the composite left out, on purpose
    assert (fo._Q, fo._COV_AR, fo._COV_TURB, fo._SHRINK, fo._SMOOTH, fo._STRIDE, fo._MIN_WARMUP) == \
        (0.90, 120, 252, 0.2, 5, 5, 252)                          # fragility_or's, unchanged
    assert er.SPEC["class"] == "risk_rule" and er.SPEC["clauses"][0]["signal"] == er.SIGNAL
    assert er.SPEC["clauses"][0]["before_peak"] == er.HOLD - 1 == 19       # resolved.md #35
    assert er.SEAL_START == date(2018, 1, 1)


def test_a_firing_holds_half_for_twenty_days_and_rearms():
    f = np.zeros(60, bool)
    f[[5, 30]] = True
    e = er.hold_exposure(f)
    assert (e[:5] == 1).all() and (e[5:25] == 0.5).all() and e[25] == 1.0
    assert (e[30:50] == 0.5).all() and (e[50:] == 1).all()


def _series(vals, start="2000-01-03"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype=float)


def test_the_flag_is_point_in_time_and_waits_for_its_warm_up():
    rng = np.random.default_rng(0)
    ar, tu = _series(rng.normal(size=400)), _series(rng.normal(size=400))
    ar.iloc[350] = 50.0
    flag = er.pit_or({"AR": ar, "TURB": tu}, q=0.9, min_warmup=252)
    assert flag.index[0] == ar.index[252]                        # nothing read before the warm-up
    assert flag[ar.index[350]]
    # a reading never moves its own threshold: the flag on a day is the same with the future cut off
    cut = er.pit_or({"AR": ar.iloc[:300], "TURB": tu.iloc[:300]}, q=0.9, min_warmup=252)
    assert (cut == flag.reindex(cut.index)).all()


def test_either_channel_fires_the_flag():
    base = _series(np.r_[np.linspace(0, 1, 300), 0.5 * np.ones(10)])
    hi = base.copy()
    hi.iloc[305] = 5.0
    assert er.pit_or({"AR": hi, "TURB": base}, min_warmup=252)[hi.index[305]]
    assert er.pit_or({"AR": base, "TURB": hi}, min_warmup=252)[hi.index[305]]
    assert not er.pit_or({"AR": base, "TURB": base}, min_warmup=252)[hi.index[305]]


def _inputs(start="2005-01-03", n=5000):
    """A synthetic stand-in that runs past the seal — so the cut is tested."""
    rng = np.random.default_rng(3)
    idx = pd.bdate_range(start, periods=n)
    fac = pd.DataFrame({"Mkt-RF": rng.normal(0.0003, 0.01, n), "RF": np.full(n, 0.0001)}, index=idx)
    ind = pd.DataFrame(rng.normal(0.0003, 0.01, (n, 3)), index=idx, columns=list("abc"))
    return {"industries": ind, "factors": fac, "fetched": "test"}


def _fake_channels(industries):
    """The real walk is slow and needs the real panel; here a channel that is
    the panel's trailing absolute return, on the strided grid."""
    grid = industries.index[::5]
    x = industries.abs().mean(axis=1).rolling(20).mean().reindex(grid).dropna()
    return {"AR": x, "TURB": x * 0}


def test_inputs_are_cut_at_the_seal_on_arrival(monkeypatch, tmp_path):
    raw = _inputs()
    assert raw["factors"].index[-1] >= pd.Timestamp("2018-01-01")
    monkeypatch.setattr(er, "fetch_inputs", lambda: raw)
    got = er._inputs(tmp_path, cached=False)
    for k in ("industries", "factors"):
        assert got[k].index[-1] < pd.Timestamp("2018-01-01")
    # and a cache written by anyone is cut again on the way in
    (tmp_path / "inputs.pkl").write_bytes(__import__("pickle").dumps(_inputs()))
    assert er._inputs(tmp_path, cached=True)["factors"].index[-1] < pd.Timestamp("2018-01-01")


def test_the_path_starts_on_the_first_readable_flag_and_stops_before_the_seal():
    inputs = {k: (er.before_seal(v) if k != "fetched" else v) for k, v in _inputs().items()}
    flag = er.pit_or(_fake_channels(inputs["industries"]))
    path = er.build_path(inputs, flag)
    assert path["dates"][0] == flag.index[0].date().isoformat()
    assert path["dates"][-1] < "2018-01-01"
    fired_days = {d for d, f in zip(path["dates"], path["signals"][er.SIGNAL]) if f}
    assert fired_days == {d.date().isoformat() for d in flag.index[flag]}   # grid days only
    assert np.allclose(path["equity"], inputs["factors"].loc[pd.to_datetime(path["dates"])].sum(axis=1))


def test_a_look_is_exploratory_writes_its_report_and_a_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_inputs", _inputs)
    monkeypatch.setattr(er, "panel_channels", _fake_channels)
    result = er.run(tmp_path)
    assert result["verdict"] == "exploratory"
    assert result["summary"]["last_date"] < "2018-01-01"
    report = (tmp_path / "report.md").read_text()
    assert "Verdict: **exploratory**" in report and "tax brought forward" in report
    rec = json.loads((tmp_path / er.RUN_LOG).read_text().splitlines()[-1])
    assert rec["arms"] == [er.ARM] and rec["seal"] == "2018-01-01"
    import hashlib
    assert rec["report_sha256"] == hashlib.sha256(report.encode()).hexdigest()
    split = result["alarm_split"]
    assert set(split["pp_per_year"]) == {"followed", "false_alarm", "invested"}


def test_a_dry_run_reads_no_rule_and_leaves_no_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_inputs", _inputs)
    monkeypatch.setattr(er, "panel_channels", _fake_channels)
    monkeypatch.setattr(cb, "read", lambda *a, **k: pytest.fail("a dry run read the rule"))
    info = er.dry_run(tmp_path)
    assert info["last_date"] < "2018-01-01" and not (tmp_path / er.RUN_LOG).exists()


def test_the_alarm_split_adds_up_to_the_whole_gap():
    inputs = {k: (er.before_seal(v) if k != "fetched" else v) for k, v in _inputs().items()}
    path = er.build_path(inputs, er.pit_or(_fake_channels(inputs["industries"])))
    split = er.alarm_split(path)
    legs = cb.risk_legs(cb.RISK_RULE, path, 10.0)
    r = {k: np.diff(np.r_[1.0, legs[k]["value"]]) / np.r_[1.0, legs[k]["value"][:-1]] for k in legs}
    whole = 100 * (r["member"] - r["static_matched"]).sum() / cb._years(path["dates"])
    assert sum(split["pp_per_year"].values()) == pytest.approx(whole, abs=0.01)
