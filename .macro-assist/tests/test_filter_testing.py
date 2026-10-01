"""Tests for filter_testing (IMP-9 §9.A, an outside input as a filter on the OR
flag). Synthetic series only — no network. The bar is improvement-track.md
IMP-9 §9.A; these pin it to the code before the run."""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import aggregator_testing as at
import filter_testing as ft


# ---------------------------------------------------------------------------
# the constants are the bar's
# ---------------------------------------------------------------------------

def test_the_constants_are_the_written_bar():
    assert (ft.SMOOTH, ft.BASE, ft.STALE_DAYS) == (5, 252, 10)
    assert (ft.DECISIVE, ft.HORIZONS, ft.DD_THRESHOLD) == (5, (5, 10), 0.05)
    assert (ft.MIN_ALARMS, ft.MIN_LEAD_5D, ft.MAX_RECALL_LOST) == (10, 2.0, 0)
    assert (ft.PASS_PREC_GAIN, ft.LIVE_PREC_FLOOR) == (0.05, 0.40)
    assert (ft.N_SHIFT, ft.LUCK_Q, ft.MIN_SHIFT) == (200, 0.90, 52)
    assert ft.VERDICTS == ("underpowered", "too_late", "recall_lost", "no_edge", "luck", "pass")


# ---------------------------------------------------------------------------
# the input
# ---------------------------------------------------------------------------

def _skew(vals, start="2000-01-03"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype=float)


def test_x_reads_only_cboe_days_strictly_before_the_reading():
    s = _skew(np.r_[np.full(300, 100.0), 200.0])         # a spike on the last day
    t = s.index[-1]
    f = ft.skew_filter(s, pd.DatetimeIndex([t, t + pd.offsets.BDay(1)]))
    assert f["x"].iloc[0] == 0.0                         # the spike is not known on its own day
    assert f["x"].iloc[1] == pytest.approx(20.0)         # the day after: (4·100 + 200)/5 − 100


def test_x_is_the_five_day_mean_less_the_trailing_year_median():
    rng = np.random.default_rng(0)
    s = _skew(120 + rng.normal(0, 3, 600))
    t = s.index[400]
    x = ft.skew_filter(s, pd.DatetimeIndex([t]))["x"].iloc[0]
    prior = s[s.index < t]
    assert x == pytest.approx(prior.iloc[-5:].mean() - prior.iloc[-252:].median())


def test_a_trend_alone_does_not_read_high_forever():
    """Against the trailing year, a level that has drifted up and stays put
    reads back at zero; a whole-history percentile would read high forever."""
    s = _skew(np.r_[np.linspace(100, 150, 800), np.full(400, 150.0)])
    x = ft.skew_filter(s, s.index[-5:])["x"]
    assert (x.abs() < 1e-9).all()


def test_too_little_history_drops_the_reading_and_stale_fails_open():
    s = _skew(np.r_[np.full(300, 100.0), np.full(10, 80.0)])     # ends low: x < 0
    early = s.index[ft.BASE + ft.SMOOTH - 1]                         # 256 prior closes
    ok = s.index[ft.BASE + ft.SMOOTH]                                # 257
    f = ft.skew_filter(s, pd.DatetimeIndex([early, ok]))
    assert not f["ready"].iloc[0] and not f["passes"].iloc[0]
    assert f["ready"].iloc[1]
    last = s.index[-1]
    fresh = ft.skew_filter(s, pd.DatetimeIndex([last + pd.Timedelta(days=1)]))
    assert fresh["x"].iloc[0] < 0 and not fresh["passes"].iloc[0]    # low fear blocks the firing
    gone = ft.skew_filter(s, pd.DatetimeIndex([last + pd.Timedelta(days=ft.STALE_DAYS + 1)]))
    assert gone["stale"].iloc[0] and gone["passes"].iloc[0]         # a dead feed never silences
    assert np.isnan(gone["x"].iloc[0])


def test_parse_cboe_reads_both_file_shapes():
    one = "DATE,SKEW\n01/03/2000,120.5\n01/04/2000,121.0\n"
    ohlc = "DATE,OPEN,HIGH,LOW,CLOSE\n01/03/2000,1,2,0.5,1.5\n"
    assert ft.parse_cboe(one).tolist() == [120.5, 121.0]
    assert ft.parse_cboe(ohlc).tolist() == [1.5]


# ---------------------------------------------------------------------------
# the bar — disqualifiers first (CLAUDE.md #7, KB-027)
# ---------------------------------------------------------------------------

def _passing_row(floor=0.40):
    return {
        "floor": floor,
        "pit": {5: {"n_alarms": 20, "caught": 12, "ref_caught": 12, "n_episodes": 18,
                    "precision": 0.50, "ref_precision": 0.30, "median_lead": 4.0},
                10: {"n_alarms": 1, "caught": 0, "ref_caught": 9, "n_episodes": 20,
                     "precision": 0.0, "ref_precision": 0.3, "median_lead": None}},
        "loco": {5: {"caught": 12, "ref_caught": 12}, 10: {"caught": 0, "ref_caught": 9}},
        "luck": {"n": 200, "q": 0.38, "median": 0.30},
    }


def test_a_passing_row_passes_and_10d_is_not_read():
    assert ft.verdict(_passing_row())["verdict"] == "pass"


@pytest.mark.parametrize("breaks, expected", [
    (lambda r: r["pit"][5].update(n_alarms=ft.MIN_ALARMS - 1), "underpowered"),
    (lambda r: r["pit"][5].update(median_lead=ft.MIN_LEAD_5D - 0.5), "too_late"),
    (lambda r: r["pit"][5].update(median_lead=None), "too_late"),
    (lambda r: r["pit"][5].update(caught=11), "recall_lost"),
    (lambda r: r["loco"][5].update(caught=11), "recall_lost"),
    (lambda r: r["pit"][5].update(precision=0.34), "no_edge"),
    (lambda r: r["pit"][5].update(precision=None), "no_edge"),
    (lambda r: r["luck"].update(q=0.50), "luck"),
    (lambda r: r["luck"].update(q=None), "luck"),
])
def test_each_disqualifier_fires_alone_ahead_of_a_strong_precision(breaks, expected):
    row = _passing_row()
    breaks(row)
    assert ft.verdict(row)["verdict"] == expected


def test_disqualifiers_are_checked_in_order():
    row = _passing_row()
    row["pit"][5].update(n_alarms=3, median_lead=None, caught=0, precision=0.0)
    row["luck"]["q"] = 0.9
    order = []
    for fix in (lambda r: r["pit"][5].update(n_alarms=20),
                lambda r: r["pit"][5].update(median_lead=4.0),
                lambda r: r["pit"][5].update(caught=12),
                lambda r: r["pit"][5].update(precision=0.5),
                lambda r: r["luck"].update(q=0.3)):
        order.append(ft.verdict(row)["verdict"])
        fix(row)
    order.append(ft.verdict(row)["verdict"])
    assert order == list(ft.VERDICTS)


def test_the_live_floor_binds_above_the_relative_gain():
    row = _passing_row()
    row["pit"][5].update(precision=0.38, ref_precision=0.25)      # +0.13, below 0.40
    row["luck"]["q"] = 0.30
    assert ft.verdict(row)["verdict"] == "no_edge"
    row["floor"] = None                                           # the long window has none
    assert ft.verdict(row)["verdict"] == "pass"


def test_gaining_crises_is_not_a_loss():
    row = _passing_row()
    row["loco"][5]["caught"] = 13
    assert ft.verdict(row)["verdict"] == "pass"


def test_overall_needs_every_window():
    p = {"verdict": {"verdict": "pass"}}
    f = {"verdict": {"verdict": "recall_lost"}}
    assert ft.overall({"live": p, "long": p}) == "pass"
    assert ft.overall({"live": p, "long": f}) == "fail"
    assert ft.overall({}) == "fail"


# ---------------------------------------------------------------------------
# scoring on a planted market
# ---------------------------------------------------------------------------

def _planted(n_days=3000, seed=4):
    """A daily close with planted 8% drops, each starting the day after a grid
    reading, so that reading's 5-day label sees the whole drop; a two-channel
    grid (stride 5) on which channel A spikes on that reading and at random
    false-alarm readings; SKEW above its year before the real drops and below
    it before the false ones."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("1995-01-02", periods=n_days)
    r = rng.normal(0.0003, 0.004, n_days)
    drops = list(range(1701, n_days - 60, 120))      # 1700 is a grid day
    for d in drops:
        r[d:d + 4] = -0.021
    close = pd.Series(100 * np.cumprod(1 + r), index=days)
    grid = days[::5]
    A = pd.Series(rng.uniform(0, 1, len(grid)), index=grid)
    B = pd.Series(rng.uniform(0, 1, len(grid)), index=grid)
    gpos = {d: grid.searchsorted(days[d]) for d in drops}
    for g in gpos.values():
        A.iloc[g - 1] = 5.0
    false = [g for g in rng.choice(np.arange(400, len(grid) - 2), 30, replace=False)
             if all(abs(g - x) > 6 for x in gpos.values())]
    for g in false:
        A.iloc[g] = 5.0
    skew = pd.Series(120.0 + rng.normal(0, 1, n_days), index=days)
    for d in drops:
        skew.iloc[d - 15:d] = 140.0                       # fear up before the real ones
    for g in false:
        at_ = days.get_loc(grid[g])
        skew.iloc[at_ - 8:at_] = 100.0                    # and down before the false ones
    return {"name": "t", "channels": {"A": A, "B": B}, "keys": ("A", "B"),
            "close": close, "floor": None, "what": "planted"}, skew, len(false)


def test_a_filter_that_sees_the_drops_keeps_every_crisis_and_lifts_precision():
    win, skew, n_false = _planted()
    row = ft.score_window(win, skew)
    p = row["pit"][5]
    assert p["caught"] == p["ref_caught"] and p["ref_caught"] >= 8
    assert p["precision"] >= p["ref_precision"] + ft.PASS_PREC_GAIN   # channel B's noise stays in
    assert row["loco"][5]["caught"] == row["loco"][5]["ref_caught"]
    assert row["blocked"] >= n_false
    assert row["luck"]["q"] < p["precision"]
    assert ft.verdict(row)["verdict"] == "pass"


def test_a_filter_that_blocks_everything_loses_every_crisis():
    win, skew, _ = _planted()
    low = skew * 0 + 120.0
    low.iloc[-400:] = 100.0                               # fear below its year: blocks all late firings
    low.iloc[:-400] = np.linspace(130, 120, len(low) - 400)  # falling: x < 0 throughout
    row = ft.score_window(win, low)
    assert row["pit"][5]["caught"] < row["pit"][5]["ref_caught"]
    assert ft.verdict(row)["verdict"] in ("underpowered", "recall_lost")


def test_without_a_filter_loco_reproduces_the_reference_row():
    win, skew, _ = _planted()
    table = at.pit_channel_table(win["channels"], keys=win["keys"])
    a = ft.loco_caught(win["channels"], win["keys"], win["close"], 5, table.index, None)
    b = ft.loco_caught(win["channels"], win["keys"], win["close"], 5, table.index,
                       pd.Series(True, index=table.index))
    assert a == b and a["n_crises"] > 0


def test_the_shift_null_is_seeded_and_keeps_the_filter_rate():
    win, skew, _ = _planted()
    table = at.pit_channel_table(win["channels"], keys=win["keys"])
    orf = at._or_flag(table, win["keys"])
    passes = pd.Series(np.arange(len(table)) % 3 == 0, index=table.index)
    a = ft.shift_null(orf, passes, win["close"])
    b = ft.shift_null(orf, passes, win["close"])
    assert len(a) == ft.N_SHIFT and (a == b).all()
    assert ft.shift_null(orf.iloc[:100], passes.iloc[:100], win["close"]).size == 0


def test_the_aggregator_helpers_index_on_the_first_key():
    """The refactor that lets the panel-only flag (no composite) use them is
    output-identical for the live keys."""
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2010-01-01", periods=400)
    ch = {k: pd.Series(rng.uniform(size=400), index=idx) for k in at._CH_KEYS}
    t1 = at.pit_channel_table(ch)
    t2 = at.pit_channel_table({k: ch[k] for k in ("AR", "TURB")}, keys=("AR", "TURB"))
    assert (t1[["AR_w", "TURB_w"]] == t2[["AR_w", "TURB_w"]]).all().all()


def test_a_run_writes_its_report(tmp_path):
    win, skew, _ = _planted()
    out = ft.run(tmp_path, skew=skew, windows=[win])
    assert out["overall"] in ("pass", "fail")
    text = (tmp_path / "report.md").read_text()
    assert "IMP-9 §9.A" in text and "Verdict: **" in text
