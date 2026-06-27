#!/usr/bin/env python3
"""
citation_screen.py — WP-18.3: model-attention / citation screen (low-cost).

Phase-18 step 2. WP-18.2 (`input_ledger.py`, KB-009) screened inputs by their own
statistics (staleness / entropy / redundancy). This one asks a complementary
question of the *model*: in its free-prose rationale, how often does it actually
**reference** each input? An input the model never names across dozens of notes is
a prune candidate; a redundant input it leans on heavily is not (yet).

It scans only the **free-prose** rationale — Executive Summary, the asset/theme
sections, Key Risks, and the per-asset Primary Driver cells — and deliberately
**excludes** the templated `### Macro Dashboard` table (lists the same 9
indicators every day → fake attention) and the raw `## Data Snapshot` (the inputs
themselves). Per input it reports the fraction of notes that cite it, then joins
the latest input-ledger so REDUNDANT (KB-009) + rarely-cited inputs surface as the
strongest WP-18.4 ablation candidates.

**Screening proxy, never a verdict (KB-discipline).** The model can *use* an input
without naming it (it's in the payload regardless) or *name* one that didn't move
the call. Citation flags candidates for the outcome-grounded ablation (18.4); it
does not decide. The alias map below is the tunable, fallible heart of the screen.

Pure text functions (top) are unit-tested; the IO shell (bottom) reads the scored
notes and writes results/citation_screen/<date>.{md,json}. No network, no LLM:

    python .macro-assist/citation_screen.py
    python .macro-assist/citation_screen.py --min-version v0.3 --ledger results/input_ledger/2026-06-27.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Input alias map — keyed by the SAME names as input_ledger / the FRED+ticker
# universe, so the two screens join cleanly. Each list is the set of surface
# forms the model uses in prose. This is a deliberate, fallible heuristic.
# ---------------------------------------------------------------------------
INPUT_ALIASES: "OrderedDict[str, list[str]]" = OrderedDict([
    # --- market ---
    ("sp500",          ["S&P 500", "S&P500", "SPX", "S&P"]),
    ("nasdaq",         ["Nasdaq", "NDX"]),
    ("gold",           ["gold"]),
    ("wti_oil",        ["WTI", "crude", "oil"]),
    ("vix",            ["VIX"]),                       # \bVIX\b won't match inside VIX3M
    ("vix3m",          ["VIX3M", "3-month VIX", "term ratio", "term structure",
                        "backwardation", "contango"]),
    ("dxy",            ["DXY", "dollar", "greenback"]),
    ("bitcoin",        ["Bitcoin", "BTC"]),
    # --- sector ETFs (ticker + sector word) ---
    ("xle",            ["XLE", "Energy"]),
    ("xlk",            ["XLK", "Technology"]),
    ("xlf",            ["XLF", "Financials"]),
    ("xli",            ["XLI", "Industrials"]),
    ("xly",            ["XLY", "Consumer Discretionary"]),
    ("xlv",            ["XLV", "Health Care", "Healthcare"]),
    ("xlu",            ["XLU", "Utilities"]),
    ("xlp",            ["XLP", "Consumer Staples"]),
    ("xlb",            ["XLB", "Materials"]),
    ("xlre",           ["XLRE", "Real Estate"]),
    ("xlc",            ["XLC", "Communication Services", "Communications"]),
    # --- FRED ---
    ("fed_funds_rate", ["fed funds", "FFR", "policy rate"]),
    ("cpi",            ["CPI", "inflation"]),
    ("gdp",            ["GDP"]),
    ("unemployment",   ["unemployment", "labor market", "labour market"]),
    ("m2",             ["M2", "money supply"]),
    ("treasury_10y",   ["10Y", "10-year", "10-yr", "ten-year"]),
    ("treasury_2y",    ["2Y", "2-year", "2-yr", "two-year"]),
    ("hy_spread",      ["HY", "high yield", "high-yield", "credit spread"]),
    ("baa_spread",     ["Baa", "BAA"]),
    ("philly_fed_mfg", ["Philly Fed", "Philadelphia Fed"]),
    ("real_yield_10y", ["real yield", "real yields", "TIPS"]),
    ("breakeven_10y",  ["breakeven", "inflation expectations", "inflation breakeven"]),
    ("fed_total_assets", ["balance sheet", "Fed assets", "total assets", "WALCL"]),
    ("treasury_gen_acct", ["TGA", "Treasury General Account", "treasury cash"]),
    ("reverse_repo",   ["reverse repo", "RRP"]),
    ("jobless_claims", ["jobless claims", "initial claims", "claims"]),
    ("nfci",           ["NFCI", "financial conditions"]),
])

# Derived inputs the model sees but the ledger panel doesn't carry as rows —
# tracked separately so we don't lose visible attention to them.
DERIVED_ALIASES: "OrderedDict[str, list[str]]" = OrderedDict([
    ("net_liquidity",  ["net liquidity", "net fed liquidity"]),
    ("yield_curve",    ["yield curve", "curve at", "curve "]),
])


# ---------------------------------------------------------------------------
# Pure text functions
# ---------------------------------------------------------------------------

def compile_patterns(aliases: "dict[str, list[str]]") -> "dict[str, re.Pattern]":
    """One case-insensitive, word-bounded regex per input.

    Uses non-word lookarounds rather than \\b so multi-word / symbol aliases
    ("S&P 500", "10-year") bound correctly on their alphanumeric ends.
    """
    out: dict[str, re.Pattern] = {}
    for name, forms in aliases.items():
        alt = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
        out[name] = re.compile(rf"(?<!\w)(?:{alt})(?!\w)", re.IGNORECASE)
    return out


def extract_rationale(md_text: str) -> str:
    """Return the free-prose rationale only.

    Keeps everything from the first `### ` section up to `## Data Snapshot`
    (exclusive), then drops the templated `### Macro Dashboard` block — both
    would otherwise inflate citation with template/raw text rather than the
    model's chosen wording.
    """
    # Cut the raw data dump.
    snap = re.search(r"^##\s+Data Snapshot", md_text, flags=re.MULTILINE)
    body = md_text[: snap.start()] if snap else md_text

    # Start at the first H3 (skip YAML frontmatter + H1 title).
    first_h3 = re.search(r"^###\s+", body, flags=re.MULTILINE)
    if first_h3:
        body = body[first_h3.start():]

    # Remove the Macro Dashboard section (### Macro Dashboard … next ###/##).
    body = re.sub(
        r"^###\s+Macro Dashboard\b.*?(?=^#{2,3}\s+)",
        "",
        body,
        flags=re.DOTALL | re.MULTILINE,
    )
    return body


def cited_inputs(text: str, patterns: "dict[str, re.Pattern]") -> "set[str]":
    """Set of input names mentioned at least once in `text` (presence, not count)."""
    return {name for name, pat in patterns.items() if pat.search(text)}


def aggregate_citations(
    rationales: "list[str]", patterns: "dict[str, re.Pattern]"
) -> "dict[str, dict]":
    """Per input: cited_in (note count), total notes, rate (fraction)."""
    total = len(rationales)
    counts = {name: 0 for name in patterns}
    for text in rationales:
        for name in cited_inputs(text, patterns):
            counts[name] += 1
    return {
        name: {"cited_in": c, "total": total,
               "rate": round(c / total, 4) if total else 0.0}
        for name, c in counts.items()
    }


def merge_with_ledger(
    agg: "dict[str, dict]", ledger: "Optional[dict]", rare_rate: float = 0.10
) -> "dict[str, dict]":
    """Join citation rates with the latest input-ledger entries.

    Adds redundancy / info_score / flags from the ledger (when the input exists
    there) and a `prune_priority`:
      - "high"   redundant (or dead) AND rarely cited (≤ rare_rate)
      - "watch"  one of the two
      - "keep"   neither
    Derived inputs absent from the ledger get ledger fields = None.
    """
    led_by_name: dict[str, dict] = {}
    if ledger:
        led_by_name = {e["name"]: e for e in ledger.get("entries", [])}

    merged: dict[str, dict] = {}
    for name, cit in agg.items():
        le = led_by_name.get(name)
        redundant = bool(le and le.get("redundant"))
        dead = bool(le and "DEAD" in (le.get("flags") or ""))
        rare = cit["rate"] <= rare_rate
        weak_input = redundant or dead
        priority = "high" if (weak_input and rare) else ("watch" if (weak_input or rare) else "keep")
        merged[name] = {
            **cit,
            "redundant": redundant if le else None,
            "info_score": (le.get("info_score") if le else None),
            "ledger_flags": (le.get("flags") if le else None),
            "prune_priority": priority,
        }
    return merged


def render_screen_md(
    merged: "dict[str, dict]", total_notes: int, rare_rate: float, has_ledger: bool
) -> "list[str]":
    """Render the citation screen as scannable markdown."""
    rows = sorted(merged.items(), key=lambda kv: (kv[1]["rate"], kv[0]))
    lines = [
        f"# Citation Screen — model attention over {total_notes} notes",
        "",
        "WP-18.3 (low-cost, no LLM). How often the model **names** each input in its "
        "free-prose rationale (Executive Summary, asset/theme sections, Key Risks, "
        "Primary Driver) — Macro Dashboard table and Data Snapshot excluded.",
        "",
        "**A screening proxy, never a verdict** — the model can use an input without "
        "naming it, or name one that didn't move the call. Flags WP-18.4 candidates.",
        "",
        f"- prune_priority: **high** = redundant/dead (KB-009) *and* cited ≤{rare_rate:.0%}; "
        "**watch** = one of the two; **keep** = neither."
        + ("" if has_ledger else "  _(no ledger supplied → redundancy unknown, priority from citation only)_"),
        "",
        "| Input | Cited rate | Notes | Redundant | info_score | Priority |",
        "|-------|-----------:|------:|:---------:|-----------:|----------|",
    ]
    for name, m in rows:
        red = "—" if m["redundant"] is None else ("yes" if m["redundant"] else "no")
        info = "—" if m["info_score"] is None else f"{m['info_score']:.3f}"
        lines.append(
            f"| {name} | {m['rate']:.0%} | {m['cited_in']}/{m['total']} | "
            f"{red} | {info} | {m['prune_priority']} |"
        )

    high = [n for n, m in rows if m["prune_priority"] == "high"]
    lines += ["", "## Strongest prune candidates (redundant/dead AND rarely cited)", ""]
    lines.append(", ".join(high) if high else "_None._")
    return lines


# ---------------------------------------------------------------------------
# IO shell
# ---------------------------------------------------------------------------

def _version_of(md_text: str) -> "Optional[str]":
    m = re.search(r"^agent_version:\s*(v[\d.]+)", md_text, flags=re.MULTILINE)
    return m.group(1) if m else None


def _version_ge(v: str, floor: str) -> bool:
    def parts(s): return [int(x) for x in s.lstrip("v").split(".")]
    try:
        return parts(v) >= parts(floor)
    except Exception:  # noqa: BLE001
        return False


def load_rationales(results_dir: Path, min_version: "Optional[str]" = None) -> "list[str]":
    """Read every *-macro.md under results/, return their extracted rationales."""
    out: list[str] = []
    for md in sorted(results_dir.rglob("*-macro.md")):
        text = md.read_text(encoding="utf-8")
        if min_version:
            v = _version_of(text)
            if not v or not _version_ge(v, min_version):
                continue
        out.append(extract_rationale(text))
    return out


def _load_latest_ledger(results_dir: Path, explicit: "Optional[Path]") -> "Optional[dict]":
    if explicit:
        return json.loads(explicit.read_text(encoding="utf-8"))
    led_dir = results_dir / "input_ledger"
    files = sorted(led_dir.glob("*.json")) if led_dir.exists() else []
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def main() -> None:
    ap = argparse.ArgumentParser(description="WP-18.3 model-attention / citation screen")
    ap.add_argument("--min-version", default=None,
                    help="only count notes at/after this agent_version (e.g. v0.3)")
    ap.add_argument("--ledger", default=None,
                    help="path to an input_ledger JSON (default: latest under results/input_ledger)")
    ap.add_argument("--rare-rate", type=float, default=0.10,
                    help="citation rate at/below which an input is 'rarely cited' (default 0.10)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    results_dir = repo_root / "results"

    rationales = load_rationales(results_dir, args.min_version)
    if not rationales:
        print("No scored notes found under results/. Nothing to screen.")
        return

    patterns = compile_patterns({**INPUT_ALIASES, **DERIVED_ALIASES})
    agg = aggregate_citations(rationales, patterns)
    ledger = _load_latest_ledger(results_dir, Path(args.ledger) if args.ledger else None)
    merged = merge_with_ledger(agg, ledger, args.rare_rate)

    asof = datetime.now(timezone.utc).date().isoformat()
    out_dir = results_dir / "citation_screen"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": asof, "n_notes": len(rationales),
        "min_version": args.min_version, "rare_rate": args.rare_rate,
        "ledger_used": bool(ledger), "inputs": merged,
    }
    (out_dir / f"{asof}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = render_screen_md(merged, len(rationales), args.rare_rate, bool(ledger))
    (out_dir / f"{asof}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"Screened {len(rationales)} notes"
          + (f" (≥{args.min_version})" if args.min_version else "")
          + f"; ledger {'joined' if ledger else 'not found'}.")
    print(f"Written: {out_dir / (asof + '.md')}\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
