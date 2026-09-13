"""Tests for companion_testing (IMP-7, the companion measures).

Synthetic panels only — no network. The real run is `python
companion_testing.py`; its trio reference row is checked against
`fragility_or._pit_backtest` in the run itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import companion_testing as ct
from companion_testing import (
    dispersion_signal, pairwise_corr_signal, breadth_signal,
    eigen_concentration_signal, build_companions, score_companion, verdict,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _panel(n=300, k=9, seed=0, rho=0.0):
    """k sector price paths on a business-day index with pairwise return
    correlation `rho` (one common factor)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    f = rng.normal(0, 0.01, n)
    e = rng.normal(0, 0.01, (n, k))
    r = np.sqrt(rho) * f[:, None] + np.sqrt(1 - rho) * e
    px = pd.DataFrame(100.0 * np.exp(np.cumsum(r, axis=0)), index=idx,
                      columns=[f"s{i}" for i in range(k)])
    return px


def _sliced(px):
    return {c: px[c] for c in px.columns}


def _admit_row(h=(5, 10)):
    """A row that clears every disqualifier AND admits — the disqualifier tests
    each break one thing and assert the admit clause is never reached."""
    return {
        "companion": "x",
        "standalone": {hh: {"auc_nonoverlap": 0.70} for hh in h},
        "pit": {hh: {"n_episodes": 15, "caught": 12, "ref_caught": 10,
                     "precision": 0.33, "ref_precision": 0.33} for hh in h},
        "loco": {hh: {"caught": 11, "ref_caught": 10} for hh in h},
    }


# ---------------------------------------------------------------------------
# the bar — disqualifiers first (CLAUDE.md #7, KB-027)
# ---------------------------------------------------------------------------

def test_admit_row_admits():
    assert verdict(_admit_row())["verdict"] == "admit"


def test_no_standalone_skill_fires_ahead_of_a_strong_recall_gain():
    row = _admit_row()
    row["standalone"][5]["auc_nonoverlap"] = ct.AUC_BAR       # <= bar, not <
    assert verdict(row)["verdict"] == "no_standalone_skill"
    row["standalone"][5]["auc_nonoverlap"] = None
    assert verdict(row)["verdict"] == "no_standalone_skill"


def test_standalone_gate_is_the_5d_auc_only():
    row = _admit_row()
    row["standalone"][10]["auc_nonoverlap"] = 0.40
    assert verdict(row)["verdict"] == "admit"


def test_underpowered_fires_ahead_of_a_strong_recall_gain():
    row = _admit_row()
    row["pit"][5]["n_episodes"] = ct.MIN_EPISODES - 1
    assert verdict(row)["verdict"] == "underpowered"


def test_precision_lost_fires_ahead_of_a_strong_recall_gain():
    row = _admit_row()
    row["pit"][10]["precision"] = row["pit"][10]["ref_precision"] - ct.PREC_TOL - 0.001
    assert verdict(row)["verdict"] == "precision_lost"
    row["pit"][10]["precision"] = row["pit"][10]["ref_precision"] - ct.PREC_TOL
    assert verdict(row)["verdict"] == "admit"


def test_disqualifiers_are_checked_in_order():
    row = _admit_row()
    row["standalone"][5]["auc_nonoverlap"] = 0.5
    row["pit"][5]["n_episodes"] = 3
    row["pit"][5]["precision"] = 0.0
    assert verdict(row)["verdict"] == "no_standalone_skill"
    row["standalone"][5]["auc_nonoverlap"] = 0.7
    assert verdict(row)["verdict"] == "underpowered"
    row["pit"][5]["n_episodes"] = 15
    assert verdict(row)["verdict"] == "precision_lost"


def test_admit_needs_recall_up_at_both_horizons():
    row = _admit_row()
    row["pit"][10]["caught"] = row["pit"][10]["ref_caught"]
    v = verdict(row)
    assert v["verdict"] == "redundant" and "did not rise" in v["reason"]


def test_admit_needs_loco_recall_held():
    row = _admit_row()
    row["loco"][5]["caught"] = row["loco"][5]["ref_caught"] - 1
    v = verdict(row)
    assert v["verdict"] == "redundant" and "LOCO" in v["reason"]


def test_a_companion_that_re_flags_the_trios_crises_is_redundant():
    row = _admit_row()
    for h in (5, 10):
        row["pit"][h]["caught"] = row["pit"][h]["ref_caught"]
        row["loco"][h]["caught"] = row["loco"][h]["ref_caught"]
    assert verdict(row)["verdict"] == "redundant"


# ---------------------------------------------------------------------------
# the four measures
# ---------------------------------------------------------------------------

def test_dispersion_is_zero_when_sectors_move_together_and_positive_otherwise():
    px = _panel()
    same = pd.DataFrame({f"s{i}": px["s0"] for i in range(5)})
    assert dispersion_signal(_sliced(same)) == pytest.approx(0.0)
    assert dispersion_signal(_sliced(px)) > 0


def test_pairwise_corr_tracks_the_planted_factor():
    lo = pairwise_corr_signal(_sliced(_panel(rho=0.0, n=600)))
    hi = pairwise_corr_signal(_sliced(_panel(rho=0.8, n=600)))
    assert -0.2 < lo < 0.2
    assert hi > 0.6
    same = pd.DataFrame({f"s{i}": _panel()["s0"] for i in range(4)})
    assert pairwise_corr_signal(_sliced(same)) == pytest.approx(1.0)


def test_breadth_is_the_fraction_below_the_sma_and_higher_means_narrower():
    idx = pd.date_range("2015-01-01", periods=200, freq="B")
    down = pd.Series(np.linspace(200, 100, 200), index=idx)     # always below SMA
    up = pd.Series(np.linspace(100, 200, 200), index=idx)       # always above
    assert breadth_signal({"a": down, "b": down, "c": down}) == pytest.approx(1.0)
    assert breadth_signal({"a": up, "b": up, "c": up}) == pytest.approx(0.0)
    assert breadth_signal({"a": up, "b": up, "c": down, "d": down}) == pytest.approx(0.5)


def test_eigen_concentration_is_the_effective_number_of_loaded_sectors():
    # one common factor loading everyone equally -> participation ~ k
    k = 9
    hi = eigen_concentration_signal(_sliced(_panel(k=k, rho=0.9, n=600)))
    assert 7.5 < hi <= k + 1e-9
    # two sectors alone share a factor, the other seven are noise -> ~2
    px = _panel(k=k, rho=0.0, n=600)
    r = np.log(px / px.shift(1)).dropna()
    r["s1"] = r["s0"] * 0.95 + r["s1"] * 0.05
    px2 = 100.0 * np.exp(r.cumsum())
    lo = eigen_concentration_signal(_sliced(px2))
    assert lo < 3.5
    assert eigen_concentration_signal(_sliced(px2)) >= 1.0


def test_measures_return_none_on_a_short_or_narrow_panel():
    px = _panel(n=30)
    assert pairwise_corr_signal(_sliced(px)) is None
    assert eigen_concentration_signal(_sliced(px)) is None
    assert breadth_signal(_sliced(px)) is None
    two = _sliced(_panel(n=300, k=2))
    assert dispersion_signal(two) is None
    assert pairwise_corr_signal(two) is None


# ---------------------------------------------------------------------------
# the walk and the scoring
# ---------------------------------------------------------------------------

def test_build_companions_is_look_ahead_safe():
    px = _panel(n=400)
    anchor = px.index[::5]
    full = build_companions(px, anchor)
    cut = px.index[250]
    trunc = build_companions(px.loc[:cut], anchor[anchor <= cut])
    for n in ct.COMPANIONS:
        a = full[n].reindex(trunc[n].index)
        pd.testing.assert_series_equal(a, trunc[n], check_names=False)
        assert full[n].index.isin(anchor).all()
        assert full[n].notna().all()


def _channels_with_companion(n=900, seed=0):
    """Trio + a companion on a strided grid over a ^GSPC with planted drops."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2012-01-01", periods=n * 5, freq="B")
    close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.003, len(days)))),
                      index=days)
    idx = days[::5]
    ch = {"common": idx, "gspc": close}
    for k in ct._CH_KEYS:
        ch[k] = pd.Series(rng.uniform(0, 1, n), index=idx)
    comp = pd.Series(rng.uniform(0, 1, n), index=idx)
    comp.iloc[:40] = np.nan                      # companion starts later
    return ch, comp


def test_score_companion_scores_trio_and_quartet_on_the_shared_window():
    ch, comp = _channels_with_companion()
    row = score_companion("X", comp, ch, verbose=False)
    n_shared = int(comp.notna().sum())
    assert row["window"][0] == n_shared
    assert row["window"][1] == n_shared - ct._MIN_WARMUP
    for h in (5, 10):
        p = row["pit"][h]
        # a random 4th channel can only add alarms / catches, never remove them
        assert p["caught"] >= p["ref_caught"]
        assert p["n_alarms"] >= 0 and p["ref_n_alarms"] >= 0
        l = row["loco"][h]
        assert l["caught"] >= l["ref_caught"]
        assert all(hit for (_s, _e, hit) in l["differs"])
    assert set(row["standalone"][5]) >= {"auc_nonoverlap", "episode_recall", "n_crises"}
