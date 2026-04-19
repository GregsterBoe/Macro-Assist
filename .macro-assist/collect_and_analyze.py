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
    "fed_funds_rate": "FEDFUNDS",
    "cpi":            "CPIAUCSL",
    "gdp":            "GDP",
    "unemployment":   "UNRATE",
    "m2":             "M2SL",
    "treasury_10y":   "DGS10",
    "treasury_2y":    "DGS2",
    "hy_spread":      "BAMLH0A0HYM2",   # HY corporate bond OAS spread (%)
    "philly_fed_mfg": "GACDFSA066MSFRBPHI",  # Philly Fed Manufacturing Activity (diffusion index; >0 expanding)
    "real_yield_10y": "DFII10",               # 10Y TIPS real yield (daily)
    "breakeven_10y":  "T10YIE",               # 10Y inflation breakeven rate (daily)
}


def fetch_fred_data(fred: Fred) -> dict:
    today_date = datetime.now(timezone.utc).date()
    data = {}
    for name, series_id in FRED_SERIES.items():
        try:
            # 5-year history enables historical context computation; daily series return ~1,250 rows
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
        # 5-year mean YoY for CPI and M2 (anchor for "elevated" / "mild" language)
        if name in ("cpi", "m2") and len(series) >= 25:
            yoy_series = series.pct_change(12).dropna() * 100
            if len(yoy_series) >= 12:
                data[name]["five_yr_mean_yoy"] = round(float(yoy_series.mean()), 2)
        # 5-year mean of raw value for spread/index/rate series
        # Note: philly_fed_mfg mean includes COVID-era extremes (~-56 in Apr 2020); treat as context, not target
        if name in ("hy_spread", "philly_fed_mfg", "real_yield_10y", "breakeven_10y") and len(series) >= 12:
            data[name]["five_yr_mean"] = round(float(series.mean()), 3)
            data[name]["vs_mean"]      = round(float(latest) - float(series.mean()), 3)

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
    "vix3m":   "^VIX3M",   # 3-month VIX; used for term structure ratio only — not in snapshot table
}

MARKET_LABELS = {
    "sp500":   "S&P 500",
    "nasdaq":  "Nasdaq",
    "gold":    "Gold",
    "wti_oil": "WTI Oil",
    "vix":     "VIX",
    "dxy":     "DXY",
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
    "sp500": 1.5, "nasdaq": 1.5, "gold": 1.5, "wti_oil": 2.0, "dxy": 0.8,
}


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


def fetch_market_data() -> tuple[dict, dict]:
    """Return (price_data, histories) where histories maps name → Close price Series."""
    data: dict = {}
    histories: dict = {}
    for name, ticker in MARKET_TICKERS.items():
        snapshot, close = _ticker_snapshot(ticker, "10d")
        if snapshot:
            data[name] = snapshot
            histories[name] = close

    if not data:
        sys.exit("Market holiday or all tickers unavailable — no market data fetched. Skipping report.")
    return data, histories


def fetch_sector_data() -> dict:
    """Fetch daily close and % change for sector ETFs."""
    data = {}
    for name, ticker in SECTOR_TICKERS.items():
        snapshot, _ = _ticker_snapshot(ticker, "5d")
        if snapshot:
            data[name] = snapshot
    return data


def detect_notable_moves(market_data: dict, histories: dict) -> str:
    """
    Flag assets where |daily_change| >= 2 * 10-day rolling std AND exceeds
    the per-asset minimum absolute threshold.
    Returns a formatted Markdown block or empty string if nothing qualifies.
    VIX and VIX3M are excluded (circular to volatility testing).
    """
    flags = []
    for name, d in market_data.items():
        if name in _NOTABLE_MOVE_EXCLUDE:
            continue
        hist = histories.get(name)
        if hist is None or len(hist) < 5:
            continue
        pct_changes = hist.pct_change().dropna() * 100
        std_pct = float(pct_changes.std())
        if std_pct == 0:
            continue
        daily_pct = d["change_pct"]
        sigma     = abs(daily_pct) / std_pct
        min_abs   = _NOTABLE_MOVE_MIN_ABS.get(name, 1.5)
        if sigma >= 2.0 and abs(daily_pct) >= min_abs:
            label = MARKET_LABELS.get(name, name)
            sign  = "+" if daily_pct >= 0 else ""
            flags.append(f"- {label}: {sign}{daily_pct:.2f}% ({sigma:.1f}σ)")

    if not flags:
        return ""
    return "## Notable Moves (≥2σ today)\n" + "\n".join(flags)


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
        "Assets where directional accuracy is <40% have systematic bias — consider revising your thesis.",
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

Confidence must never go below 50%.

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


def _clamp_confidence_floor(table: str, floor: int = 50) -> str:
    """Ensure no Confidence cell in the predictions table drops below `floor`%."""
    def clamp_cell(m: re.Match) -> str:
        val = int(m.group(1))
        return f"{max(val, floor)}%"
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


def analyze_with_claude(
    fred_data: dict,
    market_data: dict,
    today: datetime,
    sector_data: dict | None = None,
    notable_moves: str = "",
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
    return adversarial_review(client, draft)


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
    analysis = analyze_with_claude(fred_data, market_data, today, sector_data, notable_moves)

    print("Building note...")
    note = build_note(fred_data, market_data, analysis, today, sector_data)

    output_path.write_text(note, encoding="utf-8")
    print(f"Note written to: {output_path}")


if __name__ == "__main__":
    main()
