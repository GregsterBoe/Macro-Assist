"""
backfill_note_metrics.py — Stamp note_metrics onto daily notes already on `output`.

New notes get their metrics in the frontmatter at build time
(`collect_and_analyze.build_report`). This copies the same numbers into the
notes written before that, so a vault chart has the whole history. Same
function, same keys: `note_metrics.stamp`. Safe to re-run — a note that already
carries its metrics is left byte-identical.

Scope: the production daily notes only (`YYYY-MM-DD-<Weekday>-macro.md`). Arm
notes (`-kimi-`, `-exogenous-`) are left untouched, as `tag_versions.py` leaves
them. Only the frontmatter changes; the body is never rewritten.

Usage (with `results/` mounted as the `output` worktree):
    python .macro-assist/backfill_note_metrics.py --dry-run
    python .macro-assist/backfill_note_metrics.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from note_metrics import stamp

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
DAILY_NOTE = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Z][a-z]+day-macro\.md$")


def backfill(results_dir: Path, dry_run: bool = False) -> dict[str, int]:
    """Stamp every daily note under `results_dir`; return per-outcome counts."""
    tally = {"stamped": 0, "unchanged": 0, "skipped": 0}
    for path in sorted(results_dir.rglob("*-macro.md")):
        if not DAILY_NOTE.match(path.name):
            tally["skipped"] += 1
            continue
        text = path.read_text(encoding="utf-8")
        new = stamp(text)
        if new == text:
            tally["unchanged"] += 1
            continue
        tally["stamped"] += 1
        if not dry_run:
            path.write_text(new, encoding="utf-8")
    return tally


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--dry-run", action="store_true", help="count, write nothing")
    ap.add_argument("--results", type=Path, default=RESULTS_DIR)
    args = ap.parse_args()
    if not args.results.is_dir():
        print(f"No results directory at {args.results} — mount the output worktree first.")
        return 1
    t = backfill(args.results, dry_run=args.dry_run)
    verb = "would stamp" if args.dry_run else "stamped"
    print(f"{verb} {t['stamped']}, already current {t['unchanged']}, "
          f"arm notes skipped {t['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
