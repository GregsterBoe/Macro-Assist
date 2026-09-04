"""
test_conviction_floor.py — WP-16 run-config + prompt rendering.

Pure unit tests for run_config() profile resolution, the env flags, the
sentinel-stripping prompt renderer (CF/BR/PR), and a guard that the real prompt
files round-trip cleanly in both the control and loosened arms.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_and_analyze as ca

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Toggle keys a config dict must carry for _render_prompt.
_CTRL = {"conviction_floor": True,  "base_rate_first": False, "prune_rules": False}
_LOOSE = {"conviction_floor": False, "base_rate_first": True,  "prune_rules": True}


def _clean_env(monkeypatch):
    for k in ("MACRO_PROFILE", "MACRO_MODEL", "CONVICTION_FLOOR", "BASE_RATE_FIRST", "PRUNE_RULES"):
        monkeypatch.delenv(k, raising=False)


class TestRunConfig:

    def test_default_is_control(self, monkeypatch):
        _clean_env(monkeypatch)
        cfg = ca.run_config()
        assert cfg["profile"] == "control"
        assert cfg["model"] == "claude-sonnet-4-6"
        assert cfg == {"profile": "control", "model": "claude-sonnet-4-6",
                       "conviction_floor": True, "base_rate_first": False, "prune_rules": False}

    def test_loosened_profile(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("MACRO_PROFILE", "loosened")
        cfg = ca.run_config()
        assert cfg["model"] == "claude-opus-4-8"
        assert cfg["conviction_floor"] is False
        assert cfg["base_rate_first"] is True
        assert cfg["prune_rules"] is True

    def test_unknown_profile_falls_back_to_control(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("MACRO_PROFILE", "bogus")
        assert ca.run_config()["profile"] == "control"

    def test_individual_env_overrides_profile(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("MACRO_PROFILE", "loosened")
        monkeypatch.setenv("CONVICTION_FLOOR", "on")   # override the loosened default
        monkeypatch.setenv("MACRO_MODEL", "claude-haiku-4-5")
        cfg = ca.run_config()
        assert cfg["conviction_floor"] is True
        assert cfg["model"] == "claude-haiku-4-5"
        assert cfg["base_rate_first"] is True          # untouched loosened default


class TestConvictionFloorFlag:

    def test_default_on(self, monkeypatch):
        _clean_env(monkeypatch)
        assert ca.conviction_floor_on() is True

    @pytest.mark.parametrize("val", ["off", "OFF", "0", "false", "No", " off "])
    def test_off_values(self, monkeypatch, val):
        _clean_env(monkeypatch)
        monkeypatch.setenv("CONVICTION_FLOOR", val)
        assert ca.conviction_floor_on() is False

    @pytest.mark.parametrize("val", ["on", "1", "true", "yes", "anything"])
    def test_on_values(self, monkeypatch, val):
        _clean_env(monkeypatch)
        monkeypatch.setenv("CONVICTION_FLOOR", val)
        assert ca.conviction_floor_on() is True


class TestRenderPrompt:

    SAMPLE = (
        "intro line\n"
        "<!-- CF:ON-START -->- floor rule: all-Neutral not acceptable<!-- CF:ON-END -->\n"
        "- neutral keep line\n"
        "<!-- CF:OFF-START -->- floor OFF: all-Neutral acceptable<!-- CF:OFF-END -->\n"
        "<!-- BR:ON-START -->- base-rate-first rule<!-- BR:ON-END -->\n"
        "<!-- PR:OFF-START -->- hard override rule<!-- PR:OFF-END -->\n"
        "outro line\n"
    )

    def test_control_keeps_forcing_and_overrides_drops_loosened(self):
        out = ca._render_prompt(self.SAMPLE, _CTRL)
        assert "floor rule" in out          # CF:ON kept (floor on)
        assert "floor OFF" not in out       # CF:OFF dropped
        assert "base-rate-first rule" not in out   # BR:ON dropped (brf off)
        assert "hard override rule" in out  # PR:OFF kept (not pruning)
        assert "neutral keep line" in out
        assert "CF:" not in out and "BR:" not in out and "PR:" not in out

    def test_loosened_drops_forcing_and_overrides_adds_loosened(self):
        out = ca._render_prompt(self.SAMPLE, _LOOSE)
        assert "floor rule" not in out      # CF:ON dropped (floor off)
        assert "floor OFF" in out           # CF:OFF kept
        assert "base-rate-first rule" in out   # BR:ON kept (brf on)
        assert "hard override rule" not in out # PR:OFF dropped (pruned)
        assert "neutral keep line" in out
        assert "CF:" not in out and "BR:" not in out and "PR:" not in out

    def test_no_markers_is_identity(self):
        plain = "no sentinels here\njust text\n"
        assert ca._render_prompt(plain, _CTRL) == plain
        assert ca._render_prompt(plain, _LOOSE) == plain


class TestRealPromptFiles:
    """Guard the actual prompt files.

    Until v1.5 these tests asserted that the CF/BR/PR blocks rendered
    differently per arm — that was the conviction-floor A/B's contract.
    WP-21.D removed every one of those blocks with the directional product they
    gated ([KB-024]), so the contract inverts: the two arms must now render
    IDENTICALLY, and neither may ask for a call.
    """

    _FILES = ["system_prompt.md", "system_prompt_structured.md"]

    @pytest.mark.parametrize("fname", _FILES)
    def test_markers_balanced(self, fname):
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        for tag in ("CF", "BR", "PR"):
            assert raw.count(f"<!-- {tag}:ON-START -->") == raw.count(f"<!-- {tag}:ON-END -->")
            assert raw.count(f"<!-- {tag}:OFF-START -->") == raw.count(f"<!-- {tag}:OFF-END -->")

    @pytest.mark.parametrize("fname", _FILES)
    def test_no_profile_markers_remain(self, fname):
        """v1.6: every arm-gated block was a directional-call rule and is gone."""
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        for tag in ("CF", "BR", "PR"):
            assert f"<!-- {tag}:" not in raw, f"{fname} still carries a {tag} block"

    @pytest.mark.parametrize("fname", _FILES)
    def test_both_arms_render_identically(self, fname):
        """The prompt toggles are inert — control and loosened get the same text."""
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        ctrl = ca._render_prompt(raw, _CTRL)
        loose = ca._render_prompt(raw, _LOOSE)
        assert ctrl == loose == raw

    @pytest.mark.parametrize("fname", _FILES)
    def test_prompt_asks_for_no_directional_call(self, fname):
        """The regression guard for the cut itself.

        Phrases here are the ones that actually shipped a call: a bias field, a
        confidence number, or a rule that forces one. Prose *about* not making a
        call is fine, so match the instruction forms, not the bare words —
        "Bullish" still legitimately appears in the macro-dashboard signal matrix,
        which is an indicator-implication grid, not a per-asset scored call.
        """
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        banned = [
            "| Asset | Bias |",
            "confidence_pct",
            "Minimum conviction",
            "minimum conviction rule",
            "Confidence diversity",
            "Cross-horizon discount",
            "Best-window rule",
            "Systematic bias override",
            "contrarian bias correction",
            "5-Day Predictions",
        ]
        for phrase in banned:
            assert phrase not in raw, f"{fname} still contains directional instruction: {phrase!r}"

    @pytest.mark.parametrize("fname", _FILES)
    def test_prompt_states_the_cut(self, fname):
        raw = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
        assert "makes no directional call" in raw
        assert "5-Day Outlook" in raw
