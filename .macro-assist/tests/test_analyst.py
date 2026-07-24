"""
test_analyst.py — WP-19.B L2 monetary analyst (Phase 19 monetary slice).

Pure, no network: payload assembly from evidence + consensus, brief
validation/normalisation/capping (clamp, stance/bias normalise, driver + text
caps, three-asset guarantee), plus the synthesize_brief shell against a stub.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exogenous.analyst import (
    ASSETS,
    ASSET_CANONICAL,
    BIASES,
    BRANCH,
    AssetImplication,
    BriefResult,
    NetStance,
    build_analyst_payload,
    brief_to_dict,
    brief_token_estimate,
    enrich_brief,
    synthesize_brief,
)
from exogenous.extract import Evidence


def _brief(
    label="hawkish", score=0.5, what="Held steady, signalled patience.",
    gap="Economists sit slightly above the dots.", drivers=None,
    ten=("Bullish", 0.6), dxy=("Bullish", 0.5), gold=("Bearish", 0.55), conf=0.6,
) -> BriefResult:
    return BriefResult(
        net_stance=NetStance(label=label, score=score),
        what_changed=what,
        expectations_gap=gap,
        drivers=drivers if drivers is not None else ["patience on cuts", "sticky core inflation"],
        ten_year=AssetImplication(bias=ten[0], confidence=ten[1]),
        dxy=AssetImplication(bias=dxy[0], confidence=dxy[1]),
        gold=AssetImplication(bias=gold[0], confidence=gold[1]),
        brief_confidence=conf,
    )


class TestPayload:
    def test_embeds_evidence_and_consensus(self):
        ev = [Evidence("Rates held; data-dependent.", "fomc_statement", "u", "2026-06-17",
                       "neutral", 0.4, ["10Y"], 0.8)]
        consensus = {"gap": {"gap": 0.16, "read": "economists above Fed dots"}}
        msg = build_analyst_payload(ev, consensus)
        assert "Rates held; data-dependent." in msg
        assert "economists above Fed dots" in msg

    def test_accepts_dict_evidence(self):
        ev = [{"claim": "Cut signalled.", "stance": "dovish", "magnitude": 0.7,
               "affected_assets": ["gold"], "source_type": "speech", "published": "2026-06-01"}]
        msg = build_analyst_payload(ev, None)
        assert "Cut signalled." in msg
        assert "none available" in msg

    def test_empty_evidence_ok(self):
        msg = build_analyst_payload([], None)
        assert "\"evidence\": []" in msg or '"evidence": []' in msg


class TestEnrich:
    def test_three_assets_always_present(self):
        b = enrich_brief(_brief(), date(2026, 6, 17))
        assert set(b.asset_implications) == set(ASSETS)
        assert b.branch == BRANCH and b.as_of == "2026-06-17"

    def test_clamps_stance_score_and_confidence(self):
        b = enrich_brief(_brief(score=2.5, conf=-0.3, ten=("Bullish", 1.8)), "2026-06-17")
        assert b.net_stance["score"] == 1.0
        assert b.brief_confidence == 0.0
        assert b.asset_implications["10Y"]["confidence"] == 1.0

    def test_negative_stance_score_clamps_to_minus_one(self):
        b = enrich_brief(_brief(score=-4.0), "2026-06-17")
        assert b.net_stance["score"] == -1.0

    def test_normalises_bad_label_and_bias(self):
        b = enrich_brief(_brief(label="very hawkish", gold=("plummeting", 0.5)), "2026-06-17")
        assert b.net_stance["label"] == "neutral"
        assert b.asset_implications["gold"]["bias"] == "Neutral"

    def test_bias_capitalisation_normalised(self):
        b = enrich_brief(_brief(ten=("bullish", 0.5)), "2026-06-17")
        assert b.asset_implications["10Y"]["bias"] == "Bullish"
        assert b.asset_implications["10Y"]["bias"] in BIASES

    def test_caps_driver_count(self):
        b = enrich_brief(_brief(drivers=[f"d{i}" for i in range(20)]), "2026-06-17")
        assert len(b.drivers) == 6

    def test_drops_empty_drivers(self):
        b = enrich_brief(_brief(drivers=["real", "  ", ""]), "2026-06-17")
        assert b.drivers == ["real"]

    def test_caps_long_text(self):
        b = enrich_brief(_brief(what="x" * 900), "2026-06-17")
        assert len(b.what_changed) <= 400
        assert b.what_changed.endswith("…")

    def test_token_estimate_under_cap(self):
        b = enrich_brief(_brief(), "2026-06-17")
        assert brief_token_estimate(b) < 600

    def test_canonical_map_matches_scorer_names(self):
        assert ASSET_CANONICAL["10Y"] == "10Y Treasury Yield"
        assert ASSET_CANONICAL["gold"] == "Gold"
        assert ASSET_CANONICAL["DXY"] == "DXY"

    def test_brief_to_dict_roundtrips(self):
        d = brief_to_dict(enrich_brief(_brief(), "2026-06-17"))
        assert d["asset_implications"]["gold"]["bias"] == "Bearish"
        assert d["net_stance"]["label"] == "hawkish"


# --- shell against a stub client (no network) --------------------------------

class _StubBlock:
    def __init__(self, tool_input):
        self.type = "tool_use"
        self.name = "submit_brief"
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


class TestSynthesizeShell:
    def test_synthesises_via_forced_tool_use(self):
        payload = {
            "net_stance": {"label": "hawkish", "score": 0.4},
            "what_changed": "Signalled fewer cuts.",
            "expectations_gap": "Above the dots.",
            "drivers": ["sticky inflation"],
            "ten_year": {"bias": "Bullish", "confidence": 0.6},
            "dxy": {"bias": "Bullish", "confidence": 0.5},
            "gold": {"bias": "Bearish", "confidence": 0.5},
            "brief_confidence": 0.6,
        }
        client = _StubClient([_StubBlock(payload)])
        brief = synthesize_brief(client, [], {"gap": None}, date(2026, 6, 17))
        assert brief is not None
        assert brief.net_stance["label"] == "hawkish"
        assert brief.asset_implications["gold"]["bias"] == "Bearish"
        call = client.messages.calls[0]
        assert call["tool_choice"] == {"type": "tool", "name": "submit_brief"}
        assert call["tools"][0]["name"] == "submit_brief"

    def test_returns_none_when_no_tool_block(self):
        class _Text:
            type = "text"
        client = _StubClient([_Text()])
        assert synthesize_brief(client, [], None, "2026-06-17") is None
