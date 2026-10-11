"""The contribution-rule class bar (ADR-0025). The method §10: a bar is only
exercised by results that reach it, so every disqualifier is driven alone,
ahead of a strong advantage, and planted markets show what passes and what
does not — a rule that saves for the months before a rally passes, plain
buying, holding money back for nothing, and a drawdown rule do not."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

import class_bars as cb
from portfolio import book

F = cb.FLOW_RULE


# ---------------------------------------------------------------------------
# the bar is ADR-0025's as accepted (resolved.md #37)
# ---------------------------------------------------------------------------

def test_the_bar_is_adr_0025s_as_accepted():
    assert F.episode_depth == 0.10 and F.min_episodes == 5           # ADR-0023's, for its reason
    assert F.min_advantage == 0.0025                                  # 0.25 pp a year
    assert F.cost_bps == (book.DEFAULT_COST_BPS, 3 * book.DEFAULT_COST_BPS)
    assert F.interval == 0.90 and F.block_months == 24
    assert F.sealed_from == date(2018, 1, 1) and F.sealed_until is None
    assert (F.rival, F.second_rival) == ("plain", "dip_matched")
    assert cb.BARS["flow_rule"] is F and cb.FLOW_CELL_MIN == 12


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------

def test_month_ends_are_the_last_day_of_each_month_and_the_final_one_only_when_complete():
    dates = ["2018-01-30", "2018-01-31", "2018-02-01", "2018-02-28", "2018-03-01", "2018-03-02"]
    assert list(cb.flow_months(dates, False)) == [1, 3]
    assert list(cb.flow_months(dates, True)) == [1, 3, 5]


def test_dip_matched_keeps_the_members_multiples_and_gives_the_largest_to_the_deepest():
    m = np.array([0.75, 2.0, 0.75, 0.75, 2.0, 0.75])
    dd = np.array([0.0, 0.02, 0.30, 0.05, 0.0, 0.12])
    got = cb.dip_matched(m, dd)
    assert sorted(got) == sorted(m)
    assert list(got) == [0.75, 0.75, 2.0, 0.75, 0.75, 2.0]


def test_the_money_weighted_return_of_a_flat_plan_is_zero_and_of_a_rate_is_that_rate():
    assert cb.money_weighted_return(np.array([12.0]), 12)[0] == pytest.approx(0.0, abs=1e-9)
    x = 1.01 ** (1 / 12) - 1                                          # 1% a year, monthly
    w = sum((1 + x) ** (12 - k) for k in range(1, 13))
    assert cb.money_weighted_return(np.array([w]), 12)[0] == pytest.approx(0.01, abs=1e-8)


def _flat(n_months=6, eq=0.0, cash=0.0, start="2018-01"):
    days = []
    for k in range(n_months):
        m = np.datetime64(start, "M") + np.timedelta64(k, "M")
        d = np.arange(np.datetime64(m, "D"), np.datetime64(m + np.timedelta64(1, "M"), "D"))
        days += [str(x) for x in d if np.is_busday(x)]
    n = len(days)
    return {"dates": days, "equity": np.full(n, eq), "cash": np.full(n, cash),
            "last_month_complete": True}


def _run(path, multiples_at_ends, cost=0.0, track=True):
    ends = cb.flow_months(path["dates"], True)
    seg = cb._segments(np.asarray(path["equity"]), np.asarray(path["cash"]), ends)
    nm = len(ends) - 1
    return cb._wealth(seg, np.arange(nm)[None, :], np.asarray(multiples_at_ends, float)[None, :nm],
                      cost, track=track)


def test_every_euro_paid_in_is_in_the_account_and_none_is_borrowed():
    p = _flat(8)
    w = _run(p, [2.0] * 8)                                            # asks for more than it has
    assert w["wealth"][0] == pytest.approx(8.0)                       # no returns: wealth = contributions
    assert (w["reserve"][0] >= -1e-12).all()
    assert w["bought"][0].sum() <= 7.0 + 1e-12                        # the 8th contribution is not yet invested
    assert w["starved"][0][1:].all()


def test_held_back_money_waits_in_the_reserve_and_earns_cash():
    p = _flat(4, eq=0.0, cash=0.001)
    w = _run(p, [0.0] * 4)                                            # never invests
    assert w["bought"][0].sum() == 0
    assert w["wealth"][0] > 4.0 and w["reserve_end"][0] == pytest.approx(w["wealth"][0])


def test_a_purchase_is_made_at_the_next_close_and_misses_that_days_return():
    p = _flat(2)
    ends = cb.flow_months(p["dates"], True)
    eq = np.zeros(len(p["dates"]))
    eq[ends[0] + 1] = 0.10                                             # the first day after the month-end
    p["equity"] = eq
    w = _run(p, [1.0, 1.0])
    assert w["wealth"][0] == pytest.approx(2.0)                       # bought at that day's close, after the rise


def test_costs_are_paid_on_what_is_bought():
    p = _flat(5)
    free, paid = _run(p, [1.0] * 5, 0.0), _run(p, [1.0] * 5, 10.0)
    assert paid["wealth"][0] == pytest.approx(free["wealth"][0] - 4 * 0.001)


def test_the_bootstrap_draws_whole_blocks_of_consecutive_months():
    idx = cb._boot_idx(100, 24, 50, seed=1)
    assert idx.shape == (50, 100)
    for row in idx:
        for b in range(0, 96, 24):
            blk = row[b:b + 24]
            assert (np.diff(blk) == 1).all()


@pytest.mark.parametrize("over, sealed, msg", [
    ({"dates": None}, True, "sealed side"),
    ({}, False, "stops before the seal"),
    ({"multiple": -1.0}, True, "at least zero"),
])
def test_a_malformed_or_misplaced_path_is_refused(over, sealed, msg):
    p = {**_flat(3), "multiple": np.ones(len(_flat(3)["dates"]))}
    if "dates" in over:
        p = {**_flat(3, start="2017-11"), "multiple": np.ones(len(_flat(3, start="2017-11")["dates"]))}
    if "multiple" in over:
        p["multiple"] = np.full(len(p["dates"]), over["multiple"])
    with pytest.raises(cb.PreregError, match=msg):
        cb.flow_summary(F, p, "x", sealed=sealed, n_boot=10)


# ---------------------------------------------------------------------------
# the verdict, each stage driven alone
# ---------------------------------------------------------------------------

def _summary(**over):
    """A summary that clears everything: a large advantage over both rivals."""
    s = {"n_episodes": 8, "advantage": {"10.0": 0.010, "30.0": 0.009},
         "advantage_ci": {"lo": 0.004, "hi": 0.016}, "advantage_vs_dip": 0.004}
    s.update(over)
    return s


_HELD = [{"kind": "forward_contrast", "passed": True, "detail": "", "cells": []}]
_FAILED = [{"kind": "forward_contrast", "passed": False, "detail": "no", "cells": []}]


def _v(summary=None, clauses=_HELD, sealed=True, floor=None):
    return cb.flow_verdict(F, summary or _summary(), clauses, sealed=sealed, floor=floor)["verdict"]


def test_everything_cleared_is_an_edge():
    assert _v() == "edge"


@pytest.mark.parametrize("over, clauses, expected", [
    ({"n_episodes": 4}, _HELD, "underpowered"),
    ({"advantage": {"10.0": -0.0001, "30.0": -0.0002}}, _HELD, "inverted"),
    ({"advantage": {"10.0": 0.0024, "30.0": 0.0023}}, _HELD, "no_edge"),
    ({"advantage": {"10.0": 0.0030, "30.0": 0.0024}}, _HELD, "no_edge"),          # at three times the cost
    ({"advantage_ci": {"lo": 0.0, "hi": 0.02}}, _HELD, "no_edge"),                # interval touches zero
    ({"advantage_vs_dip": 0.0}, _HELD, "explained_by_rival"),
    ({}, _FAILED, "unexplained"),
    ({}, [], "unexplained"),
])
def test_each_stage_fires_on_its_own_ahead_of_a_strong_advantage(over, clauses, expected):
    assert _v(_summary(**over), clauses) == expected


def test_a_disqualifier_fires_even_when_every_later_stage_would_fail_too():
    worst = _summary(n_episodes=2, advantage={"10.0": -0.05, "30.0": -0.05},
                     advantage_ci={"lo": -0.1, "hi": 0.0}, advantage_vs_dip=-1)
    assert _v(worst, _FAILED) == "underpowered"
    assert _v(_summary(advantage={"10.0": -0.05, "30.0": -0.05}, advantage_vs_dip=-1), _FAILED) == "inverted"


def test_an_unsealed_read_is_exploratory_whatever_it_shows():
    assert _v(sealed=False) == "exploratory"


def test_an_entry_floor_tightens_the_episode_count():
    assert _v(_summary(n_episodes=6), floor={"episodes": 7}) == "underpowered"


def test_every_flow_verdict_is_reachable_and_named():
    seen = {_v(sealed=False), _v(_summary(n_episodes=1)),
            _v(_summary(advantage={"10.0": -1, "30.0": -1})),
            _v(_summary(advantage={"10.0": 0.001, "30.0": 0.001})),
            _v(_summary(advantage_vs_dip=-1)), _v(clauses=_FAILED), _v()}
    assert seen == set(cb.FLOW_VERDICTS)


# ---------------------------------------------------------------------------
# planted markets: what passes and what does not
# ---------------------------------------------------------------------------

def _market(seed=0, n_months=240, p_rally=0.25):
    """Months of three kinds, i.i.d.: a rally (~+13%), a fall (~−8%) and a
    quiet drift, on business days from 2018-01 — the sealed side. Returns the
    path and each month's kind (0 = rally)."""
    rng = np.random.default_rng(seed)
    kinds = rng.choice(3, size=n_months, p=[p_rally, 0.30, 0.70 - p_rally])
    mu = np.array([0.006, -0.004, 0.0005])[kinds]
    p = _flat(n_months)
    ym = np.array([d[:7] for d in p["dates"]])
    months = sorted(set(ym))
    eq = np.empty(len(ym))
    for k, m in enumerate(months):
        i = ym == m
        eq[i] = rng.normal(mu[k], 0.006, i.sum())
    return {**p, "equity": eq, "cash": np.full(len(ym), 0.00005)}, kinds, ym, months


def _member(path, ym, months, high_months, low=0.0, high=12.0):
    """`high` on every day of a month in `high_months`, `low` otherwise; the
    signal fires on those days."""
    m = np.full(len(ym), low)
    for k in high_months:
        m[ym == months[k]] = high
    return {**path, "multiple": m, "signals": {"flag": m > low}}


SPEC = cb.validate({"class": "flow_rule", "arm": "oracle",
                    "clauses": [{"kind": "forward_contrast", "signal": "flag", "window": 1, "months": 1}]})


@pytest.fixture(scope="module")
def planted():
    path, kinds, ym, months = _market()
    before_rally = [k for k in range(len(months) - 1) if kinds[k + 1] == 0]
    return path, kinds, ym, months, before_rally


def test_a_rule_that_saves_for_the_month_before_a_rally_reads_edge(planted):
    path, kinds, ym, months, before_rally = planted
    r = cb.read(_member(path, ym, months, before_rally), SPEC, sealed=True)
    assert r["summary"]["n_episodes"] >= 5
    assert r["verdict"] == "edge", r["reason"]


def test_plain_buying_has_no_edge_over_itself(planted):
    path, _, ym, months, _ = planted
    r = cb.read(_member(path, ym, months, [], low=1.0), SPEC, sealed=True)
    assert r["summary"]["advantage"]["10.0"] == pytest.approx(0.0, abs=1e-9)
    assert r["verdict"] == "no_edge"


def test_holding_money_back_for_nothing_reads_inverted(planted):
    path, _, ym, months, _ = planted
    r = cb.read(_member(path, ym, months, [], low=0.75), SPEC, sealed=True)
    assert r["summary"]["reserve"]["end"] > 10                        # the reserve only grows
    assert r["verdict"] == "inverted"


def test_a_drawdown_rule_in_disguise_is_explained_by_the_rival(planted):
    path, _, ym, months, before_rally = planted
    ends = cb.flow_months(path["dates"], True)
    level = np.r_[1.0, np.cumprod(1.0 + path["equity"])]
    dd = 1.0 - level / np.maximum.accumulate(level)
    member_ends = np.where(np.isin(np.arange(len(ends)), before_rally), 12.0, 0.0)
    disguised = cb.dip_matched(member_ends, dd[ends + 1])              # the rival's own multiples
    m = np.zeros(len(ym))
    for k, e in enumerate(ends):
        m[ym == months[k]] = disguised[k]
    r = cb.flow_read({**path, "multiple": m, "signals": {"flag": m > 0}}, SPEC, sealed=True)
    assert r["summary"]["advantage_vs_dip"] == pytest.approx(0.0, abs=1e-12)
    assert r["verdict"] in ("explained_by_rival", "no_edge", "inverted")
    if r["verdict"] != "explained_by_rival":       # whichever earlier stage stops it, it never passes
        assert r["summary"]["advantage"]["10.0"] < F.min_advantage or r["summary"]["advantage_ci"]["lo"] <= 0


def test_the_clause_fails_when_a_cell_is_too_small_to_see(planted):
    path, _, ym, months, before_rally = planted
    p = _member(path, ym, months, before_rally)
    s = cb.flow_summary(F, p, "oracle", sealed=True, n_boot=10)
    c = cb.evaluate_flow_clause(F, {"kind": "forward_contrast", "signal": "flag", "window": 1,
                                    "months": 1}, p, s)
    assert c["passed"]
    rare = _member(path, ym, months, before_rally[:5])
    s = cb.flow_summary(F, rare, "oracle", sealed=True, n_boot=10)
    c = cb.evaluate_flow_clause(F, {"kind": "forward_contrast", "signal": "flag", "window": 1,
                                    "months": 1}, rare, s)
    assert not c["passed"] and "needs ≥ 12" in c["detail"]


def test_the_report_carries_the_numbers_it_never_reads(planted):
    path, _, ym, months, before_rally = planted
    r = cb.read(_member(path, ym, months, before_rally), SPEC, sealed=True)
    s = r["summary"]
    assert {"in_drops", "outside_drops", "reserve_left"} == set(s["advantage_split"])
    assert len(s["halves"]) == 2 and s["starved_share_of_high_months"] is not None
    assert set(s["legs"]["10.0"]) == set(cb.FLOW_LEGS)
    assert "_months" not in s


# ---------------------------------------------------------------------------
# the pre-registration
# ---------------------------------------------------------------------------

def test_a_flow_pre_registration_is_normalised_with_the_class_floor():
    assert SPEC == {"class": "flow_rule", "arm": "oracle", "floor": {"episodes": 5},
                    "clauses": [{"kind": "forward_contrast", "signal": "flag", "window": 1, "months": 1}]}


@pytest.mark.parametrize("over, msg", [
    ({"arm": "plain"}, "arm must name the candidate"),
    ({"floor": {"episodes": 4}}, "looser than the class floor"),
    ({"clauses": []}, "non-empty"),
    ({"clauses": [{"kind": "caught_split", "signal": "f"}]}, "kind must be one of"),
    ({"clauses": [{"kind": "forward_contrast", "signal": "f", "window": 20}]}, "missing"),
    ({"clauses": [{"kind": "forward_contrast", "signal": "f", "window": 0, "months": 12}]}, "window"),
    ({"horizon": 5}, "unknown key"),
])
def test_a_bad_flow_pre_registration_is_refused(over, msg):
    base = {"class": "flow_rule", "arm": "x",
            "clauses": [{"kind": "forward_contrast", "signal": "f", "window": 20, "months": 12}]}
    with pytest.raises(cb.PreregError, match=msg):
        cb.validate({**base, **over})


def test_the_sealed_runner_refuses_a_flow_rule_until_it_has_a_walk():
    import sealed_runner as sr
    assert any("no walk yet" in r for r in sr.refusals(SPEC))


def test_the_cli_prints_the_flow_bar(capsys):
    assert cb.main([]) == 0
    out = capsys.readouterr().out
    assert "flow_rule: vs `plain`" in out and "0.25 pp a year" in out
