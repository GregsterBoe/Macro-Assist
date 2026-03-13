"""
Macro-Assist: Daily macro intelligence pipeline.

Fetches FRED + market data, runs Claude analysis, writes a dated
companion note into the Obsidian vault (Journal/YYYY/MM-Month/).

Expects env vars: FRED_API_KEY, ANTHROPIC_API_KEY
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import yfinance as yf
from fredapi import Fred

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# VAULT_ROOT can be overridden via env var (used by GitHub Actions).
# Falls back to the parent of .macro-assist/ for local runs.
VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", Path(__file__).resolve().parent.parent))
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


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
    "fed_funds_rate": "FEDFUNDS",
    "cpi":            "CPIAUCSL",
    "gdp":            "GDP",
    "unemployment":   "UNRATE",
    "m2":             "M2SL",
    "treasury_10y":   "DGS10",
    "treasury_2y":    "DGS2",
}


def fetch_fred_data(fred: Fred) -> dict:
    data = {}
    for name, series_id in FRED_SERIES.items():
        series = fred.get_series(series_id, observation_start="2024-01-01").dropna()
        latest = series.iloc[-1]
        prev   = series.iloc[-2] if len(series) > 1 else latest
        data[name] = {
            "value": round(float(latest), 3),
            "prev":  round(float(prev), 3),
            "date":  series.index[-1].strftime("%Y-%m-%d"),
        }
        # Year-over-year for CPI and M2
        if name in ("cpi", "m2") and len(series) >= 13:
            year_ago = series.iloc[-13]
            data[name]["yoy_pct"] = round(((latest - year_ago) / year_ago) * 100, 2)

    data["yield_curve_spread"] = round(
        data["treasury_10y"]["value"] - data["treasury_2y"]["value"], 3
    )
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
}

MARKET_LABELS = {
    "sp500":   "S&P 500",
    "nasdaq":  "Nasdaq",
    "gold":    "Gold",
    "wti_oil": "WTI Oil",
    "vix":     "VIX",
    "dxy":     "DXY",
}


def fetch_market_data() -> dict:
    data = {}
    for name, ticker in MARKET_TICKERS.items():
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            continue
        close      = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else close
        data[name] = {
            "price":      round(float(close), 2),
            "change_pct": round(((close - prev_close) / prev_close) * 100, 2),
            "date":       hist.index[-1].strftime("%Y-%m-%d"),
        }
    return data


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

def analyze_with_claude(fred_data: dict, market_data: dict, today: datetime) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_prompt = (PROMPTS_DIR / "system_prompt.md").read_text()

    review_date = next_review_date(today)
    user_message = f"""Today is {today.strftime('%A, %B %d, %Y')}.
Prediction review date (5 business days): {review_date}

## FRED Macro Indicators
{json.dumps(fred_data, indent=2)}

## Market Data
{json.dumps(market_data, indent=2)}

Generate the macro intelligence note as specified in your instructions."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


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
) -> str:
    date_str = today.strftime("%Y-%m-%d")
    day_name = today.strftime("%A")

    # Markets table rows
    market_rows = "\n".join(
        f"| {MARKET_LABELS[k]} | {d['price']:,.2f} | "
        f"{_arrow(d['change_pct'])} {abs(d['change_pct']):.2f}% |"
        for k, d in market_data.items()
        if k in MARKET_LABELS
    )

    # FRED table rows
    fd = fred_data
    fred_rows = "\n".join([
        f"| Fed Funds Rate   | {fd['fed_funds_rate']['value']}%  | {fd['fed_funds_rate']['date']} |",
        f"| 10Y Treasury     | {fd['treasury_10y']['value']}%   | {fd['treasury_10y']['date']} |",
        f"| 2Y Treasury      | {fd['treasury_2y']['value']}%    | {fd['treasury_2y']['date']} |",
        f"| Yield Curve (10-2Y) | {fd['yield_curve_spread']}%  | — |",
        f"| CPI YoY          | {fd['cpi'].get('yoy_pct', 'N/A')}%  | {fd['cpi']['date']} |",
        f"| Unemployment     | {fd['unemployment']['value']}%  | {fd['unemployment']['date']} |",
        f"| M2 YoY           | {fd['m2'].get('yoy_pct', 'N/A')}%  | {fd['m2']['date']} |",
    ])

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
    today = datetime.utcnow()

    # Idempotency: skip if today's note already exists
    output_path = get_output_path(today)
    if output_path.exists():
        print(f"Note already exists for {today.strftime('%Y-%m-%d')}, skipping.")
        sys.exit(0)

    fred  = Fred(api_key=os.environ["FRED_API_KEY"])

    print("Fetching FRED data...")
    fred_data = fetch_fred_data(fred)

    print("Fetching market data...")
    market_data = fetch_market_data()

    print("Running Claude analysis...")
    analysis = analyze_with_claude(fred_data, market_data, today)

    print("Building note...")
    note = build_note(fred_data, market_data, analysis, today)

    output_path.write_text(note, encoding="utf-8")
    print(f"Note written to: {output_path}")


if __name__ == "__main__":
    main()
