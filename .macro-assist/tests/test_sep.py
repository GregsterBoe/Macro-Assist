"""
test_sep.py — WP-19.B SEP adapter + SPF-vs-SEP gap (Phase 19 monetary slice).

Pure, no I/O: synthetic FRED-shaped Series exercise the dot-plot path parse, the
longer-run pick, and the directional short-rate gap (sign, aligned band, missing).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exogenous.sep import (
    GAP_ALIGNED_BAND,
    SEP_SERIES,
    latest_value,
    parse_sep_path,
    short_rate_gap,
)


class TestParseSepPath:

    def test_indexes_by_target_year(self):
        s = pd.Series(
            [3.6, 3.4, 3.1],
            index=pd.to_datetime(["2026-01-01", "2027-01-01", "2028-01-01"]),
        )
        assert parse_sep_path(s) == {2026: 3.6, 2027: 3.4, 2028: 3.1}

    def test_drops_nan(self):
        s = pd.Series([3.6, float("nan"), 3.1],
                      index=pd.to_datetime(["2026-01-01", "2027-01-01", "2028-01-01"]))
        assert parse_sep_path(s) == {2026: 3.6, 2028: 3.1}

    def test_multiple_per_year_takes_last(self):
        # meeting-dated encoding: two 2026 obs → latest wins
        s = pd.Series([3.8, 3.6],
                      index=pd.to_datetime(["2026-03-18", "2026-06-17"]))
        assert parse_sep_path(s) == {2026: 3.6}

    def test_latest_value(self):
        s = pd.Series([3.0, float("nan"), 2.9],
                      index=pd.to_datetime(["2024-06-01", "2025-06-01", "2026-06-01"]))
        assert latest_value(s) == 2.9
        assert latest_value(pd.Series([], dtype=float)) is None


class TestShortRateGap:

    _PATH = {2026: 3.60, 2027: 3.40}

    def test_positive_gap_economists_above(self):
        g = short_rate_gap(3.90, self._PATH, 2026)   # SPF 3.90 vs SEP 3.60
        assert g["gap"] == pytest.approx(0.30)
        assert g["read"] == "economists above Fed dots"

    def test_negative_gap_economists_below(self):
        g = short_rate_gap(3.30, self._PATH, 2026)
        assert g["gap"] == pytest.approx(-0.30)
        assert g["read"] == "economists below Fed dots"

    def test_aligned_within_band(self):
        g = short_rate_gap(3.60 + GAP_ALIGNED_BAND / 2, self._PATH, 2026)
        assert g["read"] == "aligned"

    def test_none_when_year_absent(self):
        assert short_rate_gap(3.9, self._PATH, 2099) is None

    def test_none_when_spf_missing(self):
        assert short_rate_gap(None, self._PATH, 2026) is None


def test_series_ids():
    assert SEP_SERIES["fed_funds_median"] == "FEDTARMD"
    assert SEP_SERIES["fed_funds_median_longrun"] == "FEDTARMDLR"
