"""
Tests for explore_conditioner.py — the explore-tier shadow-conditioner harness.

Offline. The point of each test is a property the register relies on: a quote
never sees a window that had not closed, the report dates stop at the seal, an
arm that cannot quote drops the observation for every arm, the collapse ladder
falls through below MIN_N, and the verdict on this harness's output is
`exploratory` and nothing stronger.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

import explore_conditioner as ec
from numeric_baseline import SEAL_START
from score_distributions import MIN_BLOCKS


def _ladder(n: int, labels: list[str] | None = None) -> list[np.ndarray]:
    every = np.array(["all"] * n, dtype=object)
    if labels is None:
        return [every]
    return [np.array(labels, dtype=object), every]


# ---------------------------------------------------------------------------
# Look-ahead
# ---------------------------------------------------------------------------

def test_quote_uses_only_windows_closed_by_the_report_date():
    """Snapshot i's h-day forward change is known at position i + h. A quote on
    report date t may use i <= t - h and nothing later — planting a huge value
    at t - h + 1 must leave the quantiles unchanged; at t - h it must move them."""
    rng = np.random.default_rng(0)
    fr = rng.normal(size=400)
    t, h = 300, 5
    base = ec.quote_arm(_ladder(400), fr, t, h)[0]

    leaked = fr.copy()
    leaked[t - h + 1] = 1e6
    assert ec.quote_arm(_ladder(400), leaked, t, h)[0] == base

    known = fr.copy()
    known[t - h] = 1e6
    assert ec.quote_arm(_ladder(400), known, t, h)[0] != base


def test_quote_ignores_the_report_date_itself():
    fr = np.arange(100, dtype=float)
    q, _, n = ec.quote_arm(_ladder(100), fr, 50, 5)
    assert n == 46                      # positions 0..45 inclusive
    assert q[0.75] <= 45.0


def test_trailing_window_uses_the_last_known_observations_only():
    fr = np.concatenate([np.full(300, -10.0), np.full(300, 10.0)])
    q, _, n = ec.quote_arm(_ladder(600), fr, 599, 5, window=250)
    assert n == 250
    assert q[0.25] == q[0.75] == 10.0


# ---------------------------------------------------------------------------
# Collapse ladder
# ---------------------------------------------------------------------------

def test_ladder_falls_through_below_min_n():
    n = 200
    fr = np.full(n, 1.0)
    fr[:5] = 100.0                      # five 'rare' days, all early
    labels = ["rare"] * 5 + ["common"] * (n - 5)
    ladder = _ladder(n, labels)
    # report date in the rare label: only 5 known rare obs < MIN_N -> 'all'
    ladder[0][199] = "rare"
    q, level, _ = ec.quote_arm(ladder, fr, 199, 5)
    assert level == "all"
    # the common label has plenty
    ladder[0][199] = "common"
    q, level, _ = ec.quote_arm(ladder, fr, 199, 5)
    assert level == "common" and q[0.50] == 1.0


def test_ladder_skips_an_undefined_level():
    n = 100
    fr = np.full(n, 2.0)
    labels = np.array([None] * n, dtype=object)
    q, level, _ = ec.quote_arm([labels, _ladder(n)[0]], fr, 99, 5)
    assert level == "all" and q[0.50] == 2.0


# ---------------------------------------------------------------------------
# Stress spells (looks A and B, 2026-09-21)
# ---------------------------------------------------------------------------

def test_stress_spells_count_runs_and_age_within_them():
    """Two runs below the edge, separated by one calm day: distinct ids, age
    restarting at 1, zero age and no id outside a run, NaN treated as calm."""
    dd = pd.Series([-0.01, -0.06, -0.08, -0.12, -0.02, -0.07, np.nan, -0.09])
    spell, age = ec.stress_spells(dd, edge=-0.05)
    assert list(age) == [0, 1, 2, 3, 0, 1, 0, 1]
    assert np.isnan(spell[0]) and np.isnan(spell[4]) and np.isnan(spell[6])
    assert list(spell[1:4]) == [1, 1, 1] and spell[5] == 2 and spell[7] == 3


def test_age_label_turns_old_after_the_edge():
    """A spell is `fresh` through its AGE_EDGE-th day and `old` from the next;
    the drawdown bin can be < −10% on day one — depth and age are separate."""
    n = ec.AGE_EDGE + 5
    dd = pd.Series([-0.12] * n)
    _, age = ec.stress_spells(dd)
    labels = np.where(age <= ec.AGE_EDGE, "fresh", "old")
    assert list(labels[:ec.AGE_EDGE]) == ["fresh"] * ec.AGE_EDGE
    assert list(labels[ec.AGE_EDGE:]) == ["old"] * 5


def test_realized_by_cell_measures_side_against_the_whole_slice():
    """`where` restricts the rows tabulated, not the unconditional median that
    'side' is read against — otherwise a stressed-only table would compare
    stressed cells to the stressed median and always find half of them right."""
    frame, fr = _tiny_world(n_days=600, start="2014-01-01")
    frame["dd_stressed"] = np.where(np.arange(len(frame)) < 100, "dd<=-5", "dd>-5")
    frame["spell_id"] = np.where(np.arange(len(frame)) < 100, 1.0, np.nan)
    fr["SP500"][5][:100] = -5.0                       # the stressed rows are all far left
    stressed = frame["dd_stressed"] == "dd<=-5"
    out = ec.realized_by_cell(frame, fr, "SP500", 5, ["dd_stressed"], where=stressed)
    assert list(out.index) == ["dd<=-5"]
    assert out.loc["dd<=-5", "side"] == "left" and out.loc["dd<=-5", "spells"] == 1
    assert out.loc["dd<=-5", "uncond_p50"] > -5.0     # the slice's median, not the cell's


# ---------------------------------------------------------------------------
# The slice, alignment and the verdict
# ---------------------------------------------------------------------------

def _tiny_world(n_days: int = 900, start: str = "2015-01-01"):
    """A frame whose OR flag is evaluable from day 0 (so BURN_IN alone sets the
    first report date) and whose forward changes are white noise."""
    dates = pd.bdate_range(start, periods=n_days)
    frame = pd.DataFrame(index=dates)
    frame["bucket"] = "NFCI:mid|YC:positive|CREDIT:mid"
    frame["nfci"] = "NFCI:mid"
    frame["or_state"] = np.where(np.arange(n_days) % 10 == 0, "Elevated", "Normal")
    frame["comp_state"] = "Normal"
    frame["dd_bin"] = "dd>-5"
    frame["dd_stressed"] = "dd>-5"
    frame["spell_id"] = np.nan
    frame["dd_age"] = "calm"
    frame["sp_sign"] = np.where(np.arange(n_days) % 2 == 0, "down5", "up5")
    rng = np.random.default_rng(1)
    fr = {a.key: {h: rng.normal(size=n_days) for h in ec.HORIZONS} for a in ec.ASSETS}
    for a in ec.ASSETS:
        for h in ec.HORIZONS:
            fr[a.key][h][-h:] = np.nan          # unresolved tail
    return frame, fr


def test_report_dates_stop_strictly_before_the_seal():
    frame, fr = _tiny_world(n_days=1200, start="2014-06-01")
    assert frame.index[-1] > pd.Timestamp(SEAL_START)
    obs = ec.build_observations(frame, fr, ec.arm_labels(frame))
    assert obs
    assert max(o["date"] for o in obs) < SEAL_START.isoformat()
    assert min(o["date"] for o in obs) >= frame.index[ec.BURN_IN].date().isoformat()


def test_every_observation_carries_every_arm():
    frame, fr = _tiny_world()
    obs = ec.build_observations(frame, fr, ec.arm_labels(frame))
    assert obs
    assert all(set(o["arms"]) == set(ec.ARMS) for o in obs)


def test_an_arm_that_cannot_quote_drops_the_observation_for_all_arms():
    frame, fr = _tiny_world()
    ladders = ec.arm_labels(frame)
    ladders["frag_or"] = [np.array([None] * len(frame), dtype=object)]   # no fallback
    assert ec.build_observations(frame, fr, ladders) == []


def test_the_verdict_can_only_be_exploratory():
    frame, fr = _tiny_world()
    obs = ec.build_observations(frame, fr, ec.arm_labels(frame))
    for arm in ec.ARMS:
        if arm == ec.BENCH:
            continue
        s = ec.summarize_arm(obs, arm, 5)
        assert s["verdict"]["verdict"] == "exploratory"
        # not a power artefact: the slice has more blocks than the sealed bar
        # needs, and the verdict is still nothing stronger than exploratory
        assert s["n_blocks"] >= MIN_BLOCKS


def test_identical_arms_have_zero_skill_and_a_degenerate_interval():
    frame, fr = _tiny_world()
    obs = ec.build_observations(frame, fr, ec.arm_labels(frame))
    sub = [o for o in obs if o["asset"] == "SP500" and o["horizon"] == 5]
    for o in sub:
        o["arms"]["clone"] = dict(o["arms"]["unconditional"])
    ci = ec.skill_ci(sub, "clone", n_boot=200)
    assert ci["lo"] == ci["hi"] == 0.0
    assert ec.skill_vs(sub, "clone") == 0.0


def test_the_harness_is_research_tier():
    import product_surface as ps
    assert ps.tier_of("explore_conditioner") == "RESEARCH"


# ---------------------------------------------------------------------------
# The optional HAR arms (H-006's rival)
# ---------------------------------------------------------------------------

def _closes(n: int = 1300, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n))), index=idx)


def test_har_sigma_uses_only_closes_at_or_before_the_report_date():
    """The product fits HAR on the closes it has at the report date. A jump the
    day after must leave the forecast unchanged; a jump on the date must move it."""
    closes = _closes()
    asof = closes.index[1200]
    base = ec.har_sigma(closes, asof)
    assert base is not None and base > 0

    later = closes.copy()
    later.iloc[1201:] *= 3.0
    assert ec.har_sigma(later, asof) == base

    same_day = closes.copy()
    same_day.iloc[1200] *= 1.2
    assert ec.har_sigma(same_day, asof) != base


def test_har_sigma_refuses_a_history_shorter_than_the_product_gate():
    from vol_forecast import HAR_MIN_RETURNS
    closes = _closes(n=HAR_MIN_RETURNS - 50)
    assert ec.har_sigma(closes, closes.index[-1]) is None
    # and never sees beyond `window` closes back
    long = _closes(n=3000)
    assert ec.har_sigma(long, long.index[-1]) == ec.har_sigma(long.iloc[-ec.HAR_WINDOW:], long.index[-1])


def test_har_scaled_keeps_the_median_and_rescales_the_width():
    sp = ec.BY_KEY["SP500"]
    uncond = {0.25: -1.0, 0.50: 0.3, 0.75: 1.6}
    sigma = 16.0                                   # annualised, pct
    known_sd = 2.0
    q = ec.har_scaled_quantiles(uncond, sigma, 5, sp, known_sd)
    r = sigma * np.sqrt(5 / 252) / known_sd
    assert q[0.50] == pytest.approx(0.3)
    assert q[0.75] - q[0.25] == pytest.approx(2.6 * r)
    assert ec.har_scaled_quantiles(uncond, sigma, 5, ec.BY_KEY["UST10Y"], known_sd) is None
    assert ec.har_scaled_quantiles(uncond, sigma, 5, sp, 0.0) is None


def test_an_optional_arm_never_drops_an_observation():
    """`har_*` are quoted where a forecast exists and absent otherwise; the
    required arms' sample is the same either way (WP-21.A.2's rule for the
    scorer's `har_gaussian`)."""
    frame, fr = _tiny_world()
    ladders = ec.arm_labels(frame)
    without = ec.build_observations(frame, fr, ladders)
    sig = np.full(len(frame), np.nan)
    sig[ec.BURN_IN + 100:] = 15.0                  # a forecast from some date on, SP500 only
    with_ = ec.build_observations(frame, fr, ladders, sigmas={"SP500": sig})
    assert len(with_) == len(without)
    assert not any("har_gaussian" in o["arms"] for o in without)
    sp = [o for o in with_ if o["asset"] == "SP500"]
    assert any("har_gaussian" in o["arms"] and "har_scaled" in o["arms"] for o in sp)
    assert not all("har_gaussian" in o["arms"] for o in sp)
    assert not any("har_gaussian" in o["arms"] for o in with_ if o["asset"] != "SP500")
    # and the read of an optional arm is on its own subsample
    s = ec.summarize_arm(with_, "har_gaussian", 5)
    assert s["n"] == sum("har_gaussian" in o["arms"] for o in with_ if o["horizon"] == 5)
    assert s["n_report_dates"] < ec.summarize_arm(with_, "dd_bin", 5)["n_report_dates"]
    assert s["verdict"]["verdict"] == "exploratory"
