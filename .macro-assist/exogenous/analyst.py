"""
analyst.py — WP-19.B L2: fuse L1 `Evidence` + L0 consensus → the bounded `BranchBrief`.

The **expensive-synthesise** stage (DESIGN §7: Haiku extract, Opus synth). Takes
the FOMC evidence extracted at L1 and the non-market consensus anchor from L0
(SPF economist path + SEP dot-plot + the SPF-vs-SEP gap) and produces the capped
`BranchBrief` (DESIGN §2 L2): net stance, what changed, the expectations-gap read,
top drivers, and a directional bias on each scored asset.

Split like the rest of the package: **payload assembly + brief validation/capping
are pure** (unit-tested with synthetic input, no network); `synthesize_brief` is
the thin shell that calls Claude via the codebase's forced-tool-use pattern.

ASSET SEMANTICS (matched to score_predictions.py so the A/B is like-for-like):
  - "10Y" is scored on the **yield** (^TNX) → hawkish ⇒ higher yield ⇒ **Bullish**.
  - "DXY"  → hawkish ⇒ stronger dollar ⇒ **Bullish**.
  - "gold" → hawkish ⇒ higher real rates ⇒ **Bearish**.
The brief keeps the DESIGN shorthand keys {10Y, DXY, gold}; L3 maps them to the
scorer's canonical names in ASSET_CANONICAL when it lifts to the scored ExoOutput.

HARD CAP ≈ 600 tokens on the brief (DESIGN §2) — the scalability guarantee. Enforced
deterministically in `enrich_brief` (text fields + driver count capped), not left to
the model. `brief_token_estimate` reports the rough budget used.

CONFIRM-ON-FIRST-RUN: net-stance calibration and whether the asset biases follow the
evidence need an eyeball on the first real run (run the slice via the CI smoke
workflow and read the brief) before the leans are trusted on the scoreboard.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

# Expensive synthesiser — the Opus side of the cheap/expensive split (DESIGN §7).
MODEL = "claude-opus-4-8"

BRANCH = "monetary"
ASSETS = ("10Y", "DXY", "gold")            # DESIGN shorthand (brief keys)
BIASES = ("Bullish", "Bearish", "Neutral")
STANCE_LABELS = ("hawkish", "dovish", "neutral")

# Shorthand → the exact asset names score_predictions.py keys on, so L3 can lift the
# brief into scored leans that the market-only arm is A/B'd against on the SAME assets.
ASSET_CANONICAL = {
    "10Y":  "10Y Treasury Yield",   # scored on the yield level (Bullish = yield up)
    "DXY":  "DXY",
    "gold": "Gold",
}

# Deterministic token cap (DESIGN §2). ~4 chars/token; keep total text well under
# the 600-token brief budget so N branches stay bounded at ≈ N × cap.
_MAX_WHAT_CHANGED = 400        # chars
_MAX_EXPECTATIONS = 400        # chars
_MAX_DRIVERS = 6
_MAX_DRIVER_CHARS = 160
_CHARS_PER_TOKEN = 4

SYNTH_SYSTEM = (
    "You are the monetary-policy analyst in a market-forecasting pipeline. You are "
    "given (a) structured EVIDENCE extracted from recent Federal Reserve "
    "communication and (b) a non-market CONSENSUS anchor: the economist survey "
    "(SPF) rate path, the FOMC dot-plot (SEP), and the gap between them. Fuse them "
    "into one bounded brief.\n\n"
    "Rules:\n"
    "- Use ONLY the evidence and consensus provided — no outside knowledge of what "
    "markets did afterward.\n"
    "- net_stance.label is hawkish / dovish / neutral; net_stance.score runs -1 "
    "(maximally dovish) to +1 (maximally hawkish).\n"
    "- expectations_gap: read the evidence AGAINST the consensus anchor — where is "
    "the Fed's communication tighter or looser than economists/the dots imply? A "
    "positive SPF-vs-SEP gap means economists sit above the Fed's dots.\n"
    "- asset_implications: a directional bias on each of 10Y, DXY, gold. SEMANTICS "
    "(follow exactly): 10Y is the TREASURY YIELD — hawkish ⇒ higher yield ⇒ "
    "Bullish. DXY — hawkish ⇒ stronger dollar ⇒ Bullish. gold — hawkish ⇒ higher "
    "real rates ⇒ Bearish. Reverse for dovish; Neutral when the signal is weak or "
    "mixed. confidence is 0..1.\n"
    "- drivers: the few pieces of evidence that most drove the call, each one short "
    "phrase.\n"
    "- Be concise; the brief is hard-capped. If evidence is thin, say so and lean "
    "Neutral with low confidence."
)


# ---------------------------------------------------------------------------
# LLM output schema (Pydantic → tool input_schema)
# ---------------------------------------------------------------------------

class AssetImplication(BaseModel):
    bias: str = Field(description="Directional bias: 'Bullish', 'Bearish', or 'Neutral'.")
    confidence: float = Field(description="Confidence in this bias, 0.0 to 1.0.")


class NetStance(BaseModel):
    label: str = Field(description="Net monetary stance: 'hawkish', 'dovish', or 'neutral'.")
    score: float = Field(description="Stance on a continuum, -1.0 (dovish) to +1.0 (hawkish).")


class BriefResult(BaseModel):
    net_stance: NetStance
    what_changed: str = Field(description="What shifted vs the prior stance/consensus, one or two sentences.")
    expectations_gap: str = Field(description="Our read vs the SPF/SEP consensus anchor, one or two sentences.")
    drivers: list[str] = Field(default_factory=list, description="Top evidence phrases that drove the call.")
    ten_year: AssetImplication = Field(description="Implication for 10Y Treasury YIELD (Bullish = yield up).")
    dxy: AssetImplication = Field(description="Implication for DXY (Bullish = stronger dollar).")
    gold: AssetImplication = Field(description="Implication for gold (Bearish = higher real rates).")
    brief_confidence: float = Field(description="Overall confidence in the brief, 0.0 to 1.0.")


# ---------------------------------------------------------------------------
# Final bounded record (DESIGN §2 L2 BranchBrief)
# ---------------------------------------------------------------------------

@dataclass
class BranchBrief:
    branch: str
    as_of: str                       # ISO date
    net_stance: dict                 # {"label", "score"}
    what_changed: str
    expectations_gap: str
    drivers: list[str]
    asset_implications: dict         # {"10Y": {"bias","confidence"}, "DXY": {...}, "gold": {...}}
    brief_confidence: float


# ---------------------------------------------------------------------------
# Pure: assemble the analyst input from L1 evidence + L0 consensus (no network)
# ---------------------------------------------------------------------------

def _evidence_row(e) -> dict:
    """Accept an Evidence dataclass or a plain dict; return the compact fields."""
    get = (lambda k: getattr(e, k)) if not isinstance(e, dict) else e.get
    return {
        "claim": get("claim"),
        "stance": get("stance"),
        "magnitude": get("magnitude"),
        "affected_assets": get("affected_assets") or [],
        "source_type": get("source_type"),
        "published": get("published"),
    }


def build_analyst_payload(evidence, consensus: Optional[dict]) -> str:
    """Compact JSON context block for the synthesis prompt.

    `evidence` is a list of L1 Evidence (dataclasses or dicts); `consensus` is the
    L0 anchor, e.g. {"spf": {...}, "sep": {"path_by_year","longer_run"}, "gap": {...}}
    (any subset; None → an explicit 'no consensus available' marker).
    """
    rows = [_evidence_row(e) for e in (evidence or [])]
    block = {
        "evidence": rows,
        "consensus": consensus if consensus else "none available",
    }
    return (
        "Fuse the following into the monetary brief.\n\n"
        "EVIDENCE + CONSENSUS (JSON):\n" + json.dumps(block, indent=2, default=str)
    )


# ---------------------------------------------------------------------------
# Pure: validate / normalise / cap the model's brief (no network)
# ---------------------------------------------------------------------------

def _clamp(x, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _norm_label(s: str) -> str:
    s = (s or "").strip().lower()
    return s if s in STANCE_LABELS else "neutral"


def _norm_bias(s: str) -> str:
    s = (s or "").strip().capitalize()
    return s if s in BIASES else "Neutral"


def _cap_text(s: str, limit: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _impl(ai: AssetImplication) -> dict:
    return {"bias": _norm_bias(ai.bias), "confidence": _clamp(ai.confidence, 0.0, 1.0)}


def enrich_brief(result: BriefResult, as_of: "date | str") -> BranchBrief:
    """Model brief → validated, capped `BranchBrief` (DESIGN §2 hard cap)."""
    aod = as_of.isoformat() if isinstance(as_of, date) else str(as_of)
    drivers = [_cap_text(d, _MAX_DRIVER_CHARS) for d in (result.drivers or []) if (d or "").strip()]
    return BranchBrief(
        branch=BRANCH,
        as_of=aod,
        net_stance={
            "label": _norm_label(result.net_stance.label),
            "score": round(_clamp(result.net_stance.score, -1.0, 1.0), 3),
        },
        what_changed=_cap_text(result.what_changed, _MAX_WHAT_CHANGED),
        expectations_gap=_cap_text(result.expectations_gap, _MAX_EXPECTATIONS),
        drivers=drivers[:_MAX_DRIVERS],
        asset_implications={
            "10Y":  _impl(result.ten_year),
            "DXY":  _impl(result.dxy),
            "gold": _impl(result.gold),
        },
        brief_confidence=round(_clamp(result.brief_confidence, 0.0, 1.0), 3),
    )


def brief_to_dict(brief: BranchBrief) -> dict:
    return asdict(brief)


def brief_token_estimate(brief: BranchBrief) -> int:
    """Rough token count of the brief's text payload (cap-budget check)."""
    text = " ".join([
        brief.what_changed, brief.expectations_gap, *brief.drivers,
        brief.net_stance["label"],
    ])
    return len(text) // _CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# IO shell — calls Claude (needs ANTHROPIC_API_KEY; user-run / CI)
# ---------------------------------------------------------------------------

def synthesize_brief(
    client, evidence, consensus: Optional[dict], as_of: "date | str",
    model: str = MODEL, max_tokens: int = 1024,
) -> Optional[BranchBrief]:
    """Synthesise the bounded `BranchBrief` from L1 evidence + L0 consensus.

    `client` is an `anthropic.Anthropic()` (injected so it's testable with a stub).
    Returns None if the model emits no tool call.
    """
    tools = [{
        "name": "submit_brief",
        "description": "Submit the bounded monetary branch brief.",
        "input_schema": BriefResult.model_json_schema(),
    }]
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYNTH_SYSTEM,
        tools=tools,
        tool_choice={"type": "tool", "name": "submit_brief"},
        messages=[{"role": "user", "content": build_analyst_payload(evidence, consensus)}],
    )
    block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"
         and getattr(b, "name", None) == "submit_brief"),
        None,
    )
    if block is None:
        return None
    result = BriefResult.model_validate(block.input)
    return enrich_brief(result, as_of)
