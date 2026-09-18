"""
Tests for `pipeline.yml`'s run modes (IMP-5.4).

`mode: validate` re-runs stage 1 and writes nothing — no LLM call, no note in
the vault, no commit to `main` or `output`. "Writes nothing" is a claim about
six jobs, and the graph does not enforce it on its own:

  * `refit` is deliberately NOT gated on `scoring.result` — a failed note must
    not stop the models being rebuilt (see its comment in the workflow) — and
  * GitHub's `!cancelled()` lets a job run after a *skipped* dependency.

So on a Monday, skipping `daily` alone leaves stage 5 free to run and commit a
refit to `main`. That is exactly the bug these tests were written against: the
first draft of validate mode guarded `daily` only. Every stage that writes
carries the guard explicitly, and this file is what says so.

It also pins where the fragility feed gate lives. It shipped as the last *step*
of `daily` — "the note is already published by then, so a red gate costs
nothing but a notification". Wrong: a failing step fails the job, `scoring`
requires `needs.daily.result == 'success'` and `rebalance` requires `scoring`,
so a dead vol feed on a Monday would have skipped the week's scorecard and the
paper-portfolio rebalance. It is a sibling job now, and the tests below say so.

Pure unit tests — the real workflow files are parsed, nothing is executed.

Run:
    pytest .macro-assist/tests/test_pipeline_modes.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# Every job that writes something a validate run must not touch: the note and
# the vault (stage 2), the scorecard (3), the portfolio (4), the refit commit to
# `main` (5). `plan` and `data_check` are absent on purpose — neither writes a
# file, and the whole point of the mode is that data_check still runs.
WRITING_STAGES = ("daily", "scoring", "rebalance", "refit")


def _load(name: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pipeline() -> dict:
    return _load("pipeline.yml")


def test_validate_is_an_offered_mode(pipeline):
    # `on:` parses as the boolean True in YAML 1.1 — hence the [True] index.
    inputs = pipeline[True]["workflow_dispatch"]["inputs"]
    assert inputs["mode"]["options"] == ["full", "validate"]
    assert inputs["mode"]["default"] == "full", "a dispatch that names no mode runs the pipeline"


@pytest.mark.parametrize("job", WRITING_STAGES)
def test_every_writing_stage_is_guarded_against_validate(pipeline, job):
    """The regression test for the first draft, which guarded `daily` alone."""
    condition = pipeline["jobs"][job].get("if") or ""
    assert "inputs.mode != 'validate'" in condition, (
        f"stage `{job}` would run in validate mode and it writes — "
        "skipping `daily` does not stop it, see this module's docstring"
    )


def test_the_check_stage_still_runs_in_validate_mode(pipeline):
    """A validate run that skipped the data check would validate nothing."""
    assert "if" not in pipeline["jobs"]["data_check"]
    assert "if" not in pipeline["jobs"]["plan"]


def test_validate_makes_the_vol_legs_decide_the_run(pipeline):
    """On a normal run a dead vol leg is a WARN — it costs the composite its
    label, never the note. On a run dispatched to ask about it, it is the
    answer, so it has to be able to fail the run."""
    strict = pipeline["jobs"]["data_check"]["with"]["strict_feeds"]
    assert "inputs.mode == 'validate'" in str(strict)


def test_the_check_stage_accepts_the_strictness_it_is_passed():
    """`pipeline.yml` passing an input the stage does not declare is a silent
    no-op — the run would go green with the leg still dead."""
    check = _load("macro_data_check.yml")
    for trigger in ("workflow_call", "workflow_dispatch"):
        assert "strict_feeds" in check[True][trigger]["inputs"], trigger
    run = check["jobs"]["data-check"]["steps"][-1]["run"]
    assert "--fetch-only" in run and "--strict-feeds" in run


def test_the_run_name_says_when_a_run_wrote_nothing(pipeline):
    """A validate run and a real run must not look the same in the run list."""
    assert "VALIDATE" in pipeline["run-name"]


# ---------------------------------------------------------------------------
# The fragility feed gate must be able to fail WITHOUT taking the weekly
# stages with it. See the module docstring — this is the shape it shipped in
# and had to be moved out of.
# ---------------------------------------------------------------------------

WEEKLY_STAGES = ("scoring", "rebalance", "refit")


def test_the_feed_gate_is_its_own_job(pipeline):
    gate = pipeline["jobs"]["feed_gate"]
    assert gate["needs"] == ["plan", "daily"]
    # It judges a run that actually wrote a reading; a failed note writes none.
    assert "needs.daily.result == 'success'" in gate["if"]


@pytest.mark.parametrize("job", WEEKLY_STAGES)
def test_no_weekly_stage_depends_on_the_feed_gate(pipeline, job):
    """A dead vol feed must not cost the week's scorecard or the rebalance."""
    spec = pipeline["jobs"][job]
    assert "feed_gate" not in (spec.get("needs") or [])
    assert "feed_gate" not in (spec.get("if") or "")


def test_the_feed_gate_is_not_a_step_inside_the_daily_stage():
    """The regression this file exists for: as a step it fails `daily`, and
    `scoring` is gated on `daily.result == 'success'`."""
    daily = _load("macro_daily.yml")
    steps = daily["jobs"]["generate-note"]["steps"]
    for step in steps:
        assert "feed_audit" not in (step.get("run") or ""), (
            "the feed gate is back inside the daily job — a red gate would skip "
            "scoring and rebalance, see this module's docstring"
        )


def test_the_gate_reads_the_run_s_pinned_date(pipeline):
    """ADR-0013: the date is resolved once by `plan`; no stage derives its own."""
    run = pipeline["jobs"]["feed_gate"]["steps"][-1]["run"]
    assert "needs.plan.outputs.asof" in run
