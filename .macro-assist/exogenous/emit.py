"""
emit.py — WP-19.B live/forward emission: write the exogenous arm's note into the corpus.

Runs the full monetary slice for a given as-of date and writes the arm-tagged note
to `results/<MM-Month>/<asof>-exogenous-macro.md` — exactly where `score_predictions`
scans (its default `REPORTS_DIR`), alongside the market-only notes. The existing
weekly scoring workflow then scores it when the 5-day window closes and
`summarize_accuracy` shows the exogenous-vs-market A/B (DESIGN §4/§5).

POINT-IN-TIME (two distinct dates, deliberately):
  - the FOMC **evidence** is as-of the *statement's* release date (`published`), so
    L1 never sees post-statement information; and
  - the **prediction** is dated *today* (`asof`) — same forward entry point as the
    market arm's same-day note — so the A/B is like-for-like.

Cadence (DESIGN §6.2/§7): validation is forward-only; run weekly. Between meetings
the statement is unchanged, so consecutive leans are correlated — an honest limit
of a monthly-cadence signal, not a bug (each week is still a fresh forward call
from that week's prices + consensus).

Needs ANTHROPIC_API_KEY (L1+L2). FRED_API_KEY optional (adds the SEP dots + gap).
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from exogenous.analyst import synthesize_brief
from exogenous.extract import extract_evidence
from exogenous.fed_docs import fetch_latest_statement
from exogenous.run_slice import build_consensus
from exogenous.synth import render_exo_note, to_exo_output

# Scorer's default REPORTS_DIR (repo results/). Same tree the market notes live in.
RESULTS_DIR = HERE.parent.parent / "results"


def _month_dir(d: date) -> str:
    return d.strftime("%m-%B")   # e.g. "07-July" — matches the market pipeline


def note_path(asof: date, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / _month_dir(asof) / f"{asof.isoformat()}-exogenous-macro.md"


def emit_note(
    client, asof: Optional[date] = None, results_dir: Path = RESULTS_DIR,
    year: Optional[int] = None, force: bool = False,
) -> Optional[Path]:
    """Fetch the latest statement, run L0→L3, write the arm-tagged note. Idempotent
    per day: skips if the note already exists unless `force`."""
    asof = asof or date.today()
    out = note_path(asof, results_dir)
    if out.exists() and not force:
        print(f"Note already exists (use force to overwrite): {out}", file=sys.stderr)
        return out

    stmt = fetch_latest_statement(asof)
    if stmt is None:
        print("No FOMC statement found — nothing emitted.", file=sys.stderr)
        return None

    evidence = extract_evidence(client, stmt["text"], "fomc_statement",
                                stmt["source_id"], stmt["published"])
    consensus = build_consensus(asof, year)
    brief = synthesize_brief(client, evidence, consensus, asof)
    if brief is None:
        print("L2 returned no brief — nothing emitted.", file=sys.stderr)
        return None

    exo = to_exo_output(brief, evidence)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_exo_note(exo), encoding="utf-8")
    return out


def main() -> int:
    import argparse

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — the L1/L2 model calls need it.", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(description="Emit the exogenous arm's note into results/")
    ap.add_argument("--asof", default=None, help="prediction date (YYYY-MM-DD; default today)")
    ap.add_argument("--year", type=int, default=None, help="SEP target year for the gap")
    ap.add_argument("--force", action="store_true", help="overwrite an existing note")
    args = ap.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else date.today()

    from anthropic import Anthropic
    path = emit_note(Anthropic(), asof=asof, year=args.year, force=args.force)
    if path is None:
        return 1
    print(f"Emitted exogenous note: {path}\n")
    print(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
