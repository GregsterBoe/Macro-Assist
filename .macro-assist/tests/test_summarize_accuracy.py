"""
test_summarize_accuracy.py — calibration (WP-16.B.2) unit tests.

Pure, no I/O: builds synthetic score observations / report dicts and checks the
Brier / BSS / ECE / reliability-bin math and the markdown rendering.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from summarize_accuracy import (
    _brier_and_reliability,
    _calibration_verdict,
    _calibration_md_lines,
    _commitment_md_lines,
    _ab_md_lines,
    calibration,
    calibration_by,
    calibration_by_floor,
    calibration_by_profile,
    commitment_stats,
    commitment_by_arm,
    profile_confound,
    CALIB_BIN_EDGES,
    WINDOWS,
)


def _items(*pairs: tuple[int, float]) -> list[dict]:
    """[(confidence, score), ...] → score-observation dicts."""
    return [{"confidence": c, "score": s} for c, s in pairs]


def _report(version: str, window: str, assets: dict[str, tuple[str, int, float]],
            conviction_floor: str | None = None, profile: str | None = None) -> dict:
    """Build a minimal score-file dict. assets: name -> (bias, confidence, score)."""
    report: dict = {"agent_version": version}
    if conviction_floor is not None:
        report["conviction_floor"] = conviction_floor
    if profile is not None:
        report["profile"] = profile
    return {
        **report,
        "windows": {
            window: {
                "assets": {
                    name: {"bias": bias, "confidence": conf, "score": score}
                    for name, (bias, conf, score) in assets.items()
                }
            }
        },
    }


class TestBrierAndReliability:

    def test_none_when_no_decisive_calls(self):
        # Neutral / flat (0.5) calls carry no binary outcome to calibrate.
        assert _brier_and_reliability(_items((60, 0.5), (70, 0.5))) is None
        assert _brier_and_reliability([]) is None

    def test_perfect_calibration_zero_ece(self):
        # 70%-confidence calls that are right exactly 70% of the time.
        items = _items(*([(70, 1.0)] * 7 + [(70, 0.0)] * 3))
        c = _brier_and_reliability(items)
        assert c["n"] == 10
        assert c["base_rate"] == pytest.approx(0.7)
        # Brier = 0.7*(0.3^2) + 0.3*(0.7^2) = 0.21
        assert c["brier"] == pytest.approx(0.21, abs=1e-6)
        assert c["ece"] == pytest.approx(0.0, abs=1e-9)
        # base-rate forecast Brier = 0.7*0.3 = 0.21 → BSS = 0
        assert c["brier_skill_score"] == pytest.approx(0.0, abs=1e-6)
        assert _calibration_verdict(c) == "well-calibrated"

    def test_overconfident_negative_gap(self):
        # Stated 90% but only 50% correct.
        items = _items(*([(90, 1.0)] * 5 + [(90, 0.0)] * 5))
        c = _brier_and_reliability(items)
        assert c["bins"][0]["gap"] < 0          # actual < predicted
        assert _calibration_verdict(c) == "overconfident"
        assert c["brier_skill_score"] < 0       # worse than the base-rate forecast

    def test_underconfident_positive_gap(self):
        # Stated 60% but 90% correct.
        items = _items(*([(60, 1.0)] * 9 + [(60, 0.0)] * 1))
        c = _brier_and_reliability(items)
        assert c["bins"][0]["gap"] > 0
        assert _calibration_verdict(c) == "underconfident"

    def test_excludes_flat_calls_from_n(self):
        items = _items((70, 1.0), (70, 0.0), (70, 0.5), (70, 0.5))
        c = _brier_and_reliability(items)
        assert c["n"] == 2  # only the decisive 0/1 calls

    def test_bin_assignment_and_edges(self):
        # 50→[50,60), 60→[60,70), 100→ final bin (inclusive).
        items = _items((50, 1.0), (60, 0.0), (100, 1.0))
        c = _brier_and_reliability(items)
        ranges = {b["range"]: b["n"] for b in c["bins"]}
        assert ranges.get("50-60") == 1
        assert ranges.get("60-70") == 1
        assert ranges.get(f"90-{CALIB_BIN_EDGES[-1]}") == 1

    def test_ece_is_weighted_average_of_abs_gap(self):
        # Bin A: conf .9, hit .5 → |gap| .4, n=6. Bin B: conf .6, hit .6 → |gap| 0, n=5.
        items = _items(
            *([(90, 1.0)] * 3 + [(90, 0.0)] * 3
              + [(60, 1.0)] * 3 + [(60, 0.0)] * 2)
        )
        c = _brier_and_reliability(items)
        # ECE = (6/11)*0.4 + (5/11)*0.0
        assert c["ece"] == pytest.approx((6 / 11) * 0.4, abs=1e-3)


class TestCalibrationAggregation:

    def test_pools_assets_and_windows(self):
        reports = [
            _report("v1.0", "t5", {
                "S&P 500": ("Bullish", 70, 1.0),
                "Gold":    ("Bearish", 70, 0.0),
            }),
            _report("v1.0", "t10", {
                "DXY": ("Bullish", 80, 1.0),
            }),
        ]
        calib = calibration(reports)
        assert calib["windows"]["t5"]["n"] == 2
        assert calib["windows"]["t10"]["n"] == 1
        assert calib["overall"]["n"] == 3   # pooled across windows

    def test_min_version_filter(self):
        reports = [
            _report("v0.1", "t5", {"A": ("Bullish", 70, 1.0)}),
            _report("v9.9", "t5", {"B": ("Bullish", 70, 0.0)}),
        ]
        full = calibration(reports)
        filtered = calibration(reports, min_version="v1.0")
        assert full["windows"]["t5"]["n"] == 2
        assert filtered["windows"]["t5"]["n"] == 1   # only the v9.9 report

    def test_empty_windows_are_none(self):
        calib = calibration([_report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)})])
        assert calib["windows"]["t10"] is None
        assert calib["windows"]["t20"] is None


class TestCalibrationBySplit:

    def test_untagged_floor_yields_no_arms(self):
        # An untagged conviction_floor really is unknown — nothing to split on.
        rs = [_report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)})]
        assert calibration_by_floor(rs) == {}

    def test_untagged_profile_counts_as_the_baseline_arm(self):
        # Untagged profile = pre-WP-16.B control population, not a gap. Dropping it
        # left the profile A/B with a single row and silently nothing to compare
        # against — the defect behind the unreadable loosened A/B [KB-023].
        rs = [_report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)})]
        assert set(calibration_by_profile(rs)) == {"baseline"}

    def test_profile_ab_has_both_arms_when_loosened_is_tagged(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}, profile="loosened"),
        ]
        assert set(calibration_by_profile(reports)) == {"baseline", "loosened"}

    def test_floor_splits_on_and_off_arms(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, conviction_floor="on"),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}, conviction_floor="off"),
        ]
        by_floor = calibration_by_floor(reports)
        assert set(by_floor) == {"on", "off"}
        assert by_floor["on"]["n"] == 1 and by_floor["off"]["n"] == 1

    def test_profile_split(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, profile="control"),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}, profile="loosened"),
        ]
        by_profile = calibration_by_profile(reports)
        assert set(by_profile) == {"control", "loosened"}

    def test_calibration_by_ignores_unknown_bucket(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, profile="loosened"),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}),  # no profile → "unknown", excluded
        ]
        assert set(calibration_by(reports, "profile")) == {"loosened"}

    def test_ab_md_only_when_two_or_more_arms(self):
        one_arm = {"control": {"brier": 0.2, "brier_skill_score": 0.0, "ece": 0.1, "base_rate": 0.5, "n": 5}}
        assert _ab_md_lines("Profile A/B", one_arm) == []   # need ≥2 arms
        both = {
            "control":  {"brier": 0.28, "brier_skill_score": -0.2, "ece": 0.22, "base_rate": 0.36, "n": 40},
            "loosened": {"brier": 0.23, "brier_skill_score": 0.05, "ece": 0.04, "base_rate": 0.55, "n": 35},
        }
        text = "\n".join(_ab_md_lines("Profile A/B (WP-16 — control vs loosened)", both))
        assert "Profile A/B" in text
        assert "**control**" in text and "**loosened**" in text


class TestCommitment:

    def test_none_when_empty(self):
        assert commitment_stats([]) is None
        assert commitment_stats([_report("v1.0", "t5", {})]) is None

    def test_all_neutral_zero_commitment(self):
        r = [_report("v1.0", "t5", {"A": ("Neutral", 60, 0.5), "B": ("Neutral", 55, 0.5)})]
        c = commitment_stats(r)
        assert c["commitment_rate"] == 0.0 and c["neutral_rate"] == 1.0
        assert c["net_decisive_edge"] == 0.0 and c["n_decisive"] == 0

    def test_directional_rates_and_edge(self):
        # A,B right · C wrong · D neutral · E committed-but-flat-outcome (0.5). total=5
        r = [_report("v1.0", "t5", {
            "A": ("Bullish", 70, 1.0),
            "B": ("Bearish", 70, 1.0),
            "C": ("Bullish", 70, 0.0),
            "D": ("Neutral", 50, 0.5),
            "E": ("Bearish", 60, 0.5),
        })]
        c = commitment_stats(r)
        assert c["n_resolved"] == 5
        assert c["n_directional"] == 4          # A,B,C,E
        assert c["commitment_rate"] == 0.8
        assert c["right_decisive_rate"] == pytest.approx(2 / 5, abs=1e-3)
        assert c["wrong_decisive_rate"] == pytest.approx(1 / 5, abs=1e-3)
        assert c["net_decisive_edge"] == pytest.approx((2 - 1) / 5, abs=1e-3)
        assert c["n_decisive"] == 3             # A,B,C (E's flat outcome not decisive)
        assert c["hit_rate_when_decisive"] == pytest.approx(2 / 3, abs=1e-3)

    def test_skips_unresolved(self):
        r = [_report("v1.0", "t5", {"A": ("Bullish", 70, None), "B": ("Bullish", 70, 1.0)})]
        assert commitment_stats(r)["n_resolved"] == 1

    def test_bias_fallback_uses_score(self):
        # blank bias → infer: score 1/0 is directional, 0.5 is non-committal
        r = [_report("v1.0", "t5", {"A": ("", 70, 1.0), "B": ("", 70, 0.5)})]
        c = commitment_stats(r)
        assert c["n_directional"] == 1
        assert c["right_decisive_rate"] == pytest.approx(1 / 2, abs=1e-3)
        assert c["neutral_rate"] == pytest.approx(1 / 2, abs=1e-3)

    def test_by_arm_splits_loosened_vs_baseline(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, profile="loosened"),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}, profile="control"),
            _report("v1.0", "t5", {"C": ("Neutral", 50, 0.5)}),   # no profile → baseline
        ]
        by = commitment_by_arm(reports)
        assert set(by) == {"baseline", "loosened"}
        assert by["loosened"]["n_resolved"] == 1
        assert by["baseline"]["n_resolved"] == 2     # control + untagged both pool into baseline

    def test_net_edge_negative_when_more_wrong(self):
        r = [_report("v1.0", "t5", {
            "A": ("Bullish", 70, 0.0), "B": ("Bearish", 70, 0.0), "C": ("Bullish", 70, 1.0),
        })]
        assert commitment_stats(r)["net_decisive_edge"] < 0

    def test_md_verdict_thesis_holds(self):
        by = {
            "baseline": {"n_resolved": 100, "commitment_rate": 0.56, "neutral_rate": 0.44,
                         "decisive_rate": 0.46, "wrong_decisive_rate": 0.29,
                         "right_decisive_rate": 0.17, "net_decisive_edge": -0.125,
                         "hit_rate_when_decisive": 0.36, "n_decisive": 46, "n_directional": 56},
            "loosened": {"n_resolved": 30, "commitment_rate": 0.20, "neutral_rate": 0.80,
                         "decisive_rate": 0.07, "wrong_decisive_rate": 0.07,
                         "right_decisive_rate": 0.0, "net_decisive_edge": -0.067,
                         "hit_rate_when_decisive": 0.0, "n_decisive": 2, "n_directional": 6},
        }
        text = "\n".join(_commitment_md_lines(by))
        assert "Commitment" in text and "thesis holds" in text
        assert "baseline" in text and "loosened" in text

    def test_md_empty_when_no_arms(self):
        assert _commitment_md_lines({}) == []


class TestCalibrationMarkdown:

    def test_renders_overall_and_per_window(self):
        reports = [
            _report("v1.0", w, {"A": ("Bullish", 90, 1.0), "B": ("Bearish", 90, 0.0)})
            for w in WINDOWS
        ]
        lines = _calibration_md_lines(calibration(reports))
        text = "\n".join(lines)
        assert "Calibration — Brier / Reliability" in text
        assert "Overall (all windows)" in text
        assert "Confidence bin" in text

    def test_handles_no_decisive_calls(self):
        reports = [_report("v1.0", "t5", {"A": ("Neutral", 50, 0.5)})]
        lines = _calibration_md_lines(calibration(reports))
        assert any("No decisive directional calls" in ln for ln in lines)


# ---------------------------------------------------------------------------
# Arm scoping and the profile confound (KB-023)
# ---------------------------------------------------------------------------

class TestArmScopingInAccuracy:

    def _mixed(self):
        market = _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, profile="loosened")
        market["arm"] = "market"
        kimi = _report("v1.0", "t5", {"A": ("Bearish", 90, 0.0)})
        kimi["arm"] = "kimi"
        return [market, kimi]

    def test_profile_split_excludes_other_arms(self):
        by_profile = calibration_by_profile(self._mixed())
        # The kimi report must not land in the baseline bucket just by not being
        # tagged 'loosened' — that is how three systems became one comparator.
        assert set(by_profile) == {"loosened"}

    def test_commitment_excludes_other_arms(self):
        by_arm = commitment_by_arm(self._mixed())
        assert "baseline" not in by_arm
        assert by_arm["loosened"]["n_resolved"] == 1


class TestProfileConfound:

    def test_zero_overlap_between_profiles_is_reported(self):
        reports = []
        for i, d in enumerate(["2026-03-02", "2026-03-03"]):
            r = _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)})
            r["report_date"], r["arm"] = d, "market"
            reports.append(r)
        for d in ["2026-05-04", "2026-05-05"]:
            r = _report("v1.0", "t5", {"A": ("Bullish", 70, 0.0)}, profile="loosened")
            r["report_date"], r["arm"] = d, "market"
            reports.append(r)
        pairs = profile_confound(reports)
        assert pairs
        assert all(v["confounded"] for v in pairs.values())

    def test_shared_dates_are_not_flagged(self):
        reports = []
        for d in ["2026-03-02", "2026-03-03"]:
            for prof in (None, "loosened"):
                r = _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, profile=prof)
                r["report_date"], r["arm"] = d, "market"
                reports.append(r)
        pairs = profile_confound(reports)
        assert pairs
        assert not any(v["confounded"] for v in pairs.values())

    def test_commitment_verdict_refuses_to_credit_a_confounded_arm(self):
        by_arm = {
            "baseline": {"n_resolved": 100, "commitment_rate": 0.56, "bullish_rate": 0.3,
                         "bearish_rate": 0.26, "bearish_share_of_directional": 0.46,
                         "wrong_decisive_rate": 0.29, "right_decisive_rate": 0.17,
                         "net_decisive_edge": -0.125, "hit_rate_when_decisive": 0.36,
                         "n_decisive": 46, "n_directional": 56, "n_bullish": 30,
                         "n_bearish": 26},
            "loosened": {"n_resolved": 30, "commitment_rate": 0.20, "bullish_rate": 0.19,
                         "bearish_rate": 0.01, "bearish_share_of_directional": 0.05,
                         "wrong_decisive_rate": 0.07, "right_decisive_rate": 0.0,
                         "net_decisive_edge": -0.067, "hit_rate_when_decisive": 0.0,
                         "n_decisive": 2, "n_directional": 6, "n_bullish": 6,
                         "n_bearish": 0},
        }
        confounded = {"baseline|loosened": {
            "n_shared": 0, "confounded": True,
            "span_a": ["2026-03-13", "2026-06-26"],
            "span_b": ["2026-06-29", "2026-08-21"],
        }}
        clean = "\n".join(_commitment_md_lines(by_arm, None))
        assert "the thesis holds so far" in clean

        warned = "\n".join(_commitment_md_lines(by_arm, confounded))
        assert "the thesis holds so far" not in warned
        assert "not attributable to the arm" in warned
        assert "share zero report-dates" in warned
