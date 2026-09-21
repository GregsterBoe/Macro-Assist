"""
orient.py — what `/orient` prints at turn 1 of a session (WP-24.G,
docs/record/roadmap.md → Phase 24).

The record layer's rules all have a reader problem: the board wins on status,
the owner writes a promoted hypothesis, a contradiction is not "fixed" by
picking a side — and none of that helps a session that never read the page it
is written on. `record_audit.py` gave the rules detectors; this gives the
detectors a moment. One command, one screen, before any work is proposed:

  board      the status board's "Right now", its latest changelog row, every
             Active row with its `Next:` line and every Queued row — each
             with the days since it was last edited (24.E)
  inbox      every open todo.md item, oldest first (24.E)
  audit      record_audit's findings — 24.D's contradictions included, with a
             per-check count so a zero is visible — and its red/report-only
             summary
  revisit    24.F's report-only lines: an ADR whose revisit section cites a
             todo item, WP, KB entry or Phase that closed after the section
             was last edited
  gate       the owner's competence gate from how-we-explore §6, printed
             whenever the register holds an entry that has not been promoted
             or closed (`draft`, `seen`, `proposed`) — the rule had no
             trigger; this is it. The questions are read from the page, not
             copied here (convention #8).

It reads; it never writes. Everything it prints is in the docs already — the
point is that it is in context before the docs are opened. The skill that
runs it is `.claude/skills/orient/SKILL.md`.

Run:
    python .macro-assist/orient.py
    python .macro-assist/orient.py --root PATH
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import record_audit as ra

HYPOTHESES = ra.RECORD_DIR / "hypotheses.md"
HOW_WE_EXPLORE = ra.DOCS_DIR / "concepts" / "how-we-explore.md"

# The register's status vocabulary (hypotheses.md, "Status:"). A promotion is
# pending while any entry sits in a state from which the next transition is
# `promoted` — and that transition is the owner's (§6).
PENDING_STATUSES = ("draft", "seen", "proposed")

_RIGHT_NOW_RE = re.compile(r"^\*\*Right now:\*\*[ \t]*([^\n]*(?:\n(?!\n)[^\n]*)*)", re.M)
_CHANGELOG_ROW_RE = re.compile(r"^\| \*\*(\d{4}-\d{2}-\d{2})\*\*[^|]*\| ([^\n]*?) \|[ \t]*$", re.M)
_BOLD_LEAD_RE = re.compile(r"^\*\*([^*]+)\*\*")
_NEXT_RE = re.compile(r"^- \*\*Next:\*\*[ \t]*([^\n]*)", re.M)
_REGISTER_ROW_RE = re.compile(r"^\| \[(H-\d+)\]\([^)]*\) \| `(\w+)` \| ([^\n]*?) \|[ \t]*$", re.M)
_GATE_SECTION_RE = re.compile(r"^## 6\. [^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CHECK_NAMES = tuple(c.__name__.removeprefix("check_").replace("_", "-") for c in ra.CHECKS)


def _plain(text: str) -> str:
    """Markdown → one line of prose: links to their text, bold and code
    marks dropped, whitespace collapsed."""
    text = _LINK_RE.sub(r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return " ".join(text.split())


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _head(root: Path) -> str:
    """"abc1234 subject (branch, clean)" — or what git can say."""
    head = ra._git(root, "log", "-1", "--format=%h %s")
    if head is None:
        return "(not a git repository)"
    branch = ra._git(root, "branch", "--show-current") or "detached"
    dirty = ra._git(root, "status", "--porcelain")
    state = "clean" if not dirty else f"{len(dirty.splitlines())} uncommitted"
    return f"{head} ({branch}, {state})"


# ---------------------------------------------------------------------------
# the board
# ---------------------------------------------------------------------------

def _board_lines(root: Path, table: list[ra.Age]) -> list[str]:
    text = ra._text_at(root, str(ra.BOARD), None)
    if text is None:
        return ["  (no board — docs/record/active-experiments.md is missing)"]
    out: list[str] = []
    if (m := _RIGHT_NOW_RE.search(text)):
        out.append(f"  Right now: {_plain(m.group(1))}")
    if (m := _CHANGELOG_ROW_RE.search(text)):
        lead = _BOLD_LEAD_RE.match(m.group(2))
        out.append(f"  Latest:    {m.group(1)} — {_plain(lead.group(1) if lead else _clip(m.group(2), 160))}")
    age_of = {a.subject: a for a in table if a.subject.startswith("board: ")}
    lines = text.split("\n")
    for section, rows in (("Active", _active_rows(lines)), ("Queued / dormant", _queued_rows(lines))):
        out.append(f"  {section}:")
        if not rows:
            out.append("    (none)")
        for heading, nxt in rows:
            age = age_of.get(f"board: {ra._row_name(heading)}")
            stamp = f"  [{age.days:.0f} d, {age.what.split(' ', 1)[0]}]" if age else ""
            out.append(f"    {_plain(heading)}{stamp}")
            if nxt:
                out.append(f"      next: {_plain(nxt)}")
    return out


def _section(lines: list[str], name: str) -> tuple[int, int]:
    """[first, last) line index of the `## name` section, or (0, 0)."""
    start = next((i for i, l in enumerate(lines) if l.strip() == f"## {name}"), None)
    if start is None:
        return 0, 0
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    return start + 1, end


def _active_rows(lines: list[str]) -> list[tuple[str, str | None]]:
    """(heading, its `Next:` line) per `###` row under "## Active"."""
    first, last = _section(lines, "Active")
    rows: list[tuple[str, str | None]] = []
    i = first
    while i < last:
        if lines[i].startswith("### "):
            end = next((j for j in range(i + 1, last) if lines[j].startswith("### ")), last)
            body = "\n".join(lines[i + 1:end])
            nxt = _NEXT_RE.search(body)
            rows.append((lines[i][4:], nxt.group(1) if nxt else None))
            i = end
        else:
            i += 1
    return rows


def _queued_rows(lines: list[str]) -> list[tuple[str, None]]:
    """(name + marker, None) per top-level bullet under "## Queued / dormant"."""
    first, last = _section(lines, "Queued / dormant")
    rows: list[tuple[str, None]] = []
    for line in lines[first:last]:
        if (m := ra._BOARD_BULLET_RE.match(line)):
            marker = ra._MARKER_RE.search(m.group(2))
            rows.append((m.group(1) + (f" {marker.group(0)}" if marker else ""), None))
    return rows


# ---------------------------------------------------------------------------
# the register and the gate
# ---------------------------------------------------------------------------

def pending_promotions(root: Path) -> list[tuple[str, str, str]]:
    """(id, status, claim) for every register entry in a pre-promotion
    state, from the register's own summary table."""
    text = ra._text_at(root, str(HYPOTHESES), None)
    if text is None:
        return []
    out = []
    for hid, status, claim in _REGISTER_ROW_RE.findall(text):
        if status in PENDING_STATUSES:
            out.append((hid, status, _plain(claim.split(" — *", 1)[0])))
    return out


def gate_questions(root: Path) -> list[str]:
    """The bullets of how-we-explore §6, as the page has them today."""
    text = ra._text_at(root, str(HOW_WE_EXPLORE), None)
    if text is None or not (m := _GATE_SECTION_RE.search(text)):
        return []
    out: list[str] = []
    for line in m.group(1).split("\n"):
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.startswith("  ") and out:
            out[-1] += " " + line.strip()
    return [_plain(q) for q in out]


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(root: Path, *, now: datetime | None = None) -> str:
    """The screen. `now` replays the dated parts the way record_audit's
    `--now` does; the board and the register are always read as they are."""
    table = ra.ages(root, now=now)
    findings = ra.audit(root, now=now)
    now = now or datetime.now(timezone.utc)
    revisit_notes = [f for f in findings if f.check == "adr-revisit" and not f.red]
    audited = [f for f in findings if f not in revisit_notes]
    reds = [f for f in findings if f.red]
    notes = [f for f in findings if not f.red]

    out = [f"orient — {root}  {now:%Y-%m-%d}  {_head(root)}", ""]

    out.append("BOARD — docs/record/active-experiments.md (wins on status; a detailed doc wins on substance)")
    out.extend(_board_lines(root, table))
    out.append("")

    inbox = [a for a in table if a.subject.startswith("todo.md ")]
    out.append(f"INBOX — {len(inbox)} open todo.md item(s), oldest first (days since last edit, WP-24.E)")
    for a in inbox:
        out.append(f"  {a.days:5.0f} d  {a.subject.removeprefix('todo.md '):<52}  {a.when:%Y-%m-%d}  {a.what}")
    if not inbox and not table:
        out.append("  (unreadable — not a git repository or a shallow clone; ages need history)")
    elif not inbox:
        out.append("  (empty)")
    out.append("")

    counts = {name: 0 for name in _CHECK_NAMES}
    for f in findings:
        counts[f.check] = counts.get(f.check, 0) + 1
    out.append(f"AUDIT — record_audit.py: {len(reds)} red, {len(notes)} report-only"
               f"  ({' · '.join(f'{k} {v}' for k, v in counts.items())})")
    for f in sorted(audited, key=lambda f: (not f.red, f.check)):
        out.append(f"  {f}")
    if not audited:
        out.append("  clean")
    out.append("")

    out.append("ADR REVISIT — a cited condition that closed after its section was last edited (WP-24.F)")
    for f in revisit_notes:
        out.append(f"  {f.subject} — {f.message}")
    if not revisit_notes:
        out.append("  none")
    out.append("")

    pending = pending_promotions(root)
    if pending:
        out.append("COMPETENCE GATE — a promotion is pending; the owner writes it (how-we-explore §6)")
        for hid, status, claim in pending:
            out.append(f"  {hid} `{status}` — {_clip(claim, 100)}")
        questions = gate_questions(root)
        out.append("  Before promoting any of these, the owner — without the assistant — can:")
        for i, q in enumerate(questions, 1):
            out.append(f"    {i}. {q}")
        if not questions:
            out.append("    (how-we-explore §6 has no bullet list — read the page)")
    else:
        out.append("COMPETENCE GATE — no promotion pending (the register holds no draft / seen / proposed entry)")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print the session-start orientation (WP-24.G). Never writes.")
    ap.add_argument("--root", type=Path, default=ra._repo_root(), help="repo root (default: this checkout)")
    args = ap.parse_args(argv)
    sys.stdout.write(render(args.root.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
