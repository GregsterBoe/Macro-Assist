"""
test_conviction_floor.py — WP-16.B.1 conviction-floor flag + prompt rendering.

Pure unit tests for the env flag and the sentinel-stripping prompt renderer,
plus a guard that the real prompt files round-trip cleanly in both arms.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_and_analyze as ca

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class TestConvictionFloorFlag:

    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("CONVICTION_FLOOR", raising=False)
        assert ca.conviction_floor_on() is True

    @pytest.mark.parametrize("val", ["off", "OFF", "0", "false", "No", " off "])
    def test_off_values(self, monkeypatch, val):
        monkeypatch.setenv("CONVICTION_FLOOR", val)
        assert ca.conviction_floor_on() is False

    @pytest.mark.parametrize("val", ["on", "1", "true", "yes", "anything"])
    def test_on_values(self, monkeypatch, val):
        monkeypatch.setenv("CONVICTION_FLOOR", val)
        assert ca.conviction_floor_on() is True


class TestRenderConviction:

    SAMPLE = (
        "intro line\n"
        "<!-- CF:ON-START -->- floor rule: all-Neutral not acceptable<!-- CF:ON-END -->\n"
        "- neutral keep line\n"
        "<!-- CF:OFF-START -->- floor OFF: all-Neutral acceptable<!-- CF:OFF-END -->\n"
        "outro line\n"
    )

    def test_floor_on_keeps_on_drops_off(self):
        out = ca._render_conviction(self.SAMPLE, True)
        assert "floor rule" in out
        assert "floor OFF" not in out
        assert "CF:" not in out          # all markers stripped
        assert "neutral keep line" in out

    def test_floor_off_keeps_off_drops_on(self):
        out = ca._render_conviction(self.SAMPLE, False)
        assert "floor rule" not in out
        assert "floor OFF" in out
        assert "CF:" not in out
        assert "neutral keep line" in out

    def test_no_markers_is_identity(self):
        plain = "no sentinels here\njust text\n"
        assert ca._render_conviction(plain, True) == plain
        assert ca._render_conviction(plain, False) == plain


class TestRealPromptFiles:
    """Guard the actual prompt files: markers must be balanced and strip clean."""

    @pytest.mark.parametrize("fname", ["system_prompt.md", "system_prompt_structured.md"])
    def test_round_trips_both_arms(self, fname):
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        # Balanced sentinels.
        assert raw.count("<!-- CF:ON-START -->") == raw.count("<!-- CF:ON-END -->")
        assert raw.count("<!-- CF:OFF-START -->") == raw.count("<!-- CF:OFF-END -->")
        assert raw.count("<!-- CF:ON-START -->") >= 1   # the floor exists by default

        on = ca._render_conviction(raw, True)
        off = ca._render_conviction(raw, False)
        for rendered in (on, off):
            assert "CF:" not in rendered           # no leaked markers
        # The all-Neutral floor language only appears in the ON arm.
        assert "not acceptable" in on
        assert "not acceptable" not in off
        # The OFF arm explicitly permits Neutral.
        assert "floor OFF" in off
        assert "floor OFF" not in on
