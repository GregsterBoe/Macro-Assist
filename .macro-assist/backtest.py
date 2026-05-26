"""
backtest.py — Walk-forward backtest harness.

run_backtest(start_date, end_date, strategy, output_dir) iterates day-by-day,
calls historical_snapshot(d) for the data knowable on that date, calls
strategy(snapshot) to produce predictions, and writes one JSON per date.

Baseline strategies (no API cost):
  strategy_neutral       — Neutral 50% on all assets
  strategy_random_walk   — continuation of prior day direction

Stub strategy (requires ANTHROPIC_API_KEY, see Phase 13.2):
  strategy_existing_pipeline

Scoring helper:
  score_backtest(output_dir) — computes directional accuracy from saved JSONs

Usage:
    from backtest import run_backtest, strategy_neutral, score_backtest
    from datetime import date
    from pathlib import Path

    result = run_backtest(date(2024,1,1), date(2024,3,31),
                          strategy_neutral, Path("results/backtest/neutral"))
    stats  = score_backtest(Path("results/backtest/neutral"))
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from point_in_time import historical_snapshot as _default_snapshot_fn
from score_predictions import (
    ASSET_TICKERS,
    SCORING_WINDOWS,
    BUFFER_DAYS,
    score_call,
    fetch_price_series,
    add_trading_days,
)

# ---------------------------------------------------------------------------
# Core harness
# ---------------------------------------------------------------------------

def run_backtest(
    start_date: date,
    end_date: date,
    strategy: Callable[[dict], dict],
    output_dir: Path,
    skip_weekends: bool = True,
    _snapshot_fn: Callable[[date], dict] | None = None,
) -> dict:
    """
    Walk-forward simulator.

    For each date d in [start_date, end_date]:
      1. Calls snapshot_fn(d) — defaults to historical_snapshot(d)
      2. Calls strategy(snapshot) -> predictions dict
      3. Writes {date, predictions} to output_dir/YYYY-MM-DD.json

    Returns {"dates_processed": int, "errors": list, "output_dir": str}.

    The optional _snapshot_fn parameter is provided for testing (inject a
    no-op stub to avoid ALFRED API calls when the strategy ignores the snapshot).
    """
    snapshot_fn = _snapshot_fn or _default_snapshot_fn
    output_dir  = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    current         = start_date
    dates_processed = []
    errors: list    = []

    while current <= end_date:
        if skip_weekends and current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        try:
            snapshot    = snapshot_fn(current)
            predictions = strategy(snapshot)
            out_path    = output_dir / f"{current.isoformat()}.json"
            out_path.write_text(
                json.dumps({"date": current.isoformat(), "predictions": predictions}, indent=2),
                encoding="utf-8",
            )
            dates_processed.append(current.isoformat())
        except Exception as exc:
            errors.append({"date": current.isoformat(), "error": str(exc)})

        current += timedelta(days=1)

    return {
        "dates_processed": len(dates_processed),
        "errors":          errors,
        "output_dir":      str(output_dir),
    }


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------

def _price_on(series: pd.Series | None, target: date) -> float | None:
    if series is None:
        return None
    for offset in range(5):
        ts = pd.Timestamp(target + timedelta(days=offset))
        if ts in series.index:
            return float(series.loc[ts])
    return None


def score_backtest(
    output_dir: Path,
    today: date | None = None,
) -> dict:
    """
    Score all prediction JSONs in output_dir.

    Returns nested dict:
      { window_label: { asset: {n, accuracy, directional} } }

    Uses the same scoring rules as score_predictions.py (flat threshold,
    Neutral = 0.5, directional accuracy excludes flat moves and Neutral calls).
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    output_dir = Path(output_dir)
    files = sorted(output_dir.glob("????-??-??.json"))
    if not files:
        return {}

    first_date = date.fromisoformat(files[0].stem)
    last_date  = date.fromisoformat(files[-1].stem)
    price_end  = min(last_date + timedelta(days=30), today)
    price_data = fetch_price_series(first_date, price_end)

    acc: dict[str, dict[str, list[float]]] = {
        label: {asset: [] for asset in ASSET_TICKERS}
        for label in SCORING_WINDOWS
    }

    for path in files:
        report_date = date.fromisoformat(path.stem)
        data        = json.loads(path.read_text(encoding="utf-8"))
        predictions = data.get("predictions", {})

        for label, n_days in SCORING_WINDOWS.items():
            eval_date = add_trading_days(report_date, n_days)
            if eval_date + timedelta(days=BUFFER_DAYS) > today:
                continue
            for asset in ASSET_TICKERS:
                pred = predictions.get(asset)
                if not pred:
                    continue
                entry = _price_on(price_data.get(asset), report_date)
                evalu = _price_on(price_data.get(asset), eval_date)
                sc    = score_call(entry, evalu, pred.get("bias", "Neutral"), asset)
                if sc is not None:
                    acc[label][asset].append(sc)

    result: dict = {}
    for label, assets in acc.items():
        window = {}
        for asset, scores in assets.items():
            if not scores:
                continue
            directional = [s for s in scores if s != 0.5]
            window[asset] = {
                "n":           len(scores),
                "accuracy":    round(sum(scores) / len(scores), 3),
                "directional": round(sum(directional) / len(directional), 3) if directional else None,
            }
        if window:
            result[label] = window

    return result


# ---------------------------------------------------------------------------
# Baseline strategies
# ---------------------------------------------------------------------------

def strategy_neutral(snapshot: dict) -> dict:
    """Returns Neutral 50% for every tracked asset. Ignores snapshot."""
    return {
        asset: {
            "bias":           "Neutral",
            "confidence":     50,
            "target_range":   [],
            "primary_driver": "N/A",
        }
        for asset in ASSET_TICKERS
    }


def strategy_random_walk(snapshot: dict) -> dict:
    """
    Continuation of the prior-day direction from the market snapshot.
    Falls back to Neutral when market data is absent.
    """
    market = snapshot.get("market", {})

    _asset_to_market_key = {
        "S&P 500":            "sp500",
        "Gold":               "gold",
        "WTI Oil":            "wti_oil",
        "10Y Treasury Yield": None,
        "DXY":                "dxy",
        "Bitcoin":            "bitcoin",
    }

    result: dict = {}
    for asset, mkey in _asset_to_market_key.items():
        if mkey and mkey in market:
            chg  = market[mkey].get("change_pct", 0)
            bias = "Bullish" if chg > 0 else ("Bearish" if chg < 0 else "Neutral")
        else:
            bias = "Neutral"
        result[asset] = {
            "bias":           bias,
            "confidence":     55,
            "target_range":   [],
            "primary_driver": "momentum",
        }

    return result


def strategy_existing_pipeline(snapshot: dict) -> dict:
    """
    Stub: wraps the current collect_and_analyze pipeline with historical data.
    Full implementation deferred to Phase 13.2 (end-to-end backtest).
    Requires ANTHROPIC_API_KEY and FRED_API_KEY.
    """
    raise NotImplementedError(
        "strategy_existing_pipeline requires wiring historical_snapshot data into "
        "the collect_and_analyze analysis functions. Planned for Phase 13.2."
    )
