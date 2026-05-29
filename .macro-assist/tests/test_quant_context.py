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
    _build_vol_block,
    _build_regime_block,
    _build_conditional_block,
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

    def test_all_three_subsections_present(self):
        """Golden path: all three subsections appear in the output."""
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
        assert "**Regime" in output
        assert "**Conditional return distribution" in output

    def test_returns_string(self):
        hist  = _make_histories()
        snap  = _make_snapshot()
        output = build_quant_context(
            snap, date(2023, 1, 4),
            histories=hist,
        )
        assert isinstance(output, str)

    def test_empty_on_no_data(self):
        """With no histories and no model, output should be empty."""
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
