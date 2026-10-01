"""The risk-rule class bar (ADR-0023). The method §10: a bar is only exercised
by results that reach it, so every disqualifier is driven alone, ahead of a
strong saving, and planted markets show what passes and what does not — a rule
that cuts before the crash passes, one that only holds less stock, one that is
a volatility rule, and one that trades too much do not."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

import class_bars as cb
from portfolio import book

R = cb.RISK_RULE


# ---------------------------------------------------------------------------
# the bar is ADR-0023's as accepted (resolved.md #34)
# ---------------------------------------------------------------------------

def test_the_bar_is_adr_0023s_as_accepted():
    assert R.episode_depth == 0.10 and R.min_episodes == 5
    assert R.max_shortfall == 0.005                              # the owner's 0.5 pp
    assert R.cost_bps == (book.DEFAULT_COST_BPS, 3 * book.DEFAULT_COST_BPS)
    assert R.min_saving == 0.10 and R.interval == 0.90 and R.vol_majority == pytest.approx(2 / 3)
    assert R.vol_window == 21
    assert R.tax_rate == pytest.approx(0.1846, abs=1e-4)
    assert R.sealed_from == date(2018, 1, 1) and R.sealed_until is None
    assert (R.rival, R.second_rival) == ("static_matched", "vol_matched")
    assert cb.BARS["risk_rule"] is R


def test_five_episodes_is_the_smallest_count_a_sign_test_can_clear():
    assert 0.5 ** R.min_episodes < 0.05 <= 0.5 ** (R.min_episodes - 1)


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level, eps", [
    ([1, .95, .85, .9, 1.01, 1.02], [(0, 2)]),                  # one drop, recovered
    ([1, .95, .97, 1.0], []),                                    # too shallow
    ([1, .85, .95, .80, .9, 1.01], [(0, 3)]),                    # a bounce short of a high: one episode
    ([1, .85, 1.01, .88, 1.05, .9], [(0, 1), (2, 3), (4, 5)]),   # a new high between: three
    ([1, 1.1, .97], [(1, 2)]),                                    # still open at the end: counts
])
def test_an_episode_starts_only_after_a_new_high(level, eps):
    assert cb.risk_episodes(np.array(level, float), 0.10) == eps


def test_a_decision_at_the_close_of_t_earns_from_day_t_plus_2():
    decided = np.array([1.0, 1.0, 0.5, 0.5, 0.5])
    assert list(cb._held(decided)) == [1.0, 1.0, 1.0, 1.0, 0.5]


def test_buy_and_hold_compounds_and_never_realizes_a_gain():
    eq = np.array([0.01, -0.02, 0.03, 0.01])
    leg = cb._leg(eq, np.zeros(4), np.ones(4), 10.0)
    assert np.allclose(leg["value"], np.cumprod(1 + eq))
    assert not leg["realized"].any() and not leg["turnover"].any()


def test_costs_are_paid_on_what_is_traded():
    eq, cash = np.zeros(6), np.zeros(6)
    flip = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0])
    free, paid = cb._leg(eq, cash, flip, 0.0), cb._leg(eq, cash, flip, 10.0)
    assert free["value"][-1] == pytest.approx(1.0)
    assert paid["value"][-1] < 1.0 and paid["value"][-1] > 1.0 - 6 * 10 / 1e4


def test_a_sale_after_a_rise_realizes_the_gain_on_the_average_cost():
    eq = np.array([0.0, 0.0, 0.10, 0.0, 0.0])
    leg = cb._leg(eq, np.zeros(5), np.array([1.0, 1.0, 0.5, 0.5, 0.5]), 0.0)
    # held 1.0 through the 10% day; decided 0.5 at the close of day 2, sold at the close of day 3
    assert leg["realized"][3] == pytest.approx(0.5 * 1.1 * (0.10 / 1.10), rel=1e-6)
    tax = cb._tax_line(leg, ["2018-01-0%d" % i for i in range(2, 7)], R.tax_rate)
    assert tax["tax_brought_forward_per_year"] == pytest.approx(R.tax_rate * 0.05, abs=1e-5)


def test_the_vol_rule_holds_the_members_average_exposure():
    rng = np.random.default_rng(1)
    eq = rng.normal(0, 0.01, 800) * np.r_[np.ones(400), 3 * np.ones(100), np.ones(300)]
    e = cb._vol_rule(eq, 0.8, 21)
    assert e.mean() == pytest.approx(0.8, abs=1e-6) and e.max() <= 1.0
    assert e[420:500].mean() < e[100:400].mean()                # it cuts where volatility is
    assert (cb._vol_rule(eq, 1.0, 21) == 1.0).all()


# ---------------------------------------------------------------------------
# the verdict, each stage driven alone
# ---------------------------------------------------------------------------

def _summary(**over):
    """A summary that clears everything: a large saving against both rivals."""
    s = {"n_episodes": 8, "mean_r": 0.55, "shortfall": {"10.0": 0.002, "30.0": 0.001},
         "saving": {"mean": 0.40, "ci": {"lo": 0.25, "hi": 0.55}},
         "saving_vs_vol": {"mean": 0.20, "share_better": 0.875}}
    s.update(over)
    return s


_HELD = [{"kind": "caught_split", "passed": True, "detail": "", "cells": []}]
_FAILED = [{"kind": "caught_split", "passed": False, "detail": "no", "cells": []}]


def _v(summary=None, clauses=_HELD, sealed=True, floor=None):
    return cb.risk_verdict(R, summary or _summary(), clauses, sealed=sealed, floor=floor)["verdict"]


def test_everything_cleared_is_an_edge():
    assert _v() == "edge"


@pytest.mark.parametrize("over, clauses, expected", [
    ({"n_episodes": 4}, _HELD, "underpowered"),
    ({"mean_r": 1.02}, _HELD, "inverted"),
    ({"shortfall": {"10.0": -0.006, "30.0": -0.010}}, _HELD, "too_costly"),
    ({"shortfall": {"10.0": -0.001, "30.0": -0.0051}}, _HELD, "too_costly"),     # at three times the cost
    ({"saving": {"mean": 0.09, "ci": {"lo": 0.05, "hi": 0.13}}}, _HELD, "no_edge"),
    ({"saving": {"mean": 0.40, "ci": {"lo": 0.0, "hi": 0.8}}}, _HELD, "no_edge"),  # interval touches zero
    ({"saving_vs_vol": {"mean": 0.0, "share_better": 1.0}}, _HELD, "explained_by_rival"),
    ({"saving_vs_vol": {"mean": 0.3, "share_better": 0.6}}, _HELD, "explained_by_rival"),
    ({}, _FAILED, "unexplained"),
    ({}, [], "unexplained"),
])
def test_each_stage_fires_on_its_own_ahead_of_a_strong_saving(over, clauses, expected):
    assert _v(_summary(**over), clauses) == expected


def test_a_disqualifier_fires_even_when_every_later_stage_would_fail_too():
    worst = _summary(n_episodes=3, mean_r=1.5, shortfall={"10.0": -0.1, "30.0": -0.1},
                     saving={"mean": -1.0, "ci": {"lo": -2, "hi": 0}})
    assert _v(worst, _FAILED) == "underpowered"
    assert _v(_summary(mean_r=1.5, shortfall={"10.0": -0.1, "30.0": -0.1}), _FAILED) == "inverted"


def test_an_unsealed_read_is_exploratory_whatever_it_shows():
    assert _v(sealed=False) == "exploratory"


def test_an_entry_floor_tightens_the_episode_count():
    assert _v(_summary(n_episodes=6), floor={"episodes": 7}) == "underpowered"


def test_every_risk_verdict_is_reachable_and_named():
    seen = {_v(sealed=False), _v(_summary(n_episodes=1)), _v(_summary(mean_r=2.0)),
            _v(_summary(shortfall={"10.0": -1, "30.0": -1})),
            _v(_summary(saving={"mean": 0, "ci": {"lo": -1, "hi": 1}})),
            _v(_summary(saving_vs_vol={"mean": -1, "share_better": 0})), _v(clauses=_FAILED), _v()}
    assert seen == set(cb.RISK_VERDICTS)


# ---------------------------------------------------------------------------
# planted markets: what passes and what does not
# ---------------------------------------------------------------------------

CRASH, LEAD = 40, 5


def _market(seed=0, n_crash=6, crash_sd=0.005, crash_mu=-0.008, sd=0.005):
    """Calm drift with `n_crash` 40-day falls of ~27%, each followed by a
    rebound to a new high, on business days from 2018-01-02 — the sealed side."""
    rng = np.random.default_rng(seed)
    gap = 400
    n = gap * (n_crash + 1)
    eq = rng.normal(0.0004, sd, n)
    starts = [gap * (k + 1) - 2 * CRASH for k in range(n_crash)]
    for s0 in starts:
        eq[s0:s0 + CRASH] = rng.normal(crash_mu, crash_sd, CRASH)
        eq[s0 + CRASH:s0 + 2 * CRASH] = rng.normal(0.0095, sd, CRASH)
    days = np.busday_offset("2018-01-02", np.arange(n), roll="forward")
    return {"dates": [str(d) for d in days], "equity": eq, "cash": np.full(n, 0.00005)}, starts


def _oracle(path, starts, miss=()):
    """Half out from LEAD days before each fall to its end, the signal firing
    on each of those days; the falls in `miss` it does not see."""
    n = len(path["equity"])
    e, sig = np.ones(n), np.zeros(n, bool)
    for k, s0 in enumerate(starts):
        if k in miss:
            continue
        e[s0 - LEAD:s0 + CRASH - 2] = 0.5
        sig[s0 - LEAD:s0 + CRASH - 2] = True
    return {**path, "exposure": e, "signals": {"flag": sig}}


SPEC = cb.validate({"class": "risk_rule", "arm": "oracle",
                    "clauses": [{"kind": "caught_split", "signal": "flag"}]})


def test_a_rule_that_cuts_before_the_fall_passes():
    path, starts = _market()
    got = cb.read(_oracle(path, starts, miss={2}), SPEC, sealed=True)
    assert got["summary"]["n_episodes"] == 6
    assert got["verdict"] == "edge", got["reason"]
    assert got["summary"]["saving"]["mean"] > 0.3
    assert [e["caught"] for e in got["summary"]["episodes"]] == [True, True, False, True, True, True]


def test_the_same_rule_that_sees_every_fall_cannot_show_its_mechanism():
    path, starts = _market()
    got = cb.read(_oracle(path, starts), SPEC, sealed=True)
    assert got["verdict"] == "unexplained" and "0 missed" in got["reason"]


def test_a_firing_before_the_peak_counts_only_within_before_peak():
    """A single firing LEAD days ahead of the fall lands before the peak the
    calm drift makes; the entry chooses whether its rule's hold covers it."""
    path, starts = _market()
    o = _oracle(path, starts, miss={2})
    first = np.zeros(len(o["exposure"]), bool)
    for k, s0 in enumerate(starts):
        first[s0 - LEAD] = k != 2
    o["signals"] = {"flag": first}
    at_peak = cb.read(o, SPEC, sealed=True)["summary"]["episodes"]
    spec = cb.validate({"class": "risk_rule", "arm": "oracle",
                        "clauses": [{"kind": "caught_split", "signal": "flag", "before_peak": 19}]})
    held = cb.read(o, spec, sealed=True)["summary"]["episodes"]
    assert sum(e["caught"] for e in held) == 5 > sum(e["caught"] for e in at_peak)


def test_holding_less_stock_is_not_an_edge():
    path, _ = _market()
    flat = {**path, "exposure": np.full(len(path["equity"]), 0.7), "signals": {"flag": np.zeros(len(path["equity"]), bool)}}
    got = cb.read(flat, SPEC, sealed=True)
    assert got["verdict"] == "no_edge"
    assert got["summary"]["saving"]["mean"] == pytest.approx(0.0, abs=1e-6)


def test_a_rule_firing_at_random_is_not_an_edge():
    path, _ = _market()
    rng = np.random.default_rng(7)
    fire = rng.random(len(path["equity"])) < 0.01
    e = np.where(np.convolve(fire, np.ones(20), "full")[:len(fire)] > 0, 0.5, 1.0)
    got = cb.read({**path, "exposure": e, "signals": {"flag": fire}}, SPEC, sealed=True)
    assert got["verdict"] in ("no_edge", "too_costly", "inverted"), got["reason"]


def test_a_volatility_rule_in_disguise_is_explained_by_the_rival():
    path, _ = _market(crash_sd=0.03, crash_mu=-0.006)
    e = cb._vol_rule(path["equity"], 0.8, R.vol_window)
    got = cb.read({**path, "exposure": e, "signals": {"flag": e < 1}}, SPEC, sealed=True)
    assert got["summary"]["saving"]["mean"] >= R.min_saving        # it does cut drops…
    assert got["verdict"] == "explained_by_rival", got["reason"]    # …and the rival does it too
    assert got["summary"]["saving_vs_vol"] == {"mean": 0.0, "share_better": 0.0}   # a tie, not noise


def test_a_rule_that_trades_every_day_is_too_costly():
    path, starts = _market()
    o = _oracle(path, starts, miss={2})
    e = o["exposure"].copy()
    e[1::2] = np.minimum(e[1::2], 0.0)                           # out every other day
    got = cb.read({**o, "exposure": e}, SPEC, sealed=True)
    assert got["verdict"] == "too_costly", got["reason"]


def test_a_rule_that_is_out_for_the_bounce_and_in_for_the_fall_can_be_inverted():
    """With exposure capped at 1, r > 1 takes a bounce inside the drop: full
    for the falls, half for the bounce between them."""
    n = 200
    eq = np.zeros(n)
    eq[50:60], eq[60:70], eq[70:80] = -0.02, +0.015, -0.02
    e = np.ones(n)
    e[58:68] = 0.5                                               # decided two days ahead of the bounce
    path = {"dates": [str(d) for d in np.busday_offset("2018-01-02", np.arange(n), roll="forward")],
            "equity": eq, "cash": np.zeros(n), "exposure": e}
    s = cb.risk_summary(R, path, "x", sealed=True)
    assert s["n_episodes"] == 1 and s["mean_r"] > 1.0


# ---------------------------------------------------------------------------
# what it reports, and what it refuses
# ---------------------------------------------------------------------------

def test_the_report_carries_every_leg_at_every_cost_and_the_tax_line():
    path, starts = _market()
    got = cb.read(_oracle(path, starts, miss={2}), SPEC, sealed=True)
    legs = got["summary"]["legs"]
    assert set(legs) == set(R.cost_bps) and set(legs[10.0]) == set(cb.RISK_LEGS)
    for k in ("worst_drop", "annual_return", "annual_vol", "time_reduced", "trades_per_year",
              "turnover_per_year", "realized_gain_per_year", "tax_brought_forward_per_year"):
        assert k in legs[10.0]["member"]
    assert legs[10.0]["buy_and_hold"]["tax_brought_forward_per_year"] == 0.0
    assert legs[10.0]["member"]["tax_brought_forward_per_year"] > 0.0
    assert legs[10.0]["member"]["worst_drop"] < legs[10.0]["buy_and_hold"]["worst_drop"]
    assert all("_pos" not in e for e in got["summary"]["episodes"])


def test_an_explore_read_stops_before_the_seal_and_a_sealed_read_starts_on_it():
    path, starts = _market()
    member = _oracle(path, starts)
    with pytest.raises(cb.PreregError, match="stops before the seal"):
        cb.read(member, SPEC, sealed=False)
    early = {**member, "dates": [d.replace("20", "19", 1) for d in member["dates"]]}
    with pytest.raises(cb.PreregError, match="starts on the sealed side"):
        cb.read(early, SPEC, sealed=True)
    assert cb.read(early, SPEC, sealed=False)["verdict"] == "exploratory"


def test_an_exposure_outside_zero_to_one_is_refused():
    path, starts = _market()
    member = _oracle(path, starts)
    member["exposure"] = member["exposure"] * 1.5
    with pytest.raises(cb.PreregError, match=r"\[0, 1\]"):
        cb.read(member, SPEC, sealed=True)


def test_a_clause_naming_a_signal_the_path_lacks_is_refused():
    path, starts = _market()
    spec = cb.validate({"class": "risk_rule", "arm": "x", "clauses": [{"kind": "caught_split", "signal": "nope"}]})
    with pytest.raises(cb.PreregError, match="no signal 'nope'"):
        cb.read(_oracle(path, starts), spec, sealed=True)


@pytest.mark.parametrize("spec, says", [
    ({"arm": "static_matched"}, "not a rival"),
    ({"arm": "buy_and_hold"}, "not a rival"),
    ({"horizon": 5}, "unknown key"),
    ({"floor": {"episodes": 4}}, "looser than the class floor"),
    ({"floor": {"report_dates": 100}}, "integer episodes"),
    ({"clauses": []}, "non-empty"),
    ({"clauses": [{"kind": "width_contrast", "signal": "x"}]}, "kind must be one of"),
    ({"clauses": [{"kind": "caught_split"}]}, "missing"),
    ({"clauses": [{"kind": "caught_split", "signal": "flag", "before_peak": -1}]}, "before_peak"),
    ({"clauses": [{"kind": "caught_split", "signal": "flag", "before_peak": 2.5}]}, "before_peak"),
])
def test_a_risk_pre_registration_the_bar_cannot_read_is_refused(spec, says):
    base = {"class": "risk_rule", "arm": "x", "clauses": [{"kind": "caught_split", "signal": "flag"}]}
    with pytest.raises(cb.PreregError, match=says):
        cb.validate({**base, **spec})


def test_a_risk_pre_registration_is_normalised_with_the_class_floor():
    assert SPEC == {"class": "risk_rule", "arm": "oracle", "floor": {"episodes": 5},
                    "clauses": [{"kind": "caught_split", "signal": "flag"}]}


def test_the_sealed_runner_refuses_a_risk_rule_until_it_has_a_walk():
    import sealed_runner as sr
    assert any("no walk yet" in r for r in sr.refusals(SPEC))


def test_the_cli_prints_the_risk_bar(capsys):
    assert cb.main([]) == 0
    out = capsys.readouterr().out
    assert "risk_rule: vs `static_matched`, rival `vol_matched`" in out and "18.46%" in out
