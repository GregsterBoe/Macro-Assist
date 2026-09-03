"""
test_bias_separation.py — bias-separation unit tests.

Pure, no I/O: builds synthetic score files with a known relationship between the
stated bias and the realized move, and checks that the standardization, the
block-permutation test, the ordering classification and the markdown rendering
all report it correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bias_separation import (
    BIASES,
    MIN_BUCKET_N,
    PRIMARY_ARM,
    WINDOWS,
    arm_composition,
    arm_of,
    block_bootstrap_ci,
    date_overlap,
    filter_arm,
    _blocks,
    _buckets,
    _monotonic,
    _standardize,
    bias_separation,
    block_permutation,
    observations,
    separation_md_lines,
)


def _report(report_date: str, window: str, assets: dict[str, tuple[str, float]]) -> dict:
    """Score-file dict. assets: name -> (bias, pct_change)."""
    return {
        "report_date": report_date,
        "windows": {
            window: {
                "assets": {
                    name: {
                        "bias": bias,
                        "confidence": 60,
                        "pct_change": pct,
                        "score": 1.0,
                    }
                    for name, (bias, pct) in assets.items()
                }
            }
        },
    }


def _dates(n: int, start_day: int = 1) -> list[str]:
    """n distinct ISO dates, one per day, spanning several months."""
    out = []
    day = start_day
    month = 3
    for _ in range(n):
        out.append(f"2026-{month:02d}-{day:02d}")
        day += 1
        if day > 28:
            day = 1
            month += 1
    return out


def _series(biases_and_pcts: list[tuple[str, float]], window: str = "t5",
            asset: str = "S&P 500") -> list[dict]:
    """One report per date, each carrying a single asset call."""
    ds = _dates(len(biases_and_pcts))
    return [
        _report(d, window, {asset: (bias, pct)})
        for d, (bias, pct) in zip(ds, biases_and_pcts)
    ]


class TestObservations:

    def test_flattens_windows_and_assets(self):
        scores = [_report("2026-03-02", "t5", {"S&P 500": ("Bullish", 1.0),
                                               "Gold": ("Bearish", -2.0)})]
        obs = observations(scores)
        assert len(obs) == 2
        assert {o["asset"] for o in obs} == {"S&P 500", "Gold"}
        assert all(o["window"] == "t5" for o in obs)

    def test_drops_unresolved_calls(self):
        scores = [{
            "report_date": "2026-03-02",
            "windows": {"t5": {"assets": {
                "S&P 500": {"bias": "Bullish", "confidence": 60,
                            "pct_change": None, "score": None},
                "Gold":    {"bias": "Bullish", "confidence": 60,
                            "pct_change": 1.0, "score": 1.0},
            }}},
        }]
        obs = observations(scores)
        assert [o["asset"] for o in obs] == ["Gold"]

    def test_ignores_unknown_windows(self):
        scores = [_report("2026-03-02", "t99", {"S&P 500": ("Bullish", 1.0)})]
        assert observations(scores) == []


class TestStandardize:

    def test_z_is_centred_within_group(self):
        scores = _series([("Bullish", p) for p in (1.0, 2.0, 3.0, 4.0, 5.0)])
        obs = _standardize(observations(scores))
        assert len(obs) == 5
        assert abs(sum(o["z"] for o in obs)) < 1e-9   # mean-zero within the group

    def test_assets_are_standardized_separately(self):
        # Bitcoin swings 10x wider than DXY; equal z should mean equal *relative* move.
        scores = []
        for i, d in enumerate(_dates(6)):
            scores.append(_report(d, "t5", {
                "Bitcoin": ("Bullish", (i - 2.5) * 10.0),
                "DXY":     ("Bullish", (i - 2.5) * 1.0),
            }))
        obs = _standardize(observations(scores))
        btc = sorted(o["z"] for o in obs if o["asset"] == "Bitcoin")
        dxy = sorted(o["z"] for o in obs if o["asset"] == "DXY")
        assert all(abs(a - b) < 1e-9 for a, b in zip(btc, dxy))

    def test_drops_groups_with_no_dispersion(self):
        # A constant series has no scale to standardize by — dropped, not /0.
        scores = _series([("Bullish", 1.0)] * 5)
        assert _standardize(observations(scores)) == []

    def test_drops_groups_too_small_to_standardize(self):
        scores = _series([("Bullish", 1.0), ("Bearish", 2.0)])
        assert _standardize(observations(scores)) == []


class TestBuckets:

    def test_counts_and_means_per_bias(self):
        scores = _series(
            [("Bullish", 4.0)] * 3 + [("Neutral", 0.0)] * 3 + [("Bearish", -4.0)] * 3
        )
        b = _buckets(_standardize(observations(scores)))
        assert b["Bullish"]["n"] == b["Neutral"]["n"] == b["Bearish"]["n"] == 3
        assert b["Bullish"]["mean_pct"] == 4.0
        assert b["Bearish"]["mean_pct"] == -4.0
        assert b["Bullish"]["mean_z"] > b["Neutral"]["mean_z"] > b["Bearish"]["mean_z"]

    def test_empty_bucket_reports_none(self):
        scores = _series([("Bullish", float(i)) for i in range(5)])
        b = _buckets(_standardize(observations(scores)))
        assert b["Bearish"] == {"n": 0, "mean_z": None, "median_z": None, "mean_pct": None}


class TestMonotonic:

    def _b(self, bull: float, neut: float, bear: float) -> dict:
        return {b: {"mean_z": v} for b, v in
                zip(BIASES, (bull, neut, bear))}

    def test_aligned(self):
        assert _monotonic(self._b(0.5, 0.0, -0.5)) == "aligned"

    def test_inverted(self):
        assert _monotonic(self._b(-0.5, 0.0, 0.5)) == "inverted"

    def test_mixed(self):
        assert _monotonic(self._b(0.5, -0.3, 0.2)) == "mixed"

    def test_none_when_a_bucket_is_empty(self):
        assert _monotonic(self._b(0.5, 0.0, None)) is None


class TestBlocks:

    def test_groups_contiguous_report_dates(self):
        scores = _series([("Bullish", float(i)) for i in range(50)])
        obs = _standardize(observations(scores))
        blocks = _blocks(obs, block_days=21)
        assert len(blocks) == 3               # 21 + 21 + 8
        assert sum(len(b) for b in blocks) == len(obs)

    def test_block_membership_follows_date_order(self):
        scores = _series([("Bullish", float(i)) for i in range(10)])
        obs = _standardize(observations(scores))
        blocks = _blocks(obs, block_days=4)
        first = {o["date"] for o in blocks[0]}
        last  = {o["date"] for o in blocks[-1]}
        assert max(first) < min(last)


class TestBlockPermutation:

    def test_none_when_bucket_below_minimum(self):
        scores = _series(
            [("Bullish", float(i)) for i in range(MIN_BUCKET_N + 5)]
            + [("Neutral", 1.0)] * (MIN_BUCKET_N - 1)
        )
        obs = _standardize(observations(scores))
        assert block_permutation(obs, "Bullish", "Neutral") is None

    def test_detects_a_planted_separation(self):
        # Bullish always precedes a big up move, Neutral a big down move.
        pairs = []
        for i in range(60):
            pairs.append(("Bullish", 5.0 + i * 0.01) if i % 2 == 0
                         else ("Neutral", -5.0 - i * 0.01))
        obs = _standardize(observations(_series(pairs)))
        res = block_permutation(obs, "Bullish", "Neutral", n_perm=400, block_days=10)
        assert res is not None
        assert res["gap"] > 1.0          # large, positive separation
        assert res["p_value"] < 0.05
        assert res["n_a"] == res["n_b"] == 30

    def test_no_separation_when_labels_are_unrelated_to_returns(self):
        # Labels alternate on a return series that does not track them.
        pairs = []
        for i in range(60):
            bias = "Bullish" if i % 2 == 0 else "Neutral"
            pairs.append((bias, (i % 7) - 3.0))
        obs = _standardize(observations(_series(pairs)))
        res = block_permutation(obs, "Bullish", "Neutral", n_perm=400, block_days=10)
        assert res is not None
        assert abs(res["gap"]) < 0.5
        assert res["p_value"] > 0.10

    def test_reports_block_count(self):
        pairs = [("Bullish", float(i)) if i % 2 else ("Neutral", -float(i))
                 for i in range(60)]
        obs = _standardize(observations(_series(pairs)))
        res = block_permutation(obs, "Bullish", "Neutral", n_perm=100, block_days=21)
        assert res["n_blocks"] == 3

    def test_is_deterministic(self):
        pairs = [("Bullish", float(i)) if i % 3 else ("Neutral", -float(i))
                 for i in range(60)]
        obs = _standardize(observations(_series(pairs)))
        a = block_permutation(obs, "Bullish", "Neutral", n_perm=200, block_days=10)
        b = block_permutation(obs, "Bullish", "Neutral", n_perm=200, block_days=10)
        assert a == b


class TestBiasSeparation:

    def _planted(self, inverted: bool = False) -> list[dict]:
        """60 reports across 3 windows with a strong planted ordering."""
        sign = -1.0 if inverted else 1.0
        scores = []
        for i, d in enumerate(_dates(60)):
            bias = BIASES[i % 3]
            base = {"Bullish": 4.0, "Neutral": 0.0, "Bearish": -4.0}[bias]
            for w in WINDOWS:
                scores.append(_report(d, w, {
                    "S&P 500": (bias, sign * (base + (i % 5) * 0.1)),
                }))
        return scores

    def test_returns_none_without_data(self):
        assert bias_separation([]) is None

    def test_detects_aligned_ordering(self):
        sep = bias_separation(self._planted())
        assert sep["overall"]["ordering"] == "aligned"
        assert set(sep["windows"]) == set(WINDOWS)
        assert sep["overall"]["bullish_vs_neutral"]["gap"] > 0

    def test_detects_inverted_ordering(self):
        sep = bias_separation(self._planted(inverted=True))
        assert sep["overall"]["ordering"] == "inverted"
        assert sep["overall"]["bullish_vs_neutral"]["gap"] < 0

    def test_reports_per_asset_breakdown(self):
        sep = bias_separation(self._planted())
        entry = sep["by_asset"]["S&P 500"]
        assert entry["Bullish"]["mean_pct"] > entry["Bearish"]["mean_pct"]
        assert entry["Bullish"]["n"] > 0

    def test_params_are_recorded(self):
        sep = bias_separation(self._planted())
        assert sep["params"]["block_days"] > 0
        assert sep["params"]["n_perm"] > 0


class TestSeparationMarkdown:

    def test_empty_when_no_data(self):
        assert separation_md_lines(None) == []
        assert separation_md_lines({"overall": None}) == []

    def test_renders_table_and_verdict(self):
        sep = bias_separation(TestBiasSeparation()._planted())
        md = "\n".join(separation_md_lines(sep))
        assert "## Bias Separation" in md
        assert "Bull−Neut" in md
        assert "aligned separation" in md
        assert "S&P 500" in md

    def test_flags_an_inverted_ordering(self):
        sep = bias_separation(TestBiasSeparation()._planted(inverted=True))
        md = "\n".join(separation_md_lines(sep))
        assert "inverted" in md
        assert "⚠️" in md

    def test_rows_render_for_every_window(self):
        sep = bias_separation(TestBiasSeparation()._planted())
        md = separation_md_lines(sep)
        table = [l for l in md if l.startswith("| T+") or l.startswith("| **all**")]
        assert len(table) == len(WINDOWS) + 1



# ---------------------------------------------------------------------------
# Arm scoping (KB-023) — the three prediction arms write score files that share
# a report_date, so anything keyed on the date mixes them up.
# ---------------------------------------------------------------------------

def _armed(report: dict, arm: str | None = None, profile: str | None = None) -> dict:
    out = dict(report)
    if arm is not None:
        out["arm"] = arm
    if profile is not None:
        out["profile"] = profile
    return out


class TestArmScoping:

    def test_missing_arm_resolves_to_the_primary_arm(self):
        # Score files predating the arm machinery are production-pipeline files;
        # bucketing them as "unknown" would drop the whole early history.
        assert arm_of({"report_date": "2026-03-02"}) == PRIMARY_ARM
        assert arm_of({"arm": "kimi"}) == "kimi"

    def test_filter_arm_selects_one_system(self):
        scores = [
            _armed(_report("2026-03-02", "t5", {"Gold": ("Bullish", 1.0)}), arm="market"),
            _armed(_report("2026-03-02", "t5", {"Gold": ("Bearish", -1.0)}), arm="kimi"),
        ]
        assert len(filter_arm(scores, "market")) == 1
        assert len(filter_arm(scores, "kimi")) == 1
        assert len(filter_arm(scores, None)) == 2

    def test_same_date_arms_are_kept_apart(self):
        # The exact collision from KB-023: sibling arms share a report_date.
        scores = [
            _armed(_report("2026-03-02", "t5", {"Gold": ("Bullish", 1.0)}), arm="market"),
            _armed(_report("2026-03-02", "t5", {"Gold": ("Bearish", -1.0)}), arm="kimi"),
        ]
        obs = observations(scores)
        assert {o["arm"] for o in obs} == {"market", "kimi"}
        assert [o["bias"] for o in obs if o["arm"] == "market"] == ["Bullish"]
        assert [o["bias"] for o in obs if o["arm"] == "kimi"] == ["Bearish"]

    def test_analysis_is_scoped_and_records_provenance(self):
        planted = TestBiasSeparation()._planted()
        market = [_armed(r, arm="market") for r in planted]
        noise = [_armed(_report(r["report_date"], "t5", {"Gold": ("Bullish", -9.0)}),
                        arm="kimi") for r in planted]
        sep = bias_separation(market + noise, arm="market")
        prov = sep["provenance"]
        assert prov["arm"] == "market"
        assert prov["n_reports_used"] == len(market)
        assert prov["n_reports_total"] == len(market) + len(noise)
        assert set(arm_composition(market + noise)) == {"market", "kimi"}
        # The kimi rows must not reach the market arm's buckets.
        assert sep["overall"]["n"] == bias_separation(market, arm="market")["overall"]["n"]

    def test_provenance_table_names_every_arm(self):
        planted = TestBiasSeparation()._planted()
        scores = ([_armed(r, arm="market") for r in planted]
                  + [_armed(r, arm="kimi") for r in planted])
        md = "\n".join(separation_md_lines(bias_separation(scores, arm="market")))
        assert "`market`" in md and "`kimi`" in md


class TestConfoundGuardrail:

    def _split_block(self):
        """Baseline first, loosened after — no shared dates, as actually run."""
        planted = TestBiasSeparation()._planted()
        half = len(planted) // 2
        return ([_armed(r, arm="market", profile="baseline") for r in planted[:half]]
                + [_armed(r, arm="market", profile="loosened") for r in planted[half:]])

    def test_zero_overlap_is_detected(self):
        pairs = date_overlap(self._split_block(), "profile")
        assert pairs, "expected a profile pair"
        assert all(v["confounded"] for v in pairs.values())
        assert all(v["n_shared"] == 0 for v in pairs.values())

    def test_interleaved_profiles_are_not_flagged(self):
        # Day-alternating assignment (WP-21.B) is what makes the A/B readable.
        planted = TestBiasSeparation()._planted()
        scores = [_armed(r, arm="market",
                         profile="loosened" if i % 2 else "baseline")
                  for i, r in enumerate(planted)]
        overlapping = [_armed(r, arm="market", profile="loosened") for r in planted]
        pairs = date_overlap(scores + overlapping, "profile")
        assert any(not v["confounded"] for v in pairs.values())

    def test_report_warns_when_profiles_never_overlap(self):
        md = "\n".join(separation_md_lines(bias_separation(self._split_block())))
        assert "share zero report-dates" in md
        assert "⛔" in md


class TestBootstrapInterval:

    def test_interval_brackets_the_point_estimate(self):
        sep = bias_separation(TestBiasSeparation()._planted())
        bn = sep["overall"]["bullish_vs_neutral"]
        assert bn["ci_lo"] <= bn["gap"] <= bn["ci_hi"]

    def test_too_few_blocks_yields_no_interval(self):
        obs = _standardize(observations(TestBiasSeparation()._planted()))
        single = [o for o in obs if o["date"] <= sorted({x["date"] for x in obs})[5]]
        assert block_bootstrap_ci(single, "Bullish", "Neutral") is None

    def test_wide_interval_reads_as_underpowered_not_null(self):
        # A high p-value on a short sample must not be rendered as "no separation":
        # that is the misread KB-023 corrected.
        from bias_separation import _verdict, INCONCLUSIVE_CI_WIDTH
        sec = {
            "ordering": None,
            "bullish_vs_neutral": {
                "gap": -0.008, "p_value": 0.93,
                "ci_lo": -0.250, "ci_hi": 0.424,
            },
        }
        assert sec["bullish_vs_neutral"]["ci_hi"] - sec["bullish_vs_neutral"]["ci_lo"] > INCONCLUSIVE_CI_WIDTH
        v = _verdict(sec)
        assert "underpowered" in v
        assert "no separation" not in v

    def test_tight_interval_still_reads_as_no_separation(self):
        from bias_separation import _verdict
        sec = {
            "ordering": None,
            "bullish_vs_neutral": {
                "gap": 0.004, "p_value": 0.88, "ci_lo": -0.05, "ci_hi": 0.06,
            },
        }
        assert "no separation" in _verdict(sec)
