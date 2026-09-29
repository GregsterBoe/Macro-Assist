"""The seal key (WP-25.D, ADR-0022): the owner's approval, in GitHub, before a
sealed read.

A sealed read is the one irreversible act in the research loop — the held-out
slice is read once per class, and a number seen there cannot be unseen (how we
explore §6). ADR-0022 leaves that act with the owner, as *an action only the
owner's account can take*: a GitHub Actions environment, `seal-key`, with the
owner as its required reviewer. `sealed_read.yml` has two jobs. The first
checks, before anyone is asked, that the entry may be read at all. The second
names the environment, so GitHub holds it until the owner approves it in the
Actions tab; when it starts, it checks that the owner, and nobody else, turned
the key.

Why the job checks the approval itself rather than trusting the pause: GitHub
creates an environment the first time a job names it, with no protection at
all. A missing or misconfigured `seal-key` does not stop the job — it runs
straight through. So the key is verified from what GitHub recorded, never from
the fact that the job is running:

    environment   the settings, read before the key is asked for: `seal-key`
                  exists, the owner is its only required reviewer, self-review
                  is allowed (the owner dispatches the run and approves it),
                  and administrators cannot bypass it
    approval      the run's approval record, read after the job starts: the
                  owner approved `seal-key` on this run, and nobody rejected it
    preflight     the entry, before the key and again after it: `promoted`, a
                  CI audit stamped to its current text found nothing blocking
                  (record_audit's approval-stamp check, not a second copy of
                  it), a pre-registration its class bar can read under a
                  decided seal (class_bars.py, WP-23.B), and no sealed read yet

What it cannot do: the data is public, so a deliberate look outside this
workflow is not stopped — ADR-0022 says so. The key keeps an *unapproved*
sealed read out of the record, and the credential split (the assistant's token
cannot approve) is verified by trying it, once, on a dry run (WP-25.D's done
condition). That split rests on the token's permissions, not on a separate
account: re-verify it whenever that token is recreated.

The read itself is WP-23.B's sealed runner, its second half. Until it exists
a real run stops after the key and before any data, with a refusal that says
so.

    python .macro-assist/seal_key.py H-008 --preflight --dry-run   # what the first job prints
    # in CI only: --environment FILE (the settings), --after-key --approvals FILE

A refusal exits 2. A dry run reads nothing and is soft on the *entry* — it
reports what a real run would refuse and goes on — so the pause can be shown on
an entry that is not yet eligible. It is never soft on the *key*: a dry run is
how the key is tested, so a bad setting or a missing approval fails it too.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import audit_entry as ae
import decision_packet as dp
import record_audit as ra

SEAL_KEY_ENVIRONMENT = "seal-key"
# The one account whose approval turns the key. The assistant works through a
# narrowed token on this same account, so the split is that token's permissions.
SEAL_KEY_OWNER = "GregsterBoe"
WORKFLOW = Path(".github") / "workflows" / "sealed_read.yml"
NO_HARNESS = ("the sealed read itself is WP-23.B's sealed runner, which does not exist yet; "
              "this run stopped after the key and before any data")


# ---------------------------------------------------------------------------
# the key's settings, and who turned it
# ---------------------------------------------------------------------------

def environment_refusals(env: dict | None, owner: str = SEAL_KEY_OWNER,
                         name: str = SEAL_KEY_ENVIRONMENT) -> list[str]:
    """What is wrong with the environment's settings, as GitHub's API returns
    them (`GET /repos/{repo}/environments/{name}`); None when it does not exist."""
    if not env:
        return [f"there is no `{name}` environment. GitHub would create it, unprotected, the "
                "first time the job named it, and the job would run without waiting — create it "
                "in Settings → Environments with the owner as required reviewer"]
    out = []
    rules = [r for r in env.get("protection_rules") or [] if r.get("type") == "required_reviewers"]
    reviewers = [(rv.get("type"), (rv.get("reviewer") or {}).get("login") or
                  (rv.get("reviewer") or {}).get("slug"))
                 for r in rules for rv in r.get("reviewers") or []]
    if not reviewers:
        out.append(f"`{name}` has no required reviewer, so the job would not wait for anyone")
    elif reviewers != [("User", owner)]:
        named = ", ".join(f"{t} {n}" for t, n in reviewers)
        out.append(f"`{name}`'s required reviewers are {named}; the key is the owner's alone, "
                   f"so the only reviewer is the user {owner}")
    if any(r.get("prevent_self_review") for r in rules):
        out.append(f"`{name}` prevents self-review; the owner dispatches this workflow, so the "
                   "owner could never approve it — untick *Prevent self-review*")
    if env.get("can_admins_bypass", True):
        out.append(f"administrators can bypass `{name}`'s rules, so a run could start without an "
                   "approval — untick *Allow administrators to bypass configured protection rules*")
    return out


def approval_refusals(approvals: list[dict], owner: str = SEAL_KEY_OWNER,
                      name: str = SEAL_KEY_ENVIRONMENT) -> tuple[str | None, list[str]]:
    """(the comment the owner approved with, what is wrong), from the run's
    approval record (`GET /repos/{repo}/actions/runs/{id}/approvals`)."""
    mine = [a for a in approvals or []
            if name in {e.get("name") for e in a.get("environments") or []}]
    rejected = [a for a in mine if a.get("state") == "rejected"]
    if rejected:
        who = ", ".join(sorted({(a.get("user") or {}).get("login", "?") for a in rejected}))
        return None, [f"`{name}` was rejected on this run by {who}"]
    approved = [a for a in mine if a.get("state") == "approved"]
    others = sorted({(a.get("user") or {}).get("login", "?") for a in approved} - {owner})
    if others:
        return None, [f"`{name}` was approved by {', '.join(others)}; only {owner} turns the key"]
    if not approved:
        return None, [f"this job started with no approval of `{name}` on record — the "
                      "environment did not hold it, so the key was never turned"]
    return approved[-1].get("comment") or "", []


# ---------------------------------------------------------------------------
# the entry
# ---------------------------------------------------------------------------

def _bar_refusals(entry: str, hid: str) -> list[str]:
    """A sealed read is read against the entry's pre-registration under its
    class bar: one that no bar can read, or whose class has no decided seal,
    is refused before anyone is asked to turn the key."""
    import class_bars as cb
    try:
        spec = cb.parse_preregistration(entry)
    except cb.PreregError as e:
        return [f"{hid}'s pre-registration cannot be read by a class bar: {e}"]
    if cb.BARS[spec["class"]].sealed_from is None:
        return [f"{hid} is in the {spec['class']} class, which has no decided seal"]
    return []


def preflight(root: Path, hid: str) -> list[str]:
    """Every reason `hid` may not have its sealed read now; empty when it may."""
    env = os.environ
    out = []
    if ae._tier() != "ci" or not ae._run_url():
        out.append("a sealed read runs in CI, behind the owner's key; run it from sealed_read.yml")
    if env.get("GITHUB_REF") != "refs/heads/main":
        out.append(f"dispatched on {env.get('GITHUB_REF')!r}; the stamped text is the one on main")
    if ae._shallow(root):
        out.append("this clone is shallow, so the approval stamp cannot be held to the entry's "
                   "history — check out with fetch-depth: 0 and OUTPUT_FULL_HISTORY=1")
    if ra._git(root, "status", "--porcelain", "--", dp.HYPOTHESES.as_posix()):
        out.append(f"{dp.HYPOTHESES} has uncommitted changes; a sealed read is read against "
                   "committed text")
    register = (root / dp.HYPOTHESES).read_text(encoding="utf-8")
    entry = next((e for e in dp.parse_entries(register) if e.hid == hid), None)
    if entry is None:
        return out + [f"{hid} is not in {dp.HYPOTHESES}"]
    if entry.status != "promoted":
        out.append(f"{hid} is `{entry.status}`; only a `promoted` entry has a sealed read — it "
                   "passes a CI audit first (audit_entry.yml)")
    else:
        out += [f.message for f in ra.check_approval_stamp(root) if f.subject == hid]
    out += _bar_refusals(dp.entry_text(register, hid), hid)
    if dp.field_block(dp.entry_text(register, hid), dp.SEALED_READ) is not None:
        out.append(f"{hid} already has a `{dp.SEALED_READ}`; the sealed slice is read once")
    return out


# ---------------------------------------------------------------------------
# the report, and the command line
# ---------------------------------------------------------------------------

def _report(title: str, key: list[str], entry: list[str], dry_run: bool, done: str) -> tuple[str, int]:
    """The step summary, and the exit code: the key's refusals always fail;
    the entry's fail a real run and are reported by a dry one."""
    lines = [f"## {title}", ""]
    if key:
        lines += ["Refused — the key itself is not sound:", ""] + [f"- {r}" for r in key] + [""]
    if entry:
        lead = "A real run would refuse:" if dry_run else "Refused:"
        lines += [lead, ""] + [f"- {r}" for r in entry] + [""]
    failed = bool(key) or (bool(entry) and not dry_run)
    lines.append("The sealed slice was not read." if failed else done)
    return "\n".join(lines) + "\n", 2 if failed else 0


def _load(path: str | None):
    if not path:
        return None
    text = Path(path).read_text(encoding="utf-8").strip()
    return json.loads(text) if text else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("hid")
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--preflight", action="store_true", help="before the key: may this entry be read?")
    step.add_argument("--after-key", action="store_true", help="after the key: who turned it?")
    ap.add_argument("--environment", help="the environment's settings, as JSON (null when missing)")
    ap.add_argument("--approvals", help="the run's approval record, as JSON (required with --after-key)")
    ap.add_argument("--dry-run", action="store_true", help="read nothing; report the entry's refusals")
    ap.add_argument("--root", type=Path, default=ra._repo_root())
    a = ap.parse_args(argv)
    if a.after_key and a.approvals is None:
        ap.error("--after-key needs --approvals: the key is checked from GitHub's record of it")

    entry = preflight(a.root, a.hid)
    if a.preflight:
        key = environment_refusals(_load(a.environment)) if a.environment is not None else []
        done = ("Dry run: the next job waits for the owner's key, then reads nothing."
                if a.dry_run else "The next job waits for the owner's key.")
        title = "before the key"
    else:
        comment, key = approval_refusals(_load(a.approvals) or [])
        if not a.dry_run and not entry:
            entry = [NO_HARNESS]
        done = (f"The key was turned by {SEAL_KEY_OWNER}"
                + (f" (“{comment}”)" if comment else "") + ". Dry run: nothing was read.")
        title = "after the key"
    text, code = _report(f"Sealed read of {a.hid} — {title}", key, entry, a.dry_run, done)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
