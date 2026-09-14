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

The two workflow checks and the liveness check are a pair. 24.A catches a stage
the repo cannot reach; it cannot see a dispatch-only workflow whose *external*
caller has stopped calling — that is what froze the refit for eleven days
(2026-08-31 → 09-11: the cron service was rebuilt without its call, the table
still listed it). 24.B catches that shape from the other end: a reachable stage
that produces nothing. At the 8-day threshold it would have gone red on
2026-09-08, day nine.

A finding is `red` (exit 1) or report-only (printed, never fails — resolved
#23 draws the line: red is for a claim the repo makes twice, differently;
report-only is for a number with no threshold). WP-24.A has only red findings.

Run:
    python .macro-assist/record_audit.py             # exit 1 on any red finding
    python .macro-assist/record_audit.py --root PATH
    python .macro-assist/record_audit.py --now 2026-09-08   # ages as of a date
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
# Runner
# ---------------------------------------------------------------------------

CHECKS = (check_workflow_orphans, check_schedule_table, check_artifact_liveness)


def audit(root: Path, *, now: datetime | None = None) -> list[Finding]:
    out: list[Finding] = []
    for check in CHECKS:
        if check is check_artifact_liveness:
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
                    help="read artifact ages as of this date/time instead of now (YYYY-MM-DD or ISO 8601, UTC)")
    args = ap.parse_args(argv)
    root = args.root.resolve()

    classes, _ = classify_workflows(root)
    print(f"record_audit — {root}")
    print("workflows:")
    for name, cls in sorted(classes.items(), key=lambda kv: (kv[1], kv[0])):
        print(f"  {cls:<14} {name}")

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
