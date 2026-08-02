"""
kimi_arm.py — experimental model arm: Kimi K2.5 with ENSEMBLE-derived confidence.

Two ideas, one module:
1. **Model A/B** — run the *same daily payload* the market pipeline feeds its model
   (read verbatim from `results/llm_payload_preview/<date>.md`) through **Kimi K2.5**
   via Moonshot's Anthropic-compatible endpoint, and emit an `arm: kimi` note. It
   rides the existing arm machinery (`score_predictions` arm-keying +
   `summarize_accuracy.calibration_by_arm`) — market vs kimi, same assets, same window.
2. **Better confidence (the point)** — the market arm's `confidence_pct` is a
   self-reported number CLAMPED to 50–80 that the track record shows is ~non-
   discriminative (KB-007). Instead, K2.5 is cheap enough to **sample the call N
   times** and derive confidence from **agreement across samples** (self-consistency):
   unanimous → high confidence; split → low confidence → **Neutral** (honest
   abstention). Agreement is discriminative by construction and un-clamped (33–100%),
   so a later recalibration layer can map it to a real hit-rate.

MODULAR / removable (like the exogenous engine): own file + own workflow; the shared
hooks it uses are inert without `arm:kimi` data. Kill = delete this file + its
workflow + `results/**/*-kimi-macro.md` + `results/scores/*__kimi.json`. Grep
`KIMI-ARM`.

Auth: set MOONSHOT_API_KEY (or KIMI_API_KEY). CONFIRM-ON-FIRST-RUN: verify the
Moonshot Anthropic endpoint honours forced `tool_choice` (we fall back to JSON if
not), the exact model id (`kimi-k2.5`), and that temperature actually yields sample
variation (else confidence collapses to 100 — bump --temperature).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent

# kimi-k2.5 was retired; kimi-k2.6 (Apr 2026) is its cheap general-tier successor.
# Confirmed available on the account 2026-08 (ids use a dot: kimi-k2.6, not -k2-6).
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.6")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/anthropic")
SYSTEM_PROMPT_FILE = HERE / "prompts" / "system_prompt_structured.md"
PREVIEW_DIR = HERE.parent / "results" / "llm_payload_preview"
RESULTS_DIR = HERE.parent / "results"

# The six forecast assets, canonical names (must match score_predictions.ASSET_TICKERS).
ASSETS = ("S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin")
BIASES = ("Bullish", "Bearish", "Neutral")

DEFAULT_N = 10
DEFAULT_TEMPERATURE = 0.9
# A directional call needs at least this share of the N samples, else → Neutral.
ABSTAIN_THRESHOLD = 0.55

ENSEMBLE_SYSTEM = (
    "You are a macro-markets analyst. From ONLY the data provided, give a 5-trading-day "
    "directional call — Bullish, Bearish, or Neutral — for each of these six assets: "
    "S&P 500, Gold, WTI Oil, 10Y Treasury Yield, DXY, Bitcoin. For 10Y Treasury Yield the "
    "call is on the YIELD (Bullish = yield rises). Be willing to answer Neutral when the "
    "data is genuinely mixed — do NOT force a directional call."
)
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object mapping each asset to its call, exactly like:\n"
    '{"S&P 500":"Bullish","Gold":"Neutral","WTI Oil":"Bearish",'
    '"10Y Treasury Yield":"Bullish","DXY":"Neutral","Bitcoin":"Bearish"}'
)


# ---------------------------------------------------------------------------
# LLM sample schema
# ---------------------------------------------------------------------------

class AssetCall(BaseModel):
    asset: str
    bias: str = Field(description="Bullish, Bearish, or Neutral")


class SampleOutput(BaseModel):
    calls: list[AssetCall] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure: parse payload, canonicalise, aggregate ensemble → confidence
# ---------------------------------------------------------------------------

_SEP = re.compile(r"^={20,}[ \t]*$", re.M)   # a separator LINE (not \s — must not eat newlines)


def extract_user_message(preview_text: str) -> str:
    """Pull the verbatim user message from a payload-preview file.

    The preview wraps it between `====` separators (header … ==== title ==== BODY
    ==== withheld). The body is the block between the 2nd and 3rd separators.
    """
    parts = _SEP.split(preview_text)
    # parts: [header, " MAIN ANALYSIS PAYLOAD… ", BODY, withheld, …]
    if len(parts) >= 3:
        return parts[2].strip()
    return preview_text.strip()


def _canon_asset(raw: str) -> Optional[str]:
    s = (raw or "").strip().lower()
    if "bitcoin" in s or "btc" in s: return "Bitcoin"
    if "gold" in s or "xau" in s: return "Gold"
    if "oil" in s or "wti" in s or "crude" in s: return "WTI Oil"
    if "10y" in s or "treasury" in s or "yield" in s or "tnx" in s: return "10Y Treasury Yield"
    if "dxy" in s or "dollar" in s: return "DXY"
    if "s&p" in s or "sp500" in s or "s and p" in s or "500" in s: return "S&P 500"
    return None


def _canon_bias(raw: str) -> Optional[str]:
    s = (raw or "").strip().capitalize()
    return s if s in BIASES else None


def parse_sample(obj) -> dict:
    """A tool-input dict / SampleOutput / plain {asset:bias} dict → {canon_asset: canon_bias}."""
    out: dict = {}
    pairs: list[tuple] = []
    if isinstance(obj, dict) and "calls" in obj:
        pairs = [(c.get("asset"), c.get("bias")) for c in obj.get("calls", []) if isinstance(c, dict)]
    elif isinstance(obj, dict):
        pairs = list(obj.items())
    elif isinstance(obj, SampleOutput):
        pairs = [(c.asset, c.bias) for c in obj.calls]
    for a, b in pairs:
        ca, cb = _canon_asset(str(a)), _canon_bias(str(b))
        if ca and cb and ca not in out:
            out[ca] = cb
    return out


def parse_sample_from_text(text: str) -> dict:
    """Best-effort: extract the first JSON object from free text and parse it."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return parse_sample(json.loads(m.group(0)))
    except (ValueError, TypeError):
        return {}


def aggregate(samples: list[dict], abstain_threshold: float = ABSTAIN_THRESHOLD) -> dict:
    """Ensemble → per-asset {bias, confidence, agreement, n, votes} — the confidence core.

    For each asset: tally votes across samples. If Neutral is the plurality, or the
    leading DIRECTION's share of all votes is below `abstain_threshold`, emit Neutral
    (honest abstention). Otherwise emit that direction with confidence = round(share*100)
    — un-clamped, so strong agreement can read 90–100 (unlike the market arm's 50–80).
    """
    out: dict = {}
    for asset in ASSETS:
        votes = Counter(s[asset] for s in samples if asset in s and s.get(asset) in BIASES)
        n = sum(votes.values())
        if n == 0:
            out[asset] = {"bias": "Neutral", "confidence": 50, "agreement": 0.0, "n": 0, "votes": {}}
            continue
        bull, bear, neu = votes["Bullish"], votes["Bearish"], votes["Neutral"]
        top_dir, top_ct = ("Bullish", bull) if bull >= bear else ("Bearish", bear)
        dir_share = top_ct / n
        if neu >= top_ct or dir_share < abstain_threshold:
            bias, conf, agreement = "Neutral", 50, round(max(neu, top_ct) / n, 3)
        else:
            bias, conf, agreement = top_dir, int(round(dir_share * 100)), round(dir_share, 3)
        out[asset] = {"bias": bias, "confidence": conf, "agreement": agreement,
                      "n": n, "votes": dict(votes)}
    return out


def render_kimi_note(preds: dict, asof: "date | str", n: int, model: str = KIMI_MODEL,
                     review_days: int = 5) -> str:
    """Arm-tagged note whose frontmatter + `### 5-Day Predictions` table the existing
    `score_predictions.py` parses (arm: kimi → scored as its own arm)."""
    aod = date.fromisoformat(asof) if not isinstance(asof, date) else asof
    review = (aod + timedelta(days=review_days)).isoformat()
    rows = ["| Asset | Bias | Driver | Confidence | Target |", "| --- | --- | --- | --- | --- |"]
    for asset in ASSETS:
        p = preds.get(asset, {"bias": "Neutral", "confidence": 50, "votes": {}, "agreement": 0.0})
        votes = "/".join(f"{k[0]}{v}" for k, v in p.get("votes", {}).items()) or "—"
        driver = f"ensemble n={p.get('n', 0)} votes {votes} (agreement {p.get('agreement', 0):.0%})"
        rows.append(f"| {asset} | {p['bias']} | {driver} | {p['confidence']}% | directional |")
    return (
        "---\n"
        "arm: kimi\n"
        f"model: {model}\n"
        f"ensemble_n: {n}\n"
        f"as_of: {aod.isoformat()}\n"
        "---\n\n"
        f"# Kimi Ensemble Arm — {aod.isoformat()}\n\n"
        f"Confidence = agreement across {n} samples (not self-reported). "
        "Split samples → Neutral.\n\n"
        "### 5-Day Predictions\n\n"
        + "\n".join(rows) + "\n\n"
        f"Review date: {review}\n"
    )


# ---------------------------------------------------------------------------
# IO shell — Kimi via Moonshot Anthropic-compatible endpoint (needs key)
# ---------------------------------------------------------------------------

def build_client():
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not key:
        raise SystemExit("Set MOONSHOT_API_KEY (or KIMI_API_KEY) for the Kimi arm.")
    import anthropic
    # Send both auth styles so either endpoint expectation is satisfied.
    return anthropic.Anthropic(base_url=KIMI_BASE_URL, api_key=key,
                               default_headers={"Authorization": f"Bearer {key}"})


def one_sample(client, system: str, user_message: str, model: str = KIMI_MODEL,
               temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = 1024) -> dict:
    """One directional-call sample → {canon_asset: bias}. Forced tool-use, with a
    plain-JSON fallback for endpoint compatibility. Returns {} on failure (skipped)."""
    tools = [{"name": "submit_calls", "description": "Submit the six directional calls.",
              "input_schema": SampleOutput.model_json_schema()}]
    msg = [{"role": "user", "content": user_message + _JSON_INSTRUCTION}]
    try:
        resp = client.messages.create(model=model, max_tokens=max_tokens, temperature=temperature,
                                      system=system, tools=tools,
                                      tool_choice={"type": "tool", "name": "submit_calls"}, messages=msg)
        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if block is not None:
            return parse_sample(block.input)
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return parse_sample_from_text(text)
    except Exception:
        # Fallback: no tools, ask for JSON directly (max endpoint compatibility).
        resp = client.messages.create(model=model, max_tokens=max_tokens, temperature=temperature,
                                      system=system, messages=msg)
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return parse_sample_from_text(text)


def ensemble(client, user_message: str, n: int = DEFAULT_N,
             temperature: float = DEFAULT_TEMPERATURE, model: str = KIMI_MODEL,
             system: str = ENSEMBLE_SYSTEM) -> list[dict]:
    samples = []
    for i in range(n):
        s = one_sample(client, system, user_message, model=model, temperature=temperature)
        if s:
            samples.append(s)
        print(f"  sample {i+1}/{n}: {s or 'EMPTY'}", file=sys.stderr)
    return samples


def note_path(asof: date, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / asof.strftime("%m-%B") / f"{asof.isoformat()}-kimi-macro.md"


def run_kimi_arm(asof: Optional[date] = None, n: int = DEFAULT_N,
                 temperature: float = DEFAULT_TEMPERATURE, results_dir: Path = RESULTS_DIR,
                 force: bool = False, model: str = KIMI_MODEL) -> Optional[Path]:
    asof = asof or date.today()
    out = note_path(asof, results_dir)
    if out.exists() and not force:
        print(f"Note exists (use force): {out}", file=sys.stderr)
        return out

    preview = PREVIEW_DIR / f"{asof.isoformat()}.md"
    if not preview.exists():
        print(f"No payload preview for {asof} at {preview} — run the market pipeline first "
              "(MACRO_PREVIEW=1).", file=sys.stderr)
        return None
    user_message = extract_user_message(preview.read_text(encoding="utf-8"))
    system = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8") if SYSTEM_PROMPT_FILE.exists() else ENSEMBLE_SYSTEM
    # Use the focused ensemble system prompt (asks for the 6 calls); the market system
    # prompt is huge and note-shaped. Same DATA (user_message) either way.
    system = ENSEMBLE_SYSTEM

    client = build_client()
    try:
        samples = ensemble(client, user_message, n=n, temperature=temperature, model=model)
    except Exception as exc:
        api_root = KIMI_BASE_URL.rsplit("/anthropic", 1)[0]
        print(
            f"\nKimi call failed with model '{model}': {exc}\n\n"
            f"List the exact model ids on your account:\n"
            f"  curl {api_root}/v1/models -H \"Authorization: Bearer $MOONSHOT_API_KEY\"\n"
            f"then re-run with  --model <id>  (or set KIMI_MODEL).", file=sys.stderr)
        return None
    if not samples:
        print("No usable samples — nothing emitted.", file=sys.stderr)
        return None
    preds = aggregate(samples)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_kimi_note(preds, asof, len(samples)), encoding="utf-8")
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Kimi K2.5 ensemble model arm")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD (default today)")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--model", default=os.getenv("KIMI_MODEL", KIMI_MODEL),
                    help="Moonshot model id (list via /v1/models); default %(default)s")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list-models", action="store_true",
                    help="list model ids via the working Anthropic-endpoint auth, then exit")
    args = ap.parse_args()

    if args.list_models:
        client = build_client()
        try:
            ids = [m.id for m in client.models.list()]
            print("Available model ids:")
            for i in ids:
                print(f"  {i}")
        except Exception as exc:
            print(f"models.list via /anthropic failed ({exc}).\n"
                  "Try these candidate ids directly with --model:\n"
                  "  kimi-k2-5-preview  kimi-k2-5  kimi-k2.5-preview  kimi-latest  "
                  "moonshot-v1-128k", file=sys.stderr)
            return 2
        return 0

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    path = run_kimi_arm(asof=asof, n=args.n, temperature=args.temperature,
                        force=args.force, model=args.model)
    if path is None:
        return 1
    print(f"\nEmitted Kimi arm note: {path}\n")
    print(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
