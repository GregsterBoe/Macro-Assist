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
            red(subject, f"nothing on `{ref}` had written it by {now:%Y-%m-%d} — the registry entry or the stage is wrong")
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
# Runner
# ---------------------------------------------------------------------------

CHECKS = (check_workflow_orphans, check_schedule_table, check_artifact_liveness,
          check_referential_integrity, check_contradictions, check_adr_revisit)
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
