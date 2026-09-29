"""The class bars (WP-23.B). The method §10: a bar is only exercised by results
that reach it, so every disqualifier is driven alone, ahead of a strong skill
number, and a planted signal is shown to pass — and a planted vol-only signal
shown not to."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

import class_bars as cb
import decision_packet as dp
import explore_conditioner as ec
import score_distributions as sd

C = cb.CONDITIONER


# ---------------------------------------------------------------------------
# the bar is Phase 22's, as is, and the seal is resolved.md #19's
# ---------------------------------------------------------------------------

def test_the_conditioner_bar_is_phase_22s_as_is():
    assert cb.MIN_SKILL == sd.MIN_SKILL == 0.02
    assert C.min_blocks == sd.MIN_BLOCKS == 8
    assert C.block == sd.BLOCK_DAYS and C.benchmark == "unconditional"
    assert C.rival == "har_scaled"                           # resolved.md #22
    assert C.headline_keys == frozenset(sd.ORIGINAL_KEYS)


def test_the_conditioner_reads_the_sealed_side_and_stops_at_the_live_record():
    assert C.sealed_from == date(2018, 1, 1) == ec.SEAL_START    # resolved.md #19
    assert C.sealed_until == date(2026, 9, 7)                     # Phase 22's live record starts


def test_the_gap_class_has_no_seal_yet_and_a_sealed_read_is_refused():
    assert cb.GAP_WIDTH.sealed_from is None
    spec = cb.validate({"class": "gap_width", "arm": "gap",
                        "clauses": [{"kind": "skill_in_state", "cell": {"gap_tercile": "high"}}]})
    with pytest.raises(cb.PreregError, match="no decided seal"):
        cb.read([], spec, sealed=True)


# ---------------------------------------------------------------------------
# the verdict, each stage driven alone
# ---------------------------------------------------------------------------

def _stat(skill, lo, hi):
    return {"skill": skill, "ci": {"lo": lo, "hi": hi}}


def _summary(**over):
    """A summary that clears everything: strong skill against both comparators."""
    s = {"n_blocks": 40, "n_report_dates": 840, "skill": _stat(0.10, 0.06, 0.14),
         "coverage": 0.50, "coverage_ci": {"lo": 0.46, "hi": 0.54},
         "rival": {"name": "har_scaled", "n_blocks": 40, "skill": _stat(0.08, 0.04, 0.12)}}
    s.update(over)
    return s


def _clause(passed=True, dates=200, eps=6):
    return {"kind": "width_contrast", "passed": passed, "detail": "planted",
            "cells": [{"name": "a@5", "n_report_dates": dates, "n_episodes": eps},
                      {"name": "b@5", "n_report_dates": 600, "n_episodes": 9}]}


def _v(summary=None, clauses="default", sealed=True, floor=None, bar=C):
    clauses = [_clause()] if clauses == "default" else clauses
    return cb.verdict(bar, summary or _summary(), clauses, sealed=sealed, floor=floor)["verdict"]


def test_everything_cleared_is_an_edge():
    assert _v() == "edge"


@pytest.mark.parametrize("summary, clauses, expected", [
    (_summary(n_blocks=7), "default", "underpowered"),
    (_summary(rival={"name": "har_scaled", "n_blocks": 5, "skill": _stat(0.08, 0.04, 0.12)}),
     "default", "underpowered"),
    (_summary(), [_clause(eps=2)], "underpowered"),           # 200 rows, two episodes
    (_summary(), [_clause(dates=40)], "underpowered"),        # six episodes, 40 rows
    (_summary(skill=None), "default", "underpowered"),
    (_summary(coverage_ci=None), "default", "underpowered"),
    (_summary(coverage=0.62, coverage_ci={"lo": 0.58, "hi": 0.66}), "default", "miscalibrated"),
    (_summary(skill=_stat(-0.05, -0.08, -0.02)), "default", "inverted"),
    (_summary(skill=_stat(0.003, 0.001, 0.005)), "default", "no_edge"),     # KB-027's +0.003
    (_summary(skill=_stat(0.05, -0.01, 0.11)), "default", "no_edge"),
    (_summary(rival={"name": "har_scaled", "n_blocks": 40, "skill": _stat(0.003, 0.001, 0.005)}),
     "default", "explained_by_rival"),
    (_summary(rival={"name": "har_scaled", "n_blocks": 40, "skill": _stat(-0.02, -0.05, 0.01)}),
     "default", "explained_by_rival"),
    (_summary(), [], "unexplained"),
    (_summary(), [_clause(), _clause(passed=False)], "unexplained"),
])
def test_each_stage_fires_on_its_own_ahead_of_a_strong_number(summary, clauses, expected):
    assert _v(summary, clauses) == expected


def test_a_disqualifier_fires_even_when_every_later_stage_would_pass():
    """The order is the bar: an underpowered cell is `underpowered` whatever
    the skill, not `edge` with a footnote."""
    strong = _summary(skill=_stat(0.40, 0.30, 0.50))
    assert _v(strong, [_clause(eps=2)]) == "underpowered"
    assert _v(_summary(skill=_stat(0.40, 0.30, 0.50), coverage=0.70,
                       coverage_ci={"lo": 0.66, "hi": 0.74})) == "miscalibrated"


def test_an_unsealed_sample_is_exploratory_whatever_it_shows():
    assert _v(sealed=False) == "exploratory"


def test_an_entry_floor_is_applied_and_can_only_tighten():
    assert _v(floor={"report_dates": 250, "episodes": 3}) == "underpowered"
    with pytest.raises(cb.PreregError, match="looser than the class floor"):
        cb.validate({"class": "conditioner", "arm": "x", "floor": {"episodes": 2},
                     "clauses": [{"kind": "skill_in_state", "cell": {"s": 1}}]})


def test_every_number_is_carried_whichever_verdict_fires():
    got = cb.verdict(C, _summary(n_blocks=3), [_clause()], sealed=True)
    assert got["verdict"] == "underpowered"
    assert got["summary"]["skill"]["skill"] == 0.10 and got["clauses"][0]["passed"]


def test_every_verdict_is_reachable_and_named():
    seen = {_v(sealed=False), _v(_summary(n_blocks=1)),
            _v(_summary(coverage_ci={"lo": 0.1, "hi": 0.2})), _v(_summary(skill=_stat(-.1, -.2, -.05))),
            _v(_summary(skill=_stat(0, -.01, .01))),
            _v(_summary(rival={"name": "r", "n_blocks": 40, "skill": None})), _v(clauses=[]), _v()}
    assert seen == set(cb.VERDICTS)


# ---------------------------------------------------------------------------
# the statistics agree with the harness the explore looks used
# ---------------------------------------------------------------------------

def test_pooled_skill_is_the_harness_statistic_at_its_block():
    obs, _ = _planted(n_dates=300)
    ours = cb.pooled_skill(obs, "cond", "unconditional", sd.ORIGINAL_KEYS, sd.BLOCK_DAYS)
    theirs = ec.pooled(obs, "cond", sd.ORIGINAL_KEYS)
    assert ours == theirs


@pytest.mark.parametrize("positions, gap, span, n", [
    ([], 21, 252, 0), ([0, 1, 2, 3], 21, 252, 1), ([0, 1, 50, 51, 200], 21, 252, 3),
    ([0, 22], 21, 252, 2), ([0, 21], 21, 252, 1), ([0, 1, 3], 1, 4, 2),
    (list(range(0, 700, 5)), 21, 252, 2),               # one 700-date run: two years, two episodes
    (list(range(0, 70)) + list(range(400, 470)), 21, 252, 2),   # H-008's shape: 140 rows, two spells
])
def test_episodes_are_runs_of_report_dates(positions, gap, span, n):
    dates = [f"d{i:04d}" for i in range(800)]
    assert cb.episodes([dates[p] for p in positions], dates, gap, span) == n


# ---------------------------------------------------------------------------
# the positive control: a planted state passes; a planted vol forecast does not
# ---------------------------------------------------------------------------

_Z = {0.25: -0.6744897501960817, 0.50: 0.0, 0.75: 0.6744897501960817}


def _planted(n_dates=1260, *, rival_knows_state=False, seed=3):
    """Report dates in runs: 60 Normal, 20 Elevated. The realized change is
    N(0, 1) in Normal and N(0, 3) in Elevated. `cond` quotes the state's true
    quantiles; `unconditional` the mixture's; `har_scaled` knows only the
    mixture's σ — or, with `rival_knows_state`, the state's, which is a vol
    forecast carrying all of the gain."""
    rng = np.random.default_rng(seed)
    d0 = date(2018, 1, 2)
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(n_dates)]
    state = ["Elevated" if i % 80 >= 60 else "Normal" for i in range(n_dates)]
    mix = np.concatenate([rng.normal(0, 1, 30000), rng.normal(0, 3, 10000)])
    uq = {q: float(np.quantile(mix, q)) for q in _Z}
    obs = []
    for a in sd.ORIGINAL_KEYS:
        for d, s in zip(dates, state):
            sigma = 3.0 if s == "Elevated" else 1.0
            r = float(rng.normal(0, sigma))
            rs = sigma if rival_knows_state else float(np.std(mix))
            arms = {"unconditional": ec._score_arm(uq, r, "all", 1000),
                    "cond": ec._score_arm({q: z * sigma for q, z in _Z.items()}, r, s, 100),
                    "noise": ec._score_arm({q: v * (1 + 0.3 * rng.standard_normal()) for q, v in uq.items()},
                                           r, "all", 1000),
                    "har_scaled": ec._score_arm({q: z * rs for q, z in _Z.items()}, r, "har", 1000)}
            obs.append({"date": d, "asset": a, "horizon": 5, "realized": r, "state": s, "arms": arms})
    return obs, dates


_WIDEN = {"kind": "width_contrast", "series": "SP500",
          "a": {"state": "Elevated"}, "b": {"state": "Normal"}, "min_ratio": 1.5}


def _prereg(arm="cond", clauses=None):
    return cb.validate({"class": "conditioner", "arm": arm, "horizon": 5, "clauses": clauses or [_WIDEN]})


def test_a_planted_state_passes_the_bar():
    obs, _ = _planted()
    got = cb.read(obs, _prereg(), sealed=True)
    assert got["verdict"] == "edge", got["reason"]
    assert got["summary"]["n_blocks"] == 60
    assert [c["n_episodes"] for c in got["clauses"][0]["cells"]] == [15, 5]   # 15 spells; 1,260 dates = 5 years


def test_a_planted_vol_forecast_is_explained_by_the_rival():
    """The state carries nothing a vol forecast that already knew σ does not:
    it clears `unconditional` and is caught at `har_scaled`."""
    obs, _ = _planted(rival_knows_state=True)
    got = cb.read(obs, _prereg(), sealed=True)
    assert got["summary"]["skill"]["skill"] > 0.02
    assert got["verdict"] == "explained_by_rival", got["reason"]


def test_noise_does_not_pass():
    obs, _ = _planted()
    assert cb.read(obs, _prereg(arm="noise"), sealed=True)["verdict"] in ("inverted", "no_edge", "miscalibrated")


def test_the_right_number_with_the_wrong_mechanism_is_unexplained():
    """A clause predicting the opposite contrast fails, and the arm that
    clears both comparators is `unexplained`, not `edge`."""
    obs, _ = _planted()
    wrong = {**_WIDEN, "a": {"state": "Normal"}, "b": {"state": "Elevated"}}
    assert cb.read(obs, _prereg(clauses=[wrong]), sealed=True)["verdict"] == "unexplained"
    left = {"kind": "median_side", "series": "SP500", "cell": {"state": "Elevated"}, "side": "left"}
    assert cb.read(obs, _prereg(clauses=[left]), sealed=True)["verdict"] == "unexplained"


def test_skill_in_state_sits_where_the_state_is():
    obs, _ = _planted()
    here = {"kind": "skill_in_state", "cell": {"state": "Elevated"}}
    assert cb.read(obs, _prereg(clauses=[here]), sealed=True)["verdict"] == "edge"
    # the planted gain is in Normal too (a narrower quote), so a null there fails
    null = {**here, "null_in": {"state": "Normal"}}
    assert cb.read(obs, _prereg(clauses=[null]), sealed=True)["verdict"] == "unexplained"


def test_a_thin_planted_cell_is_underpowered_not_an_edge():
    obs, _ = _planted(n_dates=240)                           # three Elevated runs of 20: 60 < 63
    got = cb.read(obs, _prereg(), sealed=True)
    assert got["verdict"] == "underpowered" and "cell a@5" in got["reason"]


def test_a_cell_naming_a_label_the_harness_does_not_write_is_refused():
    obs, _ = _planted(n_dates=200)
    typo = {**_WIDEN, "a": {"or_sate": "Elevated"}}
    with pytest.raises(cb.PreregError, match="or_sate"):
        cb.read(obs, _prereg(clauses=[typo]), sealed=True)


# ---------------------------------------------------------------------------
# the member's pre-registration, as its entry states it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec, says", [
    ([], "JSON object"),
    ({"class": "conditioner", "arm": "x", "clauses": [], "florr": {}}, "unknown key"),
    ({"class": "nope", "arm": "x", "clauses": []}, "class must be"),
    ({"class": "conditioner", "arm": "unconditional", "clauses": [_WIDEN]}, "not the benchmark or the rival"),
    ({"class": "conditioner", "arm": "har_scaled", "clauses": [_WIDEN]}, "not the benchmark or the rival"),
    ({"class": "conditioner", "arm": "x", "horizon": 7, "clauses": [_WIDEN]}, "horizon must be"),
    ({"class": "conditioner", "arm": "x", "clauses": []}, "non-empty list"),
    ({"class": "conditioner", "arm": "x", "clauses": [{"kind": "vibes"}]}, "kind must be"),
    ({"class": "conditioner", "arm": "x", "clauses": [{"kind": "median_side", "series": "SP500",
                                                       "cell": {"s": 1}}]}, "missing \\['side'\\]"),
    ({"class": "conditioner", "arm": "x", "clauses": [{**_WIDEN, "min_ratio": 0.8}]}, "not a widening"),
    ({"class": "conditioner", "arm": "x", "clauses": [{**_WIDEN, "horizons": [5, 60]}]}, "horizon 60"),
    ({"class": "conditioner", "arm": "x", "clauses": [{**_WIDEN, "a": {}}]}, "non-empty object"),
    ({"class": "conditioner", "arm": "x", "clauses": [{**_WIDEN, "tolerance": 0.1}]}, "unknown \\['tolerance'\\]"),
])
def test_a_pre_registration_no_bar_can_read_is_refused(spec, says):
    with pytest.raises(cb.PreregError, match=says):
        cb.validate(spec)


def _entry(field: str | None) -> str:
    body = "## H-901 — A planted entry {: #h-901 }\n\n**Status:** `draft`\n\n**What was seen.** Nothing.\n\n"
    if field is not None:
        body += f"**Pre-registration.** The width contrast, at 5d.\n\n{field}\n\n"
    return body + "**Read first.** Nothing.\n"


_JSON = '```json\n{"class": "conditioner", "arm": "dd_x_frag", "clauses": [{"kind": "skill_in_state", ' \
        '"cell": {"or_state": "Elevated"}}]}\n```'


def test_the_entry_states_its_pre_registration_in_one_json_block():
    got = cb.parse_preregistration(_entry(_JSON))
    assert got["arm"] == "dd_x_frag" and got["horizon"] == 5 and got["floor"] == cb.class_floor(C)


@pytest.mark.parametrize("field, says", [
    (None, "no `Pre-registration` field"),
    ("no json here", "exactly one"),
    (_JSON + "\n\n" + _JSON, "exactly one"),
    ("```json\n{not json}\n```", "does not parse"),
])
def test_an_entry_without_a_readable_pre_registration_is_refused(field, says):
    with pytest.raises(cb.PreregError, match=says):
        cb.parse_preregistration(_entry(field))


def test_the_audit_stamps_the_pre_registration_and_the_bar_includes_it():
    """Editing the pre-registration voids an approval (stamped text) and moves
    the bar (bar text), so it cannot be changed after the read."""
    before, after = _entry(_JSON), _entry(_JSON.replace("Elevated", "Normal"))
    assert dp.stamped_text(before) != dp.stamped_text(after)
    assert dp.bar_text(before) != dp.bar_text(after)
    assert "dd_x_frag" in dp.bar_text(before)


def test_the_cli_prints_both_bars(capsys):
    assert cb.main([]) == 0
    out = capsys.readouterr().out
    assert "conditioner: vs `unconditional`, rival `har_scaled`" in out and "not decided" in out
