"""
test_citation_screen.py — WP-18.3 model-attention / citation screen.

Pure, no I/O: synthetic note text exercises alias matching (incl. the VIX vs
VIX3M boundary), rationale extraction (dashboard table + data snapshot excluded),
citation aggregation, and the ledger join / prune-priority logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citation_screen import (
    INPUT_ALIASES,
    aggregate_citations,
    cited_inputs,
    compile_patterns,
    extract_rationale,
    merge_with_ledger,
    render_screen_md,
    _version_ge,
)

PATS = compile_patterns(INPUT_ALIASES)


class TestAliasMatching:

    def test_vix_does_not_match_vix3m(self):
        # "VIX3M" must not count as a VIX mention (boundary), and vice versa.
        assert cited_inputs("term ratio flipped to backwardation", PATS) == {"vix3m"}
        got = cited_inputs("VIX surged to 20", PATS)
        assert "vix" in got and "vix3m" not in got

    def test_word_boundary_no_substring_false_positive(self):
        # "M2" must not fire on "M20"; "gold" not on "golden".
        assert "m2" not in cited_inputs("the M20 motorway", PATS)
        assert "gold" not in cited_inputs("a golden opportunity", PATS)

    def test_symbol_and_hyphen_aliases(self):
        got = cited_inputs("S&P 500 sat at its 50dMA while the 10-year fell", PATS)
        assert "sp500" in got and "treasury_10y" in got

    def test_case_insensitive(self):
        assert "cpi" in cited_inputs("cpi remains sticky", PATS)
        assert "nfci" in cited_inputs("financial conditions tightened", PATS)


class TestExtractRationale:

    SAMPLE = """---
agent_version: v1.5
---
# Macro Intelligence — 2026-06-26

### Executive Summary

Gold rose while DXY softened.

### Macro Dashboard

| Indicator | Current |
|-----------|---------|
| VIX | 20.04 |
| Bitcoin | 59,664 |

### Commodities

WTI crude fell sharply.

## Data Snapshot

### Markets

| Asset | Price |
|-------|-------|
| Nasdaq | 25,358 |
"""

    def test_excludes_data_snapshot(self):
        body = extract_rationale(self.SAMPLE)
        assert "Data Snapshot" not in body
        assert "Nasdaq" not in body          # snapshot-only ticker dropped

    def test_excludes_macro_dashboard_table(self):
        body = extract_rationale(self.SAMPLE)
        # The dashboard lists Bitcoin only inside the template table → dropped.
        assert "59,664" not in body
        assert "bitcoin" not in cited_inputs(body, PATS)

    def test_keeps_prose_sections(self):
        body = extract_rationale(self.SAMPLE)
        cited = cited_inputs(body, PATS)
        assert {"gold", "dxy", "wti_oil"} <= cited   # from Exec Summary + Commodities


class TestAggregate:

    def test_rate_is_note_presence_fraction(self):
        notes = [
            "Gold and the VIX both moved.",
            "Gold rallied again.",
            "Only rates today: the 10-year fell.",
        ]
        agg = aggregate_citations(notes, PATS)
        assert agg["gold"]["cited_in"] == 2 and agg["gold"]["rate"] == pytest.approx(2 / 3, abs=1e-3)
        assert agg["vix"]["cited_in"] == 1
        assert agg["treasury_10y"]["cited_in"] == 1
        # an input cited nowhere is rate 0, not absent
        assert agg["philly_fed_mfg"]["rate"] == 0.0


class TestMergeWithLedger:

    def _ledger(self):
        return {"entries": [
            {"name": "vix3m", "redundant": True, "info_score": 0.02, "flags": "REDUNDANT"},
            {"name": "gold", "redundant": False, "info_score": 0.55, "flags": "-"},
            {"name": "xlb", "redundant": True, "info_score": 0.17, "flags": "REDUNDANT"},
        ]}

    def test_priority_high_when_redundant_and_rare(self):
        agg = {
            "vix3m": {"cited_in": 0, "total": 50, "rate": 0.0},   # redundant + never cited
            "gold":  {"cited_in": 40, "total": 50, "rate": 0.8},  # not redundant, well cited
            "xlb":   {"cited_in": 30, "total": 50, "rate": 0.6},  # redundant but well cited
        }
        merged = merge_with_ledger(agg, self._ledger(), rare_rate=0.10)
        assert merged["vix3m"]["prune_priority"] == "high"
        assert merged["gold"]["prune_priority"] == "keep"
        assert merged["xlb"]["prune_priority"] == "watch"   # redundant only

    def test_rare_but_not_redundant_is_watch(self):
        agg = {"gold": {"cited_in": 2, "total": 50, "rate": 0.04}}
        merged = merge_with_ledger(agg, self._ledger(), rare_rate=0.10)
        assert merged["gold"]["prune_priority"] == "watch"

    def test_without_ledger_redundant_is_none(self):
        agg = {"gold": {"cited_in": 2, "total": 50, "rate": 0.04}}
        merged = merge_with_ledger(agg, None, rare_rate=0.10)
        assert merged["gold"]["redundant"] is None
        assert merged["gold"]["prune_priority"] == "watch"   # rare alone


class TestVersionCompare:

    def test_version_ge(self):
        assert _version_ge("v1.5", "v0.3") is True
        assert _version_ge("v0.2", "v0.3") is False
        assert _version_ge("v1.5", "v1.5") is True


class TestRender:

    def test_render_markdown(self):
        merged = merge_with_ledger(
            {"vix3m": {"cited_in": 0, "total": 10, "rate": 0.0}},
            {"entries": [{"name": "vix3m", "redundant": True, "info_score": 0.02, "flags": "REDUNDANT"}]},
            rare_rate=0.10,
        )
        text = "\n".join(render_screen_md(merged, 10, 0.10, has_ledger=True))
        assert "Citation Screen" in text
        assert "Strongest prune candidates" in text
        assert "vix3m" in text
