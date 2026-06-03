#!/usr/bin/env python3
"""
bump_version.py — Atomic pipeline version bump.

Usage
-----
    python .macro-assist/bump_version.py vX.Y "+ capability description"

What it does (all four manual steps from versions.py, atomically)
------------------------------------------------------------------
  1. Updates PIPELINE_VERSION in versions.py
  2. Closes the current open milestone entry (end date → yesterday)
  3. Appends new milestone entry to versions.py
  4. Updates the milestones table in Project_Development.md
  5. Updates the example agent_version YAML in Project_Development.md

Then run the post-bump hooks:
    python .macro-assist/tag_versions.py
    python .macro-assist/summarize_accuracy.py
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

_HERE        = Path(__file__).resolve().parent
_REPO_ROOT   = _HERE.parent
_VERSIONS    = _HERE / "versions.py"
_PROJECT_DOC = _REPO_ROOT / "Project_Development.md"


def _update_versions_py(new_version: str, capability: str, today: date, yesterday: date) -> None:
    lines = _VERSIONS.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    in_milestones = False
    inserted = False

    for line in lines:
        # 1. PIPELINE_VERSION string
        if re.match(r'PIPELINE_VERSION:\s*str\s*=', line):
            line = re.sub(r'"v[\d.]+"', f'"{new_version}"', line)

        # Track entry into VERSION_MILESTONES list
        if "VERSION_MILESTONES" in line and "=" in line and "[" in line:
            in_milestones = True

        # 2. Close the open-ended entry and 3. insert new entry right after
        if in_milestones and not inserted and "date(2099, 12, 31)" in line:
            line = line.replace(
                "date(2099, 12, 31)",
                f"date({yesterday.year}, {yesterday.month:2d}, {yesterday.day:2d})",
            )
            new_lines.append(line)
            new_lines.append(
                f'    ("{new_version}", '
                f'date({today.year}, {today.month:2d}, {today.day:2d}), '
                f'date(2099, 12, 31)),  # {capability}\n'
            )
            inserted = True
            continue

        if in_milestones and line.strip() == "]":
            in_milestones = False

        new_lines.append(line)

    if not inserted:
        raise ValueError(
            "Could not find an open-ended entry (date(2099, 12, 31)) in VERSION_MILESTONES. "
            "Check versions.py manually."
        )

    _VERSIONS.write_text("".join(new_lines), encoding="utf-8")
    print(f"  ok  versions.py  PIPELINE_VERSION -> {new_version!r}, milestone closed + new entry added")


def _update_project_doc(new_version: str, capability: str, today: date, yesterday: date) -> None:
    lines = _PROJECT_DOC.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    table_updated = False
    yaml_updated = False

    for line in lines:
        # 4. Milestones table: close the "present" row, append new row
        if not table_updated and re.match(r"\| v[\d.]+ \| [\d-]+ – present \|", line):
            line = line.replace(" – present |", f" – {yesterday.strftime('%Y-%m-%d')} |")
            new_lines.append(line)
            new_lines.append(
                f"| {new_version} | {today.strftime('%Y-%m-%d')} – present | {capability} |\n"
            )
            table_updated = True
            continue

        # 5. Example YAML agent_version — update all occurrences
        if re.search(r"agent_version:\s*v[\d.]+", line):
            line = re.sub(r"(agent_version:\s*)v[\d.]+", rf"\g<1>{new_version}", line)
            yaml_updated = True

        new_lines.append(line)

    if not table_updated:
        raise ValueError(
            "Could not find a '– present' row in the milestones table in Project_Development.md."
        )

    _PROJECT_DOC.write_text("".join(new_lines), encoding="utf-8")
    action = "milestones table + example YAML" if yaml_updated else "milestones table"
    print(f"  ok  Project_Development.md  {action} updated")


def bump(new_version: str, capability: str) -> None:
    today     = date.today()
    yesterday = today - timedelta(days=1)

    print(f"Bumping pipeline version -> {new_version}")
    _update_versions_py(new_version, capability, today, yesterday)
    _update_project_doc(new_version, capability, today, yesterday)
    print(
        f"\nDone. Run post-bump hooks:\n"
        f"  python .macro-assist/tag_versions.py\n"
        f"  python .macro-assist/summarize_accuracy.py"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {Path(sys.argv[0]).name} vX.Y \"+ capability description\"")
        sys.exit(1)

    new_ver  = sys.argv[1].strip()
    cap_desc = sys.argv[2].strip()

    if not re.match(r"^v\d+\.\d+$", new_ver):
        print(f"Error: version must be 'vX.Y' format (e.g. v1.5), got: {new_ver!r}")
        sys.exit(1)
    if not cap_desc:
        print("Error: capability description must not be empty")
        sys.exit(1)

    try:
        bump(new_ver, cap_desc)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
