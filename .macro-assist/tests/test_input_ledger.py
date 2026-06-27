"""
test_input_ledger.py — WP-18.2 cheap input-quality proxies.

Pure, no I/O: synthetic series exercise the staleness / entropy / robust-sigma /
change-correlation-redundancy math and the ledger assembly + ranking.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from input_ledger import (
    DEAD_ENTROPY,
    DEFAULT_CORR_THRESHOLD,
    build_ledger,
    correlation_redundancy,
    info_score,
    is_stale,
    normalized_entropy,
    render_ledger_md,
    robust_sigma,
    staleness_days,
    token_estimate,
)


def _dates(n: int, freq: str = "B") -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq=freq)


class TestStaleness:

    def test_days_and_threshold(self):
        assert staleness_days(date(2026, 6, 20), date(2026, 6, 27)) == 7
        assert is_stale(7, "daily") is True       # daily limit 5
        assert is_stale(7, "weekly") is False      # weekly limit 12
        assert is_stale(50, "monthly") is True     # monthly limit 45
        assert is_stale(50, "quarterly") is False  # quarterly limit 100

    def test_unknown_frequency_uses_default(self):
        assert is_stale(46, "garbage") is True
        assert is_stale(44, "garbage") is False


class TestRobustSigma:

    def test_constant_series_is_zero(self):
        assert robust_sigma(pd.Series([3.0] * 20)) == 0.0

    def test_empty_is_zero(self):
        assert robust_sigma(pd.Series([], dtype=float)) == 0.0

    def test_outlier_robust(self):
        # One huge spike barely moves MAD-scaled sigma vs the clean run.
        clean = pd.Series(np.r_[np.zeros(50), np.ones(50)])
        spiked = clean.copy()
        spiked.iloc[0] = 1e6
        assert robust_sigma(spiked) == pytest.approx(robust_sigma(clean), abs=1e-9)


class TestEntropy:

    def test_constant_is_dead(self):
        assert normalized_entropy(pd.Series([1.0] * 100)) == 0.0

    def test_too_few_points_is_zero(self):
        assert normalized_entropy(pd.Series([1.0])) == 0.0

    def test_uniform_spread_is_high(self):
        vals = pd.Series(np.linspace(0, 1, 1000))
        assert normalized_entropy(vals, bins=10) > 0.95

    def test_bounded_unit_interval(self):
        vals = pd.Series(np.random.default_rng(0).normal(size=500))
        h = normalized_entropy(vals)
        assert 0.0 <= h <= 1.0

    def test_near_constant_below_dead_threshold(self):
        # 99% identical, a 1% jitter — should read as dead.
        vals = pd.Series([5.0] * 198 + [5.0001, 4.9999])
        assert normalized_entropy(vals) < DEAD_ENTROPY


class TestRedundancy:

    def test_perfectly_collinear_changes_flagged(self):
        idx = _dates(60)
        base = pd.Series(np.cumsum(np.random.default_rng(1).normal(size=60)), index=idx)
        panel = pd.DataFrame({"a": base, "b": base * 2.0 + 10})  # identical changes (scaled)
        out = correlation_redundancy(panel, threshold=DEFAULT_CORR_THRESHOLD)
        assert out["max_abs"]["a"]["partner"] == "b"
        assert out["max_abs"]["a"]["value"] == pytest.approx(1.0, abs=1e-6)
        assert out["pairs"] and out["pairs"][0][:2] == ("a", "b")

    def test_subdaily_series_not_assessed(self):
        # A monthly series ffilled to daily has a mostly-zero change vector, so
        # its change-correlations are artifacts → excluded from the assessment.
        idx = _dates(420)
        rng = np.random.default_rng(11)
        daily = np.cumsum(rng.normal(size=420))
        monthly = np.repeat(np.cumsum(rng.normal(size=20)), 21)[:420]  # steps ~monthly
        panel = pd.DataFrame({"daily": daily, "monthly": monthly}, index=idx)
        out = correlation_redundancy(panel, threshold=DEFAULT_CORR_THRESHOLD)
        assert out["assessed"] == ["daily"]
        assert out["max_abs"]["monthly"]["assessed"] is False
        assert out["max_abs"]["monthly"]["value"] is None
        # monthly never appears in a redundant pair
        assert all("monthly" not in (a, b) for a, b, _ in out["pairs"])

    def test_independent_series_not_flagged(self):
        idx = _dates(400)
        rng = np.random.default_rng(2)
        panel = pd.DataFrame({
            "a": np.cumsum(rng.normal(size=400)),
            "b": np.cumsum(rng.normal(size=400)),
        }, index=idx)
        out = correlation_redundancy(panel, threshold=DEFAULT_CORR_THRESHOLD)
        assert out["pairs"] == []
        assert abs(out["max_abs"]["a"]["value"]) < DEFAULT_CORR_THRESHOLD

    def test_correlates_changes_not_levels(self):
        # Two independent random walks share a strong *level* trend but uncorrelated
        # *changes* — correlating levels would falsely flag them; changes must not.
        idx = _dates(500)
        rng = np.random.default_rng(3)
        a = np.cumsum(rng.normal(0.1, 1, size=500))  # upward drift
        b = np.cumsum(rng.normal(0.1, 1, size=500))  # same drift, independent noise
        panel = pd.DataFrame({"a": a, "b": b}, index=idx)
        # level correlation is high (shared drift) …
        assert panel.corr().at["a", "b"] > 0.7
        # … but the redundancy check (on changes) is not fooled.
        out = correlation_redundancy(panel, threshold=DEFAULT_CORR_THRESHOLD)
        assert out["pairs"] == []


class TestInfoScore:

    def test_redundant_input_scores_low(self):
        # Same entropy, but one is fully redundant → strictly lower density.
        assert info_score(0.9, 0.95) < info_score(0.9, 0.1)

    def test_dead_input_scores_zero(self):
        assert info_score(0.0, 0.0) == 0.0


class TestTokenEstimate:

    def test_roughly_four_chars_per_token(self):
        assert token_estimate("x" * 400) == 100
        assert token_estimate("") == 0


class TestBuildLedger:

    def _panel(self):
        idx = _dates(400)
        rng = np.random.default_rng(7)
        walk = np.cumsum(rng.normal(size=400))
        return pd.DataFrame({
            "solo":   np.cumsum(rng.normal(size=400)),  # varied + independent → high score
            "live":   walk,                              # redundant with dupe
            "dupe":   walk * 1.5,                        # redundant with live
            "dead":   np.full(400, 2.0),                 # constant → entropy 0
        }, index=idx)

    def test_flags_and_ranking(self):
        panel = self._panel()
        groups = {"solo": "fred", "live": "fred", "dupe": "market", "dead": "fred"}
        freq = {c: "daily" for c in panel.columns}
        freq["dead"] = "monthly"
        # as_of at the last obs so nothing is "stale" by accident
        asof = panel.index[-1].date()
        ledger = build_ledger(panel, groups, freq, asof, corr_threshold=DEFAULT_CORR_THRESHOLD)

        by_name = {e["name"]: e for e in ledger["entries"]}
        assert "DEAD" in by_name["dead"]["flags"]
        assert by_name["dead"]["info_score"] == 0.0
        assert by_name["live"]["redundant"] and by_name["dupe"]["redundant"]
        assert "REDUNDANT" not in by_name["solo"]["flags"]
        assert ("live", "dupe", pytest.approx(1.0, abs=1e-6)) == (
            ledger["redundant_pairs"][0][0],
            ledger["redundant_pairs"][0][1],
            ledger["redundant_pairs"][0][2],
        )
        # The independent, varied series is least prunable → ranks last (top score).
        assert ledger["entries"][-1]["name"] == "solo"
        assert by_name["solo"]["info_score"] == max(e["info_score"] for e in ledger["entries"])

    def test_staleness_uses_last_obs_map_not_ffilled_panel(self):
        # The panel is ffilled to a recent business day, but the series' true last
        # print is old. Without the map staleness collapses to ~0 (the bug); with
        # it, staleness is real.
        panel = self._panel()
        groups = {c: "fred" for c in panel.columns}
        freq = {c: "monthly" for c in panel.columns}
        asof = panel.index[-1].date()
        true_old = (panel.index[-1] - pd.Timedelta(days=173)).date()

        without = build_ledger(panel, groups, freq, asof)
        with_map = build_ledger(panel, groups, freq, asof,
                                last_obs_map={"solo": true_old})

        get = lambda lg, n: next(e for e in lg["entries"] if e["name"] == n)
        assert get(without, "solo")["days_stale"] <= 1     # ffilled → looks fresh (the bug)
        assert get(with_map, "solo")["days_stale"] == 173   # real staleness
        assert get(with_map, "solo")["stale"] is True       # 173 > monthly limit

    def test_subdaily_input_ranked_by_entropy_alone(self):
        # A sub-daily input gets redund-n/a and info_score == its entropy (no
        # redundancy discount applied), and is flagged accordingly.
        idx = _dates(420)
        rng = np.random.default_rng(13)
        panel = pd.DataFrame({
            "daily":   np.cumsum(rng.normal(size=420)),
            "monthly": np.repeat(np.cumsum(rng.normal(size=20)), 21)[:420],
        }, index=idx)
        ledger = build_ledger(panel, {"daily": "market", "monthly": "fred"},
                              {"daily": "daily", "monthly": "monthly"},
                              idx[-1].date())
        m = next(e for e in ledger["entries"] if e["name"] == "monthly")
        assert m["redundancy_assessed"] is False
        assert m["max_abs_corr"] is None
        assert "redund-n/a" in m["flags"]
        assert m["info_score"] == pytest.approx(m["entropy"])

    def test_stale_flag_set_when_old(self):
        panel = self._panel()
        groups = {c: "fred" for c in panel.columns}
        freq = {c: "daily" for c in panel.columns}
        asof = date(2030, 1, 1)  # far future → everything stale
        ledger = build_ledger(panel, groups, freq, asof)
        assert all("STALE" in e["flags"] for e in ledger["entries"])

    def test_render_is_markdown(self):
        panel = self._panel()
        groups = {c: "fred" for c in panel.columns}
        freq = {c: "daily" for c in panel.columns}
        ledger = build_ledger(panel, groups, freq, panel.index[-1].date(),
                              section_costs={"FRED Macro": 3100, "Market": 900})
        text = "\n".join(render_ledger_md(ledger))
        assert "# Input Ledger" in text
        assert "information density" in text
        assert "Payload section token cost" in text
        assert "FRED Macro" in text
