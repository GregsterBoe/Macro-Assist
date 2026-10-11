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


# ---------------------------------------------------------------------------
# H-010 (ADR-0025): the contribution rule on the same inputs
# ---------------------------------------------------------------------------

def test_h010_is_the_entrys():
    assert (er.LOW, er.HIGH, er.WINDOW, er.FORWARD_MONTHS) == (0.75, 2.0, 20, 12)
    assert er.SPEC_H010["class"] == "flow_rule" and er.SPEC_H010["arm"] == er.ARM_H010
    assert er.SPEC_H010["clauses"] == [{"kind": "forward_contrast", "signal": er.SIGNAL,
                                        "window": 20, "months": 12}]


def test_a_firing_doubles_the_contribution_for_twenty_days():
    f = np.zeros(60, bool)
    f[10] = True
    m = er.contribution_multiple(f)
    assert (m[:10] == 0.75).all() and (m[10:30] == 2.0).all() and (m[30:] == 0.75).all()


def test_the_flow_path_is_h009s_calendar_with_the_multiple_and_a_complete_last_month():
    inputs = {k: (er.before_seal(v) if k != "fetched" else v) for k, v in _inputs().items()}
    flag = er.pit_or(_fake_channels(inputs["industries"]))
    risk, flow = er.build_path(inputs, flag), er.build_flow_path(inputs, flag)
    assert flow["dates"] == risk["dates"] and np.allclose(flow["equity"], risk["equity"])
    assert flow["last_month_complete"] and flow["dates"][-1] < "2018-01-01"
    assert set(np.unique(flow["multiple"])) <= {0.75, 2.0}


def test_an_h010_look_is_exploratory_and_leaves_h009s_report_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_inputs", _inputs)
    monkeypatch.setattr(er, "panel_channels", _fake_channels)
    result = er.run(tmp_path, member="h010")
    assert result["verdict"] == "exploratory" and result["class"] == "flow_rule"
    assert not (tmp_path / "report.md").exists()
    report = (tmp_path / "report_h010.md").read_text()
    assert "Verdict: **exploratory**" in report and "dip_matched" in report
    rec = json.loads((tmp_path / er.RUN_LOG).read_text().splitlines()[-1])
    assert rec["arms"] == [er.ARM_H010]


def test_an_h010_dry_run_reads_no_rule(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_inputs", _inputs)
    monkeypatch.setattr(er, "panel_channels", _fake_channels)
    monkeypatch.setattr(cb, "read", lambda *a, **k: pytest.fail("a dry run read the rule"))
    info = er.dry_run(tmp_path, member="h010")
    assert info["balance_share"] == pytest.approx(0.2) and 0 <= info["share_high_months"] <= 1
    assert not (tmp_path / er.RUN_LOG).exists()


# ---------------------------------------------------------------------------
# H-011 (ADR-0026): three holdings in euros, monthly
# ---------------------------------------------------------------------------

def test_h011_is_the_entrys():
    assert er.MIX_TARGETS == {"equity": 0.70, "bonds": 0.20, "gold": 0.10}
    assert er.SPEC_H011["clauses"] == [{"kind": "late_control", "from_month": 61, "max_ratio": 0.75}]
    assert er.ARM_H011 == "h011_fill_gaps" and er.MIX_START == "1972-12"


def test_filling_gaps_invests_everything_and_only_below_target():
    w = np.array([0.7, 0.2, 0.1])
    V = np.array([[0.0, 0.0, 0.0], [80.0, 10.0, 10.0], [70.0, 20.0, 10.0]])
    x = er.fill_gaps(V, w)
    assert np.allclose(x.sum(axis=1), 1.0) and (x >= 0).all()
    assert np.allclose(x[0], w)                       # an empty account buys the mix
    assert x[1, 0] == 0.0 and x[1, 1] > x[1, 2] > 0   # equity is over target; bonds furthest under
    assert np.allclose(x[2], w)                       # on target: the mix


def test_a_bond_held_at_an_unchanged_yield_earns_its_coupon():
    assert er.bond_return(0.06, 0.06) == pytest.approx(0.005)
    assert er.bond_return(0.0, 0.0) == pytest.approx(0.0)
    assert er.bond_return(0.05, 0.06) < 0 < er.bond_return(0.06, 0.05)


def _mix_inputs(last="2019-06"):
    """A synthetic stand-in for the monthly series and the daily factors,
    running past the seal — so the cut is tested."""
    rng = np.random.default_rng(5)
    ms = pd.date_range("1970-01-01", last + "-01", freq="MS")
    days = pd.bdate_range("1970-01-01", pd.Timestamp(last + "-01") + pd.offsets.MonthEnd(0))
    fac = pd.DataFrame({"Mkt-RF": rng.normal(0.0003, 0.01, len(days)), "RF": np.full(len(days), 0.0001)},
                       index=days)
    dem = pd.Series(2.0 + 0.1 * np.sin(np.arange(len(ms)) / 12), index=ms)
    dem = dem[dem.index < "2002-01-01"]
    eur = pd.Series(er.DEM_PER_EUR / (2.0 + 0.1 * np.sin(np.arange(len(ms)) / 12)), index=ms)
    eur = eur[eur.index >= "1999-01-01"]
    return {"factors": fac, "gold_usd": pd.Series(300 * np.exp(np.cumsum(rng.normal(0, 0.04, len(ms)))), index=ms),
            "bund_10y": pd.Series(6 + np.cumsum(rng.normal(0, 0.1, len(ms))).clip(-5, 5), index=ms),
            "dem_per_usd": dem, "usd_per_eur": eur, "fetched": "test"}


def test_h011_inputs_are_cut_at_the_seal_on_arrival(monkeypatch, tmp_path):
    raw = _mix_inputs()
    monkeypatch.setattr(er, "fetch_mix_inputs", lambda: raw)
    got = er._inputs(tmp_path, cached=False, member="h011")
    for k, v in got.items():
        if k != "fetched":
            assert v.index[-1] < pd.Timestamp("2018-01-01"), k
    assert (tmp_path / "inputs_h011.pkl").exists() and not (tmp_path / "inputs.pkl").exists()


def test_the_mix_path_is_in_euros_from_1973_and_stops_before_the_seal():
    inputs = {k: (er.before_seal(v) if k != "fetched" else v) for k, v in _mix_inputs().items()}
    path = er.build_mix_path(inputs)
    assert path["months"][0] == "1973-01" and path["months"][-1] == "2017-12"
    lv = er.mix_levels(inputs)
    fx = er.usd_per_eur(inputs).reindex(lv.index)
    fac = inputs["factors"]
    jan = fac[(fac.index >= "1973-01-01") & (fac.index < "1973-02-01")]
    usd = float((1 + jan["Mkt-RF"] + jan["RF"]).prod() - 1)
    assert path["returns"]["equity"][0] == pytest.approx((1 + usd) * fx.iloc[0] / fx.iloc[1] - 1)


def test_the_two_dollar_rates_are_spliced_at_the_euro():
    inputs = _mix_inputs()
    fx = er.usd_per_eur(inputs)
    assert fx["1998-12-01"] == pytest.approx(er.DEM_PER_EUR / inputs["dem_per_usd"]["1998-12-01"])
    assert fx["1999-01-01"] == pytest.approx(inputs["usd_per_eur"]["1999-01-01"])


def test_a_gap_in_a_series_or_a_rate_mismatch_stops_the_errand():
    inputs = {k: (er.before_seal(v) if k != "fetched" else v) for k, v in _mix_inputs().items()}
    holed = dict(inputs, gold_usd=inputs["gold_usd"].drop(pd.Timestamp("1990-05-01")))
    with pytest.raises(ValueError, match="gold lacks"):
        er.check_mix_inputs(holed)
    off = dict(inputs, usd_per_eur=inputs["usd_per_eur"] * 1.05)
    with pytest.raises(ValueError, match="disagree"):
        er.check_mix_inputs(off)


def test_an_h011_look_is_exploratory_and_leaves_the_others_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_mix_inputs", _mix_inputs)
    monkeypatch.setattr(cb, "N_BOOT", 20)
    result = er.run(tmp_path, member="h011")
    assert result["verdict"] == "exploratory" and result["summary"]["last_month"] == "2017-12"
    report = (tmp_path / "report_h011.md").read_text()
    assert "Verdict: **exploratory**" in report and "sell-back" in report
    assert not (tmp_path / "report.md").exists() and not (tmp_path / "report_h010.md").exists()
    rec = json.loads((tmp_path / er.RUN_LOG).read_text().splitlines()[-1])
    assert rec["arms"] == [er.ARM_H011] and rec["first_date"] == "1973-01" and rec["last_date"] == "2017-12"


def test_an_h011_dry_run_walks_no_leg(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "fetch_mix_inputs", _mix_inputs)
    monkeypatch.setattr(cb, "read", lambda *a, **k: pytest.fail("a dry run read the rule"))
    monkeypatch.setattr(cb, "mix_summary", lambda *a, **k: pytest.fail("a dry run walked a leg"))
    info = er.dry_run(tmp_path, member="h011")
    assert info["n_plans"] == 36 and info["last_month"] == "2017-12"
    assert not (tmp_path / er.RUN_LOG).exists()
