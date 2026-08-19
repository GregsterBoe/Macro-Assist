"""
Tests for portfolio/sizing.py (Phase 20, WP-20.C).

Pure unit tests — no network, no model objects. Cover the seven-step vol-target
rule: direction (incl. 10Y sign inversion), confidence scaling, risk blending,
the missing-distribution abstention, the regime gate, exact ex-ante vol
targeting, and the per-asset / gross clamps.

Run:
    pytest .macro-assist/tests/test_sizing.py -v
"""
from __future__ import annotations

import math

import pytest

from portfolio.sizing import (
    AssetSignal,
    RegimeState,
    SizingConfig,
    dispersion_annual_from_distribution,
    har_sigma_annual_from_forecast,
    size_positions,
)

LABELS = ["Risk-On Low-Vol", "Risk-On High-Vol", "Risk-Off Low-Vol", "Risk-Off High-Vol"]


def _calm_regime() -> RegimeState:
    # all mass on low-vol states -> gate = 1
    return RegimeState(posterior=[0.7, 0.0, 0.3, 0.0], labels=LABELS)


def _vol_proxy(result, signals) -> float:
    sig = {s.asset: s for s in signals}
    used = {a: t.sigma_used for a, t in result.targets.items()}
    return sum(abs(w) * used[a] for a, w in result.weights.items())


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def test_har_sigma_percent_to_fraction():
    assert har_sigma_annual_from_forecast({"forecast_daily_vol": 16.0}) == pytest.approx(0.16)


def test_dispersion_annualizes_and_handles_none():
    assert dispersion_annual_from_distribution(None, 5) is None
    # symmetric 5-day dist: p90-p10 = 2.5631*sigma_5d ; here sigma_5d = 0.02
    dist = {"p10": -0.02 * 2.5631 / 2, "p90": 0.02 * 2.5631 / 2, "n": 100}
    got = dispersion_annual_from_distribution(dist, 5)
    assert got == pytest.approx(0.02 * math.sqrt(252 / 5), rel=1e-6)


# ---------------------------------------------------------------------------
# Direction & abstention
# ---------------------------------------------------------------------------
def test_bullish_is_long_bearish_is_short():
    sigs = [
        AssetSignal("S&P 500", "Bullish", 0.5, 0.16, 0.16),
        AssetSignal("Gold", "Bearish", 0.5, 0.16, 0.16),
    ]
    r = size_positions(sigs, _calm_regime(), SizingConfig())
    assert r.weights["S&P 500"] > 0
    assert r.weights["Gold"] < 0
    assert r.targets["S&P 500"].direction == 1.0
    assert r.targets["Gold"].direction == -1.0


def test_ten_year_yield_inversion_flips_bond_proxy():
    # Bullish *yield* -> short bonds
    sig = AssetSignal("10Y (IEF)", "Bullish", 0.5, 0.06, 0.06, invert_sign=True)
    r = size_positions([sig], _calm_regime(), SizingConfig())
    assert r.targets["10Y (IEF)"].direction == -1.0
    assert r.weights["10Y (IEF)"] < 0


def test_neutral_abstains():
    sigs = [AssetSignal("S&P 500", "Neutral", 0.9, 0.16, 0.16)]
    r = size_positions(sigs, _calm_regime(), SizingConfig())
    assert "S&P 500" not in r.weights
    assert r.targets["S&P 500"].abstained
    assert r.targets["S&P 500"].reason == "neutral/no-view"


def test_missing_distribution_abstains_when_required():
    sigs = [AssetSignal("Bitcoin", "Bullish", 0.9, 0.6, None)]
    r = size_positions(sigs, _calm_regime(), SizingConfig(require_distribution=True))
    assert "Bitcoin" not in r.weights
    assert r.targets["Bitcoin"].reason == "no-distribution"


def test_missing_distribution_allowed_when_not_required():
    sigs = [AssetSignal("Bitcoin", "Bullish", 0.9, 0.6, None)]
    r = size_positions(sigs, _calm_regime(), SizingConfig(require_distribution=False))
    assert r.weights["Bitcoin"] > 0


# ---------------------------------------------------------------------------
# Confidence & risk
# ---------------------------------------------------------------------------
def test_higher_confidence_gets_more_weight():
    lo = size_positions([AssetSignal("A_only", "Bullish", 0.2, 0.16, 0.16)], _calm_regime())
    hi = size_positions([AssetSignal("A_only", "Bullish", 0.9, 0.16, 0.16)], _calm_regime())
    # single asset: vol-target rescale pins both to the same ex-ante vol, so a
    # lone position is confidence-independent post-rescale. Confidence matters
    # *relatively*, so test it across two assets sharing the book's vol budget.
    a, b = AssetSignal("A", "Bullish", 0.9, 0.16, 0.16), AssetSignal("B", "Bullish", 0.3, 0.16, 0.16)
    r = size_positions([a, b], _calm_regime())
    assert abs(r.weights["A"]) > abs(r.weights["B"])


def test_confidence_clamped_to_unit_interval():
    r = size_positions([AssetSignal("A", "Bullish", 5.0, 0.16, 0.16),
                        AssetSignal("B", "Bullish", 1.0, 0.16, 0.16)], _calm_regime())
    # c=5 clamps to 1.0 == B's confidence -> equal weights
    assert r.weights["A"] == pytest.approx(r.weights["B"])


def test_lower_vol_gets_more_weight():
    a = AssetSignal("A", "Bullish", 0.6, 0.08, 0.08)   # low vol
    b = AssetSignal("B", "Bullish", 0.6, 0.32, 0.32)   # high vol
    r = size_positions([a, b], _calm_regime())
    assert abs(r.weights["A"]) > abs(r.weights["B"])


def test_risk_blend_max_is_conservative():
    # cond dispersion higher than HAR -> "max" uses the larger sigma -> smaller |w|
    s = AssetSignal("A", "Bullish", 0.6, 0.10, 0.30)
    r_max = size_positions([s, AssetSignal("B", "Bullish", 0.6, 0.10, 0.10)],
                           _calm_regime(), SizingConfig(risk_blend="max"))
    assert r_max.targets["A"].sigma_used == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Vol targeting
# ---------------------------------------------------------------------------
def test_exante_vol_hits_target():
    sigs = [
        AssetSignal("A", "Bullish", 0.7, 0.16, 0.16),
        AssetSignal("B", "Bearish", 0.4, 0.20, 0.20),
    ]
    cfg = SizingConfig(vol_target_annual=0.10, max_weight=1.0, gross_cap=10.0)
    r = size_positions(sigs, _calm_regime(), cfg)
    # unclamped -> Σ|w|σ should equal the target exactly
    assert _vol_proxy(r, sigs) == pytest.approx(0.10, rel=1e-6)


def test_all_neutral_gives_empty_book():
    sigs = [AssetSignal("A", "Neutral", 0.9, 0.16, 0.16),
            AssetSignal("B", None, 0.9, 0.16, 0.16)]
    r = size_positions(sigs, _calm_regime())
    assert r.weights == {}
    assert r.gross == 0.0


# ---------------------------------------------------------------------------
# Regime gate
# ---------------------------------------------------------------------------
def test_high_vol_regime_shrinks_the_book():
    sigs = [AssetSignal("A", "Bullish", 0.7, 0.16, 0.16),
            AssetSignal("B", "Bearish", 0.4, 0.20, 0.20)]
    cfg = SizingConfig(max_weight=1.0, gross_cap=10.0)
    calm = size_positions(sigs, _calm_regime(), cfg)
    stormy_regime = RegimeState(posterior=[0.1, 0.4, 0.1, 0.4], labels=LABELS)  # 0.8 high-vol
    stormy = size_positions(sigs, stormy_regime, cfg)
    assert stormy.gate == pytest.approx(0.2)
    # gate folds into the effective vol target -> book vol scaled by g
    assert _vol_proxy(stormy, sigs) == pytest.approx(0.10 * 0.2, rel=1e-6)
    assert stormy.gross < calm.gross


def test_no_regime_means_no_gate():
    r = size_positions([AssetSignal("A", "Bullish", 0.7, 0.16, 0.16)], None)
    assert r.gate == 1.0


# ---------------------------------------------------------------------------
# Clamps
# ---------------------------------------------------------------------------
def test_per_asset_max_weight_clamp():
    # one screaming high-confidence low-vol name would blow past the cap
    sigs = [AssetSignal("A", "Bullish", 1.0, 0.03, 0.03)]
    cfg = SizingConfig(max_weight=0.35, gross_cap=1.5, require_distribution=True)
    r = size_positions(sigs, _calm_regime(), cfg)
    assert abs(r.weights["A"]) == pytest.approx(0.35)


def test_gross_cap_scales_book_down():
    sigs = [
        AssetSignal("A", "Bullish", 1.0, 0.05, 0.05),
        AssetSignal("B", "Bullish", 1.0, 0.05, 0.05),
        AssetSignal("C", "Bullish", 1.0, 0.05, 0.05),
        AssetSignal("D", "Bullish", 1.0, 0.05, 0.05),
        AssetSignal("E", "Bullish", 1.0, 0.05, 0.05),
    ]
    cfg = SizingConfig(max_weight=0.35, gross_cap=1.5)
    r = size_positions(sigs, _calm_regime(), cfg)
    # 5 * 0.35 = 1.75 > 1.5 -> scaled to exactly the gross cap
    assert r.gross == pytest.approx(1.5)
