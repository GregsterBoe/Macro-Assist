"""
Tests for score_distributions.py — the v1.6 distribution scorer.

Pure unit tests: prices are synthetic pandas Series and the quant log is built
inline, so nothing here touches yfinance or the real results tree.

The tests are organised around the four things that would make this scorer lie:

  1. the scoring rule not actually being a proper scoring rule,
  2. a comparator being allowed to see the future, or being handed a different
     sample than the arm it is measured against (WP-21.A.2),
  3. the overlap in daily observations being treated as independent evidence,
  4. the pre-committed bar not implementing its own pre-registration ([KB-027]).

Run:
    pytest .macro-assist/tests/test_score_distributions.py -v
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
from datetime import date

import pandas as pd
import pytest

import score_distributions as sd
from assets import BY_KEY, ORIGINAL_KEYS


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _series(start="2020-01-01", end="2026-09-08", vol=0.01, drift=0.0, seed=3):
    """A synthetic geometric random walk on business days."""
    rng = random.Random(seed)
    days = pd.bdate_range(start, end)
    px = [100.0]
    for _ in range(len(days) - 1):
        px.append(px[-1] * math.exp(rng.gauss(drift, vol)))
    return pd.Series(px, index=days)


def _record(d: str, quantiles: dict, asset="SP500", horizon=5, sigma=None):
    """One quant-log record publishing `quantiles` for one asset/horizon."""
    rec = {
        "date": d,
        "conditional": {
            "bucket": "TEST",
            "distributions": {f"{asset}_{horizon}d": {**quantiles, "n": 300}},
        },
    }
    if sigma is not None:
        rec["vol_forecasts"] = {asset: {"forecast_daily_vol": sigma}}
    return rec


# ---------------------------------------------------------------------------
# 1. The scoring rule
# ---------------------------------------------------------------------------

def test_pinball_loss_is_minimised_at_the_true_quantile():
    """The property that makes pinball the right rule: it cannot be gamed.

    If it were not minimised at the true quantile, a forecaster could improve
    its score by shading the interval, and the whole measurement would be about
    interval width rather than accuracy.
    """
    rng = random.Random(1)
    sample = [rng.gauss(0.0, 1.0) for _ in range(40000)]
    for q in sd.QUANTILES:
        true_q = sd._quantile(sorted(sample), q)
        at_true = st.mean(sd.pinball_loss(y, true_q, q) for y in sample)
        for offset in (-0.4, -0.1, 0.1, 0.4):
            shaded = st.mean(sd.pinball_loss(y, true_q + offset, q) for y in sample)
            assert shaded >= at_true


def test_pinball_loss_is_asymmetric_in_the_expected_direction():
    # At q=0.25 an over-forecast (realized below) should cost more than an
    # equally sized under-forecast: the 25th percentile is meant to be exceeded.
    over = sd.pinball_loss(realized=-1.0, forecast=0.0, q=0.25)
    under = sd.pinball_loss(realized=1.0, forecast=0.0, q=0.25)
    assert over > under
    assert over == pytest.approx(0.75)
    assert under == pytest.approx(0.25)


def test_pinball_loss_is_zero_on_an_exact_hit():
    for q in sd.QUANTILES:
        assert sd.pinball_loss(2.5, 2.5, q) == 0.0


def test_pit_bins_partition_the_distribution():
    qs = {0.25: -1.0, 0.50: 0.0, 0.75: 1.0}
    assert sd.pit_bin(-2.0, qs) == 0
    assert sd.pit_bin(-0.5, qs) == 1
    assert sd.pit_bin(0.5, qs) == 2
    assert sd.pit_bin(2.0, qs) == 3
    # Boundaries land in the upper bin, consistently.
    assert sd.pit_bin(-1.0, qs) == 1
    assert sd.pit_bin(0.0, qs) == 2
    assert sd.pit_bin(1.0, qs) == 3


# ---------------------------------------------------------------------------
# 2. Point-in-time safety and sample alignment
# ---------------------------------------------------------------------------

def test_comparator_history_never_includes_an_unobservable_forward_return():
    """A comparator may only use windows that had already closed.

    The last usable entry is `horizon` bars before the cutoff. Including the
    entries after it would let the benchmark quote quantiles computed partly
    from the very move it is about to be scored on.
    """
    s = _series()
    asset = BY_KEY["SP500"]
    upto = date(2024, 6, 3)
    horizon = 5

    changes = sd._historical_changes(s, upto, horizon, asset)
    cut = sd._entry_index(s, upto)
    # The number of usable entries is exactly cut - horizon + 1.
    assert len(changes) == cut - horizon + 1

    # And every one of them resolves on or before the cutoff bar.
    assert cut - horizon + horizon <= cut


def test_historical_changes_respects_the_trailing_window():
    s = _series()
    asset = BY_KEY["SP500"]
    upto = date(2024, 6, 3)
    full = sd._historical_changes(s, upto, 5, asset)
    windowed = sd._historical_changes(s, upto, 5, asset, window=250)
    assert len(windowed) == 250
    assert len(full) > len(windowed)
    # The window is the most recent slice, not an arbitrary one.
    assert windowed == full[-250:]


def test_entry_index_is_the_last_close_at_or_before_the_report_date():
    s = _series()
    asset_date = date(2024, 6, 1)          # a Saturday
    i = sd._entry_index(s, asset_date)
    assert s.index[i].date() <= asset_date
    assert s.index[i + 1].date() > asset_date


def test_report_predating_the_series_yields_no_entry():
    s = _series(start="2024-01-01")
    assert sd._entry_index(s, date(2020, 1, 1)) is None


def test_unresolved_window_is_not_scored():
    """A window that has not closed must produce nothing, not a partial score."""
    s = _series(end="2026-09-08")
    asset = BY_KEY["SP500"]
    # Two business days before the series ends: a 5-day window cannot have closed.
    near_end = s.index[-2].date()
    assert sd.realized_change(s, near_end, 5, asset) is None


def test_observation_is_dropped_when_a_required_comparator_cannot_score():
    """WP-21.A.2: arms must be measured on the same calls.

    With too little history the unconditional benchmark cannot quote a quantile.
    Rather than scoring the published arm alone — and later comparing it to a
    benchmark computed on a different set of days — the observation is dropped.
    """
    short = _series(start="2026-01-01", end="2026-09-08")   # < MIN_COMPARATOR_N
    records = [_record("2026-02-02", {"p25": -1.0, "p50": 0.0, "p75": 1.0})]
    obs = sd.build_observations(records, {"SP500": short}, today=date(2026, 9, 8))
    assert obs == []


def test_every_arm_quotes_exactly_the_quantiles_that_were_claimed():
    """A median-only claim must not be compared against three-quantile rivals.

    Otherwise the comparator's mean pinball loss is an average over a different
    set of quantiles, and the difference reads as skill.
    """
    s = _series()
    records = [_record("2025-03-03", {"p50": 0.2})]
    obs = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))
    assert len(obs) == 1
    o = obs[0]
    assert o["claim"] == "median"
    for arm in sd.REQUIRED_ARMS:
        assert list(o["arms"][arm]["pinball"]) == ["0.5"]


def test_full_interval_claim_is_scored_on_all_three_quantiles():
    s = _series()
    records = [_record("2025-03-03", {"p25": -1.0, "p50": 0.2, "p75": 1.4})]
    obs = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))
    o = obs[0]
    assert o["claim"] == "iqr"
    assert sorted(o["arms"]["published"]["pinball"]) == ["0.25", "0.5", "0.75"]
    assert o["inside_iqr"] is not None
    assert o["pit_bin"] is not None


def test_median_only_claim_has_no_coverage_or_pit():
    """Coverage of an interval that was never published is not a measurement."""
    s = _series()
    records = [_record("2025-03-03", {"p50": 0.2})]
    o = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))[0]
    assert o["inside_iqr"] is None
    assert o["pit_bin"] is None
    assert o["above_median"] is not None       # the median claim IS scoreable


def test_a_claim_without_a_median_is_not_a_claim():
    rec = _record("2025-03-03", {"p25": -1.0, "p75": 1.0})
    assert sd.published_claims(rec) == []


def test_nan_and_boolean_quantiles_are_rejected():
    assert sd.published_claims(_record("2025-03-03", {"p50": float("nan")})) == []
    assert sd.published_claims(_record("2025-03-03", {"p50": True})) == []


# ---------------------------------------------------------------------------
# The 10Y: the level convention has to survive the whole path
# ---------------------------------------------------------------------------

def test_the_ten_year_is_scored_in_basis_points_end_to_end():
    """A 6bp yield move must be scored as 6, not as 1.26.

    This is the same bug `assets.forward_change` exists to prevent, asserted at
    the scorer level: a percent-of-a-percent realization against a basis-point
    quantile would make every 10Y loss ~13x too small.
    """
    days = pd.bdate_range("2024-01-01", "2026-09-08")
    yields = pd.Series([4.00] * len(days), index=days)
    yields.iloc[-1] = 4.00
    # Put a clean +6bp move 5 bars after a chosen entry.
    entry_pos = len(days) - 30
    yields.iloc[entry_pos + 5] = 4.06
    report_date = days[entry_pos].date()

    got = sd.realized_change(yields, report_date, 5, BY_KEY["UST10Y"])
    assert got is not None
    change, _, entry, exit_ = got
    assert entry == pytest.approx(4.00)
    assert exit_ == pytest.approx(4.06)
    assert change == pytest.approx(6.0, abs=1e-6)


def test_har_gaussian_comparator_declines_the_level_asset():
    """Better no comparator than a wrong one.

    The HAR forecast is a percent-return vol; turning it into a basis-point
    yield move needs the yield level, which would make it a different model.
    """
    assert sd._gaussian_quantiles(16.0, 5, BY_KEY["UST10Y"]) is None
    assert sd._gaussian_quantiles(16.0, 5, BY_KEY["SP500"]) is not None


def test_har_gaussian_scales_with_the_square_root_of_horizon():
    g5 = sd._gaussian_quantiles(16.0, 5, BY_KEY["SP500"])
    g20 = sd._gaussian_quantiles(16.0, 20, BY_KEY["SP500"])
    assert g20[0.75] / g5[0.75] == pytest.approx(2.0, rel=1e-9)   # sqrt(20/5)
    assert g5[0.50] == 0.0


def test_missing_vol_forecast_drops_only_that_comparator():
    """har_gaussian is optional; its absence must not cost the observation."""
    s = _series()
    records = [_record("2025-03-03", {"p25": -1.0, "p50": 0.2, "p75": 1.4})]  # no sigma
    obs = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))
    assert len(obs) == 1
    assert "har_gaussian" not in obs[0]["arms"]
    assert all(a in obs[0]["arms"] for a in sd.REQUIRED_ARMS)


def test_skill_is_computed_only_on_the_shared_subsample():
    """A comparator is never credited for days its rival could not see."""
    base = {"pinball_mean": 1.0}
    obs = [
        {"date": "2026-01-01", "arms": {"published": base, "unconditional": base,
                                        "har_gaussian": {"pinball_mean": 0.5}}},
        {"date": "2026-01-02", "arms": {"published": base, "unconditional": base}},
    ]
    # har_gaussian only scored one of the two days; its skill uses that day only.
    assert sd.skill_vs(obs, "har_gaussian") == pytest.approx(0.5)
    assert sd.skill_vs(obs, "published") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 3. Overlap: blocks, not raw n
# ---------------------------------------------------------------------------

def test_blocks_are_twenty_one_report_dates():
    import bias_separation
    # The block definition must match the one the rest of the project uses, or
    # two analyses of the same overlap will disagree about what is independent.
    assert sd.BLOCK_DAYS == bias_separation.BLOCK_DAYS == 21


def test_block_bootstrap_needs_at_least_two_blocks():
    obs = [{"date": f"2026-01-{d:02d}", "claim": "iqr", "inside_iqr": True}
           for d in range(1, 15)]
    assert sd.block_bootstrap(obs, sd._coverage) is None


def test_block_bootstrap_interval_brackets_the_point_estimate():
    rng = random.Random(5)
    obs = [{"date": f"2026-{m:02d}-{d:02d}", "claim": "iqr",
            "inside_iqr": rng.random() < 0.5}
           for m in range(1, 7) for d in range(1, 26)]
    point = sd._coverage(obs)
    ci = sd.block_bootstrap(obs, sd._coverage)
    assert ci is not None
    assert ci["lo"] <= point <= ci["hi"]
    assert ci["n_blocks"] >= 2


def test_block_bootstrap_is_deterministic_under_the_fixed_seed():
    obs = [{"date": f"2026-{m:02d}-{d:02d}", "claim": "iqr",
            "inside_iqr": (d % 2 == 0)}
           for m in range(1, 7) for d in range(1, 26)]
    assert sd.block_bootstrap(obs, sd._coverage) == sd.block_bootstrap(obs, sd._coverage)


# ---------------------------------------------------------------------------
# 4. The pre-committed bar — [KB-027]'s lesson, asserted
# ---------------------------------------------------------------------------

def _summary(**kw):
    base = {
        "n_blocks": 12,
        "n_interval_claims": 300,
        "coverage_iqr": 0.50,
        "coverage_ci": {"lo": 0.45, "hi": 0.55},
        "skill_vs_unconditional": {
            "published": {"skill": 0.05, "ci": {"lo": 0.02, "hi": 0.09}}
        },
    }
    base.update(kw)
    return base


def test_a_clean_pass_is_reachable():
    """The bar must be passable, or it is not a bar."""
    assert verdict_of(_summary()) == "edge"


def verdict_of(summary, sealed=True):
    return sd.verdict(summary, sealed=sealed)["verdict"]


def test_an_unsealed_slice_can_never_pass():
    """The median backfill was seen before the bar was written."""
    assert verdict_of(_summary(), sealed=False) == "exploratory"


def test_underpowered_disqualifies_before_anything_else():
    v = sd.verdict(_summary(n_blocks=3))
    assert v["verdict"] == "underpowered"
    assert "3" in v["reason"]


def test_miscalibration_disqualifies_even_with_strong_skill():
    """[KB-027]'s exact failure mode, inverted into a test.

    A big pinball skill must not be reachable past a coverage CI that excludes
    nominal — the disqualifier is checked first and returns on its own.
    """
    v = sd.verdict(_summary(
        coverage_iqr=0.31,
        coverage_ci={"lo": 0.25, "hi": 0.38},
        skill_vs_unconditional={"published": {"skill": 0.40,
                                              "ci": {"lo": 0.30, "hi": 0.50}}},
    ))
    assert v["verdict"] == "miscalibrated"


def test_inversion_disqualifies_and_is_its_own_verdict():
    """An inverted result is a finding, not merely an absent edge."""
    v = sd.verdict(_summary(
        skill_vs_unconditional={"published": {"skill": -0.08,
                                              "ci": {"lo": -0.14, "hi": -0.02}}}
    ))
    assert v["verdict"] == "inverted"


def test_a_skill_margin_of_almost_zero_does_not_pass():
    """[KB-027]: a floor of literally zero is not a skill threshold.

    +0.003 with a CI that excludes zero is exactly what previously printed
    "edge". Under MIN_SKILL it must read no_edge.
    """
    v = sd.verdict(_summary(
        skill_vs_unconditional={"published": {"skill": 0.003,
                                              "ci": {"lo": 0.001, "hi": 0.006}}}
    ))
    assert v["verdict"] == "no_edge"
    assert sd.MIN_SKILL > 0


def test_skill_above_the_margin_but_with_a_zero_spanning_ci_does_not_pass():
    v = sd.verdict(_summary(
        skill_vs_unconditional={"published": {"skill": 0.06,
                                              "ci": {"lo": -0.01, "hi": 0.13}}}
    ))
    assert v["verdict"] == "no_edge"


def test_no_resolved_interval_claims_is_underpowered_not_a_pass():
    assert verdict_of(_summary(n_interval_claims=0)) == "underpowered"


def test_seal_split_separates_the_interval_record_from_the_backfill():
    obs = [
        {"date": "2026-06-01", "claim": "median"},
        {"date": "2026-09-06", "claim": "iqr"},    # before the seal
        {"date": "2026-09-07", "claim": "iqr"},    # the seal date itself
        {"date": "2026-09-20", "claim": "iqr"},
    ]
    sealed, explore = sd.split_by_seal(obs)
    assert [o["date"] for o in sealed] == ["2026-09-07", "2026-09-20"]
    assert [o["date"] for o in explore] == ["2026-06-01", "2026-09-06"]
    assert len(sealed) + len(explore) == len(obs)


# ---------------------------------------------------------------------------
# Positive / negative controls on the whole pipeline
# ---------------------------------------------------------------------------

def test_no_skill_is_reported_on_a_stationary_process():
    """The negative control.

    On a stationary walk the unconditional empirical distribution IS the truth,
    so a correct published distribution has nothing to beat. A harness that
    reports skill here is manufacturing it.
    """
    s = _series(vol=0.01, seed=21)
    sig5 = 0.01 * math.sqrt(5) * 100
    records = [
        _record(d.date().isoformat(),
                {"p25": -0.6745 * sig5, "p50": 0.0, "p75": 0.6745 * sig5})
        for d in pd.bdate_range("2025-01-01", "2026-06-01")
    ]
    obs = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))
    skill = sd.skill_vs(obs, "published")
    assert abs(skill) < 0.05


def test_planted_skill_is_detected():
    """The positive control, in the shape WP-21.A used.

    The published distribution knows a regime the unconditional benchmark cannot
    see. If the harness cannot find skill here, a null it reports means nothing.
    """
    rng = random.Random(11)
    days = pd.bdate_range("2020-01-01", "2026-09-08")
    regime = [(i // 60) % 2 for i in range(len(days))]
    px = [100.0]
    for i in range(len(days) - 1):
        px.append(px[-1] * math.exp(rng.gauss(0.0, 0.02 if regime[i] else 0.005)))
    s = pd.Series(px, index=days)
    pos = {d: i for i, d in enumerate(days)}

    records = []
    for d in pd.bdate_range("2025-01-01", "2026-06-01"):
        vol = 0.02 if regime[pos[d]] else 0.005
        s5 = vol * math.sqrt(5) * 100
        records.append(_record(d.date().isoformat(),
                               {"p25": -0.6745 * s5, "p50": 0.0, "p75": 0.6745 * s5}))

    obs = sd.build_observations(records, {"SP500": s}, today=date(2026, 9, 8))
    assert sd.skill_vs(obs, "published") > sd.MIN_SKILL


# ---------------------------------------------------------------------------
# Log reading
# ---------------------------------------------------------------------------

def test_malformed_log_line_is_skipped_not_fatal(tmp_path):
    """One bad day must not stop the forward record from being scored."""
    (tmp_path / "2026-01-01.jsonl").write_text('{"date": "2026-01-01"}\n')
    (tmp_path / "2026-01-02.jsonl").write_text("{not json\n")
    (tmp_path / "2026-01-03.jsonl").write_text('{"date": "2026-01-03"}\n')
    got = sd.load_quant_log(tmp_path)
    assert [r["date"] for r in got] == ["2026-01-01", "2026-01-03"]


def test_log_records_come_back_in_date_order(tmp_path):
    for d in ("2026-03-01", "2026-01-01", "2026-02-01"):
        (tmp_path / f"{d}.jsonl").write_text(json.dumps({"date": d}) + "\n")
    assert [r["date"] for r in sd.load_quant_log(tmp_path)] == [
        "2026-01-01", "2026-02-01", "2026-03-01"]


def test_unknown_asset_key_in_the_log_is_ignored():
    rec = _record("2026-01-01", {"p50": 0.5}, asset="NotAnAsset")
    assert sd.published_claims(rec) == []


def test_unlogged_horizon_is_ignored():
    rec = _record("2026-01-01", {"p50": 0.5}, horizon=7)
    assert sd.published_claims(rec) == []


# ---------------------------------------------------------------------------
# 5. Pooling across a mixed universe
#
# The universe goes from three percent-scale assets to six on the 2026-09-13
# refit, and one of the new three (the 10Y) is scored in basis points. Two ways
# that breaks a pooled skill number:
#
#   * a ratio of pooled pinball losses is dominated by whichever asset has the
#     largest units — the 10Y's losses are ~50x an equity's, so the "product"
#     skill would silently become a 10Y skill;
#   * an equal-weighted mean fixes that but hands an asset five report dates old
#     the same vote as one with a year of record.
#
# These tests pin both, and pin that the bar reads the safe number.
# ---------------------------------------------------------------------------

def _pool_obs(asset, n_dates, pub, unc, horizon=5, start=0):
    """`n_dates` daily observations for one asset at fixed per-arm losses."""
    days = pd.bdate_range("2026-01-01", periods=start + n_dates)[start:]
    return [{
        "date": d.date().isoformat(),
        "asset": asset,
        "horizon": horizon,
        "claim": "iqr",
        "inside_iqr": True,
        "pit_bin": 1,
        "above_median": False,
        "arms": {"published": {"pinball_mean": pub},
                 "unconditional": {"pinball_mean": unc}},
    } for d in days]


def _mixed_universe(n_dates=44):
    """Three percent assets that beat the benchmark, one bp asset that loses."""
    obs = []
    for k in ("SP500", "Gold", "WTI Oil"):
        obs += _pool_obs(k, n_dates, pub=0.9, unc=1.0)      # skill +0.10
    obs += _pool_obs("UST10Y", n_dates, pub=55.0, unc=50.0)  # skill -0.10
    return obs


def test_a_basis_point_asset_dominates_the_naive_pooled_ratio():
    """The failure being fixed, stated first as a fact about the naive number."""
    obs = _mixed_universe()
    naive = sd.skill_vs(obs, "published")
    # Three of four assets beat the benchmark by 10%, yet the pooled ratio is
    # negative: the 10Y's basis-point losses carry both sides of the fraction.
    assert naive < -0.05


def test_pooled_skill_is_equal_weighted_and_survives_the_mixed_units():
    obs = _mixed_universe()
    pooled = sd.pooled_skill(obs)
    # (+0.10 +0.10 +0.10 -0.10) / 4
    assert pooled["skill"] == pytest.approx(0.05, abs=1e-4)
    assert pooled["weighting"] == "equal per asset"
    assert set(pooled["assets"]) == {"SP500", "Gold", "WTI Oil", "UST10Y"}


def test_pooling_on_the_stable_universe_excludes_the_new_assets():
    obs = _mixed_universe()
    stable = sd.pooled_skill(obs, keys=ORIGINAL_KEYS)
    assert stable["skill"] == pytest.approx(0.10, abs=1e-4)
    assert "UST10Y" not in stable["assets"]


def test_a_short_record_is_held_out_and_named():
    """An asset with one block has no CI of its own; it does not get a vote."""
    obs = _mixed_universe()
    obs += _pool_obs("DXY", 5, pub=0.1, unc=1.0)   # skill +0.90 on 5 dates
    pooled = sd.pooled_skill(obs)
    assert "DXY" not in pooled["assets"]
    assert pooled["excluded"]["DXY"] == 1          # blocks, not observations
    assert pooled["skill"] == pytest.approx(0.05, abs=1e-4)


def test_a_five_date_asset_cannot_move_the_headline():
    """The same pooled number with and without the newcomer."""
    before = sd.pooled_skill(_mixed_universe())["skill"]
    after = sd.pooled_skill(_mixed_universe() + _pool_obs("DXY", 5, 0.1, 1.0))["skill"]
    assert before == after


def test_an_asset_joins_the_pool_once_it_has_two_blocks():
    """The gate is a threshold, not a permanent exclusion."""
    obs = _mixed_universe() + _pool_obs("DXY", 2 * sd.BLOCK_DAYS, pub=0.5, unc=1.0)
    pooled = sd.pooled_skill(obs)
    assert "DXY" in pooled["assets"]
    assert pooled["skill"] == pytest.approx((0.10 * 3 - 0.10 + 0.50) / 5, abs=1e-4)


def test_pooled_skill_is_none_when_no_asset_qualifies():
    assert sd.pooled_skill(_pool_obs("SP500", 4, 0.9, 1.0)) is None


def test_a_multi_asset_summary_carries_no_unit_mixed_skill_field():
    """Structural: the unsafe number must not exist on a poolable slice."""
    s = sd.summarize(_mixed_universe(), horizon=5)
    assert "skill_vs_unconditional" not in s
    assert s["pooled_skill"] is not None
    assert s["pooled_universe"] == sorted(ORIGINAL_KEYS)


def test_a_single_asset_summary_still_carries_the_direct_ratio():
    """Within one asset the ratio is unit-free and remains the right statistic."""
    s = sd.summarize(_mixed_universe(), horizon=5, asset="UST10Y")
    assert s["skill_vs_unconditional"]["published"]["skill"] == pytest.approx(-0.10, abs=1e-4)
    assert "pooled_skill" not in s
    assert s["unit"] == "bp"


def test_the_bar_reads_the_pooled_number_not_the_unit_mixed_ratio():
    """A summary carrying both: the pooled field decides the verdict."""
    s = _summary(
        pooled_skill={"skill": -0.30, "ci": {"lo": -0.40, "hi": -0.20}},
        skill_vs_unconditional={
            "published": {"skill": 0.90, "ci": {"lo": 0.80, "hi": 0.95}}},
    )
    assert verdict_of(s) == "inverted"


def test_the_bar_falls_back_to_the_direct_ratio_on_a_single_asset_slice():
    s = _summary(pooled_skill=None)
    assert verdict_of(s) == "edge"
