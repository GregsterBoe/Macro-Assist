"""Run-config resolution and prompt rendering.

The accuracy-feedback half of this module was removed in v1.6 (WP-21.D) — see the
note at the bottom of the file."""
from __future__ import annotations

import json
import os
import re


from pipeline_common import (
    ACCURACY_JSON,
)


# ---------------------------------------------------------------------------
# Accuracy context (self-calibration feedback loop)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Run profile (WP-16 loosened-bundle experiment)
# ---------------------------------------------------------------------------
# MACRO_PROFILE selects an experiment arm:
#   control  (default) — current production config: Sonnet main, conviction
#                        floor ON, no base-rate-first restructure, hard rules kept.
#   loosened           — the WP-16 prompt bundle on reasonable assumptions
#                        (revised 2026-06-27): Opus 4.8 main, conviction floor OFF
#                        (B.1, KB-007), base-rate-first ON (C.3), hard rules pruned
#                        (B.4). Per the "loosen prompt testing" decision, these
#                        levers ship together and are judged in aggregate by Brier
#                        — not gated individually.
#
# Each toggle also has an individual env override (CONVICTION_FLOOR, BASE_RATE_FIRST,
# PRUNE_RULES, MACRO_MODEL) so a run matrix can mix them; the profile only sets
# defaults. The prompt files wrap each lever's text in <!-- CF/BR/PR:ON|OFF -->
# sentinels; _render_prompt strips the inactive arms so each run's prompt is clean
# (no contradictory instructions). The note frontmatter records the resolved config.

_PROFILES = {
    "control":  {"model": "claude-sonnet-4-6", "conviction_floor": True,  "base_rate_first": False, "prune_rules": False},
    "loosened": {"model": "claude-opus-4-8",   "conviction_floor": False, "base_rate_first": True,  "prune_rules": True},
}

# prompt-render sentinel tag -> config key it gates ("TAG:ON" kept when the key is True)
_PROMPT_TOGGLES = {"CF": "conviction_floor", "BR": "base_rate_first", "PR": "prune_rules"}


def _profile_name() -> str:
    name = os.getenv("MACRO_PROFILE", "control").strip().lower()
    return name if name in _PROFILES else "control"


def _env_bool(name: str, default: bool) -> bool:
    """Resolve a boolean env override: off/0/false/no -> False, else True; unset -> default."""
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return v.strip().lower() not in ("off", "0", "false", "no")


def run_config() -> dict:
    """Resolve the active run config: profile defaults + individual env overrides."""
    p = _PROFILES[_profile_name()]
    return {
        "profile":          _profile_name(),
        "model":            os.getenv("MACRO_MODEL", "").strip() or p["model"],
        "conviction_floor": _env_bool("CONVICTION_FLOOR", p["conviction_floor"]),
        "base_rate_first":  _env_bool("BASE_RATE_FIRST",  p["base_rate_first"]),
        "prune_rules":      _env_bool("PRUNE_RULES",      p["prune_rules"]),
    }


def main_model() -> str:
    """The model for the main analysis + adversarial review (sub-agents stay Haiku)."""
    return run_config()["model"]


def conviction_floor_on() -> bool:
    """True if the conviction-floor forcing rules are active for this run (default ON)."""
    return run_config()["conviction_floor"]


def _render_prompt(text: str, config: dict) -> str:
    """Strip the inactive sentinel arms from a prompt for the active config.

    For each toggle tag (CF/BR/PR), blocks wrapped in `<!-- TAG:ON-START -->...
    <!-- TAG:ON-END -->` are kept only when the config key is True; `TAG:OFF` only
    when False. All markers are removed either way, so the rendered prompt is clean.
    """
    for tag, key in _PROMPT_TOGGLES.items():
        drop = "OFF" if config[key] else "ON"
        text = re.sub(
            rf"<!-- {tag}:{drop}-START -->.*?<!-- {tag}:{drop}-END -->\n?",
            "", text, flags=re.DOTALL,
        )
    text = re.sub(r"<!-- (?:CF|BR|PR):(?:ON|OFF)-(?:START|END) -->\n?", "", text)
    return text


# ---------------------------------------------------------------------------
# REMOVED in v1.6 (WP-21.D): load_accuracy_context()
#
# It read accuracy_summary.json and built the prompt's "Your Historical Prediction
# Accuracy" block — a best-window-per-asset table, "anchor YOUR confidence to the
# window where directional accuracy is highest", and a set of bias rules. It was
# the self-calibration feedback loop: score the calls, feed the score back, steer
# next week's calls.
#
# [KB-024] closed the premise. The loop was tuning the direction and confidence of
# a call that three measurements say carries no information, so its last caller
# (llm_analysis.analyze_with_claude) was removed with the columns and this became
# ~120 lines of dead code reading a file nothing consumes.
#
# accuracy_summary.json is still WRITTEN by summarize_accuracy.py — it is the
# historical record, and bias_separation.py / the accuracy report still read it.
# Nothing reads it back into a prompt.
# ---------------------------------------------------------------------------
