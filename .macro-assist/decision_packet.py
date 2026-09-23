"""
decision_packet.py — turn a register entry into the worksheet its owner sits
down with (how-we-explore §6, §9).

The bottleneck on a promotion is not the thinking. It is that before there is
anything to think *about*, someone has to re-read five modules, re-find which
paragraph of the entry bears on which of the twelve questions, re-count the
looks in the ledger, and re-resolve every `[KB-###]` the entry names. That
assembly is mechanical, it is identical for every entry, and it is done from
scratch every time. This does it once, in about a second.

What it emits is a **worksheet, not an argument**:

  header      the entry, its status, where it lives, when the register last
              moved, and which of the register's fixed fields the entry
              actually carries
  ledger      §4's multiplicity material — the dated looks in the entry, the
              reports they name, and the harness's arm vocabulary, which is the
              family size a later bar has to be written against
  read first  every KB entry, ADR, work package and code path the entry names,
              resolved to a file where one exists
  questions   the twelve questions of §9 **as they read today**, each with the
              entry's own text against it and a blank underneath

Three rules it holds itself to, and they are the point:

1. **It never recommends.** There is no verdict field, no ranking, no "this
   looks ready". A recommendation written into a checked-in document becomes
   the answer by default; the blank is the deliverable.
2. **It never measures.** It reads `docs/` and `git`, and nothing else. It does
   not open a data file, run an arm, or touch the sealed slice. Where a
   question needs a number that nobody has counted, it says
   `Needs a counted look` and stops — because that look is a look, and §4 says
   every look is counted before a promotion.
3. **It copies nothing.** The twelve questions are parsed out of
   `how-we-explore.md` at run time, the way `orient.py` reads the competence
   gate. Edit the page and the worksheet changes with it (convention #8). If
   the page's numbering changes, this tool reports fewer questions rather than
   inventing them.

What it deliberately cannot do: judge an answer. `--check` reports whether a
question has a **field that owns it** in the entry, which is presence, not
adequacy — an entry can carry every field and answer nothing. Three of the
twelve (the `underpowered` floor, the one-read commitment, the competence gate)
have no field in the register's fixed format at all, and the packet says so
rather than quietly skipping them.

Report-only. Exit status is 0 whatever it finds; it is a worksheet generator,
not a gate.

Run:
    python .macro-assist/decision_packet.py H-002
    python .macro-assist/decision_packet.py H-002 --full --out packet.md
    python .macro-assist/decision_packet.py --check --all
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import record_audit as ra

HYPOTHESES = ra.RECORD_DIR / "hypotheses.md"
HOW_WE_EXPLORE = ra.DOCS_DIR / "concepts" / "how-we-explore.md"
HARNESS = Path(".macro-assist") / "explore_conditioner.py"
MODULE_DIR = Path(".macro-assist")

# Which of the register's fixed fields bear on which of §9's twelve questions.
# Data, not logic: when the register's format grows a field, this table grows a
# row and nothing else changes.
#
# Questions 8, 11 and 12 map to nothing on purpose. The fixed format has no slot
# for the `underpowered` floor, for the commitment that the read happens once
# with the result going to the KB either way, or for the competence gate — so
# they cannot be answered out of an entry, and the packet prints that instead of
# an empty quote.
FIELDS_FOR_QUESTION: dict[int, tuple[str, ...]] = {
    1: ("What was seen", "Where"),
    2: ("Target-space check",),
    3: ("What was seen", "Explore-tier looks (ledger)"),
    4: ("The prediction that is not the score", "Mechanism it would imply"),
    5: ("The prediction that is not the score",),
    6: ("The confound",),
    7: ("What would test it",),
    8: (),
    9: ("What would test it",),
    10: ("Explore-tier looks (ledger)", "Confound resolved (ledger)"),
    11: (),
    12: (),
}

_ENTRY_RE = re.compile(r"^## (H-\d{3}) — (.+?)\s*\{:\s*#[a-z0-9-]+\s*\}\s*$", re.M)
_FIELD_RE = re.compile(r"^\*\*([A-Z][^*\n]*?)[.:]\*\*", re.M)
_SECTION_9_RE = re.compile(r"^## 9\. [^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)
_GROUP_RE = re.compile(r"^\*\*(The [a-z]+)\*\*\s*$", re.M)
_QUESTION_RE = re.compile(r"^(\d{1,2})\. +\*\*(.+?)\*\*", re.M | re.S)
_ARMS_RE = re.compile(r"^(?:OPTIONAL_)?ARMS(?:\s*:[^=\n]*)?\s*=\s*\((.*?)\)", re.M | re.S)
_STATUS_RE = re.compile(r"`(draft|seen|proposed|promoted|closed)`")
_DATE_RE = re.compile(r"\*(\d{4}-\d{2}-\d{2})\*")
_REPORT_RE = re.compile(r"`(results/[^`]+)`")
_CODE_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.py)`|`([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


# ---------------------------------------------------------------------------
# the register
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    """One `## H-### — …` block of the register."""
    hid: str
    title: str
    line: int
    body: str
    status: str
    fields: dict[str, str] = field(default_factory=dict)
    field_lines: dict[str, int] = field(default_factory=dict)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def parse_entries(text: str) -> list[Entry]:
    """Every entry in the register, in page order."""
    marks = list(_ENTRY_RE.finditer(text))
    out: list[Entry] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        base = m.end()
        fields: dict[str, str] = {}
        lines: dict[str, int] = {}
        fm = list(_FIELD_RE.finditer(body))
        for j, f in enumerate(fm):
            stop = fm[j + 1].start() if j + 1 < len(fm) else len(body)
            name = f.group(1).strip()
            fields[name] = body[f.end():stop].strip()
            lines[name] = _line_of(text, base + f.start())
        status = fields.get("Status", "")
        sm = _STATUS_RE.search(status)
        out.append(Entry(
            hid=m.group(1), title=m.group(2).strip(), line=_line_of(text, m.start()),
            body=body, status=sm.group(1) if sm else "?", fields=fields, field_lines=lines,
        ))
    return out


# ---------------------------------------------------------------------------
# the twelve questions, read from the page (convention #8)
# ---------------------------------------------------------------------------

@dataclass
class Question:
    number: int
    group: str      # "The claim" / "The mechanism" / "The bar" / "The record"
    text: str       # the bold question itself
    gloss: str      # the prose under it, which is where the trap usually is


def parse_questions(text: str) -> list[Question]:
    """§9's checklist as it reads today. Empty if the section is gone or has
    been renumbered — the caller says so rather than falling back to a copy."""
    sec = _SECTION_9_RE.search(text)
    if not sec:
        return []
    body = sec.group(1)
    groups = [(m.start(), m.group(1)) for m in _GROUP_RE.finditer(body)]
    marks = list(_QUESTION_RE.finditer(body))
    out: list[Question] = []
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        group = ""
        for pos, name in groups:
            if pos < m.start():
                group = name
        whole = body[m.end():stop]
        out.append(Question(
            number=int(m.group(1)), group=group,
            text=_flatten(m.group(2)), gloss=_flatten(whole),
        ))
    return out


def _flatten(text: str) -> str:
    """Markdown → one line: links to their text, hard wraps collapsed, the
    page's horizontal rules dropped (the last question's gloss runs into them)."""
    lines = [ln for ln in text.splitlines() if not _RULE_RE.match(ln)]
    return " ".join(_LINK_RE.sub(r"\1", "\n".join(lines)).split())


# ---------------------------------------------------------------------------
# the material a question needs and nobody wants to re-assemble
# ---------------------------------------------------------------------------

def harness_arms(root: Path) -> tuple[str, ...]:
    """The explore harness's arm vocabulary — `ARMS` and `OPTIONAL_ARMS`
    together, which is §4's family size as an upper bound. Read textually, so
    this module stays TOOLING and never imports a research harness."""
    path = root / HARNESS
    if not path.is_file():
        return ()
    src = path.read_text(encoding="utf-8")
    out: list[str] = []
    for m in _ARMS_RE.finditer(src):
        out += [a for a in re.findall(r'"([^"]+)"', m.group(1)) if a not in out]
    return tuple(out)


def ledger(entry: Entry) -> tuple[list[str], list[str]]:
    """(dated looks, report paths) named in the entry's ledger fields.

    Dates are counted; **arms and configurations are not** — those are stated in
    prose that varies per entry, and a wrong count here would be worse than no
    count. The ledger block is quoted in full under question 10 for that reason.
    """
    text = "\n".join(v for k, v in entry.fields.items() if "ledger" in k.lower())
    return sorted(set(_DATE_RE.findall(text))), sorted(set(_REPORT_RE.findall(text)))


def citations(root: Path, entry: Entry) -> dict[str, list[str]]:
    """Everything the entry points at, grouped and resolved where possible."""
    body = entry.body
    out: dict[str, list[str]] = {
        "KB": sorted({f"KB-{n}" for n in ra._KB_RE.findall(body)}),
        "ADR": sorted({f"ADR-{n}" for n in ra._ADR_RE.findall(body)}),
        "WP": sorted({f"WP-{n}" for n in ra._WP_RE.findall(body)}),
    }
    code: set[str] = set()
    for whole, mod, sym in _CODE_RE.findall(body):
        if whole:
            code.add(whole)
        elif (root / MODULE_DIR / f"{mod}.py").is_file():
            code.add(f"{mod}.py::{sym}")
    resolved = []
    for c in sorted(code):
        name = c.split("::")[0]
        where = MODULE_DIR / name
        resolved.append(f"{c}  →  {where}" if (root / where).is_file() else c)
    out["code"] = resolved
    return out


def register_age(root: Path, now: datetime) -> str:
    ref = ra._resolve_ref(root, "main") or "HEAD"
    last = ra.last_changed(root, ref, str(HYPOTHESES))
    if last is None:
        return "(unreadable — not a git repository, or a shallow clone)"
    when, what = last
    days = (now - when).total_seconds() / 86400
    return f"{when:%Y-%m-%d} ({days:.0f} d ago) — {what}"


# ---------------------------------------------------------------------------
# the packet
# ---------------------------------------------------------------------------

_EXCERPT = 420


def _quote(text: str, *, full: bool) -> list[str]:
    body = text if full or len(text) <= _EXCERPT else text[:_EXCERPT].rstrip() + " …"
    return [f"> {ln}" if ln.strip() else ">" for ln in body.splitlines()]


def render_packet(
    root: Path, entry: Entry, questions: list[Question], *,
    full: bool = False, now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    dates, reports = ledger(entry)
    arms = harness_arms(root)
    cites = citations(root, entry)
    unowned = [q.number for q in questions if not FIELDS_FOR_QUESTION.get(q.number)]

    out: list[str] = [
        f"# Decision packet — {entry.hid}",
        "",
        f"**{entry.title}**",
        "",
        "| | |",
        "|---|---|",
        f"| Status | `{entry.status}` |",
        f"| Entry | `{HYPOTHESES}`:{entry.line} |",
        f"| Register last changed | {register_age(root, now)} |",
        f"| Generated | {now:%Y-%m-%d} by `decision_packet.py` — report-only |",
        "",
        "This is a worksheet, not an argument. It carries the twelve questions of",
        "[how we explore §9](../concepts/how-we-explore.md) as they read today, what",
        "the entry already says against each, and a blank. **It contains no",
        "recommendation and nothing in it was measured.** A line marked *Needs a",
        "counted look* is a look that has not happened — and when it does happen it is",
        "a look, counted in §4's ledger like any other.",
        "",
        "---",
        "",
        "## What the entry carries",
        "",
        "| Field | Line |",
        "|---|---|",
    ]
    for name, line in entry.field_lines.items():
        out.append(f"| {name} | {line} |")
    missing = sorted({f for fs in FIELDS_FOR_QUESTION.values() for f in fs} - set(entry.fields))
    out += [
        "",
        (f"**Fields a question below wants and the entry does not have:** "
         f"{', '.join(missing)}." if missing else
         "Every field a question below wants is present."),
        "",
        (f"**Questions no field owns:** {', '.join(str(n) for n in unowned)} — these are "
         "not in the entry and cannot be read out of it." if unowned else ""),
        "",
        "## The ledger, as it stands",
        "",
        f"- **Dated looks in the entry:** {len(dates)}"
        + (f" — {', '.join(dates)}" if dates else " — none recorded"),
        f"- **Reports named:** {', '.join(f'`{r}`' for r in reports) if reports else 'none'}",
        (f"- **The harness's arm vocabulary ({len(arms)}):** "
         f"{', '.join(f'`{a}`' for a in arms)} — the upper bound on family size a "
         "later bar is written against, not a count of what this entry read."
         if arms else "- **The harness's arm vocabulary:** unreadable."),
        "",
        "Arms and configurations are **not** counted from the prose — the ledger block",
        "is quoted in full under question 10 instead. Counting it is the owner's.",
        "",
        "## Read first",
        "",
    ]
    for label, items in cites.items():
        out.append(f"- **{label}:** {', '.join(items) if items else '—'}")
    out += ["", "---", "", "# The twelve questions", ""]

    if not questions:
        out += [
            "**how-we-explore §9 could not be parsed.** Its heading or numbering has",
            "changed. Read the page directly — this tool does not keep a copy.", "",
        ]

    group = None
    for q in questions:
        if q.group != group:
            group, _ = q.group, out.append(f"## {q.group}")
            out.append("")
        out += [f"### {q.number}. {q.text}", "", f"*{q.gloss}*", ""]
        names = FIELDS_FOR_QUESTION.get(q.number, ())
        present = [n for n in names if n in entry.fields]
        if not names:
            out += [
                "**No field in the register's fixed format owns this question.** It is",
                "not in the entry and cannot be quoted from it.", "",
            ]
        elif not present:
            out += [f"**The entry has no {' / '.join(names)} field.**", ""]
        else:
            for n in present:
                out += [f"**{n}** (`{HYPOTHESES}`:{entry.field_lines[n]}):", ""]
                out += _quote(entry.fields[n], full=full)
                out.append("")
        out += ["**My answer:**", "", "**Needs a counted look:**", "", "---", ""]

    return "\n".join(ln for ln in out if ln is not None) + "\n"


def render_check(entry: Entry, questions: list[Question]) -> str:
    """The readiness vector: which questions have a field that owns them.

    Presence, not adequacy. An entry can carry every field and answer nothing.
    """
    out = [f"{entry.hid}  `{entry.status}`  {entry.title}"]
    owned = 0
    for q in questions:
        names = FIELDS_FOR_QUESTION.get(q.number, ())
        present = [n for n in names if n in entry.fields]
        if not names:
            mark, why = "NO FIELD  ", "no field in the register's format owns it"
        elif not present:
            mark, why = "MISSING   ", f"wants {' / '.join(names)}"
        else:
            mark, why = "has field ", "; ".join(present)
            owned += 1
        out.append(f"  q{q.number:<2} {mark} {why}")
    if questions:
        out.append(f"  {owned}/{len(questions)} questions have a field. "
                   "Presence is not adequacy — read the packet.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the worksheet for a register entry (how-we-explore §9). "
                    "Reads docs/ and git; never measures, never recommends.")
    ap.add_argument("hid", nargs="?", help="entry id, e.g. H-002")
    ap.add_argument("--all", action="store_true", help="every entry (with --check)")
    ap.add_argument("--check", action="store_true",
                    help="print the readiness vector instead of the packet")
    ap.add_argument("--full", action="store_true",
                    help="quote fields in full rather than excerpting them")
    ap.add_argument("--out", type=Path, help="write the packet here instead of stdout")
    ap.add_argument("--root", type=Path, default=ra._repo_root(), help="repo root")
    args = ap.parse_args(argv)
    root = args.root.resolve()

    reg = root / HYPOTHESES
    hwe = root / HOW_WE_EXPLORE
    for p in (reg, hwe):
        if not p.is_file():
            ap.error(f"not found: {p}")

    entries = parse_entries(reg.read_text(encoding="utf-8"))
    questions = parse_questions(hwe.read_text(encoding="utf-8"))
    if not entries:
        ap.error(f"no entries parsed from {HYPOTHESES} — has its heading format changed?")

    if args.check and args.all:
        print("\n\n".join(render_check(e, questions) for e in entries))
        return 0
    if not args.hid:
        ap.error("give an entry id, or --check --all. "
                 f"The register holds: {', '.join(e.hid for e in entries)}")

    wanted = args.hid.upper()
    hit = next((e for e in entries if e.hid == wanted), None)
    if hit is None:
        ap.error(f"{wanted} is not in the register. It holds: "
                 f"{', '.join(e.hid for e in entries)}")

    if args.check:
        print(render_check(hit, questions))
        return 0

    text = render_packet(root, hit, questions, full=args.full)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"{args.out}  ({len(text.splitlines())} lines)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
