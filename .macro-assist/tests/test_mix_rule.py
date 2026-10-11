"""The allocation-rule class bar (ADR-0026, `class_bars.MIX_RULE`). What it
must do: read drift from the owner's mix against splitting every contribution
at it, with return only a cost limit against a fixed mix holding the member's
mean equity weight; disqualifiers first, each driven alone; never sell, never
hold money back; refuse a path on the wrong side of the seal."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import class_bars as cb
import explore_rules as er

BAR = cb.MIX_RULE
W = {"equity": 0.7, "bonds": 0.2, "gold": 0.1}
SPEC = cb.validate({"class": "mix_rule", "arm": "x",
                    "clauses": [{"kind": "late_control", "from_month": 61, "max_ratio": 0.75}]})


@pytest.fixture(autouse=True)
def few_boots(monkeypatch):
    monkeypatch.setattr(cb, "N_BOOT", 40)


def test_the_bar_is_adr_0026s_as_accepted():
    assert (BAR.max_ratio, BAR.max_shortfall, BAR.min_episodes, BAR.episode_depth) == (0.5, 0.0025, 5, 0.10)
    assert BAR.cost_bps == (10.0, 30.0) and (BAR.interval, BAR.block_months) == (0.90, 24)
    assert (BAR.plan_months, BAR.min_sealed_months) == (120, 96)
    assert BAR.sealed_from.isoformat() == "2018-01-01" and BAR.sealed_until is None
    assert (BAR.rival, BAR.second_rival) == ("plain", "exposure_matched")
    assert cb.BARS["mix_rule"] is BAR


def _months(first="1973-01", last="2017-12"):
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def _market(seed=1, first="1973-01", last="2017-12", flat=False):
    months = _months(first, last)
    n = len(months)
    if flat:
        return months, {k: np.zeros(n) for k in W}
    rng = np.random.default_rng(seed)
    return months, {"equity": rng.normal(0.007, 0.045, n), "bonds": rng.normal(0.004, 0.015, n),
                    "gold": rng.normal(0.004, 0.05, n)}


def _path(allocate=er.fill_gaps, **kw):
    months, ret = _market(**kw)
    return {"months": months, "returns": ret, "targets": dict(W), "equity": "equity", "allocate": allocate}


def _plain(V, w, k):
    return np.broadcast_to(w, V.shape)


def _one_holding(V, w, k):
    tot = V.sum(axis=1) + 1.0
    gap = w * tot[:, None] - V
    x = np.zeros_like(V)
    x[np.arange(len(V)), gap.argmax(axis=1)] = 1.0
    return x


def _all_equity(V, w, k):
    x = np.zeros_like(V)
    x[:, 0] = 1.0
    return x


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

def test_every_euro_is_invested_and_nothing_is_sold():
    months, ret = _market(flat=True)
    R = np.array([ret[k] for k in W]).T[None]
    out = cb._mix_legs(R, [0], 120, np.array(list(W.values())), 0, er.fill_gaps, None, 0.0)
    assert out["member"]["wealth"][0, 0] == pytest.approx(120.0)
    assert out["plain"]["wealth"][0, 0] == pytest.approx(120.0)


def test_costs_are_paid_on_what_is_bought():
    months, ret = _market(flat=True)
    R = np.array([ret[k] for k in W]).T[None]
    out = cb._mix_legs(R, [0], 120, np.array(list(W.values())), 0, er.fill_gaps, None, 30.0)
    assert out["plain"]["wealth"][0, 0] == pytest.approx(120.0 * (1 - 0.003))


def test_a_flat_plan_returns_nothing_a_year():
    months, ret = _market(flat=True)
    R = np.array([ret[k] for k in W]).T[None]
    w = cb._mix_legs(R, [0], 120, np.array(list(W.values())), 0, er.fill_gaps, None, 0.0)["plain"]["wealth"]
    assert cb._plan_mwr(w, 120)[0, 0] == pytest.approx(0.0, abs=1e-9)


def test_plain_never_drifts_in_a_flat_market_and_the_first_month_end_is_not_read():
    months, ret = _market(flat=True)
    R = np.array([ret[k] for k in W]).T[None]
    out = cb._mix_legs(R, [0], 120, np.array(list(W.values())), 0, er.fill_gaps, None, 0.0)
    assert out["plain"]["drift"].shape == (1, 1, 120)
    assert np.allclose(out["plain"]["drift"], 0.0) and np.allclose(out["member"]["drift"], 0.0, atol=1e-12)


def test_plans_start_each_january_and_fit_before_the_end():
    months = _months()
    starts = cb._plan_starts(months, 120, sealed=False)
    assert [months[s] for s in starts][:2] == ["1973-01", "1974-01"]
    assert months[starts[-1]] == "2008-01" and len(starts) == 36
    assert cb._plan_starts(months, 120, sealed=True) == [0]


def test_the_matched_rival_holds_the_members_mean_equity_weight():
    s = cb.mix_summary(BAR, _path(), "x")
    mw = s["mean_equity_weight"]
    assert mw["exposure_matched"] == pytest.approx(mw["member"], abs=2e-4)


def test_the_bootstrap_draws_whole_blocks_of_consecutive_months():
    bi = cb._boot_idx(100, 24, 5, 7)
    assert bi.shape == (5, 100)
    assert np.all(np.diff(bi[:, :24], axis=1) == 1)


def test_an_annual_sell_back_realizes_no_gain_in_a_flat_market():
    months, ret = _market(flat=True)
    R = np.array([ret[k] for k in W]).T
    sr = cb._sell_rebalanced(R, months, [0], 120, np.array(list(W.values())), 10.0)
    assert sr["gains_per_plan"] == pytest.approx(0.0) and sr["mean_drift"] == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# the path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("over, sealed, msg", [
    ({"months": _months("2010-01", "2018-03")}, False, "explore read stops before the seal"),
    ({"months": _months("2017-06", "2026-08")}, True, "sealed read starts on the sealed side"),
    ({"targets": {"equity": 0.7, "bonds": 0.2, "gold": 0.2}}, False, "summing to 1"),
    ({"equity": "stocks"}, False, "`equity` must name"),
    ({"allocate": None}, False, "no `allocate` rule"),
])
def test_a_malformed_or_misplaced_path_is_refused(over, sealed, msg):
    p = _path()
    if "months" in over:
        n = len(over["months"])
        p["returns"] = {k: np.zeros(n) for k in W}
    p.update(over)
    with pytest.raises(cb.PreregError, match=msg):
        cb.mix_summary(BAR, p, "x", sealed=sealed)


# ---------------------------------------------------------------------------
# the verdict, each stage alone
# ---------------------------------------------------------------------------

def _summary(**over):
    s = {"n_episodes": 12, "plan_months": 120, "control_ratio": 0.30,
         "control_ratio_ci": {"lo": 0.25, "hi": 0.40}, "shortfall": {"10.0": 0.0005, "30.0": 0.0006}}
    s.update(over)
    return s


HELD = [{"kind": "late_control", "passed": True, "detail": "ok"}]
FAILED = [{"kind": "late_control", "passed": False, "detail": "faded"}]


def test_everything_cleared_is_an_edge():
    assert cb.mix_verdict(BAR, _summary(), HELD, sealed=True)["verdict"] == "edge"


@pytest.mark.parametrize("over, sealed_months, clauses, expected", [
    ({"n_episodes": 4}, 120, HELD, "underpowered"),
    ({"plan_months": 95}, 95, HELD, "underpowered"),
    ({"control_ratio": 1.0, "control_ratio_ci": {"lo": 0.9, "hi": 1.1}}, 120, HELD, "inverted"),
    ({"shortfall": {"10.0": 0.0005, "30.0": 0.0026}}, 120, HELD, "costly"),
    ({"control_ratio": 0.51}, 120, HELD, "no_control"),
    ({"control_ratio_ci": {"lo": 0.2, "hi": 1.0}}, 120, HELD, "no_control"),
    ({}, 120, FAILED, "unexplained"),
    ({}, 120, [], "unexplained"),
])
def test_each_stage_fires_on_its_own(over, sealed_months, clauses, expected):
    s = _summary(**over)
    s["plan_months"] = sealed_months
    assert cb.mix_verdict(BAR, s, clauses, sealed=True)["verdict"] == expected


def test_a_disqualifier_fires_even_when_every_later_stage_would_fail_too():
    bad = _summary(n_episodes=2, control_ratio=1.4, control_ratio_ci={"lo": 1.2, "hi": 1.6},
                   shortfall={"10.0": 0.01, "30.0": 0.01})
    assert cb.mix_verdict(BAR, bad, FAILED, sealed=True)["verdict"] == "underpowered"
    bad["n_episodes"] = 12
    assert cb.mix_verdict(BAR, bad, FAILED, sealed=True)["verdict"] == "inverted"
    bad["control_ratio"], bad["control_ratio_ci"] = 0.9, {"lo": 0.8, "hi": 1.0}
    assert cb.mix_verdict(BAR, bad, FAILED, sealed=True)["verdict"] == "costly"


def test_an_unsealed_read_is_exploratory_whatever_it_shows():
    assert cb.mix_verdict(BAR, _summary(), HELD, sealed=False)["verdict"] == "exploratory"


def test_an_entry_floor_tightens_the_episode_count():
    v = cb.mix_verdict(BAR, _summary(n_episodes=6), HELD, sealed=True, floor={"episodes": 8})
    assert v["verdict"] == "underpowered"


def test_every_mix_verdict_is_reachable_and_named():
    assert set(cb.MIX_VERDICTS) == {"exploratory", "underpowered", "inverted", "costly", "no_control",
                                    "unexplained", "edge"}


# ---------------------------------------------------------------------------
# planted markets: what the reader does with known rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2])
def test_filling_every_gap_keeps_the_mix_at_least_twice_as_close_as_plain(seed):
    s = cb.mix_summary(BAR, _path(seed=seed), "x")
    assert s["control_ratio"] < BAR.max_ratio
    assert s["control_ratio_by_half"]["second"] < 0.75


def test_plain_buying_has_no_control_over_itself():
    s = cb.mix_summary(BAR, _path(allocate=_plain), "x")
    assert s["control_ratio"] == pytest.approx(1.0)
    assert cb.mix_verdict(BAR, s, HELD, sealed=True)["verdict"] == "inverted"


def test_buying_only_equity_drifts_further_than_plain():
    s = cb.mix_summary(BAR, _path(allocate=_all_equity), "x")
    assert s["control_ratio"] > 1.0


def test_one_lumpy_purchase_a_month_drifts_more_than_plain_early_in_a_plan():
    """The build finding that changed H-011 before any data (resolved.md #38):
    the whole contribution into one holding moves a small account a lot."""
    s = cb.mix_summary(BAR, _path(allocate=_one_holding), "x")
    assert s["control_ratio_by_half"]["first"] > 1.0
    assert s["control_ratio"] > BAR.max_ratio


def test_the_clause_reads_each_plans_second_half():
    p = _path()
    s = cb.mix_summary(BAR, p, "x")
    c = cb.evaluate_mix_clause(BAR, SPEC["clauses"][0], p, s)
    assert c["passed"] and c["cells"][0]["n_plans"] == 36
    s2 = cb.mix_summary(BAR, _path(allocate=_plain), "x")
    assert not cb.evaluate_mix_clause(BAR, SPEC["clauses"][0], p, s2)["passed"]


def test_the_report_carries_the_numbers_it_never_reads():
    r = cb.read(_path(), SPEC, sealed=False)
    s = r["summary"]
    assert r["verdict"] == "exploratory" and "_plans" not in s
    for k in ("control_ratio_by_half", "control_ratio_by_plan", "received", "sell_rebalanced",
              "mean_equity_weight", "legs", "halves", "episodes", "shortfall_ci"):
        assert k in s
    assert sum(s["received"].values()) == pytest.approx(1.0, abs=1e-3)


def test_a_sealed_plan_shorter_than_eight_years_is_underpowered():
    p = _path(first="2018-01", last="2024-12")
    r = cb.read(p, SPEC, sealed=True)
    assert r["summary"]["plan_months"] == 84 and r["verdict"] == "underpowered"


# ---------------------------------------------------------------------------
# the pre-registration
# ---------------------------------------------------------------------------

def test_a_mix_pre_registration_is_normalised_with_the_class_floor():
    assert SPEC == {"class": "mix_rule", "arm": "x", "floor": {"episodes": 5},
                    "clauses": [{"kind": "late_control", "from_month": 61, "max_ratio": 0.75}]}


@pytest.mark.parametrize("over, msg", [
    ({"arm": "plain"}, "not a rival"),
    ({"floor": {"episodes": 3}}, "looser than the class floor"),
    ({"clauses": []}, "non-empty list"),
    ({"clauses": [{"kind": "forward_contrast"}]}, "kind must be one of"),
    ({"clauses": [{"kind": "late_control", "from_month": 50, "max_ratio": 0.75}]}, "from_month must be 61"),
    ({"clauses": [{"kind": "late_control", "from_month": 61, "max_ratio": 0.4}]}, "max_ratio must be"),
    ({"clauses": [{"kind": "late_control", "from_month": 61, "max_ratio": 1.0}]}, "max_ratio must be"),
    ({"horizon": 5}, "unknown key"),
])
def test_a_bad_mix_pre_registration_is_refused(over, msg):
    base = {"class": "mix_rule", "arm": "x",
            "clauses": [{"kind": "late_control", "from_month": 61, "max_ratio": 0.75}]}
    with pytest.raises(cb.PreregError, match=msg):
        cb.validate({**base, **over})


def test_the_sealed_runner_refuses_a_mix_rule_until_it_has_a_walk():
    import sealed_runner as sr
    assert any("no walk yet" in r for r in sr.refusals(SPEC))


def test_the_cli_prints_the_mix_bar(capsys):
    assert cb.main([]) == 0
    out = capsys.readouterr().out
    assert "mix_rule: vs `plain`" in out and "0.25 pp a year" in out


def test_the_record_audit_fingerprints_the_mix_bar():
    from pathlib import Path
    import record_audit as ra
    root = Path(__file__).resolve().parents[2]
    assert ra.bar_fingerprint(root, "mix_rule") and ra.bar_fingerprint(root, "flow_rule")
