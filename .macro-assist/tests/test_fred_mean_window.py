"""
todo #13 — `five_yr_mean` is labelled five years but computed over whatever
FRED returned, and free FRED serves `BAMLH0A0HYM2` on a rolling ~3-year window
([KB-028] nuance (d)). The fix is to emit the window actually used beside the
number, in every place the number is computed, so the model is never told
"5-yr average" for something that is not.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

import fred_data
import point_in_time


def _series(start: str, periods: int, freq: str = "D") -> pd.Series:
    idx = pd.date_range(start, periods=periods, freq=freq)
    return pd.Series(range(1, periods + 1), index=idx, dtype=float)


def test_mean_window_names_the_span_actually_covered():
    w = fred_data._mean_window(_series("2023-09-12", 1096))     # ≈ 3 years
    assert w["mean_window_start"] == "2023-09-12"
    assert w["mean_window_years"] == pytest.approx(3.0, abs=0.05)
    w5 = fred_data._mean_window(_series("2021-09-14", 1827))    # ≈ 5 years
    assert w5["mean_window_years"] == pytest.approx(5.0, abs=0.05)


def test_fetch_fred_data_emits_the_window_beside_every_five_yr_mean(monkeypatch):
    """A rolling-window HY series and a full-window NFCI series come back with
    their own windows, not a shared five-year label."""
    served = {
        "BAMLH0A0HYM2": _series("2023-09-12", 1096),
        "NFCI":         _series("2021-09-17", 261, freq="W-FRI"),
    }
    def fake_get(fred, series_id, observation_start, max_retries=3):
        if series_id not in served:
            raise RuntimeError("unavailable")
        return served[series_id]
    monkeypatch.setattr(fred_data, "_fred_get_with_retry", fake_get)
    monkeypatch.setattr(fred_data.time, "sleep", lambda *_: None)
    out = fred_data.fetch_fred_data(MagicMock())
    hy, nfci = out["hy_spread"], out["nfci"]
    assert "five_yr_mean" in hy and "five_yr_mean" in nfci
    assert hy["mean_window_start"] == "2023-09-12"
    assert hy["mean_window_years"] == pytest.approx(3.0, abs=0.05)
    assert nfci["mean_window_years"] == pytest.approx(5.0, abs=0.05)
    # a series that carries no five_yr_mean carries no window either
    no_mean = [k for k, v in out.items() if isinstance(v, dict) and "five_yr_mean" not in v]
    assert all("mean_window_years" not in out[k] for k in no_mean)


def test_quant_inputs_carry_the_window_too(monkeypatch):
    served = _series("2021-09-14", 1827)
    monkeypatch.setattr(fred_data, "_fred_get_with_retry", lambda *a, **k: served)
    monkeypatch.setattr(fred_data.time, "sleep", lambda *_: None)
    out = fred_data.fetch_quant_inputs(MagicMock())
    for entry in out.values():
        assert entry["mean_window_start"] == "2021-09-14"
        assert entry["mean_window_years"] == pytest.approx(5.0, abs=0.05)


def test_point_in_time_snapshot_mirrors_the_live_keys(monkeypatch):
    """`test_point_in_time.test_schema_matches_current` compares the historical
    and live key sets over the network; this is the offline half."""
    served = {sid: _series("2019-01-02", 1200) for sid in point_in_time.FRED_SERIES.values()}
    monkeypatch.setattr(point_in_time, "_fetch_alfred_series",
                        lambda sid, snap, start, key: served.get(sid))
    monkeypatch.setattr(point_in_time, "_fetch_market_snapshot", lambda *a, **k: {})
    monkeypatch.setenv("FRED_API_KEY", "x")
    snap = point_in_time.historical_snapshot(date(2022, 4, 15))
    hy = snap["hy_spread"]
    assert hy["mean_window_start"] == "2019-01-02"
    assert hy["mean_window_years"] == pytest.approx(3.3, abs=0.05)
