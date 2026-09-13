"""
Tests for har_backtest.py (WP-17.5 second half — HAR-RV walk-forward read).

Pure unit tests: no network. Return series are synthetic (GARCH-like or iid).
The verdict tests assert the pre-registered order — the disqualifier fires
ahead of a strong skill number — per CLAUDE.md convention 7 / KB-027.

Run:
    pytest .macro-assist/tests/test_har_backtest.py -v
"""
import numpy as np
import pandas as pd
import pytest

from har_backtest import (
    BENCHMARKS, COVERAGE_BAND, DEGENERATE_SHARE, MIN_SKILL, PUBLISHED,
    VAR_RATIO_BAND, WIRED_NOTE_WINDOW,
    block_bootstrap_skill, har_variance, horizon_ok, horizon_read, log_returns,
    qlike, realized_forward, score_arms, score_asset, trailing_benchmarks,
    verdict, walk_forward_har, wiring_read,
)
from vol_forecast import har_rv_forecast


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _garch(n=1500, seed=0, omega=1e-5, alpha=0.1, beta=0.85):
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    s2 = omega / (1 - alpha - beta)
    for t in range(n):
        r[t] = rng.normal(0, np.sqrt(s2))
        s2 = omega + alpha * r[t] ** 2 + beta * s2
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(r, index=idx)


def _iid(n=6000, sigma=0.01, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0, sigma, n), index=pd.bdate_range("2000-01-03", periods=n))


def _row(skill, lo, hi, degenerate=0.0):
    return {"skill": skill, "skill_ci": {"lo": lo, "hi": hi}, "degenerate_share": degenerate}


# ---------------------------------------------------------------------------
# verdict order (pre-registered)
# ---------------------------------------------------------------------------

def test_verdict_degenerate_fires_ahead_of_strong_skill():
    assert verdict(_row(0.40, 0.30, 0.50, degenerate=DEGENERATE_SHARE + 0.001)) == "degenerate"


def test_verdict_degenerate_needs_more_than_share():
    assert verdict(_row(0.40, 0.30, 0.50, degenerate=DEGENERATE_SHARE)) == "skill"


def test_verdict_skill_needs_margin_and_interval():
    assert verdict(_row(0.05, 0.01, 0.09)) == "skill"
    assert verdict(_row(MIN_SKILL, 0.01, 0.09)) == "parity"        # not strictly above
    assert verdict(_row(0.05, -0.01, 0.11)) == "parity"            # interval touches zero
    assert verdict({"skill": 0.05, "skill_ci": None, "degenerate_share": 0}) == "parity"


def test_verdict_worse_is_symmetric():
    assert verdict(_row(-0.05, -0.09, -0.01)) == "worse"
    assert verdict(_row(-0.05, -0.09, 0.01)) == "parity"
    assert verdict(_row(-MIN_SKILL, -0.09, -0.01)) == "parity"


# ---------------------------------------------------------------------------
# forecasts and targets
# ---------------------------------------------------------------------------

def test_har_variance_inverts_forecast_daily_vol_exactly():
    r = _garch(300)
    fc = har_rv_forecast(pd.Series(r.to_numpy()))
    v = har_variance(r.to_numpy())
    assert v == pytest.approx((fc["forecast_daily_vol"] / 100) ** 2 / 252, rel=1e-12)
    assert np.isnan(har_variance(r.to_numpy()[:20]))                # too short -> NaN, not raise


def test_walk_forward_har_is_look_ahead_safe_and_matches_window_fit():
    r = _garch(400)
    fc = walk_forward_har(r, fit_window=62)
    assert fc.iloc[:61].isna().all() and fc.iloc[61:].notna().all()
    t = 200
    direct = har_variance(r.to_numpy()[t - 61: t + 1])
    assert fc.iloc[t] == pytest.approx(direct, rel=1e-12)
    # perturb the future: nothing at or before t may change
    r2 = r.copy()
    r2.iloc[t + 1:] = r2.iloc[t + 1:] * 5 + 0.01
    fc2 = walk_forward_har(r2, fit_window=62)
    pd.testing.assert_series_equal(fc.iloc[:t + 1], fc2.iloc[:t + 1])


def test_trailing_benchmarks_are_trailing():
    r = _garch(200)
    b = trailing_benchmarks(r)
    assert list(b.columns) == list(BENCHMARKS)
    r2 = r ** 2
    assert b["rv22"].iloc[100] == pytest.approx(r2.iloc[79:101].mean())
    assert b["rv5"].iloc[100] == pytest.approx(r2.iloc[96:101].mean())
    # ewma recursion
    e = r2.iloc[0]
    for x in r2.iloc[1:101]:
        e = 0.94 * e + 0.06 * x
    assert b["ewma94"].iloc[100] == pytest.approx(e)


def test_realized_forward_windows():
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.01], index=pd.bdate_range("2020-01-01", periods=5))
    rv, fret = realized_forward(r, 2)
    assert rv.iloc[0] == pytest.approx((0.02 ** 2 + 0.03 ** 2) / 2)
    assert fret.iloc[0] == pytest.approx(-0.02 + 0.03)
    assert rv.iloc[2] == pytest.approx((0.0 + 0.01 ** 2) / 2)
    assert np.isnan(rv.iloc[3]) and np.isnan(rv.iloc[4])           # incomplete windows


def test_log_returns_dedupes_and_sorts():
    idx = pd.to_datetime(["2020-01-03", "2020-01-02", "2020-01-02", "2020-01-06"])
    c = pd.Series([102.0, 100.0, 101.0, 103.0], index=idx)
    r = log_returns(c)
    assert list(r.index) == list(pd.to_datetime(["2020-01-03", "2020-01-06"]))
    assert r.iloc[0] == pytest.approx(np.log(102 / 101))


# ---------------------------------------------------------------------------
# losses, interval, calibration
# ---------------------------------------------------------------------------

def test_qlike_zero_at_perfect_positive_elsewhere():
    f = np.array([1e-4, 2e-4, 3e-4])
    assert np.allclose(qlike(f, f), 0.0)
    assert (qlike(f, f * 2) > 0).all() and (qlike(f, f / 2) > 0).all()


def test_block_bootstrap_brackets_point_and_is_seeded():
    rng = np.random.default_rng(0)
    la, lb = rng.exponential(1.0, 400), rng.exponential(1.2, 400)
    point = 1 - la.mean() / lb.mean()
    ci = block_bootstrap_skill(la, lb, n_boot=300)
    assert ci["lo"] <= point <= ci["hi"] and ci["n_blocks"] == 20
    assert ci == block_bootstrap_skill(la, lb, n_boot=300)
    assert block_bootstrap_skill(la[:10], lb[:10]) is None            # one block -> no interval


def test_score_arms_planted_perfect_forecast_is_skill_and_calibrated():
    """A forecast equal to the true variance beats every trailing estimator on
    iid data, and the Gaussian bands cover at nominal."""
    r = _iid(6000, sigma=0.01)
    truth = pd.Series(1e-4, index=r.index)
    bench = trailing_benchmarks(r)
    rv, fret = realized_forward(r, 5)
    row = score_arms(truth, bench, rv, fret, 5)
    assert row["verdict"] == "skill" and row["skill"] > MIN_SKILL and row["skill_ci"]["lo"] > 0
    assert all(row["skill_vs"][b] > 0 for b in BENCHMARKS)
    assert VAR_RATIO_BAND[0] < row["var_ratio"] < VAR_RATIO_BAND[1]
    for q, (lo, hi) in COVERAGE_BAND.items():
        assert lo < row["coverage"][q] < hi
    assert row["horizon_ok"] is True
    assert row["n_zero"] == 0 and row["n_wild"] == 0


def test_score_arms_noisy_forecast_is_worse_and_zero_forecasts_are_counted():
    r = _iid(6000, sigma=0.01, seed=3)
    rng = np.random.default_rng(9)
    noisy = pd.Series(1e-4 * np.exp(rng.normal(0, 0.6, len(r))), index=r.index)
    noisy.iloc[100:110] = 0.0                                          # ten clipped readings (< 1 %)
    bench = trailing_benchmarks(r)
    rv, fret = realized_forward(r, 5)
    row = score_arms(noisy, bench, rv, fret, 5)
    assert row["verdict"] == "worse" and row["skill_ci"]["hi"] < 0
    assert row["n_zero"] == 10 and row["n_loss"] == row["n"] - 10
    assert row["degenerate_share"] <= DEGENERATE_SHARE                 # so the bar, not the disqualifier, decided


def test_score_arms_degenerate_share_disqualifies_before_skill():
    r = _iid(3000, sigma=0.01, seed=4)
    truth = pd.Series(1e-4, index=r.index)
    truth.iloc[200:300] = 0.0                                          # 100 zeros on ~2,900 -> > 1 %
    bench = trailing_benchmarks(r)
    rv, fret = realized_forward(r, 5)
    row = score_arms(truth, bench, rv, fret, 5)
    assert row["skill"] > MIN_SKILL and row["skill_ci"]["lo"] > 0     # would be skill...
    assert row["verdict"] == "degenerate"                              # ...but the disqualifier wins


def test_horizon_ok_bands():
    ok = {"var_ratio": 1.0, "coverage": {0.5: 0.5, 0.9: 0.9}}
    assert horizon_ok(ok) is True
    assert horizon_ok({**ok, "var_ratio": 1.5}) is False
    assert horizon_ok({**ok, "coverage": {0.5: 0.5, 0.9: 0.80}}) is False
    assert horizon_ok({"var_ratio": None, "coverage": {}}) is None


def test_score_asset_shape_and_stride():
    close = 100 * np.exp(_garch(700).cumsum())
    res = score_asset(close, fit_windows=(62, 252), horizons=(1, 5), stride=5)
    assert res["n_returns"] == 699
    assert set(res["windows"]) == {62, 252} and set(res["windows"][62]) == {1, 5}
    row = res["windows"][252][5]
    assert row["n"] > 0 and row["verdict"] in {"degenerate", "skill", "worse", "parity"}
    assert set(row["qlike"]) == {"har", *BENCHMARKS}


# ---------------------------------------------------------------------------
# secondary reads
# ---------------------------------------------------------------------------

def _results(flip: dict[str, bool]) -> dict:
    out = {}
    for a in PUBLISHED:
        out[a] = {"n_returns": 1, "windows": {
            WIRED_NOTE_WINDOW: {5: {"verdict": "parity", "horizon_ok": True,
                                    "var_ratio": 1.0, "coverage": {0.5: 0.5, 0.9: 0.9}}},
            1000: {5: {"verdict": "skill" if flip.get(a) else "parity"}},
        }}
    return out


def test_wiring_read_needs_three_of_four_published_assets():
    assert wiring_read(_results({"SP500": True, "Gold": True}))["wiring_defect"] is False
    r = wiring_read(_results({"SP500": True, "Gold": True, "WTI Oil": True}))
    assert r["wiring_defect"] is True and r["assets"] == ["SP500", "Gold", "WTI Oil"]


def test_wiring_read_ignores_assets_that_are_already_skill_when_wired():
    res = _results({"SP500": True, "Gold": True, "WTI Oil": True})
    res["SP500"]["windows"][WIRED_NOTE_WINDOW][5]["verdict"] = "skill"
    assert wiring_read(res)["assets"] == ["Gold", "WTI Oil"]


def test_horizon_read_reports_wired_window_only():
    hr = horizon_read(_results({}))
    assert set(hr) == set(PUBLISHED) and hr["SP500"][5]["ok"] is True
