"""Run-config resolution, prompt rendering, and accuracy-feedback context."""
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


def load_accuracy_context(floor_on: bool = True) -> str:
    """
    Read accuracy_summary.json and return a compact text block for injection
    into the Claude prompt. Returns empty string if no data exists yet.
    Includes a best-window summary so Claude anchors confidence to the horizon
    where each asset's signal is strongest, not uniformly to T+5.
    """
    if not ACCURACY_JSON.exists():
        return ""

    try:
        data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return ""

    windows = data.get("windows", {})
    n_total = data.get("n_reports_total", 0)
    as_of   = data.get("generated_at", "unknown")
    asset_order = ["S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin"]
    window_keys = ["t5", "t10", "t20"]
    window_labels = {"t5": "T+5", "t10": "T+10", "t20": "T+20"}

    # --- Compute best window per asset -------------------------------------------
    # Best = highest directional_acc at n>=8; tie-break on longer horizon.
    best: dict[str, dict] = {}
    for asset in asset_order:
        top_dacc, top_wkey, top_n = None, None, 0
        for wkey in reversed(window_keys):   # reversed = prefer longer horizon on tie
            wdata = windows.get(wkey, {})
            astat = wdata.get("by_asset", {}).get(asset, {})
            dacc  = astat.get("directional_acc")
            dn    = astat.get("directional_n", 0)
            if dacc is None or dn < 8:
                continue
            if top_dacc is None or dacc > top_dacc:
                top_dacc, top_wkey, top_n = dacc, wkey, dn
        best[asset] = {"wkey": top_wkey, "dacc": top_dacc, "n": top_n}

    # --- Best-window summary table ------------------------------------------------
    lines = [
        f"## Your Historical Prediction Accuracy (as of {as_of}, {n_total} reports scored)",
        "",
        "### Best Prediction Window Per Asset",
        "Anchor YOUR confidence to the window where directional accuracy is highest at n≥8.",
        (
            "Calling an asset Neutral at 50% when you have a ≥70% signal at T+10 or T+20 wastes genuine edge."
            if floor_on else
            "An all-Neutral table is acceptable when the honest read is no edge — make a directional call ONLY where you have genuine conviction."
        ),
        "",
        "| Asset | Best Window | Dir. Acc | n | Guidance |",
        "|-------|------------|---------|---|----------|",
    ]

    for asset in asset_order:
        b = best[asset]
        if b["wkey"] is None:
            lines.append(f"| {asset} | Insufficient data | — | — | Default Neutral; do not invent conviction |")
            continue
        wlabel = window_labels[b["wkey"]]
        dacc   = b["dacc"]
        n      = b["n"]
        if dacc >= 0.70:
            guidance = (
                "STRONG signal — make a directional call at ≥55% confidence" if floor_on
                else "STRONG signal — directional call supported at ≥55% if evidence agrees; Neutral OK otherwise"
            )
        elif dacc >= 0.60:
            guidance = "Moderate signal — directional call permitted at 52–60%"
        elif dacc <= 0.40:
            guidance = "SYSTEMATIC BIAS — direction demonstrably wrong; apply bias rules"
        else:
            guidance = "Coin flip — Neutral acceptable; widen range if directional"
        lines.append(f"| {asset} | {wlabel} | {dacc:.0%} | {n} | {guidance} |")

    lines.append("")
    if floor_on:
        lines += [
            "### Bias Rules (MANDATORY)",
            "- Any asset whose best-window directional accuracy is <40% at n≥8: weight market structure",
            "  and momentum at least equally to macro fundamentals. Do not repeat a call the data shows",
            "  has been wrong 8+ times — that is miscalibration, not caution.",
            "- Any asset whose best-window directional accuracy is ≥70% at n≥10: you MUST make a",
            "  directional call when the macro evidence points in a direction. Neutral at 50% is",
            "  not conservative here — it discards a real edge.",
            "",
        ]
    else:
        lines += [
            "### Bias Rules",
            "- Any asset whose best-window directional accuracy is <40% at n≥8: weight market structure",
            "  and momentum at least equally to macro fundamentals. Do not repeat a call the data shows",
            "  has been wrong 8+ times — that is miscalibration, not caution.",
            "- Conviction floor OFF: an all-Neutral table is acceptable. Make a directional call only where",
            "  you have genuine conviction; do not manufacture a call to avoid Neutral.",
            "",
        ]

    # --- Per-window breakdown (unchanged) -----------------------------------------
    lines.append("### Full Window Breakdown")
    for wkey in window_keys:
        wdata = windows.get(wkey)
        if not wdata or wdata.get("overall_accuracy") is None:
            continue
        ov = wdata["overall_accuracy"]
        n  = wdata["n_reports"]
        lines.append(f"**{window_labels[wkey]}** — overall {ov:.0%} ({n} reports)")
        for asset in asset_order:
            astat = wdata["by_asset"].get(asset)
            if not astat:
                continue
            acc      = astat["accuracy"]
            dacc     = astat["directional_acc"]
            dn       = astat["directional_n"]
            dacc_str = f"{dacc:.0%} (n={dn})" if dacc is not None else "n/a"
            lines.append(f"  - {asset}: accuracy {acc:.0%}, directional {dacc_str}")
        lines.append("")

    return "\n".join(lines)
