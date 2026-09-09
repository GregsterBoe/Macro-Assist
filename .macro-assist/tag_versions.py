"""
tag_versions.py — Retroactively apply agent_version to existing result and score files.

Assigns the correct pipeline version to every report that predates the versioning
system (introduced 2026-05-26). Safe to re-run — skips files that already carry
an agent_version field.

Version milestones are derived from the git commit history. Each version boundary
corresponds to a structural capability change (new data source, new agent pass,
new prompt architecture).

Scope: the **production `market` arm only**. `versions.py` maps dates to milestones
of the main pipeline, so stamping a sibling arm (`kimi`, `exogenous`) with one would
assert a lineage it does not share — a kimi note's version axis is its `model` and
`ensemble_n`, not vX.Y. Arm files are therefore identified, counted on their own
line, and left untouched, including their `agent_version: "unknown"` in the score
JSON. Consequence to keep in mind: `_version_key("unknown")` falls back to (0, 0),
so `summarize_accuracy.py` drops those 25 score files from any run gated on
MIN_FEEDBACK_VERSION. They still reach `calibration_by_arm`, which splits on `arm`
rather than on version.

Usage:
    python .macro-assist/tag_versions.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from bias_separation import PRIMARY_ARM, UNTAGGED, arm_of
from versions import version_for_date

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
SCORES_DIR  = RESULTS_DIR / "scores"


class Tally(Counter):
    """Per-pass outcome counts, plus which arms were skipped and why."""

    def __init__(self) -> None:
        super().__init__()
        self.arms: Counter = Counter()

    def skip_arm(self, arm: str) -> None:
        self["arm"] += 1
        self.arms[arm] += 1

    def line(self) -> str:
        parts = [f"{self['tagged']} tagged", f"{self['versioned']} already versioned"]
        if self["arm"]:
            arms = ", ".join(f"{a} {n}" for a, n in sorted(self.arms.items()))
            parts.append(f"{self['arm']} arm files, not main-pipeline ({arms})")
        if self["unrecognised"]:
            parts.append(f"{self['unrecognised']} unrecognised")
        return "  Result:  " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def _frontmatter(content: str) -> str:
    """The YAML frontmatter block of a report, or "" if it has none.

    Same contract as score_predictions.parse_frontmatter, kept local so the
    backfill does not import the scorer just to read two lines.
    """
    if not content.startswith("---"):
        return ""
    end = content.find("---", 3)
    return content[3:end] if end != -1 else ""


def _arm_of_markdown(content: str) -> str:
    """The arm a report markdown belongs to.

    The markdown-side mirror of bias_separation.arm_of: an absent `arm:` means
    the note predates the arm machinery, which only ever ran the production
    pipeline, so it resolves to PRIMARY_ARM rather than to a separate bucket.
    """
    m = re.search(r"^arm:\s*(\S+)", _frontmatter(content), re.MULTILINE)
    return arm_of({"arm": m.group(1)} if m else {})


# ---------------------------------------------------------------------------
# Tag result markdown files
# ---------------------------------------------------------------------------

def tag_result_files() -> Tally:
    """Insert agent_version into YAML frontmatter of main-pipeline *-macro.md files.

    Inserts the field after the ``type: macro-intelligence`` line to match
    the format used by the pipeline going forward. Sibling-arm notes carry a
    different frontmatter shape (`arm:`/`model:`/`as_of:`, no `type:` line) and
    are skipped by arm rather than by failing the regex.
    """
    tally = Tally()
    for path in sorted(RESULTS_DIR.rglob("*-macro.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not m:
            continue
        report_date = date.fromisoformat(m.group(1))
        version = version_for_date(report_date)

        content = path.read_text(encoding="utf-8")

        arm = _arm_of_markdown(content)
        if arm != PRIMARY_ARM:
            tally.skip_arm(arm)
            continue

        if "agent_version:" in content:
            tally["versioned"] += 1
            continue

        updated = re.sub(
            r"(^type: macro-intelligence\s*$)",
            r"\1\nagent_version: " + version,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == content:
            print(f"  WARN: {path.name} is a {PRIMARY_ARM}-arm note but has no "
                  f"'type: macro-intelligence' line — skipping")
            tally["unrecognised"] += 1
            continue

        path.write_text(updated, encoding="utf-8")
        tally["tagged"] += 1
        print(f"  {path.name}  →  {version}")

    return tally


# ---------------------------------------------------------------------------
# Tag score JSON files
# ---------------------------------------------------------------------------

def tag_score_files() -> Tally:
    """Insert agent_version into main-pipeline results/scores/*.json files.

    The field is inserted immediately after report_date to keep the JSON
    readable in the same order as the markdown frontmatter. A file already
    holding the UNTAGGED sentinel counts as untagged and is backfilled, since
    the sentinel means the scorer found no version to copy — but only for the
    production arm; sibling arms keep theirs.
    """
    tally = Tally()
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
            tally["unrecognised"] += 1
            continue

        arm = arm_of(data)
        if arm != PRIMARY_ARM:
            tally.skip_arm(arm)
            continue

        current = data.get("agent_version")
        if current and current != UNTAGGED:
            tally["versioned"] += 1
            continue

        if "agent_version" in data:
            # Sentinel already sits in the right position — overwrite in place.
            data["agent_version"] = version
            new_data = data
        else:
            new_data = {}
            for k, v in data.items():
                new_data[k] = v
                if k == "report_date":
                    new_data["agent_version"] = version

        path.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
        tally["tagged"] += 1
        print(f"  {path.name}  →  {version}")

    return tally


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("tag_versions.py - backfilling agent_version metadata")
    print("=" * 55)

    print(f"\nTagging result markdown files in {RESULTS_DIR} ...")
    md = tag_result_files()
    print(md.line() + "\n")

    print(f"Tagging score JSON files in {SCORES_DIR} ...")
    js = tag_score_files()
    print(js.line() + "\n")

    updated = md["tagged"] + js["tagged"]
    print(f"Done. {updated} file(s) updated.")
    if updated:
        print("\nNext step: re-run summarize_accuracy.py to regenerate")
        print("accuracy_summary.json with feedback_windows populated.")
    else:
        print("Nothing to backfill — every main-pipeline file already carries its version.")


if __name__ == "__main__":
    main()
