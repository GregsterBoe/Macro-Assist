"""
tag_versions.py — Retroactively apply agent_version to existing result and score files.

Assigns the correct pipeline version to every report that predates the versioning
system (introduced 2026-05-26). Safe to re-run — skips files that already carry
an agent_version field.

Version milestones are derived from the git commit history. Each version boundary
corresponds to a structural capability change (new data source, new agent pass,
new prompt architecture).

Usage:
    python .macro-assist/tag_versions.py
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from versions import VERSION_MILESTONES, version_for_date

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
SCORES_DIR  = RESULTS_DIR / "scores"


# ---------------------------------------------------------------------------
# Tag result markdown files
# ---------------------------------------------------------------------------

def tag_result_files() -> tuple[int, int]:
    """Insert agent_version into YAML frontmatter of all *-macro.md files.

    Inserts the field after the ``type: macro-intelligence`` line to match
    the format used by the pipeline going forward.

    Returns (tagged, skipped) counts.
    """
    tagged = skipped = 0
    for path in sorted(RESULTS_DIR.rglob("*-macro.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not m:
            continue
        report_date = date.fromisoformat(m.group(1))
        version = version_for_date(report_date)

        content = path.read_text(encoding="utf-8")
        if "agent_version:" in content:
            skipped += 1
            continue

        updated = re.sub(
            r"(^type: macro-intelligence\s*$)",
            r"\1\nagent_version: " + version,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == content:
            print(f"  WARN: no 'type:' line found in {path.name} — skipping")
            skipped += 1
            continue

        path.write_text(updated, encoding="utf-8")
        tagged += 1
        print(f"  {path.name}  →  {version}")

    return tagged, skipped


# ---------------------------------------------------------------------------
# Tag score JSON files
# ---------------------------------------------------------------------------

def tag_score_files() -> tuple[int, int]:
    """Insert agent_version into results/scores/*.json files.

    The field is inserted immediately after report_date to keep the JSON
    readable in the same order as the markdown frontmatter.

    Returns (tagged, skipped) counts.
    """
    tagged = skipped = 0
    for path in sorted(SCORES_DIR.glob("*.json")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
        if not m:
            continue
        report_date = date.fromisoformat(m.group(1))
        version = version_for_date(report_date)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: could not load {path.name}: {exc} — skipping")
            skipped += 1
            continue

        if "agent_version" in data:
            skipped += 1
            continue

        # Re-serialise with agent_version inserted after report_date
        new_data: dict = {}
        for k, v in data.items():
            new_data[k] = v
            if k == "report_date":
                new_data["agent_version"] = version

        path.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
        tagged += 1
        print(f"  {path.name}  →  {version}")

    return tagged, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("tag_versions.py - backfilling agent_version metadata")
    print("=" * 55)

    print(f"\nTagging result markdown files in {RESULTS_DIR} ...")
    md_tagged, md_skipped = tag_result_files()
    print(f"  Result:  {md_tagged} tagged, {md_skipped} already had version / skipped\n")

    print(f"Tagging score JSON files in {SCORES_DIR} ...")
    j_tagged, j_skipped = tag_score_files()
    print(f"  Result:  {j_tagged} tagged, {j_skipped} already had version / skipped\n")

    print(f"Done. {md_tagged + j_tagged} file(s) updated.")
    print("\nNext step: re-run summarize_accuracy.py to regenerate")
    print("accuracy_summary.json with feedback_windows populated.")


if __name__ == "__main__":
    main()
