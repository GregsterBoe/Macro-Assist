#!/usr/bin/env python3
"""
model_compare.py — the same days through the main analysis call, on several
models, side by side.

The main model (MA-1 structured analysis + MA-2 review) is chosen by
`MACRO_PROFILE` / `MACRO_MODEL` (`pipeline_config.run_config`). Before switching
it, this replays saved days: for each of the last N
`results/llm_payload_preview/<date>.md` it takes the verbatim user message the
model received that day and sends it through `llm_analysis._analyze_structured`
and `_adversarial_review_structured` — the production functions, not a copy —
with today's structured system prompt, once per model.

Recorded per call: whether the answer validated on the first try, after the
retry, or not at all (production would then fall back to free text); tokens,
seconds, estimated cost. And three reading aids, computed by code, never a
verdict:

- **numbers not in the payload** — a number in the prose that no payload value
  rounds to. Derived figures (a spread, a change) land here too, so it is a
  list to read, not an error count; it is comparable across models because
  every model saw the same payload;
- **inputs named** — how many distinct inputs the prose names, with
  `citation_screen`'s alias map;
- **call language** — words the system prompt forbids since the cut (v1.6):
  "bullish", "bearish", "I expect X to rise", a likelihood. The Macro
  Dashboard table is exempt; its Bullish/Bearish cells are what the prompt asks
  for there.

Writes results/model_compare/<stamp>.{json,md}. Costs API money, so CI runs it
(`model_compare.yml`); `--dry-run` lists what would be sent, free.

    python .macro-assist/model_compare.py --dry-run
    python .macro-assist/model_compare.py --days 10 --models claude-opus-4-8,claude-sonnet-5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import audit_entry as ae
import citation_screen as cs
import llm_analysis as la
from pipeline_config import _render_prompt, run_config

REPO_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = Path("results") / "llm_payload_preview"
OUT_DIR = Path("results") / "model_compare"
SYSTEM_PROMPT = la.PROMPTS_DIR / "system_prompt_structured.md"

DEFAULT_MODELS = ("claude-opus-4-8", "claude-sonnet-5", "claude-sonnet-5-5")
DEFAULT_DAYS = 10
DEFAULT_MAX_USD = 5.0

_BANNER = "MAIN ANALYSIS PAYLOAD (verbatim — what the model receives)"
_RULE = "=" * 72

PROSE_FIELDS = ("executive_summary", "equities_note", "rates_note",
                "inflation_growth_note", "commodities_note")

# What the prompt forbids since v1.6 ("Do not write 'Bullish', 'Bearish', a
# probability, a percentage likelihood, or 'I expect X to rise/fall'").
_CALL_RE = re.compile(
    r"\b(bullish|bearish)\b"
    r"|\bI expect\b"
    r"|\bexpect(?:s|ed)?\b[^.]{0,60}\bto (?:rise|fall|rally|decline|climb|drop|gain|weaken|strengthen)\b"
    r"|\blikely to (?:rise|fall|rally|decline|climb|drop|gain|weaken|strengthen)\b"
    r"|\b\d{1,3}\s?% (?:chance|probability|likelihood)\b"
    r"|\b(?:probability|likelihood) of\b",
    re.I,
)
_NUM_RE = re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


# ---------------------------------------------------------------------------
# pure functions
# ---------------------------------------------------------------------------

def payload_message(preview: str) -> str:
    """The verbatim user message inside a payload preview — the inverse of
    `llm_analysis.build_payload_preview`."""
    head = f"{_BANNER}\n{_RULE}\n\n"
    i = preview.index(head) + len(head)
    end = preview.find(f"\n\n{_RULE}\n\n", i)
    return preview[i: end if end >= 0 else len(preview)]


def _numbers(text: str) -> list[tuple[str, float, int]]:
    out = []
    for m in _NUM_RE.finditer(text):
        tok = m.group(0)
        raw = tok.replace(",", "").replace("−", "-")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        out.append((tok, float(raw), decimals))
    return out


def ungrounded_numbers(prose: str, payload: str) -> list[str]:
    """Numbers in `prose` that no payload value rounds to, at the precision the
    prose wrote. Small integers and years are skipped (horizons, counts, dates);
    a payload value also counts as a percent (×100), in thousands and millions
    ("$977bn" for a TGA of 977,084 $M, "197k" claims), and with its sign
    dropped, because prose writes "fell 1.2%" for -0.012 or -1.2."""
    pay = {abs(v) for _, v, _ in _numbers(payload)}
    pay |= {v * s for v in pay for s in (100, 1e-3, 1e-6)}
    out = []
    for tok, v, d in _numbers(prose):
        if d == 0 and (abs(v) < 100 or 1990 <= abs(v) <= 2035):
            continue
        tol = 0.5 * 10 ** -d + 1e-9
        if not any(abs(p - abs(v)) <= tol for p in pay):
            out.append(tok)
    return out


def prose_of(output: dict) -> str:
    """Every free-prose field of an AnalysisOutput, without the Macro Dashboard
    table and without the target ranges (a forward band is not in the data)."""
    parts = [output.get(f) or "" for f in PROSE_FIELDS]
    parts += list(output.get("key_risks") or [])
    parts += [p.get("primary_driver", "") for p in output.get("predictions") or []]
    return "\n".join(parts)


def call_language(prose: str) -> list[str]:
    return [m.group(0) for m in _CALL_RE.finditer(prose)]


def reading_aids(output: dict, payload: str, patterns: dict) -> dict:
    prose = prose_of(output)
    dashboard = output.get("macro_dashboard_text") or ""
    return {
        "ungrounded": ungrounded_numbers(prose + "\n" + dashboard, payload),
        "inputs_named": sorted(cs.cited_inputs(prose, patterns)),
        "call_language": call_language(prose),
    }


# ---------------------------------------------------------------------------
# the replay
# ---------------------------------------------------------------------------

class Recorder:
    """Stands in for the Anthropic client: forwards every call, keeps its
    model, usage and duration. `_analyze_structured` only calls
    `client.messages.create`."""

    def __init__(self, client):
        self._client = client
        self.messages = self
        self.calls: list[dict] = []

    def create(self, **kw):
        t0 = time.monotonic()
        r = self._client.messages.create(**kw)
        u = r.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
        self.calls.append({"model": kw.get("model"), "max_tokens": kw.get("max_tokens"),
                           "stop_reason": getattr(r, "stop_reason", None),
                           "seconds": round(time.monotonic() - t0, 2), "usage": usage,
                           "est_usd": ae.estimate_usd(kw.get("model", ""), usage)})
        return r


@contextmanager
def main_model_as(model: str):
    """`pipeline_config.main_model()` reads MACRO_MODEL on every call."""
    old = os.environ.get("MACRO_MODEL")
    os.environ["MACRO_MODEL"] = model
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("MACRO_MODEL", None)
        else:
            os.environ["MACRO_MODEL"] = old


def recent_payloads(root: Path, days: int) -> list[tuple[str, str]]:
    """(date, user message) for the newest `days` previews, oldest first."""
    paths = sorted((root / PREVIEW_DIR).glob("*.md"))[-days:]
    return [(p.stem, payload_message(p.read_text(encoding="utf-8"))) for p in paths]


def system_prompt() -> str:
    return _render_prompt(SYSTEM_PROMPT.read_text(encoding="utf-8"), run_config())


def available(client, models: list[str]) -> tuple[list[str], dict[str, str]]:
    ok, skipped = [], {}
    for m in models:
        try:
            client.models.retrieve(m)
            ok.append(m)
        except Exception as e:                      # NotFoundError, or a key without access
            skipped[m] = f"{type(e).__name__}: {e}"
    return ok, skipped


def replay_one(client, model: str, system: str, payload: str, patterns: dict) -> dict:
    rec = Recorder(client)
    with main_model_as(model):
        t0 = time.monotonic()
        structured = la._analyze_structured(rec, system, payload)
        ma1_calls = len(rec.calls)
        reviewed = la._adversarial_review_structured(rec, structured) if structured else None
    out: dict = {"model": model, "calls": rec.calls,
                 "seconds": round(time.monotonic() - t0, 2),
                 "est_usd": round(sum(c["est_usd"] or 0 for c in rec.calls), 4)}
    if structured is None:
        out["structured"] = "failed"                # production falls back to free text
        return out
    out["structured"] = "first_try" if ma1_calls == 1 else "after_retry"
    final = reviewed or structured
    out["output"] = final.model_dump()
    out["review_changed_risks"] = list(final.key_risks) != list(structured.key_risks)
    out["aids"] = reading_aids(out["output"], payload, patterns)
    return out


def run(root: Path, *, client, models: list[str], days: int,
        max_usd: float = DEFAULT_MAX_USD) -> dict:
    system = system_prompt()
    payloads = recent_payloads(root, days)
    if not payloads:
        raise SystemExit(f"no payload previews under {root / PREVIEW_DIR}")
    models, skipped = available(client, models)
    patterns = cs.compile_patterns(cs.INPUT_ALIASES)
    results: list[dict] = []
    spent = 0.0
    for day, payload in payloads:
        for m in models:
            if spent >= max_usd:
                results.append({"day": day, "model": m, "structured": "not_run",
                                "why": f"spend guard: ${spent:.2f} of ${max_usd:.2f}"})
                continue
            try:
                r = replay_one(client, m, system, payload, patterns)
            except Exception as e:                  # an API error is a result, not a crash
                r = {"model": m, "structured": "error", "why": f"{type(e).__name__}: {e}",
                     "est_usd": 0.0}
            spent += r.get("est_usd") or 0.0
            results.append({"day": day, **r})
    return {
        "schema": 1,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": ae._tier(), "run": ae._run_url(),
        "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
        "days": [d for d, _ in payloads], "models": models, "skipped_models": skipped,
        "est_cost_usd": round(spent, 4), "results": results,
    }


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------

def summarize(report: dict) -> list[dict]:
    rows = []
    for m in report["models"]:
        rs = [r for r in report["results"] if r["model"] == m]
        done = [r for r in rs if "output" in r]
        ma1 = [c for r in rs for c in r.get("calls", [])[:1]]
        n = len(done) or 1
        rows.append({
            "model": m, "days": len(rs),
            "first_try": sum(r["structured"] == "first_try" for r in rs),
            "after_retry": sum(r["structured"] == "after_retry" for r in rs),
            "failed": sum(r["structured"] in ("failed", "error") for r in rs),
            "output_tokens": round(sum(c["usage"]["output_tokens"] for c in ma1) / (len(ma1) or 1)),
            "seconds": round(sum(r.get("seconds", 0) for r in done) / n, 1),
            "usd_per_day": round(sum(r.get("est_usd") or 0 for r in rs) / (len(rs) or 1), 3),
            "ungrounded": round(sum(len(r["aids"]["ungrounded"]) for r in done) / n, 1),
            "inputs_named": round(sum(len(r["aids"]["inputs_named"]) for r in done) / n, 1),
            "call_language": sum(len(r["aids"]["call_language"]) for r in done),
        })
    return rows


def _clip(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def render(report: dict) -> str:
    out = [
        "# Model comparison — the main analysis call",
        "",
        f"{report['ran_at']} · tier `{report['tier']}`"
        + (f" · [run]({report['run']})" if report.get("run") else "")
        + f" · {len(report['days'])} days ({report['days'][0]} → {report['days'][-1]})"
        + f" · estimated cost ${report['est_cost_usd']:.2f}",
        "",
        f"Every model got the same saved payload for each day and today's structured system "
        f"prompt (`sha256:{report['system_prompt_sha256'][:16]}…`), through the production "
        "functions. Nothing here is a verdict; the columns are for reading.",
        "",
    ]
    if report["skipped_models"]:
        out += [f"- **Skipped** `{m}`: {why}" for m, why in report["skipped_models"].items()] + [""]
    out += [
        "| model | valid first try | after retry | failed | output tokens | seconds | $ / day "
        "| numbers not in payload | inputs named | call language |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summarize(report):
        out.append(f"| `{s['model']}` | {s['first_try']}/{s['days']} | {s['after_retry']} | "
                   f"{s['failed']} | {s['output_tokens']:,} | {s['seconds']} | "
                   f"${s['usd_per_day']:.3f} | {s['ungrounded']} | {s['inputs_named']} | "
                   f"{s['call_language']} |")
    out += [
        "",
        "- **failed** — the answer did not validate after the retry; production would have "
        "fallen back to the free-text path that day.",
        "- **numbers not in payload** — per note, a number in the prose that no input value "
        "rounds to. Changes and spreads the model computed land here too; read the lists below.",
        "- **inputs named** — per note, distinct inputs the prose mentions (`citation_screen`).",
        "- **call language** — total uses of wording the prompt forbids since v1.6 (bullish, "
        "bearish, \"I expect X to rise\", a likelihood), outside the Macro Dashboard table. "
        "Should be 0.",
        "",
    ]
    for day in report["days"]:
        out += [f"## {day}", ""]
        for r in (r for r in report["results"] if r["day"] == day):
            out += [f"### `{r['model']}`", ""]
            if "output" not in r:
                out += [f"**{r['structured']}** — {r.get('why', 'no valid answer after the retry')}", ""]
                continue
            o, a = r["output"], r["aids"]
            out += [_clip(o["executive_summary"], 1000), "", "**Key risks**", ""]
            out += [f"- {_clip(k, 400)}" for k in o["key_risks"]]
            out += ["", "| asset | range | driver |", "|---|---|---|"]
            out += [f"| {p['asset']} | {p['target_range']} | {_clip(p['primary_driver'], 280)} |"
                    for p in o["predictions"]]
            out += ["", f"*Numbers not in payload:* {', '.join(a['ungrounded']) or 'none'} · "
                    f"*call language:* {', '.join(repr(x) for x in a['call_language']) or 'none'} · "
                    f"{r['structured'].replace('_', ' ')} · {r['seconds']}s · ${r['est_usd']:.3f}", ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS),
                    help="comma-separated; the first is the one in production today")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    ap.add_argument("--dry-run", action="store_true", help="list what would be sent; no call")
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    args = ap.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    if args.dry_run:
        payloads = recent_payloads(args.root, args.days)
        print(f"system prompt: {len(system_prompt()):,} chars · models: {', '.join(models)}")
        for day, p in payloads:
            print(f"  {day}  {len(p):>6,} chars")
        print(f"{len(payloads)} days × {len(models)} models; no API call made.")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. The comparison runs in CI: model_compare.yml.",
              file=sys.stderr)
        return 2
    import anthropic
    report = run(args.root, client=anthropic.Anthropic(), models=models, days=args.days,
                 max_usd=args.max_usd)
    out = args.root / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    (out / f"{stamp}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    md = render(report)
    (out / f"{stamp}.md").write_text(md, encoding="utf-8")
    (out / "latest.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
