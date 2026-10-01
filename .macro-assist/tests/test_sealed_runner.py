"""The sealed runner (WP-23.B, second half) and the record checks it answers to.

Offline, on made-up data only: a planted world walked on its "sealed" dates,
and the replayed clean canary of test_audit_entry.py promoted the way
test_seal_key.py promotes it. Nothing here fetches or reads the real slice."""
from __future__ import annotations

import json
import pickle
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

import audit_entry as ae
import class_bars as cb
import decision_packet as dp
import explore_conditioner as ec
import record_audit as ra
import seal_key as sk
import sealed_runner as sr
from assets import ORIGINAL_KEYS
from test_audit_entry import CI_ENV, _commit_output, canaries, ci_repo  # noqa: F401 — fixtures
from test_seal_key import PREREG, _approval, _promote

ROOT = Path(__file__).resolve().parents[2]
KEY_ENV = {"GITHUB_WORKFLOW_REF": f"o/r/{sr.WORKFLOW}@refs/heads/main", "GITHUB_JOB": "key",
           "GITHUB_RUN_ATTEMPT": "1"}


def _spec(**over) -> dict:
    base = {"class": "conditioner", "arm": "frag_or",
            "clauses": [{"kind": "width_contrast", "series": "SP500",
                         "a": {"or_state": "Elevated"}, "b": {"or_state": "Normal"}, "min_ratio": 1.5}]}
    return cb.validate({**base, **over})


# ---------------------------------------------------------------------------
# what the runner refuses before any data
# ---------------------------------------------------------------------------

def test_a_walkable_pre_registration_has_no_refusal():
    assert sr.refusals(_spec()) == []


@pytest.mark.parametrize("over, says", [
    ({"arm": "frag_or_v2"}, "not one the harness walks"),
    ({"clauses": [{"kind": "skill_in_state", "cell": {"or_state": "Elevatd"}}]}, "never writes"),
    ({"clauses": [{"kind": "skill_in_state", "cell": {"or_state": ["Elevated", "elevated"]}}]},
     "['elevated']"),
    ({"clauses": [{"kind": "skill_in_state", "cell": {"orstate": "Elevated"}}]}, "not one the harness writes"),
    ({"clauses": [{"kind": "median_side", "series": "S&P", "cell": {"dd_bin": "dd<-10"},
                   "side": "left"}]}, "is not an asset"),
    ({"clauses": [{"kind": "skill_in_state", "cell": {"or_state": "Elevated"},
                   "null_in": {"dd_bin": "dd<-5"}}]}, "never writes"),
])
def test_a_pre_registration_the_runner_cannot_walk_is_refused(over, says):
    """A misspelt cell is an empty cell, and an empty cell reads `underpowered`
    on the class's one read — so it is refused before the key."""
    assert any(says in r for r in sr.refusals(_spec(**over)))


def test_a_class_with_no_walk_is_refused():
    spec = {**_spec(), "class": "gap_width"}
    assert "has no walk yet" in sr.refusals(spec)[0]


def test_the_label_vocabulary_is_what_the_harness_writes():
    """Every label is a column `build_panel` writes, and every value a literal
    in the harness or the bucket's code — so the vocabulary cannot drift from
    the walk it guards."""
    src = (ROOT / ".macro-assist" / "explore_conditioner.py").read_text()
    bucket_src = (ROOT / ".macro-assist" / "conditional.py").read_text()
    for label, values in sr.LABELS.items():
        assert f'frame["{label}"]' in src, label
        if label in ("bucket", "nfci"):
            continue
        for v in values:
            assert f'"{v}"' in src, (label, v)
    for tier in ("low", "mid", "high", "positive", "inverted", "tight", "wide"):
        assert f'"{tier}"' in bucket_src
    assert set(sr.WALKABLE) == set(ec.ARMS) - {ec.BENCH}


# ---------------------------------------------------------------------------
# where it runs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("drop, says", [
    ({"GITHUB_ACTIONS": None}, "CI only"),
    ({"GITHUB_WORKFLOW_REF": "o/r/.github/workflows/audit_entry.yml@refs/heads/main"}, "only .github"),
    ({"GITHUB_WORKFLOW_REF": f"o/r/{sr.WORKFLOW}@refs/heads/feature"}, "only .github"),
    ({"GITHUB_JOB": "preflight"}, "only the `key` job"),
])
def test_the_runner_runs_in_the_key_job_on_main_or_nowhere(monkeypatch, drop, says):
    for k, v in {**CI_ENV, **KEY_ENV}.items():
        monkeypatch.setenv(k, v)
    assert sr.ci_refusals() == []
    for k, v in drop.items():
        if v is None:
            monkeypatch.delenv(k)
        else:
            monkeypatch.setenv(k, v)
    got = sr.ci_refusals()
    assert len(got) == 1 and says in got[0]


# ---------------------------------------------------------------------------
# the walk, on a planted world
# ---------------------------------------------------------------------------

def _world(n: int = 1800, start: str = "2016-06-01", planted: bool = True, seed: int = 3):
    """Business days across the seal. Runs of 60 Normal and 20 Elevated report
    dates; the forward change is N(0, 1) in Normal and N(0, 3) in Elevated
    (planted) or N(0, 1) throughout. The rival's σ is constant: it does not
    know the state."""
    dates = pd.bdate_range(start, periods=n)
    i = np.arange(n)
    elevated = (i % 80) >= 60
    frame = pd.DataFrame(index=dates)
    frame["bucket"] = "NFCI:mid|YC:positive|CREDIT:mid"
    frame["nfci"] = "NFCI:mid"
    frame["or_state"] = np.where(elevated, "Elevated", "Normal")
    frame["comp_state"] = "Normal"
    frame["dd_bin"] = "dd>-5"
    frame["dd_stressed"] = "dd>-5"
    frame["dd_age"] = "calm"
    frame["sp_sign"] = np.where(i % 2 == 0, "down5", "up5")
    sd = np.where(elevated, 3.0, 1.0) if planted else np.ones(n)
    rng = np.random.default_rng(seed)
    fr = {a.key: {h: rng.normal(size=n) * sd for h in ec.HORIZONS} for a in ec.ASSETS}
    for a in ec.ASSETS:
        for h in ec.HORIZONS:
            fr[a.key][h][-h:] = np.nan
    mix = np.sqrt(np.mean(sd ** 2))
    sigmas = {k: np.full(n, mix * np.sqrt(252 / 5)) for k in ORIGINAL_KEYS}
    return frame, fr, sigmas


def test_the_walk_stays_on_the_sealed_side_and_carries_every_label():
    frame, fr, sigmas = _world()
    obs = sr.walk(frame, fr, _spec(), sigmas)
    assert obs
    assert min(o["date"] for o in obs) >= "2018-01-01"
    assert all(set(sr.LABELS) <= set(o) for o in obs)
    assert all({ec.BENCH, "frag_or"} <= set(o["arms"]) for o in obs)
    assert all("har_scaled" in o["arms"] for o in obs if o["asset"] in ORIGINAL_KEYS)


def test_the_sealed_positions_end_the_day_before_the_live_record():
    frame = pd.DataFrame(index=pd.bdate_range("2026-08-03", "2026-10-30"))
    pos = sr.sealed_positions(frame, cb.CONDITIONER)
    assert frame.index[pos.stop - 1] < pd.Timestamp("2026-09-07") <= frame.index[pos.stop]
    with pytest.raises(sr.Refused):
        sr.sealed_positions(frame, cb.GAP_WIDTH)


def test_the_walk_quotes_from_what_was_known_before_the_seal():
    """Quotes on the first sealed dates use the pre-seal history — the walk is
    forward from 2010, not a fresh start at the seal."""
    frame, fr, sigmas = _world()
    obs = sr.walk(frame, fr, _spec(), sigmas)
    first = min(o["date"] for o in obs)
    o = next(o for o in obs if o["date"] == first and o["asset"] == "SP500" and o["horizon"] == 5)
    assert o["arms"][ec.BENCH]["n"] > 300


def test_a_planted_state_reads_edge_and_noise_does_not():
    """The positive control, through the whole runner: the planted width reads
    `edge` against both comparators with its clause held; the same walk on
    noise does not pass."""
    frame, fr, sigmas = _world()
    read = sr.read_walked(sr.walk(frame, fr, _spec(), sigmas), _spec())
    assert read["verdict"] == "edge", read["reason"]
    frame, fr, sigmas = _world(planted=False)
    read = sr.read_walked(sr.walk(frame, fr, _spec(), sigmas), _spec())
    assert read["verdict"] != "edge"


def test_a_read_with_nothing_walked_is_an_error_not_a_verdict():
    with pytest.raises(RuntimeError):
        sr.read_walked([], _spec())


# ---------------------------------------------------------------------------
# claim, then read, in the replayed repo
# ---------------------------------------------------------------------------

@pytest.fixture
def bar_repo(ci_repo):
    """The replayed repo with the real class bar and what it imports."""
    for name in ("class_bars", "score_distributions", "numeric_baseline", "assets"):
        dst = ci_repo / ".macro-assist" / f"{name}.py"
        dst.parent.mkdir(exist_ok=True)
        shutil.copy(ROOT / ".macro-assist" / f"{name}.py", dst)
    (ci_repo / ra.RESOLVED).parent.mkdir(parents=True, exist_ok=True)
    (ci_repo / ra.RESOLVED).write_text("# Resolved\n\n### RESOLVED 2026-09-14 — #19 the seal\n")
    return ci_repo


@pytest.fixture
def key_repo(bar_repo, monkeypatch, tmp_path):
    ci_repo = bar_repo
    subprocess.run(["git", "-C", str(ci_repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ci_repo), "commit", "-qm", "the class bar"], check=True)
    for k, v in KEY_ENV.items():
        monkeypatch.setenv(k, v)
    _promote(ci_repo)
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps([_approval()]))
    return ci_repo, str(approvals)


def _publish(root: Path) -> None:
    """What ci_publish_results.sh does: every file under results/sealed_reads onto output."""
    base = root / "results"
    files = {p.relative_to(base).as_posix(): p.read_text()
             for p in (base / ra.SEALED_RECORDS).rglob("*") if p.is_file()}
    _commit_output(root, files, msg="sealed read")


def _read(root: Path, approvals: str, tmp_path: Path, monkeypatch) -> int:
    frame, fr, sigmas = _world()
    monkeypatch.setattr(ec, "build_panel", lambda inputs: (frame, fr))
    monkeypatch.setattr(ec, "har_sigmas", lambda *a, **k: sigmas)
    inputs = tmp_path / "inputs.pkl"
    inputs.write_bytes(pickle.dumps({"prices": None, "fetched": "2027-01-10"}))
    return sr.main(["H-101", "--read", "--inputs", str(inputs), "--approvals", approvals,
                    "--root", str(root)])


def test_the_read_waits_for_its_claim_on_output(key_repo, tmp_path, monkeypatch, capsys):
    root, approvals = key_repo
    assert _read(root, approvals, tmp_path, monkeypatch) == 2
    assert "claim is not on the output branch" in capsys.readouterr().out
    assert sr.main(["H-101", "--claim", "--approvals", approvals, "--root", str(root)]) == 0
    assert _read(root, approvals, tmp_path, monkeypatch) == 2, "written is not pushed"
    assert not list((root / "results" / ra.SEALED_RECORDS).rglob("*.md"))


def test_a_claimed_read_writes_its_result_and_the_ledger_follows(key_repo, tmp_path, monkeypatch, capsys):
    root, approvals = key_repo
    assert sr.main(["H-101", "--claim", "--approvals", approvals, "--root", str(root)]) == 0
    _publish(root)
    assert ra.check_sealed_reads(root) and "lost read" in ra.check_sealed_reads(root)[0].message
    assert sr.main(["H-101", "--claim", "--approvals", approvals, "--root", str(root)]) == 2
    capsys.readouterr()

    assert _read(root, approvals, tmp_path, monkeypatch) == 0
    report = capsys.readouterr().out
    assert report.startswith("# Sealed read — H-101 (conditioner class)")
    _publish(root)
    recs = ra.ci_sealed_reads(root, "output")
    result = next(r for r in recs if r["kind"] == "result")
    assert result["verdict"] in cb.VERDICTS and result["report_sha256"] == sr._sha(report)
    assert result["bar_fingerprint"] == ra.bar_fingerprint(root, "conditioner") is not None
    assert ra.check_sealed_reads(root) == []

    # the ledger: missing until synced, then exactly the records
    assert "no Sealed read (ledger)" in ra.check_sealed_read_field(root)[0].message
    assert sr.main(["H-101", "--sync-field", "--root", str(root)]) == 0
    assert ra.check_sealed_read_field(root) == []
    entry = dp.entry_text((root / dp.HYPOTHESES).read_text(), "H-101")
    field = dp.field_block(entry, dp.SEALED_READ)
    assert f"`{result['verdict']}`" in field and "report `results/sealed_reads/H-101/" in field
    # the stamp the audit approved does not move when the ledger is written
    assert dp.stamped_text(entry) == dp.stamped_text(dp.entry_text(
        (root / dp.HYPOTHESES).read_text().replace(field, ""), "H-101"))


def test_a_read_class_is_refused_for_every_later_run(key_repo, tmp_path, monkeypatch):
    root, approvals = key_repo
    assert sr.main(["H-101", "--claim", "--approvals", approvals, "--root", str(root)]) == 0
    _publish(root)
    assert sk.preflight(root, "H-101") == [], "the run that claimed it goes on to read"
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    assert any("slice is already read" in r for r in sk.preflight(root, "H-101")), \
        "a re-run of a run that claimed is a second read"
    monkeypatch.setenv("GITHUB_RUN_ID", "8")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    assert any("slice is already read" in r for r in sk.preflight(root, "H-101"))


def test_a_misspelt_cell_is_refused_before_the_key(ci_repo):
    _promote(ci_repo, prereg=PREREG.replace('"Elevated"', '"Elevatd"'))
    assert any("never writes" in r for r in sk.preflight(ci_repo, "H-101"))


def test_no_data_step_runs_outside_the_key_job(key_repo, monkeypatch, capsys, tmp_path):
    root, approvals = key_repo
    monkeypatch.setenv("GITHUB_JOB", "preflight")
    for step in (["--claim"], ["--fetch", "--inputs", str(tmp_path / "x")],
                 ["--read", "--inputs", str(tmp_path / "x")]):
        assert sr.main(["H-101", *step, "--approvals", approvals, "--root", str(root)]) == 2
    assert not (root / "results" / ra.SEALED_RECORDS).exists()
    assert not (tmp_path / "x").exists()


def test_check_needs_no_ci_and_reads_no_data(ci_repo, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS")
    _promote(ci_repo)
    assert sr.main(["H-101", "--check", "--root", str(ci_repo)]) == 0
    assert "can walk `frag_or`" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# record_audit's sealed-read checks, one defect at a time
# ---------------------------------------------------------------------------

def _claim(root: Path, stamp: str, *, hid="H-101", cls="conditioner", run_id="7", fp=None) -> str:
    path = f"{ra.SEALED_RECORDS}/{hid}/{stamp}.claim.json"
    rec = {"kind": "claim", "hid": hid, "class": cls, "arm": "frag_or", "horizon": 5,
           "tier": "ci", "run": f"https://github.com/o/r/actions/runs/{run_id}", "run_id": run_id,
           "run_attempt": "1", "claimed_at": stamp, "sealed_from": "2018-01-01",
           "sealed_until": "2026-09-07", "bar_fingerprint": fp or ra.bar_fingerprint(ROOT, cls)}
    return path, json.dumps(rec)


def _result(claim_path: str, hid="H-101") -> tuple[str, str]:
    path = claim_path.replace(".claim.json", ".json")
    return path, json.dumps({"kind": "result", "hid": hid, "class": "conditioner", "claim": claim_path,
                             "tier": "ci", "run": "https://github.com/o/r/actions/runs/7",
                             "verdict": "no_edge", "reason": "r", "arm": "frag_or", "horizon": 5})


def test_a_claim_then_its_result_is_clean(bar_repo):
    c = _claim(bar_repo, "2027-01-10T1400Z")
    _commit_output(bar_repo, dict([c]))
    _commit_output(bar_repo, dict([_result(c[0])]))
    assert ra.check_sealed_reads(bar_repo) == []


def test_a_result_that_landed_with_its_claim_is_red(bar_repo):
    c = _claim(bar_repo, "2027-01-10T1400Z")
    _commit_output(bar_repo, dict([c, _result(c[0])]))
    assert "did not land after its claim" in ra.check_sealed_reads(bar_repo)[0].message


def test_a_second_claim_in_the_class_is_red(bar_repo):
    a = _claim(bar_repo, "2027-01-10T1400Z")
    b = _claim(bar_repo, "2027-02-10T1400Z", hid="H-102", run_id="9")
    _commit_output(bar_repo, dict([a, b]))
    _commit_output(bar_repo, dict([_result(a[0]), _result(b[0], hid="H-102")]))
    msgs = [f.message for f in ra.check_sealed_reads(bar_repo)]
    assert any("claimed 2 times" in m for m in msgs)


def test_a_bar_changed_after_its_read_is_red_until_the_owner_pins_it(bar_repo, monkeypatch):
    c = _claim(bar_repo, "2027-01-10T1400Z", fp="sha256:" + "0" * 64)
    _commit_output(bar_repo, dict([c]))
    _commit_output(bar_repo, dict([_result(c[0])]))
    [f] = ra.check_sealed_reads(bar_repo)
    assert f.red and "bar changed since its sealed read" in f.message
    now = ra.bar_fingerprint(bar_repo, "conditioner")
    monkeypatch.setattr(ra, "BAR_EDITS_AFTER_READ", {"conditioner": (now, "#19")})
    [f] = ra.check_sealed_reads(bar_repo)
    assert not f.red and "the owner accepted it" in f.message


def test_a_void_pin_without_its_claim_is_red(bar_repo, monkeypatch):
    monkeypatch.setattr(ra, "VOIDED_CLAIMS", {"sealed_reads/H-101/x.claim.json": "#19"})
    assert "drop the pin" in ra.check_sealed_reads(bar_repo)[0].message


def test_a_hand_written_sealed_read_field_is_red(ci_repo):
    path = ci_repo / dp.HYPOTHESES
    entry = dp.entry_text(path.read_text(), "H-101")
    path.write_text(path.read_text().replace(
        entry, entry.rstrip() + f"\n\n**{dp.SEALED_READ}.** `edge`, honestly.\n", 1))
    assert "only CI writes that field" in ra.check_sealed_read_field(ci_repo)[0].message


# ---------------------------------------------------------------------------
# the bar's fingerprint: what a class is read by, and nothing else
# ---------------------------------------------------------------------------

def _edit(root: Path, name: str, old: str, new: str) -> None:
    p = root / ".macro-assist" / f"{name}.py"
    text = p.read_text()
    assert text.count(old) == 1, old
    p.write_text(text.replace(old, new))


@pytest.mark.parametrize("name, old, new, moves", [
    ("class_bars", 'block=4, min_blocks=10', 'block=4, min_blocks=11', False),     # the other class's bar
    ("class_bars", 'episode_depth=0.10, min_episodes=5', 'episode_depth=0.10, min_episodes=4', False),  # ADR-0023's bar
    ("class_bars", 'print("\\n\\n".join', 'print("\\n\\n\\n".join', False),       # the command line
    ("class_bars", 'f"  seal: {seal}",', 'f"  seal (decided): {seal}",', False),      # the printer
    ("class_bars", 'cell_min_episodes=3, episode_gap=BLOCK_DAYS', 'cell_min_episodes=2, episode_gap=BLOCK_DAYS', True),
    ("class_bars", 'if skill["ci"]["hi"] < 0:', 'if skill["ci"]["hi"] < -0.01:', True),  # the verdict
    ("score_distributions", "MIN_SKILL = 0.02", "MIN_SKILL = 0.01", True),       # what it imports
    ("numeric_baseline", "import gzip", "import gzip  # unrelated", False),
])
def test_the_fingerprint_moves_with_the_class_bar_and_nothing_else(bar_repo, name, old, new, moves):
    before = ra.bar_fingerprint(bar_repo, "conditioner")
    _edit(bar_repo, name, old, new)
    assert (ra.bar_fingerprint(bar_repo, "conditioner") != before) is moves


def test_the_risk_bar_moves_its_own_fingerprint_and_not_the_conditioners(bar_repo):
    risk, cond = ra.bar_fingerprint(bar_repo, "risk_rule"), ra.bar_fingerprint(bar_repo, "conditioner")
    _edit(bar_repo, "class_bars", "episode_depth=0.10, min_episodes=5", "episode_depth=0.10, min_episodes=4")
    assert ra.bar_fingerprint(bar_repo, "risk_rule") != risk
    assert ra.bar_fingerprint(bar_repo, "conditioner") == cond


def test_a_class_that_does_not_exist_has_no_fingerprint():
    assert ra.bar_fingerprint(ROOT, "conditioner") and ra.bar_fingerprint(ROOT, "gap_width")
    assert ra.bar_fingerprint(ROOT, "risk_rule")
    assert ra.bar_fingerprint(ROOT, "nope") is None


# ---------------------------------------------------------------------------
# the workflow's shape, and the auditor's bundle
# ---------------------------------------------------------------------------

def test_the_runner_runs_only_after_the_key_and_only_on_a_real_run():
    wf = yaml.safe_load((ROOT / sr.WORKFLOW).read_text())
    assert wf["concurrency"]["group"] == "sealed-read", "one sealed read at a time, repo-wide"
    steps = wf["jobs"]["key"]["steps"]
    names = [s["name"] for s in steps]
    key = names.index("Check the key, then the entry again")
    runner = [i for i, s in enumerate(steps) if ".macro-assist/sealed_runner.py" in s.get("run", "")]
    assert runner and min(runner) > key
    for i in runner:
        assert "!inputs.dry_run" in steps[i]["if"], names[i]
    for s in steps[:key + 1]:
        assert "sealed_runner.py" not in s.get("run", "")
    assert not any(".macro-assist/sealed_runner.py" in s.get("run", "")
                   for s in wf["jobs"]["preflight"]["steps"])
    fred = [n for n, s in zip(names, steps) if "FRED_API_KEY" in (s.get("env") or {})]
    assert fred == ["Fetch the inputs (nothing scored)"]
    claim, read = names.index("Claim the slice, before anything is scored"), names.index("The sealed read")
    assert "ci_publish_results.sh" in steps[claim]["run"] and claim < read, \
        "the claim is pushed before anything is scored"


def test_no_other_workflow_calls_the_runners_data_steps():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        if wf.name == Path(sr.WORKFLOW).name:
            continue
        assert not re.search(r"sealed_runner\.py[^\n]*--(fetch|claim|read)\b", wf.read_text()), wf.name


def test_the_bundle_carries_the_class_bar_only_for_a_pre_registration(ci_repo):
    shutil.copy(ROOT / ".macro-assist" / "class_bars.py", ci_repo / ".macro-assist" / "class_bars.py")
    assert "The class bar its" not in ae.build_bundle(ci_repo, "H-101").material
    _promote(ci_repo)
    material = ae.build_bundle(ci_repo, "H-101").material
    assert "The class bar its `Pre-registration` names" in material
    assert "def verdict(bar: ClassBar" in material and '"floor": {' in material


def test_a_pre_registration_that_does_not_parse_says_so_in_the_bundle(ci_repo):
    shutil.copy(ROOT / ".macro-assist" / "class_bars.py", ci_repo / ".macro-assist" / "class_bars.py")
    _promote(ci_repo, prereg="**Pre-registration.** In words only.\n\n")
    material = ae.build_bundle(ci_repo, "H-101").material
    assert "**It does not parse:**" in material and "def verdict(" not in material
