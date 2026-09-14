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

All pure unit tests — no network. The liveness tests shell out to `git`.

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
    """A synthetic checkout with no soft-killed pins and no registered
    artifacts; tests that need either pass their own. It is a git repo, so the
    liveness check has something to read and reports nothing."""
    monkeypatch.setattr(ra, "SOFT_KILLED_WORKFLOWS", frozenset())
    monkeypatch.setattr(ra, "ARTIFACTS", ())
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
    findings = ra.check_workflow_orphans(_REPO) + ra.check_schedule_table(_REPO)
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
