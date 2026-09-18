"""
Tests for fragility.py (WP-16.A.1 — fragility / phase-transition monitor).

Pure unit tests only: no network calls. Uses synthetic.py generators.

Run:
    pytest .macro-assist/tests/test_fragility.py -v
"""
import numpy as np
import pandas as pd
import pytest

from synthetic import synthetic_garch
from fragility import (
    realized_variance_trend,
    correlation_tightening,
    absorption_ratio,
    vix_term_backwardation,
    vix_term_reason,
    level_acceleration,
    lag1_autocorrelation,
    fragility_index,
    pit_label_cuts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _returns_to_close(returns: np.ndarray, start: float = 100.0) -> pd.Series:
    """Convert a log-return array to a Close price Series."""
    idx = pd.date_range("2024-01-01", periods=len(returns) + 1, freq="B")
    prices = start * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    return pd.Series(prices, index=idx)


def _vol_explosion(n: int = 200, seed: int = 7) -> np.ndarray:
    """Stationary returns whose volatility ramps up sharply in the final third."""
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 0.008, n)
    ramp = np.ones(n)
    tail = n // 3
    ramp[-tail:] = np.linspace(1.0, 6.0, tail)   # 6x vol blow-out
    return base * ramp


# ---------------------------------------------------------------------------
# realized_variance_trend
# ---------------------------------------------------------------------------

def test_variance_trend_rising_on_vol_explosion():
    close = _returns_to_close(_vol_explosion())
    result = realized_variance_trend(close)
    assert result is not None
    assert result["norm_slope"] > 0
    assert result["score"] > 60, f"expected fragile score, got {result['score']:.1f}"


def test_variance_trend_neutral_on_stationary():
    rng = np.random.default_rng(3)
    close = _returns_to_close(rng.normal(0, 0.01, 300))
    result = realized_variance_trend(close)
    assert result is not None
    # A stationary series should not register as strongly rising.
    assert 30 < result["score"] < 70


def test_variance_trend_insufficient_history_returns_none():
    close = _returns_to_close(np.zeros(5))
    assert realized_variance_trend(close) is None


# ---------------------------------------------------------------------------
# correlation_tightening
# ---------------------------------------------------------------------------

def test_correlation_high_when_assets_move_together():
    rng = np.random.default_rng(1)
    common = rng.normal(0, 0.01, 200)
    histories = {
        f"a{i}": _returns_to_close(common + rng.normal(0, 0.001, 200))
        for i in range(4)
    }
    result = correlation_tightening(histories)
    assert result is not None
    assert result["mean_abs_corr"] > 0.8
    assert result["score"] > 70


def test_correlation_low_when_assets_independent():
    rng = np.random.default_rng(2)
    histories = {
        f"a{i}": _returns_to_close(rng.normal(0, 0.01, 200))
        for i in range(4)
    }
    result = correlation_tightening(histories)
    assert result is not None
    assert result["mean_abs_corr"] < 0.3


def test_correlation_needs_two_assets():
    histories = {"only": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200))}
    assert correlation_tightening(histories) is None


# ---------------------------------------------------------------------------
# absorption_ratio
# ---------------------------------------------------------------------------

def _coupled_histories(n: int, rho_common: float, seed: int) -> dict:
    """Five assets, each a blend of a common factor and idiosyncratic noise.
    `rho_common` in [0,1] scales how much of each asset is the shared factor —
    higher => a more unified (tightly-coupled, high-absorption) market.
    """
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.01, n)
    histories = {}
    for i in range(5):
        idio = rng.normal(0, 0.01, n)
        rets = rho_common * common + (1 - rho_common) * idio
        histories[f"a{i}"] = _returns_to_close(rets)
    return histories


def test_absorption_needs_three_assets():
    histories = {
        "a": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200)),
        "b": _returns_to_close(np.random.default_rng(1).normal(0, 0.01, 200)),
    }
    assert absorption_ratio(histories) is None


def test_absorption_shift_rises_when_coupling_tightens():
    # First half loosely coupled, second half tightly coupled: AR_short should
    # sit above the baseline, so the standardized shift is positive.
    n = 260
    rng = np.random.default_rng(5)
    common = rng.normal(0, 0.01, n)
    histories = {}
    for i in range(5):
        idio = rng.normal(0, 0.01, n)
        rho = np.concatenate([np.full(n // 2, 0.1), np.full(n - n // 2, 0.9)])
        rets = rho * common + (1 - rho) * idio
        histories[f"a{i}"] = _returns_to_close(rets)
    result = absorption_ratio(histories)
    assert result is not None
    assert result["shift_z"] > 0
    assert result["score"] > 50
    assert 0.0 <= result["ar"] <= 1.0


def test_absorption_score_in_range():
    result = absorption_ratio(_coupled_histories(220, rho_common=0.5, seed=3))
    assert result is not None
    assert 0.0 <= result["score"] <= 100.0
    assert result["n_eig"] >= 1


# ---------------------------------------------------------------------------
# vix_term_backwardation
# ---------------------------------------------------------------------------

def test_vix_backwardation_full_persistence():
    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    vix = pd.Series(np.full(30, 30.0), index=idx)
    vix3m = pd.Series(np.full(30, 25.0), index=idx)   # ratio 1.2 > 1 every day
    result = vix_term_backwardation(vix, vix3m)
    assert result is not None
    assert result["persistence"] == 1.0
    assert result["score"] == 100.0


def test_vix_contango_zero_persistence():
    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    vix = pd.Series(np.full(30, 15.0), index=idx)
    vix3m = pd.Series(np.full(30, 18.0), index=idx)   # ratio < 1 (calm)
    result = vix_term_backwardation(vix, vix3m)
    assert result is not None
    assert result["score"] == 0.0


def test_vix_term_missing_returns_none():
    assert vix_term_backwardation(None, None) is None


def test_vix_term_stale_vix3m_returns_none():
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    vix = pd.Series(20.0, index=idx)
    vix3m = pd.Series(18.0, index=idx)                        # backwardation throughout
    assert vix_term_backwardation(vix, vix3m)["score"] == 100.0
    assert vix_term_backwardation(vix, vix3m.iloc[:-6]) is None   # 6 > max_stale (5)
    assert vix_term_backwardation(vix, vix3m.iloc[:-5])["score"] == 100.0  # within tolerance


# ---------------------------------------------------------------------------
# level_acceleration
# ---------------------------------------------------------------------------

def test_acceleration_positive_when_level_accelerates():
    # Quadratic ramp => positive, growing first differences => positive 2nd diff.
    series = pd.Series([float(t ** 2) * 0.01 for t in range(20)])
    result = level_acceleration(series)
    assert result is not None
    assert result["accel_z"] > 0
    assert result["score"] > 50


def test_acceleration_flat_series_returns_none():
    # Constant series => zero first-difference std => undefined => None.
    assert level_acceleration(pd.Series(np.ones(20))) is None


# ---------------------------------------------------------------------------
# lag1_autocorrelation
# ---------------------------------------------------------------------------

def test_autocorr_score_in_range():
    rng = np.random.default_rng(9)
    close = _returns_to_close(rng.normal(0, 0.01, 200))
    result = lag1_autocorrelation(close)
    assert result is not None
    assert 0.0 <= result["score"] <= 100.0


# ---------------------------------------------------------------------------
# fragility_index (composite)
# ---------------------------------------------------------------------------

def _make_histories(n: int = 250, seed: int = 0, explode: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    histories = {}
    for i, name in enumerate(["sp500", "nasdaq", "gold", "wti_oil"]):
        rets = _vol_explosion(n, seed=seed + i) if explode else rng.normal(0, 0.01, n)
        histories[name] = _returns_to_close(rets)
    return histories


def _with_vol(histories: dict, n: int = 250, seed: int = 1, backwardation: bool = False) -> dict:
    """Add fresh vix / vix3m legs on the same index as the price series."""
    rng = np.random.default_rng(seed)
    idx = next(iter(histories.values())).index
    vix = pd.Series(np.clip(20 + rng.normal(0, 2, len(idx)), 10, 80), index=idx)
    out = dict(histories)
    out["vix"] = vix
    out["vix3m"] = vix * (0.9 if backwardation else 1.1)
    return out


def test_index_output_keys_and_ranges():
    result = fragility_index(_with_vol(_make_histories()))
    assert result is not None
    assert set(result.keys()) == {"composite", "label", "trend", "components", "weights",
                                  "degraded", "degraded_detail"}
    assert 0.0 <= result["composite"] <= 100.0
    assert result["label"] in {"Resilient", "Normal", "Elevated"}
    assert result["degraded"] == []
    assert result["degraded_detail"] == {}
    assert result["trend"] in {"Rising", "Stable", "Falling"}
    # Renormalised weights over available components sum to ~1.
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9


def test_index_rising_under_vol_explosion():
    calm = fragility_index(_make_histories(explode=False, seed=10))
    stressed = fragility_index(_make_histories(explode=True, seed=10))
    assert calm is not None and stressed is not None
    assert stressed["composite"] > calm["composite"]
    assert stressed["trend"] == "Rising"


def test_index_none_when_no_components():
    assert fragility_index({}) is None


def test_index_weights_renormalise_when_components_missing():
    # Only one asset => no correlation, no vix term, no acceleration.
    histories = {"sp500": _returns_to_close(np.random.default_rng(0).normal(0, 0.01, 200))}
    result = fragility_index(histories)
    assert result is not None
    assert "correlation" not in result["components"]
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Degradation (IMP-5 / KB-029): a composite missing a required component is
# not on the distribution the cut-points were fitted to, so it carries no
# calibrated label. The live monitor printed its first-ever Elevated
# (2026-08-13..19, composite 59-62) with vix_term absent; with vix_term at its
# neighbouring value the same days score ~36 (Normal).
# ---------------------------------------------------------------------------

def test_index_label_unavailable_when_vix_term_missing():
    result = fragility_index(_make_histories())          # no vix / vix3m at all
    assert result is not None
    assert "vix_term" not in result["components"]
    assert result["degraded"] == ["vix_term"]
    assert result["label"] == "Unavailable"
    # The number is still reported for the record.
    assert 0.0 <= result["composite"] <= 100.0


def test_degradation_would_have_flagged_the_august_2026_false_alarm():
    # A vol explosion with vix_term present reads Normal-ish; drop the vol legs
    # and the renormalised composite (now ~90% variance_trend) jumps. Before the
    # fix that jump could cross the Elevated cut; now it carries no label at all.
    stressed = _make_histories(explode=True, seed=10)
    full = fragility_index(_with_vol(stressed, backwardation=False))
    degraded = fragility_index(stressed)
    assert full["degraded"] == [] and full["label"] != "Unavailable"
    assert degraded["label"] == "Unavailable"
    assert degraded["composite"] > full["composite"]     # the renormalisation inflates it


def test_degradation_ignores_components_with_zero_weight():
    # A weight scheme that zeroes vix_term does not require it.
    weights = {"variance_trend": 1.0, "vix_term": 0.0, "correlation": 0.0,
               "acceleration": 0.0, "autocorr": 0.0, "absorption": 0.0}
    result = fragility_index(_make_histories(), weights=weights)
    assert result["degraded"] == []
    assert result["label"] in {"Resilient", "Normal", "Elevated"}


def test_stale_vix3m_degrades_rather_than_freezing():
    # vix3m that stopped updating 30 observations ago: the ratio would silently
    # freeze on the last shared window. It must count as missing instead.
    h = _with_vol(_make_histories(), backwardation=True)
    h["vix3m"] = h["vix3m"].iloc[:-30]
    result = fragility_index(h)
    assert "vix_term" not in result["components"]
    assert result["label"] == "Unavailable"
    assert result["degraded"] == ["vix_term"]


# ---------------------------------------------------------------------------
# Attribution (IMP-5.4): `degraded` says the label is withheld; it does not say
# WHICH feed died. Three consecutive Unavailable readings in September 2026
# (09-16..09-18) were unattributable after the fact for exactly that reason —
# nothing recorded whether yfinance was empty, the leg was stale, or the CBOE
# fallback had failed. Each of those is now a distinct, asserted reason.
# ---------------------------------------------------------------------------

def test_vix_term_reason_is_none_when_the_component_computes():
    h = _with_vol(_make_histories(), backwardation=True)
    assert vix_term_reason(h["vix"], h["vix3m"]) is None
    assert vix_term_backwardation(h["vix"], h["vix3m"]) is not None


def test_vix_term_reason_names_an_absent_leg():
    h = _with_vol(_make_histories())
    reason = vix_term_reason(h["vix"], None)
    assert reason is not None and "vix3m" in reason and "absent" in reason
    assert "vix series absent" == vix_term_reason(None, h["vix3m"])


def test_vix_term_reason_names_a_stale_leg_with_its_last_date():
    h = _with_vol(_make_histories())
    h["vix3m"] = h["vix3m"].iloc[:-30]
    reason = vix_term_reason(h["vix"], h["vix3m"])
    assert reason is not None and "stale" in reason
    # The reason carries the two numbers a human needs to act: how far behind,
    # and since when.
    assert str(h["vix3m"].index[-1].date()) in reason
    assert "30 vix observations after it" in reason


def test_vix_term_reason_names_a_non_overlapping_pair():
    h = _with_vol(_make_histories())
    # Fresh by the staleness rule (its last date is the anchor's), but only
    # three dates in common — a different failure with a different fix.
    h["vix3m"] = h["vix3m"].iloc[[-5, -3, -1]]
    reason = vix_term_reason(h["vix"], h["vix3m"])
    assert reason is not None and "shared vix/vix3m dates" in reason


def test_degraded_detail_carries_the_reason_into_the_reading():
    h = _with_vol(_make_histories())
    h["vix3m"] = h["vix3m"].iloc[:-30]
    result = fragility_index(h)
    assert result["degraded"] == ["vix_term"]
    assert "stale" in result["degraded_detail"]["vix_term"]


def test_degraded_detail_distinguishes_absent_from_stale():
    h = _with_vol(_make_histories())
    absent = fragility_index({k: v for k, v in h.items() if k != "vix3m"})
    stale = dict(h, vix3m=h["vix3m"].iloc[:-30])
    stale = fragility_index(stale)
    assert absent["degraded"] == stale["degraded"] == ["vix_term"]
    # Same `degraded` list, different diagnosis — which is the whole point.
    assert absent["degraded_detail"]["vix_term"] != stale["degraded_detail"]["vix_term"]


def test_index_deterministic():
    h = _make_histories(seed=42)
    assert fragility_index(h)["composite"] == fragility_index(h)["composite"]


# ---------------------------------------------------------------------------
# IMP-5.3 — expanding-PIT label cuts (tested and NOT adopted, KB-030; the
# function stays because the gate harness is the reproducible record)
# ---------------------------------------------------------------------------

def test_pit_label_cuts_none_below_warmup():
    assert pit_label_cuts(np.arange(251), warmup=252) is None
    assert pit_label_cuts([], warmup=252) is None


def test_pit_label_cuts_are_quantiles_of_the_prior_history():
    cuts = pit_label_cuts(np.arange(1001), warmup=252)
    assert cuts["n_prior"] == 1001
    assert cuts["elevated"] == pytest.approx(900.0)
    assert cuts["resilient"] == pytest.approx(400.0)


def test_pit_label_cuts_ignore_nan_readings():
    prior = np.r_[np.arange(300.0), [np.nan] * 50]
    cuts = pit_label_cuts(prior, warmup=252)
    assert cuts["n_prior"] == 300           # NaN (degraded) days are not history
    assert pit_label_cuts(np.r_[np.arange(200.0), [np.nan] * 100], warmup=252) is None
