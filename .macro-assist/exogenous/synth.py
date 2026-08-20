"""
synth.py — WP-19.B L3: lift the L2 `BranchBrief` into the scored `ExoOutput` (DESIGN §2/§3).

For the single monetary slice, L3 is a **deterministic** transform (no LLM): take
the brief's per-asset implications and express them as directional **leans** on the
scorer's canonical assets, tagged `arm: "exogenous"` for the A/B (DESIGN §4). A
multi-branch L3 would reconcile several briefs; here it lifts one.

It also renders the leans as a macro-note whose `### 5-Day Predictions` table and
frontmatter are **exactly the shape `score_predictions.py` already parses**, so an
exogenous note flows through the existing scoring + `summarize_accuracy` machinery
as its own arm with zero bespoke scoring code. The arm is scored forward-only
(DESIGN §6.2): the note is emitted now, scored when outcomes resolve.

Pure throughout (no network) — unit-tested, incl. a render→parse round-trip against
the real `score_predictions` parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

from exogenous.analyst import ASSET_CANONICAL, BranchBrief

ARM = "exogenous"          # this branch's A/B tag (DESIGN §4)
MARKET_ARM = "market"      # what existing (untagged) notes default to, scorer-side

_MAX_RATIONALE = 180


@dataclass
class Lean:
    bias: str                       # Bullish | Bearish | Neutral
    confidence: int                 # 0..100 (scorer scale)
    rationale: str
    citations: list[str] = field(default_factory=list)   # evidence source_ids


@dataclass
class ExoOutput:
    as_of: str                      # ISO date
    arm: str
    leans: dict                     # {canonical_asset: Lean}
    regime_note: str                # non-scored context
    scenario_map: list = field(default_factory=list)     # optional, non-scored


# ---------------------------------------------------------------------------
# Pure: lift BranchBrief -> ExoOutput
# ---------------------------------------------------------------------------

def _evi_get(e, key):
    return (e.get(key) if isinstance(e, dict) else getattr(e, key, None))


def _citations_for(short_asset: str, evidence) -> list[str]:
    """Distinct source_ids of evidence bearing on this (shorthand) asset."""
    seen: list[str] = []
    for e in (evidence or []):
        assets = _evi_get(e, "affected_assets") or []
        sid = _evi_get(e, "source_id")
        if short_asset in assets and sid and sid not in seen:
            seen.append(sid)
    return seen


def _cap(s: str, limit: int = _MAX_RATIONALE) -> str:
    s = " ".join((s or "").split()).replace("|", "/")   # no pipes (table-safe)
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def to_exo_output(brief: BranchBrief, evidence=None) -> ExoOutput:
    """Deterministic lift of one monetary `BranchBrief` into the scored `ExoOutput`."""
    label = brief.net_stance["label"]
    score = brief.net_stance["score"]
    stance_clause = f"Monetary net stance {label} ({score:+.2f})."

    leans: dict[str, Lean] = {}
    for short, impl in brief.asset_implications.items():
        canonical = ASSET_CANONICAL.get(short, short)
        leans[canonical] = Lean(
            bias=impl["bias"],
            confidence=int(round(float(impl["confidence"]) * 100)),
            rationale=_cap(f"{stance_clause} {brief.what_changed}"),
            citations=_citations_for(short, evidence),
        )
    regime_note = _cap(f"Net {label} ({score:+.2f}). "
                       f"Expectations gap: {brief.expectations_gap}", limit=400)
    return ExoOutput(as_of=brief.as_of, arm=ARM, leans=leans,
                     regime_note=regime_note, scenario_map=[])


def exo_to_dict(exo: ExoOutput) -> dict:
    d = asdict(exo)
    d["leans"] = {a: asdict(l) if isinstance(l, Lean) else l for a, l in exo.leans.items()}
    return d


# ---------------------------------------------------------------------------
# Pure: render the exogenous note (parseable by score_predictions.py)
# ---------------------------------------------------------------------------

def render_exo_note(exo: ExoOutput, review_days: int = 5) -> str:
    """Markdown note whose frontmatter + `### 5-Day Predictions` table match the
    format `score_predictions.parse_frontmatter` / `parse_predictions` expect.

    `arm: exogenous` is the A/B tag; the Target column is directional (the exogenous
    arm makes no numeric price target — scoring is directional, which score_call
    handles without a target range).
    """
    aod = date.fromisoformat(exo.as_of) if not isinstance(exo.as_of, date) else exo.as_of
    review = (aod + timedelta(days=review_days)).isoformat()

    rows = ["| Asset | Bias | Driver | Confidence | Target |",
            "| --- | --- | --- | --- | --- |"]
    for asset, lean in exo.leans.items():
        rows.append(f"| {asset} | {lean.bias} | {_cap(lean.rationale, 120)} "
                    f"| {lean.confidence}% | directional |")

    return (
        "---\n"
        f"arm: {exo.arm}\n"
        "branch: monetary\n"
        f"as_of: {exo.as_of}\n"
        "---\n\n"
        f"# Exogenous Monetary Brief — {exo.as_of}\n\n"
        f"Regime: {exo.regime_note}\n\n"
        "### 5-Day Predictions\n\n"
        + "\n".join(rows) + "\n\n"
        f"Review date: {review}\n"
    )
