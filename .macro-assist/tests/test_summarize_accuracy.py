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
    _floor_ab_md_lines,
    calibration,
    calibration_by_floor,
    CALIB_BIN_EDGES,
    WINDOWS,
)


def _items(*pairs: tuple[int, float]) -> list[dict]:
    """[(confidence, score), ...] → score-observation dicts."""
    return [{"confidence": c, "score": s} for c, s in pairs]


def _report(version: str, window: str, assets: dict[str, tuple[str, int, float]],
            conviction_floor: str | None = None) -> dict:
    """Build a minimal score-file dict. assets: name -> (bias, confidence, score)."""
    report: dict = {"agent_version": version}
    if conviction_floor is not None:
        report["conviction_floor"] = conviction_floor
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


class TestCalibrationByFloor:

    def test_empty_when_no_tagged_reports(self):
        # Pre-flag reports have no conviction_floor field → no arms.
        assert calibration_by_floor([_report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)})]) == {}

    def test_splits_on_and_off_arms(self):
        reports = [
            _report("v1.0", "t5", {"A": ("Bullish", 70, 1.0)}, conviction_floor="on"),
            _report("v1.0", "t5", {"B": ("Bearish", 70, 0.0)}, conviction_floor="off"),
        ]
        by_floor = calibration_by_floor(reports)
        assert set(by_floor) == {"on", "off"}
        assert by_floor["on"]["n"] == 1
        assert by_floor["off"]["n"] == 1

    def test_ab_md_only_when_both_arms_present(self):
        one_arm = {"on": {"brier": 0.2, "brier_skill_score": 0.0, "ece": 0.1, "base_rate": 0.5, "n": 5}}
        assert _floor_ab_md_lines(one_arm) == []          # need both arms
        both = {
            "on":  {"brier": 0.28, "brier_skill_score": -0.2, "ece": 0.22, "base_rate": 0.36, "n": 40},
            "off": {"brier": 0.23, "brier_skill_score": 0.05, "ece": 0.04, "base_rate": 0.55, "n": 35},
        }
        text = "\n".join(_floor_ab_md_lines(both))
        assert "Conviction-floor A/B" in text
        assert "floor **on**" in text and "floor **off**" in text


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
