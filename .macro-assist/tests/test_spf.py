"""
test_spf.py — WP-19.B SPF adapter (Phase 19 monetary slice).

Pure, no I/O: synthetic SPF-shaped frames exercise release-date mapping, horizon
parsing, point-in-time selection (no look-ahead), and the consensus snapshot.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exogenous.spf import (
    RATE_HORIZONS,
    SPF_VARIABLES,
    _resolve_horizon,
    latest_before,
    load_spf_file,
    parse_spf,
    snapshot_from_series,
    survey_release_date,
)

# Real median-level workbooks committed as fixtures (confirm the live layout).
_EXAMPLE = Path(__file__).resolve().parent.parent / "exogenous" / "example"
_REAL_TBOND = _EXAMPLE / "Median_TBOND_Level.xlsx"
_REAL_FIXTURES = {
    "TBOND": _EXAMPLE / "Median_TBOND_Level.xlsx",
    "TBILL": _EXAMPLE / "Median_TBILL_Level.xlsx",
    "UNEMP": _EXAMPLE / "Median_UNEMP_Level.xlsx",
}


def _spf_frame() -> pd.DataFrame:
    # Two survey quarters, a TBOND (10Y) variable with 3 horizon columns, plus a
    # NaN forecast and an unparseable row that must be dropped.
    return pd.DataFrame({
        "YEAR":    [2025, 2025, 2026, "n/a"],
        "QUARTER": [1,    2,    1,    2],
        "TBOND1":  [4.10, 4.20, 4.35, 9.9],
        "TBOND2":  [4.15, 4.25, float("nan"), 9.9],
        "TBOND3":  [4.20, 4.30, 4.45, 9.9],
    })


class TestReleaseDate:

    def test_quarter_to_release_month(self):
        assert survey_release_date(2026, 1) == date(2026, 2, 15)
        assert survey_release_date(2026, 2) == date(2026, 5, 15)
        assert survey_release_date(2026, 3) == date(2026, 8, 15)
        assert survey_release_date(2026, 4) == date(2026, 11, 15)

    def test_bad_quarter_raises(self):
        with pytest.raises(ValueError):
            survey_release_date(2026, 5)


class TestParse:

    def test_indexes_by_release_date_and_horizon(self):
        s = parse_spf(_spf_frame(), "TBOND", horizon=1)
        assert list(s.index) == [
            pd.Timestamp(2025, 2, 15), pd.Timestamp(2025, 5, 15), pd.Timestamp(2026, 2, 15)
        ]
        assert s.loc[pd.Timestamp(2025, 2, 15)] == 4.10
        assert s.name == "TBOND_h1"

    def test_horizon_selects_correct_column(self):
        s3 = parse_spf(_spf_frame(), "TBOND", horizon=3)
        assert s3.loc[pd.Timestamp(2026, 2, 15)] == 4.45

    def test_drops_nan_and_unparseable_rows(self):
        # horizon 2 has a NaN for 2026-Q1 → that survey drops; the "n/a" year row
        # drops from every horizon.
        s2 = parse_spf(_spf_frame(), "TBOND", horizon=2)
        assert pd.Timestamp(2026, 2, 15) not in s2.index
        assert len(s2) == 2

    def test_case_insensitive_columns(self):
        df = _spf_frame().rename(columns={"YEAR": "Year", "QUARTER": "quarter",
                                          "TBOND1": "tbond1"})
        s = parse_spf(df, "tbond", horizon=1)
        assert len(s) == 3

    def test_missing_year_quarter_raises(self):
        with pytest.raises(ValueError):
            parse_spf(pd.DataFrame({"TBOND1": [4.1]}), "TBOND")

    def test_unknown_variable_raises(self):
        with pytest.raises(ValueError):
            parse_spf(_spf_frame(), "NOPE")

    def test_horizon_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_spf(_spf_frame(), "TBOND", horizon=9)


class TestPointInTime:

    def test_latest_before_no_lookahead(self):
        s = parse_spf(_spf_frame(), "TBOND", horizon=1)
        # Between the Q1 and Q2 2025 surveys → only Q1 is available.
        got = latest_before(s, date(2025, 4, 1))
        assert got == (date(2025, 2, 15), 4.10)

    def test_latest_before_uses_most_recent(self):
        s = parse_spf(_spf_frame(), "TBOND", horizon=1)
        got = latest_before(s, date(2026, 3, 1))
        assert got == (date(2026, 2, 15), 4.35)

    def test_latest_before_none_when_too_early(self):
        s = parse_spf(_spf_frame(), "TBOND", horizon=1)
        assert latest_before(s, date(2020, 1, 1)) is None


class TestSnapshot:

    def test_snapshot_across_variables_point_in_time(self):
        tbond = parse_spf(_spf_frame(), "TBOND", horizon=1)
        # A second variable that only starts in 2026 → absent for a 2025 as-of.
        tbill = pd.Series({pd.Timestamp(2026, 2, 15): 3.90}, name="TBILL_h1")
        snap = snapshot_from_series({"treasury_10y": tbond, "treasury_3m": tbill},
                                    date(2025, 6, 1))
        assert snap["treasury_10y"] == {"as_of_survey": "2025-05-15", "value": 4.20}
        assert "treasury_3m" not in snap    # not released by 2025-06-01

    def test_snapshot_includes_both_when_available(self):
        tbond = parse_spf(_spf_frame(), "TBOND", horizon=1)
        tbill = pd.Series({pd.Timestamp(2026, 2, 15): 3.90}, name="TBILL_h1")
        snap = snapshot_from_series({"treasury_10y": tbond, "treasury_3m": tbill},
                                    date(2026, 3, 1))
        assert set(snap) == {"treasury_10y", "treasury_3m"}


def test_variable_map_covers_slice_targets():
    assert {"treasury_10y", "treasury_3m", "unemployment", "cpi"} <= set(SPF_VARIABLES)


class TestRateHorizons:
    """Layout confirmed against Median_TBOND_Level.xlsx: TBOND1..6 (quarterly) +
    TBONDA..D (annual, must be ignored); 1=T-1, 2=T current, 3..6=T+1..T+4."""

    def _full_rate_frame(self) -> pd.DataFrame:
        return pd.DataFrame({
            "YEAR": [2026], "QUARTER": [2],
            "TBOND1": [4.20], "TBOND2": [4.31], "TBOND3": [4.30],
            "TBOND4": [4.30], "TBOND5": [4.25], "TBOND6": [4.20],
            "TBONDA": [4.27], "TBONDB": [4.21], "TBONDC": [4.15], "TBONDD": [4.10],
        })

    def test_annual_letter_columns_ignored(self):
        # only the 6 numeric-suffixed columns are horizons
        s6 = parse_spf(self._full_rate_frame(), "TBOND", horizon=6)
        assert s6.iloc[0] == 4.20
        with pytest.raises(ValueError):     # there is no 7th quarterly horizon
            parse_spf(self._full_rate_frame(), "TBOND", horizon=7)

    def test_named_horizons_select_expected_quarter(self):
        f = self._full_rate_frame()
        assert parse_spf(f, "TBOND", "prev_q").iloc[0] == 4.20     # col 1 = T-1
        assert parse_spf(f, "TBOND", "current_q").iloc[0] == 4.31  # col 2 = T
        assert parse_spf(f, "TBOND", "q1_ahead").iloc[0] == 4.30   # col 3 = T+1

    def test_default_is_current_quarter(self):
        assert parse_spf(self._full_rate_frame(), "TBOND").iloc[0] == 4.31

    def test_resolve_horizon(self):
        assert _resolve_horizon("current_q") == 2
        assert _resolve_horizon(3) == 3
        with pytest.raises(ValueError):
            _resolve_horizon("bogus")

    def test_rate_horizons_map(self):
        assert RATE_HORIZONS["current_q"] == 2 and RATE_HORIZONS["q4_ahead"] == 6


@pytest.mark.skipif(not _REAL_TBOND.exists(), reason="real SPF fixtures not present")
class TestRealFile:
    """Confirms the adapter reads the actual published workbooks (metadata quirk,
    sheet, columns, point-in-time) — not just synthetic frames. Covers the three
    confirmed variables (TBOND/TBILL/UNEMP), all the same 6-quarterly layout."""

    @pytest.mark.parametrize("var", list(_REAL_FIXTURES))
    def test_reads_and_is_point_in_time(self, var):
        s = load_spf_file(_REAL_FIXTURES[var], var)      # current-quarter consensus
        assert len(s) > 100
        assert s.index.is_monotonic_increasing
        # As-of before the 2026-Q2 survey (released mid-May) we must not see it.
        got = latest_before(s, date(2026, 3, 1))
        assert got is not None and got[0] < date(2026, 5, 1)
