"""
sealed_runner.py — the sealed read (WP-23.B, its second half).

Research tier (product_surface: RESEARCH). The one module that reads the sealed
slice for a distribution question. It walks a promoted entry's arm, and its
class bar's benchmark and rival, forward on the sealed side — the explore
harness's own walk (`explore_conditioner.observations_on`), on the report dates
the class bar names, with the same known-by-t quantiles and collapse ladder —
and hands what it walked to `class_bars.read(..., sealed=True)`. It runs in one
place: `sealed_read.yml`'s key job, after the owner's key was checked
(seal_key.py, WP-25.D). Every step that touches data refuses anywhere else.

The steps, in the order the key job runs them
---------------------------------------------
    --fetch       download the inputs (prices, the bucket's FRED series, the
                  fragility channels) to a file. Public data, nothing scored:
                  a failure here spends nothing, which is why it comes first.
    --claim       write `sealed_reads/<hid>/<stamp>.claim.json`, which the
                  workflow pushes to output BEFORE anything is scored. The read
                  is irreversible, so the slice is spent first and read second:
                  a run that dies after its claim has spent it and says so — a
                  lost read, red in record_audit's sealed-reads check — rather
                  than leaving a read nobody recorded.
    --read        only once this run's claim is on output: build the panel,
                  walk the arms on the sealed side, apply the class bar, write
                  `<stamp>.json` (every number the verdict read) and `<stamp>.md`
                  (the report). The workflow publishes both.
    --sync-field  the entry's `Sealed read (ledger)` from CI's records. Free,
                  reads no data, and the one step that runs anywhere.

    --check       what the runner would refuse the entry's pre-registration for,
                  from the code alone: a class it cannot walk, an arm the
                  harness does not walk, a cell label or value the harness never
                  writes. seal_key.py's preflight runs this before the owner is
                  asked — a misspelt cell would be an empty cell, and an empty
                  cell reads `underpowered` on the class's one read.

What the guard cannot do: the data is public, so a deliberate look outside
this workflow is not stopped (ADR-0022 says so). It stops an accident — this
module run from a shell, or from another workflow — and it keeps a read that
the owner did not approve out of the record: only CI's records, pushed from
the key job, count.

    python .macro-assist/sealed_runner.py H-008 --check        # free, anywhere
    python .macro-assist/sealed_runner.py H-008 --sync-field   # free, anywhere
    # in sealed_read.yml's key job only: --fetch / --claim / --read
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import audit_entry as ae
import class_bars as cb
import decision_packet as dp
import explore_conditioner as ec
import record_audit as ra
import seal_key as sk
from assets import BY_KEY

WORKFLOW = ".github/workflows/sealed_read.yml"
KEY_JOB = "key"
RESULTS = Path("results")

# The classes this runner can walk. The gap → width class has no seal
# (todo.md #33) and no scorer data (H-003's point-in-time errand); its walk is
# written when it has both.
WALKS = frozenset({"conditioner"})
WALKABLE = tuple(a for a in ec.ARMS if a != ec.BENCH)

# What `explore_conditioner.build_panel` writes, label by label: the values a
# cell may name. Pinned against the harness's source in the tests.
_BUCKETS = frozenset(f"NFCI:{n}|YC:{y}|CREDIT:{c}" for n in ("low", "mid", "high")
                     for y in ("positive", "inverted") for c in ("tight", "mid", "wide"))
LABELS: dict[str, frozenset[str]] = {
    "or_state": frozenset({"Elevated", "Normal"}),
    "comp_state": frozenset({"Elevated", "Normal"}),
    "dd_bin": frozenset({"dd<-10", "dd-5..-10", "dd>-5"}),
    "dd_stressed": frozenset({"dd<=-5", "dd>-5"}),
    "dd_age": frozenset({"calm", "fresh", "old"}),
    "sp_sign": frozenset({"down5", "up5"}),
    "nfci": frozenset({"NFCI:low", "NFCI:mid", "NFCI:high"}),
    "bucket": _BUCKETS,
}


class Refused(Exception):
    """A step that must not run here, or on this entry."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# what the runner refuses, before any data
# ---------------------------------------------------------------------------

def refusals(spec: dict) -> list[str]:
    """Why this (validated) pre-registration cannot be walked, from the code alone."""
    bar = cb.BARS[spec["class"]]
    if bar.name not in WALKS:
        return [f"the sealed runner walks the {', '.join(sorted(WALKS))} class; the {bar.name} class "
                "has no walk yet"]
    out = []
    if spec["arm"] not in WALKABLE:
        out.append(f"arm `{spec['arm']}` is not one the harness walks ({', '.join(WALKABLE)})")
    for i, c in enumerate(spec["clauses"]):
        if "series" in c and c["series"] not in BY_KEY:
            out.append(f"clause {i}: series {c['series']!r} is not an asset ({', '.join(BY_KEY)})")
        for k in ("a", "b", "cell", "null_in"):
            for label, v in (c.get(k) or {}).items():
                if label not in LABELS:
                    out.append(f"clause {i} `{k}`: label {label!r} is not one the harness writes "
                               f"({', '.join(LABELS)})")
                    continue
                bad = [x for x in (v if isinstance(v, list) else [v])
                       if not isinstance(x, str) or x not in LABELS[label]]
                if bad:
                    shown = sorted(LABELS[label]) if label != "bucket" else ["NFCI:…|YC:…|CREDIT:…"]
                    out.append(f"clause {i} `{k}`: {label} = {bad} is a value the harness never writes "
                               f"({', '.join(shown)}); the cell would be empty")
    return out


def ci_refusals(env=None) -> list[str]:
    """This step runs in sealed_read.yml's key job on main, or nowhere."""
    env = os.environ if env is None else env
    out = []
    if ae._tier() != "ci" or not ae._run_url():
        out.append("the sealed runner runs in CI only, in sealed_read.yml's key job")
    wf = env.get("GITHUB_WORKFLOW_REF", "")
    if not wf.endswith(f"/{WORKFLOW}@refs/heads/main"):
        out.append(f"called from {wf or 'no workflow'}; only {WORKFLOW} on main runs it")
    if env.get("GITHUB_JOB") != KEY_JOB:
        out.append(f"called from job {env.get('GITHUB_JOB')!r}; only the `{KEY_JOB}` job runs it, "
                   "after the owner's key")
    return out


def _load_json(path: str | None):
    if not path:
        return None
    text = Path(path).read_text(encoding="utf-8").strip()
    return json.loads(text) if text else None


def key_refusals(root: Path, hid: str, approvals: str | None) -> tuple[str | None, list[str]]:
    """(the owner's comment, every reason this step may not run): the CI guard,
    the key checked again from GitHub's record of it, and the seal key's own
    preflight of the entry — which also refuses a class whose slice is read."""
    out = ci_refusals()
    comment, bad = sk.approval_refusals(_load_json(approvals) or [])
    return comment, out + bad + sk.preflight(root, hid)


def _spec(root: Path, hid: str) -> tuple[str, dict]:
    entry = dp.entry_text((root / dp.HYPOTHESES).read_text(encoding="utf-8"), hid)
    return entry, cb.parse_preregistration(entry)


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

def sealed_positions(frame: pd.DataFrame, bar: cb.ClassBar) -> range:
    """Positions of the frame's report dates on the class's sealed side:
    `sealed_from` inclusive, `sealed_until` exclusive."""
    if bar.sealed_from is None:
        raise Refused(f"the {bar.name} class has no decided seal")
    idx = frame.index.to_numpy()
    first = int(np.searchsorted(idx, np.datetime64(pd.Timestamp(bar.sealed_from))))
    stop = int(np.searchsorted(idx, np.datetime64(pd.Timestamp(bar.sealed_until))))
    return range(first, stop)


def walk(frame: pd.DataFrame, fr: dict, spec: dict,
         sigmas: dict[str, np.ndarray] | None) -> list[dict]:
    """The member's arm and the benchmark on every sealed report date, the
    rival where it quotes — the harness's walk, every label a cell may name."""
    bar = cb.BARS[spec["class"]]
    obs = ec.observations_on(frame, fr, ec.arm_labels(frame), sealed_positions(frame, bar),
                             arms=(ec.BENCH, spec["arm"]), sigmas=sigmas, labels=tuple(LABELS))
    lo, hi = bar.sealed_from.isoformat(), bar.sealed_until.isoformat()
    stray = [o["date"] for o in obs if not lo <= o["date"] < hi]
    if stray:
        raise RuntimeError(f"the walk left the sealed side: {stray[:3]}")
    return obs


def read_walked(obs: list[dict], spec: dict) -> dict:
    """The class bar on what was walked. `sealed=True` because `walk` stayed
    on the sealed side, and checked it did."""
    if not obs:
        raise RuntimeError("no observations on the sealed side")
    return cb.read(obs, spec, sealed=True)


def obs_sha256(obs: list[dict]) -> str:
    return _sha(json.dumps(obs, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# the records
# ---------------------------------------------------------------------------

def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%MZ")


def _run() -> dict:
    env = os.environ
    return {"tier": ae._tier(), "run": ae._run_url(), "run_id": env.get("GITHUB_RUN_ID"),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT")}


def make_claim(root: Path, hid: str, comment: str | None, *, now: datetime) -> dict:
    entry, spec = _spec(root, hid)
    bar = cb.BARS[spec["class"]]
    fingerprint = ra.bar_fingerprint(root, bar.name)
    if fingerprint is None:
        raise Refused(f"the {bar.name} bar has no fingerprint here, so nothing could hold it to "
                      "this read afterwards")
    return {
        "schema": 1, "kind": "claim", "hid": hid, "class": bar.name,
        "arm": spec["arm"], "horizon": spec["horizon"], "pre_registration": spec,
        "sealed_from": bar.sealed_from.isoformat(), "sealed_until": bar.sealed_until.isoformat(),
        "claimed_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        **_run(), "commit": ra._git(root, "rev-parse", "HEAD"),
        "entry_stamp": f"sha256:{_sha(dp.stamped_text(entry))}",
        "entry_bar": f"sha256:{_sha(dp.bar_text(entry))}",
        "bar_fingerprint": fingerprint,
        "approved_by": sk.SEAL_KEY_OWNER, "approval_comment": comment,
    }


def own_claim(root: Path, hid: str) -> dict | None:
    """This run attempt's claim of `hid`, as the output branch holds it."""
    ref = ra._resolve_ref(root, ae.OUTPUT_BRANCH)
    if ref is None:
        return None
    run = _run()
    mine = [r for r in ra.ci_sealed_reads(root, ref)
            if r["kind"] == "claim" and r["hid"] == hid
            and (r.get("run_id"), r.get("run_attempt")) == (run["run_id"], run["run_attempt"])]
    return mine[-1] if mine else None


def make_result(root: Path, claim: dict, read: dict, obs: list[dict], report: str,
                inputs_fetched: str | None, *, now: datetime) -> dict:
    s = read["summary"]
    return {
        "schema": 1, "kind": "result", "hid": claim["hid"], "class": claim["class"],
        "arm": claim["arm"], "horizon": claim["horizon"], "claim": claim["_path"],
        "read_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        **_run(), "commit": ra._git(root, "rev-parse", "HEAD"),
        "verdict": read["verdict"], "reason": read["reason"], "read": read,
        "first_date": s["first_date"], "last_date": s["last_date"],
        "n_report_dates": s["n_report_dates"], "n_obs": len(obs),
        "inputs_fetched": inputs_fetched, "obs_sha256": obs_sha256(obs),
        "report_sha256": _sha(report), "bar_fingerprint": ra.bar_fingerprint(root, claim["class"]),
    }


def _num(x, fmt="+.4f") -> str:
    return "—" if x is None else format(x, fmt)


def _skill(st: dict | None) -> str:
    if not st or st.get("skill") is None:
        return "none"
    ci = st.get("ci") or {}
    return f"{st['skill']:+.4f} [{_num(ci.get('lo'))}, {_num(ci.get('hi'))}]"


def render_report(claim: dict, read: dict, obs: list[dict]) -> str:
    """The report, verdict first. Every stage's number is in it, whichever
    verdict fired (the method §10)."""
    s, bar = read["summary"], cb.BARS[claim["class"]]
    cov = s.get("coverage_ci") or {}
    L = [f"# Sealed read — {claim['hid']} ({claim['class']} class)", "",
         f"**Verdict: `{read['verdict']}`** — {read['reason']}", "",
         f"The {claim['class']} class's one read of its sealed side: report dates "
         f"{claim['sealed_from']} → before {claim['sealed_until']}, as walked "
         f"{s['first_date']} → {s['last_date']} ({s['n_report_dates']} report dates, "
         f"{s['n_blocks']} blocks of {bar.block}). It is read once for the whole class; no other "
         "member of the class reads it again.", "",
         f"Claimed {claim['claimed_at']} by [the run]({claim['run']}) at commit "
         f"`{str(claim['commit'])[:12]}`, after {claim['approved_by']} turned the key. "
         f"Class bar `{str(claim['bar_fingerprint'])[:19]}…`; entry text `{claim['entry_stamp'][:19]}…`.", "",
         "## What was read against what", "",
         f"- **Arm** `{claim['arm']}` at h={claim['horizon']}, on {', '.join(s['series'])} "
         "(equal-weight pooled)",
         f"- **Benchmark** `{bar.benchmark}`; **rival** `{bar.rival}`, on the subsample where it quotes",
         f"- **Pass clause, both comparators:** skill > {cb.MIN_SKILL} with a block-bootstrap "
         "interval clear of zero", "",
         "The pre-registration, as the audit stamped it and `class_bars.validate` normalised it:", "",
         "```json", json.dumps(claim["pre_registration"], indent=2, ensure_ascii=False), "```", "",
         "## Every stage's number", "",
         f"Order: {' → '.join(cb.VERDICTS)}. The first to fire is the verdict.", "",
         "| stage | number | needs |", "|---|---|---|",
         f"| power | {s['n_blocks']} blocks, {s['n_report_dates']} report dates | ≥ {bar.min_blocks} blocks"
         + (f", ≥ {bar.min_report_dates} report dates" if bar.min_report_dates else "") + " |",
         f"| rival's power | {s['rival']['n_blocks']} blocks, {s['rival']['n_report_dates']} report dates "
         f"| ≥ {bar.min_blocks} blocks |",
         f"| coverage P25–P75 | {_num(s.get('coverage'), '.4f')} [{_num(cov.get('lo'), '.4f')}, "
         f"{_num(cov.get('hi'), '.4f')}] | interval holds {cb.NOMINAL_COVERAGE} |",
         f"| skill vs `{bar.benchmark}` | {_skill(s.get('skill'))} | > {cb.MIN_SKILL}, interval above 0 |",
         f"| skill vs `{bar.rival}` | {_skill(s['rival'].get('skill'))} | > {cb.MIN_SKILL}, interval above 0 |",
         ]
    fl = read["floor"]
    for c in read["clauses"]:
        cells = "; ".join(f"{x['name']}: {x['n_report_dates']} dates in {x['n_episodes']} episodes"
                          for x in c["cells"])
        L.append(f"| clause `{c['kind']}` — {'held' if c['passed'] else 'failed'} | {c['detail']} · {cells} "
                 f"| cells ≥ {fl['report_dates']} dates in ≥ {fl['episodes']} episodes |")
    L += ["", "## Reproduce", "",
          f"{len(obs)} observations, sha256 `{obs_sha256(obs)[:16]}…`, walked by "
          "`explore_conditioner.observations_on` on the sealed positions and read by "
          "`class_bars.read(sealed=True)`. Nothing here is re-run: the slice is read."]
    return "\n".join(L) + "\n"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / RESULTS / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sync_field(root: Path, hid: str | None = None) -> list[str]:
    """Rewrite the `Sealed read (ledger)` of `hid` (or of every entry) from CI's
    records on the output branch. Returns the entries whose field changed."""
    ref = ra._resolve_ref(root, ae.OUTPUT_BRANCH)
    if ref is None:
        raise Refused(f"no `{ae.OUTPUT_BRANCH}` branch here — `git fetch origin {ae.OUTPUT_BRANCH}`")
    by_hid: dict[str, list[dict]] = {}
    for r in ra.ci_sealed_reads(root, ref):
        by_hid.setdefault(r["hid"], []).append(r)
    path = root / dp.HYPOTHESES
    text = path.read_text(encoding="utf-8")
    changed = []
    for h in ([hid] if hid else [e.hid for e in dp.parse_entries(text)]):
        new = dp.with_field(text, h, dp.SEALED_READ, dp.sealed_read_paragraph(by_hid.get(h, [])))
        if new != text:
            changed.append(h)
            text = new
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------

def _refuse(step: str, reasons: list[str]) -> int:
    sys.stdout.write(f"## Sealed runner — {step} refused\n\n" + "".join(f"- {r}\n" for r in reasons)
                     + "\nThe sealed slice was not read.\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("hid")
    step = ap.add_mutually_exclusive_group(required=True)
    for s in ("check", "fetch", "claim", "read", "sync-field"):
        step.add_argument(f"--{s}", action="store_true")
    ap.add_argument("--inputs", help="the fetched inputs (--fetch writes it, --read reads it)")
    ap.add_argument("--approvals", help="the run's approval record, as JSON")
    ap.add_argument("--root", type=Path, default=ra._repo_root())
    a = ap.parse_args(argv)
    root, hid = a.root, a.hid

    if a.sync_field:
        try:
            changed = sync_field(root, hid)
        except Refused as e:
            return _refuse("sync-field", [str(e)])
        print(f"{hid}: {dp.SEALED_READ} " + ("rewritten from CI's records" if changed else "already current"))
        return 0

    if a.check:
        try:
            _, spec = _spec(root, hid)
        except KeyError:
            return _refuse("check", [f"{hid} is not in {dp.HYPOTHESES}"])
        except cb.PreregError as e:
            return _refuse("check", [f"{hid}'s pre-registration: {e}"])
        bad = refusals(spec)
        if bad:
            return _refuse("check", bad)
        print(f"{hid}: the sealed runner can walk `{spec['arm']}` at h={spec['horizon']} under the "
              f"{spec['class']} class, and every cell names labels the harness writes")
        return 0

    if (a.fetch or a.read) and not a.inputs:
        ap.error("--fetch and --read need --inputs")
    comment, bad = key_refusals(root, hid, a.approvals)
    if bad:
        return _refuse("fetch" if a.fetch else "claim" if a.claim else "read", bad)

    if a.fetch:
        Path(a.inputs).write_bytes(pickle.dumps(ec.fetch_inputs()))
        print(f"{hid}: inputs fetched; nothing scored")
        return 0

    now = datetime.now(timezone.utc)
    if a.claim:
        if own_claim(root, hid) is not None:
            return _refuse("claim", ["this run attempt has claimed the slice already"])
        try:
            claim = make_claim(root, hid, comment, now=now)
        except Refused as e:
            return _refuse("claim", [str(e)])
        rel = f"{ra.SEALED_RECORDS}/{hid}/{_stamp(now)}.claim.json"
        _write(root, rel, json.dumps(claim, indent=2, ensure_ascii=False) + "\n")
        print(f"{hid}: the {claim['class']} slice is claimed (`results/{rel}`); the workflow pushes "
              "it before anything is scored")
        return 0

    claim = own_claim(root, hid)
    if claim is None:
        return _refuse("read", ["this run attempt's claim is not on the output branch; the slice is "
                                "claimed, and the claim pushed, before it is read"])
    _, spec = _spec(root, hid)
    if spec != claim["pre_registration"]:
        return _refuse("read", ["the pre-registration differs from the one this run claimed with"])
    inputs = pickle.loads(Path(a.inputs).read_bytes())
    frame, fr = ec.build_panel(inputs)
    bar = cb.BARS[spec["class"]]
    pos = sealed_positions(frame, bar)
    sigmas = ec.har_sigmas(inputs["prices"], frame.index, pos.start, pos.stop)
    obs = walk(frame, fr, spec, sigmas)
    read = read_walked(obs, spec)
    report = render_report(claim, read, obs)
    stem = claim["_path"].removesuffix(".claim.json")
    result = make_result(root, claim, read, obs, report, inputs.get("fetched"), now=now)
    _write(root, f"{stem}.json", json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    _write(root, f"{stem}.md", report)
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
