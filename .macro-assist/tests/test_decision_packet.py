"""
decision_packet.py parses two living documents — the register and
how-we-explore §9 — and both will be edited. A silent parse failure here is the
worst outcome: the worksheet would come back short and look finished. These
tests hold it to the real pages, not to fixtures, so a format change fails here
rather than in front of an owner who trusts the blank list.

They also hold the two rules the tool exists to keep: it never recommends, and
its `--check` output claims presence, not adequacy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import decision_packet as dp

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def entries():
    return dp.parse_entries((ROOT / dp.HYPOTHESES).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def questions():
    return dp.parse_questions((ROOT / dp.HOW_WE_EXPLORE).read_text(encoding="utf-8"))


def test_every_register_entry_parses(entries):
    """One Entry per `## H-###` heading, each with a status from the register's
    own vocabulary."""
    assert len(entries) >= 7
    ids = [e.hid for e in entries]
    assert ids == sorted(ids), "entries should come back in page order"
    assert all(e.status in ("draft", "seen", "proposed", "promoted", "closed")
               for e in entries), [(e.hid, e.status) for e in entries]


def test_fixed_format_fields_are_found(entries):
    """The format is fixed (hypotheses.md header). If a field stops parsing the
    packet quietly loses a question's evidence, so assert the shape."""
    h002 = next(e for e in entries if e.hid == "H-002")
    for name in ("What was seen", "Where", "Mechanism it would imply",
                 "The confound", "What would test it", "Target-space check"):
        assert name in h002.fields, f"{name} no longer parses out of H-002"
        assert h002.fields[name].strip()
        assert h002.field_lines[name] > h002.line


def test_all_twelve_questions_parse(questions):
    """§9 is the checklist the packet is built from; twelve is the count the
    page states. Fewer means the page was renumbered and the mapping table in
    decision_packet.FIELDS_FOR_QUESTION needs looking at."""
    assert [q.number for q in questions] == list(range(1, 13))
    assert all(q.text.endswith("?") for q in questions), [q.text for q in questions]
    assert {q.group for q in questions} == {
        "The claim", "The mechanism", "The bar", "The record"}


def test_question_mapping_covers_the_checklist(questions):
    assert set(dp.FIELDS_FOR_QUESTION) == {q.number for q in questions}
    unowned = [n for n, f in dp.FIELDS_FOR_QUESTION.items() if not f]
    assert unowned == [8, 11, 12], (
        "the floor, the one-read commitment and the competence gate have no slot "
        "in the register's fixed format; if that changed, say so deliberately")


def test_harness_arms_are_the_family_size():
    arms = dp.harness_arms(ROOT)
    assert "unconditional" in arms and "dd_x_frag" in arms
    assert len(arms) > 5, "ARMS/OPTIONAL_ARMS stopped parsing out of the harness"


def test_ledger_counts_dates_not_arms(entries):
    h002 = next(e for e in entries if e.hid == "H-002")
    dates, reports = dp.ledger(h002)
    assert dates == sorted(dates) and len(dates) >= 2
    assert any(r.startswith("results/") for r in reports)


def test_packet_carries_blanks_and_no_recommendation(entries, questions):
    h002 = next(e for e in entries if e.hid == "H-002")
    text = dp.render_packet(ROOT, h002, questions)
    assert text.count("**My answer:**") == 12
    assert text.count("**Needs a counted look:**") == 12
    # the rule from the module docstring: no verdict, no ranking, no readiness.
    # The header states the rule, so "recommendation" appears exactly once there.
    assert "It contains no" in text and "recommendation and nothing in it was measured" in text
    lowered = text.lower()
    for banned in ("i recommend", "we recommend", "i suggest",
                   "looks ready", "should be promoted", "ready to promote"):
        assert banned not in lowered, f"the packet must not say {banned!r}"
    # questions no field owns are named, not skipped
    assert "No field in the register's fixed format owns this question." in text


def test_check_claims_presence_not_adequacy(entries, questions):
    h002 = next(e for e in entries if e.hid == "H-002")
    out = dp.render_check(h002, questions)
    assert "Presence is not adequacy" in out
    assert out.count("NO FIELD") == 3


def test_cli_is_report_only(entries, capsys):
    assert dp.main(["--check", "--all", "--root", str(ROOT)]) == 0
    assert dp.main(["h-002", "--root", str(ROOT)]) == 0   # id is case-insensitive
    assert "# Decision packet — H-002" in capsys.readouterr().out


def test_unknown_entry_is_an_error_that_names_the_register():
    with pytest.raises(SystemExit):
        dp.main(["H-999", "--root", str(ROOT)])
