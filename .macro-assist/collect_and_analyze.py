"""
Macro-Assist: Daily macro intelligence pipeline.

Fetches FRED + market data, runs Claude analysis, writes a dated
companion note into the Obsidian vault (Journal/YYYY/MM-Month/).

Expects env vars: FRED_API_KEY, ANTHROPIC_API_KEY
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import pandas as pd
import requests
import yfinance as yf
from fredapi import Fred

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# VAULT_ROOT can be overridden via env var (used by GitHub Actions).
# Falls back to the parent of .macro-assist/ for local runs.
VAULT_ROOT     = Path(os.environ.get("VAULT_ROOT", Path(__file__).resolve().parent.parent))
PROMPTS_DIR    = Path(__file__).resolve().parent / "prompts"
ACCURACY_JSON  = Path(__file__).resolve().parent / "data" / "accuracy_summary.json"
REPO_ROOT      = Path(__file__).resolve().parent.parent
POSITIONS_CSV  = Path(os.environ.get("POSITIONS_CSV", REPO_ROOT / "data" / "tr_positions.csv"))

# ---------------------------------------------------------------------------
# YouTube channel configuration
# Each entry: (channel_id, display_name)
# Run: python .macro-assist/youtube_data.py --resolve <channel_url>
# to find the channel ID for any channel.
# ---------------------------------------------------------------------------

YOUTUBE_CHANNELS = [
    ("UCOHxDwCcOzBaLkeTazanwcw", "Bravos Research"),
]


def get_output_path(today: datetime) -> Path:
    """Return the output path, creating parent dirs as needed."""
    year = today.strftime("%Y")
    month_folder = today.strftime("%m-%B")          # e.g. "03-March"
    filename = today.strftime("%Y-%m-%d-%A") + "-macro.md"
    path = VAULT_ROOT / "Economy" / year / month_folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def next_review_date(today: datetime) -> str:
    """Return the date 5 business days from today (for prediction tracking)."""
    d, count = today, 0
    while count < 5:
        d += timedelta(days=1)
        if d.weekday() < 5:   # Mon–Fri
            count += 1
    return d.strftime("%Y-%m-%d")


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
    "philly_fed_mfg":    "GACDFSA066MSFRBPHI",  # Philly Fed diffusion index; >0 expanding
    "real_yield_10y":    "DFII10",              # 10Y TIPS real yield (daily)
    "breakeven_10y":     "T10YIE",              # 10Y inflation breakeven rate (daily)
    # --- Phase 1 additions ---
    "fed_total_assets":  "WALCL",       # Fed balance sheet (millions USD; scaled ÷1000 → billions)
    "treasury_gen_acct": "WTREGEN",     # Treasury General Account (billions USD)
    "reverse_repo":      "RRPONTSYD",   # Overnight reverse repo (billions USD)
    "jobless_claims":    "ICSA",        # Initial jobless claims (weekly, thousands)
    "nfci":              "NFCI",        # Chicago Fed National Financial Conditions Index
}

# Keys whose raw Series are retained after the fetch loop for net-liquidity calculation
_NET_LIQ_KEYS = {"fed_total_assets", "treasury_gen_acct", "reverse_repo"}


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
        "walcl": raw_series["fed_total_assets"] / 1000,   # millions → billions
        "tga":   raw_series["treasury_gen_acct"],
        "rrp":   raw_series["reverse_repo"],
    }).resample("W").last().ffill().dropna()

    if len(combined) < 5:
        return None

    combined["nl"] = combined["walcl"] - combined["tga"] - combined["rrp"]
    nl = combined["nl"]

    current = float(nl.iloc[-1])
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

    return {
        "value_bn":      round(current, 1),
        "wow_pct":       wow_pct,
        "mom_pct":       mom_pct,
        "trend":         trend,
        "trend_summary": ", ".join(parts),
        "date":          combined.index[-1].strftime("%Y-%m-%d"),
    }


def fetch_fred_data(fred: Fred) -> dict:
    today_date = datetime.now(timezone.utc).date()
    data: dict = {}
    _raw_series: dict = {}   # raw Series retained for net-liquidity calculation

    for name, series_id in FRED_SERIES.items():
        try:
            observation_start = (datetime.now(timezone.utc).date() - timedelta(days=365 * 5)).isoformat()
            series = fred.get_series(series_id, observation_start=observation_start).dropna()
        except Exception as e:
            print(f"  Warning: FRED series {series_id} ({name}) unavailable: {e}")
            continue
        latest = series.iloc[-1]
        prev   = series.iloc[-2] if len(series) > 1 else latest
        latest_date = series.index[-1].date()
        data[name] = {
            "value":      round(float(latest), 3),
            "prev":       round(float(prev), 3),
            "date":       latest_date.strftime("%Y-%m-%d"),
            "days_stale": (today_date - latest_date).days,
        }
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
        if name in ("hy_spread", "philly_fed_mfg", "real_yield_10y", "breakeven_10y",
                    "nfci", "jobless_claims") and len(series) >= 12:
            data[name]["five_yr_mean"] = round(float(series.mean()), 3)
            data[name]["vs_mean"]      = round(float(latest) - float(series.mean()), 3)
        # WoW % change for jobless claims (trend direction matters more than level)
        if name == "jobless_claims" and len(series) >= 2:
            wow = round(((float(latest) - float(prev)) / float(prev)) * 100, 2)
            data[name]["wow_pct"] = wow
            data[name]["trend"]   = "Rising" if wow > 0 else "Falling"
        # Retain raw series for net-liquidity components
        if name in _NET_LIQ_KEYS:
            _raw_series[name] = series

    data["yield_curve_spread"] = round(
        data["treasury_10y"]["value"] - data["treasury_2y"]["value"], 3
    )

    net_liq = _compute_net_liquidity(_raw_series)
    if net_liq:
        data["net_liquidity"] = net_liq

    return data


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

MARKET_TICKERS = {
    "sp500":   "^GSPC",
    "nasdaq":  "^IXIC",
    "gold":    "GC=F",
    "wti_oil": "CL=F",
    "vix":     "^VIX",
    "dxy":     "DX-Y.NYB",
    "vix3m":   "^VIX3M",   # 3-month VIX; used for term structure ratio only
    "bitcoin": "BTC-USD",  # added Phase 2: enables technical indicators + direct price context
}

MARKET_LABELS = {
    "sp500":   "S&P 500",
    "nasdaq":  "Nasdaq",
    "gold":    "Gold",
    "wti_oil": "WTI Oil",
    "vix":     "VIX",
    "dxy":     "DXY",
    "bitcoin": "Bitcoin",
    # vix3m intentionally omitted — it's a derived-ratio input, not a standalone snapshot row
}

SECTOR_TICKERS = {
    "xle": "XLE",  # Energy
    "xlk": "XLK",  # Technology
    "xlf": "XLF",  # Financials
    "xli": "XLI",  # Industrials
    "xly": "XLY",  # Consumer Discretionary
}

SECTOR_LABELS = {
    "xle": "Energy (XLE)",
    "xlk": "Technology (XLK)",
    "xlf": "Financials (XLF)",
    "xli": "Industrials (XLI)",
    "xly": "Consumer Discretionary (XLY)",
}

# Tickers excluded from the notable-move detector (volatility measures are circular to σ-test)
_NOTABLE_MOVE_EXCLUDE = {"vix", "vix3m"}
# Minimum absolute % threshold per asset to avoid false flags in low-volatility windows
_NOTABLE_MOVE_MIN_ABS: dict = {
    "sp500": 1.5, "nasdaq": 1.5, "gold": 1.5, "wti_oil": 2.0, "dxy": 0.8, "bitcoin": 3.0,
}

# Assets for which technical indicators (RSI, 50dMA, Z-score) are computed — Phase 2
_TECHNICAL_ASSETS = {"sp500", "nasdaq", "gold", "wti_oil", "dxy", "bitcoin"}
# sp500 50dMA already computed from 1y history in fetch_equity_momentum — skip recompute from 90d
_SKIP_MA50 = {"sp500"}


def _ticker_snapshot(ticker: str, period: str) -> tuple[dict | None, object]:
    """
    Fetch latest close and daily % change for a single ticker.
    Returns (snapshot_dict, close_series). Either may be None on failure.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty or len(hist) < 2:
            print(f"  Warning: no data for {ticker}, skipping.")
            return None, None
        close = hist["Close"]
        c, p  = float(close.iloc[-1]), float(close.iloc[-2])
        return {
            "price":      round(c, 2),
            "change_pct": round(((c - p) / p) * 100, 2),
            "date":       hist.index[-1].strftime("%Y-%m-%d"),
        }, close
    except Exception as e:
        print(f"  Warning: failed to fetch {ticker}: {e}")
        return None, None


def fetch_equity_momentum() -> dict | None:
    """Fetch SPX 50dma vs 200dma and 1-month return for structural trend context."""
    try:
        hist = yf.Ticker("^GSPC").history(period="1y")
        if hist.empty or len(hist) < 50:
            print("  Warning: insufficient SPX history for momentum calculation.")
            return None
        close = hist["Close"]
        price = float(close.iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1])
        one_month_return = round(
            ((price - float(close.iloc[-21])) / float(close.iloc[-21])) * 100, 2
        ) if len(close) >= 21 else None
        result: dict = {"ma50": round(ma50, 2), "one_month_return": one_month_return}
        if len(close) >= 200:
            ma200 = float(close.rolling(200).mean().iloc[-1])
            result["ma200"] = round(ma200, 2)
            if price > ma50 > ma200:
                result["trend"] = "uptrend"
            elif price < ma50 < ma200:
                result["trend"] = "downtrend"
            else:
                result["trend"] = "mixed"
        return result
    except Exception as e:
        print(f"  Warning: failed to fetch SPX momentum: {e}")
        return None


def fetch_market_data() -> tuple[dict, dict]:
    """Return (price_data, histories) where histories maps name → Close price Series."""
    data: dict = {}
    histories: dict = {}
    for name, ticker in MARKET_TICKERS.items():
        snapshot, close = _ticker_snapshot(ticker, "90d")  # 90d needed for RSI/50dMA/Z-score
        if snapshot:
            data[name] = snapshot
            histories[name] = close

    if not data:
        sys.exit("Market holiday or all tickers unavailable — no market data fetched. Skipping report.")

    momentum = fetch_equity_momentum()
    if momentum and "sp500" in data:
        data["sp500"]["momentum"] = momentum

    return data, histories


def fetch_sector_data() -> dict:
    """Fetch daily close and % change for sector ETFs."""
    data = {}
    for name, ticker in SECTOR_TICKERS.items():
        snapshot, _ = _ticker_snapshot(ticker, "5d")
        if snapshot:
            data[name] = snapshot
    return data


# ---------------------------------------------------------------------------
# COT positioning data (Phase 3 — Nasdaq Data Link / CFTC)
# ---------------------------------------------------------------------------

# CFTC commodity codes for Nasdaq Data Link CFTC dataset
# Source: https://data.nasdaq.com/data/CFTC
COT_SERIES = {
    "WTI Oil": "CFTC/067651_FUT_ALL_CR",
    "Gold":    "CFTC/088691_FUT_ALL_CR",
}


def fetch_cot_data() -> str:
    """
    Fetch CFTC Commitments of Traders net non-commercial positioning for
    WTI Crude and Gold via Nasdaq Data Link (free tier, ~weekly frequency).
    Returns a ## COT Positioning Markdown block, or empty string if the
    API key is absent or any fetch fails. The pipeline never crashes on COT failure.
    """
    api_key = os.environ.get("NASDAQ_DATA_LINK_KEY")
    if not api_key:
        print("  NASDAQ_DATA_LINK_KEY not set — skipping COT data.")
        return ""

    try:
        import nasdaqdatalink
        nasdaqdatalink.ApiConfig.api_key = api_key
    except ImportError:
        print("  nasdaq-data-link not installed — skipping COT data.")
        return ""

    today_date = datetime.now(timezone.utc).date()
    rows = [
        "## COT Positioning (CFTC Non-Commercial, Net)",
        "",
        "| Asset | Net Long | Percentile (1yr) | Signal | As Of |",
        "|-------|----------|-----------------|--------|-------|",
    ]

    for label, dataset in COT_SERIES.items():
        try:
            df = nasdaqdatalink.get(dataset, rows=54)   # ~1 yr of weekly data
            df = df.sort_index()

            long_col  = next((c for c in df.columns if "noncomm" in c.lower() and "long" in c.lower()), None)
            short_col = next((c for c in df.columns if "noncomm" in c.lower() and "short" in c.lower()), None)
            if long_col is None or short_col is None:
                print(f"  Warning: COT column names not found for {label}. Columns: {list(df.columns)}")
                rows.append(f"| {label} | n/a | n/a | n/a | n/a |")
                continue

            df["net_long"] = df[long_col] - df[short_col]
            current  = float(df["net_long"].iloc[-1])
            min_val  = float(df["net_long"].min())
            max_val  = float(df["net_long"].max())
            pct      = round(((current - min_val) / (max_val - min_val)) * 100) if max_val > min_val else 50

            as_of_date  = df.index[-1].date()
            days_stale  = (today_date - as_of_date).days

            if pct >= 80:
                signal = "Crowded Long — contrarian bearish"
            elif pct <= 20:
                signal = "Crowded Short — contrarian bullish"
            else:
                signal = "Neutral"

            stale_note = f" ({days_stale}d stale)" if days_stale > 10 else ""
            rows.append(
                f"| {label} | {current:,.0f} | {pct}th pct | {signal} | {as_of_date}{stale_note} |"
            )

        except Exception as e:
            print(f"  Warning: COT fetch failed for {label} ({dataset}): {e}")
            rows.append(f"| {label} | n/a | n/a | fetch failed | n/a |")

    return "\n".join(rows)


def detect_notable_moves(market_data: dict, histories: dict) -> str:
    """
    Flag assets where today's move is ≥2σ of the 60-day return distribution AND
    exceeds the per-asset minimum absolute threshold.
    Returns a formatted Markdown block or empty string if nothing qualifies.
    VIX and VIX3M are excluded (circular to volatility testing).
    """
    flags = []
    for name, d in market_data.items():
        if name in _NOTABLE_MOVE_EXCLUDE:
            continue
        hist = histories.get(name)
        if hist is None or len(hist) < 10:
            continue
        pct_changes = hist.pct_change().dropna() * 100
        window_60 = pct_changes.iloc[-60:] if len(pct_changes) >= 60 else pct_changes
        std_pct = float(window_60.std())
        if std_pct == 0:
            continue
        daily_pct = d["change_pct"]
        sigma     = abs(daily_pct) / std_pct
        min_abs   = _NOTABLE_MOVE_MIN_ABS.get(name, 1.5)
        if sigma >= 2.0 and abs(daily_pct) >= min_abs:
            label = MARKET_LABELS.get(name, name)
            sign  = "+" if daily_pct >= 0 else ""
            flags.append(f"- {label}: {sign}{daily_pct:.2f}% ({sigma:.1f}σ, 60d basis)")

    if not flags:
        return ""
    return "## Notable Moves (≥2σ today)\n" + "\n".join(flags)


# ---------------------------------------------------------------------------
# Technical indicators (Phase 2)
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """14-period Wilder's RSI using exponential smoothing (com = period - 1)."""
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gain  = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    if float(loss.iloc[-1]) == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / float(loss.iloc[-1])
    return round(100 - (100 / (1 + rs)), 1)


def compute_technicals(histories: dict) -> dict:
    """
    For each asset in _TECHNICAL_ASSETS compute:
    - 14-day RSI with Overbought/Oversold/Neutral label
    - % distance from 50-day MA
    - 60-day Z-score of today's daily return
    Returns a dict of {asset_name: indicator_dict}.
    """
    results: dict = {}
    for name in _TECHNICAL_ASSETS:
        close = histories.get(name)
        if close is None or len(close) < 15:
            continue
        t: dict = {}

        rsi = _compute_rsi(close)
        if rsi is not None:
            t["rsi"] = rsi
            t["rsi_label"] = "Overbought" if rsi > 70 else ("Oversold" if rsi < 30 else "Neutral")

        if len(close) >= 50 and name not in _SKIP_MA50:
            ma50  = float(close.rolling(50).mean().iloc[-1])
            price = float(close.iloc[-1])
            dist  = round(((price - ma50) / ma50) * 100, 2)
            t["ma50_dist_pct"]   = dist
            t["ma50_dist_label"] = f"{'+' if dist >= 0 else ''}{dist:.1f}% vs 50dMA"

        if len(close) >= 61:
            returns  = close.pct_change().dropna()
            window60 = returns.iloc[-60:]
            std60    = float(window60.std())
            if std60 > 0:
                t["z60"] = round(float(returns.iloc[-1]) / std60, 2)

        if t:
            results[name] = t
    return results


def format_technicals_block(technicals: dict) -> str:
    """Return a Markdown ## Technical & Positioning State table, or empty string if no data."""
    if not technicals:
        return ""

    _labels = {"sp500": "S&P 500", "nasdaq": "Nasdaq", "gold": "Gold",
               "wti_oil": "WTI Oil", "dxy": "DXY", "bitcoin": "Bitcoin"}

    lines = [
        "## Technical & Positioning State",
        "",
        "| Asset | RSI (14d) | vs 50dMA | 60d Z-Score |",
        "|-------|-----------|----------|-------------|",
    ]
    for name, label in _labels.items():
        t = technicals.get(name)
        if not t:
            lines.append(f"| {label} | n/a | n/a | n/a |")
            continue
        rsi_str = f"{t['rsi']} ({t['rsi_label']})" if "rsi" in t else "n/a"
        ma_str  = t.get("ma50_dist_label", "n/a")
        z_str   = f"{t['z60']:+.2f}σ" if "z60" in t else "n/a"
        lines.append(f"| {label} | {rsi_str} | {ma_str} | {z_str} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Economic calendar
# ---------------------------------------------------------------------------

# FOMC meeting dates (start of 2-day meeting; decision on day 2).
# !! UPDATE THIS LIST EVERY JANUARY !!
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# BLS release names to watch (matched as substrings against BLS schedule)
BLS_RELEASES_OF_INTEREST = {"consumer price index", "employment situation", "producer price index"}


def fetch_upcoming_events(today: datetime, lookahead_days: int = 7) -> str:
    """
    Returns a formatted ## Upcoming Events block covering:
    - BLS high-impact releases (CPI, PPI, NFP) within the next `lookahead_days`
    - FOMC meeting dates within the next `lookahead_days`
    Returns empty string on any fetch failure so the pipeline never crashes.
    """
    today_date = today.date()
    cutoff     = today_date + timedelta(days=lookahead_days)
    events     = []

    # --- BLS releases ---
    try:
        resp = requests.get(
            "https://www.bls.gov/schedule/news_release/schedule.json",
            timeout=10,
            headers={"User-Agent": "macro-assist/1.0"},
        )
        if resp.ok:
            for item in resp.json().get("releases", []):
                name     = item.get("release_name", "").lower()
                date_str = item.get("date", "")
                if not any(k in name for k in BLS_RELEASES_OF_INTEREST):
                    continue
                try:
                    rel_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if today_date <= rel_date <= cutoff:
                    days_away = (rel_date - today_date).days
                    label = "TODAY" if days_away == 0 else f"in {days_away}d"
                    events.append((rel_date, f"BLS: {item.get('release_name')} ({label})"))
    except Exception as e:
        print(f"  Warning: BLS calendar fetch failed: {e}")

    # --- FOMC dates ---
    for date_str in FOMC_DATES:
        try:
            fomc_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        # Show the decision day (day after start) and the start day
        for offset, label in [(0, "FOMC meeting begins"), (1, "FOMC decision day")]:
            event_date = fomc_date + timedelta(days=offset)
            if today_date <= event_date <= cutoff:
                days_away = (event_date - today_date).days
                tag = "TODAY" if days_away == 0 else f"in {days_away}d"
                events.append((event_date, f"Fed: {label} ({tag})"))

    if not events:
        return ""

    events.sort(key=lambda x: x[0])
    lines = ["## Upcoming Events (next 7 days)"]
    for _, desc in events:
        lines.append(f"- {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Accuracy context (self-calibration feedback loop)
# ---------------------------------------------------------------------------

def load_accuracy_context() -> str:
    """
    Read accuracy_summary.json and return a compact text block for injection
    into the Claude prompt. Returns empty string if no data exists yet.
    """
    if not ACCURACY_JSON.exists():
        return ""

    try:
        data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return ""

    windows = data.get("windows", {})
    n_total = data.get("n_reports_total", 0)
    as_of   = data.get("generated_at", "unknown")

    lines = [
        f"## Your Historical Prediction Accuracy (as of {as_of}, {n_total} reports scored)",
        "",
        "Use this to calibrate confidence. 50% = random. >65% with meaningful n = genuine signal.",
        "MANDATORY BIAS CORRECTION: If directional accuracy for an asset at any window is <40% with n≥8,",
        "your natural lean on that asset is systematically wrong. You MUST weight market structure and",
        "momentum at least equally to macro indicators. Do not repeat a bearish call that has been wrong",
        "8+ times — that is not caution, it is miscalibration.",
        "",
    ]

    window_labels = {"t5": "T+5 (1 week)", "t10": "T+10 (2 weeks)", "t20": "T+20 (1 month)"}
    asset_order   = ["S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin"]

    for wkey, wlabel in window_labels.items():
        wdata = windows.get(wkey)
        if not wdata or wdata.get("overall_accuracy") is None:
            continue

        ov  = wdata["overall_accuracy"]
        n   = wdata["n_reports"]
        lines.append(f"**{wlabel}** — overall {ov:.0%} ({n} reports)")

        for asset in asset_order:
            astat = wdata["by_asset"].get(asset)
            if not astat:
                continue
            acc  = astat["accuracy"]
            dacc = astat["directional_acc"]
            dn   = astat["directional_n"]
            dacc_str = f"{dacc:.0%} (n={dn})" if dacc is not None else "n/a"
            lines.append(f"  - {asset}: accuracy {acc:.0%}, directional {dacc_str}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

TRANSCRIPT_SUMMARY_PROMPT = """\
Extract the 6-8 most important macro-relevant insights from this analyst video transcript.

Focus exclusively on:
- Specific data points and market levels cited (include the numbers)
- Cause-and-effect arguments about macro dynamics
- Forward-looking implications for bonds, equities, commodities, or Fed policy

Ignore completely: stock picks, fund promotions, subscription pitches, calls to action.

Format as a concise bullet list. Be specific — keep every number mentioned.\
"""


def summarize_transcript(client: anthropic.Anthropic, title: str, transcript: str) -> str:
    """Use Claude Haiku to extract macro signal from a raw transcript."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"Video title: {title}\n\nTranscript:\n{transcript}",
        }],
        system=TRANSCRIPT_SUMMARY_PROMPT,
    )
    return response.content[0].text.strip()


def fetch_youtube_context(client: anthropic.Anthropic) -> str:
    """
    Fetch recent transcripts from configured channels, summarize each with Haiku,
    and return a formatted context block. Returns empty string if nothing found.
    """
    from youtube_data import get_recent_transcripts
    blocks = []

    for channel_id, channel_name in YOUTUBE_CHANNELS:
        print(f"  Checking YouTube: {channel_name}...")
        videos = get_recent_transcripts(channel_id)

        if not videos:
            print(f"    -> no new videos in last 36h")
            continue

        print(f"    -> {len(videos)} video(s) found, summarizing...")
        for video in videos:
            summary = summarize_transcript(client, video["title"], video["transcript"])
            blocks.append(
                f"### {channel_name}: \"{video['title']}\"\n"
                f"*Published: {video['published'][:10]} | {video['url']}*\n\n"
                f"{summary}"
            )

    if not blocks:
        return ""

    header = "## Analyst Video Insights"
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


def adversarial_review(client: anthropic.Anthropic, draft_analysis: str) -> str:
    """
    Second Claude pass: stress-tests each prediction against the Key Risks section.
    Lowers Confidence by 5-10pp and annotates Primary Driver for any prediction
    whose thesis is directly contradicted by a listed Key Risk.
    Returns the full analysis with the revised predictions table spliced in.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": f"""Adversarial prediction review.

Read the Key Risks & Themes section and the 5-Day Predictions table in the report below.

Apply a HIGH bar. For each prediction row, lower Confidence by 5-10pp and append " [Risk: <2-3 word label>]" to the Primary Driver cell ONLY IF both conditions are true:
1. A listed Key Risk would make the directional call (Bullish/Bearish) OUTRIGHT WRONG if it materialized — not merely add uncertainty or reduce magnitude.
2. That Key Risk is assessed as a probable near-term scenario, not just a tail risk.

Do NOT lower confidence if:
- The risk only affects magnitude, not direction.
- The risk is generic market uncertainty (e.g. "volatility may increase").
- The prediction is already Neutral.
- You can construct a counter-argument but the original thesis remains the base case.

Confidence must never go below 50% or above 70%.

If no prediction meets both conditions, return the table completely unchanged.

Return ONLY the complete revised 5-Day Predictions table (header row + separator row + all asset rows). No preamble, no explanation, no Review date line.

REPORT:
{draft_analysis}"""}]
    )
    revised_table = response.content[0].text.strip()

    # Splice the revised table back into the draft, replacing the original
    pattern = r'(\| Asset \| Bias \| Target Range \| Confidence \| Primary Driver \|.*?\n(?:\|[^\n]+\n)+)'
    match = re.search(pattern, draft_analysis, re.DOTALL)
    if not match:
        print("  Warning: could not locate predictions table for adversarial review; using original.")
        return draft_analysis

    original_table = match.group(1)
    revised_table = _clamp_confidence_floor(revised_table)
    _log_adversarial_diff(original_table, revised_table)
    return draft_analysis[:match.start()] + revised_table + "\n" + draft_analysis[match.end():]


def _clamp_confidence_floor(table: str, floor: int = 50, ceiling: int = 70) -> str:
    """Clamp all Confidence cells to [floor, ceiling]%."""
    def clamp_cell(m: re.Match) -> str:
        val = int(m.group(1))
        return f"{max(floor, min(val, ceiling))}%"
    return re.sub(r'\b(\d{2})%', clamp_cell, table)


def _log_adversarial_diff(original: str, revised: str) -> None:
    """Print a compact diff of what the adversarial pass changed."""
    orig_rows  = [r.strip() for r in original.strip().splitlines() if r.startswith("|") and "---" not in r]
    rev_rows   = [r.strip() for r in revised.strip().splitlines() if r.startswith("|") and "---" not in r]

    # Skip header row (first row)
    orig_data = orig_rows[1:]
    rev_data  = rev_rows[1:] if len(rev_rows) > 1 else rev_rows

    changes = 0
    for orig_row, rev_row in zip(orig_data, rev_data):
        if orig_row == rev_row:
            continue
        orig_cells = [c.strip() for c in orig_row.split("|")[1:-1]]
        rev_cells  = [c.strip() for c in rev_row.split("|")[1:-1]]
        asset = orig_cells[0] if orig_cells else "?"
        diffs = []
        labels = ["Bias", "Target Range", "Confidence", "Primary Driver"]
        for label, o, r in zip(labels, orig_cells[1:], rev_cells[1:]):
            if o != r:
                diffs.append(f"  {label}: {o!r} -> {r!r}")
        if diffs:
            print(f"[adversarial] {asset}:")
            for d in diffs:
                print(d)
            changes += 1

    if changes == 0:
        print("[adversarial] No predictions changed.")
    else:
        print(f"[adversarial] {changes} prediction(s) revised.")


def _apply_accuracy_override(analysis: str) -> str:
    """
    Code-level bias correction applied after adversarial review.
    If T+5 directional accuracy for an asset is <40% at n>=8 and the current
    prediction is Bearish, floor confidence at 50% and annotate — but keep the
    direction so the call remains scoreable. This allows accuracy stats to evolve
    naturally; once they recover above 40% the override stops firing automatically.
    Flipping to Neutral would freeze the scoring sample and lock in the bad stats.
    """
    if not ACCURACY_JSON.exists():
        print("[accuracy-override] No accuracy data — skipping.")
        return analysis
    try:
        acc_data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return analysis

    t5_by_asset = acc_data.get("windows", {}).get("t5", {}).get("by_asset", {})
    if not t5_by_asset:
        return analysis

    table_pattern = r'(\| Asset \| Bias \| Target Range \| Confidence \| Primary Driver \|.*?\n(?:\|[^\n]+\n)+)'
    match = re.search(table_pattern, analysis, re.DOTALL)
    if not match:
        print("[accuracy-override] Could not locate predictions table.")
        return analysis

    table    = match.group(0)
    modified = table
    overrides = 0

    for asset, stat in t5_by_asset.items():
        dacc = stat.get("directional_acc")
        dn   = stat.get("directional_n", 0)
        if dacc is None or dn < 8 or dacc >= 0.40:
            continue

        row_pat   = re.compile(
            rf'(\|\s*{re.escape(asset)}\s*\|\s*)Bearish(\s*\|[^\n]+\n)',
            re.IGNORECASE,
        )
        row_match = row_pat.search(modified)
        if not row_match:
            continue

        original_row = row_match.group(0)
        cells = original_row.rstrip("\n").split("|")
        if len(cells) < 6:
            continue

        # Keep direction (scoreable); floor confidence; annotate driver
        cells[4] = " 50% "
        cells[5] = (
            f" {cells[5].strip()} "
            f"[Caution: T+5 Bearish dir. acc. {dacc:.0%} n={dn} — historical bias flagged] "
        )
        new_row  = "|".join(cells) + "\n"
        modified = modified.replace(original_row, new_row, 1)
        print(f"[accuracy-override] {asset}: confidence floored at 50% (T+5 Bearish {dacc:.0%}, n={dn})")
        overrides += 1

    if overrides == 0:
        print("[accuracy-override] No accuracy-based overrides applied.")
        return analysis

    return analysis[: match.start()] + modified + analysis[match.end():]


def analyze_with_claude(
    fred_data: dict,
    market_data: dict,
    today: datetime,
    sector_data: dict | None = None,
    notable_moves: str = "",
    histories: dict | None = None,
) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_prompt = (PROMPTS_DIR / "system_prompt.md").read_text()

    from parse_positions import get_portfolio_summary, format_portfolio_for_prompt

    review_date      = next_review_date(today)
    accuracy_context = load_accuracy_context()
    youtube_context  = fetch_youtube_context(client)
    events_context   = fetch_upcoming_events(today)

    portfolio_summary = get_portfolio_summary(str(POSITIONS_CSV))
    portfolio_context = format_portfolio_for_prompt(portfolio_summary) if portfolio_summary else ""

    technicals_block = ""
    if histories:
        technicals = compute_technicals(histories)
        technicals_block = format_technicals_block(technicals)

    print("Fetching COT positioning data...")
    cot_block = fetch_cot_data()

    sector_block = (
        f"\n\n## Sector ETF Data\n{json.dumps(sector_data, indent=2)}"
        if sector_data else ""
    )

    user_message = f"""Today is {today.strftime('%A, %B %d, %Y')}.
Prediction review date (5 business days): {review_date}

## FRED Macro Indicators
{json.dumps(fred_data, indent=2)}

## Market Data
{json.dumps(market_data, indent=2)}
{f"{chr(10)}{sector_block}" if sector_block else ""}
{f"{chr(10)}{technicals_block}" if technicals_block else ""}
{f"{chr(10)}{cot_block}" if cot_block else ""}
{f"{chr(10)}{notable_moves}" if notable_moves else ""}
{f"{chr(10)}{events_context}" if events_context else ""}
{f"{chr(10)}{youtube_context}" if youtube_context else ""}
{f"{chr(10)}{accuracy_context}" if accuracy_context else ""}
{f"{chr(10)}{portfolio_context}" if portfolio_context else ""}
Generate the macro intelligence note as specified in your instructions."""

    print("=" * 72)
    print("SYSTEM PROMPT")
    print("=" * 72)
    print(system_prompt)
    print("=" * 72)
    print("USER MESSAGE")
    print("=" * 72)
    print(user_message)
    print("=" * 72)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    draft = response.content[0].text

    print("Running adversarial prediction review...")
    reviewed = adversarial_review(client, draft)
    print("Applying accuracy-based override check...")
    return _apply_accuracy_override(reviewed)


# ---------------------------------------------------------------------------
# Note assembly
# ---------------------------------------------------------------------------

def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def build_note(
    fred_data: dict,
    market_data: dict,
    analysis: str,
    today: datetime,
    sector_data: dict | None = None,
) -> str:
    date_str = today.strftime("%Y-%m-%d")
    day_name = today.strftime("%A")

    # Markets table rows (vix3m and vix_term_ratio excluded via MARKET_LABELS filter)
    market_rows = "\n".join(
        f"| {MARKET_LABELS[k]} | {d['price']:,.2f} | "
        f"{_arrow(d['change_pct'])} {abs(d['change_pct']):.2f}% |"
        for k, d in market_data.items()
        if k in MARKET_LABELS
    )

    # Sector ETF table (optional)
    sector_section = ""
    if sector_data:
        sector_rows = "\n".join(
            f"| {SECTOR_LABELS[k]} | {d['price']:,.2f} | "
            f"{_arrow(d['change_pct'])} {abs(d['change_pct']):.2f}% |"
            for k, d in sector_data.items()
            if k in SECTOR_LABELS
        )
        sector_section = f"""
### Sector ETFs

| Sector | Price | Change |
|--------|-------|--------|
{sector_rows}
"""

    # FRED table rows — build as list to handle optional series cleanly
    fd = fred_data
    fred_row_list = [
        f"| Fed Funds Rate      | {fd['fed_funds_rate']['value']}%  | {fd['fed_funds_rate']['date']} |",
        f"| 10Y Treasury        | {fd['treasury_10y']['value']}%   | {fd['treasury_10y']['date']} |",
        f"| 2Y Treasury         | {fd['treasury_2y']['value']}%    | {fd['treasury_2y']['date']} |",
        f"| Yield Curve (10-2Y) | {fd['yield_curve_spread']}%      | — |",
        f"| CPI YoY             | {fd['cpi'].get('yoy_pct', 'N/A')}%  | {fd['cpi']['date']} |",
        f"| Unemployment        | {fd['unemployment']['value']}%   | {fd['unemployment']['date']} |",
        f"| M2 YoY              | {fd['m2'].get('yoy_pct', 'N/A')}%   | {fd['m2']['date']} |",
    ]
    if "real_yield_10y" in fd:
        fred_row_list.append(
            f"| 10Y Real Yield      | {fd['real_yield_10y']['value']}%  | {fd['real_yield_10y']['date']} |"
        )
    if "breakeven_10y" in fd:
        fred_row_list.append(
            f"| 10Y Breakeven       | {fd['breakeven_10y']['value']}%  | {fd['breakeven_10y']['date']} |"
        )
    if "net_liquidity" in fd:
        nl = fd["net_liquidity"]
        fred_row_list.append(
            f"| Fed Net Liquidity   | ${nl['value_bn'] / 1000:.2f}T ({nl['trend_summary']}) | {nl['date']} |"
        )
    if "jobless_claims" in fd:
        jc = fd["jobless_claims"]
        wow_str = f", {'+' if jc.get('wow_pct', 0) >= 0 else ''}{jc.get('wow_pct', 0):.1f}% WoW" if "wow_pct" in jc else ""
        fred_row_list.append(
            f"| Initial Claims      | {jc['value']:,.0f}k ({jc.get('trend', '')+wow_str}) | {jc['date']} |"
        )
    if "nfci" in fd:
        fred_row_list.append(
            f"| NFCI                | {fd['nfci']['value']} (0=neutral, +tight, -loose) | {fd['nfci']['date']} |"
        )
    fred_rows = "\n".join(fred_row_list)

    return f"""---
date: {date_str}
day: {day_name}
type: macro-intelligence
tags: [macro, daily-note, economics]
---

# Macro Intelligence — {date_str}

{analysis}

---

## Data Snapshot

### Markets

| Asset | Price | Change |
|-------|-------|--------|
{market_rows}
{sector_section}
### Macro Indicators

| Indicator | Value | As Of |
|-----------|-------|-------|
{fred_rows}

---
*Generated by Macro-Assist · {today.strftime("%Y-%m-%d %H:%M")} UTC*
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    today = datetime.now(timezone.utc)

    # Idempotency: skip if today's note already exists
    output_path = get_output_path(today)
    if output_path.exists():
        print(f"Note already exists for {today.strftime('%Y-%m-%d')}, skipping.")
        sys.exit(0)

    fred  = Fred(api_key=os.environ["FRED_API_KEY"])

    print("Fetching FRED data...")
    fred_data = fetch_fred_data(fred)

    print("Fetching market data...")
    market_data, histories = fetch_market_data()

    # VIX term structure ratio: > 1.0 = backwardation (acute stress), < 1.0 = contango (calm)
    if "vix" in market_data and "vix3m" in market_data:
        market_data["vix_term_ratio"] = round(
            market_data["vix"]["price"] / market_data["vix3m"]["price"], 3
        )

    notable_moves = detect_notable_moves(market_data, histories)
    if notable_moves:
        print(f"Notable moves detected:\n{notable_moves}")

    print("Fetching sector ETF data...")
    sector_data = fetch_sector_data()

    print("Running Claude analysis...")
    analysis = analyze_with_claude(fred_data, market_data, today, sector_data, notable_moves, histories)

    print("Building note...")
    note = build_note(fred_data, market_data, analysis, today, sector_data)

    output_path.write_text(note, encoding="utf-8")
    print(f"Note written to: {output_path}")


if __name__ == "__main__":
    main()
