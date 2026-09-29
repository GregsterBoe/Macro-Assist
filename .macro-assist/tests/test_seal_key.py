"""The seal key (WP-25.D, ADR-0022). Offline: the key's settings and its
approval record are GitHub API payloads, fed in as JSON; the entry is the
replayed clean canary of test_audit_entry.py, promoted here."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

import audit_entry as ae
import decision_packet as dp
import record_audit as ra
import seal_key as sk
from test_audit_entry import CI_ENV, _commit_output, canaries, ci_repo  # noqa: F401 — fixtures

ROOT = Path(__file__).resolve().parents[2]
OWNER = sk.SEAL_KEY_OWNER


def _env(**over) -> dict:
    """The environment as GitHub returns it, set up the way the key needs."""
    return {"name": "seal-key", "can_admins_bypass": False,
            "protection_rules": [{"type": "required_reviewers", "prevent_self_review": False,
                                  "reviewers": [{"type": "User", "reviewer": {"login": OWNER}}]}],
            **over}


def _approval(login: str = OWNER, state: str = "approved", env: str = "seal-key") -> dict:
    return {"state": state, "comment": "go", "user": {"login": login},
            "environments": [{"name": env}]}


# ---------------------------------------------------------------------------
# the key's settings
# ---------------------------------------------------------------------------

def test_a_sound_key_has_no_refusal():
    assert sk.environment_refusals(_env()) == []


@pytest.mark.parametrize("env, says", [
    (None, "no `seal-key` environment"),
    (_env(protection_rules=[]), "no required reviewer"),
    (_env(protection_rules=[{"type": "branch_policy"}]), "no required reviewer"),
    (_env(protection_rules=[{"type": "required_reviewers", "reviewers": [
        {"type": "User", "reviewer": {"login": OWNER}},
        {"type": "User", "reviewer": {"login": "someone-else"}}]}]), "the owner's alone"),
    (_env(protection_rules=[{"type": "required_reviewers", "reviewers": [
        {"type": "Team", "reviewer": {"slug": "maintainers"}}]}]), "Team maintainers"),
    (_env(protection_rules=[{"type": "required_reviewers", "prevent_self_review": True,
                             "reviewers": [{"type": "User", "reviewer": {"login": OWNER}}]}]),
     "prevents self-review"),
    (_env(can_admins_bypass=True), "bypass"),
    ({k: v for k, v in _env().items() if k != "can_admins_bypass"}, "bypass"),
])
def test_an_unsound_key_is_refused(env, says):
    assert any(says in r for r in sk.environment_refusals(env))


# ---------------------------------------------------------------------------
# who turned it
# ---------------------------------------------------------------------------

def test_the_owners_approval_turns_the_key():
    assert sk.approval_refusals([_approval()]) == ("go", [])


@pytest.mark.parametrize("approvals, says", [
    ([], "no approval of `seal-key` on record"),
    ([_approval(env="github-pages")], "no approval of `seal-key` on record"),
    ([_approval(login="someone-else")], "only GregsterBoe turns the key"),
    ([_approval(), _approval(login="someone-else")], "approved by someone-else"),
    ([_approval(state="rejected")], "rejected"),
])
def test_a_key_the_owner_did_not_turn_is_refused(approvals, says):
    comment, bad = sk.approval_refusals(approvals)
    assert comment is None and any(says in r for r in bad)


# ---------------------------------------------------------------------------
# the entry
# ---------------------------------------------------------------------------

def _promote(root: Path, hid: str = "H-101", *, verdict: str = "no_blocking_finding") -> None:
    """Promote `hid` on main and give it a certified CI audit of its current text."""
    path = root / dp.HYPOTHESES
    path.write_text(path.read_text().replace("**Status:** `draft`", "**Status:** `promoted`", 1))
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "promote"], check=True)
    entry = dp.entry_text(path.read_text(), hid)
    rec = {"schema": 1, "hid": hid, "tier": "ci", "run": "https://github.com/o/r/actions/runs/1",
           "entry_fingerprint": "sha256:" + ae._sha(dp.stamped_text(entry)), "verdict": verdict,
           "reasons": [], "requested_model": ae.DEFAULT_MODEL, "effort": ae.DEFAULT_EFFORT,
           "instructions_sha256": ae._sha(ae.read_instructions(root)),
           "canary_set_sha256": ae.canary_set_sha(root)}
    _commit_output(root, {f"audit/entries/{hid}/2026-09-29T1000Z-ci.json": json.dumps(rec)})


def test_a_draft_is_not_read(ci_repo):
    assert any("`draft`; only a `promoted` entry" in r for r in sk.preflight(ci_repo, "H-101"))


def test_a_promoted_entry_with_a_stamped_approval_may_be_read(ci_repo):
    _promote(ci_repo)
    assert sk.preflight(ci_repo, "H-101") == []


def test_a_promoted_entry_edited_since_its_audit_is_not_read(ci_repo):
    _promote(ci_repo)
    path = ci_repo / dp.HYPOTHESES
    path.write_text(path.read_text().replace("Gold", "Gold, edited", 1))
    subprocess.run(["git", "-C", str(ci_repo), "commit", "-qam", "edit"], check=True)
    assert any("no CI audit is stamped to its current text" in r for r in sk.preflight(ci_repo, "H-101"))


def test_a_rejected_entry_is_not_read(ci_repo):
    _promote(ci_repo, verdict="reject")
    assert any("rejected it" in r for r in sk.preflight(ci_repo, "H-101"))


def test_the_sealed_slice_is_read_once(ci_repo):
    _promote(ci_repo)
    path = ci_repo / dp.HYPOTHESES
    entry = dp.entry_text(path.read_text(), "H-101")
    path.write_text(path.read_text().replace(
        entry, entry.rstrip() + f"\n\n**{dp.SEALED_READ}.** *2027-05-01* — `output:x.md`\n", 1))
    subprocess.run(["git", "-C", str(ci_repo), "commit", "-qam", "read"], check=True)
    assert sk.preflight(ci_repo, "H-101") == [f"H-101 already has a `{dp.SEALED_READ}`; "
                                              "the sealed slice is read once"]


def test_outside_ci_or_off_main_is_refused(ci_repo, monkeypatch):
    _promote(ci_repo)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    monkeypatch.delenv("GITHUB_ACTIONS")
    got = sk.preflight(ci_repo, "H-101")
    assert any("runs in CI" in r for r in got) and any("on main" in r for r in got)


# ---------------------------------------------------------------------------
# the command line: soft on the entry in a dry run, never soft on the key
# ---------------------------------------------------------------------------

def _json(tmp_path: Path, name: str, obj) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return str(p)


def test_a_dry_run_reaches_the_key_on_an_entry_that_is_not_eligible(ci_repo, tmp_path, capsys):
    env = _json(tmp_path, "env.json", _env())
    assert sk.main(["H-101", "--preflight", "--environment", env, "--dry-run", "--root", str(ci_repo)]) == 0
    out = capsys.readouterr().out
    assert "A real run would refuse:" in out and "waits for the owner's key, then reads nothing" in out
    # ... and a real run on the same entry never asks for the key
    assert sk.main(["H-101", "--preflight", "--environment", env, "--root", str(ci_repo)]) == 2


def test_a_dry_run_on_an_unsound_key_fails(ci_repo, tmp_path, capsys):
    env = _json(tmp_path, "env.json", None)
    assert sk.main(["H-101", "--preflight", "--environment", env, "--dry-run", "--root", str(ci_repo)]) == 2
    assert "the key itself is not sound" in capsys.readouterr().out
    none = _json(tmp_path, "approvals.json", [])
    assert sk.main(["H-101", "--after-key", "--approvals", none, "--dry-run", "--root", str(ci_repo)]) == 2


def test_after_the_key_a_dry_run_names_who_turned_it(ci_repo, tmp_path, capsys):
    ok = _json(tmp_path, "approvals.json", [_approval()])
    assert sk.main(["H-101", "--after-key", "--approvals", ok, "--dry-run", "--root", str(ci_repo)]) == 0
    assert "turned by GregsterBoe (“go”). Dry run: nothing was read." in capsys.readouterr().out


def test_a_real_run_reads_nothing_until_the_harness_exists(ci_repo, tmp_path, capsys):
    """Everything in order — promoted, approved, the owner's key — and still no
    read: WP-23.B's harness is what reads, and it does not exist."""
    _promote(ci_repo)
    ok = _json(tmp_path, "approvals.json", [_approval()])
    assert sk.main(["H-101", "--after-key", "--approvals", ok, "--root", str(ci_repo)]) == 2
    assert "WP-23.B's harness" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the workflow's shape
# ---------------------------------------------------------------------------

def test_the_workflow_waits_for_the_key_and_checks_who_turned_it():
    wf = yaml.safe_load((ROOT / sk.WORKFLOW).read_text())
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"}, "a sealed read is dispatched, never scheduled or pushed"
    assert on["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    jobs = wf["jobs"]
    assert "environment" not in jobs["preflight"]
    assert jobs["key"]["needs"] == "preflight"
    assert jobs["key"]["environment"] == sk.SEAL_KEY_ENVIRONMENT
    assert [n for n, j in jobs.items() if j.get("environment")] == ["key"], \
        "the key job is the only one that may run after the key"
    runs = [s.get("run", "") for s in jobs["key"]["steps"]]
    assert any("/approvals" in r for r in runs) and any("--after-key" in r for r in runs)
    assert not any(s.get("env", {}).get("ANTHROPIC_API_KEY") for j in jobs.values() for s in j["steps"])
