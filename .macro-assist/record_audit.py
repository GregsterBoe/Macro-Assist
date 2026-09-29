"""
record_audit.py — the record layer's audit (Phase 24, docs/record/roadmap.md).

Everywhere a claim could be inflated, this project built a mechanism rather
than a request: `verdict(sealed=False)` cannot return a pass, the boundary test
fails on an unclassified module. The record layer — workflows, the status
board, the roadmap, the ADRs — ran on good intentions. This script is where
those intentions get a detector. It reads; it never repairs.

Checks, one per work package. Each is a function taking the repo root and
returning Findings; `audit()` runs them all.

  workflow-orphans   WP-24.A   Every file in .github/workflows/ is one of:
                               the entry point, a `needs:`-ordered stage it
                               calls, dispatch-only, CI (push / pull_request),
                               or pinned below as soft-killed. Anything else
                               is an orphan — ADR-0013 with a detector.
  schedule-table     WP-24.A   The external cron's schedule table in
                               operations.md names only pipeline.yml. The
                               external service is outside the repo; its
                               declaration is not, and the weekly refit's own
                               Sunday slot sat in that table until 2026-09-11.
  artifact-liveness  WP-24.B   Every live track's output artifact, pinned in
                               ARTIFACTS with the branch it lands on and the
                               cadence it is owed, has a last-changed commit
                               younger than that cadence. The date comes from
                               git, never mtime — a fresh clone rewrites
                               mtimes and would pass vacuously; a shallow
                               clone is refused for the same reason.
  referential-       WP-24.C   Every KB-###, ADR-#### and WP-##.x cited under
  integrity                    docs/ (and CLAUDE.md) resolves; ADR numbering
                               is contiguous, unique and never deleted from
                               history (convention #11); the inbox holds one
                               item per number and none that resolved.md also
                               holds; every `todo.md #N` / `resolved.md #N`
                               pointer lands. `mkdocs build --strict` covers
                               links; this covers the identifiers that are
                               not links. Two pins, held exactly:
                               RESERVED_KB_NUMBERS and KNOWN_ITEM_COLLISIONS.
  contradictions     WP-24.D   Every phase's status is one class (open /
                               dormant / closed, read from the record's own
                               markers) wherever the record states it: the
                               board, the roadmap's heading and phase table,
                               CLAUDE.md's Current-state table; and that
                               table's version row is versions.py's. Prints
                               the disagreeing pair and never picks a side —
                               CLAUDE.md says who wins. Red with a pin
                               (resolved #23): KNOWN_CONTRADICTIONS names the
                               pair against an open todo.md item, and a pin
                               whose sources agree again is itself red.
  ages               WP-24.E   Not a check: days since each open todo.md
                               item and each board row was last edited, per
                               line from `git blame`, printed oldest first.
                               No threshold, never red — an old item breaks
                               no rule (resolved #23). The hand-written
                               `Last reviewed:` line, computed.
  adr-revisit        WP-24.F   Every ADR that is not superseded carries a
                               non-empty `## Would we revisit it?` — part 4
                               of the page shape, enforced (resolved #24); a
                               reasoned "No." is an answer. Report-only: a
                               revisit section citing a todo.md item, WP, KB
                               entry or Phase whose record heading is younger
                               than the section — resolved, closed or landed
                               since it was last edited — is printed as
                               "cited condition may have fired". Prose
                               conditions are not read.

The audit's own checks — ADR-0022's mechanisms that git can settle, so the
auditor model is not trusted with them (WP-25.B–C, Phase 25). Each reads the
register and, where it needs one, the output branch.

  approval-stamp     WP-25.B   A `promoted` entry has a CI audit record whose
                               entry_fingerprint is its current stamped text
                               (`decision_packet.stamped_text`: the entry less
                               what the promotion and the sealed read write),
                               whose newest such record found nothing
                               blocking, and whose model / effort /
                               instructions / canary set a passing canary
                               suite certifies.
  no-grinding        WP-25.B   A third CI audit after two rejections is red,
                               pass or not, until the entry closes or the
                               owner's decision is pinned in
                               OWNER_RESUBMISSIONS (held exactly).
  instruction-freeze WP-25.B   No commit changes the auditor's instructions
                               and the status or stamped text of an entry that
                               is or was ever promoted.
  bar-before-result  WP-25.B   An entry's bar (`decision_packet.bar_text`: the
                               entry less status, audit record and ledgers)
                               last changed before the first commit of the
                               report its `Sealed read (ledger)` names.
  receipts           WP-25.B   Every dated look in an open entry's ledger has
                               a run the harness logged that day
                               (explore_conditioner/runs.jsonl on output). The
                               looks before the log are pinned exactly in
                               LOOKS_BEFORE_RECEIPTS. Report-only: a logged run
                               no ledger dates, which is an uncounted look.
  audit-record-field WP-25.C   An entry's `Audit record` field is exactly what
                               CI's audit records on output render to
                               (`decision_packet.audit_record_paragraph`), and
                               an entry CI never audited has none — so every
                               submission shows in the entry as a counted look,
                               and none is written by hand.

The sealed read's checks (WP-23.B). Each reads CI's sealed-read records on the
output branch (`sealed_reads/<hid>/`), which `sealed_runner.py` writes in
`sealed_read.yml`'s key job — a claim before the read, a result after it.

  sealed-reads       WP-23.B   A class's slice is claimed once (resolved.md
                               #19: the read burns it for the class); every
                               claim has a result, or it is a lost read; a
                               result landed after its claim; and the class's
                               bar (`bar_fingerprint`: class_bars.py less the
                               CLI and the other classes' bars, plus the
                               sources of what it imports) is what it was when
                               the slice was claimed. Pins: VOIDED_CLAIMS,
                               BAR_EDITS_AFTER_READ, each the owner's, held
                               exactly.
  sealed-read-field  WP-23.B   An entry's `Sealed read (ledger)` is exactly
                               what those records render to
                               (`decision_packet.sealed_read_paragraph`), and
                               an entry CI never read has none.

The two workflow checks and the liveness check are a pair. 24.A catches a stage
the repo cannot reach; it cannot see a dispatch-only workflow whose *external*
caller has stopped calling — that is what froze the refit for eleven days
(2026-08-31 → 09-11: the cron service was rebuilt without its call, the table
still listed it). 24.B catches that shape from the other end: a reachable stage
that produces nothing. At the 8-day threshold it would have gone red on
2026-09-08, day nine.

A finding is `red` (exit 1) or report-only (printed, never fails — resolved
#23 draws the line: red is for a claim the repo makes twice, differently;
report-only is for a number with no threshold). WP-24.A has only red findings;
24.C's one report-only is a `todo.md #N` pointer whose item has since resolved —
the pointer still lands, in the other file. 24.D's is a pinned contradiction:
still printed, so the pair stays visible while its todo item is open. 24.E
returns a table (`ages()`), not findings; the runner prints it before them and
`--now` replays it the same way. 24.F's report-only is a revisit condition whose
cited referent closed after the section was last edited — the page has not been
re-read since; editing it (even to say "and it did not fire") clears the line.

Run:
    python .macro-assist/record_audit.py             # exit 1 on any red finding
    python .macro-assist/record_audit.py --root PATH
    python .macro-assist/record_audit.py --now 2026-09-08   # artifact and record ages, and ADR conditions, as of a date
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------

# Workflows that keep a `workflow_call` trigger nothing in pipeline.yml calls,
# on purpose: soft-killed arms (ADR-0015) whose trigger stays so restoring the
# arm is putting the job back in pipeline.yml and nothing else. Held exactly,
# the KNOWN_LEAKS way (product_surface.py): a callable workflow the pipeline
# does not reach fails unless it is here, AND a pin fails once it is no longer
# needed — the file is gone, is wired back in as a stage, or has dropped its
# `workflow_call`. So the escape hatch cannot rot.
SOFT_KILLED_WORKFLOWS: frozenset[str] = frozenset({
    "exo_weekly_emit.yml",   # Phase 19 emitter — was stage 3 until 2026-09-04
    "kimi_arm_daily.yml",    # Kimi ensemble arm — was stage 4 until 2026-09-04
})

PIPELINE = "pipeline.yml"   # the one entry point (ADR-0013); the only file that may carry `schedule:`

# Trigger vocabulary the audit understands. Anything outside it is red — not
# because it is wrong, but because it has to be classified deliberately, the
# way a new module has to be given a tier.
_SCHEDULE = "schedule"
_CALL = "workflow_call"
_DISPATCH = "workflow_dispatch"
_CI = frozenset({"push", "pull_request"})
_KNOWN_TRIGGERS = frozenset({_SCHEDULE, _CALL, _DISPATCH}) | _CI


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    message: str
    red: bool = True

    def __str__(self) -> str:
        tag = "RED " if self.red else "note"
        return f"{tag}  {self.check}  {self.subject} — {self.message}"


# ---------------------------------------------------------------------------
# Workflow parsing
# ---------------------------------------------------------------------------

def _load_workflow(path: Path) -> dict | None:
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _triggers(wf: dict) -> set[str]:
    # PyYAML reads the bare key `on:` as the boolean True (YAML 1.1).
    on = wf.get("on", wf.get(True))
    if on is None:
        return set()
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    if isinstance(on, dict):
        return set(on)
    return set()


def _stage_files(pipeline: dict) -> dict[str, str]:
    """job name → the workflow file it `uses:`, for every reusable-workflow job."""
    out: dict[str, str] = {}
    for job, spec in (pipeline.get("jobs") or {}).items():
        uses = (spec or {}).get("uses") if isinstance(spec, dict) else None
        if isinstance(uses, str) and uses.startswith("./.github/workflows/"):
            out[job] = uses.rsplit("/", 1)[-1]
    return out


# ---------------------------------------------------------------------------
# WP-24.A — workflow orphans
# ---------------------------------------------------------------------------

def classify_workflows(
    root: Path,
    soft_killed: frozenset[str] | None = None,
) -> tuple[dict[str, str], list[Finding]]:
    """Return (file → class, findings). Classes: entry-point, stage,
    soft-killed, dispatch-only, ci, orphan."""
    if soft_killed is None:
        soft_killed = SOFT_KILLED_WORKFLOWS
    check = "workflow-orphans"
    wf_dir = root / ".github" / "workflows"
    files = sorted(p for p in wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    names = {p.name for p in files}
    classes: dict[str, str] = {}
    findings: list[Finding] = []

    def red(subject: str, msg: str) -> None:
        findings.append(Finding(check, subject, msg))

    pipeline_path = wf_dir / PIPELINE
    pipeline = _load_workflow(pipeline_path) if pipeline_path.exists() else None
    if pipeline is None:
        red(PIPELINE, "missing or unparsable — there is no entry point to audit against (ADR-0013)")
        return classes, findings

    stages = _stage_files(pipeline)
    wired: set[str] = set()
    for job, target in stages.items():
        if target not in names:
            red(PIPELINE, f"job `{job}` uses ./.github/workflows/{target}, which does not exist")
            continue
        wired.add(target)
        spec = pipeline["jobs"][job]
        if not spec.get("needs"):
            red(PIPELINE, f"job `{job}` calls {target} with no `needs:` — a stage nothing orders is a cron offset in disguise")

    for path in files:
        name = path.name
        wf = _load_workflow(path)
        if wf is None:
            red(name, "unparsable YAML")
            classes[name] = "orphan"
            continue
        trig = _triggers(wf)
        unknown = trig - _KNOWN_TRIGGERS
        if unknown:
            red(name, f"trigger(s) {sorted(unknown)} are outside the audit's vocabulary — classify deliberately in record_audit.py")
            classes[name] = "orphan"
            continue
        if not trig:
            red(name, "no `on:` triggers at all")
            classes[name] = "orphan"
            continue

        if name == PIPELINE:
            classes[name] = "entry-point"
            continue
        if _SCHEDULE in trig:
            red(name, "carries its own `schedule:` — a scheduled thing is a stage of pipeline.yml, not a cron entry (ADR-0013)")
            classes[name] = "orphan"
            continue
        if name in wired:
            classes[name] = "stage"
            if _CALL not in trig:
                red(name, "called as a pipeline stage but has no `workflow_call` trigger")
            if name in soft_killed:
                red(name, "wired into pipeline.yml again but still pinned as soft-killed — remove it from SOFT_KILLED_WORKFLOWS")
            continue
        if _CALL in trig:
            if name in soft_killed:
                classes[name] = "soft-killed"
            else:
                red(name, "has `workflow_call` but no pipeline.yml stage calls it and it is not pinned as soft-killed (ADR-0015) — the frozen-refit shape")
                classes[name] = "orphan"
            continue
        if trig & _CI:
            classes[name] = "ci"
        else:
            classes[name] = "dispatch-only"
        if name in soft_killed:
            red(name, "pinned as soft-killed but has no `workflow_call` — the pin is no longer needed, remove it")

    for name in sorted(soft_killed - names):
        red(name, "pinned as soft-killed but no such workflow file — remove the pin")

    return classes, findings


def check_workflow_orphans(root: Path) -> list[Finding]:
    return classify_workflows(root)[1]


# ---------------------------------------------------------------------------
# WP-24.A — the external schedule, as declared
# ---------------------------------------------------------------------------

OPERATIONS_MD = Path("docs") / "reference" / "operations.md"
_SCHEDULE_HEADING = "### The schedule"
_TICK_RE = re.compile(r"`([^`]+)`")


def schedule_table_calls(root: Path) -> list[str] | None:
    """The `Call` column of operations.md's schedule table, first backticked
    token per row; None if the section or its table is not there."""
    path = root / OPERATIONS_MD
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    try:
        start = lines.index(_SCHEDULE_HEADING) + 1
    except ValueError:
        return None
    rows: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", ":", " "} or cells[0] == "Slot":
            continue
        m = _TICK_RE.search(cells[-1])
        rows.append(m.group(1) if m else cells[-1])
    return rows or None


def check_schedule_table(root: Path) -> list[Finding]:
    check = "schedule-table"
    calls = schedule_table_calls(root)
    if calls is None:
        return [Finding(check, str(OPERATIONS_MD),
                        f"no table under `{_SCHEDULE_HEADING}` — the audit reads the external schedule from there")]
    return [
        Finding(check, str(OPERATIONS_MD),
                f"a cron slot calls `{call}` — a scheduled thing is a stage of {PIPELINE}, not a cron entry (ADR-0013)")
        for call in calls if call != PIPELINE
    ]


# ---------------------------------------------------------------------------
# WP-24.B — artifact liveness
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Artifact:
    """One live track's output: where it lands, and how often it is owed."""
    path: str            # git pathspec, relative to the branch root
    branch: str          # "main" or "output" — the branch the stage pushes to
    max_age_days: float  # red once the last-changed commit is older than this
    stage: str           # who writes it, for the message
    # What to say when the path has NEVER been written. The default reading of
    # that — "the registry entry or the stage is wrong" — is right for an entry
    # that has drifted off a live track, and wrong for one deliberately armed
    # ahead of its first run, where nothing has landed *yet* and the entry is
    # the reminder. Set this and the red names the actual fix.
    awaiting: str | None = None


# The registry. One entry per live track on the board; the threshold is the
# cadence plus one day of grace, so a run that is merely late does not fail
# and a run that did not happen does. Ages are read from the *branch the stage
# pushes to* (origin/<branch> when fetched, the local branch otherwise), not
# from HEAD — a feature branch cut two weeks ago does not carry the refits
# that landed since, and must not fail for it.
#
# A track that stops is a red here until its entry goes, deliberately — the
# same shape as SOFT_KILLED_WORKFLOWS. The first one due: accuracy_summary.json
# is rewritten weekly by `summarize_accuracy.py` (its `generated_at` moves even
# when the directional numbers no longer do), so it keeps landing after the
# directional scorer's closure banner ~2026-10-02; if that step is ever
# retired, retire the entry with it.
ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(".macro-assist/data/conditional_distributions.json", "main", 8,
             "stage 5 · weekly refit, Mondays"),
    Artifact(".macro-assist/data/accuracy_summary.json", "main", 8,
             "stage 3 · weekly scoring, Mondays"),
    Artifact("dist_scores_summary.json", "output", 8,
             "stage 3 · weekly scoring, Mondays — the Phase 22 record"),
    # the note itself, any month directory; Friday → Tuesday is four days, so
    # one missed weekday can slip through and two cannot
    Artifact(":(glob)*/*-macro.md", "output", 4,
             "stage 2 · daily note, Mon–Fri"),
    # WP-24.B turned on the schedule itself (todo #27). Every run leaves
    # `schedule/last-<source>.txt` (pipeline.yml, job `heartbeat`), so a cron
    # slot that stops arriving is an ordinary stale artifact and reads as one.
    # Same 4 days as the note, for the same reason: Friday → Tuesday is four
    # days, so one missed weekday can slip through and two cannot.
    #
    # Both landed 2026-09-23, the first day the caller ran on UTC with both jobs
    # configured — `cron-catchup` for the first time ever (todo #27, closed).
    # Their `awaiting` messages are gone with the condition they described: from
    # here a missing file means the entry or the stage is wrong, which is the
    # default reading and the right one.
    Artifact("schedule/last-cron-primary.txt", "output", 4,
             "the external caller's 06:23 slot"),
    Artifact("schedule/last-cron-catchup.txt", "output", 4,
             "the external caller's 10:47 slot"),
)


def _git(root: Path, *args: str) -> str | None:
    """stdout of a git command in `root`, None on any failure."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _resolve_ref(root: Path, branch: str) -> str | None:
    """`origin/<branch>` if it exists (what the bots push to), else the local
    branch, else None."""
    for cand in (f"origin/{branch}", branch):
        if _git(root, "rev-parse", "--verify", "-q", f"{cand}^{{commit}}") is not None:
            return cand
    return None


def last_changed(
    root: Path, ref: str, pathspec: str, *, until: datetime | None = None,
) -> tuple[datetime, str] | None:
    """(committer date, short hash + subject) of the last commit on `ref` that
    touched `pathspec` — no later than `until`, so `--now` replays history
    rather than comparing today's commit with an earlier clock. None if nothing
    on that ref ever did."""
    args = ["log", "-1", "--format=%cI%x1f%h %s"]
    if until is not None:
        args.append(f"--until={until.isoformat()}")
    out = _git(root, *args, ref, "--", pathspec)
    if not out:
        return None
    stamp, _, what = out.partition("\x1f")
    return datetime.fromisoformat(stamp), what


def check_artifact_liveness(
    root: Path,
    *,
    now: datetime | None = None,
    artifacts: tuple[Artifact, ...] | None = None,
) -> list[Finding]:
    check = "artifact-liveness"
    if now is None:
        now = datetime.now(timezone.utc)
    if artifacts is None:
        artifacts = ARTIFACTS
    findings: list[Finding] = []

    def red(subject: str, msg: str) -> None:
        findings.append(Finding(check, subject, msg))

    if _git(root, "rev-parse", "--git-dir") is None:
        red(str(root), "not a git repository — ages are read from git, and there is none to read")
        return findings
    if _git(root, "rev-parse", "--is-shallow-repository") == "true":
        red(str(root), "shallow clone — every artifact would look as old as the clone boundary and pass vacuously "
                       "(record_audit.yml checks out with fetch-depth: 0)")
        return findings

    for art in artifacts:
        subject = f"{art.branch}:{art.path}"
        ref = _resolve_ref(root, art.branch)
        if ref is None:
            red(subject, f"branch `{art.branch}` is not available here — `git fetch origin {art.branch}` and rerun")
            continue
        hit = last_changed(root, ref, art.path, until=now)
        if hit is None:
            red(subject, f"nothing on `{ref}` had written it by {now:%Y-%m-%d} — "
                         + (art.awaiting or "the registry entry or the stage is wrong"))
            continue
        when, what = hit
        age = now - when
        days = age.total_seconds() / 86400
        if age > timedelta(days=art.max_age_days):
            red(subject, f"last changed {days:.1f} days ago on `{ref}` ({what}) — owed every {art.max_age_days:g} days "
                         f"by {art.stage}; the stage is reachable and producing nothing")

    return findings


# ---------------------------------------------------------------------------
# WP-24.C — referential integrity
# ---------------------------------------------------------------------------

DOCS_DIR = Path("docs")
RECORD_DIR = DOCS_DIR / "record"
DECISIONS_DIR = DOCS_DIR / "decisions"
KNOWLEDGE_BASE = RECORD_DIR / "knowledge-base.md"
ROADMAPS = (RECORD_DIR / "roadmap.md", RECORD_DIR / "roadmap-archive.md")
TODO = RECORD_DIR / "todo.md"
RESOLVED = RECORD_DIR / "resolved.md"
# CLAUDE.md is read alongside docs/: its Current-state table is held to the
# board by rule, and it cites the same identifiers.
EXTRA_DOCS = (Path("CLAUDE.md"),)

# A KB number that was reserved and never written stays a dangling mention in
# the KB's own prose; it is pinned rather than silently allowed, and held
# exactly. 008 was reserved for the loosened-vs-baseline A/B that the cut made
# moot (knowledge-base.md, under KB-011).
RESERVED_KB_NUMBERS: frozenset[str] = frozenset({"008"})

# An inbox number that heads an open item in todo.md *and* a resolved one in
# resolved.md. #7 was numbered twice while the inbox numbered per section
# (Phase 22's open decision and the carried accuracy finding); the carried one
# closed 2026-09-14 under "#7 (carried)" and the maintenance log calls the
# duplicate gone, so the pin records that reading. Held exactly: when the
# open #7 closes, this pin is red until it is removed.
KNOWN_ITEM_COLLISIONS: frozenset[str] = frozenset({"7"})

_KB_RE = re.compile(r"\bKB-(\d{3})\b")
_KB_HEADING_RE = re.compile(r"^##+ +KB-(\d{3})\b", re.M)
_ADR_RE = re.compile(r"\bADR-(\d{4})\b")
_ADR_FILE_RE = re.compile(r"^ADR-(\d{4})-.*\.md$")
_WP_RE = re.compile(r"\bWP-(\d{1,2}\.[A-Za-z0-9]+)")
_ITEM_HEADING_RE = re.compile(r"^### [^\n]*?#(\d+[a-z]?)\b", re.M)
_RESOLVED_HEADING_RE = re.compile(r"^### (?:RESOLVED|DONE) [^\n]*?#(\d+[a-z]?)\b", re.M)
# "`todo.md` #17", "todo.md (#12", "[`resolved.md`](resolved.md) #15",
# "`resolved.md`, #18", "resolved.md: #19" — the pointer forms the record uses
_TODO_REF_RE = re.compile(r"`?todo\.md`?(?:\]\(todo\.md\))?[\s,:(*]{0,4}#(\d+[a-z]?)\b")
_RESOLVED_REF_RE = re.compile(r"`?resolved\.md`?(?:\]\(resolved\.md\))?[\s,:(*]{0,4}#(\d+[a-z]?)\b")


def _record_docs(root: Path) -> list[Path]:
    docs = sorted((root / DOCS_DIR).rglob("*.md")) if (root / DOCS_DIR).is_dir() else []
    return docs + [root / p for p in EXTRA_DOCS if (root / p).is_file()]


def _adr_files(root: Path) -> dict[str, list[str]]:
    """ADR number → the file names that carry it (more than one is a dupe)."""
    out: dict[str, list[str]] = {}
    if (root / DECISIONS_DIR).is_dir():
        for p in sorted((root / DECISIONS_DIR).iterdir()):
            m = _ADR_FILE_RE.match(p.name)
            if m:
                out.setdefault(m.group(1), []).append(p.name)
    return out


def _deleted_adrs(root: Path) -> dict[str, str]:
    """ADR number → short hash of a commit in HEAD's history that removed a
    file carrying it. `--no-renames` so a renumbering shows as a deletion of
    the old number; a slug rename keeps the number and is not reported."""
    log = _git(root, "log", "--diff-filter=D", "--no-renames", "--format=%x1e%h", "--name-only",
               "--", f"{DECISIONS_DIR.as_posix()}/ADR-*.md")
    out: dict[str, str] = {}
    for block in (log or "").split("\x1e"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        sha, names = lines[0], lines[1:]
        for name in names:
            m = _ADR_FILE_RE.match(Path(name).name)
            if m:
                out.setdefault(m.group(1), sha)
    return out


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def check_referential_integrity(root: Path) -> list[Finding]:
    """Every KB-###, ADR-#### and WP-##.x cited under docs/ (and CLAUDE.md)
    resolves; ADR numbering is contiguous, unique and never deleted; the inbox
    and its resolved list do not both hold one number, and every `todo.md #N`
    / `resolved.md #N` pointer lands. `mkdocs build --strict` covers links;
    this covers the identifiers that are not links."""
    check = "referential-integrity"
    out: list[Finding] = []

    kb_text = (root / KNOWLEDGE_BASE).read_text(encoding="utf-8") if (root / KNOWLEDGE_BASE).is_file() else ""
    kb_defined = set(_KB_HEADING_RE.findall(kb_text))
    roadmap_text = "\n".join((root / p).read_text(encoding="utf-8") for p in ROADMAPS if (root / p).is_file())
    wp_defined = set(_WP_RE.findall(roadmap_text))
    adr_files = _adr_files(root)
    todo_text = (root / TODO).read_text(encoding="utf-8") if (root / TODO).is_file() else ""
    resolved_text = (root / RESOLVED).read_text(encoding="utf-8") if (root / RESOLVED).is_file() else ""
    todo_headings = _ITEM_HEADING_RE.findall(todo_text)
    todo_open = set(todo_headings)
    resolved_items = set(_RESOLVED_HEADING_RE.findall(resolved_text))

    # -- one number, one open item. The inbox numbered per section until
    #    2026-09-11 and carried two open #7s from 09-08 to 09-13.
    for n in sorted({n for n in todo_headings if todo_headings.count(n) > 1}, key=lambda s: (len(s), s)):
        out.append(Finding(check, TODO.as_posix(),
                           f"#{n} heads {todo_headings.count(n)} open items in todo.md — one number, one item"))

    # -- ADR numbering: contiguous from 0001, one file per number, never deleted
    if adr_files:
        numbers = sorted(int(n) for n in adr_files)
        for n in range(1, numbers[-1] + 1):
            if f"{n:04d}" not in adr_files:
                out.append(Finding(check, DECISIONS_DIR.as_posix(),
                                   f"ADR numbering has a gap at ADR-{n:04d} — convention #11 (sequential, never renumber)"))
        for n, names in sorted(adr_files.items()):
            if len(names) > 1:
                out.append(Finding(check, DECISIONS_DIR.as_posix(),
                                   f"ADR-{n} has {len(names)} files: {', '.join(names)}"))
    for n, sha in sorted(_deleted_adrs(root).items()):
        if n not in adr_files:
            out.append(Finding(check, DECISIONS_DIR.as_posix(),
                               f"ADR-{n} was deleted in history ({sha}) and no file carries the number now — "
                               f"convention #11 (supersede, never delete)"))

    # -- pins, held exactly
    for n in sorted(RESERVED_KB_NUMBERS):
        if n in kb_defined:
            out.append(Finding(check, KNOWLEDGE_BASE.as_posix(),
                               f"RESERVED_KB_NUMBERS pins KB-{n} but the KB now defines it — remove the pin"))
    for n in sorted(KNOWN_ITEM_COLLISIONS, key=lambda s: (len(s), s)):
        if not (n in todo_open and n in resolved_items):
            out.append(Finding(check, TODO.as_posix(),
                               f"KNOWN_ITEM_COLLISIONS pins #{n} but it no longer heads both an open and a "
                               f"resolved item — remove the pin"))
    for n in sorted(todo_open & resolved_items - KNOWN_ITEM_COLLISIONS, key=lambda s: (len(s), s)):
        out.append(Finding(check, TODO.as_posix(),
                           f"#{n} heads an open item in todo.md and a resolved one in resolved.md — "
                           f"one number, two items; the single inbox cannot be both"))

    # -- citations
    for path in _record_docs(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        stale: list[str] = []
        for m in _KB_RE.finditer(text):
            n = m.group(1)
            if n not in kb_defined and n not in RESERVED_KB_NUMBERS:
                out.append(Finding(check, f"{rel}:{_line_of(text, m.start())}",
                                   f"KB-{n} is cited and knowledge-base.md has no such entry"))
        for m in _ADR_RE.finditer(text):
            n = m.group(1)
            if n not in adr_files:
                out.append(Finding(check, f"{rel}:{_line_of(text, m.start())}",
                                   f"ADR-{n} is cited and docs/decisions/ has no such file"))
        if path not in (root / p for p in ROADMAPS):
            for m in _WP_RE.finditer(text):
                n = m.group(1)
                if n not in wp_defined:
                    out.append(Finding(check, f"{rel}:{_line_of(text, m.start())}",
                                       f"WP-{n} is cited and neither roadmap.md nor roadmap-archive.md names it"))
        for m in _TODO_REF_RE.finditer(text):
            n = m.group(1)
            if n in todo_open:
                continue
            if n in resolved_items:
                stale.append(f"#{n}")
            else:
                out.append(Finding(check, f"{rel}:{_line_of(text, m.start())}",
                                   f"todo.md #{n} heads no item in todo.md or resolved.md"))
        for m in _RESOLVED_REF_RE.finditer(text):
            n = m.group(1)
            if n not in resolved_items:
                out.append(Finding(check, f"{rel}:{_line_of(text, m.start())}",
                                   f"resolved.md #{n} heads no resolved item"))
        if stale and path != root / RESOLVED:
            # the pointer still lands — the item exists, in the other file —
            # so this is not a broken reference; it is printed so the next
            # housekeeping pass can redirect it
            uniq = sorted(set(stale), key=lambda s: (len(s), s))
            out.append(Finding(check, rel,
                               f"cites todo.md {', '.join(uniq)} — resolved since; the pointer now lands in resolved.md",
                               red=False))
    return out


# ---------------------------------------------------------------------------
# WP-24.D — contradiction surfacing
# ---------------------------------------------------------------------------

BOARD = RECORD_DIR / "active-experiments.md"
ROADMAP = RECORD_DIR / "roadmap.md"
VERSIONS_PY = Path(".macro-assist") / "versions.py"

# A phase whose status the board and the roadmap (or CLAUDE.md) state
# differently, on purpose, for now. Keyed by the subject the finding prints
# ("Phase 24"), valued by the open todo.md item that carries the disagreement
# — resolved #23: the pin names the pair and must appear in todo.md. Held
# exactly: a pin whose sources agree again, or whose item is not open, is red.
# The audit prints the pair either way and takes no side — CLAUDE.md says who
# wins; red only insists that someone applies it.
KNOWN_CONTRADICTIONS: dict[str, str] = {}

# The status vocabulary is the record's own markers. Everything the check
# compares is the coarse class; "🟢 SHIPPED" and "🟡 IN PROGRESS" are one
# claim worded twice, "🟡 IN PROGRESS" and "⏸ Draft" are two claims.
_OPEN, _DORMANT, _CLOSED = "open", "dormant", "closed"
_MARKER_CLASS = {"🟢": _OPEN, "🟡": _OPEN, "🔍": _OPEN,
                 "⏸": _DORMANT,
                 "✅": _CLOSED, "❌": _CLOSED}
_MARKER_RE = re.compile("[" + "".join(_MARKER_CLASS) + "]")
_PHASE_RE = re.compile(r"\bPhase (\d+)\b")
# CLAUDE.md's Current-state table is prose: the class is the status word in
# the clause that follows "Phase N" — up to the next ";", ".", "|" or "Phase
# N", with parenthesised and backticked spans removed first (they hold asides
# and identifiers, not the row's claim). No such word means the row names the
# phase as current.
_ASIDE_RE = re.compile(r"\([^()\n]*\)|`[^`\n]*`")
_CLAUSE_SPLIT_RE = re.compile(r"[;|]|\.(?!\d)|(?=\bPhase \d)")
_CLOSED_WORDS = re.compile(r"\b(?:closed|complete|completed|resolved|done)\b", re.I)
_DORMANT_WORDS = re.compile(r"\b(?:dormant|paused|soft-killed|draft|drafted|queued|backlog|winding down)\b", re.I)
_BOARD_HEADING_RE = re.compile(r"^### (.*)$", re.M)
_BOARD_BULLET_RE = re.compile(r"^- \*\*((?:[^*\n]|\*(?!\*))+)\*\*([^\n]*)$", re.M)
_ROADMAP_PHASE_HEADING_RE = re.compile(r"^## [^\n]*\(Phase (\d+)\)[^\n]*$", re.M)
_ROADMAP_TABLE_ROW_RE = re.compile(r"^\| (\d+) \|[^\n|]*\|([^\n|]*)\|", re.M)
_CURRENT_STATE_RE = re.compile(r"^## Current state\n(.*?)(?=^## |\Z)", re.M | re.S)
_ROW_LABEL_RE = re.compile(r"\| \*\*([^*\n]+)\*\* \|")
_VERSION_ROW_RE = re.compile(r"^\| \*\*Version\*\* \|[^\n]*?\b(v\d+\.\d+)\b", re.M)
_PIPELINE_VERSION_RE = re.compile(r'^PIPELINE_VERSION(?:\s*:\s*str)?\s*=\s*"(v\d+\.\d+)"', re.M)


@dataclass(frozen=True)
class _Claim:
    where: str      # "docs/record/roadmap.md:53"
    cls: str        # _OPEN / _DORMANT / _CLOSED
    text: str       # the status as written, for the printout


def _status_text(line: str, start: int) -> str:
    tail = line[start:].strip().rstrip("|").strip()
    return tail if len(tail) <= 90 else tail[:87].rstrip() + "…"


def _marker_claim(rel: str, text: str, line_start: int, id_end: int, line: str) -> _Claim | None:
    m = _MARKER_RE.search(line, id_end)
    if not m:
        return None
    return _Claim(f"{rel}:{_line_of(text, line_start)}", _MARKER_CLASS[m.group()], _status_text(line, m.start()))


def board_claims(root: Path, *, rev: str | None = None) -> dict[str, list[_Claim]]:
    """Phase → status claims on the board: every `### …` heading and every
    `- **…**` bullet whose bold span names a Phase, classed by the first
    status marker after the name. A heading or bullet with no marker claims
    nothing. At `rev` when given (24.F replays), else the working tree."""
    text = _text_at(root, BOARD.as_posix(), rev)
    if text is None:
        return {}
    rel = BOARD.as_posix()
    out: dict[str, list[_Claim]] = {}
    for m in _BOARD_HEADING_RE.finditer(text):
        p = _PHASE_RE.search(m.group(1))
        if p:
            c = _marker_claim(rel, text, m.start(), 4 + p.end(), m.group(0))
            if c:
                out.setdefault(p.group(1), []).append(c)
    for m in _BOARD_BULLET_RE.finditer(text):
        p = _PHASE_RE.search(m.group(1))
        if p:
            c = _marker_claim(rel, text, m.start(), 4 + p.end(), m.group(0))
            if c:
                out.setdefault(p.group(1), []).append(c)
    return out


def roadmap_claims(root: Path, *, rev: str | None = None) -> dict[str, list[_Claim]]:
    """Phase → status claims in roadmap.md: the phase's `## … (Phase N) …`
    heading and its row in the phase table, each classed by its first marker."""
    text = _text_at(root, ROADMAP.as_posix(), rev)
    if text is None:
        return {}
    rel = ROADMAP.as_posix()
    out: dict[str, list[_Claim]] = {}
    for m in _ROADMAP_PHASE_HEADING_RE.finditer(text):
        c = _marker_claim(rel, text, m.start(), m.end(1) - m.start(), m.group(0))
        if c:
            out.setdefault(m.group(1), []).append(c)
    for m in _ROADMAP_TABLE_ROW_RE.finditer(text):
        c = _marker_claim(rel, text, m.start(), m.start(2) - m.start(), m.group(0))
        if c:
            out.setdefault(m.group(1), []).append(c)
    return out


def claude_md_claims(root: Path) -> dict[str, list[_Claim]]:
    """Phase → status claims in CLAUDE.md's Current-state table, by the
    clause rule above."""
    path = root / EXTRA_DOCS[0]
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    sec = _CURRENT_STATE_RE.search(text)
    if not sec:
        return {}
    out: dict[str, list[_Claim]] = {}
    for m in _PHASE_RE.finditer(text, sec.start(1), sec.end(1)):
        line_end = text.find("\n", m.end())
        line_end = len(text) if line_end < 0 else line_end
        clause = _CLAUSE_SPLIT_RE.split(_ASIDE_RE.sub(" ", text[m.end():line_end]), maxsplit=1)[0]
        if _CLOSED_WORDS.search(clause):
            cls = _CLOSED
        elif _DORMANT_WORDS.search(clause):
            cls = _DORMANT
        else:
            cls = _OPEN
        line_start = text.rfind("\n", 0, m.start()) + 1
        label = _ROW_LABEL_RE.match(text, line_start)
        where = f"CLAUDE.md:{_line_of(text, m.start())}" + (f" ({label.group(1)} row)" if label else "")
        out.setdefault(m.group(1), []).append(_Claim(where, cls, _status_text(text[m.start():line_end], 0)))
    return out


def check_contradictions(root: Path) -> list[Finding]:
    """Every phase's status is one class wherever the record states it — the
    board, the roadmap's heading and phase table, CLAUDE.md's Current-state
    table — and CLAUDE.md's version row is `versions.py`'s. Prints the
    disagreeing pair; never picks a side."""
    check = "contradictions"
    out: list[Finding] = []

    claims: dict[str, list[_Claim]] = {}
    for source in (board_claims, roadmap_claims, claude_md_claims):
        for phase, cs in source(root).items():
            claims.setdefault(phase, []).extend(cs)

    todo_text = (root / TODO).read_text(encoding="utf-8") if (root / TODO).is_file() else ""
    open_items = set(_ITEM_HEADING_RE.findall(todo_text))

    for phase in sorted(claims, key=int):
        subject = f"Phase {phase}"
        cs = claims[phase]
        classes = {c.cls for c in cs}
        pinned = KNOWN_CONTRADICTIONS.get(subject)
        if len(classes) <= 1:
            if pinned is not None:
                out.append(Finding(check, subject,
                                   f"KNOWN_CONTRADICTIONS pins it to todo.md #{pinned} but every source now agrees "
                                   f"({', '.join(sorted(classes)) or 'no claim'}) — remove the pin"))
            continue
        pair = "; ".join(f'{c.where} says "{c.text}"' for c in cs)
        if pinned is None:
            out.append(Finding(check, subject,
                               f"{pair} — CLAUDE.md says who wins; apply it, or pin the pair in "
                               f"KNOWN_CONTRADICTIONS against an open todo.md item"))
        elif pinned not in open_items:
            out.append(Finding(check, subject,
                               f"{pair} — pinned to todo.md #{pinned}, which heads no open item; "
                               f"the pin must appear in todo.md (resolved #23)"))
        else:
            out.append(Finding(check, subject, f"{pair} — pinned, todo.md #{pinned}", red=False))

    claude_md = root / EXTRA_DOCS[0]
    versions_py = root / VERSIONS_PY
    if claude_md.is_file() and versions_py.is_file():
        text = claude_md.read_text(encoding="utf-8")
        sec = _CURRENT_STATE_RE.search(text)
        row = _VERSION_ROW_RE.search(sec.group(1)) if sec else None
        code = _PIPELINE_VERSION_RE.search(versions_py.read_text(encoding="utf-8"))
        if row and code and row.group(1) != code.group(1):
            where = f"CLAUDE.md:{_line_of(text, sec.start(1) + row.start())}"
            out.append(Finding(check, where,
                               f"the Current-state table says {row.group(1)} and versions.py says "
                               f"{code.group(1)} — bump_version.py does not edit CLAUDE.md"))
    return out


# ---------------------------------------------------------------------------
# WP-24.E — ages, from git
# ---------------------------------------------------------------------------

# Not a check. Days since each open todo.md item and each board row was last
# edited, oldest first — no threshold, so nothing here is ever red (resolved
# #23: an old item breaks no rule). The runner prints the table before the
# findings; /orient (WP-24.G) prints it at turn 1. The date is per line from
# `git blame`, so an item's age is its youngest line's; whitespace-only and
# moved-within-the-file changes are not edits (-w -M), a line moved in from
# another file is one — the consolidation of 2026-09-04 → 09-11 is that
# young, and so is everything it moved.
#
# The board's rows are its `###` sections and the `- **…**` bullets under
# "Queued / dormant"; the changelog table and "Recently closed" are not rows
# — a closed row is finished, not stale.

_AGED_BOARD_SECTIONS = ("## Active", "## Queued / dormant")
_H2_RE = re.compile(r"^## ", re.M)
_H3_RE = re.compile(r"^### (.*)$", re.M)
_ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class Age:
    subject: str          # "todo.md #26" / "board: Phase 24 — …"
    days: float
    when: datetime        # the youngest line's committer date
    what: str             # "abc1234 subject", or "uncommitted"

    def __str__(self) -> str:
        return f"{self.days:6.1f}  {self.subject:<62}  {self.when:%Y-%m-%d}  {self.what}"


def _blame(root: Path, rel: str, rev: str | None) -> list[tuple[datetime, str]] | None:
    """(committer date, "hash subject") per line of `rel` — at `rev`, or the
    working tree when rev is None (an uncommitted line dates from now)."""
    args = ["blame", "--porcelain", "-w", "-M"]
    if rev is not None:
        args.append(rev)
    out = _git(root, *args, "--", rel)
    if out is None:
        return None
    meta: dict[str, dict[str, str]] = {}
    lines: list[tuple[datetime, str]] = []
    it = iter(out.split("\n"))
    for head in it:
        if not head:
            continue
        sha = head.split(" ", 1)[0]
        for field in it:
            if field.startswith("\t"):
                break
            key, _, val = field.partition(" ")
            meta.setdefault(sha, {})[key] = val
        m = meta.get(sha, {})
        if sha == _ZERO_SHA:
            lines.append((datetime.now(timezone.utc), "uncommitted"))
        else:
            when = datetime.fromtimestamp(int(m["committer-time"]), timezone.utc)
            lines.append((when, f"{sha[:7]} {m.get('summary', '')}"))
    return lines


def _text_at(root: Path, rel: str, rev: str | None) -> str | None:
    if rev is None:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None
    return _git(root, "show", f"{rev}:{rel}")


def _short(name: str, n: int = 52) -> str:
    name = name.strip(" —-*")
    return name if len(name) <= n else name[:n - 1] + "…"


def _row_name(heading: str) -> str:
    """A board row's name: its heading up to the first status marker."""
    m = _MARKER_RE.search(heading)
    return _short(heading[:m.start()] if m else heading)


def _item_name(heading: str, n: str) -> str:
    """An inbox item's name: its number and the title after the dash."""
    _, dash, title = heading.partition(" — ")
    return _short(f"#{n} — {title}" if dash else f"#{n}", 52)


def _todo_spans(text: str) -> list[tuple[str, int, int]]:
    """(subject, first line, last line) of each `### … #N` item: the heading
    through the line before the next numbered `###` or any `##` heading, so
    an unnumbered sub-heading stays with its item."""
    lines = text.split("\n")
    spans = []
    for i, line in enumerate(lines):
        m = _ITEM_HEADING_RE.match(line)
        if not m:
            continue
        end = next((j for j in range(i + 1, len(lines))
                    if lines[j].startswith("## ") or _ITEM_HEADING_RE.match(lines[j])), len(lines)) - 1
        spans.append((f"todo.md {_item_name(line[4:], m.group(1))}", i, end))
    return spans


def _board_spans(text: str) -> list[tuple[str, int, int]]:
    """(subject, first line, last line) of each board row inside the aged
    sections: a `###` section through the line before the next heading, or a
    top-level `- **…**` bullet through its continuation lines."""
    lines = text.split("\n")
    spans = []
    section = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            section = line.strip() if line.strip() in _AGED_BOARD_SECTIONS else None
            i += 1
            continue
        if section is None:
            i += 1
            continue
        if line.startswith("### "):
            end = next((j for j in range(i + 1, len(lines))
                        if lines[j].startswith("## ") or lines[j].startswith("### ")), len(lines)) - 1
            spans.append((f"board: {_row_name(line[4:])}", i, end))
            i = end + 1
            continue
        if (m := _BOARD_BULLET_RE.match(line)):
            end = next((j for j in range(i + 1, len(lines))
                        if not lines[j].startswith("  ") or not lines[j].strip()), len(lines)) - 1
            spans.append((f"board: {_row_name(m.group(1))}", i, end))
            i = end + 1
            continue
        i += 1
    return spans


def ages(root: Path, *, now: datetime | None = None) -> list[Age]:
    """Every open todo.md item and every board row with the days since its
    youngest line was committed, oldest first. Empty when git cannot answer
    (no repository, a shallow clone — 24.B is red there)."""
    if now is None:
        now = datetime.now(timezone.utc)
        rev = None
    else:
        rev = _git(root, "rev-list", "-1", f"--until={now.isoformat()}", "HEAD")
        if not rev:
            return []
    if _git(root, "rev-parse", "--is-shallow-repository") != "false":
        return []
    out: list[Age] = []
    for rel, spans_of in ((str(TODO), _todo_spans), (str(BOARD), _board_spans)):
        text = _text_at(root, rel, rev)
        if text is None:
            continue
        blame = _blame(root, rel, rev)
        if blame is None:
            continue
        for subject, first, last in spans_of(text):
            when, what = max(blame[first:last + 1], key=lambda t: t[0])
            out.append(Age(subject, max(0.0, (now - when).total_seconds() / 86400), when, what))
    return sorted(out, key=lambda a: (-a.days, a.subject))


# ---------------------------------------------------------------------------
# WP-24.F — ADR revisit conditions
# ---------------------------------------------------------------------------

# Part 4 of the page shape (decisions/index.md), enforced rather than
# introduced (resolved #24): every ADR that is not superseded carries
# `## Would we revisit it?`, non-empty — presence, the sibling of convention
# #11's "a page with no costs listed has not been thought through". A
# reasoned "No." is an answer; a superseded page's replacement is its answer.
#
# The became-true half reads only what a machine can. A revisit section that
# cites a todo.md item, a WP, a KB entry or a Phase whose record heading is
# *younger* than the section — the item resolved, the WP or phase marked
# closed, the KB entry landed, all after the section was last edited — is
# printed as "cited condition may have fired", report-only. The date
# comparison, per line from `git blame` as in 24.E, is what keeps it quiet:
# ADR-0009 names [KB-027] as the result it already absorbed, not a condition
# still pending, and its section is younger than that entry. Prose
# conditions ("if GitHub's scheduler became reliable") are not read, and a
# structured condition field was rejected as narrower than the prose.

_REVISIT_HEADING = "## Would we revisit it?"
_REVISIT_RE = re.compile(r"^## Would we revisit it\?[ \t]*$", re.M)
_ADR_STATUS_RE = re.compile(r"^\| \*\*Status\*\* \|([^\n]*)", re.M)
_SUPERSEDED_RE = re.compile(r"\bsuperseded\b", re.I)
_HEADING_LINE_RE = re.compile(r"^#{2,4} [^\n]*$", re.M)
# "#7 and #8 in [todo.md](../record/todo.md)" — a bare item number, read as
# an inbox pointer only in a section that names todo.md
_BARE_ITEM_RE = re.compile(r"(?<![\w-])#(\d+[a-z]?)\b")
# "*(family 1 ✅ RESOLVED 2026-09-08 — …)*" on WP-21.E's heading is about
# family 1; the heading's own marker is the first one outside such an aside
# (which may itself hold a markdown link's parentheses — the aside ends at
# the first `)*`)
_ITALIC_ASIDE_RE = re.compile(r"\*\([^\n]*?\)\*")


@dataclass(frozen=True)
class _Referent:
    what: str                 # "resolved" / "closed" / "landed"
    where: str                # "docs/record/resolved.md:165"
    when: datetime | None     # blame date of that heading line; None when git cannot say


class _Dater:
    """Blame date of a line, per file, blamed once; None where git cannot answer."""

    def __init__(self, root: Path, rev: str | None):
        self.root, self.rev = root, rev
        self.ok = _git(root, "rev-parse", "--is-shallow-repository") == "false"
        self._cache: dict[str, list[tuple[datetime, str]] | None] = {}

    def lines(self, rel: str) -> list[tuple[datetime, str]] | None:
        if not self.ok:
            return None
        if rel not in self._cache:
            self._cache[rel] = _blame(self.root, rel, self.rev)
        return self._cache[rel]

    def at(self, rel: str, line: int) -> datetime | None:
        blame = self.lines(rel)
        return blame[line - 1][0] if blame and line <= len(blame) else None

    def youngest(self, rel: str, first: int, last: int) -> datetime | None:
        blame = self.lines(rel)
        return max(t for t, _ in blame[first - 1:last]) if blame and first <= len(blame) else None


def _adr_paths(root: Path, rev: str | None) -> list[str]:
    if rev is None:
        return [f"{DECISIONS_DIR.as_posix()}/{name}" for names in _adr_files(root).values() for name in names]
    listing = _git(root, "ls-tree", "--name-only", rev, "--", f"{DECISIONS_DIR.as_posix()}/") or ""
    return sorted(p for p in listing.splitlines() if _ADR_FILE_RE.match(Path(p).name))


def _revisit_section(text: str) -> tuple[int, int, str] | None:
    """(heading line, last non-blank line, body) of `## Would we revisit
    it?`; the section runs to the next `## ` heading or the end of the page."""
    m = _REVISIT_RE.search(text)
    if not m:
        return None
    nxt = _H2_RE.search(text, m.end())
    body = text[m.end():nxt.start() if nxt else len(text)]
    first = _line_of(text, m.start())
    return first, first + len(body.rstrip().split("\n")) - 1, body


def _youngest_referent(what: str, spots: list[tuple[str, int]], dater: _Dater) -> _Referent:
    dated = [(dater.at(rel, line), rel, line) for rel, line in spots]
    when, rel, line = max(dated, key=lambda t: (t[0] is not None, t[0] or datetime.min.replace(tzinfo=timezone.utc)))
    return _Referent(what, f"{rel}:{line}", when)


def _closed_referents(root: Path, rev: str | None, dater: _Dater) -> dict[str, _Referent]:
    """Cited id → the record heading that closes it, dated. Only ids whose
    referent has closed or landed appear: a resolved item that no longer
    heads an open one, a WP whose every marked heading in the roadmaps is
    closed-class, a phase whose every status claim is, a KB entry that
    exists."""
    out: dict[str, _Referent] = {}

    todo_text = _text_at(root, TODO.as_posix(), rev) or ""
    resolved_text = _text_at(root, RESOLVED.as_posix(), rev) or ""
    todo_open = set(_ITEM_HEADING_RE.findall(todo_text))
    spots: dict[str, list[tuple[str, int]]] = {}
    for m in _RESOLVED_HEADING_RE.finditer(resolved_text):
        spots.setdefault(m.group(1), []).append((RESOLVED.as_posix(), _line_of(resolved_text, m.start())))
    for n, where in spots.items():
        if n not in todo_open:
            out[f"todo.md #{n}"] = _youngest_referent("resolved", where, dater)

    kb_text = _text_at(root, KNOWLEDGE_BASE.as_posix(), rev) or ""
    for m in _KB_HEADING_RE.finditer(kb_text):
        out.setdefault(f"KB-{m.group(1)}",
                       _youngest_referent("landed", [(KNOWLEDGE_BASE.as_posix(), _line_of(kb_text, m.start()))], dater))

    claims: dict[str, list[tuple[str, str, int]]] = {}
    for rel in ROADMAPS:
        text = _text_at(root, rel.as_posix(), rev) or ""
        for h in _HEADING_LINE_RE.finditer(text):
            line = _ITALIC_ASIDE_RE.sub("", h.group(0))
            for w in _WP_RE.finditer(line):
                mk = _MARKER_RE.search(line, w.end())
                if mk:
                    claims.setdefault(w.group(1), []).append(
                        (_MARKER_CLASS[mk.group()], rel.as_posix(), _line_of(text, h.start())))
    for wp, cs in claims.items():
        if all(cls == _CLOSED for cls, _, _ in cs):
            out[f"WP-{wp}"] = _youngest_referent("closed", [(rel, line) for _, rel, line in cs], dater)

    phases: dict[str, list[_Claim]] = {}
    for src in (board_claims(root, rev=rev), roadmap_claims(root, rev=rev)):
        for n, cs in src.items():
            phases.setdefault(n, []).extend(cs)
    for n, cs in phases.items():
        if all(c.cls == _CLOSED for c in cs):
            where = [(c.where.rsplit(":", 1)[0], int(c.where.rsplit(":", 1)[1])) for c in cs]
            out[f"Phase {n}"] = _youngest_referent("closed", where, dater)
    return out


def _cited(body: str) -> list[str]:
    """The ids a revisit section cites — KB, WP, Phase, then inbox items — each kind in order of mention, once."""
    ids: list[str] = []
    for m in _KB_RE.finditer(body):
        ids.append(f"KB-{m.group(1)}")
    for m in _WP_RE.finditer(body):
        ids.append(f"WP-{m.group(1)}")
    for m in _PHASE_RE.finditer(body):
        ids.append(f"Phase {m.group(1)}")
    if "todo.md" in body:
        for m in _BARE_ITEM_RE.finditer(body):
            ids.append(f"todo.md #{m.group(1)}")
    return list(dict.fromkeys(ids))


def check_adr_revisit(root: Path, *, now: datetime | None = None) -> list[Finding]:
    """Every ADR that is not superseded has a non-empty `## Would we revisit
    it?` (red); a revisit section citing an id whose record heading is
    younger than the section — resolved, closed or landed since it was last
    edited — is printed as "cited condition may have fired" (report-only)."""
    check = "adr-revisit"
    out: list[Finding] = []
    rev = None
    if now is not None:
        rev = _git(root, "rev-list", "-1", f"--until={now.isoformat()}", "HEAD")
        if not rev:
            return []
    paths = _adr_paths(root, rev)
    if not paths:
        return []
    dater = _Dater(root, rev)
    referents: dict[str, _Referent] | None = None

    for rel in paths:
        text = _text_at(root, rel, rev) or ""
        status = _ADR_STATUS_RE.search(text)
        if status and _SUPERSEDED_RE.search(status.group(1)):
            continue
        sec = _revisit_section(text)
        if sec is None:
            out.append(Finding(check, rel,
                               f"no `{_REVISIT_HEADING}` section — part 4 of the page shape (decisions/index.md); "
                               f"a reasoned \"No.\" is an answer, an absent section is not (resolved #24)"))
            continue
        first, last, body = sec
        if not body.strip():
            out.append(Finding(check, f"{rel}:{first}",
                               f"`{_REVISIT_HEADING}` is empty — a reasoned \"No.\" is an answer, "
                               f"an empty section is not (resolved #24)"))
            continue
        cited = _cited(body)
        if not cited:
            continue
        if referents is None:
            referents = _closed_referents(root, rev, dater)
        edited = dater.youngest(rel, first, last)
        for cid in cited:
            ref = referents.get(cid)
            if ref is None:
                continue
            if ref.when is not None and edited is not None:
                if ref.when <= edited:
                    continue
                dates = (f"{ref.when:%Y-%m-%d}, after the section was last edited {edited:%Y-%m-%d}")
            else:
                dates = "undated — no git history to say which came first"
            out.append(Finding(check, f"{rel}:{first}",
                               f"cites {cid}, {ref.what} ({ref.where}) {dates} — cited condition may have fired",
                               red=False))
    return out


# ---------------------------------------------------------------------------
# WP-25.B — the audit's code checks (ADR-0022)
# ---------------------------------------------------------------------------

HYPOTHESES = RECORD_DIR / "hypotheses.md"
AUDITOR_INSTRUCTIONS = Path(".macro-assist") / "auditor" / "instructions.md"
# On the output branch, whose root is results/ (ADR-0001). audit_entry.py
# writes the records; explore_conditioner.py appends the run log.
AUDIT_RECORDS = "audit/entries"
CANARY_RECORDS = "audit/canaries"
RUN_LOG = "explore_conditioner/runs.jsonl"

# Dated looks that ran before the harness kept a run log (WP-25.B, 2026-09-29),
# so no receipt can exist for them. Held exactly: a pin whose look has left its
# entry's ledger, or that a logged run now covers, is itself red. A look added
# after 2026-09-29 cannot be pinned without this diff showing it.
LOOKS_BEFORE_RECEIPTS: frozenset[tuple[str, str]] = frozenset({
    ("H-006", "2026-09-14"),
})   # H-004's and H-008's (two, inherited from H-002) dropped when they closed, 2026-09-29

# Entries the owner let past two rejections (ADR-0022, *No grinding*), each
# against the number of the resolved.md item that records the decision, e.g.
# {"H-008": "31"}. Held exactly: a pin
# on an entry that has not been rejected twice, or whose item does not exist,
# is red.
OWNER_RESUBMISSIONS: dict[str, str] = {}

_LOOK_DATE_RE = re.compile(r"\*(\d{4}-\d{2}-\d{2})\b[^*\n]*\*")   # an italic span that opens with a date
_REPORT_PATH_RE = re.compile(r"`results/([^`]+)`")
_PROMOTED_LINE = r"^\*\*Status:\*\* `promoted`"


def _dp():
    # decision_packet parses the register and imports this module at its top,
    # so the import is deferred to call time rather than made circular.
    import decision_packet
    return decision_packet


def _register(root: Path, rev: str | None = None) -> dict[str, tuple[object, str]]:
    """hid → (Entry, its text) in the register at `rev` (None: the working tree)."""
    dp = _dp()
    text = _text_at(root, HYPOTHESES.as_posix(), rev)
    if text is None:
        return {}
    return {e.hid: (e, dp.entry_text(text, e.hid)) for e in dp.parse_entries(text)}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_files(root: Path, ref: str, prefix: str) -> list[tuple[str, dict | None]]:
    """(path, parsed JSON or None when it does not parse) for every .json under
    `prefix` on `ref`, sorted by path — the records' names open with their stamp."""
    names = (_git(root, "ls-tree", "-r", "--name-only", ref, "--", prefix) or "").splitlines()
    out = []
    for p in sorted(n for n in names if n.endswith(".json")):
        try:
            out.append((p, json.loads(_git(root, "show", f"{ref}:{p}") or "")))
        except ValueError:
            out.append((p, None))
    return out


def ci_audits(root: Path, ref: str) -> dict[str, list[dict]]:
    """hid → CI's audit records of it on `ref`, oldest first. A record counts
    only if it says CI ran it and links the run; a local audit is not a
    submission (audit_entry.py), and a record that does not parse is nothing."""
    out: dict[str, list[dict]] = {}
    for path, rec in _json_files(root, ref, AUDIT_RECORDS):
        if isinstance(rec, dict) and rec.get("tier") == "ci" and rec.get("run") and rec.get("hid"):
            out.setdefault(rec["hid"], []).append({**rec, "_path": path})
    return out


CERTIFIED_BY = ("requested_model", "effort", "instructions_sha256", "canary_set_sha256")


def certified_configs(root: Path, ref: str) -> dict[tuple, str]:
    """(requested_model, effort, instructions_sha256, canary_set_sha256) of
    every canary suite CI ran that passed → the suite's path: the configurations
    an audit may approve with (WP-25.A). A change to any of the four needs a
    new pass."""
    return {tuple(s.get(k) for k in CERTIFIED_BY): p
            for p, s in _json_files(root, ref, CANARY_RECORDS)
            if isinstance(s, dict) and s.get("passed") is True and s.get("tier") == "ci"}


def check_approval_stamp(root: Path) -> list[Finding]:
    """A `promoted` entry has a CI audit stamped to its current text that found
    nothing blocking, made with a configuration the canaries certified."""
    check = "approval-stamp"
    dp = _dp()
    promoted = {h: t for h, (e, t) in _register(root).items() if e.status == "promoted"}
    if not promoted:
        return []
    ref = _resolve_ref(root, "output")
    if ref is None:
        return [Finding(check, h, "promoted, and the output branch that holds audit records is not "
                                  "available here — `git fetch origin output`") for h in promoted]
    audits, certified = ci_audits(root, ref), certified_configs(root, ref)
    out: list[Finding] = []
    for hid, text in sorted(promoted.items()):
        stamp = f"sha256:{_sha256(dp.stamped_text(text))}"
        recs = audits.get(hid, [])
        mine = [r for r in recs if r.get("entry_fingerprint") == stamp]
        if not recs:
            out.append(Finding(check, hid, f"promoted with no audit CI recorded (none under "
                                           f"`{ref}:{AUDIT_RECORDS}/{hid}/`)"))
        elif not mine:
            out.append(Finding(check, hid, f"promoted, but no CI audit is stamped to its current text "
                                           f"({stamp[:19]}…) — edited since its last audit, "
                                           f"`{recs[-1]['_path']}`"))
        elif mine[-1].get("verdict") != "no_blocking_finding":
            out.append(Finding(check, hid, f"promoted, and the latest CI audit of its current text "
                                           f"rejected it (`{mine[-1]['_path']}`)"))
        else:
            r = mine[-1]
            cfg = tuple(r.get(k) for k in CERTIFIED_BY)
            if cfg not in certified:
                out.append(Finding(check, hid, f"approved by `{cfg[0]}` / `{cfg[1]}` on instructions "
                                               f"{str(cfg[2])[:12]}… and canary set {str(cfg[3])[:12]}…, "
                                               f"which no passing canary suite on `{ref}` certifies "
                                               f"(`{r['_path']}`)"))
    return out


def check_audit_record_field(root: Path) -> list[Finding]:
    """Every entry's `Audit record` field is exactly what CI's audit records on
    output make of it, and an entry CI never audited has none (WP-25.C). So the
    field lists every submission — the counted looks of *No grinding* — and
    nobody can write one by hand that CI did not."""
    check = "audit-record-field"
    dp = _dp()
    entries = _register(root)
    ref = _resolve_ref(root, "output")
    audits = ci_audits(root, ref) if ref else {}
    fix = "`python .macro-assist/audit_entry.py {} --sync-field` rewrites it from the records"
    out: list[Finding] = []
    for hid, (e, text) in sorted(entries.items()):
        got = dp.field_block(text, dp.AUDIT_RECORD)
        if ref is None:
            if got is not None:
                out.append(Finding(check, hid, "carries an Audit record, and the output branch that "
                                               "holds CI's records is not available here — "
                                               "`git fetch origin output`"))
            continue
        recs = audits.get(hid, [])
        want = dp.audit_record_paragraph(recs)
        if want is None and got is not None:
            out.append(Finding(check, hid, "carries an Audit record with no CI audit of it on "
                                           f"`{ref}` — only CI writes that field"))
        elif want is not None and got is None:
            out.append(Finding(check, hid, f"CI audited it {len(recs)} time(s) and the entry has no "
                                           f"Audit record — {fix.format(hid)}"))
        elif want is not None and _norm(got) != _norm(want):
            out.append(Finding(check, hid, "its Audit record is not what CI's records on "
                                           f"`{ref}` say — {fix.format(hid)}"))
    return out


def _norm(block: str) -> str:
    return "\n".join(ln.strip() for ln in block.strip().splitlines() if ln.strip())


def check_no_grinding(root: Path) -> list[Finding]:
    """A third CI audit of an entry after two rejections is red, until the
    entry closes or the owner decides (OWNER_RESUBMISSIONS)."""
    check = "no-grinding"
    entries = _register(root)
    ref = _resolve_ref(root, "output")
    audits = ci_audits(root, ref) if ref else {}
    resolved = _text_at(root, RESOLVED.as_posix(), None) or ""
    items = set(_ITEM_HEADING_RE.findall(resolved))
    out: list[Finding] = []
    ground: set[str] = set()
    for hid, recs in sorted(audits.items()):
        rejects = 0
        for r in recs:
            if rejects >= 2:
                ground.add(hid)
                entry = entries.get(hid)
                if entry is not None and entry[0].status != "closed" and hid not in OWNER_RESUBMISSIONS:
                    out.append(Finding(check, hid, f"audited again after two rejections (`{r['_path']}`) — "
                                                   "the entry closes or the owner decides (ADR-0022)"))
                break
            rejects += r.get("verdict") == "reject"
    for hid, item in sorted(OWNER_RESUBMISSIONS.items()):
        n = item.lstrip("#")
        if n not in items:
            out.append(Finding(check, f"OWNER_RESUBMISSIONS[{hid}]",
                               f"points at resolved.md #{n}, which has no heading there"))
        if hid not in ground:
            out.append(Finding(check, f"OWNER_RESUBMISSIONS[{hid}]",
                               "pinned, but the entry has not been audited past two rejections — drop the pin"))
    return out


def _commits_touching(root: Path, path: str, *extra: str) -> list[tuple[str, datetime]]:
    """(sha, committer date) of every commit on HEAD touching `path`, oldest first."""
    lines = (_git(root, "log", "--reverse", "--format=%H%x1f%cI", *extra, "HEAD", "--", path) or "").splitlines()
    return [(sha, datetime.fromisoformat(d)) for sha, d in (ln.split("\x1f") for ln in lines if ln)]


def _ever_promoted(root: Path) -> set[str]:
    """Every entry that is `promoted` at HEAD, in the working tree, or at any
    revision where a `promoted` status line came or went."""
    hids = {h for h, (e, _) in _register(root).items() if e.status == "promoted"}
    for sha, _ in _commits_touching(root, HYPOTHESES.as_posix(), "-G", _PROMOTED_LINE):
        for rev in (sha, f"{sha}^"):
            hids |= {h for h, (e, _) in _register(root, rev).items() if e.status == "promoted"}
    return hids


def check_instruction_freeze(root: Path) -> list[Finding]:
    """No commit edits the auditor's instructions and, in the same commit, an
    entry that is or was ever promoted — its status or its stamped text."""
    check = "instruction-freeze"
    if _git(root, "rev-parse", "--git-dir") is None:
        return []
    if _git(root, "rev-parse", "--is-shallow-repository") == "true":
        return [Finding(check, str(root), "shallow clone — the instructions' history is cut short and "
                                          "the check would pass vacuously")]
    promoted = _ever_promoted(root)
    if not promoted:
        return []
    dp = _dp()
    reg = HYPOTHESES.as_posix()
    out: list[Finding] = []
    for sha, when in _commits_touching(root, AUDITOR_INSTRUCTIONS.as_posix()):
        files = (_git(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha) or "").splitlines()
        if reg not in files:
            continue
        def view(reg: dict, hid: str) -> tuple[str, str] | None:
            hit = reg.get(hid)
            return None if hit is None else (hit[0].status, dp.stamped_text(hit[1]))

        after, before = _register(root, sha), _register(root, f"{sha}^")
        for hid in sorted(promoted & (set(after) | set(before))):
            if view(after, hid) != view(before, hid):
                out.append(Finding(check, hid, f"commit {sha[:9]} ({when:%Y-%m-%d}) changed the auditor's "
                                               f"instructions and this entry together; it is or was promoted"))
    return out


def _bar_changed(root: Path, hid: str) -> tuple[datetime, str] | None:
    """When the entry's bar text last changed: the newest commit that changed
    it, or now if the working tree differs from HEAD."""
    dp = _dp()
    last, prev = None, None
    for sha, when in _commits_touching(root, HYPOTHESES.as_posix()):
        cur = _register(root, sha).get(hid)
        bar = None if cur is None else dp.bar_text(cur[1])
        if bar is not None and bar != prev:
            last = (when, sha[:9])
        prev = bar
    work = _register(root).get(hid)
    if work is not None and dp.bar_text(work[1]) != prev:
        last = (datetime.now(timezone.utc), "the working tree")
    return last


def check_bar_before_result(root: Path) -> list[Finding]:
    """An entry's bar — everything but its status, audit record and ledgers —
    last changed before the first commit of the sealed read it is read against."""
    check = "bar-before-result"
    dp = _dp()
    read = {h: e for h, (e, _) in _register(root).items() if dp.SEALED_READ in e.fields}
    if not read:
        return []
    ref = _resolve_ref(root, "output")
    out: list[Finding] = []
    for hid, e in sorted(read.items()):
        paths = _REPORT_PATH_RE.findall(e.fields[dp.SEALED_READ])
        if not paths:
            out.append(Finding(check, hid, f"its {dp.SEALED_READ} names no report under results/"))
            continue
        if ref is None:
            out.append(Finding(check, hid, "the output branch that holds its result is not available here"))
            continue
        bar = _bar_changed(root, hid)
        for p in paths:
            first = (_git(root, "log", "--reverse", "--format=%cI%x1f%h", ref, "--", p) or "").splitlines()
            if not first:
                out.append(Finding(check, hid, f"its result `results/{p}` is not on `{ref}`"))
                continue
            stamp, short = first[0].split("\x1f")
            landed = datetime.fromisoformat(stamp)
            if bar is None or bar[0] >= landed:
                where = "never committed" if bar is None else f"last changed {bar[0]:%Y-%m-%d %H:%M} ({bar[1]})"
                out.append(Finding(check, hid, f"its bar was {where}, not before its result "
                                               f"`results/{p}` first landed {landed:%Y-%m-%d %H:%M} ({short}) — "
                                               "a result file older than the bar cannot be checked either"))
    return out


def _look_dates(entry) -> set[str]:
    """Dates of the looks an entry's ledgers record, less the sealed read's."""
    dp = _dp()
    return {d for name, body in entry.fields.items()
            if name.endswith("(ledger)") and name != dp.SEALED_READ
            for d in _LOOK_DATE_RE.findall(body)}


def logged_runs(root: Path, ref: str) -> tuple[list[dict], list[int]]:
    """The harness's run log on `ref`, and the line numbers that do not parse."""
    runs, bad = [], []
    for i, line in enumerate((_git(root, "show", f"{ref}:{RUN_LOG}") or "").splitlines(), 1):
        try:
            rec = json.loads(line)
            at = datetime.fromisoformat(rec["run_at"])
        except (ValueError, KeyError, TypeError):
            bad.append(i)
            continue
        rec["_dates"] = {at.date().isoformat(), at.astimezone(timezone.utc).date().isoformat()}
        runs.append(rec)
    return runs, bad


def check_receipts(root: Path) -> list[Finding]:
    """Every dated look in an open entry's ledger has a run the harness logged
    that day (red). A logged run no entry's ledger dates is report-only — a
    look nobody counted."""
    check = "receipts"
    entries = _register(root)
    looks = {(h, d) for h, (e, _) in entries.items() if e.status != "closed" for d in _look_dates(e)}
    cited = {d for _, (e, _) in entries.items() for d in _look_dates(e)}
    ref = _resolve_ref(root, "output")
    runs, bad = logged_runs(root, ref) if ref else ([], [])
    logged = set().union(*(r["_dates"] for r in runs)) if runs else set()
    out: list[Finding] = []
    for n in bad:
        out.append(Finding(check, f"output:results/{RUN_LOG}", f"line {n} does not parse as a run"))
    for hid, d in sorted(looks - LOOKS_BEFORE_RECEIPTS):
        if d not in logged:
            where = f"`{ref}:{RUN_LOG}`" if ref else "the output branch (not available here)"
            out.append(Finding(check, hid, f"look dated {d} has no run logged that day in {where}"))
    for hid, d in sorted(LOOKS_BEFORE_RECEIPTS):
        if (hid, d) not in looks:
            out.append(Finding(check, f"LOOKS_BEFORE_RECEIPTS {hid} {d}",
                               "no longer a look in an open entry's ledger — drop the pin"))
        elif d in logged:
            out.append(Finding(check, f"LOOKS_BEFORE_RECEIPTS {hid} {d}",
                               "a logged run covers it now — drop the pin"))
    for r in runs:
        if not r["_dates"] & cited:
            out.append(Finding(check, f"run {r['run_at']}",
                               "logged, and in no entry's ledger — an uncounted look (how-we-explore §4)",
                               red=False))
    return out


# ---------------------------------------------------------------------------
# the sealed read's own checks (WP-23.B)
# ---------------------------------------------------------------------------

SEALED_RECORDS = "sealed_reads"                   # on output: <hid>/<stamp>.claim.json, <stamp>.json, <stamp>.md
CLASS_BARS = Path(".macro-assist") / "class_bars.py"

# A claim the owner has judged read nothing — its run failed after the claim
# and before any sealed number was computed — so it does not spend its class's
# slice. Path on output → the resolved.md item that decided it. Held exactly:
# a pin whose claim is not on output is red.
VOIDED_CLAIMS: dict[str, str] = {}

# A class bar that changed after its class's sealed read, with the owner's
# decision that the change was a defect fix the pre-registration already
# required, not a goalpost move (CLAUDE.md #7): class → (the fingerprint now in
# force, the resolved.md item). A pin for any other fingerprint is red.
BAR_EDITS_AFTER_READ: dict[str, tuple[str, str]] = {}

# What a class's bar is NOT: the command line, the printer, and the registry
# (built from each bar's own `name=`, so the bar's own definition covers it).
_NOT_THE_BAR = frozenset({"describe", "main", "BARS"})


def ci_sealed_reads(root: Path, ref: str) -> list[dict]:
    """CI's sealed-read records on `ref` — claims and results — sorted by
    path. Like an audit, a record counts only if CI made it and links the run."""
    return [{**rec, "_path": path} for path, rec in _json_files(root, ref, SEALED_RECORDS)
            if isinstance(rec, dict) and rec.get("tier") == "ci" and rec.get("run")
            and rec.get("hid") and rec.get("kind") in ("claim", "result")]


def class_claims(records: list[dict], voided=None) -> dict[str, list[dict]]:
    """class → its claims on record, less the voided ones, oldest first."""
    voided = VOIDED_CLAIMS if voided is None else voided
    out: dict[str, list[dict]] = {}
    for r in sorted((r for r in records if r["kind"] == "claim"),
                    key=lambda r: str(r.get("claimed_at"))):
        if r["_path"] not in voided:
            out.setdefault(str(r.get("class")), []).append(r)
    return out


def _segment(lines: list[str], node) -> str:
    start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
    return "\n".join(ln.rstrip() for ln in lines[start - 1: node.end_lineno])


def _defined(node) -> set[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    targets = node.targets if isinstance(node, ast.Assign) else \
        [node.target] if isinstance(node, ast.AnnAssign) else []
    return {t.id for t in targets if isinstance(t, ast.Name)}


def _bar_named(node) -> str | None:
    """The `name=` of a module-level `X = ClassBar(name=..., ...)`, else None."""
    call = getattr(node, "value", None)
    if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(call, ast.Call) \
            and getattr(call.func, "id", None) == "ClassBar":
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                return kw.value.value
    return None


def bar_fingerprint(root: Path, cls: str) -> str | None:
    """sha256 over what the class `cls` is read by: `class_bars.py` less its
    docstring, its command line and every OTHER class's bar, plus the source of
    each name it imports from a module of this repo (MIN_SKILL, skill_vs, the
    seal dates, the asset registry). Read as text, not imported — this module
    runs without numpy — and as source lines, not `ast.dump`, which differs
    between the Python versions CI uses. None when there is no such class."""
    path = root / CLASS_BARS
    if not path.is_file():
        return None
    src = path.read_text(encoding="utf-8")
    lines, tree = src.splitlines(), ast.parse(src)
    parts, found = [], False
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.If) or _defined(node) & _NOT_THE_BAR:
            continue
        named = _bar_named(node)
        if named is not None and named != cls:
            continue
        found |= named == cls
        if isinstance(node, ast.ImportFrom) and not node.level \
                and (root / CLASS_BARS.parent / f"{node.module}.py").is_file():
            dep = (root / CLASS_BARS.parent / f"{node.module}.py").read_text(encoding="utf-8")
            dlines = dep.splitlines()
            defs = {n: _segment(dlines, d) for d in ast.parse(dep).body for n in _defined(d)}
            parts += [f"{node.module}.{a.name}:\n{defs.get(a.name, '<not defined at module level>')}"
                      for a in node.names]
            continue
        parts.append(_segment(lines, node))
    return f"sha256:{_sha256(chr(10).join(parts))}" if found else None


def check_sealed_reads(root: Path) -> list[Finding]:
    """A class's slice is claimed once, the claim lands before its result, a
    claim has a result, and the class's bar has not changed since its claim."""
    check = "sealed-reads"
    ref = _resolve_ref(root, "output")
    if ref is None:
        return []
    recs = ci_sealed_reads(root, ref)
    claims = {r["_path"]: r for r in recs if r["kind"] == "claim"}
    results = [r for r in recs if r["kind"] == "result"]
    answered = {r.get("claim") for r in results}
    resolved = _text_at(root, RESOLVED.as_posix(), None) or ""
    items = set(_ITEM_HEADING_RE.findall(resolved))
    out: list[Finding] = []
    for cls, cs in sorted(class_claims(recs).items()):
        if len(cs) > 1:
            out.append(Finding(check, cls, f"the {cls} slice was claimed {len(cs)} times ("
                                           + ", ".join(f"`{c['_path']}`" for c in cs)
                                           + ") — it is read once for the whole class"))
        for c in cs:
            if c["_path"] not in answered:
                out.append(Finding(check, c["hid"], f"`{c['_path']}` claimed the {cls} slice and no "
                                                    "result was recorded — a lost read, which counts as "
                                                    "a read; only the owner voids it (VOIDED_CLAIMS)"))
        now, was = bar_fingerprint(root, cls), cs[0].get("bar_fingerprint")
        if now != was:
            pin = BAR_EDITS_AFTER_READ.get(cls)
            if pin and pin[0] == now and pin[1].lstrip("#") in items:
                out.append(Finding(check, cls, f"the {cls} bar changed since its read; the owner "
                                               f"accepted it (resolved.md {pin[1]})", red=False))
            else:
                out.append(Finding(check, cls, f"the {cls} bar changed since its sealed read "
                                               f"(`{cs[0]['_path']}`): {str(was)[:19]}… then, "
                                               f"{str(now)[:19]}… now — a bar does not move once its "
                                               "data is visible"))
    for r in results:
        c = claims.get(r.get("claim"))
        if c is None:
            out.append(Finding(check, r["hid"], f"`{r['_path']}` is a result with no claim on `{ref}`"))
            continue
        first = [(_git(root, "log", "--reverse", "--format=%H", ref, "--", p) or "").split("\n")[0]
                 for p in (c["_path"], r["_path"])]
        if not all(first) or first[0] == first[1] or \
                _git(root, "merge-base", "--is-ancestor", first[0], first[1]) is None:
            out.append(Finding(check, r["hid"], f"`{r['_path']}` did not land after its claim "
                                                f"`{c['_path']}` — the slice is claimed before it is read"))
    for p, item in sorted(VOIDED_CLAIMS.items()):
        if p not in claims:
            out.append(Finding(check, f"VOIDED_CLAIMS[{p}]", f"no such claim on `{ref}` — drop the pin"))
        elif item.lstrip("#") not in items:
            out.append(Finding(check, f"VOIDED_CLAIMS[{p}]", f"points at resolved.md {item}, which has "
                                                             "no heading there"))
    for cls, (fp, item) in sorted(BAR_EDITS_AFTER_READ.items()):
        if fp != bar_fingerprint(root, cls) or cls not in class_claims(recs):
            out.append(Finding(check, f"BAR_EDITS_AFTER_READ[{cls}]", "not the bar in force after a "
                                                                      "read — drop the pin"))
    return out


def check_sealed_read_field(root: Path) -> list[Finding]:
    """Every entry's `Sealed read (ledger)` is exactly what CI's sealed-read
    records on output make of it, and an entry CI never read has none."""
    check = "sealed-read-field"
    dp = _dp()
    entries = _register(root)
    ref = _resolve_ref(root, "output")
    by_hid: dict[str, list[dict]] = {}
    for r in (ci_sealed_reads(root, ref) if ref else []):
        by_hid.setdefault(r["hid"], []).append(r)
    fix = "`python .macro-assist/sealed_runner.py {} --sync-field` rewrites it from the records"
    out: list[Finding] = []
    for hid, (e, text) in sorted(entries.items()):
        got = dp.field_block(text, dp.SEALED_READ)
        if ref is None:
            if got is not None:
                out.append(Finding(check, hid, f"carries a {dp.SEALED_READ}, and the output branch that "
                                               "holds CI's records is not available here"))
            continue
        want = dp.sealed_read_paragraph(by_hid.get(hid, []))
        if want is None and got is not None:
            out.append(Finding(check, hid, f"carries a {dp.SEALED_READ} with no sealed-read record of it "
                                           f"on `{ref}` — only CI writes that field"))
        elif want is not None and got is None:
            out.append(Finding(check, hid, f"CI claimed its sealed read and the entry has no "
                                           f"{dp.SEALED_READ} — {fix.format(hid)}"))
        elif want is not None and _norm(got) != _norm(want):
            out.append(Finding(check, hid, f"its {dp.SEALED_READ} is not what CI's records on "
                                           f"`{ref}` say — {fix.format(hid)}"))
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = (check_workflow_orphans, check_schedule_table, check_artifact_liveness,
          check_referential_integrity, check_contradictions, check_adr_revisit,
          check_approval_stamp, check_no_grinding, check_instruction_freeze,
          check_bar_before_result, check_receipts, check_audit_record_field,
          check_sealed_reads, check_sealed_read_field)
_DATED_CHECKS = (check_artifact_liveness, check_adr_revisit)   # the ones `--now` replays


def audit(root: Path, *, now: datetime | None = None) -> list[Finding]:
    out: list[Finding] = []
    for check in CHECKS:
        if check in _DATED_CHECKS:
            out.extend(check(root, now=now))
        else:
            out.extend(check(root))
    return out


def _parse_now(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit the record layer; exit 1 on a red finding.")
    ap.add_argument("--root", type=Path, default=_repo_root(), help="repo root (default: this checkout)")
    ap.add_argument("--now", type=_parse_now, default=None,
                    help="read artifact and record ages, and ADR revisit conditions, as of this date/time instead of now (YYYY-MM-DD or ISO 8601, UTC)")
    args = ap.parse_args(argv)
    root = args.root.resolve()

    classes, _ = classify_workflows(root)
    print(f"record_audit — {root}")
    print("workflows:")
    for name, cls in sorted(classes.items(), key=lambda kv: (kv[1], kv[0])):
        print(f"  {cls:<14} {name}")

    table = ages(root, now=args.now)
    print()
    print("ages — days since last edit, oldest first (WP-24.E; never red):")
    for a in table:
        print(f"  {a}")
    if not table:
        print("  (unreadable — not a git repository, a shallow clone, or nothing before --now)")

    findings = audit(root, now=args.now)
    reds = [f for f in findings if f.red]
    notes = [f for f in findings if not f.red]
    if findings:
        print()
        for f in findings:
            print(f"  {f}")
    print()
    print(f"{len(reds)} red, {len(notes)} report-only")
    return 1 if reds else 0


if __name__ == "__main__":
    sys.exit(main())
