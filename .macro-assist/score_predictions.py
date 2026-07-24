"""
score_predictions.py — Score 5-Day Predictions from macro reports.

For each report, scores directional accuracy at T+5, T+10, and T+20 trading days.
Only processes reports where the evaluation window has fully passed (plus 1-day buffer).

Saves results to: results/scores/YYYY-MM-DD.json
Run manually or on a schedule (e.g. weekly).

Usage:
    python .macro-assist/score_predictions.py
"""

import json
import os
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Point yfinance timezone cache at a per-process temp dir to avoid SQLite
# database lock errors when multiple CI jobs share the default cache location.
try:
    yf.set_tz_cache_location(tempfile.mkdtemp(prefix="yf_tz_"))
except Exception:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
SCORES_DIR  = RESULTS_DIR / "scores"

# In CI, reports live in the vault checkout rather than results/.
# Set MACRO_REPORTS_DIR to the vault root to find them there.
REPORTS_DIR = Path(os.environ.get("MACRO_REPORTS_DIR", RESULTS_DIR))

# Scoring windows: label -> number of trading days
SCORING_WINDOWS = {"t5": 5, "t10": 10, "t20": 20}

# How many extra buffer days after the eval date before we score
# (ensures the market has had time to close on that day)
BUFFER_DAYS = 1

# Directional flat threshold — moves smaller than this are considered "Flat"
# and award 0.5 points to any directional call.
# For ABSOLUTE_DIFF_ASSETS the threshold is compared against |evals - entry|
# (yield level difference in percentage points, so 0.03 = 3 bps).
# For all other assets it is compared against |(evals - entry) / entry| (fractional return).
FLAT_THRESHOLDS = {
    "10Y Treasury Yield": 0.06,   # 6 bps absolute (^TNX reports yield as level, e.g. 4.50)
    "default":            0.005,  # 0.5% return
}

# Assets where the threshold is an absolute price/yield difference, not a % return.
# ^TNX returns the yield level in percent (4.50 = 4.50%); pct arithmetic gives % of %,
# which inflates the denominator and makes the threshold ~13x too large.
ABSOLUTE_DIFF_ASSETS = {"10Y Treasury Yield"}

# Map from normalised asset name -> Yahoo Finance ticker
ASSET_TICKERS = {
    "S&P 500":            "^GSPC",
    "Gold":               "GC=F",
    "WTI Oil":            "CL=F",
    "10Y Treasury Yield": "^TNX",   # Yahoo returns the yield directly (e.g. 4.21)
    "DXY":                "DX-Y.NYB",
    "Bitcoin":            "BTC-USD",
}

# ---------------------------------------------------------------------------
# Helpers — date arithmetic
# ---------------------------------------------------------------------------

def add_trading_days(start: date, n: int) -> date:
    """Return the date that is exactly n trading days (Mon-Fri) after start."""
    current = start
    count = 0
    while count < n:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return current


# ---------------------------------------------------------------------------
# Helpers — frontmatter & report parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter key-value pairs from a report file."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    result = {}
    for line in content[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def find_reports() -> list[tuple[date, Path]]:
    """Return (report_date, path) pairs for all dated macro reports, sorted."""
    reports = []
    for path in REPORTS_DIR.rglob("*-macro.md"):
        if "test" in path.name.lower():
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if m:
            reports.append((date.fromisoformat(m.group(1)), path))
    return sorted(reports)


def normalize_asset(raw: str) -> str:
    """Map potentially verbose asset names to our standard keys."""
    raw = raw.strip()
    if "Bitcoin" in raw:
        return "Bitcoin"
    if "Treasury" in raw or "10Y" in raw:
        return "10Y Treasury Yield"
    return raw


def parse_predictions(path: Path) -> dict | None:
    """
    Parse the 5-Day Predictions table from a report.
    Returns a dict keyed by normalised asset name, or None if section absent.
    """
    content = path.read_text(encoding="utf-8")

    # Locate the predictions block (between heading and "Review date:")
    block = re.search(
        r"### 5-Day Predictions\s*\n+(.*?)\nReview date:",
        content,
        re.DOTALL,
    )
    if not block:
        return None

    table_text = block.group(1)
    predictions = {}

    for line in table_text.splitlines():
        if not line.startswith("|") or "---" in line or "Asset" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 5:
            continue

        asset_raw, bias_raw, driver_raw, conf_raw, target_raw, *_ = cols

        asset = normalize_asset(asset_raw)
        if asset not in ASSET_TICKERS:
            continue

        # Bias
        if "Bullish" in bias_raw:
            bias = "Bullish"
        elif "Bearish" in bias_raw:
            bias = "Bearish"
        else:
            bias = "Neutral"

        # Confidence (integer %)
        cm = re.search(r"(\d+)", conf_raw)
        confidence = int(cm.group(1)) if cm else 50

        # Target range — store as string; extract numbers for reference
        # Filter out pure-comma matches (e.g. "," → "" after strip) that float() rejects
        nums = [float(n.replace(",", "")) for n in re.findall(r"[\d,]+\.?\d*", target_raw)
                if n.replace(",", "")]

        predictions[asset] = {
            "bias": bias,
            "confidence": confidence,
            "target_range_str": target_raw,
            "target_range": nums,
        }

    return predictions if predictions else None


# ---------------------------------------------------------------------------
# Helpers — price fetching
# ---------------------------------------------------------------------------

def _extract_ticker_series(raw: "pd.DataFrame", ticker: str) -> "pd.Series | None":
    """Pull a clean Close series for one ticker out of a batch yf.download result."""
    try:
        close_block = raw["Close"]
        col = close_block[ticker] if hasattr(close_block, "columns") else close_block
        col = col.dropna()
        if col.empty:
            return None
        col.index = pd.to_datetime(col.index).tz_localize(None).normalize()
        col = col[~col.index.duplicated(keep="last")]
        return col
    except (KeyError, Exception):
        return None


def _download_single(ticker: str, start: date, end: date) -> "pd.Series | None":
    """Download one ticker individually; returns a clean Close series or None."""
    try:
        raw = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return None
        col = raw["Close"].dropna()
        col.index = pd.to_datetime(col.index).tz_localize(None).normalize()
        col = col[~col.index.duplicated(keep="last")]
        return col if not col.empty else None
    except Exception as exc:
        print(f"  Warning: individual fetch for {ticker} failed: {exc}")
        return None


def fetch_price_series(start: date, end: date) -> dict[str, pd.Series]:
    """Download daily closing prices for all tracked assets over a date range."""
    tickers = list(ASSET_TICKERS.values())
    series: dict[str, pd.Series] = {}

    try:
        raw = yf.download(
            tickers,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        print(f"  Warning: batch price fetch failed: {exc}")
        raw = None

    if raw is not None and not raw.empty:
        for asset, ticker in ASSET_TICKERS.items():
            col = _extract_ticker_series(raw, ticker)
            if col is not None:
                series[asset] = col
            else:
                print(f"  Warning: no data for {ticker} in batch — retrying individually")

    # Retry any tickers absent from the batch result (e.g. SQLite lock on BTC-USD).
    for asset, ticker in ASSET_TICKERS.items():
        if asset not in series:
            col = _download_single(ticker, start, end)
            if col is not None:
                series[asset] = col
                print(f"  Recovered {ticker} via individual download.")
            else:
                print(f"  Warning: {ticker} unavailable — {asset} will be skipped in scoring.")

    return series


def price_on(series: "pd.Series | None", target: date) -> float | None:
    """
    Return the closing price on target, or the next available trading day
    (up to 4 calendar days forward) if the market was closed.
    """
    if series is None:
        return None
    for offset in range(5):
        ts = pd.Timestamp(target + timedelta(days=offset))
        if ts in series.index:
            val = series.loc[ts]
            # loc returns a Series when the index has duplicate dates
            if isinstance(val, pd.Series):
                val = val.iloc[-1]
            return float(val)
    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_call(entry: float, evals: float, bias: str, asset: str) -> float | None:
    """
    Return directional accuracy score:
      1.0  — correct direction
      0.0  — wrong direction
      0.5  — move within flat threshold, or Neutral call
    """
    if entry is None or evals is None:
        return None

    if asset in ABSOLUTE_DIFF_ASSETS:
        pct = evals - entry          # absolute level change (e.g. bps for yields)
    else:
        pct = (evals - entry) / entry  # fractional return

    threshold = FLAT_THRESHOLDS.get(asset, FLAT_THRESHOLDS["default"])
    if abs(pct) < threshold:
        return 0.5   # too small to call, give half credit

    if bias == "Neutral":
        return 0.5   # neutral calls always get half credit

    direction_up = pct > 0
    if (bias == "Bullish" and direction_up) or (bias == "Bearish" and not direction_up):
        return 1.0
    return 0.0


def score_report(report_date: date, predictions: dict, price_series: dict, today: date) -> dict:
    """
    Score all eligible scoring windows for one report.
    Returns a dict of window results (may be empty if no windows are eligible yet).
    """
    results = {}

    for label, n_days in SCORING_WINDOWS.items():
        eval_date = add_trading_days(report_date, n_days)
        if eval_date + timedelta(days=BUFFER_DAYS) > today:
            continue  # window hasn't closed yet

        window_assets = {}
        for asset, pred in predictions.items():
            entry = price_on(price_series.get(asset), report_date)
            evalu = price_on(price_series.get(asset), eval_date)

            if entry is None or evalu is None:
                continue

            pct_change = (evalu - entry) / entry * 100
            sc = score_call(entry, evalu, pred["bias"], asset)

            window_assets[asset] = {
                "bias":        pred["bias"],
                "confidence":  pred["confidence"],
                "entry_price": round(entry, 4),
                "eval_price":  round(evalu, 4),
                "eval_date":   eval_date.isoformat(),
                "pct_change":  round(pct_change, 3),
                "score":       sc,
            }

        if not window_assets:
            continue

        valid_scores = [v["score"] for v in window_assets.values() if v["score"] is not None]
        accuracy = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else None

        results[label] = {
            "eval_date": eval_date.isoformat(),
            "assets":    window_assets,
            "summary": {
                "n_scored": len(valid_scores),
                "accuracy": accuracy,
            },
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()

    reports = find_reports()
    print(f"Found {len(reports)} reports. Today: {today}\n")

    # Filter to reports with at least T+5 complete
    eligible = [
        (d, p) for d, p in reports
        if add_trading_days(d, 5) + timedelta(days=BUFFER_DAYS) <= today
    ]
    print(f"{len(eligible)} report(s) eligible (T+5 window closed).\n")

    if not eligible:
        print("Nothing to score yet.")
        return

    # Fetch price data spanning all eligible reports + their max eval dates
    min_date = min(d for d, _ in eligible)
    max_eval  = add_trading_days(max(d for d, _ in eligible), 20)
    fetch_end = min(max_eval, today)

    print(f"Fetching price data: {min_date} to {fetch_end} ...")
    price_series = fetch_price_series(min_date, fetch_end)
    print(f"Loaded: {', '.join(price_series)}\n")

    # Score each eligible report
    scored = 0
    for report_date, path in eligible:
        fm = parse_frontmatter(path)
        agent_version = fm.get("agent_version", "unknown")
        # WP-16 experiment arm tags (profile + per-lever, from frontmatter)
        conviction_floor = fm.get("conviction_floor", "unknown")
        profile          = fm.get("profile", "unknown")
        # Phase-19 A/B arm: exogenous-engine notes carry `arm: exogenous`; every
        # existing market-only note is untagged → defaults to "market" (DESIGN §4).
        arm              = fm.get("arm", "market")
        model            = fm.get("model", "unknown")
        base_rate_first  = fm.get("base_rate_first", "unknown")
        prune_rules      = fm.get("prune_rules", "unknown")

        predictions = parse_predictions(path)
        if predictions is None:
            print(f"  {report_date}: no predictions table - skipping")
            continue

        window_results = score_report(report_date, predictions, price_series, today)
        if not window_results:
            print(f"  {report_date}: no windows complete yet")
            continue

        output = {
            "report_date":      report_date.isoformat(),
            "agent_version":    agent_version,
            "conviction_floor": conviction_floor,
            "profile":          profile,
            "arm":              arm,
            "model":            model,
            "base_rate_first":  base_rate_first,
            "prune_rules":      prune_rules,
            "scored_at":        today.isoformat(),
            "windows":          window_results,
        }

        # Key score files by (date, arm) so a same-day exogenous note doesn't
        # clobber the market note's score. Market keeps the bare name (backward
        # compatible); other arms get a suffix. summarize globs *.json regardless.
        arm_suffix = "" if arm == "market" else f"__{arm}"
        score_path = SCORES_DIR / f"{report_date.isoformat()}{arm_suffix}.json"
        score_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        scored += 1

        for label, data in window_results.items():
            acc = data["summary"]["accuracy"]
            n   = data["summary"]["n_scored"]
            acc_str = f"{acc:.0%}" if acc is not None else "n/a"
            print(f"  {report_date} [{label}] {acc_str} accuracy ({n} assets) | eval: {data['eval_date']}")

    print(f"\nDone. {scored} score file(s) written to results/scores/")


if __name__ == "__main__":
    main()
