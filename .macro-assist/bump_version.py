#!/usr/bin/env python3
"""
bump_version.py — Atomic pipeline version bump.

Usage
-----
    python .macro-assist/bump_version.py vX.Y "+ capability description"
    python .macro-assist/bump_version.py vX.Y "+ ..." --start 2026-09-14

What it does
------------
  1. Updates PIPELINE_VERSION in versions.py
  2. Closes the currently-open milestone (end date -> the day before the start)
  3. Appends the new milestone entry to VERSION_MILESTONES
  4. Regenerates the milestone table in docs/reference/versions.md from
     VERSION_MILESTONES, and updates the example `agent_version` YAML/JSON there

Steps 1-3 are the source of truth; step 4 is a derived view. The table is
rewritten wholesale between HTML markers rather than patched row-by-row, so a
row whose wording drifted cannot survive a bump, and there is no anchor to go
missing the way the old roadmap-table regex did (Open decision #9).

`--start` exists because a capability does not always go live the day it merges.
The weekly refit runs Sunday night, so a change that only takes effect once the
models rebuild should be stamped from that date, not from the merge. Default is
today.

Then run the post-bump hooks:
    python .macro-assist/tag_versions.py
    python .macro-assist/summarize_accuracy.py
    pytest .macro-assist/tests/test_versions.py
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

_HERE      = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_VERSIONS  = _HERE / "versions.py"
_DOC       = _REPO_ROOT / "docs" / "reference" / "versions.md"

_BEGIN = "<!-- BEGIN VERSION MILESTONES — generated from versions.py by bump_version.py; do not edit by hand -->"
_END   = "<!-- END VERSION MILESTONES -->"


# ---------------------------------------------------------------------------
# The derived view
# ---------------------------------------------------------------------------

def render_milestones_table(milestones) -> str:
    """The markdown milestone table, exactly as it appears in the docs page.

    Imported by tests/test_versions.py, which asserts the committed page matches
    this output — that assertion is the whole reason the table is allowed to
    exist in two places at once.
    """
    rows = [
        "| Version | Date Range | Capability Added |",
        "|---------|-----------|-----------------|",
    ]
    for m in milestones:
        if m.is_zero_range:
            span = f"{m.start:%Y-%m-%d} – *(superseded same day)*"
        elif m.is_open:
            span = f"**{m.start:%Y-%m-%d} – present**"
        else:
            span = f"{m.start:%Y-%m-%d} – {m.end:%Y-%m-%d}"
        version = f"**{m.version}**" if m.is_open else m.version
        rows.append(f"| {version} | {span} | {m.capability} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 1-3. versions.py
# ---------------------------------------------------------------------------

def _update_versions_py(new_version: str, capability: str, start: date, closed_end: date) -> None:
    text = _VERSIONS.read_text(encoding="utf-8")

    new_text, n = re.subn(
        r'(PIPELINE_VERSION:\s*str\s*=\s*)"v[\d.]+"',
        lambda m: f'{m.group(1)}"{new_version}"',
        text,
        count=1,
    )
    if n != 1:
        raise ValueError("could not find the PIPELINE_VERSION assignment in versions.py")
    text = new_text

    # The open milestone is the one ending 2099-12-31. Close it, then append the
    # new open entry directly after it. `[^\n]` keeps the match on one physical
    # line: with DOTALL a lazy `.*?` would happily start at the *first* milestone
    # and swallow the whole list up to the 2099 sentinel.
    open_entry = re.search(r'^([ \t]*)Milestone\([^\n]*date\(2099, 12, 31\)[^\n]*\),[ \t]*$',
                           text, flags=re.MULTILINE)
    if open_entry is None:
        raise ValueError(
            "could not find an open milestone (date(2099, 12, 31)) in VERSION_MILESTONES. "
            "Check versions.py by hand."
        )

    indent = open_entry.group(1)
    closed = open_entry.group(0).replace(
        "date(2099, 12, 31)",
        f"date({closed_end.year}, {closed_end.month:2d}, {closed_end.day:2d})",
    )
    appended = (
        f'{indent}Milestone("{new_version}", '
        f'date({start.year}, {start.month:2d}, {start.day:2d}), '
        f'date(2099, 12, 31), '
        f'"{capability}"),'
    )
    text = text[:open_entry.start()] + closed + "\n" + appended + text[open_entry.end():]

    _VERSIONS.write_text(text, encoding="utf-8")
    print(f"  ok  versions.py            PIPELINE_VERSION -> {new_version!r}, milestone closed + appended")


# ---------------------------------------------------------------------------
# 4. The docs page (derived)
# ---------------------------------------------------------------------------

def _update_doc(new_version: str) -> None:
    # Import only after versions.py is rewritten, so the table renders the new list.
    sys.path.insert(0, str(_HERE))
    sys.modules.pop("versions", None)   # a test may already hold the pre-bump module
    import versions

    text = _DOC.read_text(encoding="utf-8")

    if _BEGIN not in text or _END not in text:
        raise ValueError(
            f"could not find the generated-table markers in {_DOC.relative_to(_REPO_ROOT)}. "
            "The table is rewritten between them; restore the BEGIN/END comments."
        )

    head, rest = text.split(_BEGIN, 1)
    _, tail = rest.split(_END, 1)
    table = render_milestones_table(versions.VERSION_MILESTONES)
    text = f"{head}{_BEGIN}\n\n{table}\n\n{_END}{tail}"

    # The example frontmatter and score-file stamps on the same page.
    text, n_yaml = re.subn(r'(agent_version:\s*)v[\d.]+', rf'\g<1>{new_version}', text)
    text, n_json = re.subn(r'("agent_version":\s*")v[\d.]+(")', rf'\g<1>{new_version}\g<2>', text)

    _DOC.write_text(text, encoding="utf-8")
    print(
        f"  ok  docs/reference/versions.md  table regenerated "
        f"({len(versions.VERSION_MILESTONES)} milestones), {n_yaml + n_json} example stamps updated"
    )


def bump(new_version: str, capability: str, start: date) -> None:
    closed_end = start - timedelta(days=1)
    print(f"Bumping pipeline version -> {new_version}  (live from {start:%Y-%m-%d})")
    _update_versions_py(new_version, capability, start, closed_end)
    _update_doc(new_version)
    print(
        "\nDone. Run the post-bump hooks:\n"
        "  python .macro-assist/tag_versions.py\n"
        "  python .macro-assist/summarize_accuracy.py\n"
        "  pytest .macro-assist/tests/test_versions.py"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="bump_version.py",
        description="Bump the pipeline version and regenerate the derived docs table.",
    )
    ap.add_argument("version", help='new version, "vX.Y" (e.g. v1.8)')
    ap.add_argument("capability", help="one-line capability description for the milestone table")
    ap.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="date the capability goes live (default: today). Use when a change only "
             "takes effect on a later run, e.g. after the Sunday refit.",
    )
    args = ap.parse_args()

    if not re.match(r"^v\d+\.\d+$", args.version):
        ap.error(f"version must be 'vX.Y' format (e.g. v1.8), got: {args.version!r}")
    if not args.capability.strip():
        ap.error("capability description must not be empty")
    if '"' in args.capability:
        ap.error("capability description must not contain a double quote")

    if args.start:
        try:
            start = date.fromisoformat(args.start)
        except ValueError:
            ap.error(f"--start must be YYYY-MM-DD, got: {args.start!r}")
    else:
        start = date.today()

    try:
        bump(args.version, args.capability.strip(), start)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
