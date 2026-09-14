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
