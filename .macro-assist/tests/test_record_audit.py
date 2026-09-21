"""
Tests for record_audit.py (Phase 24 — the record layer's audit).

WP-24.A: every workflow is the entry point, a `needs:`-ordered stage of it,
dispatch-only, CI, or pinned soft-killed; the external schedule table names
only pipeline.yml. Each finding is driven on its own from a synthetic tree,
and the real checkout is asserted clean — that assertion *is* the guard when
the suite runs, the workflow `record_audit.yml` being the same check in CI.

WP-24.B: every registered artifact's last-changed commit is younger than its
cadence, read from git on the branch the stage pushes to. Driven from
synthetic git repos with pinned commit dates and an explicit clock, so the
suite is not a function of what day it is; the real checkout is asserted
only for *shape* (every registry entry names something that exists on its
branch) — its ages are the script's business in CI, not a unit test's.

WP-24.C: every KB-###, ADR-#### and WP-##.x cited under docs/ resolves; ADR
numbering is contiguous, unique and never deleted from history; the inbox
holds one item per number and none that resolved.md also holds; every
`todo.md #N` / `resolved.md #N` pointer lands. Driven from a synthetic docs
tree, one defect at a time; the real checkout is asserted clean, since this
check does not depend on the date.

WP-24.D: every phase's status is one class wherever the record states it —
the board, the roadmap's heading and phase table, CLAUDE.md's Current-state
table — and that table's version row is versions.py's. Red with a pin
(resolved #23): the pin names the pair against an open todo.md item, and a
pin whose sources agree again is itself red. Driven from a synthetic board +
roadmap + CLAUDE.md; the real checkout is asserted clean.

WP-24.E: days since each open todo.md item and each board row was last
edited, per line from `git blame`, oldest first — a table, never a finding.
Driven from a synthetic repo with pinned commit dates and an explicit clock;
the real checkout is asserted for shape only (every open item has a row).

All pure unit tests — no network. The liveness and ADR-history tests shell
out to `git`.

Run:
    pytest .macro-assist/tests/test_record_audit.py -v
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import record_audit as ra

_REPO = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# A synthetic repo: workflows + the operations page's schedule table
# ---------------------------------------------------------------------------

PIPELINE_OK = """
name: Macro Pipeline
on:
  schedule:
    - cron: "37 14 * * 1-5"
  workflow_dispatch:
jobs:
  plan:
    runs-on: ubuntu-latest
    steps: [{run: "true"}]
  daily:
    needs: plan
    uses: ./.github/workflows/daily.yml
  refit:
    needs: [plan, daily]
    uses: ./.github/workflows/refit.yml
"""
STAGE = "name: S\non:\n  workflow_call:\n  workflow_dispatch:\njobs:\n  j: {runs-on: ubuntu-latest, steps: [{run: 'true'}]}\n"
DISPATCH_ONLY = "name: D\non:\n  workflow_dispatch:\njobs:\n  j: {runs-on: ubuntu-latest, steps: [{run: 'true'}]}\n"
CI = "name: Docs\non:\n  push:\n    branches: [main]\n  pull_request:\n  workflow_dispatch:\njobs:\n  j: {runs-on: ubuntu-latest, steps: [{run: 'true'}]}\n"
SCHEDULE_TABLE = """# Operations

### The schedule

| Slot | Cron (UTC) | Call |
|---|---|---|
| Daily pipeline | `23 6 * * 1-5` | `pipeline.yml`, `source=cron-primary` |
| Catch-up | `47 10 * * 1-5` | `pipeline.yml`, `source=cron-catchup` |

### The backstop
"""


# ---------------------------------------------------------------------------
# git helpers — commits with pinned dates, so ages are exact
# ---------------------------------------------------------------------------

T0 = datetime(2026, 8, 31, 0, 9, tzinfo=timezone.utc)   # the last refit before the freeze


def _git(root: Path, *args: str, date: datetime | None = None) -> str:
    env = dict(os.environ,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    if date is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date.isoformat()
    r = subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _init(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "root", date=T0 - timedelta(days=30))


def _commit(root: Path, rel: str, date: datetime, *, branch: str = "main", msg: str = "update") -> str:
    """Write `rel` on `branch` (created orphan if new) and commit it at `date`; returns the short hash."""
    if branch != _git(root, "branch", "--show-current"):
        exists = _git(root, "branch", "--list", branch)
        _git(root, "checkout", "-q", branch) if exists else _git(root, "checkout", "-q", "--orphan", branch)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{msg} {date.isoformat()}\n")
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", msg, date=date)
    return _git(root, "rev-parse", "--short", "HEAD")


def _art(path: str, branch: str = "main", max_age_days: float = 8) -> tuple[ra.Artifact, ...]:
    return (ra.Artifact(path, branch, max_age_days, "the stage"),)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A synthetic checkout with no pins and no registered artifacts; tests
    that need any pass their own. It is a git repo, so the
    liveness check has something to read and reports nothing."""
    monkeypatch.setattr(ra, "SOFT_KILLED_WORKFLOWS", frozenset())
    monkeypatch.setattr(ra, "ARTIFACTS", ())
    monkeypatch.setattr(ra, "RESERVED_KB_NUMBERS", frozenset())
    monkeypatch.setattr(ra, "KNOWN_ITEM_COLLISIONS", frozenset())
    monkeypatch.setattr(ra, "KNOWN_CONTRADICTIONS", {})
    _init(tmp_path)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "pipeline.yml").write_text(PIPELINE_OK)
    (wf / "daily.yml").write_text(STAGE)
    (wf / "refit.yml").write_text(STAGE)
    (wf / "smoke.yml").write_text(DISPATCH_ONLY)
    (wf / "docs.yml").write_text(CI)
    ops = tmp_path / "docs" / "reference"
    ops.mkdir(parents=True)
    (ops / "operations.md").write_text(SCHEDULE_TABLE)
    return tmp_path


def _wf(repo: Path, name: str, text: str) -> None:
    (repo / ".github" / "workflows" / name).write_text(text)


def _reds(findings: list[ra.Finding]) -> list[str]:
    return [f.subject + ": " + f.message for f in findings if f.red]


# ---------------------------------------------------------------------------
# Clean tree, classification
# ---------------------------------------------------------------------------

def test_clean_tree_has_no_findings(repo):
    classes, findings = ra.classify_workflows(repo, soft_killed=frozenset())
    assert findings == []
    assert classes == {
        "pipeline.yml": "entry-point",
        "daily.yml": "stage", "refit.yml": "stage",
        "smoke.yml": "dispatch-only",
        "docs.yml": "ci",
    }
    assert ra.audit(repo) == []


# ---------------------------------------------------------------------------
# Each red finding, on its own
# ---------------------------------------------------------------------------

def test_own_schedule_outside_pipeline_is_red(repo):
    _wf(repo, "refit.yml", STAGE.replace("on:\n", "on:\n  schedule:\n    - cron: '0 22 * * 0'\n"))
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    assert len(reds) == 1 and reds[0].startswith("refit.yml: carries its own `schedule:`")


def test_callable_workflow_nothing_calls_is_red_unless_pinned(repo):
    _wf(repo, "emit.yml", STAGE)   # workflow_call, never wired into pipeline.yml
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    assert len(reds) == 1 and reds[0].startswith("emit.yml: has `workflow_call` but no pipeline.yml stage calls it")
    classes, findings = ra.classify_workflows(repo, soft_killed=frozenset({"emit.yml"}))
    assert findings == [] and classes["emit.yml"] == "soft-killed"


def test_pin_is_held_exactly_in_both_directions(repo):
    # restored: wired back in as a stage but still pinned
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset({"refit.yml"}))[1])
    assert len(reds) == 1 and "still pinned as soft-killed" in reds[0]
    # pinned but the file dropped its workflow_call
    _wf(repo, "emit.yml", DISPATCH_ONLY)
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset({"emit.yml"}))[1])
    assert len(reds) == 1 and "the pin is no longer needed" in reds[0]
    # pinned but no such file
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset({"gone.yml"}))[1])
    assert len(reds) == 1 and reds[0].startswith("gone.yml: pinned as soft-killed but no such workflow file")


def test_pipeline_job_using_a_missing_file_is_red(repo):
    _wf(repo, "pipeline.yml", PIPELINE_OK.replace("refit.yml", "missing.yml"))
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    # the dangling job, and refit.yml is now a callable nothing reaches
    assert any("missing.yml, which does not exist" in r for r in reds)
    assert any(r.startswith("refit.yml: has `workflow_call`") for r in reds)
    assert len(reds) == 2


def test_stage_without_needs_is_red(repo):
    _wf(repo, "pipeline.yml", PIPELINE_OK.replace("    needs: [plan, daily]\n", ""))
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    assert len(reds) == 1 and "no `needs:`" in reds[0]


def test_stage_without_workflow_call_is_red(repo):
    _wf(repo, "refit.yml", DISPATCH_ONLY)
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    assert len(reds) == 1 and "no `workflow_call` trigger" in reds[0]


def test_unknown_trigger_and_no_trigger_and_bad_yaml_are_red(repo):
    _wf(repo, "chained.yml", "name: C\non:\n  workflow_run:\n    workflows: [Docs]\njobs: {}\n")
    _wf(repo, "empty.yml", "name: E\njobs: {}\n")
    _wf(repo, "broken.yml", "name: [\n")
    classes, findings = ra.classify_workflows(repo, soft_killed=frozenset())
    reds = _reds(findings)
    assert len(reds) == 3
    assert any(r.startswith("chained.yml: trigger(s) ['workflow_run']") for r in reds)
    assert any(r.startswith("empty.yml: no `on:`") for r in reds)
    assert any(r.startswith("broken.yml: unparsable") for r in reds)
    assert {classes[n] for n in ("chained.yml", "empty.yml", "broken.yml")} == {"orphan"}


def test_missing_pipeline_is_red(repo):
    (repo / ".github" / "workflows" / "pipeline.yml").unlink()
    reds = _reds(ra.classify_workflows(repo, soft_killed=frozenset())[1])
    assert reds == ["pipeline.yml: missing or unparsable — there is no entry point to audit against (ADR-0013)"]


# ---------------------------------------------------------------------------
# The external schedule, as declared
# ---------------------------------------------------------------------------

def test_schedule_table_is_read(repo):
    assert ra.schedule_table_calls(repo) == ["pipeline.yml", "pipeline.yml"]
    assert ra.check_schedule_table(repo) == []


def test_schedule_slot_calling_another_workflow_is_red(repo):
    """The refit's Sunday slot as operations.md listed it until 2026-09-11."""
    ops = repo / "docs" / "reference" / "operations.md"
    ops.write_text(SCHEDULE_TABLE.replace(
        "\n### The backstop",
        "| Weekly refit | `0 22 * * 0` | `macro_weekly_refit.yml`, `source=cron-refit` |\n\n### The backstop"))
    reds = _reds(ra.check_schedule_table(repo))
    assert len(reds) == 1 and "calls `macro_weekly_refit.yml`" in reds[0]


def test_missing_schedule_table_is_red(repo):
    ops = repo / "docs" / "reference" / "operations.md"
    ops.write_text("# Operations\n\nno table here\n")
    reds = _reds(ra.check_schedule_table(repo))
    assert len(reds) == 1 and "no table under" in reds[0]
    ops.unlink()
    assert len(_reds(ra.check_schedule_table(repo))) == 1


# ---------------------------------------------------------------------------
# The runner, and the real checkout
# ---------------------------------------------------------------------------

def test_main_exits_nonzero_on_red_and_prints_the_finding(repo, capsys):
    _wf(repo, "emit.yml", STAGE)
    rc = ra.main(["--root", str(repo)])
    out = capsys.readouterr().out
    assert rc == 1 and "RED   workflow-orphans  emit.yml" in out and "1 red, 0 report-only" in out
    (repo / ".github" / "workflows" / "emit.yml").unlink()
    assert ra.main(["--root", str(repo)]) == 0


def test_this_checkout_is_clean():
    """The guard itself. A new workflow with its own cron, a callable stage
    nothing reaches, or a schedule slot that is not pipeline.yml fails here.
    The liveness check is deliberately *not* run: its answer depends on the
    date, and a unit suite that fails because the pipeline had a bad week
    would be noise where the script in CI is the signal."""
    findings = (ra.check_workflow_orphans(_REPO) + ra.check_schedule_table(_REPO)
                + ra.check_referential_integrity(_REPO) + ra.check_contradictions(_REPO))
    assert not [f for f in findings if f.red], "\n".join(str(f) for f in findings)


def test_the_soft_killed_pins_are_the_adr_0015_arms():
    """Each pinned workflow is soft-killed per ADR-0015 — its own header says
    so — and the pins are exactly the callable-but-unwired set."""
    classes, _ = ra.classify_workflows(_REPO)
    assert {n for n, c in classes.items() if c == "soft-killed"} == set(ra.SOFT_KILLED_WORKFLOWS)
    for name in ra.SOFT_KILLED_WORKFLOWS:
        text = (_REPO / ".github" / "workflows" / name).read_text()
        assert "WAS stage" in text and "pipeline.yml" in text, f"{name} does not say it was a stage"


def test_the_pipeline_is_the_only_scheduled_workflow():
    classes, _ = ra.classify_workflows(_REPO)
    assert [n for n, c in classes.items() if c == "entry-point"] == ["pipeline.yml"]
    assert "orphan" not in classes.values()


# ---------------------------------------------------------------------------
# WP-24.B — artifact liveness
# ---------------------------------------------------------------------------

def test_fresh_artifact_is_clean_and_stale_one_is_red(repo):
    h = _commit(repo, "data/table.json", T0, msg="refit")
    arts = _art("data/table.json")
    assert ra.check_artifact_liveness(repo, now=T0 + timedelta(days=7, hours=23), artifacts=arts) == []
    [f] = ra.check_artifact_liveness(repo, now=T0 + timedelta(days=8, hours=12), artifacts=arts)
    assert f.red and f.check == "artifact-liveness" and f.subject == "main:data/table.json"
    assert "8.5 days ago" in f.message and h in f.message and "refit" in f.message


def test_age_comes_from_git_not_mtime(repo):
    """A fresh clone rewrites every mtime to now; the check must not notice."""
    _commit(repo, "data/table.json", T0)
    path = repo / "data" / "table.json"
    assert datetime.now(timezone.utc).timestamp() - path.stat().st_mtime < 60     # mtime says "just now"
    findings = ra.check_artifact_liveness(repo, now=datetime.now(timezone.utc), artifacts=_art("data/table.json"))
    assert len(findings) == 1 and "days ago" in findings[0].message               # git says T0


def test_the_frozen_refit_replayed(repo):
    """Refit lands 2026-08-31, nothing after. Day 8 (09-07) is quiet, day 9
    (09-08) is red — the roadmap's claim, on a synthetic tree."""
    _commit(repo, "data/table.json", T0 - timedelta(days=7), msg="refit: 2026-08-24")
    _commit(repo, "data/table.json", T0, msg="refit: 2026-08-31")
    arts = _art("data/table.json")
    noon = lambda d: datetime(2026, 9, d, 12, tzinfo=timezone.utc)
    assert ra.check_artifact_liveness(repo, now=noon(7), artifacts=arts) == []
    assert len(ra.check_artifact_liveness(repo, now=noon(8), artifacts=arts)) == 1
    assert len(ra.check_artifact_liveness(repo, now=noon(11), artifacts=arts)) == 1
    _commit(repo, "data/table.json", datetime(2026, 9, 11, 17, tzinfo=timezone.utc), msg="refit: 2026-09-11")
    assert ra.check_artifact_liveness(repo, now=noon(12), artifacts=arts) == []


def test_now_replays_history_rather_than_reading_todays_commit(repo):
    """`--now` sees only commits up to that clock — otherwise every replay
    would compare a later commit with an earlier date and pass."""
    _commit(repo, "data/table.json", T0)
    _commit(repo, "data/table.json", T0 + timedelta(days=14))
    arts = _art("data/table.json")
    assert ra.check_artifact_liveness(repo, now=T0 + timedelta(days=15), artifacts=arts) == []
    [f] = ra.check_artifact_liveness(repo, now=T0 + timedelta(days=10), artifacts=arts)
    assert "10.0 days ago" in f.message


def test_output_branch_and_glob_pathspec(repo):
    """The note lands on the orphan `output` branch under a month directory;
    a glob pathspec finds the latest one wherever it is."""
    _commit(repo, "08-August/2026-08-28-Friday-macro.md", T0 - timedelta(days=3), branch="output", msg="note")
    _commit(repo, "09-September/2026-09-01-Tuesday-macro.md", T0 + timedelta(days=1), branch="output", msg="note")
    _git(repo, "checkout", "-q", "main")
    arts = _art(":(glob)*/*-macro.md", "output", 4)
    assert ra.check_artifact_liveness(repo, now=T0 + timedelta(days=4), artifacts=arts) == []
    [f] = ra.check_artifact_liveness(repo, now=T0 + timedelta(days=6), artifacts=arts)
    assert f.subject == "output::(glob)*/*-macro.md" and "5.0 days ago" in f.message


def test_ages_are_read_from_the_remote_branch_when_present(repo):
    """A feature branch cut before this week's refit must not fail for it:
    the check reads origin/<branch>, where the bots push, not HEAD."""
    _commit(repo, "data/table.json", T0)
    _git(repo, "checkout", "-q", "-b", "feature")                    # HEAD stops here
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "data/table.json", T0 + timedelta(days=7), msg="refit")
    _git(repo, "update-ref", "refs/remotes/origin/main", "main")     # what a fetch would leave
    _git(repo, "checkout", "-q", "feature")
    arts = _art("data/table.json")
    assert ra.check_artifact_liveness(repo, now=T0 + timedelta(days=10), artifacts=arts) == []
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    _git(repo, "branch", "-f", "main", "feature")                    # local main is stale now
    [f] = ra.check_artifact_liveness(repo, now=T0 + timedelta(days=10), artifacts=arts)
    assert "on `main`" in f.message


def test_missing_branch_and_never_written_are_red(repo):
    _commit(repo, "data/table.json", T0)
    [f] = ra.check_artifact_liveness(repo, now=T0, artifacts=_art("data/table.json", "output"))
    assert "branch `output` is not available" in f.message and "git fetch origin output" in f.message
    [f] = ra.check_artifact_liveness(repo, now=T0, artifacts=_art("data/other.json"))
    assert "nothing on `main` had written it" in f.message


def test_shallow_clone_is_red(repo, tmp_path):
    """Depth-1 clone: every path's last commit is the clone boundary, dated
    whenever it was — the vacuous pass the roadmap warns about, refused."""
    _commit(repo, "data/table.json", T0)
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    [f] = ra.check_artifact_liveness(shallow, now=T0, artifacts=_art("data/table.json"))
    assert "shallow clone" in f.message and "fetch-depth: 0" in f.message


def test_not_a_git_repository_is_red(tmp_path):
    [f] = ra.check_artifact_liveness(tmp_path, now=T0, artifacts=_art("x"))
    assert "not a git repository" in f.message


def test_main_takes_now_and_fails_on_a_stale_artifact(repo, monkeypatch, capsys):
    _commit(repo, "data/table.json", T0)
    monkeypatch.setattr(ra, "ARTIFACTS", _art("data/table.json"))
    assert ra.main(["--root", str(repo), "--now", "2026-09-07"]) == 0
    assert ra.main(["--root", str(repo), "--now", "2026-09-09"]) == 1
    out = capsys.readouterr().out
    assert "RED   artifact-liveness  main:data/table.json" in out and "1 red, 0 report-only" in out


def test_the_registry_names_what_the_pipeline_writes():
    """Shape only, on the real checkout: every entry's branch resolves and
    something on it has written the path. Ages are CI's question."""
    for art in ra.ARTIFACTS:
        ref = ra._resolve_ref(_REPO, art.branch)
        assert ref is not None, f"{art.branch} not fetched — `git fetch origin {art.branch}`"
        assert ra.last_changed(_REPO, ref, art.path) is not None, f"{art.path} never written on {ref}"
        assert art.max_age_days >= 4, "the daily note is the tightest cadence the pipeline has"
    assert {a.branch for a in ra.ARTIFACTS} == {"main", "output"}


# ---------------------------------------------------------------------------
# WP-24.C — referential integrity
# ---------------------------------------------------------------------------

KB = """# Knowledge base

## KB-001 — first
text

## KB-002 — second
text citing [KB-001].
"""
ROADMAP = "# Roadmap\n\n### WP-30.A — open work\n\nSee [KB-002] and ADR-0002.\n"
ARCHIVE = "# Archive\n\n1. **WP-29.B — done.** (→ KB-001)\n"
TODO_MD = "# TODO\n\n### Open decision #3 — a call\n\n### Carried finding #5b — a caveat\n"
RESOLVED_MD = "# Resolved\n\n### RESOLVED 2026-09-14 — #1 the first\n\n### DONE 2026-08-24 — #2 the second\n"
ADR = "# ADR-{n:04d} — {title}\n\nSupersedes nothing.\n"


def _doc(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def record(repo: Path, monkeypatch) -> Path:
    """The `repo` fixture plus a small, consistent docs/ tree: two KB entries,
    two ADRs, one open WP and one archived, an inbox with #3 and #5b open and
    #1/#2 resolved. Clean by construction."""
    _doc(repo, "docs/record/knowledge-base.md", KB)
    _doc(repo, "docs/record/roadmap.md", ROADMAP)
    _doc(repo, "docs/record/roadmap-archive.md", ARCHIVE)
    _doc(repo, "docs/record/todo.md", TODO_MD)
    _doc(repo, "docs/record/resolved.md", RESOLVED_MD)
    _doc(repo, "docs/decisions/ADR-0001-first.md", ADR.format(n=1, title="first"))
    _doc(repo, "docs/decisions/ADR-0002-second.md", ADR.format(n=2, title="second"))
    _doc(repo, "docs/concepts/page.md",
         "Cites [KB-001], ADR-0001, WP-30.A, WP-29.B, `todo.md` #3, `resolved.md` #1 "
         "and [`resolved.md`](resolved.md) #2.\n")
    _doc(repo, "CLAUDE.md", "See `todo.md` #5b and ADR-0002.\n")
    return repo


def _ri(repo: Path) -> list[ra.Finding]:
    return ra.check_referential_integrity(repo)


def test_a_consistent_record_has_no_findings(record):
    assert _ri(record) == []


def test_a_kb_citation_with_no_entry_is_red_with_its_line(record):
    _doc(record, "docs/concepts/page.md", "line one\nline two cites [KB-009] here\n")
    (red,) = _reds(_ri(record))
    assert red.startswith("docs/concepts/page.md:2: KB-009 is cited") and "no such entry" in red


def test_a_reserved_kb_number_is_pinned_and_the_pin_is_held_exactly(record, monkeypatch):
    _doc(record, "docs/concepts/page.md", "KB-009 was reserved and never written.\n")
    assert len(_reds(_ri(record))) == 1
    monkeypatch.setattr(ra, "RESERVED_KB_NUMBERS", frozenset({"009"}))
    assert _ri(record) == []
    # the entry gets written: the pin is now the defect
    _doc(record, "docs/record/knowledge-base.md", KB + "\n## KB-009 — written after all\n")
    (red,) = _reds(_ri(record))
    assert "RESERVED_KB_NUMBERS pins KB-009" in red and "remove the pin" in red


def test_an_adr_citation_with_no_file_is_red(record):
    _doc(record, "docs/concepts/page.md", "Per ADR-0007.\n")
    (red,) = _reds(_ri(record))
    assert "ADR-0007 is cited" in red and "no such file" in red


def test_adr_numbering_is_contiguous_and_unique(record):
    _doc(record, "docs/decisions/ADR-0004-fourth.md", ADR.format(n=4, title="fourth"))
    reds = _reds(_ri(record))
    assert len(reds) == 1 and "gap at ADR-0003" in reds[0] and "convention #11" in reds[0]
    _doc(record, "docs/decisions/ADR-0003-third.md", ADR.format(n=3, title="third"))
    _doc(record, "docs/decisions/ADR-0003-third-again.md", ADR.format(n=3, title="third again"))
    (red,) = _reds(_ri(record))
    assert "ADR-0003 has 2 files" in red and "ADR-0003-third-again.md" in red


def test_an_adr_deleted_from_history_is_red_and_a_slug_rename_is_not(record):
    for rel in ("docs/decisions/ADR-0001-first.md", "docs/decisions/ADR-0002-second.md",
                "docs/decisions/ADR-0003-third.md"):
        _doc(record, rel, ADR.format(n=int(rel.split("-")[1]), title="x"))
    _git(record, "add", "docs")
    _git(record, "commit", "-q", "-m", "three ADRs", date=T0)
    assert _ri(record) == []
    # renaming the slug keeps the number: fine
    _git(record, "mv", "docs/decisions/ADR-0002-second.md", "docs/decisions/ADR-0002-the-second.md")
    _git(record, "commit", "-q", "-m", "rename slug", date=T0 + timedelta(hours=1))
    assert _ri(record) == []
    # deleting the last ADR leaves the numbering contiguous — only history says
    _git(record, "rm", "-q", "docs/decisions/ADR-0003-third.md")
    _git(record, "commit", "-q", "-m", "delete an ADR", date=T0 + timedelta(hours=2))
    (red,) = _reds(_ri(record))
    assert "ADR-0003 was deleted in history" in red and "never delete" in red


def test_a_wp_named_nowhere_in_the_roadmaps_is_red(record):
    _doc(record, "docs/concepts/page.md", "WP-29.B is archived; WP-31.Z is invented.\n")
    (red,) = _reds(_ri(record))
    assert "WP-31.Z is cited" in red and "roadmap-archive.md" in red


def test_todo_pointers_land_or_are_red_and_resolved_ones_are_report_only(record):
    _doc(record, "docs/concepts/page.md",
         "`todo.md` #3 is open; `todo.md` #1 resolved; todo.md (#2 too; `todo.md` #40 is nowhere.\n")
    findings = _ri(record)
    assert _reds(findings) == ["docs/concepts/page.md:1: todo.md #40 heads no item in todo.md or resolved.md"]
    (note,) = [f for f in findings if not f.red]
    assert note.subject == "docs/concepts/page.md"
    assert "cites todo.md #1, #2 — resolved since" in note.message


def test_a_resolved_pointer_with_no_item_is_red(record):
    _doc(record, "docs/concepts/page.md", "Closed as `resolved.md` #9.\n")
    (red,) = _reds(_ri(record))
    assert red == "docs/concepts/page.md:1: resolved.md #9 heads no resolved item"


def test_one_number_one_open_item(record):
    _doc(record, "docs/record/todo.md", TODO_MD + "\n### Carried finding #3 — a second #3\n")
    (red,) = _reds(_ri(record))
    assert red == "docs/record/todo.md: #3 heads 2 open items in todo.md — one number, one item"


def test_an_open_and_a_resolved_item_sharing_a_number_is_red_unless_pinned(record, monkeypatch):
    _doc(record, "docs/record/resolved.md", RESOLVED_MD + "\n### RESOLVED 2026-09-14 — #3 (carried) the other #3\n")
    (red,) = _reds(_ri(record))
    assert "#3 heads an open item in todo.md and a resolved one" in red
    monkeypatch.setattr(ra, "KNOWN_ITEM_COLLISIONS", frozenset({"3"}))
    assert _ri(record) == []
    # the open one closes: the pin outlives its collision and is red itself
    _doc(record, "docs/record/todo.md", "# TODO\n\n### Carried finding #5b — a caveat\n")
    (red,) = _reds(_ri(record))
    assert "KNOWN_ITEM_COLLISIONS pins #3" in red and "remove the pin" in red


def test_the_pins_describe_this_checkout():
    """Held exactly, on the real tree: KB-008 is the number the KB names in
    prose and never defines, and #7 heads one open item and one resolved."""
    kb = (_REPO / ra.KNOWLEDGE_BASE).read_text()
    assert ra.RESERVED_KB_NUMBERS == {"008"}
    assert "KB-008" in kb and "008" not in ra._KB_HEADING_RE.findall(kb)
    assert ra.KNOWN_ITEM_COLLISIONS == {"7"}
    assert "7" in ra._ITEM_HEADING_RE.findall((_REPO / ra.TODO).read_text())
    assert "7" in ra._RESOLVED_HEADING_RE.findall((_REPO / ra.RESOLVED).read_text())


# ---------------------------------------------------------------------------
# WP-24.D — contradiction surfacing
# ---------------------------------------------------------------------------

BOARD_MD = """# Board

## Active

### Phase 30 — The thing 🟢 LIVE, sealed
- **Where:** `roadmap.md` (Phase 32 — closed; the bullet's bold span names no phase)

## Queued / dormant

- **Phase 31 — The other** ⏸ — parked, nothing runs

## Recently closed

### Phase 32 — The done one ✅ CLOSED 2026-09-01
"""
ROADMAP_STATUS_MD = """# Roadmap

| Phase | What it added | Status |
|-------|---------------|--------|
| 30 | The thing | 🟢 Open 2026-09-08 — sealed |
| 32 | The done one | ✅ Closed 2026-09-01 |

## The thing (Phase 30) — *the scorer follows the product* 🟢 OPEN

## The other (Phase 31) — *no marker in this heading*

## The done one (Phase 32) ✅ CLOSED 2026-09-01
"""
CLAUDE_MD = """# CLAUDE.md

## Current state

| | |
|---|---|
| **Version** | **v9.9** (2026-09-13) — the measured line |
| **Live experiment** | Phase 30 the thing — bar sealed, first read ~2027-05 |
| **Queued** | Phase 32 closed 2026-09-01 (its gate had no metric); Phase 31 dormant |

The board wins.

## Gotchas
"""
VERSIONS_PY = 'PIPELINE_VERSION: str = "v9.9"\n'


@pytest.fixture
def statuses(repo: Path) -> Path:
    """The `repo` fixture plus a board, a roadmap, a CLAUDE.md and a
    versions.py that agree: Phase 30 open, 31 dormant, 32 closed, v9.9."""
    _doc(repo, "docs/record/active-experiments.md", BOARD_MD)
    _doc(repo, "docs/record/roadmap.md", ROADMAP_STATUS_MD)
    _doc(repo, "docs/record/todo.md", TODO_MD)
    _doc(repo, "CLAUDE.md", CLAUDE_MD)
    _doc(repo, ".macro-assist/versions.py", VERSIONS_PY)
    return repo


def _cx(repo: Path) -> list[ra.Finding]:
    return ra.check_contradictions(repo)


def _edit(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new))


def test_a_consistent_record_has_no_contradictions(statuses):
    assert _cx(statuses) == []
    # every source was read: three phases, each with its claims
    assert set(ra.board_claims(statuses)) == {"30", "31", "32"}
    assert set(ra.roadmap_claims(statuses)) == {"30", "32"}        # 31's heading has no marker
    assert {p: c[0].cls for p, c in ra.claude_md_claims(statuses).items()} == {
        "30": "open", "31": "dormant", "32": "closed"}


def test_a_stale_table_row_is_red_and_the_pair_is_printed(statuses):
    """The shape found on the real tree 2026-09-21: the roadmap's phase table
    still said Draft a week after the board, the roadmap's own heading and
    CLAUDE.md said in progress."""
    _edit(statuses, "docs/record/roadmap.md", "| 30 | The thing | 🟢 Open 2026-09-08 — sealed |",
          "| 30 | The thing | ⏸ Draft 2026-09-08 — first step WP-30.A |")
    (f,) = _cx(statuses)
    assert f.red and f.subject == "Phase 30"
    assert 'docs/record/active-experiments.md:5 says "🟢 LIVE, sealed"' in f.message
    assert 'docs/record/roadmap.md:5 says "⏸ Draft 2026-09-08 — first step WP-30.A"' in f.message
    assert 'docs/record/roadmap.md:8 says "🟢 OPEN"' in f.message
    assert 'CLAUDE.md:8 (Live experiment row) says "Phase 30 the thing — bar sealed' in f.message
    assert "CLAUDE.md says who wins" in f.message


def test_wording_within_a_class_is_not_a_contradiction(statuses):
    """SHIPPED, LIVE, IN PROGRESS and OPEN are one claim; so are CLOSED,
    RESOLVED and COMPLETE. Only the class is compared."""
    _edit(statuses, "docs/record/active-experiments.md", "🟢 LIVE, sealed", "🟡 IN PROGRESS — 30.A running")
    _edit(statuses, "docs/record/roadmap.md", "🟢 OPEN", "🔍 OPEN — drafted")
    _edit(statuses, "docs/record/roadmap.md", "The done one (Phase 32) ✅ CLOSED", "The done one (Phase 32) ❌ DROPPED")
    assert _cx(statuses) == []


def test_a_heading_with_no_marker_claims_nothing_and_one_with_a_marker_does(statuses):
    assert _cx(statuses) == []                      # Phase 31's heading is bare; the board's ⏸ stands alone
    _edit(statuses, "docs/record/roadmap.md", "*no marker in this heading*", "*now closed* ✅ CLOSED")
    (f,) = _cx(statuses)
    assert f.red and f.subject == "Phase 31"
    assert 'roadmap.md:10 says "✅ CLOSED"' in f.message and 'says "⏸ — parked, nothing runs"' in f.message


def test_claude_md_reads_the_status_word_in_the_clause_and_skips_asides(statuses):
    """A phase named in the Current-state table with no status word is
    claimed current; the word is looked for in the clause after the name,
    with parenthesised and backticked spans removed first."""
    # the Live-experiment row names Phase 30 as current; close it everywhere else → red from CLAUDE.md
    _edit(statuses, "docs/record/active-experiments.md", "### Phase 30 — The thing 🟢 LIVE, sealed",
          "### Phase 30 — The thing ✅ CLOSED 2026-09-20")
    _edit(statuses, "docs/record/roadmap.md", "| 30 | The thing | 🟢 Open 2026-09-08 — sealed |",
          "| 30 | The thing | ✅ Closed 2026-09-20 |")
    _edit(statuses, "docs/record/roadmap.md", "*the scorer follows the product* 🟢 OPEN",
          "*the scorer follows the product* ✅ CLOSED")
    (f,) = _cx(statuses)
    assert f.red and f.subject == "Phase 30" and "(Live experiment row)" in f.message
    # an aside or a code span holding "closed" does not close the phase
    _edit(statuses, "CLAUDE.md", "Phase 30 the thing — bar sealed, first read ~2027-05",
          "Phase 30 — harness built (its `closed` rival ran); register holds H-1 `closed`")
    assert [f.subject for f in _cx(statuses)] == ["Phase 30"]
    _edit(statuses, "CLAUDE.md", "Phase 30 — harness built", "Phase 30 closed 2026-09-20 — harness built")
    assert _cx(statuses) == []
    # a decimal point and a date do not end the clause; a sentence does
    _edit(statuses, "CLAUDE.md", "Phase 32 closed 2026-09-01 (its gate had no metric); Phase 31 dormant",
          "Phase 32 at 18.3. Closed for good; Phase 31 dormant")
    (f,) = _cx(statuses)
    assert f.subject == "Phase 32" and "(Queued row)" in f.message


def test_a_contradiction_is_pinned_against_an_open_todo_item_and_the_pin_is_held_exactly(statuses, monkeypatch):
    _edit(statuses, "docs/record/roadmap.md", "| 30 | The thing | 🟢 Open 2026-09-08 — sealed |",
          "| 30 | The thing | ⏸ Draft 2026-09-08 |")
    assert [f.red for f in _cx(statuses)] == [True]
    # pinned to the open #3: printed, not red, and the pair is still there
    monkeypatch.setattr(ra, "KNOWN_CONTRADICTIONS", {"Phase 30": "3"})
    (f,) = _cx(statuses)
    assert not f.red and "pinned, todo.md #3" in f.message
    assert 'says "⏸ Draft 2026-09-08"' in f.message and 'says "🟢 LIVE, sealed"' in f.message
    # pinned to a number that heads no open item: red — the pin must appear in todo.md
    monkeypatch.setattr(ra, "KNOWN_CONTRADICTIONS", {"Phase 30": "4"})
    (f,) = _cx(statuses)
    assert f.red and "todo.md #4, which heads no open item" in f.message
    # the sources agree again but the pin is still there: red
    monkeypatch.setattr(ra, "KNOWN_CONTRADICTIONS", {"Phase 30": "3"})
    _edit(statuses, "docs/record/roadmap.md", "⏸ Draft 2026-09-08", "🟢 Open 2026-09-08")
    (f,) = _cx(statuses)
    assert f.red and "pins it to todo.md #3 but every source now agrees (open) — remove the pin" in f.message


def test_the_version_row_must_match_versions_py(statuses):
    _edit(statuses, ".macro-assist/versions.py", '"v9.9"', '"v10.0"')
    (f,) = _cx(statuses)
    assert f.red and f.subject == "CLAUDE.md:7"
    assert "says v9.9 and versions.py says v10.0" in f.message


def test_the_contradiction_pins_name_open_items():
    """Resolved #23: a pin must appear in todo.md. Vacuous while the pin
    table is empty; the check itself enforces it on a populated one."""
    open_items = set(ra._ITEM_HEADING_RE.findall((_REPO / ra.TODO).read_text()))
    for subject, item in ra.KNOWN_CONTRADICTIONS.items():
        assert subject.startswith("Phase "), subject
        assert item in open_items, f"{subject} is pinned to todo.md #{item}, which heads no open item"



# ---------------------------------------------------------------------------
# WP-24.E — ages, from git
# ---------------------------------------------------------------------------

AGED_TODO = """# TODO

## A section

### Open decision #3 — an old call

Body of three.

### Carried finding #5b — a caveat

Body of five.

### The original question, kept for its admission rule

Belongs to #5b.

## Housekeeping

Not an item.
"""

AGED_BOARD = """# Board

### Changelog — newest first

| Date | What |
|---|---|
| **2026-09-14** | not a row |

## Active

### Phase 30 — Something live 🟢 LIVE
- **Tests:** a question.
- **Where:** here.

## Queued / dormant

- **Retire the *directional* scorer** ⏸ — one line.
- **Phase 31 — dormant** ⏸ — with a continuation
  line under it.

## Recently closed

### Phase 29 — Done ✅ CLOSED
- **Where:** there.
"""


def _commit_text(root: Path, rel: str, text: str, date: datetime, msg: str = "update") -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", msg, date=date)
    return _git(root, "rev-parse", "--short", "HEAD")


@pytest.fixture
def aged(repo: Path) -> Path:
    """todo.md and the board written 20 days before T0, then #3's body
    edited 2 days before it."""
    _commit_text(repo, "docs/record/todo.md", AGED_TODO, T0 - timedelta(days=20), "inbox")
    _commit_text(repo, "docs/record/active-experiments.md", AGED_BOARD, T0 - timedelta(days=20), "board")
    _commit_text(repo, "docs/record/todo.md", AGED_TODO.replace("Body of three.", "Body of three, revised."),
                 T0 - timedelta(days=2), "revise three")
    return repo


def _ages(repo: Path, now: datetime = T0) -> dict[str, ra.Age]:
    return {a.subject: a for a in ra.ages(repo, now=now)}


def test_ages_are_per_item_from_git_and_sorted_oldest_first(aged):
    table = ra.ages(aged, now=T0)
    assert [a.days for a in table] == sorted((a.days for a in table), reverse=True)
    by = {a.subject: a for a in table}
    assert set(by) == {"todo.md #3 — an old call", "todo.md #5b — a caveat",
                       "board: Phase 30 — Something live", "board: Retire the *directional* scorer",
                       "board: Phase 31 — dormant"}
    assert by["todo.md #3 — an old call"].days == pytest.approx(2)
    assert by["todo.md #3 — an old call"].what.endswith(" revise three")
    assert by["todo.md #5b — a caveat"].days == pytest.approx(20)
    assert by["board: Phase 30 — Something live"].days == pytest.approx(20)
    assert by["board: Phase 30 — Something live"].when == T0 - timedelta(days=20)


def test_an_unnumbered_subheading_stays_with_its_item(aged):
    """`### The original question…` under #5b is #5b's text, not a row."""
    _commit_text(aged, "docs/record/todo.md",
                 (aged / "docs/record/todo.md").read_text().replace("Belongs to #5b.", "Belongs to #5b, still."),
                 T0 - timedelta(days=1), "touch the sub-heading")
    by = _ages(aged)
    assert by["todo.md #5b — a caveat"].days == pytest.approx(1)
    assert by["todo.md #3 — an old call"].days == pytest.approx(2)


def test_whitespace_and_a_move_within_the_file_are_not_edits(aged):
    text = (aged / "docs/record/todo.md").read_text()
    # re-indent a line of #5b, and move the #3 block below #5b's
    three = text[text.index("### Open decision #3"):text.index("### Carried finding #5b")]
    moved = text.replace(three, "").replace("## Housekeeping", three + "## Housekeeping")
    moved = moved.replace("Body of five.", "  Body of five.")
    _commit_text(aged, "docs/record/todo.md", moved, T0 - timedelta(days=1), "tidy")
    by = _ages(aged)
    assert by["todo.md #3 — an old call"].days == pytest.approx(2)
    assert by["todo.md #5b — a caveat"].days == pytest.approx(20)


def test_the_board_rows_are_active_sections_and_queued_bullets(aged):
    """The changelog table and Recently closed are not rows; a bullet's
    continuation lines belong to it; bold text with emphasis inside is a
    bullet too."""
    by = _ages(aged)
    assert not [s for s in by if "Changelog" in s or "Phase 29" in s or "2026-09-14" in s]
    board = (aged / "docs/record/active-experiments.md").read_text()
    _commit_text(aged, "docs/record/active-experiments.md", board.replace("line under it.", "line under it, edited."),
                 T0 - timedelta(days=3), "edit the continuation")
    assert _ages(aged)["board: Phase 31 — dormant"].days == pytest.approx(3)
    assert _ages(aged)["board: Retire the *directional* scorer"].days == pytest.approx(20)


def test_now_replays_history_and_an_uncommitted_line_is_age_zero(aged):
    # before the revision landed, #3 was as old as the inbox
    by = _ages(aged, now=T0 - timedelta(days=5))
    assert by["todo.md #3 — an old call"].days == pytest.approx(15)
    assert by["todo.md #3 — an old call"].what.endswith(" inbox")
    # without --now the working tree is read: an edit with no commit yet is
    # zero days old and says so
    path = aged / "docs/record/todo.md"
    path.write_text(path.read_text().replace("Body of five.", "Body of five, uncommitted."))
    by = {a.subject: a for a in ra.ages(aged)}
    a = by["todo.md #5b — a caveat"]
    assert a.what == "uncommitted" and a.days == pytest.approx(0, abs=0.01)
    assert by["todo.md #3 — an old call"].what.endswith(" revise three")


def test_ages_are_empty_where_git_cannot_answer(tmp_path):
    (tmp_path / "docs" / "record").mkdir(parents=True)
    (tmp_path / "docs" / "record" / "todo.md").write_text(AGED_TODO)
    assert ra.ages(tmp_path) == []


def test_main_prints_the_table_and_an_old_item_never_fails(aged, capsys):
    rc = ra.main(["--root", str(aged), "--now", (T0 + timedelta(days=400)).isoformat()])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ages — days since last edit, oldest first" in out
    assert "todo.md #5b — a caveat" in out and " 420.0  " in out
    assert "0 red, 0 report-only" in out


def test_every_open_item_and_live_row_has_an_age():
    """Shape only on the real checkout — the numbers are the script's
    business in CI. Every `### … #N` in todo.md is a row, and so is every
    Active section of the board."""
    table = ra.ages(_REPO)
    subjects = {a.subject for a in table}
    for n in ra._ITEM_HEADING_RE.findall((_REPO / ra.TODO).read_text()):
        assert any(s.startswith(f"todo.md #{n} ") or s == f"todo.md #{n}" for s in subjects), n
    assert any(s.startswith("board: Phase 22") for s in subjects)
    assert [a.days for a in table] == sorted((a.days for a in table), reverse=True)
