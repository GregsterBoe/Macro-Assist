"""Market, sector, technicals, COT positioning and notable-move data fetching."""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

from pipeline_common import (
    _log, ACCURACY_JSON,
)


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
    "xle":  "XLE",   # Energy
    "xlk":  "XLK",   # Technology
    "xlf":  "XLF",   # Financials
    "xli":  "XLI",   # Industrials
    "xly":  "XLY",   # Consumer Discretionary
    "xlv":  "XLV",   # Health Care
    "xlu":  "XLU",   # Utilities
    "xlp":  "XLP",   # Consumer Staples
    "xlb":  "XLB",   # Materials
    "xlre": "XLRE",  # Real Estate
    "xlc":  "XLC",   # Communication Services
}

SECTOR_LABELS = {
    "xle":  "Energy (XLE)",
    "xlk":  "Technology (XLK)",
    "xlf":  "Financials (XLF)",
    "xli":  "Industrials (XLI)",
    "xly":  "Consumer Discretionary (XLY)",
    "xlv":  "Health Care (XLV)",
    "xlu":  "Utilities (XLU)",
    "xlp":  "Consumer Staples (XLP)",
    "xlb":  "Materials (XLB)",
    "xlre": "Real Estate (XLRE)",
    "xlc":  "Communication Services (XLC)",
}

# Approximate 5yr trailing P/E reference per sector ETF (basis for relative-valuation flags)
SECTOR_PE_REFERENCE: dict[str, float] = {
    "xle":  16.0,
    "xlk":  30.0,
    "xlf":  14.5,
    "xli":  21.0,
    "xly":  27.0,
    "xlv":  19.5,
    "xlu":  18.5,
    "xlp":  21.5,
    "xlb":  19.0,
    "xlre": 40.0,   # P/E unreliable for REITs; use as directional signal only
    "xlc":  21.0,
}

# Top-3 holdings per sector ETF (as of 2025 Q2; review quarterly)
# XLRE omitted: P/E-based holding analysis is misleading for REITs
SECTOR_HOLDINGS: dict[str, list[str]] = {
    "xle":  ["XOM", "CVX", "EOG"],
    "xlk":  ["MSFT", "NVDA", "AAPL"],
    "xlf":  ["BRK-B", "JPM", "V"],
    "xli":  ["GE", "CAT", "RTX"],
    "xly":  ["AMZN", "TSLA", "HD"],
    "xlv":  ["LLY", "UNH", "ABBV"],
    "xlu":  ["NEE", "SO", "DUK"],
    "xlp":  ["PG", "KO", "COST"],
    "xlb":  ["LIN", "APD", "SHW"],
    "xlre": [],
    "xlc":  ["META", "GOOGL", "NFLX"],
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

    _missing = [k for k in MARKET_TICKERS if k not in data]
    _log("MARKET", "WARN" if _missing else "OK",
         f"{len(data)}/{len(MARKET_TICKERS)} tickers"
         + (f" | missing: {', '.join(_missing)}" if _missing else ""))

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


def fetch_sector_fundamentals() -> str:
    """
    Fetch sector ETF fundamentals (1M/1Y returns, trailing P/E, 52wk context) and
    top-3 stock holding fundamentals for ETFs flagged below historical P/E average.
    Returns a Markdown block for injection into the Claude prompt.
    Every number is fetched from yfinance — nothing is invented.
    """
    def _fmt_pct(v: float | None) -> str:
        if v is None:
            return "N/A"
        return f"{'+' if v >= 0 else ''}{v:.1f}%"

    # SPX 1M return for relative comparison
    spx_1m: float | None = None
    try:
        spx_hist = yf.Ticker("^GSPC").history(period="2mo")
        if len(spx_hist) >= 21:
            spx_1m = round(
                ((float(spx_hist["Close"].iloc[-1]) / float(spx_hist["Close"].iloc[-21])) - 1) * 100, 2
            )
    except Exception:
        pass

    etf_rows: list[dict] = []
    below_avg_keys: list[str] = []

    for etf_key, ticker in SECTOR_TICKERS.items():
        label  = SECTOR_LABELS.get(etf_key, ticker)
        ref_pe = SECTOR_PE_REFERENCE.get(etf_key)

        # --- Price history (1Y returns, 52wk high) ---
        one_yr_ret: float | None    = None
        one_mo_ret: float | None    = None
        high_52wk_dist: float | None = None
        try:
            hist = yf.Ticker(ticker).history(period="13mo")
            if len(hist) >= 21:
                current = float(hist["Close"].iloc[-1])
                if len(hist) >= 252:
                    one_yr_ret = round(((current / float(hist["Close"].iloc[-252])) - 1) * 100, 2)
                elif len(hist) >= 200:
                    one_yr_ret = round(((current / float(hist["Close"].iloc[0])) - 1) * 100, 2)
                one_mo_ret = round(((current / float(hist["Close"].iloc[-21])) - 1) * 100, 2)
                window = hist["Close"].tail(252) if len(hist) >= 252 else hist["Close"]
                high_52wk = float(window.max())
                high_52wk_dist = round(((current / high_52wk) - 1) * 100, 2)
        except Exception:
            pass

        # --- Trailing P/E from .info ---
        trailing_pe: float | None = None
        try:
            info = yf.Ticker(ticker).info
            raw_pe = info.get("trailingPE")
            if raw_pe and float(raw_pe) > 0:
                trailing_pe = round(float(raw_pe), 1)
        except Exception:
            pass

        # --- Relative P/E flag ---
        pe_flag = "N/A"
        if trailing_pe is not None and ref_pe is not None:
            ratio = trailing_pe / ref_pe
            if ratio < 0.90:
                pe_flag = f"Below avg (ref {ref_pe}x)"
                below_avg_keys.append(etf_key)
            elif ratio > 1.10:
                pe_flag = f"Above avg (ref {ref_pe}x)"
            else:
                pe_flag = f"Near avg (ref {ref_pe}x)"

        vs_spx = "N/A"
        if one_mo_ret is not None and spx_1m is not None:
            diff = round(one_mo_ret - spx_1m, 2)
            vs_spx = f"{'+' if diff >= 0 else ''}{diff}%"

        etf_rows.append({
            "key":            etf_key,
            "ticker":         ticker,
            "label":          label,
            "one_mo_ret":     one_mo_ret,
            "one_yr_ret":     one_yr_ret,
            "vs_spx":         vs_spx,
            "trailing_pe":    trailing_pe,
            "pe_flag":        pe_flag,
            "high_52wk_dist": high_52wk_dist,
        })

    n_below = len(below_avg_keys)
    _log("SECTORS", "OK" if etf_rows else "WARN",
         f"sector fundamentals: {len(etf_rows)} ETFs, {n_below} below avg P/E")

    # --- Build main table ---
    lines: list[str] = [
        "## Sector Fundamentals\n",
        "| ETF | Sector | 1M Ret | 1Y Ret | vs SPX 1M | Trailing P/E | P/E vs Ref | 52wk High |",
        "|-----|--------|--------|--------|-----------|--------------|------------|-----------|",
    ]
    for r in etf_rows:
        lines.append(
            f"| {r['ticker']} | {r['label']} "
            f"| {_fmt_pct(r['one_mo_ret'])} | {_fmt_pct(r['one_yr_ret'])} "
            f"| {r['vs_spx']} | {r['trailing_pe'] or 'N/A'} "
            f"| {r['pe_flag']} | {_fmt_pct(r['high_52wk_dist'])} |"
        )
    lines.append("")

    # --- Holdings for below-avg P/E sectors ---
    if below_avg_keys:
        lines.append("### Below-Average P/E Sectors — Research Candidates\n")
        lines.append("*(All values from yfinance. Research candidates only — not investment advice.)*\n")

        for etf_key in below_avg_keys:
            ticker  = SECTOR_TICKERS[etf_key]
            label   = SECTOR_LABELS.get(etf_key, ticker)
            ref_pe  = SECTOR_PE_REFERENCE.get(etf_key)
            etf_row = next((r for r in etf_rows if r["key"] == etf_key), None)
            tpe_str = str(etf_row["trailing_pe"]) if etf_row and etf_row["trailing_pe"] else "N/A"

            lines.append(f"**{ticker} — {label} [Trailing P/E {tpe_str} vs ref {ref_pe}x]**")

            holdings = SECTOR_HOLDINGS.get(etf_key, [])
            if not holdings:
                lines.append("*(No stock-level data for this sector — P/E metric unreliable.)*\n")
                continue

            lines.append("| Ticker | Fwd P/E | Trailing P/E | Mkt Cap ($B) | 1Y Return |")
            lines.append("|--------|---------|--------------|--------------|-----------|")

            for h_ticker in holdings:
                try:
                    h_info  = yf.Ticker(h_ticker).info
                    h_fpe   = h_info.get("forwardPE")
                    h_tpe   = h_info.get("trailingPE")
                    h_mcap  = h_info.get("marketCap")
                    h_1yr   = h_info.get("52WeekChange")
                    fpe_str  = f"{float(h_fpe):.1f}"  if h_fpe  else "N/A"
                    tpe_str2 = f"{float(h_tpe):.1f}"  if h_tpe  else "N/A"
                    cap_str  = f"{float(h_mcap)/1e9:.0f}" if h_mcap else "N/A"
                    ret_str  = _fmt_pct(round(float(h_1yr) * 100, 1)) if h_1yr else "N/A"
                    lines.append(f"| {h_ticker} | {fpe_str} | {tpe_str2} | {cap_str} | {ret_str} |")
                except Exception:
                    lines.append(f"| {h_ticker} | N/A | N/A | N/A | N/A |")

            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# COT positioning data — CFTC Legacy Futures-Only (deafut.txt)
# ---------------------------------------------------------------------------

# Source: https://www.cftc.gov/dea/newcot/deafut.txt  (updated each Friday, no key required)
# WTI and Gold are commodity futures — they appear in the Legacy report, not Financial Traders.
COT_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"
COT_HISTORY_FILE = ACCURACY_JSON.parent / "cot_history.json"
COT_HISTORY_WEEKS = 54  # rolling window for percentile (~1 year)

COT_SERIES = {
    "WTI Oil": "067651",   # Light Sweet Crude Oil (CL), NYMEX
    "Gold":    "088691",   # Gold (GC), COMEX
    "Bitcoin": "133741",   # Bitcoin (BTC), CME — appears in legacy deafut.txt; WARN if absent
}


def fetch_cot_data() -> str:
    """
    Fetch CFTC COT net non-commercial positioning for WTI, Gold, and Bitcoin.
    Uses the current-week Legacy Futures-Only plain-text file (deafut.txt).
    Maintains a rolling 54-week JSON cache to compute 1-year percentile.
    Returns a ## COT Positioning Markdown block, or empty string on failure.
    Note: if Bitcoin (133741) is absent from deafut.txt, a WARN is logged and
    the other assets still publish — Bitcoin may require the TFF report instead.
    """
    today_date = datetime.now(timezone.utc).date()

    # deafut.txt has NO header row — column positions are fixed by CFTC format spec:
    #   [0] market name  [2] report date  [3] contract code
    #   [8] noncomm long [9] noncomm short
    _COL_CODE  = 3
    _COL_DATE  = 2
    _COL_LONG  = 8
    _COL_SHORT = 9

    try:
        resp = requests.get(COT_URL, timeout=30)
        resp.raise_for_status()
        df = None
        for enc in ("cp1252", "latin-1", "utf-8"):
            try:
                df = pd.read_csv(
                    io.StringIO(resp.content.decode(enc)),
                    header=None,
                    low_memory=False,
                )
                break
            except (UnicodeDecodeError, ValueError):
                continue
        if df is None:
            _log("COT", "WARN", "could not decode CFTC deafut.txt")
            return ""
    except Exception as e:
        _log("COT", "WARN", f"could not fetch CFTC deafut.txt: {e}")
        return ""

    if df.shape[1] <= _COL_SHORT:
        _log("COT", "WARN", f"unexpected column count: {df.shape[1]} (expected ≥{_COL_SHORT + 1})")
        return ""

    # Rename only the columns we use to readable names
    df = df.rename(columns={
        _COL_CODE:  "code",
        _COL_DATE:  "report_date",
        _COL_LONG:  "noncomm_long",
        _COL_SHORT: "noncomm_short",
    })
    code_col, date_col, long_col, short_col = "code", "report_date", "noncomm_long", "noncomm_short"

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # Load rolling history cache (keyed by asset label)
    try:
        history: dict = json.loads(COT_HISTORY_FILE.read_text(encoding="utf-8")) \
                        if COT_HISTORY_FILE.exists() else {}
    except Exception:
        history = {}

    rows = [
        "## COT Positioning (CFTC Non-Commercial, Net)",
        "",
        "| Asset | Net Long | Percentile (1yr) | Signal | As Of |",
        "|-------|----------|-----------------|--------|-------|",
    ]
    _cot_ok = 0
    _history_updated = False

    for label, code in COT_SERIES.items():
        subset = df[df[code_col].astype(str).str.strip() == code].copy()
        if subset.empty:
            _log("COT", "WARN", f"no rows found for {label} (code {code})")
            rows.append(f"| {label} | n/a | n/a | code not found | n/a |")
            continue

        subset["net_long"] = (
            pd.to_numeric(subset[long_col], errors="coerce")
            - pd.to_numeric(subset[short_col], errors="coerce")
        )
        subset = subset.dropna(subset=["net_long"]).sort_values(date_col)
        if subset.empty:
            rows.append(f"| {label} | n/a | n/a | parse error | n/a |")
            continue

        current_net = float(subset["net_long"].iloc[-1])
        as_of_ts    = subset[date_col].iloc[-1]
        as_of       = as_of_ts.date() if pd.notna(as_of_ts) else today_date
        days_stale  = (today_date - as_of).days

        # Append to rolling cache if this week isn't already stored
        asset_history = history.get(label, [])
        date_str = str(as_of)
        if not asset_history or asset_history[-1]["date"] != date_str:
            asset_history.append({"date": date_str, "net_long": current_net})
            asset_history = asset_history[-COT_HISTORY_WEEKS:]
            history[label] = asset_history
            _history_updated = True

        # Percentile from cache (need ≥4 weeks for a meaningful rank)
        net_series = [e["net_long"] for e in asset_history]
        if len(net_series) >= 4:
            min_v, max_v = min(net_series), max(net_series)
            pct = round(((current_net - min_v) / (max_v - min_v)) * 100) if max_v > min_v else 50
            pct_label = f"{pct}th pct"
        else:
            pct = 50
            pct_label = "n/a (building history)"

        if pct >= 80:
            signal = "Crowded Long — contrarian bearish"
        elif pct <= 20:
            signal = "Crowded Short — contrarian bullish"
        else:
            signal = "Neutral"

        stale_note = f" ({days_stale}d stale)" if days_stale > 10 else ""
        rows.append(
            f"| {label} | {current_net:,.0f} | {pct_label} | {signal} | {as_of}{stale_note} |"
        )
        _cot_ok += 1

    # Persist updated cache alongside accuracy data
    if _history_updated:
        try:
            COT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            COT_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception as e:
            _log("COT", "WARN", f"could not save COT history cache: {e}")

    _log("COT", "OK" if _cot_ok == len(COT_SERIES) else "WARN",
         f"{_cot_ok}/{len(COT_SERIES)} assets fetched")
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
