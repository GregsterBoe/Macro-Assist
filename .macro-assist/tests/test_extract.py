"""
test_extract.py — WP-19.B L1 FOMC-text extractor (Phase 19 monetary slice).

Pure, no network: exercises the schema, prompt build, and enrichment/validation
(clamping, asset filtering, stance normalisation, metadata attachment), plus the
extract_evidence shell against a stub client (no real API call).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exogenous.extract import (
    ALLOWED_ASSETS,
    Evidence,
    ExtractedClaim,
    ExtractionResult,
    build_user_message,
    enrich_evidence,
    evidence_to_dicts,
    extract_evidence,
)


def _result(*claims: dict) -> ExtractionResult:
    return ExtractionResult(claims=[ExtractedClaim(**c) for c in claims])


class TestPrompt:
    def test_user_message_embeds_document(self):
        msg = build_user_message("  The Committee decided to hold rates.  ")
        assert "The Committee decided to hold rates." in msg


class TestEnrich:
    def test_attaches_metadata_and_iso_date(self):
        ev = enrich_evidence(
            _result({"claim": "Rates held steady.", "stance": "neutral",
                     "magnitude": 0.4, "affected_assets": ["10Y"], "confidence": 0.7}),
            "fomc_statement", "http://fed/x", date(2026, 6, 17),
        )
        assert len(ev) == 1
        e = ev[0]
        assert e.source_type == "fomc_statement" and e.source_id == "http://fed/x"
        assert e.published == "2026-06-17"

    def test_clamps_out_of_range_scores(self):
        ev = enrich_evidence(
            _result({"claim": "Strong hawkish shift.", "stance": "hawkish",
                     "magnitude": 1.9, "affected_assets": [], "confidence": -0.5}),
            "speech", "s1", "2026-06-17",
        )
        assert ev[0].magnitude == 1.0 and ev[0].extractor_conf == 0.0

    def test_filters_unknown_assets(self):
        ev = enrich_evidence(
            _result({"claim": "Dollar implications.", "stance": "hawkish",
                     "magnitude": 0.5, "affected_assets": ["DXY", "SPX", "oil", "gold"],
                     "confidence": 0.6}),
            "fomc_statement", "s", "2026-06-17",
        )
        assert ev[0].affected_assets == ["DXY", "gold"]
        assert set(ev[0].affected_assets) <= set(ALLOWED_ASSETS)

    def test_normalises_bad_stance_to_neutral(self):
        ev = enrich_evidence(
            _result({"claim": "Ambiguous.", "stance": "slightly hawkish",
                     "magnitude": 0.3, "affected_assets": [], "confidence": 0.5}),
            "fomc_statement", "s", "2026-06-17",
        )
        assert ev[0].stance == "neutral"

    def test_drops_empty_claims(self):
        ev = enrich_evidence(
            _result(
                {"claim": "   ", "stance": "hawkish", "magnitude": 0.5,
                 "affected_assets": [], "confidence": 0.5},
                {"claim": "Real claim.", "stance": "dovish", "magnitude": 0.5,
                 "affected_assets": [], "confidence": 0.5},
            ),
            "fomc_statement", "s", "2026-06-17",
        )
        assert len(ev) == 1 and ev[0].claim == "Real claim."

    def test_empty_result_gives_empty_list(self):
        assert enrich_evidence(ExtractionResult(), "fomc_statement", "s", "2026-06-17") == []

    def test_evidence_to_dicts_roundtrips(self):
        ev = enrich_evidence(
            _result({"claim": "c", "stance": "dovish", "magnitude": 0.5,
                     "affected_assets": ["gold"], "confidence": 0.5}),
            "fomc_statement", "s", "2026-06-17",
        )
        d = evidence_to_dicts(ev)[0]
        assert d["stance"] == "dovish" and d["affected_assets"] == ["gold"]


# --- shell against a stub client (no network) --------------------------------

class _StubBlock:
    def __init__(self, tool_input):
        self.type = "tool_use"
        self.name = "submit_evidence"
        self.input = tool_input


class _StubResponse:
    def __init__(self, content):
        self.content = content


class _StubMessages:
    def __init__(self, content):
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse(self._content)


class _StubClient:
    def __init__(self, content):
        self.messages = _StubMessages(content)


class TestExtractShell:
    def test_extracts_via_forced_tool_use(self):
        payload = {"claims": [
            {"claim": "Held rates; data-dependent.", "stance": "neutral",
             "magnitude": 0.4, "affected_assets": ["10Y"], "confidence": 0.8},
        ]}
        client = _StubClient([_StubBlock(payload)])
        ev = extract_evidence(client, "…statement text…", "fomc_statement",
                              "http://fed/2026a", date(2026, 6, 17))
        assert len(ev) == 1 and ev[0].affected_assets == ["10Y"]
        # forced tool_choice on the extraction tool
        call = client.messages.calls[0]
        assert call["tool_choice"] == {"type": "tool", "name": "submit_evidence"}
        assert call["tools"][0]["name"] == "submit_evidence"

    def test_returns_empty_when_no_tool_block(self):
        class _Text:
            type = "text"
        client = _StubClient([_Text()])
        assert extract_evidence(client, "x", "fomc_statement", "s", "2026-06-17") == []
