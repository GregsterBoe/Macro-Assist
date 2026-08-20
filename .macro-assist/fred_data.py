"""FRED data fetching for the daily macro pipeline (net liquidity, retry/backoff)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from fredapi import Fred

from pipeline_common import (
    _log,
)


# ---------------------------------------------------------------------------
# FRED data
# ---------------------------------------------------------------------------

FRED_SERIES = {
    "fed_funds_rate":    "FEDFUNDS",
    "cpi":               "CPIAUCSL",
    "gdp":               "GDP",
    "unemployment":      "UNRATE",
    "m2":                "M2SL",
    "treasury_10y":      "DGS10",
    "treasury_2y":       "DGS2",
    "hy_spread":         "BAMLH0A0HYM2",        # HY corporate bond OAS spread (%)
    # baa_spread (BAA10Y) removed 2026-06-27 (WP-18.4 cleanup): its only consumer was the
    # retired HMM regime credit feature (KB-006); 0/78 model citations (KB-010). refit_models.py
    # keeps its own BAA10Y fetch for any future regime revival.
    "philly_fed_mfg":    "GACDFSA066MSFRBPHI",  # Philly Fed diffusion index; >0 expanding
    "real_yield_10y":    "DFII10",              # 10Y TIPS real yield (daily)
    "breakeven_10y":     "T10YIE",              # 10Y inflation breakeven rate (daily)
    # --- Phase 1 additions ---
    "fed_total_assets":  "WALCL",       # Fed balance sheet (millions USD; scaled ÷1000 → billions)
    "treasury_gen_acct": "WTREGEN",     # Treasury General Account (millions USD → ÷1000 = billions)
    "reverse_repo":      "RRPONTSYD",   # Overnight reverse repo (billions USD)
    "jobless_claims":    "ICSA",        # Initial jobless claims (weekly, thousands)
    "nfci":              "NFCI",        # Chicago Fed National Financial Conditions Index
}

# Keys whose raw Series are retained after the fetch loop for net-liquidity calculation
_NET_LIQ_KEYS = {"fed_total_assets", "treasury_gen_acct", "reverse_repo"}

# Release frequency per series — injected as metadata so Claude applies the right staleness threshold
FRED_SERIES_FREQUENCY = {
    "fed_funds_rate":    "monthly",    # FOMC sets rate at ~6-week intervals; data dated month-start
    "cpi":               "monthly",
    "gdp":               "quarterly",
    "unemployment":      "monthly",
    "m2":                "monthly",
    "treasury_10y":      "daily",
    "treasury_2y":       "daily",
    "hy_spread":         "daily",
    "philly_fed_mfg":    "monthly",
    "real_yield_10y":    "daily",
    "breakeven_10y":     "daily",
    "fed_total_assets":  "weekly",
    "treasury_gen_acct": "weekly",
    "reverse_repo":      "daily",
    "jobless_claims":    "weekly",
    "nfci":              "weekly",
}


def _compute_net_liquidity(raw_series: dict) -> dict | None:
    """
    Net Liquidity = (WALCL / 1000) - WTREGEN - RRPONTSYD  (all in billions USD).
    WALCL is reported in millions on FRED; the other two in billions.
    Resamples to weekly frequency so all three series align cleanly.
    Returns a signal dict or None if data is insufficient.
    """
    if not all(k in raw_series for k in _NET_LIQ_KEYS):
        return None

    combined = pd.DataFrame({
        "walcl": raw_series["fed_total_assets"] / 1000,    # millions → billions
        "tga":   raw_series["treasury_gen_acct"] / 1000,   # millions → billions (WTREGEN is in millions, same as WALCL)
        "rrp":   raw_series["reverse_repo"],                # already in billions
    }).resample("W").last().ffill().dropna()

    if len(combined) < 5:
        return None

    combined["nl"] = combined["walcl"] - combined["tga"] - combined["rrp"]
    nl = combined["nl"]

    current = float(nl.iloc[-1])
    # Sanity check: Fed net liquidity should be in the range $0–$20T (0–20,000 B).
    # Values outside this range indicate a unit mismatch in one of the component series.
    if not (0 <= current <= 20_000):
        _log("FRED", "WARN",
             f"net liquidity sanity check FAILED: {current:.1f}B — possible unit mismatch; "
             f"walcl={combined['walcl'].iloc[-1]:.0f}B, tga={combined['tga'].iloc[-1]:.0f}B, "
             f"rrp={combined['rrp'].iloc[-1]:.0f}B")
        return None
    wow_ref = float(nl.iloc[-2])
    mom_ref = float(nl.iloc[-5]) if len(nl) >= 5 else None

    wow_pct = round(((current - wow_ref) / abs(wow_ref)) * 100, 2) if wow_ref != 0 else None
    mom_pct = round(((current - mom_ref) / abs(mom_ref)) * 100, 2) if mom_ref and mom_ref != 0 else None

    # 4-week rolling mean trend is more stable than single-week WoW
    roll4 = nl.rolling(4).mean().dropna()
    if len(roll4) >= 2:
        trend = "Expanding" if float(roll4.iloc[-1]) > float(roll4.iloc[-2]) else "Contracting"
    else:
        trend = "Expanding" if (wow_pct or 0) > 0 else "Contracting"
    parts  = [trend]
    if wow_pct is not None:
        parts.append(f"{'+' if wow_pct >= 0 else ''}{wow_pct:.1f}% WoW")
    if mom_pct is not None:
        parts.append(f"{'+' if mom_pct >= 0 else ''}{mom_pct:.1f}% MoM")

    # Cap at today — weekly resampling (resample("W")) assigns period-end Sunday,
    # which places the date in the future when the pipeline runs mid-week.
    as_of = min(combined.index[-1].date(), datetime.now(timezone.utc).date())
    return {
        "value_bn":      round(current, 1),
        "wow_pct":       wow_pct,
        "mom_pct":       mom_pct,
        "trend":         trend,
        "trend_summary": ", ".join(parts),
        "date":          as_of.strftime("%Y-%m-%d"),
    }


_FRED_RATE_LIMIT_KEYWORDS = ("too many requests", "rate limit", "429")
_FRED_INTER_REQUEST_DELAY = 0.6    # seconds between FRED calls — 16 series = ~10s, safely under 120/min


def _fred_get_with_retry(fred: Fred, series_id: str, observation_start: str,
                         max_retries: int = 3) -> pd.Series:
    """Fetch a FRED series; retries with exponential backoff on rate-limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return fred.get_series(series_id, observation_start=observation_start).dropna()
        except Exception as exc:
            is_rate_limit = any(kw in str(exc).lower() for kw in _FRED_RATE_LIMIT_KEYWORDS)
            if is_rate_limit and attempt < max_retries:
                wait = 10 * (2 ** attempt)   # 10s → 20s → 40s
                _log("FRED", "WARN",
                     f"{series_id} rate-limited — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise


def fetch_fred_data(fred: Fred) -> dict:
    today_date = datetime.now(timezone.utc).date()
    data: dict = {}
    _raw_series: dict = {}   # raw Series retained for net-liquidity calculation
    _fetched, _failed, _stale_30d = 0, [], []

    for name, series_id in FRED_SERIES.items():
        try:
            observation_start = (datetime.now(timezone.utc).date() - timedelta(days=365 * 5)).isoformat()
            series = _fred_get_with_retry(fred, series_id, observation_start)
            time.sleep(_FRED_INTER_REQUEST_DELAY)
        except Exception as e:
            _log("FRED", "WARN", f"series {series_id} ({name}) unavailable: {e}")
            _failed.append(name)
            continue
        latest = series.iloc[-1]
        prev   = series.iloc[-2] if len(series) > 1 else latest
        latest_date = series.index[-1].date()
        data[name] = {
            "value":      round(float(latest), 3),
            "prev":       round(float(prev), 3),
            "date":       latest_date.strftime("%Y-%m-%d"),
            "days_stale": (today_date - latest_date).days,
            "frequency":  FRED_SERIES_FREQUENCY.get(name, "unknown"),
        }
        _fetched += 1
        if data[name]["days_stale"] > 30:
            _stale_30d.append(f"{name}({data[name]['days_stale']}d)")
        # Year-over-year for CPI and M2
        if name in ("cpi", "m2") and len(series) >= 13:
            year_ago = series.iloc[-13]
            data[name]["yoy_pct"] = round(((latest - year_ago) / year_ago) * 100, 2)
        # 5-year mean YoY for CPI and M2
        if name in ("cpi", "m2") and len(series) >= 25:
            yoy_series = series.pct_change(12).dropna() * 100
            if len(yoy_series) >= 12:
                data[name]["five_yr_mean_yoy"] = round(float(yoy_series.mean()), 2)
        # 5-year mean of raw value for spread/index/rate series
        # Note: philly_fed_mfg mean includes COVID-era extremes (~-56 in Apr 2020)
        # Note: jobless_claims 5yr window (starts ~2021) excludes COVID spike — post-crisis baseline
        if name in ("hy_spread", "philly_fed_mfg", "real_yield_10y",
                    "breakeven_10y", "nfci", "jobless_claims") and len(series) >= 12:
            data[name]["five_yr_mean"] = round(float(series.mean()), 3)
            data[name]["vs_mean"]      = round(float(latest) - float(series.mean()), 3)
        # MoM point change for diffusion indices — absolute swing reveals regime shifts
        # that level-vs-mean comparisons miss (e.g. -0.4 looks mild; -27pt drop from +26.7 is a shock)
        if name == "philly_fed_mfg" and len(series) >= 2:
            data[name]["mom_change"] = round(float(latest) - float(prev), 1)
        # WoW % change for jobless claims (trend direction matters more than level)
        if name == "jobless_claims" and len(series) >= 2:
            wow = round(((float(latest) - float(prev)) / float(prev)) * 100, 2)
            data[name]["wow_pct"] = wow
            data[name]["trend"]   = "Rising" if wow > 0 else "Falling"
        # Retain raw series for net-liquidity components
        if name in _NET_LIQ_KEYS:
            _raw_series[name] = series

    _stale_str = f" | stale>30d: {', '.join(_stale_30d)}" if _stale_30d else ""
    _fail_str  = f" | missing: {', '.join(_failed)}"      if _failed    else ""
    _log("FRED", "WARN" if _failed else "OK",
         f"{_fetched}/{len(FRED_SERIES)} series{_fail_str}{_stale_str}")

    if "treasury_10y" in data and "treasury_2y" in data:
        data["yield_curve_spread"] = round(
            data["treasury_10y"]["value"] - data["treasury_2y"]["value"], 3
        )
    else:
        _log("FRED", "WARN", "yield_curve_spread skipped — treasury data incomplete")

    net_liq = _compute_net_liquidity(_raw_series)
    if net_liq:
        data["net_liquidity"] = net_liq

    return data
