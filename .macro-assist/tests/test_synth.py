"""
test_synth.py — WP-19.B L3 ExoOutput lift + arm-tagging contract (Phase 19).

Pure, no network. Covers: BranchBrief → ExoOutput lift (canonical asset names,
0-100 confidence, citations from evidence), the regime note, and — the key L4
proof — a render → parse round-trip against the REAL score_predictions parser,
so an exogenous note flows through the existing scoring machinery as its own arm.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import score_predictions as sp
from exogenous.analyst import BranchBrief
from exogenous.extract import Evidence
from exogenous.synth import (
    ARM,
    ExoOutput,
    Lean,
    exo_to_dict,
    render_exo_note,
    to_exo_output,
)
from summarize_accuracy import calibration_by_arm


def _brief() -> BranchBrief:
    return BranchBrief(
        branch="monetary",
        as_of="2026-07-24",
        net_stance={"label": "hawkish", "score": 0.55},
        what_changed="Fed signalled on-hold-for-longer on stronger inflation.",
        expectations_gap="Communication reads tighter than the SPF path implies.",
        drivers=["sticky inflation", "no cuts yet"],
        asset_implications={
            "10Y":  {"bias": "Bullish", "confidence": 0.65},
            "DXY":  {"bias": "Bullish", "confidence": 0.60},
            "gold": {"bias": "Bearish", "confidence": 0.55},
        },
        brief_confidence=0.7,
    )


def _evidence() -> list[Evidence]:
    return [
        Evidence("Inflation sticky.", "fomc_statement", "fed/stmt-a", "2026-07-24",
                 "hawkish", 0.8, ["10Y", "DXY", "gold"], 0.9),
        Evidence("QT continues.", "fomc_statement", "fed/stmt-b", "2026-07-24",
                 "hawkish", 0.5, ["10Y", "DXY"], 0.9),
    ]


class TestLift:
    def test_canonical_names_and_arm(self):
        exo = to_exo_output(_brief())
        assert exo.arm == ARM
        assert set(exo.leans) == {"10Y Treasury Yield", "DXY", "Gold"}

    def test_confidence_scaled_to_0_100(self):
        exo = to_exo_output(_brief())
        assert exo.leans["10Y Treasury Yield"].confidence == 65
        assert exo.leans["Gold"].confidence == 55

    def test_bias_preserved(self):
        exo = to_exo_output(_brief())
        assert exo.leans["Gold"].bias == "Bearish"
        assert exo.leans["DXY"].bias == "Bullish"

    def test_citations_from_evidence_by_asset(self):
        exo = to_exo_output(_brief(), _evidence())
        # gold only appears in stmt-a; 10Y in both
        assert exo.leans["Gold"].citations == ["fed/stmt-a"]
        assert exo.leans["10Y Treasury Yield"].citations == ["fed/stmt-a", "fed/stmt-b"]

    def test_no_evidence_gives_empty_citations(self):
        exo = to_exo_output(_brief())
        assert exo.leans["DXY"].citations == []

    def test_regime_note_carries_stance_and_gap(self):
        exo = to_exo_output(_brief())
        assert "hawkish" in exo.regime_note
        assert "tighter" in exo.regime_note

    def test_exo_to_dict_nested(self):
        d = exo_to_dict(to_exo_output(_brief()))
        assert d["leans"]["Gold"]["bias"] == "Bearish"
        assert d["arm"] == ARM


class TestRenderRoundTrip:
    """The note the renderer emits must be parseable by the real scorer."""

    def test_frontmatter_and_table_parse(self, tmp_path):
        exo = to_exo_output(_brief(), _evidence())
        note = render_exo_note(exo)
        p = tmp_path / "2026-07-24-Friday-macro.md"
        p.write_text(note, encoding="utf-8")

        fm = sp.parse_frontmatter(p)
        assert fm.get("arm") == "exogenous"

        preds = sp.parse_predictions(p)
        assert preds is not None
        assert preds["10Y Treasury Yield"]["bias"] == "Bullish"
        assert preds["10Y Treasury Yield"]["confidence"] == 65
        assert preds["Gold"]["bias"] == "Bearish"
        assert preds["DXY"]["confidence"] == 60

    def test_review_date_present(self):
        note = render_exo_note(to_exo_output(_brief()), review_days=5)
        assert "Review date: 2026-07-29" in note


class TestArmSplit:
    """calibration_by_arm splits the same way profile does (DESIGN §4)."""

    def _score(self, arm, brier_conf, hit):
        # minimal score-file shape calibration() consumes (decisive call)
        return {
            "arm": arm,
            "windows": {"t5": {"assets": {"DXY": {"confidence": brier_conf, "score": hit}}}},
        }

    def test_splits_market_vs_exogenous(self):
        scores = [self._score("market", 70, 1.0), self._score("market", 60, 0.0),
                  self._score("exogenous", 65, 1.0), self._score("exogenous", 55, 1.0)]
        by_arm = calibration_by_arm(scores)
        assert set(by_arm) == {"market", "exogenous"}

    def test_single_arm_still_returned(self):
        # (the A/B renderer requires >=2, but the split itself returns what it has)
        by_arm = calibration_by_arm([self._score("exogenous", 65, 1.0)])
        assert set(by_arm) == {"exogenous"}
