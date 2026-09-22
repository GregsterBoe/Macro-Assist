"""
Tests for the date `trigger_pipeline.sh` sends (todo #27).

`pipeline.yml`'s `plan` job resolves the run's date itself when the dispatch
does not carry one, and it resolves it from a cutoff: a run landing before
06:00 UTC is the *previous* day's slot, delivered late. That guess is correct
for a genuinely late delivery and wrong for a primary call that drifts a minute
early — and every observed primary call has landed at 06:00:31-06:00:41 UTC,
about 31 seconds from the wrong side.

The failure it produces is silent, which is what makes it worth a test: the run
writes to yesterday's date, finds yesterday's note already there, no-ops, and
leaves today with no note and every check green.

So the caller says what day it is. These tests pin that it does, that an
explicit date still wins, and — the part that is easy to break — that the date
is sent *only* to the workflow that declares an `asof` input and guesses
without one. GitHub rejects a whole dispatch with 422 for an input the target
workflow does not declare, and `--workflow macro_weekly_refit.yml` is a
documented call that declares none.

Pure unit tests — the script is run with `--dry-run`, which prints the request
body and sends nothing.

Run:
    pytest .macro-assist/tests/test_trigger_asof.py -v
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "trigger_pipeline.sh"
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _dispatch(*args: str) -> dict:
    """Run the script in dry-run mode and return the JSON body it would POST."""
    proc = subprocess.run(
        ["bash", str(_SCRIPT), "--dry-run", *args],
        capture_output=True, text=True, cwd=_ROOT, check=True,
    )
    # Two lines: "POST <url>" then the body.
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _declares_asof(workflow: str) -> bool:
    spec = yaml.safe_load((_WORKFLOWS / workflow).read_text())
    # `on:` parses as the boolean True under the YAML 1.1 rules PyYAML follows.
    triggers = spec.get(True) or spec.get("on") or {}
    dispatch = triggers.get("workflow_dispatch") or {}
    return "asof" in (dispatch.get("inputs") or {})


def test_the_cron_call_carries_a_date():
    """Without this, `plan` falls back to its 06:00 UTC cutoff."""
    body = _dispatch("--source", "cron-primary")
    assert body["inputs"]["asof"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_an_explicit_date_is_not_overwritten():
    """A late catch-up for a previous day has to stay possible."""
    body = _dispatch("--input", "asof=2026-08-31", "--input", "force=true")
    assert body["inputs"]["asof"] == "2026-08-31"
    assert body["inputs"]["force"] == "true"


def test_no_asof_restores_the_guess():
    body = _dispatch("--no-asof")
    assert "asof" not in body["inputs"]


@pytest.mark.parametrize("workflow", [
    "macro_weekly_refit.yml",     # the documented --workflow example
    "portfolio_rebalance.yml",
    "numeric_baseline.yml",
])
def test_workflows_without_an_asof_input_are_not_sent_one(workflow):
    """GitHub 422s a dispatch carrying an input the workflow does not declare."""
    assert not _declares_asof(workflow), (
        f"{workflow} now declares `asof` — this test is guarding the wrong list"
    )
    body = _dispatch("--workflow", workflow, "--source", "manual")
    assert "asof" not in body["inputs"]


def test_the_pinned_workflow_actually_declares_the_input():
    """The other half: the one workflow we do send a date to must accept it."""
    assert _declares_asof("pipeline.yml")


def test_plan_still_guesses_when_no_date_is_sent():
    """The cutoff stays for the `schedule:` backstop, which sends no inputs.

    Pinning the date in the caller does not remove the guess — it removes the
    cron path's dependence on it. If this ever stops being true the comment in
    the script is wrong and so is this file's docstring.
    """
    plan = yaml.safe_load((_WORKFLOWS / "pipeline.yml").read_text())["jobs"]["plan"]
    script = plan["steps"][0]["run"]
    assert "-lt 06" in script
    assert "yesterday" in script
