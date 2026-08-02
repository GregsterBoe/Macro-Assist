"""
test_kimi_arm.py — Kimi ensemble model arm (experimental).

Pure, no network. Focus = the ENSEMBLE CONFIDENCE aggregation (agreement-based,
un-clamped, abstains to Neutral on disagreement), plus payload extraction, sample
parsing/canonicalisation, and a render→scorer round-trip.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import score_predictions as sp
from kimi_arm import (
    ASSETS,
    aggregate,
    extract_user_message,
    parse_sample,
    parse_sample_from_text,
    render_kimi_note,
)


def _samples(**per_asset_lists):
    """Build N sample dicts from {asset: [bias, bias, ...]} columns of equal length."""
    n = max(len(v) for v in per_asset_lists.values())
    out = []
    for i in range(n):
        s = {}
        for a, lst in per_asset_lists.items():
            if i < len(lst):
                s[a] = lst[i]
        out.append(s)
    return out


class TestExtractUserMessage:
    def test_pulls_body_between_separators(self):
        bar = "=" * 72
        preview = (
            "# header\nmeta\n\n"
            + bar + "\nMAIN ANALYSIS PAYLOAD (verbatim)\n" + bar + "\n\n"
            + "Today is Friday.\n## FRED\n{...data...}\n\n"
            + bar + "\nWITHHELD SIGNALS\nsecret\n"
        )
        body = extract_user_message(preview)
        assert "Today is Friday." in body and "## FRED" in body
        assert "WITHHELD" not in body and "MAIN ANALYSIS PAYLOAD" not in body

    def test_falls_back_when_no_separators(self):
        assert extract_user_message("just text") == "just text"


class TestParseSample:
    def test_tool_calls_shape_canonicalised(self):
        obj = {"calls": [{"asset": "SP500", "bias": "bullish"},
                         {"asset": "10Y yield", "bias": "Bearish"},
                         {"asset": "BTC", "bias": "neutral"}]}
        got = parse_sample(obj)
        assert got == {"S&P 500": "Bullish", "10Y Treasury Yield": "Bearish", "Bitcoin": "Neutral"}

    def test_plain_dict(self):
        got = parse_sample({"Gold": "Bullish", "WTI crude": "Bearish", "Dollar": "Neutral"})
        assert got == {"Gold": "Bullish", "WTI Oil": "Bearish", "DXY": "Neutral"}

    def test_drops_unknown_asset_or_bias(self):
        assert parse_sample({"Tesla": "Bullish", "Gold": "sideways"}) == {}

    def test_from_text_embedded_json(self):
        text = 'Here you go:\n{"S&P 500":"Bullish","Gold":"Neutral"}\nThanks!'
        assert parse_sample_from_text(text) == {"S&P 500": "Bullish", "Gold": "Neutral"}

    def test_from_text_no_json(self):
        assert parse_sample_from_text("no json here") == {}


class TestAggregateConfidence:
    def test_unanimous_is_max_confidence(self):
        s = _samples(**{"S&P 500": ["Bullish"] * 10})
        r = aggregate(s)["S&P 500"]
        assert r["bias"] == "Bullish" and r["confidence"] == 100 and r["n"] == 10

    def test_confidence_is_unclamped_above_80(self):
        # 9/10 agreement → confidence 90, which the market arm (50–80 clamp) could never emit
        s = _samples(**{"Gold": ["Bullish"] * 9 + ["Bearish"]})
        r = aggregate(s)["Gold"]
        assert r["bias"] == "Bullish" and r["confidence"] == 90

    def test_weak_majority_still_commits_at_threshold(self):
        # 6 Bull / 4 Bear = 0.60 share ≥ 0.55 → Bullish @ 60
        s = _samples(**{"DXY": ["Bullish"] * 6 + ["Bearish"] * 4})
        r = aggregate(s)["DXY"]
        assert r["bias"] == "Bullish" and r["confidence"] == 60

    def test_split_abstains_to_neutral(self):
        # 5 Bull / 5 Bear = 0.50 < 0.55 → Neutral (honest abstention)
        s = _samples(**{"Bitcoin": ["Bullish"] * 5 + ["Bearish"] * 5})
        r = aggregate(s)["Bitcoin"]
        assert r["bias"] == "Neutral"

    def test_neutral_plurality_abstains(self):
        s = _samples(**{"WTI Oil": ["Neutral"] * 6 + ["Bullish"] * 4})
        r = aggregate(s)["WTI Oil"]
        assert r["bias"] == "Neutral"

    def test_missing_asset_gives_neutral_n0(self):
        r = aggregate([{"Gold": "Bullish"}])  # no S&P votes at all
        assert r["S&P 500"] == {"bias": "Neutral", "confidence": 50, "agreement": 0.0, "n": 0, "votes": {}}

    def test_all_six_assets_present(self):
        assert set(aggregate([{"Gold": "Bullish"}])) == set(ASSETS)


class TestRenderRoundTrip:
    def test_note_parses_with_scorer(self, tmp_path):
        s = _samples(**{
            "S&P 500": ["Bearish"] * 7 + ["Bullish"] * 3,
            "10Y Treasury Yield": ["Bullish"] * 9 + ["Neutral"],
            "Gold": ["Bullish"] * 5 + ["Bearish"] * 5,   # → Neutral
        })
        note = render_kimi_note(aggregate(s), date(2026, 8, 3), n=10)
        p = tmp_path / "2026-08-03-kimi-macro.md"
        p.write_text(note, encoding="utf-8")

        assert sp.parse_frontmatter(p).get("arm") == "kimi"
        preds = sp.parse_predictions(p)
        assert preds["S&P 500"]["bias"] == "Bearish" and preds["S&P 500"]["confidence"] == 70
        assert preds["10Y Treasury Yield"]["bias"] == "Bullish" and preds["10Y Treasury Yield"]["confidence"] == 90
        assert preds["Gold"]["bias"] == "Neutral"
