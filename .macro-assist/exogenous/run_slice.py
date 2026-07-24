"""
run_slice.py — WP-19.B live smoke driver for the monetary slice (L0 → L1 → L2).

Chains the deterministic consensus adapters (L0: SPF economist path + SEP dot-plot
+ gap), the FOMC-text extractor (L1: Evidence via Haiku), and the analyst (L2:
bounded BranchBrief via Opus), printing each stage as JSON. Intended to be run in
CI (the `exo_slice_smoke.yml` workflow) so API keys live as repo secrets, not local
env vars — see DESIGN §6.2 (validation is forward/live; a run on a bundled fixture
is a *pipeline shakedown*, clearly flagged, NOT a scored result).

Needs ANTHROPIC_API_KEY (L1+L2). FRED_API_KEY is optional: without it the SEP/gap
anchor is skipped and the brief is built on FOMC evidence + SPF only.

  python .macro-assist/exogenous/run_slice.py \
      --fomc .macro-assist/exogenous/example/SHAKEDOWN_synthetic_fomc.txt \
      --published 2026-06-18
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # .macro-assist on path

from exogenous.analyst import ASSET_CANONICAL, brief_to_dict, synthesize_brief
from exogenous.extract import evidence_to_dicts, extract_from_file
from exogenous.spf import SPF_VARIABLES, latest_before, load_spf_file, load_spf_snapshot

# Default SPF workbooks shipped in example/ (median-level; economist consensus).
_EXAMPLE = HERE / "example"
_SPF_FILES = {
    "treasury_10y": _EXAMPLE / "Median_TBOND_Level.xlsx",
    "treasury_3m":  _EXAMPLE / "Median_TBILL_Level.xlsx",
    "unemployment": _EXAMPLE / "Median_UNEMP_Level.xlsx",
}


def _parse_date(s: str | None) -> date:
    return date.fromisoformat(s) if s else date.today()


def build_consensus(asof: date, year: int | None) -> dict:
    """L0 anchor: SPF snapshot (+ TBILL current) and, if FRED_API_KEY is set, SEP + gap."""
    consensus: dict = {}

    files = {k: v for k, v in _SPF_FILES.items() if v.exists()}
    if files:
        consensus["spf"] = load_spf_snapshot(files, asof)
        # short-rate for the gap (SPF 3M bill, point-in-time)
        tbill = files.get("treasury_3m")
        spf_short = None
        if tbill:
            got = latest_before(load_spf_file(tbill, SPF_VARIABLES["treasury_3m"]), asof)
            spf_short = got[1] if got else None
    else:
        spf_short = None
        print("  (no SPF workbooks found in example/ — skipping SPF anchor)", file=sys.stderr)

    if os.environ.get("FRED_API_KEY"):
        try:
            from exogenous.sep import consensus_gap
            sep = consensus_gap(spf_short_rate=spf_short, year=year or asof.year)
            consensus["sep"] = {"path_by_year": sep.get("path_by_year"),
                                "longer_run": sep.get("longer_run")}
            consensus["gap"] = sep.get("gap")
        except Exception as exc:  # keep the slice running without the SEP leg
            print(f"  (SEP/gap unavailable: {exc})", file=sys.stderr)
    else:
        print("  (FRED_API_KEY not set — skipping SEP dot-plot + gap)", file=sys.stderr)

    return consensus


def _section(title: str, obj) -> None:
    print(f"\n===== {title} =====")
    print(json.dumps(obj, indent=2, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description="Live smoke run of the monetary slice (L0→L1→L2)")
    ap.add_argument("--fomc", default=str(_EXAMPLE / "SHAKEDOWN_synthetic_fomc.txt"),
                    help="path to an FOMC statement text file")
    ap.add_argument("--published", default=None, help="ISO date the document was published")
    ap.add_argument("--year", type=int, default=None, help="SEP target year for the gap")
    ap.add_argument("--source-type", default="fomc_statement")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — the L1/L2 model calls need it.", file=sys.stderr)
        return 2

    published = _parse_date(args.published)
    fomc_path = Path(args.fomc)
    if not fomc_path.exists():
        print(f"FOMC document not found: {fomc_path}", file=sys.stderr)
        return 2

    is_fixture = "SHAKEDOWN" in fomc_path.name
    print("=" * 64)
    print("Phase-19 monetary slice — LIVE SMOKE (L0→L1→L2)")
    print(f"  document : {fomc_path.name}  (published {published})")
    if is_fixture:
        print("  NOTE: SYNTHETIC shakedown fixture — pipeline-wiring check only,")
        print("        NOT a real Fed statement and NOT a scored result (DESIGN §6.2).")
    print("=" * 64)

    from anthropic import Anthropic
    client = Anthropic()

    # L0 — deterministic consensus anchor
    consensus = build_consensus(published, args.year)
    _section("L0 consensus anchor (SPF / SEP / gap)", consensus)

    # L1 — FOMC text → Evidence
    evidence = extract_from_file(client, str(fomc_path), source_type=args.source_type,
                                 published=published)
    _section(f"L1 evidence ({len(evidence)} items)", evidence_to_dicts(evidence))

    # L2 — fuse → bounded BranchBrief
    brief = synthesize_brief(client, evidence, consensus, published)
    if brief is None:
        print("\nL2 returned no brief (no tool call).", file=sys.stderr)
        return 1
    _section("L2 BranchBrief", brief_to_dict(brief))

    print("\n----- asset lean → scorer names (for the eventual A/B) -----")
    for short, impl in brief.asset_implications.items():
        print(f"  {ASSET_CANONICAL[short]:<20} {impl['bias']:<8} conf={impl['confidence']}")
    print("\n(Eyeball: do net_stance and the asset biases follow the evidence? "
          "That is the CONFIRM-ON-FIRST-RUN gate before these leans are trusted.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
