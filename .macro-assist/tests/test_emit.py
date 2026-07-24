"""
test_emit.py — WP-19.B live/forward emission wiring (Phase 19 monetary slice).

No network / no API: a smart stub client answers both the L1 (submit_evidence) and
L2 (submit_brief) tool calls; fetch + consensus are monkeypatched. Verifies the
emitter writes a parseable, arm-tagged note to the scorer's results/ layout, dates
the prediction on `asof` (not the statement date), and is idempotent per day.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import score_predictions as sp
from exogenous import emit


class _StubBlock:
    def __init__(self, name, tool_input):
        self.type = "tool_use"
        self.name = name
        self.input = tool_input


class _StubResponse:
    def __init__(self, content):
        self.content = content


class _StubMessages:
    def create(self, **kwargs):
        tool = kwargs["tools"][0]["name"]
        if tool == "submit_evidence":
            return _StubResponse([_StubBlock("submit_evidence", {"claims": [
                {"claim": "Inflation elevated; committed to price stability.",
                 "stance": "hawkish", "magnitude": 0.3,
                 "affected_assets": ["10Y", "gold"], "confidence": 0.85},
            ]})])
        if tool == "submit_brief":
            return _StubResponse([_StubBlock("submit_brief", {
                "net_stance": {"label": "hawkish", "score": 0.2},
                "what_changed": "Hold with a hawkish tilt on elevated inflation.",
                "expectations_gap": "Gap near-neutral/structural.",
                "drivers": ["inflation elevated"],
                "ten_year": {"bias": "Bullish", "confidence": 0.4},
                "dxy": {"bias": "Bullish", "confidence": 0.35},
                "gold": {"bias": "Bearish", "confidence": 0.35},
                "brief_confidence": 0.5,
            })])
        raise AssertionError(f"unexpected tool {tool}")


class _StubClient:
    def __init__(self):
        self.messages = _StubMessages()


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(emit, "fetch_latest_statement", lambda asof=None: {
        "published": "2026-06-17", "source_id": "https://fed/monetary20260617a.htm",
        "text": "…statement text…",
    })
    monkeypatch.setattr(emit, "build_consensus", lambda asof, year: {
        "gap": {"gap": -0.16, "interpretation": "modest negative — partly STRUCTURAL"},
    })


class TestEmit:
    def test_writes_parseable_arm_tagged_note(self, patched, tmp_path):
        out = emit.emit_note(_StubClient(), asof=date(2026, 7, 24), results_dir=tmp_path)
        assert out is not None and out.exists()
        # correct results/<MM-Month>/<asof>-exogenous-macro.md layout
        assert out.name == "2026-07-24-exogenous-macro.md"
        assert out.parent.name == "07-July"

        fm = sp.parse_frontmatter(out)
        assert fm["arm"] == "exogenous"
        # prediction dated on asof (today), NOT the statement's 2026-06-17
        assert fm["as_of"] == "2026-07-24"

        preds = sp.parse_predictions(out)
        assert preds["10Y Treasury Yield"]["bias"] == "Bullish"
        assert preds["Gold"]["bias"] == "Bearish"

    def test_prediction_date_is_asof_not_statement(self, patched, tmp_path):
        out = emit.emit_note(_StubClient(), asof=date(2026, 7, 24), results_dir=tmp_path)
        # the scorer keys report_date off the filename → must be asof
        import re
        assert re.match(r"2026-07-24", out.name)

    def test_idempotent_per_day(self, patched, tmp_path):
        c = _StubClient()
        first = emit.emit_note(c, asof=date(2026, 7, 24), results_dir=tmp_path)
        marker = "SENTINEL — must not be overwritten"
        first.write_text(marker, encoding="utf-8")
        again = emit.emit_note(c, asof=date(2026, 7, 24), results_dir=tmp_path)
        assert again == first
        assert first.read_text(encoding="utf-8") == marker   # skipped, not rewritten

    def test_force_overwrites(self, patched, tmp_path):
        c = _StubClient()
        p = emit.emit_note(c, asof=date(2026, 7, 24), results_dir=tmp_path)
        p.write_text("stale", encoding="utf-8")
        emit.emit_note(c, asof=date(2026, 7, 24), results_dir=tmp_path, force=True)
        assert "arm: exogenous" in p.read_text(encoding="utf-8")

    def test_none_when_no_statement(self, monkeypatch, tmp_path):
        monkeypatch.setattr(emit, "fetch_latest_statement", lambda asof=None: None)
        assert emit.emit_note(_StubClient(), asof=date(2026, 7, 24), results_dir=tmp_path) is None
