"""
Tests for numeric_baseline.py — WP-21.A, the numeric directional baseline.

The suite is organised around the three ways this experiment could lie to us:

  1. **Look-ahead in the panel.** A revised or same-day input would let the model
     see the future. Tested by `test_publication_lag_*` and the FRED-eligibility
     guard, which encodes the no-revision rule as an assertion rather than a
     comment.
  2. **Look-ahead in the fit.** Training on a row whose forward window has not
     closed leaks the label. Tested by `test_walk_forward_embargo_*`, which spies
     on every training matrix the harness hands the model.
  3. **A harness that cannot tell signal from noise.** Both directions matter: a
     planted signal must be *found* (`test_walk_forward_finds_planted_signal`),
     and pure noise must not be reported as an edge
     (`test_run_on_random_walk_finds_no_edge`). A harness that only ever says "no
     edge" would look identical to the truth we suspect, which is exactly why the
     positive control is here.
  4. **A second feature set that quietly changes the comparison.** The exogenous
     arms add the Phase-19 SPF anchor to the harness, and three things have to
     stay true for their rows to mean anything: the survey is invisible before it
     is released, the exogenous columns contain no market input, and every arm is
     still scored on one shared call set even though the feature sets become
     usable on different dates. Section 8 asserts all three.

Everything runs offline: the panel fixtures are synthetic, and only
`build_panel` / feature / model code is exercised — no yfinance, no FRED.

Run:
    pytest .macro-assist/tests/test_numeric_baseline.py -q
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import numeric_baseline as nb
from backtest import run_backtest
from score_predictions import ASSET_TICKERS, SCORING_WINDOWS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _bdays(n: int, start: str = "2010-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _random_walk(n: int, seed: int, start_price: float = 100.0,
                 sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, size=n)
    return pd.Series(start_price * np.exp(np.cumsum(steps)), index=_bdays(n))


@pytest.fixture
def noise_panel() -> pd.DataFrame:
    """A panel of pure geometric random walks — by construction, no edge exists."""
    n = 1400
    idx = _bdays(n)
    cols = {}
    for i, asset in enumerate(["S&P 500", "Gold"]):
        cols[f"px:{asset}"] = _random_walk(n, seed=100 + i).values
    rng = np.random.default_rng(7)
    cols["macro:treasury_10y"]   = 3.0 + np.cumsum(rng.normal(0, 0.02, n))
    cols["macro:treasury_2y"]    = 2.0 + np.cumsum(rng.normal(0, 0.02, n))
    cols["macro:baa_spread"]     = 2.0 + np.cumsum(rng.normal(0, 0.01, n))
    cols["macro:breakeven_10y"]  = 2.0 + np.cumsum(rng.normal(0, 0.01, n))
    cols["macro:real_yield_10y"] = 1.0 + np.cumsum(rng.normal(0, 0.01, n))
    cols["macro:vix"]            = 18 + np.abs(rng.normal(0, 3, n))
    panel = pd.DataFrame(cols, index=idx)
    panel.index.name = "date"
    return panel


# ---------------------------------------------------------------------------
# 1. Panel integrity — the point-in-time contract
# ---------------------------------------------------------------------------

def test_fred_inputs_contain_only_unrevised_series():
    """The eligibility rule from the module docstring, as an assertion.

    A revised or lagged-release series in FRED_INPUTS silently reintroduces
    look-ahead: the panel carries no vintage information, so today's value would
    be attributed to a date on which nobody could have seen it.
    """
    forbidden = {
        "CPIAUCSL", "CPILFESL", "PAYEMS", "UNRATE", "M2SL", "WALCL",
        "NFCI", "ICSA", "INDPRO", "GDP", "GDPC1", "RRPONTSYD", "WTREGEN",
        "PCEPI", "RSAFS", "HOUST", "UMCSENT", "PHLX", "BAMLH0A0HYM2",
    }
    assert set(nb.FRED_INPUTS.values()).isdisjoint(forbidden), (
        "FRED_INPUTS gained a revised / lagged-release series — see the "
        "point-in-time section of numeric_baseline.py"
    )


def test_build_panel_shifts_fred_by_publication_lag():
    """A FRED print stamped day d must first appear on the panel row for d+1."""
    idx = _bdays(6)
    prices = {"S&P 500": pd.Series(np.arange(6, dtype=float) + 100.0, index=idx)}
    # A step function: 0 before the 3rd business day, 1 from it onwards.
    fred = {"vix": pd.Series([0.0, 0.0, 1.0, 1.0, 1.0, 1.0], index=idx)}

    panel = nb.build_panel(prices, fred, lag_bdays=1)
    vix = panel["macro:vix"]

    assert vix.loc[idx[2]] == 0.0, "same-day FRED value leaked into its own row"
    assert vix.loc[idx[3]] == 1.0, "lagged value did not arrive the next day"


def test_build_panel_forward_fills_prices_without_lag():
    """Prices are marks, not releases — they are known on their own day."""
    idx = _bdays(4)
    prices = {"Gold": pd.Series([10.0, 11.0, 12.0, 13.0], index=idx)}
    panel = nb.build_panel(prices, {})
    assert panel["px:Gold"].tolist() == [10.0, 11.0, 12.0, 13.0]


def test_features_are_strictly_backward_looking(noise_panel):
    """Changing a future price must not move any earlier feature row.

    This is the check a lookback bug fails silently: a `rolling(...).mean()` with
    `center=True`, a `shift(-n)`, or a `bfill` all still produce a plausible
    frame — and a model fitted on it looks brilliant.
    """
    cut = 900
    base = nb.build_features(noise_panel, "S&P 500")

    tampered = noise_panel.copy()
    tampered.iloc[cut:, tampered.columns.get_loc("px:S&P 500")] *= 3.0
    after = nb.build_features(tampered, "S&P 500")

    pd.testing.assert_frame_equal(base.iloc[:cut], after.iloc[:cut])


def test_forward_label_marks_up_days():
    close = pd.Series([1.0, 2.0, 1.5, 3.0, 2.0], index=_bdays(5))
    lab = nb.forward_label(close, horizon=1)
    assert lab.tolist()[:4] == [1.0, 0.0, 1.0, 0.0]
    assert pd.isna(lab.iloc[-1]), "the unresolvable tail row must be NaN, not 0"


# ---------------------------------------------------------------------------
# 2. Walk-forward — the embargo
# ---------------------------------------------------------------------------

def _spy_fitter(record: list):
    def _fit(X, y, columns):
        record.append(X[:, 0].max())
        p = float(np.mean(y))
        return nb.FittedModel(
            predict_proba=lambda Z, _p=p: np.full(len(Z), _p),
            coefficients={c: 0.0 for c in columns},
        )
    return _fit


@pytest.mark.parametrize("horizon", [5, 10, 20])
def test_walk_forward_embargo_excludes_unresolved_labels(horizon):
    """No training row's forward window may still be open at prediction time.

    The feature column *is* the row's position, so the largest value the fitter
    ever sees names the newest training row. It must resolve strictly before the
    row being predicted: `train_idx + horizon < predict_idx`.
    """
    n = 400
    idx = _bdays(n)
    features = pd.DataFrame({"idx": np.arange(n, dtype=float)}, index=idx)
    labels = pd.Series((np.arange(n) % 2).astype(float), index=idx)

    seen: list[float] = []
    min_train = 100
    res = nb.walk_forward(
        features, labels, horizon, _spy_fitter(seen),
        min_train=min_train, refit_every=1,
    )

    assert res.dates, "walk-forward produced no predictions"
    predict_positions = [idx.get_indexer([d])[0] for d in res.dates]
    # refit_every=1 ⇒ one fit per prediction, in order.
    assert len(seen) == len(predict_positions)
    for newest_train_row, predict_pos in zip(seen, predict_positions):
        assert newest_train_row + horizon < predict_pos, (
            f"training row {newest_train_row} resolves at "
            f"{newest_train_row + horizon}, not strictly before prediction "
            f"row {predict_pos}"
        )


def test_walk_forward_respects_min_train():
    n = 300
    idx = _bdays(n)
    features = pd.DataFrame({"idx": np.arange(n, dtype=float)}, index=idx)
    labels = pd.Series((np.arange(n) % 2).astype(float), index=idx)
    seen: list[float] = []
    nb.walk_forward(features, labels, 5, _spy_fitter(seen),
                    min_train=120, refit_every=1)
    assert seen, "no fits happened"
    assert min(seen) + 1 >= 120, "a fit ran on fewer rows than min_train"


def test_walk_forward_refits_on_cadence():
    n = 400
    idx = _bdays(n)
    features = pd.DataFrame({"idx": np.arange(n, dtype=float)}, index=idx)
    labels = pd.Series((np.arange(n) % 2).astype(float), index=idx)

    seen_daily: list[float] = []
    daily = nb.walk_forward(features, labels, 5, _spy_fitter(seen_daily),
                            min_train=100, refit_every=1)
    seen_monthly: list[float] = []
    monthly = nb.walk_forward(features, labels, 5, _spy_fitter(seen_monthly),
                              min_train=100, refit_every=21)

    assert len(daily.dates) == len(monthly.dates)
    assert monthly.n_fits < daily.n_fits
    assert monthly.n_fits == pytest.approx(len(monthly.dates) / 21, abs=1)


def test_walk_forward_returns_nothing_when_history_too_short():
    idx = _bdays(50)
    features = pd.DataFrame({"idx": np.arange(50, dtype=float)}, index=idx)
    labels = pd.Series((np.arange(50) % 2).astype(float), index=idx)
    res = nb.walk_forward(features, labels, 20, _spy_fitter([]), min_train=100)
    assert res.dates == [] and res.n_fits == 0


# ---------------------------------------------------------------------------
# 3. Does the harness have any power? (both directions)
# ---------------------------------------------------------------------------

def test_walk_forward_finds_planted_signal():
    """Positive control: a learnable relationship must actually be learned.

    Without this, "no edge everywhere" is indistinguishable from a broken
    harness — and "no edge" is the result Phase 21 half expects, so the null
    finding is only worth anything if this test passes.
    """
    pytest.importorskip("sklearn")
    n = 900
    idx = _bdays(n)
    rng = np.random.default_rng(11)
    signal = rng.normal(size=n)
    features = pd.DataFrame(
        {"signal": signal, "noise": rng.normal(size=n)}, index=idx
    )
    # Label is the sign of the feature 85% of the time.
    flip = rng.random(n) < 0.15
    labels = pd.Series(
        np.where((signal > 0) ^ flip, 1.0, 0.0), index=idx
    )

    res = nb.walk_forward(features, labels, horizon=5, fit_fn=nb.fit_ridge,
                          min_train=250, refit_every=21)
    assert res.dates
    calls = [nb.call_from_probability(p) for p in res.probabilities]
    hits = [
        (bias == "Bullish") == bool(labels.loc[d])
        for (bias, _), d in zip(calls, res.dates)
        if bias != "Neutral"
    ]
    assert len(hits) > 100, "planted signal produced almost no decisive calls"
    assert np.mean(hits) > 0.75, f"planted signal not recovered: {np.mean(hits):.3f}"

    mean_coef = nb._mean_coefficients(res.coefficients)
    assert mean_coef["signal"] > abs(mean_coef["noise"]), (
        "the informative input did not outweigh the noise input"
    )


def test_run_on_random_walk_finds_no_edge(noise_panel, tmp_path):
    """Negative control: on data with no signal, no arm may be reported as edged."""
    pytest.importorskip("sklearn")
    result = nb.run(
        noise_panel,
        out_dir=tmp_path,
        arms=(nb.ARM_RIDGE,),
        horizons={"t5": 5},
        min_train=400,
        refit_every=60,
        with_importance=False,
        with_separation=False,
        write=False,
    )
    assert result["evaluations"][nb.ARM_RIDGE]["n_calls"] > 0
    for arm, v in result["verdicts"].items():
        assert v != "edge", f"{arm} claimed an edge on a pure random walk"


def test_run_wires_the_separation_reader_into_the_verdict(noise_panel):
    """The full path, with separation on — the permutation draws turned down.

    `with_separation=False` is what keeps the other end-to-end tests quick, so
    something has to exercise the branch that actually feeds `verdict`.
    """
    pytest.importorskip("sklearn")
    result = nb.run(
        noise_panel.iloc[:800], out_dir=None, arms=(nb.ARM_RIDGE,),
        horizons={"t5": 5}, min_train=500, refit_every=120,
        with_importance=False, with_separation=True, separation_draws=50,
        write=False,
    )
    sep = result["evaluations"][nb.ARM_RIDGE]["separation"]
    assert sep is not None
    assert sep["provenance"]["arm"] == nb.ARM_RIDGE
    assert sep["overall"]["ordering"] in ("aligned", "inverted", "mixed", None)
    assert sep["params"]["n_perm"] == 50, "the draw override did not reach the reader"
    assert result["meta"]["separation_draws"] == 50
    assert result["verdicts"][nb.ARM_RIDGE] in ("edge", "no edge", "underpowered")


def test_verdict_distinguishes_abstention_from_a_small_sample():
    """An all-Neutral arm has nothing to score; more data would not change that."""
    abstainer = {"n_calls": 4000,
                 "overall": {"decisive_hit_rate": None, "calibration": None}}
    assert nb.verdict(abstainer) == "abstains"

    thin = {"n_calls": 12,
            "overall": {"decisive_hit_rate": 0.6,
                        "calibration": {"n": 12, "brier_skill_score": 0.1}}}
    assert nb.verdict(thin) == "underpowered"


def test_verdict_is_underpowered_below_the_bar():
    ev = {"overall": {"decisive_hit_rate": 0.9,
                      "calibration": {"n": nb.EDGE_MIN_N - 1,
                                      "brier_skill_score": 0.5}}}
    assert nb.verdict(ev) == "underpowered"


def test_verdict_reports_edge_when_the_bar_is_cleared():
    ev = {
        "overall": {"decisive_hit_rate": 0.58,
                    "calibration": {"n": 500, "brier_skill_score": 0.04}},
        "separation": {"overall": {"ordering": "aligned"}},
    }
    assert nb.verdict(ev) == "edge"


def test_verdict_rejects_a_hit_rate_without_calibration_or_ordering():
    ev = {
        "overall": {"decisive_hit_rate": 0.58,
                    "calibration": {"n": 500, "brier_skill_score": -0.10}},
        "separation": {"overall": {"ordering": "inverted"}},
    }
    assert nb.verdict(ev) == "no edge"


# ---------------------------------------------------------------------------
# 4. Calls, comparators, score files
# ---------------------------------------------------------------------------

def test_call_from_probability_deadband():
    assert nb.call_from_probability(0.50) == ("Neutral", 50)
    assert nb.call_from_probability(0.54, deadband=0.05) == ("Neutral", 50)
    assert nb.call_from_probability(0.70)[0] == "Bullish"
    assert nb.call_from_probability(0.30)[0] == "Bearish"


def test_confidence_is_probability_of_the_stated_call():
    """Bearish 0.20 must read as 80% confident, not 20% — the Brier convention."""
    bias, conf = nb.call_from_probability(0.20)
    assert (bias, conf) == ("Bearish", 80)


def test_comparator_random_walk_matches_backtest_rule():
    idx = _bdays(4)
    close = pd.Series([10.0, 11.0, 10.5, 10.5], index=idx)
    assert nb.comparator_call(nb.ARM_RANDOM_WALK, close, idx[1])[0] == "Bullish"
    assert nb.comparator_call(nb.ARM_RANDOM_WALK, close, idx[2])[0] == "Bearish"
    assert nb.comparator_call(nb.ARM_RANDOM_WALK, close, idx[3])[0] == "Neutral"
    assert nb.comparator_call(nb.ARM_NEUTRAL, close, idx[1]) == ("Neutral", 50)
    assert nb.comparator_call(nb.ARM_ALWAYS_BULL, close, idx[1])[0] == "Bullish"


def test_score_reports_are_readable_by_the_production_readers():
    """The emitted files must satisfy summarize_accuracy and bias_separation.

    Reusing the production readers is the whole reason the numeric arms are
    comparable to the LLM arm; a shape drift here would quietly turn the
    comparison into two different metrics with the same names.
    """
    from bias_separation import bias_separation, observations
    from summarize_accuracy import _brier_and_reliability

    idx = _bdays(60)
    close = pd.Series(np.linspace(100, 130, 60), index=idx)   # a steady uptrend
    prices = {"S&P 500": close}
    calls = {
        "ridge": {
            "t5": {
                idx[i].date().isoformat(): {"S&P 500": ("Bullish", 70)}
                for i in range(0, 40)
            }
        }
    }
    reports = nb.build_score_reports(calls, prices)
    assert reports
    for r in reports:
        assert r["arm"] == "ridge"
        assert r["profile"] == nb.NUMERIC_PROFILE
        assert "t5" in r["windows"]

    obs = observations(reports)
    assert len(obs) == len(reports)
    assert all(o["arm"] == "ridge" for o in obs)

    calib = _brier_and_reliability(
        [{"confidence": 70, "score": 1.0} for _ in range(10)]
    )
    assert calib["n"] == 10

    sep = bias_separation(reports, arm="ridge")
    assert sep is not None
    assert sep["provenance"]["arm"] == "ridge"


def test_score_reports_use_the_production_scorer_for_flat_moves():
    """A move inside the flat threshold scores 0.5 even for a decisive call."""
    idx = _bdays(10)
    close = pd.Series([100.0] * 5 + [100.1] * 5, index=idx)  # +0.1%, under 0.5%
    calls = {"ridge": {"t5": {idx[0].date().isoformat(): {"Gold": ("Bullish", 80)}}}}
    reports = nb.build_score_reports(calls, {"Gold": close})
    assert reports[0]["windows"]["t5"]["assets"]["Gold"]["score"] == 0.5


def test_score_reports_skip_dates_whose_window_has_not_closed():
    idx = _bdays(6)
    close = pd.Series(np.linspace(100, 106, 6), index=idx)
    calls = {"ridge": {"t20": {idx[0].date().isoformat(): {"Gold": ("Bullish", 80)}}}}
    assert nb.build_score_reports(calls, {"Gold": close}) == []


def test_profile_tag_never_joins_the_live_ab():
    """`baseline` / `loosened` name the live LLM A/B; simulated arms stay out."""
    assert nb.NUMERIC_PROFILE not in ("baseline", "loosened")


# ---------------------------------------------------------------------------
# 5. The backtest.py strategy interface
# ---------------------------------------------------------------------------

def test_strategies_cover_every_scored_asset():
    preds = nb.strategy_ridge({"numeric_calls": {}})
    assert set(preds) == set(ASSET_TICKERS)
    assert all(p["bias"] == "Neutral" for p in preds.values()), (
        "a missing model call must abstain, not guess"
    )


def test_strategy_reads_its_own_arm_only():
    snapshot = {
        "numeric_calls": {
            "ridge": {"Gold": ("Bullish", 72)},
            "gbm":   {"Gold": ("Bearish", 61)},
        }
    }
    assert nb.strategy_ridge(snapshot)["Gold"]["bias"] == "Bullish"
    assert nb.strategy_gbm(snapshot)["Gold"]["bias"] == "Bearish"
    assert nb.strategy_ridge(snapshot)["Bitcoin"]["bias"] == "Neutral"


def test_numeric_arms_replay_through_run_backtest(tmp_path):
    """The arms must run through the existing harness, not a parallel one."""
    calls = {
        "ridge": {
            "t5": {
                "2024-06-03": {"Gold": ("Bullish", 66)},
                "2024-06-04": {"Gold": ("Bearish", 58)},
            }
        }
    }
    snapshot_fn = nb.make_snapshot_fn(calls, "t5")
    out = run_backtest(
        date(2024, 6, 3), date(2024, 6, 5), nb.strategy_ridge, tmp_path,
        _snapshot_fn=snapshot_fn,
    )
    assert out["dates_processed"] == 3
    assert out["errors"] == []

    import json
    day1 = json.loads((tmp_path / "2024-06-03.json").read_text())
    assert day1["predictions"]["Gold"]["bias"] == "Bullish"
    day3 = json.loads((tmp_path / "2024-06-05.json").read_text())
    assert day3["predictions"]["Gold"]["bias"] == "Neutral"


# ---------------------------------------------------------------------------
# 6. Output isolation and reporting
# ---------------------------------------------------------------------------

def test_run_writes_only_under_its_own_output_dir(noise_panel, tmp_path):
    """Simulated score files must never land in the production accuracy corpus."""
    pytest.importorskip("sklearn")
    out = tmp_path / "numeric"
    result = nb.run(
        noise_panel, out_dir=out, arms=(nb.ARM_RIDGE,), horizons={"t5": 5},
        min_train=400, refit_every=120, with_importance=False,
        with_separation=False, emit_scores=True, write=True,
    )
    assert result["output_dir"] == str(out)
    assert (out / "numeric_baseline.md").exists()
    assert (out / "numeric_baseline.json").exists()

    import gzip
    import json
    with gzip.open(out / "scores.json.gz", "rt", encoding="utf-8") as fh:
        reports = json.load(fh)
    assert reports, "no scored reports emitted"
    assert {r["arm"] for r in reports} >= {nb.ARM_RIDGE, nb.ARM_NEUTRAL}

    written = [p for p in out.rglob("*") if p.is_file()]
    assert all(p.is_relative_to(out) for p in written)

    from bias_separation import SCORES_DIR
    assert not str(out).startswith(str(SCORES_DIR))


def test_raw_calls_are_not_written_unless_asked(noise_panel, tmp_path):
    """~30k reports of indented JSON is ~100MB — never a routine commit."""
    pytest.importorskip("sklearn")
    out = tmp_path / "numeric"
    nb.run(
        noise_panel, out_dir=out, arms=(nb.ARM_RIDGE,), horizons={"t5": 5},
        min_train=400, refit_every=120, with_importance=False,
        with_separation=False, write=True,
    )
    assert (out / "numeric_baseline.md").exists()
    assert not (out / "scores.json.gz").exists()


def test_report_renders_every_arm(noise_panel):
    evaluations = {
        "ridge": {"overall": {"decisive_hit_rate": 0.49,
                              "calibration": {"n": 120, "brier": 0.26,
                                              "brier_skill_score": -0.05,
                                              "ece": 0.08}},
                  "windows": {}, "separation": None},
        "neutral": {"overall": {"decisive_hit_rate": None, "calibration": None},
                    "windows": {}, "separation": None},
    }
    md = "\n".join(nb.report_md_lines(evaluations, {}, {"panel_rows": 10}))
    assert "`ridge`" in md and "`neutral`" in md
    assert "WP-21.A" in md
    assert "n/a" in md, "a missing metric must render as n/a, not 0"


def test_run_models_covers_every_scoring_window(noise_panel):
    pytest.importorskip("sklearn")
    calls, diagnostics = nb.run_models(
        noise_panel, arms=(nb.ARM_RIDGE,), min_train=400, refit_every=120,
        with_importance=False,
    )
    assert set(calls[nb.ARM_RIDGE]) == set(SCORING_WINDOWS)
    assert diagnostics[nb.ARM_RIDGE]["n_fits"] > 0


def test_comparators_are_scored_on_the_model_dates(noise_panel):
    dates = [d.date().isoformat() for d in noise_panel.index[500:520]]
    assets = frozenset(nb.ASSET_TICKERS)
    comp = nb.comparator_calls(noise_panel, {"t5": {d: assets for d in dates}})
    for arm in nb.COMPARATOR_ARMS:
        assert sorted(comp[arm]["t5"]) == sorted(dates), (
            "a comparator was scored on a different sample than the models"
        )


def test_comparators_do_not_call_an_asset_the_models_skipped(noise_panel):
    """The KB-023 error one level down: same dates, different assets.

    A model cannot predict an asset until it has `min_train` days of that
    asset's own history; a comparator keyed off price availability calls it from
    day one. That hands `always_bullish` — the benchmark the whole verdict turns
    on — a free sample of a young asset the models never saw.
    """
    dates = [d.date().isoformat() for d in noise_panel.index[500:520]]
    late = sorted(nb.ASSET_TICKERS)[0]
    keys = {"t5": {d: frozenset(a for a in nb.ASSET_TICKERS if a != late)
                   for d in dates}}
    comp = nb.comparator_calls(noise_panel, keys)

    for arm in nb.COMPARATOR_ARMS:
        called = {a for per_asset in comp[arm]["t5"].values() for a in per_asset}
        assert late not in called, (
            f"{arm} called {late}, which the models never predicted"
        )


def test_shared_call_keys_intersects_across_model_arms():
    """One sample for the whole table, not one per arm."""
    model_calls = {
        "ridge": {"t5": {"2020-01-02": {"Gold": ("Bullish", 60),
                                        "DXY":  ("Bearish", 60)},
                         "2020-01-03": {"Gold": ("Bullish", 60)}}},
        "gbm":   {"t5": {"2020-01-02": {"Gold": ("Bearish", 60)}}},
    }
    keys = nb.shared_call_keys(model_calls)
    assert keys == {"t5": {"2020-01-02": frozenset({"Gold"})}}, (
        "an asset or date only one model arm reached must not enter the sample"
    )


def test_every_arm_is_scored_on_an_identical_call_set(noise_panel):
    """The guarantee the headline comparison rests on, asserted end to end."""
    pytest.importorskip("sklearn")
    model_calls, _ = nb.run_models(
        noise_panel, arms=(nb.ARM_RIDGE,), min_train=400, refit_every=120,
        with_importance=False,
    )
    keys = nb.shared_call_keys(model_calls)
    comp = nb.comparator_calls(noise_panel, keys)
    all_calls = nb.restrict_calls({**model_calls, **comp}, keys)

    def key_set(calls):
        return {(w, iso, asset)
                for w, dated in calls.items()
                for iso, per_asset in dated.items()
                for asset in per_asset}

    reference = key_set(all_calls[nb.ARM_RIDGE])
    assert reference, "the fixture produced no calls to compare"
    for arm, calls in all_calls.items():
        assert key_set(calls) == reference, (
            f"{arm} was scored on a different sample than the models"
        )


def test_unsigned_weights_are_not_rendered_with_a_sign_stability_column():
    """A tree's `feature_importances_` counts splits and is never negative.

    Rendering it under a "sign stability" heading would print a constant 1.000
    and read as a strong, stable directional claim it cannot make.
    """
    signed = {"ridge": {
        "weight_kind": nb.WEIGHT_SIGNED, "n_fits": 3,
        "streams": {"Gold|t5": {"coefficients": {"ret_20": -0.2},
                                "sign_stability": {"ret_20": 0.9}}},
    }}
    unsigned = {"gbm": {
        "weight_kind": nb.WEIGHT_UNSIGNED, "n_fits": 3,
        "streams": {"Gold|t5": {"coefficients": {"ret_20": 0.2}}},
    }}
    md_signed = "\n".join(nb._importance_lines(signed))
    md_unsigned = "\n".join(nb._importance_lines(unsigned))

    assert "sign stability" in md_signed and "mean coefficient" in md_signed
    assert "sign stability" not in md_unsigned
    assert "mean split importance" in md_unsigned
    assert "reversion candidate" in md_signed
    assert "reversion candidate" not in md_unsigned


def test_gbm_weights_are_tagged_unsigned():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(5)
    X = rng.normal(size=(200, 3))
    y = (X[:, 0] > 0).astype(float)
    assert nb.fit_ridge(X, y, ["a", "b", "c"]).weight_kind == nb.WEIGHT_SIGNED
    assert nb.fit_gbm(X, y, ["a", "b", "c"]).weight_kind == nb.WEIGHT_UNSIGNED


def test_sign_stability_flags_a_flipping_coefficient():
    stable = nb._sign_stability([{"a": 1.0}, {"a": 0.8}, {"a": 1.2}])
    flipping = nb._sign_stability([{"a": 1.0}, {"a": -0.9}, {"a": 1.1}, {"a": -1.0}])
    assert stable["a"] == 1.0
    assert flipping["a"] <= 0.5


def test_importance_fit_carries_the_same_embargo_as_the_walk_forward():
    """The importance refit must not train on labels that resolve in its test set.

    It is a second fit, on a second boundary, and the embargo has to be repeated
    there — an out-of-sample importance measured against outcomes the model was
    trained on is not out of sample.
    """
    n = 500
    idx = _bdays(n)
    features = pd.DataFrame({"idx": np.arange(n, dtype=float)}, index=idx)
    labels = pd.Series((np.arange(n) % 2).astype(float), index=idx)
    horizon = 20

    seen: list[float] = []
    res = nb.walk_forward(features, labels, horizon, _spy_fitter([]),
                          min_train=200, refit_every=50)
    assert res.dates
    nb._out_of_sample_importance(
        features, labels, res, horizon, _spy_fitter(seen), min_train=100,
    )
    assert seen, "the importance refit never ran"
    first_test_pos = idx.get_indexer([res.dates[0]])[0]
    assert seen[0] + horizon < first_test_pos, (
        f"importance refit trained on row {seen[0]}, whose label resolves at "
        f"{seen[0] + horizon} — inside the test set starting at {first_test_pos}"
    )


def test_permutation_importance_ranks_the_useful_column_first():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(400, 2))
    y = (X[:, 0] > 0).astype(float)
    model = nb.FittedModel(
        predict_proba=lambda Z: 1 / (1 + np.exp(-4 * Z[:, 0])),
    )
    imp = nb.permutation_importance(model, X, y, ["useful", "useless"])
    assert imp["useful"] > imp["useless"]
    assert imp["useful"] > 0.1


def test_report_flags_arms_scored_on_different_samples():
    """The guard that would have caught the Bitcoin mismatch in the first run.

    `restrict_calls` makes unequal samples impossible upstream; this is the
    reader-side backstop, in the shape [WP-21.B.1] gave the accuracy readers —
    a ⛔ line in the report rather than a silently invalid comparison.
    """
    def arm(n_calls):
        return {
            "n_calls": n_calls,
            "overall": {"decisive_hit_rate": 0.53,
                        "calibration": {"n": n_calls, "brier": 0.25,
                                        "brier_skill_score": -0.01, "ece": 0.02}},
            "windows": {},
        }

    matched = "\n".join(nb.report_md_lines(
        {"ridge": arm(1000), "always_bullish": arm(1000)}, {}, {"panel_rows": 10}))
    assert "all arms scored on the same 1000 calls" in matched
    assert "⛔" not in matched

    mismatched = "\n".join(nb.report_md_lines(
        {"ridge": arm(1000), "always_bullish": arm(1400)}, {}, {"panel_rows": 10}))
    assert "⛔" in mismatched
    assert "KB-023" in mismatched


# ---------------------------------------------------------------------------
# 8. The exogenous arms — the Phase-19 anchor folded into the harness
# ---------------------------------------------------------------------------

_SPF_DIR = Path(nb.__file__).resolve().parent / "exogenous" / "example"


@pytest.fixture
def spf_series(noise_panel) -> dict:
    """Synthetic quarterly surveys on the noise panel's window.

    Synthetic on purpose: the real workbooks are exercised once, by
    `test_spf_loader_reads_the_committed_workbooks`. Everything else needs
    surveys whose release dates and values the test controls.
    """
    idx = noise_panel.index
    stamps = pd.DatetimeIndex([idx[0] - pd.offsets.BDay(30), *idx[::63]])
    rng = np.random.default_rng(21)

    def survey(base: float, drift: float) -> pd.Series:
        return pd.Series(base + np.cumsum(rng.normal(0, drift, len(stamps))), index=stamps)

    out = {
        "spf_10y":    survey(4.0, 0.15),
        "spf_10y_q4": survey(4.2, 0.15),
        "spf_3m":     survey(2.0, 0.10),
        "spf_3m_q4":  survey(2.1, 0.10),
        "spf_unemp":  survey(5.0, 0.10),
    }
    out[nb.SPF_ASOF_KEY] = pd.Series(
        [float(ts.toordinal()) for ts in stamps], index=stamps
    )
    return out


@pytest.fixture
def exo_panel(noise_panel, spf_series) -> pd.DataFrame:
    """The noise panel with the exogenous anchor attached."""
    prices = {c.split(":", 1)[1]: noise_panel[c]
              for c in noise_panel.columns if c.startswith("px:")}
    fred = {c.split(":", 1)[1]: noise_panel[c]
            for c in noise_panel.columns if c.startswith("macro:")}
    return nb.build_panel(prices, fred, spf_series)


def test_sep_is_excluded_because_fred_serves_the_current_vintage():
    """The one input from the live branch that must never enter the panel.

    `sep.py` reads FEDTARMD from FRED, which returns the *current* dot plot —
    every SEP release rewrites the earlier target years. Reading it in a
    walk-forward hands the model the Fed's later revisions, exactly the leak the
    FRED eligibility rule exists to prevent. Encoded as an assertion so a future
    "just add the dots" change has to argue with a red test.
    """
    from exogenous.sep import SEP_SERIES

    for series_id in SEP_SERIES.values():
        assert series_id in nb.EXCLUDED_EXOGENOUS_SERIES, (
            f"{series_id} is used by the live exogenous branch but is not "
            "listed as ineligible here"
        )
        assert series_id not in nb.FRED_INPUTS.values()
    codes = {code for code, _ in nb.SPF_INPUTS.values()}
    assert not codes & set(nb.EXCLUDED_EXOGENOUS_SERIES)


def test_spf_columns_are_not_visible_before_the_survey_is_released(noise_panel):
    """Point-in-time, at the panel level: no survey before its release date."""
    idx = noise_panel.index
    release = idx[400]
    spf = {"spf_10y": pd.Series([3.0, 9.0], index=[idx[0] - pd.offsets.BDay(30), release])}
    prices = {c.split(":", 1)[1]: noise_panel[c]
              for c in noise_panel.columns if c.startswith("px:")}

    panel = nb.build_panel(prices, {}, spf, lag_bdays=1)
    col = panel["exo:spf_10y"]
    assert col.loc[release] == 3.0, "the survey was readable on its own release day"
    assert col.loc[idx[401]] == 9.0, "the survey was still invisible a day after release"


def test_survey_revision_is_zero_when_a_survey_repeats_its_number():
    """A repeated consensus is an update whose revision is 0.0, not a stale one.

    The 3M consensus sat pinned through years of ZIRP. Detecting updates by
    value change would read every one of those quarters as "no new survey" and
    leave a months-old revision standing as if it were current.
    """
    idx = pd.bdate_range("2020-01-01", periods=9)
    value = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.4, 1.4, 1.4], index=idx)
    asof  = pd.Series([10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 30.0, 30.0, 30.0], index=idx)

    rev = nb._survey_revision(value, asof)
    assert pd.isna(rev.iloc[0]), "no revision exists before a second survey"
    assert rev.iloc[3] == pytest.approx(0.0), "an unchanged survey revises by zero"
    assert rev.iloc[5] == pytest.approx(0.0), "the zero is held across the quarter"
    assert rev.iloc[6] == pytest.approx(0.4)


def test_survey_staleness_counts_from_the_survey_not_the_value():
    idx = pd.bdate_range("2020-01-01", periods=6)
    asof = pd.Series([10.0, 10.0, 10.0, 20.0, 20.0, 20.0], index=idx)

    stale = nb._survey_staleness(asof, scale=3)
    assert list(stale) == pytest.approx([0.0, 1 / 3, 2 / 3, 0.0, 1 / 3, 2 / 3])


def test_exogenous_features_carry_no_market_input(exo_panel):
    """The claim that makes this a different hypothesis, not a bigger model."""
    exo = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_EXO)
    market = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_MARKET)

    assert not exo.empty
    assert set(exo.columns).isdisjoint(market.columns), (
        "an exogenous column also appears in the market panel"
    )
    assert all(c.startswith("spf_") for c in exo.columns)


def test_the_survey_clock_is_never_a_model_feature(exo_panel):
    """A raw date ordinal is the purest date proxy there is — it stays a panel
    column and never reaches an estimator."""
    exo = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_EXO)
    combined = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_COMBINED)
    for frame in (exo, combined):
        assert nb.SPF_ASOF_KEY not in frame.columns
        assert not any(c.endswith(nb.SPF_ASOF_KEY) for c in frame.columns)


def test_combined_feature_set_is_exactly_the_union(exo_panel):
    """`market_plus_exo` vs `ridge` is only a clean read if nothing else moved."""
    market   = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_MARKET)
    exo      = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_EXO)
    combined = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_COMBINED)

    assert list(combined.columns) == list(market.columns) + list(exo.columns)
    pd.testing.assert_frame_equal(combined[market.columns], market)


def test_exogenous_features_are_strictly_backward_looking(exo_panel):
    """The feature guard from section 1, applied to the new columns."""
    base = nb.build_features(exo_panel, "S&P 500", nb.FEATURES_EXO)
    cut = len(exo_panel) // 2

    tampered = exo_panel.copy()
    for col in tampered.columns:
        if col.startswith("exo:"):
            tampered.iloc[cut:, tampered.columns.get_loc(col)] *= 3.0
    after = nb.build_features(tampered, "S&P 500", nb.FEATURES_EXO)

    pd.testing.assert_frame_equal(base.iloc[:cut - 1], after.iloc[:cut - 1])


def test_exogenous_arms_are_skipped_on_a_market_only_panel(noise_panel):
    """No SPF in the panel means the arm cannot run — and must not run empty.

    An arm that survives with zero calls empties the `shared_call_keys`
    intersection and takes the entire table down with it, which would turn a
    missing workbook into a silently unreadable report.
    """
    pytest.importorskip("sklearn")
    calls, diagnostics = nb.run_models(
        noise_panel, arms=nb.DEFAULT_ARMS, horizons={"t5": 5},
        min_train=400, refit_every=200, with_importance=False,
    )
    assert set(calls) == set(nb.MARKET_ARMS)
    for arm in nb.EXO_ARMS:
        assert "skipped" in diagnostics[arm]
    assert nb.shared_call_keys(calls), "the surviving arms still share a sample"


def test_exogenous_arms_share_the_market_arms_sample(exo_panel):
    """The KB-023 guarantee, across feature sets rather than across models.

    The exogenous columns carry fewer NaNs than the market panel's 252-day
    lookbacks, so an exo-only arm can start predicting earlier. Every arm must
    still be judged on the calls all of them made.
    """
    pytest.importorskip("sklearn")
    model_calls, _ = nb.run_models(
        exo_panel, arms=nb.DEFAULT_ARMS, horizons={"t5": 5},
        min_train=400, refit_every=200, with_importance=False,
    )
    assert set(model_calls) == set(nb.DEFAULT_ARMS)

    keys = nb.shared_call_keys(model_calls)
    comp = nb.comparator_calls(exo_panel, keys)
    all_calls = nb.restrict_calls({**model_calls, **comp}, keys)

    def key_set(calls):
        return {(w, iso, asset)
                for w, dated in calls.items()
                for iso, per_asset in dated.items()
                for asset in per_asset}

    reference = key_set(all_calls[nb.ARM_RIDGE])
    assert reference
    for arm, calls in all_calls.items():
        assert key_set(calls) == reference, (
            f"{arm} was scored on a different sample than the market arms"
        )


def test_numeric_arm_names_never_collide_with_a_live_arm():
    """[KB-023] was a pooling defect. A simulated arm sharing the live
    `exogenous` tag is the same defect waiting for someone to pool the files."""
    for live in ("market", "exogenous", "kimi"):
        assert live not in nb.ARM_SPECS


def test_every_arm_declares_a_known_feature_set_and_a_question():
    for arm, spec in nb.ARM_SPECS.items():
        assert spec.feature_set in nb.FEATURE_SETS
        assert spec.question.strip(), f"{arm} has no stated question"
    assert nb.MODEL_FITTERS.keys() == nb.ARM_SPECS.keys()


def test_report_names_a_skipped_arm_rather_than_dropping_it():
    """A blank row and an absent row read very differently to a human."""
    evaluations = {
        nb.ARM_RIDGE: {
            "n_calls": 100,
            "overall": {"decisive_hit_rate": 0.51, "mean_score": 0.5,
                        "calibration": {"n": 100, "brier": 0.25,
                                        "brier_skill_score": -0.01, "ece": 0.02}},
            "windows": {},
        }
    }
    meta = {"arms_skipped": {nb.ARM_EXO: "the panel carries no `exogenous` features"}}
    md = "\n".join(nb.report_md_lines(evaluations, {}, meta))
    assert nb.ARM_EXO in md
    assert "skipped" in md


def test_report_renders_the_increment_read_when_both_arms_ran():
    def arm(hit, bss):
        return {
            "n_calls": 100,
            "overall": {"decisive_hit_rate": hit, "mean_score": hit,
                        "calibration": {"n": 100, "brier": 0.25,
                                        "brier_skill_score": bss, "ece": 0.02}},
            "windows": {},
        }
    evaluations = {nb.ARM_RIDGE: arm(0.520, -0.05),
                   nb.ARM_MARKET_EXO: arm(0.530, -0.03)}
    md = "\n".join(nb.report_md_lines(evaluations, {}, {}))
    assert "Increment over the market panel" in md
    assert "+0.010" in md and "+0.020" in md


def test_spf_loader_reads_the_committed_workbooks():
    """The one test that touches the real Philly Fed files — still offline."""
    pytest.importorskip("openpyxl")
    series = nb.load_spf_inputs(_SPF_DIR)

    assert set(series) == set(nb.SPF_INPUTS) | {nb.SPF_ASOF_KEY}
    for key, s in series.items():
        assert not s.empty and s.index.is_monotonic_increasing, key
    # The clock spans every variable's surveys, not just one workbook's.
    stamps = set(series[nb.SPF_ASOF_KEY].index)
    for key in nb.SPF_INPUTS:
        assert set(series[key].index) <= stamps


def test_missing_workbooks_leave_the_market_arms_runnable(tmp_path):
    """A missing download degrades to the original WP-21.A run, not to a crash."""
    assert nb.load_spf_inputs(tmp_path) == {}
