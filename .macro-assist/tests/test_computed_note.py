"""
v2.2 (ADR-0024) — the daily note with no model in it.

The note became the Fragility Monitor, the volatility-targeting dial and the
conditional distributions, all computed, and the run makes no LLM call unless
`NOTE_ANALYSIS=llm` asks for one. These tests pin:

  1. The switch defaults to off, and off means `analyze_with_claude` is never
     reached — the whole point of the change is the cost.
  2. The dial is typical ÷ forecast, capped at 1, rounded to 5 %, and logged
     with the reading it came from.
  3. The computed note keeps what its readers parse: the `### 5-Day Outlook`
     heading (`note_is_post_cut`) and the frontmatter keys — and says no model ran.

The quant reading below is copied from `results/quant_context_log/2026-10-01.jsonl`
(convention #10); the dial's `typical_vol` / `exposure` are that day's values,
computed on the live 5y histories when this file was written.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_and_analyze as ca
import quant_context as qc
from pipeline_config import note_analysis_on
from portfolio.rebalance import note_is_post_cut
from vol_forecast import HAR_MIN_RETURNS

TODAY = datetime(2026, 10, 1, 6, 25, tzinfo=timezone.utc)

QUANT_RAW = {
    "date": "2026-10-01",
    "vol_forecasts": {
        "SP500":   {"forecast_daily_vol": 12.47, "percentile_60d": 76.7, "vix": 16.34, "vrp": 3.89,
                    "vrp_interpretation": "Normal", "typical_vol": 16.99, "exposure": 1.0},
        "Gold":    {"forecast_daily_vol": 22.75, "percentile_60d": 73.3, "typical_vol": 19.17, "exposure": 0.85},
        "WTI Oil": {"forecast_daily_vol": 42.82, "percentile_60d": 66.7, "typical_vol": 41.74, "exposure": 0.95},
        "Bitcoin": {"forecast_daily_vol": 36.39, "percentile_60d": 85.0, "typical_vol": 42.6, "exposure": 1.0},
    },
    "conditional": {
        "bucket": "NFCI:mid|YC:positive|CREDIT:tight",
        "distributions": {
            "SP500_5d":   {"n": 821, "p10": -2.23, "p25": -0.96, "p50": 0.32, "p75": 1.3, "p90": 2.25},
            "Gold_5d":    {"n": 821, "p10": -2.82, "p25": -1.14, "p50": 0.48, "p75": 1.92, "p90": 3.31},
            "WTI Oil_5d": {"n": 821, "p10": -5.73, "p25": -2.53, "p50": 0.43, "p75": 3.14, "p90": 7.02},
            "UST10Y_5d":  {"n": 821, "p10": -10.3, "p25": -4.9, "p50": 0.8, "p75": 6.8, "p90": 12.4},
            "DXY_5d":     {"n": 821, "p10": -0.93, "p25": -0.48, "p50": 0.05, "p75": 0.59, "p90": 1.08},
            "Bitcoin_5d": {"n": 733, "p10": -8.94, "p25": -4.49, "p50": -0.0, "p75": 3.94, "p90": 8.27},
        },
    },
    "fragility": {"composite": 16.12, "label": "Resilient", "trend": "Falling",
                  "components": {"variance_trend": 26.08, "correlation": 39.34, "absorption": 60.13,
                                 "vix_term": 0.0, "autocorr": 57.91},
                  "weights": {"variance_trend": 0.529, "correlation": 0.059, "absorption": 0.0,
                              "vix_term": 0.412, "autocorr": 0.0},
                  "degraded": [], "mode": "log"},
    "fragility_or": {"asof": "2026-09-30", "flag": False, "fired_channels": [], "q": 0.9,
                     "channels": {"comp": {"value": 16.0972, "threshold": 56.3288, "fired": False, "percentile": 0.236},
                                  "AR": {"value": 23.741, "threshold": 97.3429, "fired": False, "percentile": 0.468},
                                  "TURB": {"value": 3.782, "threshold": 11.4873, "fired": False, "percentile": 0.268}},
                     "mode": "show"},
}

FRED = {
    "fed_funds_rate": {"value": 3.63, "date": "2026-08-01"},
    "treasury_10y": {"value": 5.26, "date": "2026-09-29"},
    "treasury_2y": {"value": 4.89, "date": "2026-09-29"},
    "yield_curve_spread": 0.37,
    "cpi": {"value": 330.0, "yoy_pct": 3.71, "date": "2026-08-01"},
    "unemployment": {"value": 4.1, "date": "2026-08-01"},
    "m2": {"value": 22000.0, "yoy_pct": 5.66, "date": "2026-08-01"},
}
MARKET = {"sp500": {"price": 7651.54, "change_pct": -0.25}, "vix": {"price": 16.34, "change_pct": 1.87},
          "gold": {"price": 4219.80, "change_pct": 0.79}}


# ---------------------------------------------------------------------------
# 1. The switch
# ---------------------------------------------------------------------------

class TestSwitch:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTE_ANALYSIS", raising=False)
        assert note_analysis_on() is False

    @pytest.mark.parametrize("v", ["llm", "on", " LLM "])
    def test_llm_restores_the_model(self, monkeypatch, v):
        monkeypatch.setenv("NOTE_ANALYSIS", v)
        assert note_analysis_on() is True

    @pytest.mark.parametrize("v", ["off", "", "yes-please", "0"])
    def test_anything_else_is_off(self, monkeypatch, v):
        monkeypatch.setenv("NOTE_ANALYSIS", v)
        assert note_analysis_on() is False

    def test_off_never_reaches_the_model(self, monkeypatch, tmp_path):
        """A full `main()` with every fetch stubbed: the note is written and the
        LLM entry point is never called."""
        monkeypatch.delenv("NOTE_ANALYSIS", raising=False)
        monkeypatch.setenv("FRED_API_KEY", "x")
        out = tmp_path / "note.md"

        def boom(*a, **k):
            raise AssertionError("analyze_with_claude called with NOTE_ANALYSIS off")

        stubs = {
            "Fred": lambda **k: None, "fetch_fred_data": lambda f: dict(FRED),
            "fetch_quant_inputs": lambda f: {}, "fetch_market_data": lambda: (dict(MARKET), {}),
            "fetch_vol_histories": lambda: {}, "validate_data": lambda *a, **k: None,
            "write_fred_snapshot": lambda *a, **k: None, "detect_notable_moves": lambda *a: "",
            "fetch_sector_data": lambda: {}, "get_output_path": lambda t: out,
            "_check_fomc_dates_expiry": lambda t: None, "analyze_with_claude": boom,
            "VAULT_ROOT": tmp_path,
        }
        for k, v in stubs.items():
            monkeypatch.setattr(ca, k, v)
        monkeypatch.setattr(qc, "build_quant_context", lambda *a, **k: "")
        monkeypatch.setattr(sys, "argv", ["collect_and_analyze.py", "--asof", "2026-10-01"])
        ca.main()
        text = out.read_text()
        assert "model: none" in text and "### 5-Day Outlook" in text


# ---------------------------------------------------------------------------
# 2. The dial
# ---------------------------------------------------------------------------

class TestDial:
    @pytest.mark.parametrize("forecast,typical,want", [
        (12.47, 16.99, 1.0),     # calmer than usual: never more than normal
        (22.75, 19.17, 0.85),    # 0.843 → 0.85
        (40.0, 20.0, 0.5),
        (100.0, 10.0, 0.1),
    ])
    def test_typical_over_forecast_capped_and_rounded(self, forecast, typical, want):
        assert qc.vol_target_exposure(forecast, typical) == pytest.approx(want)

    @pytest.mark.parametrize("forecast,typical", [(0.0, 15.0), (15.0, 0.0), (float("nan"), 15.0)])
    def test_no_reading_is_no_cut(self, forecast, typical):
        assert qc.vol_target_exposure(forecast, typical) == 1.0

    def test_typical_vol_is_on_the_har_scale(self):
        r = pd.Series(np.full(HAR_MIN_RETURNS, 0.01))
        assert qc.typical_vol(r) == pytest.approx(0.01 * np.sqrt(252) * 100)

    def test_typical_vol_refuses_a_short_history(self):
        assert qc.typical_vol(pd.Series(np.full(HAR_MIN_RETURNS - 1, 0.01))) is None

    def test_the_dial_is_logged_with_its_forecast(self):
        rng = np.random.default_rng(0)
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, HAR_MIN_RETURNS + 50))))
        raw = qc.collect_quant_raw({}, TODAY.date(), vol_histories={"sp500": close})
        v = raw["vol_forecasts"]["SP500"]
        assert v["exposure"] == qc.vol_target_exposure(v["forecast_daily_vol"], v["typical_vol"])
        assert 0.0 < v["exposure"] <= 1.0


# ---------------------------------------------------------------------------
# 3. The note
# ---------------------------------------------------------------------------

class TestComputedNote:
    def test_dial_block_renders_every_logged_asset(self):
        block = qc.build_vol_target_block(QUANT_RAW)
        assert "### Volatility Targeting" in block
        assert "| Gold | 22.8% | 19.2% | **85%** of normal |" in block
        assert "not a forecast" in block

    def test_dial_block_is_empty_without_a_dial(self):
        assert qc.build_vol_target_block({"vol_forecasts": {"SP500": {"forecast_daily_vol": 12.0}}}) == ""
        assert qc.build_vol_target_block(None) == ""

    def test_outlook_lists_every_asset_and_marks_the_gaps(self):
        raw = {"conditional": {"bucket": "b", "distributions": {"SP500_5d": QUANT_RAW["conditional"]["distributions"]["SP500_5d"]}}}
        block = qc.build_outlook_block(raw, "2026-10-08")
        assert "| S&P 500 | median +0.3%" in block
        assert "| Bitcoin | no base rate in this bucket |" in block
        assert block.endswith("Review date: 2026-10-08")

    def test_note_has_no_model_and_says_so(self):
        note = ca.build_note(FRED, MARKET, ca.computed_analysis(QUANT_RAW, TODAY), TODAY,
                             quant_raw=QUANT_RAW, llm=False)
        assert "model: none" in note and "profile: none" in note
        assert "no model (v2.2, ADR-0024)" in note
        for gone in ("Executive Summary", "Portfolio Risk", "Primary Driver", "Target Range"):
            assert gone not in note
        order = [note.index(h) for h in ("### Fragility Monitor", "### Volatility Targeting",
                                         "### 5-Day Outlook", "## Data Snapshot")]
        assert order == sorted(order)

    def test_readers_still_see_a_post_cut_note(self):
        note = ca.build_note(FRED, MARKET, ca.computed_analysis(QUANT_RAW, TODAY), TODAY,
                             quant_raw=QUANT_RAW, llm=False)
        assert note_is_post_cut(note)
        for key in ("agent_version:", "conviction_floor:", "base_rate_first:", "prune_rules:"):
            assert key in note
