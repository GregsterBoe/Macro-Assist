"""
Tests for versions.py — the pipeline version record.

Three readers branch on the version stamp: `score_predictions.py` skips post-cut
notes by it, `summarize_accuracy.py` filters the feedback loop by it, and
`tag_versions.py` backfills it onto older files from the date ranges. All three
fail *quietly* when the milestone list is wrong — a gap in the ranges makes
`version_for_date()` return "unknown" and the file simply goes untagged; a
PIPELINE_VERSION that does not match the open milestone stamps new notes with one
version while tagging them as another.

So these tests pin the invariants nothing else checks, plus the one thing the
2026-09-04 archive pass broke and nobody noticed until a bump was attempted: the
docs table and the code disagreeing (Open decision #9).

All pure unit tests — no network.

Run:
    pytest .macro-assist/tests/test_versions.py -v
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import versions
from bump_version import _BEGIN, _END, render_milestones_table
from versions import (
    LAST_DIRECTIONAL_VERSION,
    MIN_FEEDBACK_VERSION,
    PIPELINE_VERSION,
    VERSION_MILESTONES,
    current_milestone,
    has_directional_calls,
    version_for_date,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC = _REPO_ROOT / "docs" / "reference" / "versions.md"

_ALL_VERSIONS = [m.version for m in VERSION_MILESTONES]
_REAL = [m for m in VERSION_MILESTONES if not m.is_zero_range]


# ---------------------------------------------------------------------------
# Shape of the milestone list
# ---------------------------------------------------------------------------

def test_versions_are_unique():
    assert len(_ALL_VERSIONS) == len(set(_ALL_VERSIONS))


def test_all_versions_are_v_prefixed():
    for v in _ALL_VERSIONS:
        assert re.match(r"^v\d+\.\d+$", v), f"malformed version string: {v!r}"


def test_exactly_one_open_milestone():
    assert sum(1 for m in VERSION_MILESTONES if m.is_open) == 1


def test_pipeline_version_is_the_open_milestone():
    """A mismatch stamps new notes with one version and tags them as another."""
    assert PIPELINE_VERSION == current_milestone().version


def test_open_milestone_is_last():
    assert VERSION_MILESTONES[-1].is_open


def test_versions_ascend():
    tuples = [versions._version_tuple(v) for v in _ALL_VERSIONS]
    assert tuples == sorted(tuples), "VERSION_MILESTONES must be in ascending version order"


def test_capabilities_are_present_and_table_safe():
    """Capability text is rendered into a markdown table cell, so no pipes."""
    for m in VERSION_MILESTONES:
        assert m.capability.strip(), f"{m.version} has no capability description"
        assert "|" not in m.capability, f"{m.version} capability would break the table"
        assert "\n" not in m.capability, f"{m.version} capability must be one line"


# ---------------------------------------------------------------------------
# Date coverage — a gap here makes tag_versions.py silently skip files
# ---------------------------------------------------------------------------

def test_real_milestones_are_contiguous_and_non_overlapping():
    for previous, current in zip(_REAL, _REAL[1:]):
        assert current.start == previous.end + timedelta(days=1), (
            f"gap or overlap between {previous.version} (ends {previous.end}) "
            f"and {current.version} (starts {current.start})"
        )


def test_every_real_milestone_round_trips_through_version_for_date():
    for m in _REAL:
        assert version_for_date(m.start) == m.version
        assert version_for_date(m.end) == m.version


def test_zero_range_milestones_own_no_dates():
    """v1.1 and v1.3 were superseded the day they shipped. They are kept because
    notes stamped with them at runtime exist, but no date resolves to them."""
    for m in VERSION_MILESTONES:
        if m.is_zero_range:
            assert version_for_date(m.start) != m.version
            assert version_for_date(m.end) != m.version


def test_dates_before_the_first_milestone_are_unknown():
    assert version_for_date(_REAL[0].start - timedelta(days=1)) == "unknown"


def test_today_resolves_to_the_current_pipeline_version():
    assert version_for_date(date.today()) == PIPELINE_VERSION


# ---------------------------------------------------------------------------
# The gates other modules read
# ---------------------------------------------------------------------------

def test_gate_constants_name_real_versions():
    assert MIN_FEEDBACK_VERSION in _ALL_VERSIONS
    assert LAST_DIRECTIONAL_VERSION in _ALL_VERSIONS


def test_directional_gate_closed_before_the_current_version():
    """The cut is only meaningful while the current version is past it. If a
    bump ever lands *on* LAST_DIRECTIONAL_VERSION, the scorer re-opens."""
    assert versions._version_tuple(LAST_DIRECTIONAL_VERSION) < versions._version_tuple(PIPELINE_VERSION)


@pytest.mark.parametrize("version", ["v0.1", "v1.0", "v1.5"])
def test_pre_cut_versions_still_score(version):
    assert has_directional_calls(version) is True


@pytest.mark.parametrize("version", ["v1.6", "v1.7", "v2.0", "v10.0"])
def test_post_cut_versions_are_skipped(version):
    assert has_directional_calls(version) is False


@pytest.mark.parametrize("version", [None, "", "garbage", "v", "vX.Y"])
def test_unknown_versions_read_as_directional(version):
    """Mis-skipping real history is the worse failure — an unparseable stamp
    sorts first and stays scoreable. See versions.has_directional_calls."""
    assert has_directional_calls(version) is True


# ---------------------------------------------------------------------------
# The derived docs table (Open decision #9)
# ---------------------------------------------------------------------------

def _doc_table() -> str:
    text = _DOC.read_text(encoding="utf-8")
    assert _BEGIN in text and _END in text, (
        f"{_DOC.relative_to(_REPO_ROOT)} is missing the generated-table markers"
    )
    return text.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()


def test_docs_table_matches_milestones():
    """The docs page holds a second copy of the milestone list. It is allowed to,
    on the sole condition that it is generated and this test proves it. Regenerate
    with: python .macro-assist/bump_version.py — or by hand from
    render_milestones_table() if you are only fixing wording in versions.py."""
    assert _doc_table() == render_milestones_table(VERSION_MILESTONES)


def test_docs_example_stamps_match_the_current_version():
    text = _DOC.read_text(encoding="utf-8")
    stamps = re.findall(r'agent_version"?:\s*"?(v[\d.]+)', text)
    assert stamps, "expected at least one example agent_version stamp on the page"
    assert set(stamps) == {PIPELINE_VERSION}, (
        f"example stamps {sorted(set(stamps))} do not all match PIPELINE_VERSION {PIPELINE_VERSION!r}"
    )
