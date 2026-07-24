"""
extract.py — WP-19.B L1: FOMC-text → structured monetary `Evidence` (the first LLM stage).

Turns a Fed document (statement first; minutes/speeches later) into a list of
structured `Evidence` items per DESIGN §2. Uses the **cheap** model (Haiku) via
the codebase's established forced-tool-use structured-output pattern (matches
`_run_risk_agent` etc.) — not `messages.parse`, which isn't guaranteed on the
pinned SDK.

Split like the rest of the package: the **schema + prompt + enrichment are pure**
(unit-tested with synthetic model output, no network); `extract_evidence` is the
thin shell that calls Claude. Point-in-time is the caller's responsibility — pass
the document's real `published` date; the model only sees the document text.

CONFIRM-ON-FIRST-RUN: the extraction quality (what counts as a salient claim,
stance calibration) needs an eyeball on the first real FOMC statement — run
`extract_evidence` on one and check the Evidence list before trusting it.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

# Cheap extractor model — matches the Haiku sub-agents already in the pipeline.
MODEL = "claude-haiku-4-5-20251001"

# The monetary slice's scored assets (DESIGN §1). Claims may bear on any subset.
ALLOWED_ASSETS = ("10Y", "DXY", "gold")
STANCES = ("hawkish", "dovish", "neutral")

EXTRACTION_SYSTEM = (
    "You extract monetary-policy signal from a Federal Reserve document (FOMC "
    "statement, minutes, or a Fed official's speech). Read ONLY the text provided "
    "— do not use outside knowledge of what happened afterward.\n\n"
    "For each genuinely policy-relevant statement, emit one claim with:\n"
    "- claim: the point, paraphrased in one concise sentence.\n"
    "- stance: its monetary-policy lean — 'hawkish' (tighter/higher-for-longer), "
    "'dovish' (easier/cuts), or 'neutral'.\n"
    "- magnitude: how strong/market-moving the signal is, 0.0 (boilerplate) to "
    "1.0 (a clear policy shift).\n"
    "- affected_assets: which of {10Y, DXY, gold} the claim most bears on "
    "(rates→10Y, dollar→DXY, real-rates/inflation→gold); empty if none.\n"
    "- confidence: your confidence in this reading, 0.0 to 1.0.\n\n"
    "Be selective: extract only claims that carry policy information. Skip "
    "procedural boilerplate. If the document says nothing policy-relevant, return "
    "an empty list."
)


# ---------------------------------------------------------------------------
# LLM output schema (Pydantic → tool input_schema) — the model fills this in
# ---------------------------------------------------------------------------

class ExtractedClaim(BaseModel):
    claim: str = Field(description="One salient, policy-relevant statement, paraphrased concisely.")
    stance: str = Field(description="Monetary-policy stance: 'hawkish', 'dovish', or 'neutral'.")
    magnitude: float = Field(description="Signal strength, 0.0 (boilerplate) to 1.0 (clear policy shift).")
    affected_assets: list[str] = Field(
        default_factory=list,
        description="Subset of ['10Y','DXY','gold'] the claim bears on; empty if none.",
    )
    confidence: float = Field(description="Confidence in this reading, 0.0 to 1.0.")


class ExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = Field(
        default_factory=list,
        description="All salient policy-relevant claims; empty list if none.",
    )


# ---------------------------------------------------------------------------
# Final enriched record (DESIGN §2 L1 Evidence)
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    claim: str
    source_type: str          # fomc_statement | fomc_minutes | speech
    source_id: str            # url / doc id (provenance)
    published: str            # ISO date — point-in-time key
    stance: str               # hawkish | dovish | neutral
    magnitude: float          # 0..1
    affected_assets: list[str]
    extractor_conf: float     # 0..1


# ---------------------------------------------------------------------------
# Pure: prompt + enrichment/validation (no network)
# ---------------------------------------------------------------------------

def build_user_message(doc_text: str) -> str:
    return f"Extract the monetary-policy evidence from this document:\n\n{doc_text.strip()}"


def _clamp01(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _norm_stance(s: str) -> str:
    s = (s or "").strip().lower()
    return s if s in STANCES else "neutral"


def enrich_evidence(
    result: ExtractionResult, source_type: str, source_id: str, published: "date | str"
) -> list[Evidence]:
    """Model output → validated `Evidence`: clamp scores, filter assets, attach
    the trusted metadata (source/date) the model never sees. Drops empty claims.
    """
    pub = published.isoformat() if isinstance(published, date) else str(published)
    out: list[Evidence] = []
    for c in result.claims:
        claim = (c.claim or "").strip()
        if not claim:
            continue
        assets = [a for a in (c.affected_assets or []) if a in ALLOWED_ASSETS]
        out.append(Evidence(
            claim=claim,
            source_type=source_type,
            source_id=source_id,
            published=pub,
            stance=_norm_stance(c.stance),
            magnitude=_clamp01(c.magnitude),
            affected_assets=assets,
            extractor_conf=_clamp01(c.confidence),
        ))
    return out


def evidence_to_dicts(evidence: list[Evidence]) -> list[dict]:
    return [asdict(e) for e in evidence]


# ---------------------------------------------------------------------------
# IO shell — calls Claude (needs ANTHROPIC_API_KEY; user-run)
# ---------------------------------------------------------------------------

def extract_evidence(
    client, doc_text: str, source_type: str, source_id: str,
    published: "date | str", model: str = MODEL, max_tokens: int = 2048,
) -> list[Evidence]:
    """Extract `Evidence` from one document via forced-tool-use structured output.

    `client` is an `anthropic.Anthropic()` (injected so it's testable with a
    stub). Returns [] if the model emits no tool call.
    """
    tools = [{
        "name": "submit_evidence",
        "description": "Submit the extracted monetary-policy evidence.",
        "input_schema": ExtractionResult.model_json_schema(),
    }]
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=EXTRACTION_SYSTEM,
        tools=tools,
        tool_choice={"type": "tool", "name": "submit_evidence"},
        messages=[{"role": "user", "content": build_user_message(doc_text)}],
    )
    block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"
         and getattr(b, "name", None) == "submit_evidence"),
        None,
    )
    if block is None:
        return []
    result = ExtractionResult.model_validate(block.input)
    return enrich_evidence(result, source_type, source_id, published)


def extract_from_file(
    client, path: str, source_type: str = "fomc_statement",
    published: "Optional[date]" = None, model: str = MODEL,
) -> list[Evidence]:
    """Convenience: read a saved document (plain text) and extract from it.

    `source_id` defaults to the file path; pass the true `published` date for
    point-in-time correctness (defaults to today with a warning-worthy caveat).
    """
    from pathlib import Path
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    pub = published or date.today()
    return extract_evidence(client, text, source_type, str(p), pub, model=model)
