"""Tests for fragility_or (IMP-4.3, the live OR-of-channels recall mode).

These exercise the PIT-threshold flag logic on injected channel series — no
network, no walk-forward. The end-to-end reproduction of the KB-020 operating
point is validated by `python fragility_or.py` and `input_testing.py etf`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fragility_or import or_mode_reading, _CH_KEYS


def _channels(comp_last, ar_last, turb_last, n=400, seed=0):
    """Build a channels dict: n-1 baseline readings in [0,1) plus a chosen last
    value per channel, so the PIT top-decile threshold is well-defined."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    out = {"common": idx, "gspc": pd.Series(np.ones(n), index=idx)}
    for k, last in zip(_CH_KEYS, (comp_last, ar_last, turb_last)):
        base = rng.uniform(0.0, 1.0, n - 1)
        out[k] = pd.Series(np.append(base, last), index=idx)
    return out


def test_flag_fires_when_a_channel_tops_its_decile():
    # AR's last value (5.0) is far above its own 90th pct (~0.9) -> fires.
    r = or_mode_reading(_channels(0.1, 5.0, 0.1), min_warmup=100)
    assert r["flag"] is True
    assert "AR" in r["fired_channels"]
    assert r["channels"]["AR"]["fired"] is True
    assert r["channels"]["comp"]["fired"] is False


def test_quiet_when_all_channels_mid_distribution():
    # Every last value sits near the median of its own history -> no fire.
    r = or_mode_reading(_channels(0.5, 0.5, 0.5), min_warmup=100)
    assert r["flag"] is False
    assert r["fired_channels"] == []


def test_or_fires_if_any_single_channel_fires():
    # Only turbulence tops its decile; the OR still fires (recall knob).
    r = or_mode_reading(_channels(0.4, 0.3, 9.0), min_warmup=100)
    assert r["flag"] is True
    assert r["fired_channels"] == ["TURB"]


def test_threshold_uses_only_prior_values():
    # The last value must be EXCLUDED from its own threshold (no self-leakage):
    # with a huge last value, the 90th pct of the prior-only history stays small.
    r = or_mode_reading(_channels(0.1, 100.0, 0.1), min_warmup=100)
    assert r["channels"]["AR"]["pit_threshold"] < 1.0
    assert r["channels"]["AR"]["percentile"] == 1.0  # above all priors


def test_insufficient_history_yields_no_threshold():
    # Fewer prior readings than min_warmup -> threshold None, channel cannot fire.
    r = or_mode_reading(_channels(9.0, 9.0, 9.0, n=50), min_warmup=252)
    for k in _CH_KEYS:
        assert r["channels"][k]["pit_threshold"] is None
        assert r["channels"][k]["fired"] is False
    assert r["flag"] is False


def test_reading_carries_asof_and_all_channels():
    r = or_mode_reading(_channels(0.5, 0.5, 0.5), min_warmup=100)
    assert r["asof"] == pd.Timestamp("2020-01-01") + pd.tseries.offsets.BDay(399)
    assert set(r["channels"]) == set(_CH_KEYS)
    assert r["q"] == 0.90
