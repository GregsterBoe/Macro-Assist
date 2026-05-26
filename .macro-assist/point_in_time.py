"""
point_in_time.py — ALFRED vintage FRED data for point-in-time backtesting.

Returns FRED + market data as knowable on a given historical date, using
ALFRED (FRED's archival API) to avoid look-ahead bias.

ALFRED endpoint:
  https://api.stlouisfed.org/fred/series/observations
    ?series_id=X&realtime_start=YYYY-MM-DD&realtime_end=YYYY-MM-DD&...

Usage:
    from point_in_time import historical_snapshot
    snap = historical_snapshot(date(2024, 6, 1))
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Import shared constants from the main pipeline
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from collect_and_analyze import (
    FRED_SERIES,
    FRED_SERIES_FREQUENCY,
    _NET_LIQ_KEYS,
    MARKET_TICKERS,
)

ALFRED_MIN_DATE = date(1997, 1, 1)
_FRED_API_BASE  = "https://api.stlouisfed.org/fred/series/observations"


# ---------------------------------------------------------------------------
# Net-liquidity helper (identical logic to collect_and_analyze, but caps
# the as_of date at snapshot_date rather than today)
# ---------------------------------------------------------------------------

def _compute_net_liquidity_pit(raw_series: dict, snapshot_date: date) -> dict | None:
    if not all(k in raw_series for k in _NET_LIQ_KEYS):
        return None

    combined = pd.DataFrame({
        "walcl": raw_series["fed_total_assets"] / 1000,
        "tga":   raw_series["treasury_gen_acct"] / 1000,
        "rrp":   raw_series["reverse_repo"],
    }).resample("W").last().ffill().dropna()

    if len(combined) < 5:
        return None

    combined["nl"] = combined["walcl"] - combined["tga"] - combined["rrp"]
    nl = combined["nl"]

    current = float(nl.iloc[-1])
    if not (0 <= current <= 20_000):
        return None

    wow_ref = float(nl.iloc[-2])
    mom_ref = float(nl.iloc[-5]) if len(nl) >= 5 else None
    wow_pct = round(((current - wow_ref) / abs(wow_ref)) * 100, 2) if wow_ref != 0 else None
    mom_pct = round(((current - mom_ref) / abs(mom_ref)) * 100, 2) if mom_ref and mom_ref != 0 else None

    roll4 = nl.rolling(4).mean().dropna()
    if len(roll4) >= 2:
        trend = "Expanding" if float(roll4.iloc[-1]) > float(roll4.iloc[-2]) else "Contracting"
    else:
        trend = "Expanding" if (wow_pct or 0) > 0 else "Contracting"

    parts = [trend]
    if wow_pct is not None:
        parts.append(f"{'+' if wow_pct >= 0 else ''}{wow_pct:.1f}% WoW")
    if mom_pct is not None:
        parts.append(f"{'+' if mom_pct >= 0 else ''}{mom_pct:.1f}% MoM")

    as_of = min(combined.index[-1].date(), snapshot_date)
    return {
        "value_bn":      round(current, 1),
        "wow_pct":       wow_pct,
        "mom_pct":       mom_pct,
        "trend":         trend,
        "trend_summary": ", ".join(parts),
        "date":          as_of.strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------------------
# ALFRED fetch
# ---------------------------------------------------------------------------

def _fetch_alfred_series(
    series_id: str,
    snapshot_date: date,
    observation_start: date,
    api_key: str,
) -> pd.Series | None:
    """Return a pandas Series of FRED observations as published on snapshot_date."""
    params = {
        "series_id":         series_id,
        "realtime_start":    snapshot_date.isoformat(),
        "realtime_end":      snapshot_date.isoformat(),
        "observation_start": observation_start.isoformat(),
        "file_type":         "json",
        "api_key":           api_key,
    }
    try:
        resp = requests.get(_FRED_API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
    except Exception:
        return None

    valid = [
        (obs["date"], float(obs["value"]))
        for obs in observations
        if obs.get("value") not in (".", "", None)
    ]
    if not valid:
        return None

    return pd.Series(
        {pd.Timestamp(d): v for d, v in valid}
    ).sort_index()


# ---------------------------------------------------------------------------
# Market data (yfinance — prices don't revise materially)
# ---------------------------------------------------------------------------

def _fetch_market_snapshot(snapshot_date: date) -> dict:
    start = (snapshot_date - timedelta(days=90)).isoformat()
    end   = (snapshot_date + timedelta(days=1)).isoformat()
    market: dict = {}

    for name, ticker in MARKET_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(start=start, end=end)
            if hist.empty or len(hist) < 2:
                continue
            close = hist["Close"]
            c, p  = float(close.iloc[-1]), float(close.iloc[-2])
            market[name] = {
                "price":      round(c, 2),
                "change_pct": round(((c - p) / p) * 100, 2),
                "date":       hist.index[-1].date().isoformat(),
            }
        except Exception:
            continue

    return market


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def historical_snapshot(snapshot_date: date) -> dict:
    """
    Return FRED data as knowable on snapshot_date (via ALFRED vintage API)
    plus yfinance market prices as of that date.

    Return structure mirrors fetch_fred_data() output, with two additions:
      'market'        — price_data dict (same shape as fetch_market_data()[0])
      'snapshot_date' — ISO string of the requested date

    Raises ValueError for snapshot_date before 1997-01-01 (ALFRED coverage limit).
    """
    if snapshot_date < ALFRED_MIN_DATE:
        raise ValueError(
            f"snapshot_date {snapshot_date} predates ALFRED coverage "
            f"(minimum supported date: {ALFRED_MIN_DATE})"
        )

    api_key           = os.environ["FRED_API_KEY"]
    observation_start = snapshot_date - timedelta(days=365 * 5)

    data: dict       = {}
    raw_series: dict = {}

    for name, series_id in FRED_SERIES.items():
        series = _fetch_alfred_series(series_id, snapshot_date, observation_start, api_key)
        if series is None or series.empty:
            continue

        latest      = float(series.iloc[-1])
        prev        = float(series.iloc[-2]) if len(series) > 1 else latest
        latest_date = series.index[-1].date()

        data[name] = {
            "value":      round(latest, 3),
            "prev":       round(prev, 3),
            "date":       latest_date.isoformat(),
            "days_stale": (snapshot_date - latest_date).days,
            "frequency":  FRED_SERIES_FREQUENCY.get(name, "unknown"),
        }

        if name in ("cpi", "m2") and len(series) >= 13:
            year_ago = float(series.iloc[-13])
            data[name]["yoy_pct"] = round(((latest - year_ago) / year_ago) * 100, 2)
        if name in ("cpi", "m2") and len(series) >= 25:
            yoy_s = series.pct_change(12).dropna() * 100
            if len(yoy_s) >= 12:
                data[name]["five_yr_mean_yoy"] = round(float(yoy_s.mean()), 2)
        if name in ("hy_spread", "philly_fed_mfg", "real_yield_10y", "breakeven_10y",
                    "nfci", "jobless_claims") and len(series) >= 12:
            data[name]["five_yr_mean"] = round(float(series.mean()), 3)
            data[name]["vs_mean"]      = round(latest - float(series.mean()), 3)
        if name == "jobless_claims" and len(series) >= 2:
            wow = round(((latest - prev) / prev) * 100, 2)
            data[name]["wow_pct"] = wow
            data[name]["trend"]   = "Rising" if wow > 0 else "Falling"

        if name in _NET_LIQ_KEYS:
            raw_series[name] = series

    if "treasury_10y" in data and "treasury_2y" in data:
        data["yield_curve_spread"] = round(
            data["treasury_10y"]["value"] - data["treasury_2y"]["value"], 3
        )

    net_liq = _compute_net_liquidity_pit(raw_series, snapshot_date)
    if net_liq:
        data["net_liquidity"] = net_liq

    data["market"]        = _fetch_market_snapshot(snapshot_date)
    data["snapshot_date"] = snapshot_date.isoformat()
    return data
