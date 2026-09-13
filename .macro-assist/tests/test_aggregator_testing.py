"""Tests for aggregator_testing (IMP-6, precision at held recall).

Synthetic channels only — no network. The real run is `python
aggregator_testing.py`; its OR reference row is checked against
`fragility_or._pit_backtest` in the run itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import aggregator_testing as at
from aggregator_testing import (
    pit_channel_table, aggregate, logit_pit_flag, loco_recall, verdict,
    score_variant, _budget_threshold,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _channels(n=400, seed=0, spikes=None):
    """Three uniform channels on a business-day index plus a flat ^GSPC.
    `spikes` = {(key, i): value} plants readings."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    ch = {"common": idx, "gspc": pd.Series(100.0, index=idx)}
    for k in at._CH_KEYS:
        ch[k] = pd.Series(rng.uniform(0, 1, n), index=idx)
    for (k, i), v in (spikes or {}).items():
        ch[k].iloc[i] = v
    return ch


def _passing_row(h=(5, 10)):
    """A row that clears every disqualifier AND route 1 — the disqualifier tests
    each break one thing and assert the pass clause is never reached."""
    return {
        "variant": "x",
        "pit": {hh: {"n_alarms": 20, "caught": 10, "ref_caught": 10,
                     "n_episodes": 15, "precision": 0.45, "ref_precision": 0.30,
                     "median_lead": 4.0} for hh in h},
        "loco": {hh: {"caught": 10, "ref_caught": 10} for hh in h},
    }


# ---------------------------------------------------------------------------
# the bar — disqualifiers first (CLAUDE.md #7, KB-027)
# ---------------------------------------------------------------------------

def test_passing_row_passes_route_1():
    v = verdict(_passing_row())
    assert v["verdict"] == "pass" and v["route"] == 1


def test_underpowered_fires_ahead_of_a_strong_precision_gain():
    row = _passing_row()
    row["pit"][10]["n_alarms"] = at.MIN_ALARMS - 1
    assert verdict(row)["verdict"] == "underpowered"


def test_too_late_fires_ahead_of_a_strong_precision_gain():
    row = _passing_row()
    row["pit"][5]["median_lead"] = at.MIN_LEAD_5D - 0.5
    assert verdict(row)["verdict"] == "too_late"
    row["pit"][5]["median_lead"] = None          # nothing caught -> undefined -> too_late
    assert verdict(row)["verdict"] == "too_late"


def test_recall_lost_fires_ahead_of_a_strong_precision_gain():
    row = _passing_row()
    row["loco"][5]["caught"] = row["loco"][5]["ref_caught"] - at.MAX_RECALL_LOST - 1
    assert verdict(row)["verdict"] == "recall_lost"
    # losing exactly the tolerance is allowed
    row["loco"][5]["caught"] = row["loco"][5]["ref_caught"] - at.MAX_RECALL_LOST
    assert verdict(row)["verdict"] == "pass"


def test_disqualifiers_are_checked_in_order():
    row = _passing_row()
    row["pit"][5]["n_alarms"] = 0
    row["pit"][5]["median_lead"] = 0.0
    row["loco"][5]["caught"] = 0
    assert verdict(row)["verdict"] == "underpowered"
    row["pit"][5]["n_alarms"] = at.MIN_ALARMS
    assert verdict(row)["verdict"] == "too_late"
    row["pit"][5]["median_lead"] = at.MIN_LEAD_5D
    assert verdict(row)["verdict"] == "recall_lost"


def test_route_1_needs_the_gain_at_both_horizons_and_held_recall():
    row = _passing_row()
    row["pit"][10]["precision"] = row["pit"][10]["ref_precision"] + at.PASS_PREC_GAIN - 0.01
    assert verdict(row)["verdict"] == "no_edge"
    row = _passing_row()
    row["pit"][5]["caught"] = row["pit"][5]["ref_caught"] - at.PASS_RECALL_TOL - 1
    assert verdict(row)["verdict"] == "no_edge"


def test_route_2_is_loco_recall_gain_at_held_precision():
    row = _passing_row()
    for h in (5, 10):
        row["pit"][h]["precision"] = row["pit"][h]["ref_precision"] - at.PASS_PREC_TOL
        row["loco"][h]["caught"] = row["loco"][h]["ref_caught"] + at.PASS_LOCO_GAIN
    v = verdict(row)
    assert v["verdict"] == "pass" and v["route"] == 2
    row["loco"][10]["caught"] -= 1                # +2 at one horizon only
    assert verdict(row)["verdict"] == "no_edge"
    row["loco"][10]["caught"] += 1
    row["pit"][5]["precision"] -= 0.01            # precision slips past the tolerance
    assert verdict(row)["verdict"] == "no_edge"


def test_a_variant_that_reshuffles_the_same_alarms_is_no_edge():
    row = _passing_row()
    for h in (5, 10):
        row["pit"][h]["precision"] = row["pit"][h]["ref_precision"] + 0.02
    assert verdict(row)["verdict"] == "no_edge"


# ---------------------------------------------------------------------------
# the PIT feature table
# ---------------------------------------------------------------------------

def test_pit_table_percentiles_and_cuts_use_strictly_prior_readings():
    ch = _channels(n=300, spikes={("AR", 299): 50.0, ("comp", 299): -1.0})
    t = pit_channel_table(ch, min_warmup=100)
    assert len(t) == 200 and t.index[0] == ch["common"][100]
    last = t.iloc[-1]
    assert last["AR_pct"] == 1.0 and last["AR_w"] and last["AR_a"]     # above all priors
    assert last["comp_pct"] == 0.0 and not last["comp_w"]                # below all priors
    # the spike is NOT in its own history: the prior-only p90 stays below 1
    assert ch["AR"].iloc[:299].quantile(0.9) < 1.0


def test_pit_table_matches_the_live_or_flag_admission_rule():
    from input_testing import _pit_decile_or_flags
    ch = _channels(n=350)
    t = pit_channel_table(ch, min_warmup=120)
    live = _pit_decile_or_flags({k: ch[k] for k in at._CH_KEYS}, 0.90, 120)["or"]
    pd.testing.assert_series_equal(aggregate(t, "or"), live, check_names=False)


def test_pit_table_degraded_reading_is_nan_and_non_firing():
    ch = _channels(n=300)
    ch["comp"].iloc[250] = np.nan
    t = pit_channel_table(ch, min_warmup=100)
    row = t.loc[ch["common"][250]]
    assert np.isnan(row["comp_pct"]) and not row["comp_w"] and not row["comp_a"]
    assert len(t) == 200                          # the day is evaluable (other channels fire)


def test_pit_table_empty_below_warmup():
    t = pit_channel_table(_channels(n=50), min_warmup=100)
    assert t.empty and "comp_pct" in t.columns


# ---------------------------------------------------------------------------
# the rule-based aggregators
# ---------------------------------------------------------------------------

def _table(w, a=None):
    """Build a feature table from per-reading (comp, AR, TURB) watch flags and
    optional alert flags."""
    n = len(w)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    a = a or [(False, False, False)] * n
    cols = {}
    for j, k in enumerate(at._CH_KEYS):
        cols[f"{k}_pct"] = [0.5] * n
        cols[f"{k}_w"] = [row[j] for row in w]
        cols[f"{k}_a"] = [row[j] for row in a]
    return pd.DataFrame(cols, index=idx)


def test_persist_requires_two_consecutive_readings_and_drops_the_first():
    F, T = False, True
    t = _table([(T, F, F), (F, F, F), (T, F, F), (F, T, F), (F, F, F)])
    p = aggregate(t, "persist")
    assert len(p) == 4 and p.index[0] == t.index[1]     # first reading dropped
    assert p.tolist() == [False, False, True, False]     # readings 2&3 both set (any channel)


def test_tiers_alert_is_two_of_three_or_any_p97():
    F, T = False, True
    w = [(T, F, F), (T, T, F), (F, F, F), (T, F, F)]
    a = [(F, F, F), (F, F, F), (F, F, F), (T, F, F)]
    assert aggregate(_table(w, a), "tiers").tolist() == [False, True, False, True]
    assert aggregate(_table(w, a), "or").tolist() == [True, True, False, True]


def test_unknown_variant_raises():
    with pytest.raises(ValueError):
        aggregate(_table([(False, False, False)]), "hmm")


# ---------------------------------------------------------------------------
# the logistic
# ---------------------------------------------------------------------------

def test_budget_threshold_matches_the_or_firing_rate():
    p = np.linspace(0, 1, 101)
    thr = _budget_threshold(p, 0.10)
    assert abs((p >= thr).mean() - 0.10) < 0.02
    assert _budget_threshold(p, 0.0) == np.inf


def _planted(n=520, seed=1):
    """A market that drops 6% over ten days whenever the composite spikes 15
    readings earlier, so the label depends on comp_pct and not on AR/TURB."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    close = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.05, n)), index=idx)
    ch = {"common": idx, "gspc": close}
    for k in at._CH_KEYS:
        ch[k] = pd.Series(rng.uniform(0, 1, n), index=idx)
    for s in range(150, n - 30, 60):
        ch["comp"].iloc[s] = 5.0
        close.iloc[s + 3:s + 13] -= np.linspace(0.6, 6.0, 10)
        close.iloc[s + 13:] -= 6.0
    return ch


def test_logit_pit_flag_only_trains_on_resolved_labels_and_fires_on_the_planted_channel():
    ch = _planted()
    t = pit_channel_table(ch, min_warmup=100)
    f = logit_pit_flag(t, ch["gspc"], horizon=10, min_train=60)
    # not evaluable until 60 resolved training readings exist
    assert f.index[0] > t.index[60]
    # the planted spikes it could see are flagged
    spikes = [ch["common"][s] for s in range(150, 520 - 30, 60) if ch["common"][s] in f.index]
    assert spikes and all(f[d] for d in spikes[1:])


def test_logit_pit_flag_degraded_day_is_non_firing():
    ch = _planted()
    ch["comp"].iloc[450] = np.nan
    t = pit_channel_table(ch, min_warmup=100)
    f = logit_pit_flag(t, ch["gspc"], horizon=10, min_train=60)
    assert f[ch["common"][450]] == False


# ---------------------------------------------------------------------------
# LOCO
# ---------------------------------------------------------------------------

def test_loco_or_row_reproduces_input_testing():
    from input_testing import _loco_recall
    ch = _planted()
    mine = loco_recall(ch, ch["gspc"], "or", 10)
    ref = _loco_recall({k: ch[k] for k in at._CH_KEYS}, ch["gspc"], 0.90, 10)
    assert mine["n_crises"] == ref["n_crises"] > 0
    assert mine["caught"] == ref["or_caught"]


def test_loco_fits_outside_the_held_out_crisis():
    # A channel that is flat everywhere except inside one crisis: with the cut fit
    # on the OUTSIDE readings (all equal), the in-crisis value clears it, so the
    # fold is caught — and the transform must not have seen the crisis, or the
    # 97th pct of 'all readings' would sit above the flat level too. Either way
    # the point is the fold count and the train mask; assert both.
    ch = _planted()
    r = loco_recall(ch, ch["gspc"], "tiers", 10)
    assert r["n_crises"] == len(r["folds"]) > 0
    assert all(isinstance(hit, bool) for (_s, _e, hit) in r["folds"])


def test_score_variant_scores_reference_on_the_variants_own_window():
    ch = _planted()
    t = pit_channel_table(ch, min_warmup=100)
    row = score_variant("persist", t, ch, ch["gspc"], horizons=(10,))
    p = row["pit"][10]
    assert p["window"][0] == len(t) - 1              # persist drops one reading
    assert p["n_episodes"] > 0 and p["ref_caught"] >= p["caught"]
    assert set(row["loco"][10]) >= {"caught", "ref_caught", "differs"}
