"""
Tests for conditional.py (Phases 11.1 / 11.2 / 11.3).

All tests are pure unit tests — no external API or network calls.

Run:
    pytest .macro-assist/tests/test_conditional.py -v
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from conditional import (
    assign_bucket,
    build_bucket_index,
    build_distribution_table,
    build_distribution_table_for_backtest,
    load_distribution_table,
    lookup_distribution,
    _bucket_drop_hy,
    _bucket_drop_yc,
    _NFCI_LOW_MID,
    _NFCI_MID_HIGH,
    _HY_LOW_MID,
    _HY_MID_HIGH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(nfci: float | None, yield_10y: float | None, yield_2y: float | None,
                   hy: float | None) -> dict:
    snap: dict = {}
    if nfci is not None:
        snap["nfci"] = {"value": nfci}
    if yield_10y is not None and yield_2y is not None:
        snap["treasury_10y"] = {"value": yield_10y}
        snap["treasury_2y"]  = {"value": yield_2y}
        snap["yield_curve_spread"] = yield_10y - yield_2y
    if hy is not None:
        snap["hy_spread"] = {"value": hy}
    return snap


def _make_forward_returns(
    dates: list[date],
    assets: list[str],
    horizons: list[int] = [5, 10, 20],
    base_return: float = 0.5,
) -> dict[str, dict[date, dict[int, float]]]:
    """
    Create synthetic forward returns: every asset/date/horizon gets base_return.
    Useful for testing structure; override individual entries for signal tests.
    """
    fr: dict = {}
    for asset in assets:
        fr[asset] = {d: {h: base_return for h in horizons} for d in dates}
    return fr


def _make_snapshots_in_bucket(
    n: int,
    nfci_val: float,
    yield_10y: float,
    yield_2y: float,
    hy_val: float,
    start: date = date(2020, 1, 2),
) -> list[tuple[date, dict]]:
    """Generate n snapshots all mapping to the same bucket."""
    snap = _make_snapshot(nfci_val, yield_10y, yield_2y, hy_val)
    return [(start + timedelta(days=i), snap) for i in range(n)]


# ---------------------------------------------------------------------------
# Phase 11.1 — assign_bucket
# ---------------------------------------------------------------------------

class TestAssignBucket:

    def test_format(self):
        snap = _make_snapshot(-0.6, 4.0, 2.0, 3.0)
        label = assign_bucket(snap)
        parts = label.split("|")
        assert len(parts) == 3
        assert parts[0].startswith("NFCI:")
        assert parts[1].startswith("YC:")
        assert parts[2].startswith("HY:")

    def test_nfci_low(self):
        snap = _make_snapshot(_NFCI_LOW_MID - 0.1, 4.0, 2.0, 3.0)
        assert assign_bucket(snap).startswith("NFCI:low|")

    def test_nfci_mid(self):
        mid = (_NFCI_LOW_MID + _NFCI_MID_HIGH) / 2
        snap = _make_snapshot(mid, 4.0, 2.0, 3.0)
        assert assign_bucket(snap).startswith("NFCI:mid|")

    def test_nfci_high(self):
        snap = _make_snapshot(_NFCI_MID_HIGH + 0.1, 4.0, 2.0, 3.0)
        assert assign_bucket(snap).startswith("NFCI:high|")

    def test_nfci_boundary_low_mid(self):
        # Exactly at boundary → mid (not low)
        snap = _make_snapshot(_NFCI_LOW_MID, 4.0, 2.0, 3.0)
        assert assign_bucket(snap).startswith("NFCI:mid|")

    def test_yield_curve_positive(self):
        snap = _make_snapshot(-0.5, 4.5, 2.0, 3.0)  # 10Y > 2Y
        assert "|YC:positive|" in assign_bucket(snap)

    def test_yield_curve_inverted(self):
        snap = _make_snapshot(-0.5, 2.0, 4.5, 3.0)  # 10Y < 2Y
        assert "|YC:inverted|" in assign_bucket(snap)

    def test_yield_curve_from_spread_field(self):
        snap = {"yield_curve_spread": -0.5, "nfci": {"value": -0.5},
                "hy_spread": {"value": 3.0}}
        assert "|YC:inverted|" in assign_bucket(snap)

    def test_hy_tight(self):
        snap = _make_snapshot(-0.5, 4.0, 2.0, _HY_LOW_MID - 0.1)
        assert assign_bucket(snap).endswith("|HY:tight")

    def test_hy_mid(self):
        mid = (_HY_LOW_MID + _HY_MID_HIGH) / 2
        snap = _make_snapshot(-0.5, 4.0, 2.0, mid)
        assert assign_bucket(snap).endswith("|HY:mid")

    def test_hy_wide(self):
        snap = _make_snapshot(-0.5, 4.0, 2.0, _HY_MID_HIGH + 0.1)
        assert assign_bucket(snap).endswith("|HY:wide")

    def test_full_benign_bucket(self):
        # low NFCI (loose), positive curve, tight spreads → benign
        snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        assert assign_bucket(snap) == "NFCI:low|YC:positive|HY:tight"

    def test_full_stress_bucket(self):
        # high NFCI (tight), inverted curve, wide spreads → stress
        snap = _make_snapshot(0.5, 2.0, 4.5, 6.0)
        assert assign_bucket(snap) == "NFCI:high|YC:inverted|HY:wide"

    def test_missing_nfci_defaults_to_mid(self):
        snap = _make_snapshot(None, 4.0, 2.0, 3.0)
        assert assign_bucket(snap).startswith("NFCI:mid|")

    def test_missing_yield_curve_defaults_to_positive(self):
        snap = {"nfci": {"value": -0.5}, "hy_spread": {"value": 3.0}}
        assert "|YC:positive|" in assign_bucket(snap)

    def test_missing_hy_defaults_to_mid(self):
        snap = _make_snapshot(-0.5, 4.0, 2.0, None)
        assert assign_bucket(snap).endswith("|HY:mid")

    def test_empty_snapshot_returns_default(self):
        # All defaults: mid, positive, mid
        label = assign_bucket({})
        assert label == "NFCI:mid|YC:positive|HY:mid"

    def test_18_distinct_buckets_exist(self):
        # Every combination of (3 × 2 × 3) should be reachable
        nfci_vals = [_NFCI_LOW_MID - 0.1, (_NFCI_LOW_MID + _NFCI_MID_HIGH) / 2, _NFCI_MID_HIGH + 0.1]
        yc_vals   = [(4.0, 2.0), (2.0, 4.0)]
        hy_vals   = [_HY_LOW_MID - 0.1, (_HY_LOW_MID + _HY_MID_HIGH) / 2, _HY_MID_HIGH + 0.1]
        seen: set[str] = set()
        for n in nfci_vals:
            for y10, y2 in yc_vals:
                for h in hy_vals:
                    seen.add(assign_bucket(_make_snapshot(n, y10, y2, h)))
        assert len(seen) == 18


# ---------------------------------------------------------------------------
# Phase 11.1 — build_bucket_index
# ---------------------------------------------------------------------------

class TestBuildBucketIndex:

    def test_inverted_index_keys(self):
        snaps = [
            (date(2024, 1, 2), _make_snapshot(-0.6, 4.5, 2.0, 3.0)),  # benign
            (date(2024, 1, 3), _make_snapshot(0.5,  2.0, 4.5, 6.0)),  # stress
            (date(2024, 1, 4), _make_snapshot(-0.6, 4.5, 2.0, 3.0)),  # benign again
        ]
        idx = build_bucket_index(snaps)
        assert "NFCI:low|YC:positive|HY:tight" in idx
        assert "NFCI:high|YC:inverted|HY:wide" in idx
        assert len(idx["NFCI:low|YC:positive|HY:tight"]) == 2
        assert len(idx["NFCI:high|YC:inverted|HY:wide"]) == 1

    def test_dates_are_sorted(self):
        snaps = [
            (date(2024, 1, 5), _make_snapshot(-0.6, 4.5, 2.0, 3.0)),
            (date(2024, 1, 2), _make_snapshot(-0.6, 4.5, 2.0, 3.0)),
        ]
        idx = build_bucket_index(snaps)
        dates = idx["NFCI:low|YC:positive|HY:tight"]
        assert dates == sorted(dates)

    def test_empty_input(self):
        assert build_bucket_index([]) == {}

    def test_single_snapshot(self):
        snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        idx = build_bucket_index([(date(2024, 1, 2), snap)])
        assert len(idx) == 1
        bucket = list(idx.keys())[0]
        assert len(idx[bucket]) == 1


# ---------------------------------------------------------------------------
# Helpers — bucket parent collapse helpers
# ---------------------------------------------------------------------------

class TestBucketHelpers:

    def test_drop_hy(self):
        assert _bucket_drop_hy("NFCI:low|YC:positive|HY:tight") == "NFCI:low|YC:positive"

    def test_drop_hy_no_hy_dim(self):
        assert _bucket_drop_hy("NFCI:low|YC:positive") is None

    def test_drop_yc(self):
        assert _bucket_drop_yc("NFCI:low|YC:positive") == "NFCI:low"

    def test_drop_yc_no_yc_dim(self):
        assert _bucket_drop_yc("NFCI:low") is None


# ---------------------------------------------------------------------------
# Phase 11.2 — build_distribution_table
# ---------------------------------------------------------------------------

class TestBuildDistributionTable:

    def _benign_snapshots(self, n: int = 25) -> list[tuple[date, dict]]:
        snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        return [(date(2020, 1, 2) + timedelta(days=i), snap) for i in range(n)]

    def _stress_snapshots(self, n: int = 25) -> list[tuple[date, dict]]:
        snap = _make_snapshot(0.5, 2.0, 4.5, 6.0)
        start = date(2020, 1, 2) + timedelta(days=100)
        return [(start + timedelta(days=i), snap) for i in range(n)]

    def _all_snapshots(self, n: int = 25):
        return self._benign_snapshots(n) + self._stress_snapshots(n)

    def _forward_returns(
        self,
        snapshots: list[tuple[date, dict]],
        value: float = 1.0,
    ) -> dict[str, dict[date, dict[int, float]]]:
        dates = [d for d, _ in snapshots]
        return _make_forward_returns(dates, ["S&P 500", "Gold"], base_return=value)

    def test_table_schema(self):
        snaps = self._all_snapshots(15)
        fr = self._forward_returns(snaps)
        table = build_distribution_table(snaps, fr, min_n=10)
        assert isinstance(table, dict)
        for bucket, asset_dict in table.items():
            assert isinstance(bucket, str)
            for asset, horizon_dict in asset_dict.items():
                for horizon, stats in horizon_dict.items():
                    assert isinstance(horizon, int)
                    assert set(stats.keys()) >= {"p10", "p25", "p50", "p75", "p90", "n"}

    def test_percentile_ordering(self):
        snaps = self._all_snapshots(20)
        fr = self._forward_returns(snaps)
        table = build_distribution_table(snaps, fr, min_n=10)
        for bucket in table.values():
            for asset in bucket.values():
                for stats in asset.values():
                    assert stats["p10"] <= stats["p25"] <= stats["p50"] <= stats["p75"] <= stats["p90"]

    def test_full_and_parent_buckets_present(self):
        snaps = self._all_snapshots(15)
        fr = self._forward_returns(snaps)
        table = build_distribution_table(snaps, fr, min_n=5)
        # At least some full buckets and at least one parent bucket
        full_buckets    = [k for k in table if k.count("|") == 2]
        parent_buckets  = [k for k in table if k.count("|") == 1]
        assert len(full_buckets) >= 1
        assert len(parent_buckets) >= 1

    def test_min_n_respected(self):
        snaps = self._benign_snapshots(5)  # only 5 dates
        fr = self._forward_returns(snaps)
        table = build_distribution_table(snaps, fr, min_n=10)
        # Full bucket should not appear (n=5 < 10), but parent might not either
        benign_full = "NFCI:low|YC:positive|HY:tight"
        if benign_full in table:
            for asset in table[benign_full].values():
                for stats in asset.values():
                    assert stats["n"] >= 10

    def test_empty_snapshots(self):
        table = build_distribution_table([], {}, min_n=10)
        assert table == {}

    def test_json_persistence_roundtrip(self):
        snaps = self._all_snapshots(15)
        fr = self._forward_returns(snaps)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_table.json"
            table = build_distribution_table(snaps, fr, min_n=5, persist_path=path)
            assert path.exists()
            loaded = load_distribution_table(path)

        # Horizon keys must be restored as integers
        for bucket in loaded.values():
            for asset in bucket.values():
                for horizon in asset.keys():
                    assert isinstance(horizon, int), f"Expected int, got {type(horizon)}: {horizon}"

        # Values should match original (within float precision)
        for bucket, asset_dict in table.items():
            assert bucket in loaded
            for asset, horizon_dict in asset_dict.items():
                assert asset in loaded[bucket]
                for horizon, stats in horizon_dict.items():
                    loaded_stats = loaded[bucket][asset][horizon]
                    assert abs(loaded_stats["p50"] - stats["p50"]) < 1e-9


# ---------------------------------------------------------------------------
# Phase 11.2 — distinct distributions (signal quality test)
# ---------------------------------------------------------------------------

class TestDistinctDistributions:

    def test_benign_vs_stress_median_differs(self):
        """
        Median 5d SP500 return in 'NFCI:low|YC:positive|HY:tight' should be
        higher than in 'NFCI:high|YC:inverted|HY:wide' (by construction here).
        """
        rng = np.random.default_rng(42)
        n = 40

        benign_dates = [date(2010, 1, 4) + timedelta(days=i) for i in range(n)]
        stress_dates = [date(2012, 1, 2) + timedelta(days=i) for i in range(n)]

        benign_snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        stress_snap = _make_snapshot(0.5, 2.0, 4.5, 6.0)

        snaps = [(d, benign_snap) for d in benign_dates] + [(d, stress_snap) for d in stress_dates]

        # Assign different return profiles: benign = positive drift, stress = negative drift
        fr: dict[str, dict[date, dict[int, float]]] = {"S&P 500": {}}
        for d in benign_dates:
            fr["S&P 500"][d] = {5: float(rng.normal(1.0, 0.5)), 10: float(rng.normal(2.0, 1.0)), 20: float(rng.normal(4.0, 2.0))}
        for d in stress_dates:
            fr["S&P 500"][d] = {5: float(rng.normal(-1.0, 0.5)), 10: float(rng.normal(-2.0, 1.0)), 20: float(rng.normal(-4.0, 2.0))}

        table = build_distribution_table(snaps, fr, min_n=10)

        benign_bucket = "NFCI:low|YC:positive|HY:tight"
        stress_bucket = "NFCI:high|YC:inverted|HY:wide"

        assert benign_bucket in table, "Benign bucket not in table"
        assert stress_bucket in table, "Stress bucket not in table"

        benign_med = table[benign_bucket]["S&P 500"][5]["p50"]
        stress_med = table[stress_bucket]["S&P 500"][5]["p50"]

        # Benign median should be at least 0.5pp higher than stress median
        assert benign_med - stress_med >= 0.5, (
            f"Expected benign median > stress median by ≥0.5pp; "
            f"got benign={benign_med:.3f}, stress={stress_med:.3f}"
        )


# ---------------------------------------------------------------------------
# Phase 11.2 — lookup_distribution
# ---------------------------------------------------------------------------

class TestLookupDistribution:

    def _build_simple_table(self) -> dict:
        """Build a table with one benign full bucket and a parent."""
        n = 20
        benign_dates = [date(2020, 1, 2) + timedelta(days=i) for i in range(n)]
        benign_snap  = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        snaps = [(d, benign_snap) for d in benign_dates]
        fr    = _make_forward_returns(benign_dates, ["S&P 500"])
        return build_distribution_table(snaps, fr, min_n=10)

    def test_exact_match(self):
        table = self._build_simple_table()
        result = lookup_distribution("NFCI:low|YC:positive|HY:tight", "S&P 500", 5, table)
        assert result is not None
        assert "p50" in result
        assert result["n"] >= 10

    def test_parent_fallback(self):
        table = self._build_simple_table()
        # A bucket that doesn't exist directly but has a parent that does
        non_existent_full = "NFCI:low|YC:positive|HY:wide"
        result = lookup_distribution(non_existent_full, "S&P 500", 5, table)
        # Should fall back to "NFCI:low|YC:positive" parent
        assert result is not None

    def test_none_when_no_data(self):
        table: dict = {}
        result = lookup_distribution("NFCI:low|YC:positive|HY:tight", "S&P 500", 5, table)
        assert result is None

    def test_none_for_missing_asset(self):
        table = self._build_simple_table()
        result = lookup_distribution("NFCI:low|YC:positive|HY:tight", "WTI Oil", 5, table)
        assert result is None

    def test_none_for_missing_horizon(self):
        table = self._build_simple_table()
        result = lookup_distribution("NFCI:low|YC:positive|HY:tight", "S&P 500", 999, table)
        assert result is None

    def test_global_fallback(self):
        """When full + parent + grandparent all miss, fall back to 'all' bucket."""
        n = 20
        dates = [date(2020, 1, 2) + timedelta(days=i) for i in range(n)]
        snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        snaps = [(d, snap) for d in dates]
        fr = _make_forward_returns(dates, ["S&P 500"])
        # Build with low min_n to ensure 'all' bucket gets included
        table = build_distribution_table(snaps, fr, min_n=5)

        # Query a bucket whose NFCI part ("high") differs from what was put in ("low")
        # so full + parent + grandparent won't match, but 'all' will
        result = lookup_distribution("NFCI:high|YC:inverted|HY:wide", "S&P 500", 5, table)
        # 'all' bucket should have the data
        assert result is not None


# ---------------------------------------------------------------------------
# Phase 11.2 — full coverage test
# ---------------------------------------------------------------------------

class TestFullCoverage:

    def test_every_date_maps_to_bucket_with_n_gte_10(self):
        """
        Using synthetic data with n=30 per bucket, every date should map
        to a bucket with n ≥ 10 after parent fallback.
        """
        rng = np.random.default_rng(99)
        n_per_bucket = 30
        assets = ["S&P 500"]
        all_snaps: list[tuple[date, dict]] = []
        all_fr: dict[str, dict[date, dict[int, float]]] = {"S&P 500": {}}

        start = date(2020, 1, 2)
        idx = 0
        for nfci_v in [-0.6, -0.25, 0.2]:
            for yc10, yc2 in [(4.5, 2.0), (2.0, 4.5)]:
                for hy_v in [3.0, 4.3, 6.0]:
                    snap = _make_snapshot(nfci_v, yc10, yc2, hy_v)
                    for _ in range(n_per_bucket):
                        d = start + timedelta(days=idx)
                        all_snaps.append((d, snap))
                        all_fr["S&P 500"][d] = {5: float(rng.normal(0, 1)), 10: float(rng.normal(0, 2)), 20: float(rng.normal(0, 3))}
                        idx += 1

        table = build_distribution_table(all_snaps, all_fr, min_n=10)

        # Every snapshot date should be resolvable to n≥10
        for snap_date, snapshot in all_snaps:
            bucket = assign_bucket(snapshot)
            dist = lookup_distribution(bucket, "S&P 500", 5, table)
            assert dist is not None, f"No distribution found for bucket {bucket} on {snap_date}"
            assert dist["n"] >= 10, f"n={dist['n']} < 10 for bucket {bucket}"


# ---------------------------------------------------------------------------
# Phase 11.3 — build_distribution_table_for_backtest
# ---------------------------------------------------------------------------

class TestBuildDistributionTableForBacktest:

    def _make_data(
        self,
        n: int = 60,
        base_return: float = 0.5,
    ) -> tuple[list[tuple[date, dict]], dict]:
        snap = _make_snapshot(-0.6, 4.5, 2.0, 3.0)
        snaps = [(date(2020, 1, 2) + timedelta(days=i), snap) for i in range(n)]
        fr    = _make_forward_returns([d for d, _ in snaps], ["S&P 500"], base_return=base_return)
        return snaps, fr

    def test_subset_monotone(self):
        """
        For D1 < D2, bucket n at D1 <= bucket n at D2 (table grows monotonically).
        """
        snaps, fr = self._make_data(n=60)

        d1 = date(2020, 3, 1)
        d2 = date(2020, 5, 1)
        assert d1 < d2

        table_d1 = build_distribution_table_for_backtest(snaps, fr, d1, max_horizon=20, min_n=5)
        table_d2 = build_distribution_table_for_backtest(snaps, fr, d2, max_horizon=20, min_n=5)

        # Every bucket in d1 table must be in d2 table with n >= that in d1
        for bucket, asset_dict in table_d1.items():
            assert bucket in table_d2, f"Bucket {bucket} in D1 table but not D2 table"
            for asset, horizon_dict in asset_dict.items():
                for horizon, stats_d1 in horizon_dict.items():
                    if asset in table_d2[bucket] and horizon in table_d2[bucket][asset]:
                        assert table_d2[bucket][asset][horizon]["n"] >= stats_d1["n"], (
                            f"n decreased from D1={stats_d1['n']} to D2={table_d2[bucket][asset][horizon]['n']}"
                        )

    def test_no_future_leak(self):
        """
        No observation used at as_of_date D should have snapshot_date + max_horizon > D.
        Verified by checking that as_of=early_date produces an empty or small table.
        """
        snaps, fr = self._make_data(n=60)
        # as_of_date of day 0 + 20 days = day 20; so only days 0..0 should be included
        as_of = date(2020, 1, 2) + timedelta(days=20)
        table = build_distribution_table_for_backtest(snaps, fr, as_of, max_horizon=20, min_n=1)

        # The latest snapshot date used must be <= as_of - 20 days = day 0
        latest_allowed = as_of - timedelta(days=20)

        # Cross-check: using min_n=1 to see all included observations
        # Build a reference of what dates were included by checking against
        # forward returns that appear in the table
        table_any = build_distribution_table_for_backtest(snaps, fr, as_of, max_horizon=20, min_n=1)

        for bucket, asset_dict in table_any.items():
            for asset, horizon_dict in asset_dict.items():
                for horizon, stats in horizon_dict.items():
                    # n should reflect only dates <= latest_allowed
                    max_possible_n = sum(
                        1 for d, _ in snaps
                        if d <= latest_allowed and d in fr.get(asset, {}) and horizon in fr[asset][d]
                    )
                    assert stats["n"] <= max_possible_n, (
                        f"n={stats['n']} exceeds max_possible={max_possible_n} "
                        f"for {bucket}/{asset}/{horizon}"
                    )

    def test_empty_before_horizon_window(self):
        """
        When as_of is so early no snapshots pass the filter, table is empty.
        """
        snaps, fr = self._make_data(n=10)
        # as_of = day 0 (data starts day 0); no snapshots can satisfy d <= day 0 - 20
        as_of = date(2020, 1, 2)
        table = build_distribution_table_for_backtest(snaps, fr, as_of, max_horizon=20, min_n=1)
        assert table == {}

    def test_all_snapshots_included_far_future(self):
        """
        When as_of is far in the future, all snapshots are included.
        """
        snaps, fr = self._make_data(n=30)
        as_of = date(2025, 1, 1)
        table_full = build_distribution_table(snaps, fr, min_n=5)
        table_pit  = build_distribution_table_for_backtest(snaps, fr, as_of, max_horizon=20, min_n=5)
        # Should produce identical tables
        assert set(table_full.keys()) == set(table_pit.keys())
