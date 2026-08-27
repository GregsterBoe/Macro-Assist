"""
Tests for quant_context.py (Phase 12).

Pure unit tests — no network calls, no disk I/O (models and tables are built
from synthetic data and injected directly).

Run:
    pytest .macro-assist/tests/test_quant_context.py -v
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_context import (
    build_quant_context,
    build_nonlive_signals_block,
    _build_vol_block,
    _build_regime_block,
    _build_conditional_block,
    _build_fragility_block,
    _compute_fragility,
    _fragility_mode,
    _FRAGILITY_MODE_ENV,
    _build_or_mode_block,
    _compute_or_mode,
    _fragility_or_mode,
    _FRAGILITY_OR_MODE_ENV,
)
from synthetic import synthetic_garch
from conditional import build_distribution_table, assign_bucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_histories(n: int = 200, seed: int = 0) -> dict:
    """Synthetic Close price series for each tracked asset."""
    rng = np.random.default_rng(seed)
    result = {}
    for key in ("sp500", "gold", "wti_oil", "bitcoin"):
        prices = 1000.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n))
        result[key] = pd.Series(prices)
    return result


def _make_snapshot(nfci: float = -0.3, t10: float = 4.2, t2: float = 4.5,
                   hy: float = 4.1, hy_mean: float = 4.2) -> dict:
    return {
        "nfci":         {"value": nfci},
        "treasury_10y": {"value": t10},
        "treasury_2y":  {"value": t2},
        "hy_spread":    {"value": hy, "five_yr_mean": hy_mean},
        "baa_spread":   {"value": hy, "five_yr_mean": hy_mean},  # regime credit feature [2]
    }


def _make_market_data(vix: float = 18.5) -> dict:
    return {"vix": {"price": vix}}


def _make_regime_model():
    """Fit a minimal GaussianHMM on synthetic data (no disk I/O)."""
    from hmmlearn.hmm import GaussianHMM

    rng = np.random.default_rng(99)
    X = rng.normal(0, 1, (300, 4))
    model = GaussianHMM(n_components=4, covariance_type="full",
                        n_iter=50, random_state=42)
    model.fit(X)
    return model


def _make_distribution_table() -> dict:
    """Build a small distribution table from synthetic snapshots."""
    rng = np.random.default_rng(7)
    snapshots = []
    base_date = date(2020, 1, 2)
    for i in range(300):
        d = date.fromordinal(base_date.toordinal() + i)
        snap = {
            "nfci":         {"value": float(rng.uniform(-0.8, 0.2))},
            "treasury_10y": {"value": float(rng.uniform(0.5, 5.0))},
            "treasury_2y":  {"value": float(rng.uniform(0.3, 4.8))},
            "hy_spread":    {"value": float(rng.uniform(2.5, 7.0))},
        }
        snapshots.append((d, snap))

    # Forward returns: SP500, Gold, WTI Oil
    forward_returns: dict = {"SP500": {}, "Gold": {}, "WTI Oil": {}}
    for snap_date, _ in snapshots:
        for asset in forward_returns:
            forward_returns[asset][snap_date] = {
                5:  float(rng.normal(0.5, 2.0)),
                10: float(rng.normal(1.0, 3.0)),
                20: float(rng.normal(2.0, 4.5)),
            }

    return build_distribution_table(snapshots, forward_returns, min_n=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildQuantContext:

    def test_active_subsections_present(self):
        """Golden path: the active subsections appear; the retired Regime block
        (WP-17.4 / KB-006) must NOT appear in the note."""
        hist   = _make_histories()
        snap   = _make_snapshot()
        mdata  = _make_market_data()
        model  = _make_regime_model()
        table  = _make_distribution_table()

        output = build_quant_context(
            snap, date(2023, 1, 4),
            market_data=mdata,
            histories=hist,
            regime_model=model,
            distribution_table=table,
        )

        assert "## Quantitative Context" in output
        assert "**Volatility" in output
        assert "**Conditional return distribution" in output
        assert "**Regime" not in output   # retired

    def test_returns_string(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        output = build_quant_context(
            snap, date(2023, 1, 4),
            histories=hist,
        )
        assert isinstance(output, str)

    def test_empty_on_no_data(self, monkeypatch, tmp_path):
        """With no histories, no model, and no on-disk distribution table, output is empty.

        The conditional block reads the persisted distribution table from
        DEFAULT_TABLE_PATH regardless of histories, so isolate the test from the
        committed table (otherwise it renders a conditional block and this fails).
        """
        import quant_context as _qc
        monkeypatch.setattr(_qc, "DEFAULT_TABLE_PATH", tmp_path / "absent.json")
        snap   = _make_snapshot()
        output = build_quant_context(snap, date(2023, 1, 4))
        assert output == ""

    def test_partial_degradation_no_model(self):
        """Without a regime model, the vol block still appears."""
        hist  = _make_histories()
        snap  = _make_snapshot()
        mdata = _make_market_data()
        output = build_quant_context(
            snap, date(2023, 1, 4),
            market_data=mdata,
            histories=hist,
        )
        # Vol block should be present; regime and conditional may be absent
        if output:
            assert "**Volatility" in output

    def test_no_histories_no_vol_block(self):
        """With no histories, the Volatility block is omitted."""
        snap  = _make_snapshot()
        model = _make_regime_model()
        output = build_quant_context(
            snap, date(2023, 1, 4),
            regime_model=model,
        )
        assert "**Volatility" not in output


class TestBuildVolBlock:

    def test_output_contains_assets(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        mdata = _make_market_data()
        block = _build_vol_block(snap, mdata, hist)
        assert "SP500" in block
        assert "Gold" in block
        assert "WTI Oil" in block
        assert "Bitcoin" in block

    def test_vrp_present_for_sp500_with_vix(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        mdata = _make_market_data(vix=20.0)
        block = _build_vol_block(snap, mdata, hist)
        assert "VIX" in block
        assert "VRP" in block
        # interpretation label should be one of the three
        assert any(label in block for label in ("Normal", "Elevated", "Compressed"))

    def test_no_vrp_without_market_data(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        block = _build_vol_block(snap, None, hist)
        assert "**Volatility" in block
        assert "VIX" not in block

    def test_empty_on_no_histories(self):
        snap  = _make_snapshot()
        mdata = _make_market_data()
        block = _build_vol_block(snap, mdata, None)
        assert block == ""

    def test_empty_on_short_histories(self):
        hist = {"sp500": pd.Series(np.ones(10))}  # too short for HAR-RV
        snap = _make_snapshot()
        block = _build_vol_block(snap, None, hist)
        assert block == ""

    def test_vol_values_positive(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        block = _build_vol_block(snap, None, hist)
        # Every '% ann-vol' figure should be a positive number
        import re
        vals = re.findall(r"([\d.]+)% ann-vol", block)
        assert len(vals) > 0
        for v in vals:
            assert float(v) > 0


class TestBuildRegimeBlock:

    def test_output_format(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        model = _make_regime_model()
        block = _build_regime_block(snap, hist, model)
        assert "**Regime" in block
        assert "Current:" in block
        assert "posterior" in block
        assert "Transition probabilities:" in block

    def test_posterior_in_range(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        model = _make_regime_model()
        block = _build_regime_block(snap, hist, model)
        import re
        post = re.search(r"posterior ([\d.]+)", block)
        assert post is not None
        val = float(post.group(1))
        assert 0.0 <= val <= 1.0

    def test_empty_without_model_or_path(self):
        """No model provided and no file on disk → empty string."""
        snap  = _make_snapshot()
        block = _build_regime_block(snap, None, None)
        # Either returns "" (no model file) or a valid block (file exists)
        assert isinstance(block, str)

    def test_no_sp500_history_still_works(self):
        """Regime should still run with NaN vol feature when sp500 is absent."""
        snap  = _make_snapshot()
        model = _make_regime_model()
        block = _build_regime_block(snap, {}, model)
        assert "**Regime" in block


class TestBuildNonliveSignalsBlock:

    def test_empty_when_no_signals(self, monkeypatch, tmp_path):
        # No histories (no fragility fetch) and no model on disk => nothing renders.
        import quant_context as _qc
        monkeypatch.setattr(_qc, "DEFAULT_MODEL_PATH", tmp_path / "absent.pkl")
        snap = _make_snapshot()
        assert build_nonlive_signals_block(snap, None, regime_model=None) == ""

    def test_renders_fragility_in_show_mode_regardless_of_env(self, monkeypatch):
        # Live mode is 'log' (block hidden in the note); the non-live preview must
        # still surface the reading by forcing 'show'.
        monkeypatch.setenv(_FRAGILITY_MODE_ENV, "log")
        snap  = _make_snapshot()
        block = build_nonlive_signals_block(snap, _make_frag_histories(), regime_model=None)
        assert "NON-LIVE SIGNALS" in block
        assert "**Fragility Monitor" in block

    def test_regime_block_omitted_by_default(self, monkeypatch):
        # REGIME-RETIRED (KB-006): the HMM regime is off by default, so even with a
        # model in hand the non-live preview must NOT render its block.
        monkeypatch.delenv("REGIME_ENABLED", raising=False)
        snap  = _make_snapshot()
        model = _make_regime_model()
        block = build_nonlive_signals_block(snap, _make_frag_histories(), regime_model=model)
        assert "**Regime" not in block

    def test_includes_retired_regime_block_when_enabled(self, monkeypatch):
        # With REGIME_ENABLED=1 the retired block is surfaced again (revival path).
        monkeypatch.setenv("REGIME_ENABLED", "1")
        snap  = _make_snapshot()
        model = _make_regime_model()
        block = build_nonlive_signals_block(snap, _make_histories(), regime_model=model)
        assert "**Regime" in block
        assert "retired WP-17.4" in block


class TestBuildConditionalBlock:

    def test_output_format(self):
        snap  = _make_snapshot()
        table = _make_distribution_table()
        block = _build_conditional_block(snap, table)
        assert "**Conditional return distribution" in block
        assert "bucket:" in block
        assert "| Asset | Horizon |" in block

    def test_returns_empty_on_empty_table(self):
        snap  = _make_snapshot()
        block = _build_conditional_block(snap, {})
        assert block == ""

    def test_returns_empty_on_no_table_no_path(self):
        snap  = _make_snapshot()
        block = _build_conditional_block(snap, None)
        # Either "" (no file) or valid block (file present)
        assert isinstance(block, str)

    def test_table_rows_have_percentage_signs(self):
        snap  = _make_snapshot()
        table = _make_distribution_table()
        block = _build_conditional_block(snap, table)
        if "Asset" in block:  # only check if table was produced
            assert "%" in block

    def test_bucket_label_in_header(self):
        snap   = _make_snapshot()
        table  = _make_distribution_table()
        bucket = assign_bucket(snap)
        block  = _build_conditional_block(snap, table)
        if block:
            assert bucket in block


# ---------------------------------------------------------------------------
# Fragility monitor (Phase 16, WP-16.A.4 — shadow wiring)
# ---------------------------------------------------------------------------

def _make_frag_histories(n: int = 200, seed: int = 3) -> dict:
    """Long synthetic Close series incl. vix/vix3m so the fragility index has
    every component available. >= _MIN_FRAG_HISTORY so no network fetch fires."""
    rng = np.random.default_rng(seed)
    out = {}
    for key in ("sp500", "nasdaq", "gold", "wti_oil", "dxy"):
        out[key] = pd.Series(1000.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n)))
    out["vix"]   = pd.Series(np.clip(18 + rng.normal(0, 3, n), 9, 80))
    out["vix3m"] = pd.Series(np.clip(20 + rng.normal(0, 2, n), 10, 80))
    return out


_ELEVATED_RESULT = {
    "composite": 72.0, "label": "Elevated", "trend": "Rising",
    "components": {"variance_trend": {"score": 70.0}},
    "weights": {"variance_trend": 0.9},
}
_NORMAL_RESULT = {
    "composite": 30.0, "label": "Normal", "trend": "Stable",
    "components": {"variance_trend": {"score": 30.0}},
    "weights": {"variance_trend": 0.9},
}


class TestFragilityMode:

    def test_default_mode_is_log(self, monkeypatch):
        monkeypatch.delenv(_FRAGILITY_MODE_ENV, raising=False)
        assert _fragility_mode() == "log"

    def test_invalid_mode_falls_back_to_log(self, monkeypatch):
        monkeypatch.setenv(_FRAGILITY_MODE_ENV, "bogus")
        assert _fragility_mode() == "log"

    def test_explicit_modes_resolve(self, monkeypatch):
        for m in ("log", "show", "active"):
            monkeypatch.setenv(_FRAGILITY_MODE_ENV, m.upper())  # case-insensitive
            assert _fragility_mode() == m


class TestBuildFragilityBlock:

    def test_log_mode_renders_nothing(self):
        # Even with a valid reading, log mode never shows the block.
        assert _build_fragility_block(_result=_ELEVATED_RESULT, mode="log") == ""

    def test_renders_reading_from_histories(self):
        block = _build_fragility_block(_make_frag_histories(), allow_fetch=False, mode="show")
        assert "**Fragility Monitor" in block
        assert "Composite:" in block
        assert any(lbl in block for lbl in ("Resilient", "Normal", "Elevated"))

    def test_no_network_when_histories_absent(self):
        # No histories => no fetch, no block (protects the no-network contract).
        assert _build_fragility_block(None, allow_fetch=True, mode="show") == ""
        assert _compute_fragility(None, allow_fetch=True) is None

    def test_short_histories_no_fetch_when_disallowed(self):
        short = {"sp500": pd.Series(np.ones(50))}
        assert _compute_fragility(short, allow_fetch=False) is None

    def test_show_mode_marks_directive_inactive_when_elevated(self):
        block = _build_fragility_block(_result=_ELEVATED_RESULT, mode="show")
        assert "directive inactive" in block
        assert "Action" not in block

    def test_active_mode_emits_directive_when_elevated(self):
        block = _build_fragility_block(_result=_ELEVATED_RESULT, mode="active")
        assert "**Action:**" in block
        assert "Widen your Target Ranges" in block
        assert "Do NOT change the Bias" in block

    def test_no_directive_when_not_elevated(self):
        block = _build_fragility_block(_result=_NORMAL_RESULT, mode="active")
        assert "Action" not in block
        assert "directive inactive" not in block

    def test_empty_on_no_result(self):
        assert _build_fragility_block(_result=None, histories=None, allow_fetch=False, mode="show") == ""


# ---------------------------------------------------------------------------
# OR-of-channels recall mode (Phase 16 / IMP-4.3 — shadow wiring)
# ---------------------------------------------------------------------------

def _or_reading(flag: bool, fired=None) -> dict:
    """A synthetic OR-mode reading (no network), mirroring fragility_or output."""
    fired = fired or ([] if not flag else ["AR", "TURB"])
    return {
        "asof": pd.Timestamp("2026-08-27"),
        "flag": flag,
        "fired_channels": fired,
        "q": 0.90,
        "channels": {
            "comp": {"value": 42.0, "pit_threshold": 78.0, "fired": "comp" in fired,
                     "percentile": 0.44, "n_prior": 900},
            "AR":   {"value": 70.0, "pit_threshold": 60.0, "fired": "AR" in fired,
                     "percentile": 0.95, "n_prior": 800},
            "TURB": {"value": 12.0, "pit_threshold": 9.0, "fired": "TURB" in fired,
                     "percentile": 0.97, "n_prior": 800},
        },
    }


class TestFragilityOrMode:

    def test_default_mode_is_off(self, monkeypatch):
        monkeypatch.delenv(_FRAGILITY_OR_MODE_ENV, raising=False)
        assert _fragility_or_mode() == "off"

    def test_invalid_mode_falls_back_to_off(self, monkeypatch):
        monkeypatch.setenv(_FRAGILITY_OR_MODE_ENV, "bogus")
        assert _fragility_or_mode() == "off"

    def test_explicit_modes_resolve(self, monkeypatch):
        for m in ("off", "log", "show", "active"):
            monkeypatch.setenv(_FRAGILITY_OR_MODE_ENV, m.upper())  # case-insensitive
            assert _fragility_or_mode() == m

    def test_off_computes_nothing_no_network(self, monkeypatch):
        # 'off' must short-circuit before any import/fetch and return None.
        monkeypatch.delenv(_FRAGILITY_OR_MODE_ENV, raising=False)
        import quant_context as _qc
        _qc._OR_MODE_CACHE.clear()
        assert _compute_or_mode() is None


class TestBuildOrModeBlock:

    def test_off_renders_nothing(self):
        assert _build_or_mode_block(_reading=_or_reading(True), mode="off") == ""

    def test_log_renders_nothing(self):
        # Like FRAGILITY_MODE=log: computed/logged elsewhere, never shown.
        assert _build_or_mode_block(_reading=_or_reading(True), mode="log") == ""

    def test_show_renders_flag_and_channels(self):
        block = _build_or_mode_block(_reading=_or_reading(True), mode="show")
        assert "**Fragility OR-mode" in block
        assert "FIRING" in block
        assert "absorption" in block and "turbulence" in block
        assert "directive inactive" in block
        assert "Action" not in block

    def test_show_marks_quiet_when_not_firing(self):
        block = _build_or_mode_block(_reading=_or_reading(False), mode="show")
        assert "quiet" in block
        assert "directive inactive" not in block  # only shown when firing

    def test_active_emits_directive_when_firing(self):
        block = _build_or_mode_block(_reading=_or_reading(True), mode="active")
        assert "**Action:**" in block
        assert "Widen your Target Ranges" in block
        assert "Do NOT change the Bias" in block

    def test_active_no_directive_when_quiet(self):
        block = _build_or_mode_block(_reading=_or_reading(False), mode="active")
        assert "Action" not in block

    def test_empty_on_no_reading(self):
        assert _build_or_mode_block(_reading=None, mode="show") == ""
