"""
audit_entry.py is the judge the proposer may not be (ADR-0022). These tests
hold the parts of it that are code, offline, with no API call:

- the bundle is built from the record and the page, and only from them;
- the verdict is derived by code and cannot be an approval the model wrote;
- the canary set is non-empty, every canary plants exactly what it says it
  plants, and a canary is bundled by the same code as a real entry;
- the canary score cannot be passed by an auditor that rejects everything.

Whether the model actually catches the canaries is not a unit test. It costs
money and is run by CI (`auditor_canaries.yml`), which records the result.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import audit_entry as ae
import decision_packet as dp

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
SECTIONS = ["## 1. Facts from code", "## 2. The entry under audit", "## 3. The entry's history",
            "## 4. Reports the entry names", "## 5. Knowledge Base entries the entry cites",
            "## 6. Work packages the entry cites", "## 7. What to return"]


def _headings(material: str) -> list[str]:
    """The bundle's own top-level sections — not the headings inside fenced
    material, which belong to the entry, the reports and the KB."""
    out, fence = [], None
    for ln in material.splitlines():
        m = re.match(r"^(`{5,})", ln)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence is None and re.match(r"^## \d\. ", ln):
            out.append(ln)
    return out


def _answer(blocking: tuple[str, ...] = (), unanswered: tuple[int, ...] = ()) -> dict:
    return {
        "findings": [{"category": c, "blocking": True, "questions": [1],
                      "claim": f"planted {c}", "evidence": "§2"} for c in blocking],
        "questions": [{"number": n, "status": "unanswered" if n in unanswered else "answered",
                       "note": "…"} for n in range(1, 12)],
        "brief": {"case_against": "a", "what_it_claims": "b", "what_would_change_it": "c"},
    }


def _message(answer, *, stop: str = "end_turn", text: str | None = None):
    return SimpleNamespace(
        stop_reason=stop, stop_details=None, model="claude-opus-5", _request_id="req_x",
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(answer) if text is None else text)],
        usage=SimpleNamespace(input_tokens=20_000, output_tokens=4_000,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """Stands in for `anthropic.Anthropic()`: records every request and answers
    with `respond(request) -> message`."""

    def __init__(self, respond):
        self.respond, self.calls = respond, []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        return _Stream(self.respond(kw))


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def h008():
    return ae.build_bundle(ROOT, "H-008", now=NOW)


def test_a_real_bundle_has_every_section_in_order(h008):
    assert _headings(h008.material) == SECTIONS


def test_the_entry_is_exactly_the_register_text(h008):
    register = (ROOT / dp.HYPOTHESES).read_text(encoding="utf-8")
    entry = ae.entry_text(register, "H-008")
    assert entry.startswith("## H-008 — ")
    assert "## Closed" not in entry, "the last entry must not carry the register's index"
    assert "## H-007" not in h008.material
    assert h008.fingerprint == hashlib.sha256(dp.stamped_text(entry).encode()).hexdigest()
    assert entry.rstrip() in h008.material


def test_facts_and_citations_come_from_the_tree(h008):
    assert "(`numeric_baseline.SEAL_START`): 2018-01-01." in h008.material
    assert "`dd_x_frag`" in h008.material                     # the harness vocabulary
    for kb in ("KB-016", "KB-017", "KB-033"):                 # what H-008 cites
        assert f"### {kb}\n" in h008.material
    assert "`results/explore_conditioner/report.md`" in h008.material
    # the questions are the page's, not a copy
    questions = dp.parse_questions((ROOT / dp.HOW_WE_EXPLORE).read_text(encoding="utf-8"))
    for q in questions:
        assert f"{q.number}. *({q.group})* {q.text}" in h008.material
    assert h008.rules == (ROOT / dp.HOW_WE_EXPLORE).read_text(encoding="utf-8")


def test_an_unknown_entry_is_refused():
    with pytest.raises(ae.BundleError, match="H-999"):
        ae.build_bundle(ROOT, "H-999")


def test_a_fence_outlasts_the_backticks_inside_it():
    lines = ae._fence("a\n```\ncode\n```\n``````\n")
    assert lines[0] == "`" * 7 and lines[-1] == "`" * 7


def test_the_instructions_do_not_copy_the_checklist():
    """§9 is read from the page at run time (convention #8); a copy in the
    prompt would drift from it."""
    text = (ROOT / ae.INSTRUCTIONS).read_text(encoding="utf-8")
    for q in dp.parse_questions((ROOT / dp.HOW_WE_EXPLORE).read_text(encoding="utf-8")):
        assert q.text not in text
    assert "Question 12" in text
    for c in ae.CATEGORIES:                                  # every category is defined for the model
        assert f"`{c}`" in text


# ---------------------------------------------------------------------------
# the verdict is code
# ---------------------------------------------------------------------------

def test_the_verdict_is_derived_not_returned():
    assert "verdict" not in json.dumps(ae.RESPONSE_SCHEMA)
    ok = ae.parse_answer(_answer())
    assert ae.derive_verdict(ok) == ("no_blocking_finding", [])
    verdict, reasons = ae.derive_verdict(ae.parse_answer(_answer(blocking=("sealed_slice",))))
    assert verdict == "reject" and reasons == ["blocking finding: sealed_slice"]
    verdict, reasons = ae.derive_verdict(ae.parse_answer(_answer(unanswered=(8,))))
    assert verdict == "reject" and reasons == ["question 8: unanswered"]


def test_a_non_blocking_finding_does_not_reject():
    a = _answer()
    a["findings"] = [{"category": "other", "blocking": False, "questions": [], "claim": "x",
                      "evidence": "y"}]
    assert ae.derive_verdict(ae.parse_answer(a))[0] == "no_blocking_finding"


@pytest.mark.parametrize("breakage", ["missing_q", "twice", "category", "brief", "status"])
def test_a_malformed_answer_is_not_a_pass(breakage):
    a = _answer()
    if breakage == "missing_q":
        a["questions"] = a["questions"][:-1]
    elif breakage == "twice":
        a["questions"].append(dict(a["questions"][0]))
    elif breakage == "category":
        a["findings"] = [{"category": "looks_fine", "blocking": False, "questions": [],
                          "claim": "", "evidence": ""}]
    elif breakage == "brief":
        a["brief"]["case_against"] = " "
    elif breakage == "status":
        a["questions"][0]["status"] = "probably"
    with pytest.raises(ae.InvalidAudit):
        ae.parse_answer(a)


def test_question_12_is_not_the_auditors_to_answer():
    a = _answer()
    a["questions"].append({"number": 12, "status": "answered", "note": "I passed it"})
    assert 12 not in ae.parse_answer(a).questions


def test_the_schema_is_closed():
    """Structured outputs need every object closed and every property required."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
    walk(ae.RESPONSE_SCHEMA)
    enum = ae.RESPONSE_SCHEMA["properties"]["findings"]["items"]["properties"]["category"]["enum"]
    assert enum == list(ae.CATEGORIES)


def test_the_request_is_one_fresh_context_call(h008):
    client = FakeClient(lambda kw: _message(_answer()))
    rec = ae.audit(h008, "INSTRUCTIONS", client=client, model="claude-opus-5", effort="high")
    (kw,) = client.calls
    assert kw["system"][0] == {"type": "text", "text": "INSTRUCTIONS"}
    assert kw["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert h008.rules in kw["system"][1]["text"]
    assert kw["messages"] == [{"role": "user", "content": h008.material}]
    assert "tools" not in kw
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["schema"] is ae.RESPONSE_SCHEMA
    assert rec["verdict"] == "no_blocking_finding"
    assert rec["entry_fingerprint"] == f"sha256:{h008.fingerprint}"
    assert rec["est_cost_usd"] == pytest.approx((20_000 * 5 + 4_000 * 25) / 1e6)


@pytest.mark.parametrize("stop,text", [("refusal", None), ("max_tokens", None),
                                       ("end_turn", "{not json")])
def test_an_incomplete_call_is_not_a_pass(h008, stop, text):
    client = FakeClient(lambda kw: _message(_answer(), stop=stop, text=text))
    with pytest.raises(ae.AuditNotRun):
        ae.audit(h008, "I", client=client, model="claude-opus-5", effort="high")


def test_a_local_record_says_it_is_local(h008, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    rec = ae.audit(h008, "I", client=FakeClient(lambda kw: _message(_answer())),
                   model="claude-opus-5", effort="high")
    assert rec["tier"] == "local" and rec["run"] is None
    assert "does not satisfy §9 question 12" in ae.render_record(rec)
    assert ae.render_record(rec).index("## The case against") < ae.render_record(rec).index("## Findings")


# ---------------------------------------------------------------------------
# the canaries
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def canaries():
    return ae.load_canaries(ROOT)


@pytest.fixture(scope="module")
def bundles(canaries, tmp_path_factory):
    base, variants = canaries
    work = tmp_path_factory.mktemp("canaries")
    return {c.name: ae.canary_bundle(ROOT, c, work, now=NOW) for c in (base, *variants)}


def test_the_canary_set_is_non_empty_with_a_finding_each(canaries):
    base, variants = canaries
    assert base.expect is None
    assert len(variants) >= 4, "WP-25.A: at least four planted defects"
    expects = [c.expect for c in variants]
    assert len(set(expects)) == len(expects), "one canary per defect"
    assert {"bar_after_data", "signed_forecast", "sealed_slice", "thin_evidence"} <= set(expects), \
        "the four ADR-0022 names"
    for c in variants:
        assert c.expect in ae.CATEGORIES and c.planted.strip()


def test_an_edit_that_does_not_apply_exactly_once_is_refused(tmp_path):
    src = ROOT / ae.CANARY_DIR
    dest = tmp_path / ae.CANARY_DIR
    dest.mkdir(parents=True)
    import shutil
    shutil.copytree(src / ae.BASE, dest / ae.BASE)
    (dest / "broken").mkdir()
    (dest / "broken" / "canary.json").write_text(json.dumps({
        "expect": "number_mismatch", "planted": "x",
        "edits": [{"file": "entry-v2.md", "old": "this text is nowhere", "new": "y"}]}))
    with pytest.raises(ae.CanaryError, match="matches 0 times"):
        ae.load_canaries(tmp_path)


def test_a_canary_is_bundled_exactly_like_a_real_entry(bundles, h008):
    for name, b in bundles.items():
        assert _headings(b.material) == SECTIONS, name
        assert b.rules == h008.rules, name


def test_nothing_in_a_canary_bundle_says_canary(canaries, bundles):
    base, variants = canaries
    for c in variants:
        text = bundles[c.name].material
        assert "canary" not in text.lower(), c.name
        assert c.planted not in text, c.name


def test_the_clean_base_replays_as_a_real_history(bundles):
    b = bundles[ae.BASE].material
    assert b.count("\nCOMMIT ") == 2                             # drafted, then the ledger
    assert "2026-09-25T10:14:09+02:00  register: draft H-101" in b
    assert "- `" in b and "2026-09-26T21:40:52+02:00  explore conditioner`" in b
    assert "matches the latest committed version" in b
    assert "report dates 2010-06-25 → 2017-12-29" in b


def test_nothing_the_clean_base_cites_postdates_it(canaries, bundles):
    """The first paid run (2026-09-28) rejected the clean base as backdated: it
    was dated August and cited text dated September. The cited KB entries and
    work packages are frozen excerpts now; every one must be found, and none
    may carry a date after the entry's first commit."""
    base, _ = canaries
    b = bundles[ae.BASE].material
    assert "Not found in" not in b
    drafted = min(datetime.fromisoformat(k["date"]) for k in base.commits).date().isoformat()
    frozen = ROOT / ae.CANARY_DIR / ae.BASE / ae.FROZEN_DIR
    for name in ae.CANARY_FROZEN.values():
        dates = re.findall(r"\b20\d\d-\d\d-\d\d\b", (frozen / name).read_text(encoding="utf-8"))
        assert dates and max(dates) < drafted, (name, max(dates), drafted)


def test_the_cost_estimate_prices_each_model_as_itself():
    """`claude-opus-5-5` starts with `claude-opus-5-`; a prefix match that took
    the first hit priced Opus 5.5 as Opus 5. Checked against the first paid
    run's record ($3.51 on Opus 5) and the published rates."""
    usage = {"input_tokens": 144_169, "output_tokens": 108_146,
             "cache_creation_input_tokens": 9_528, "cache_read_input_tokens": 57_168}
    assert ae.estimate_usd("claude-opus-5", usage) == pytest.approx(3.5127, abs=1e-3)
    assert ae.estimate_usd("claude-opus-5-5", usage) == pytest.approx(2.7989, abs=1e-3)
    assert ae.estimate_usd("claude-opus-5-5-20261001", usage) == ae.estimate_usd("claude-opus-5-5", usage)
    assert ae.estimate_usd("claude-unknown", usage) is None
    assert ae.DEFAULT_MODEL in ae.PRICES


def test_the_facts_say_what_a_multiplicity_line_counts(h008):
    """The harness prints `len(ALL_ARMS) - 1` arms; the facts list the whole
    vocabulary. Without the reconciling sentence the auditor flagged 13 vs 14."""
    arms = dp.harness_arms(ROOT)
    assert f"multiplicity line counts {len(arms) - 1} arms" in h008.material


def test_each_canary_plants_where_it_says(bundles):
    base = bundles[ae.BASE]
    # history only: the final text is word for word the clean base's
    b = bundles["bar_after_data"]
    assert b.fingerprint == base.fingerprint and b.material != base.material
    assert re.search(r"^-\*\*The prediction.*at least 1\.4 times", b.material, re.M)
    assert re.search(r"^\+\*\*The prediction.*at least 1\.2 times", b.material, re.M)
    # a second run on the report, not on the ledger
    assert bundles["uncounted_look"].material.count("explore conditioner") == \
        base.material.count("explore conditioner") + 1
    assert bundles["uncounted_look"].fingerprint == base.fingerprint
    # the report crosses the seal; the entry does not say so
    assert "→ 2019-06-28" in bundles["sealed_slice"].material
    assert bundles["sealed_slice"].fingerprint == base.fingerprint
    # these change what the entry says
    for name in ("number_mismatch", "signed_forecast", "thin_evidence"):
        assert bundles[name].fingerprint != base.fingerprint, name


def _auditor(bundles, canaries, flag):
    """A fake auditor keyed by bundle: `flag(expect)` → the categories it reports
    as blocking on that bundle (expect is None for the clean base)."""
    base, variants = canaries
    by_sha = {hashlib.sha256(bundles[c.name].material.encode()).hexdigest(): c.expect
              for c in (base, *variants)}

    def respond(kw):
        expect = by_sha[hashlib.sha256(kw["messages"][0]["content"].encode()).hexdigest()]
        return _message(_answer(blocking=tuple(flag(expect))))
    return FakeClient(respond)


def test_an_auditor_that_catches_each_defect_passes(bundles, canaries):
    client = _auditor(bundles, canaries, lambda e: [e] if e else [])
    suite = ae.run_canaries(ROOT, client=client, model="claude-opus-5", effort="high", now=NOW)
    assert suite["passed"], suite["canaries"]
    assert suite["clean_base_verdict"] == "no_blocking_finding"
    assert len(client.calls) == 1 + len(canaries[1])


def test_an_auditor_that_rejects_everything_fails(bundles, canaries):
    """The point of the clean base: rejecting is easy."""
    client = _auditor(bundles, canaries, lambda e: list(ae.CATEGORIES))
    suite = ae.run_canaries(ROOT, client=client, model="claude-opus-5", effort="high", now=NOW)
    assert not suite["passed"]
    assert all("also raised against the clean base" in r["why"] for r in suite["canaries"])


def test_an_auditor_that_finds_nothing_fails(bundles, canaries):
    client = _auditor(bundles, canaries, lambda e: [])
    suite = ae.run_canaries(ROOT, client=client, model="claude-opus-5", effort="high", now=NOW)
    assert not suite["passed"]
    assert all(not r["caught"] for r in suite["canaries"])


def test_an_auditor_that_finds_the_wrong_thing_fails(bundles, canaries):
    client = _auditor(bundles, canaries, lambda e: ["other"] if e else [])
    suite = ae.run_canaries(ROOT, client=client, model="claude-opus-5", effort="high", now=NOW)
    assert not suite["passed"] and all(r["rejected"] and not r["caught"] for r in suite["canaries"])


def test_a_base_that_did_not_run_fails_every_canary(bundles, canaries):
    base_sha = hashlib.sha256(bundles[ae.BASE].material.encode()).hexdigest()
    inner = _auditor(bundles, canaries, lambda e: [e] if e else [])

    def respond(kw):
        if hashlib.sha256(kw["messages"][0]["content"].encode()).hexdigest() == base_sha:
            return _message(None, stop="refusal")
        return inner.respond(kw)
    suite = ae.run_canaries(ROOT, client=FakeClient(respond), model="claude-opus-5",
                            effort="high", now=NOW)
    assert not suite["passed"]
    assert all("nothing is discriminated" in r["why"] for r in suite["canaries"])


def test_the_spend_guard_stops_the_suite(bundles, canaries):
    client = _auditor(bundles, canaries, lambda e: [e] if e else [])
    suite = ae.run_canaries(ROOT, client=client, model="claude-opus-5", effort="high",
                            max_usd=0.01, now=NOW)
    assert len(client.calls) == 1 and not suite["passed"]
    assert all("spend guard" in r["why"] for r in suite["canaries"])


def test_an_empty_canary_set_cannot_pass():
    assert ae.score_canaries([], {}) == (False, [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_offline_modes_make_no_call(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ae.main(["h-008", "--bundle-only", "--root", str(ROOT)]) == 0
    assert capsys.readouterr().out.startswith("# Audit bundle — H-008")
    assert ae.main(["--check-canaries", "--root", str(ROOT)]) == 0
    assert "no API call made" in capsys.readouterr().out
    assert ae.main(["--bundle-only", "--canary", "thin_evidence", "--root", str(ROOT)]) == 0
    assert "# Audit bundle — H-101" in capsys.readouterr().out


def test_cli_without_a_key_says_where_the_suite_runs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="auditor_canaries.yml"):
        ae.main(["--canaries", "--root", str(ROOT)])


# ---------------------------------------------------------------------------
# the promotion tier (WP-25.C): CI runs it, CI records it
#
# The clean canary replayed into a throwaway repository — register on main, a
# report on an orphan output, full history — with the real auditor directory
# copied in and a passing canary suite committed to output for the current
# instructions and canary set. Each refusal is driven one condition at a time.
# ---------------------------------------------------------------------------

import os
import shutil
import subprocess

import record_audit as ra

CI_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "7", "GITHUB_REPOSITORY": "o/r",
          "GITHUB_SERVER_URL": "https://github.com", "GITHUB_REF": "refs/heads/main"}


def _commit_output(root: Path, files: dict[str, str], msg: str = "output") -> None:
    """Commit `files` onto `output` with plumbing, leaving main's tree alone."""
    env = {**os.environ, "GIT_INDEX_FILE": str(root / ".git" / "test-output-index"),
           "GIT_AUTHOR_NAME": "bot", "GIT_AUTHOR_EMAIL": "b@b",
           "GIT_COMMITTER_NAME": "bot", "GIT_COMMITTER_EMAIL": "b@b"}

    def g(*args, data=None):
        r = subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    parent = g("rev-parse", "output")
    g("read-tree", parent)
    for path, text in files.items():
        blob = g("hash-object", "-w", "--stdin", data=text)
        g("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
    g("update-ref", "refs/heads/output", g("commit-tree", g("write-tree"), "-p", parent, "-m", msg))


def _suite_json(root: Path, **over) -> str:
    return json.dumps({"schema": 1, "passed": True, "tier": "ci", "requested_model": ae.DEFAULT_MODEL,
                       "effort": ae.DEFAULT_EFFORT,
                       "instructions_sha256": ae._sha(ae.read_instructions(root)),
                       "canary_set_sha256": ae.canary_set_sha(root), **over})


def _ci_record(root: Path, hid: str, verdict: str, *, text: str | None = None) -> str:
    entry = text or dp.entry_text((root / dp.HYPOTHESES).read_text(), hid)
    return json.dumps({"schema": 1, "hid": hid, "tier": "ci", "run": "https://github.com/o/r/actions/runs/1",
                       "entry_fingerprint": "sha256:" + ae._sha(dp.stamped_text(entry)),
                       "verdict": verdict, "reasons": ["blocking finding: other"] if verdict == "reject" else []})


@pytest.fixture
def ci_repo(canaries, tmp_path, monkeypatch):
    base, _ = canaries
    root = ae.materialize(ROOT, base, tmp_path / "repo")
    shutil.copytree(ROOT / ae.AUDITOR_DIR, root / ae.AUDITOR_DIR)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "bot"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "b@b"], check=True)
    _commit_output(root, {"audit/canaries/2026-09-28T2005Z-abcdef12.json": _suite_json(root)})
    for k, v in CI_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(ra, "OWNER_RESUBMISSIONS", {})
    return root


def _pf(root: Path, **kw):
    return ae.preflight(root, "H-101", model=kw.get("model", ae.DEFAULT_MODEL),
                        effort=kw.get("effort", ae.DEFAULT_EFFORT))


def test_a_certified_ci_audit_passes_preflight(ci_repo, capsys):
    pf = _pf(ci_repo)
    assert pf.certified_by == "audit/canaries/2026-09-28T2005Z-abcdef12.json"
    assert pf.history_commits == 2 and pf.prior == []
    assert ae.main(["H-101", "--ci", "--dry-run", "--root", str(ci_repo)]) == 0
    out = capsys.readouterr().out
    assert "No API call was made and nothing was recorded" in out
    assert not (ci_repo / "results" / "audit" / "entries").exists()


def test_outside_ci_or_off_main_is_refused(ci_repo, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    with pytest.raises(ae.Refused, match="the one on main"):
        _pf(ci_repo)
    monkeypatch.delenv("GITHUB_ACTIONS")
    with pytest.raises(ae.Refused, match="runs in CI"):
        _pf(ci_repo)
    assert ae.main(["H-101", "--ci", "--dry-run", "--root", str(ci_repo)]) == 2
    assert "nothing was spent" in capsys.readouterr().err


def test_a_shallow_clone_is_refused(ci_repo, tmp_path):
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", "--no-single-branch",
                    f"file://{ci_repo}", str(shallow)], check=True)
    shutil.copytree(ci_repo / ae.AUDITOR_DIR, shallow / ae.AUDITOR_DIR)
    with pytest.raises(ae.Refused, match="shallow"):
        _pf(shallow)


def test_an_uncertified_configuration_is_refused(ci_repo):
    with pytest.raises(ae.Refused, match="`medium`.*auditor_canaries.yml"):
        _pf(ci_repo, effort="medium")
    # the canary set is one of the four: a suite on another set certifies nothing here
    (ci_repo / ae.CANARY_DIR / "base" / "timeline.json").write_text("{}\n")
    with pytest.raises(ae.Refused, match="canary set"):
        _pf(ci_repo)


def test_the_same_text_twice_is_a_retry_and_refused(ci_repo):
    _commit_output(ci_repo, {"audit/entries/H-101/2026-09-28T2100Z-ci.json": _ci_record(ci_repo, "H-101", "reject")})
    with pytest.raises(ae.Refused, match="retry, not a resubmission"):
        _pf(ci_repo)


def test_a_third_submission_after_two_rejections_is_refused(ci_repo, monkeypatch):
    reg = (ci_repo / dp.HYPOTHESES).read_text()
    old = dp.entry_text(reg, "H-101")
    _commit_output(ci_repo, {f"audit/entries/H-101/2026-09-28T2{i}00Z-ci.json":
                             _ci_record(ci_repo, "H-101", "reject", text=old.replace("Gold", f"Gold{i}"))
                             for i in (1, 2)})
    with pytest.raises(ae.Refused, match="rejected 2 times"):
        _pf(ci_repo)
    monkeypatch.setattr(ra, "OWNER_RESUBMISSIONS", {"H-101": "31"})
    assert _pf(ci_repo).prior and len(_pf(ci_repo).prior) == 2


def test_a_closed_or_uncommitted_entry_is_refused(ci_repo):
    path = ci_repo / dp.HYPOTHESES
    path.write_text(path.read_text().replace("**Status:** `draft`", "**Status:** `closed`", 1))
    with pytest.raises(ae.Refused, match="uncommitted"):
        _pf(ci_repo)
    subprocess.run(["git", "-C", str(ci_repo), "commit", "-qam", "close"], check=True)
    with pytest.raises(ae.Refused, match="closed"):
        _pf(ci_repo)


def test_a_ci_audit_records_its_provenance_and_the_field_follows_the_records(ci_repo, monkeypatch, capsys):
    """End to end, offline: audit → record on output → Audit record field on
    main, which record_audit holds to the records and the stamp ignores."""
    fake = FakeClient(lambda kw: _message(_answer(blocking=("thin_evidence",))))
    monkeypatch.setattr(ae, "_client", lambda: fake)
    before = (ci_repo / dp.HYPOTHESES).read_text()
    assert ae.main(["H-101", "--ci", "--root", str(ci_repo)]) == 0 and len(fake.calls) == 1
    (rec_path,) = (ci_repo / "results" / "audit" / "entries" / "H-101").glob("*.json")
    rec = json.loads(rec_path.read_text())
    assert rec["tier"] == "ci" and rec["run"] == "https://github.com/o/r/actions/runs/7"
    assert rec["certified_by"] == "audit/canaries/2026-09-28T2005Z-abcdef12.json"
    assert rec["canary_set_sha256"] == ae.canary_set_sha(ci_repo) and rec["verdict"] == "reject"
    assert "audited_at" in rec

    # CI publishes the record, then writes the field from what it published
    assert ra.check_audit_record_field(ci_repo) == []           # nothing on output yet
    _commit_output(ci_repo, {f"audit/entries/H-101/{rec_path.name}": rec_path.read_text()})
    assert [f.message for f in ra.check_audit_record_field(ci_repo)][0].startswith(
        "CI audited it 1 time(s) and the entry has no Audit record")
    assert ae.sync_field(ci_repo) == ["H-101"] and ae.sync_field(ci_repo) == []
    after = (ci_repo / dp.HYPOTHESES).read_text()
    entry = dp.entry_text(after, "H-101")
    assert "**Audit record.** Written by CI" in entry and "1 audit, 1 rejection." in entry
    assert "`reject` (blocking finding: thin_evidence)" in entry
    assert dp.stamped_text(entry) == dp.stamped_text(dp.entry_text(before, "H-101"))
    assert ra.check_audit_record_field(ci_repo) == []

    # the same text cannot be audited again: the field did not change the stamp
    subprocess.run(["git", "-C", str(ci_repo), "commit", "-qam", "audit record"], check=True)
    with pytest.raises(ae.Refused, match="retry"):
        _pf(ci_repo)
