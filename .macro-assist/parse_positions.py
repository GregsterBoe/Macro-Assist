"""
parse_positions.py — Parse Trade Republic transaction CSV into current portfolio positions.

Reads data/tr_positions.csv, aggregates net shares per asset, fetches current prices
via yfinance (USD assets converted to EUR via EURUSD=X), and returns a portfolio summary
dict suitable for injection into the daily macro prompt.

Usage:
    from parse_positions import get_portfolio_summary
    summary = get_portfolio_summary("data/tr_positions.csv")

CSV path is relative to the Macro-Assist repo root, or set POSITIONS_CSV env var.

Unknown ISINs are auto-resolved via the OpenFIGI API and cached in data/ticker_cache.json.
Only push the updated tr_positions.csv — new tickers are discovered automatically.
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# ISIN / TR symbol → yfinance ticker + currency of that ticker
# Extend this table when new positions are opened.
# ---------------------------------------------------------------------------
ISIN_TO_TICKER: dict[str, tuple[str | None, str]] = {
    # (yfinance_ticker, price_currency)
    # --- US stocks ---
    "US67066G1040": ("NVDA",     "USD"),   # NVIDIA
    "US46284V1017": ("IRM",      "USD"),   # Iron Mountain
    "US0378331005": ("AAPL",     "USD"),   # Apple
    "US6541061031": ("NKE",      "USD"),   # Nike B
    "US8740391003": ("TSM",      "USD"),   # TSMC ADR
    "US4581401001": ("INTC",     "USD"),   # Intel
    "US02079K3059": ("GOOGL",    "USD"),   # Alphabet A
    "US7475251036": ("QCOM",     "USD"),   # Qualcomm
    "US7445731067": ("PEG",      "USD"),   # Public Service Enterprise Group
    "US0079031078": ("AMD",      "USD"),   # AMD
    # --- Crypto ---
    "BTC":          ("BTC-EUR",  "EUR"),   # Bitcoin
    "ETH":          ("ETH-EUR",  "EUR"),   # Ethereum
    "SOL":          ("SOL-EUR",  "EUR"),   # Solana
    # --- ETFs — EUR-listed tickers (Euronext / Frankfurt / Milan) ---
    "IE00B44Z5B48": ("SPYY.DE",  "EUR"),   # SPDR MSCI ACWI Acc (Frankfurt)
    "IE000KCS7J59": (None,       "EUR"),   # HSBC MSCI EM Acc — no reliable yfinance EUR ticker
    "FR0010790980": ("C50.PA",   "EUR"),   # Lyxor Stoxx Europe 50 (Paris)
    "IE00BJ38QD84": ("ZPRR.DE",  "EUR"),   # SPDR Russell 2000 (Frankfurt)
    # --- Bonds / ETC — no liquid yfinance feed ---
    "DE0001135226": (None,       "EUR"),   # German Bund Jul 2034
    "JE00B588CD74": (None,       "EUR"),   # WisdomTree Physical Swiss Gold
    # --- Closed positions (kept for mapping completeness) ---
    "KYG9830T1067": ("1810.HK",  "HKD"),   # Xiaomi
    "NL0010273215": ("ASML",     "USD"),   # ASML (ADR on NASDAQ)
    "DE0006231004": ("IFNNY",    "USD"),   # Infineon (ADR)
    "DE000A1K0235": (None,       "EUR"),   # SUSS MicroTec (no yfinance)
}

DISPLAY_NAMES: dict[str, str] = {
    "US67066G1040": "NVIDIA",
    "US46284V1017": "Iron Mountain",
    "US0378331005": "Apple",
    "US6541061031": "Nike (B)",
    "US8740391003": "TSMC (ADR)",
    "US4581401001": "Intel",
    "US02079K3059": "Alphabet (A)",
    "US7475251036": "Qualcomm",
    "US7445731067": "Public Service Enterprise",
    "US0079031078": "AMD",
    "BTC":          "Bitcoin",
    "ETH":          "Ethereum",
    "SOL":          "Solana",
    "IE00B44Z5B48": "MSCI ACWI ETF",
    "IE000KCS7J59": "MSCI EM ETF",
    "FR0010790980": "Stoxx Europe 50 ETF",
    "IE00BJ38QD84": "Russell 2000 ETF",
    "DE0001135226": "German Bund 2034",
    "JE00B588CD74": "WisdomTree Swiss Gold",
    "KYG9830T1067": "Xiaomi",
    "NL0010273215": "ASML",
    "DE0006231004": "Infineon",
    "DE000A1K0235": "SUSS MicroTec",
}


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _parse_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _aggregate_positions(rows: list[dict]) -> dict[str, dict]:
    """
    Aggregate TRADING rows into net positions per asset.

    Returns dict keyed by symbol (ISIN or 'BTC'):
        {
            "net_shares": float,          # positive = long
            "total_cost_eur": float,      # sum of |amount| for BUY rows (EUR invested)
            "total_shares_bought": float, # for avg-cost computation
            "name": str,
        }
    """
    positions: dict[str, dict] = defaultdict(lambda: {
        "net_shares": 0.0,
        "total_cost_eur": 0.0,
        "total_shares_bought": 0.0,
        "name": "",
    })

    for row in rows:
        if row.get("category") != "TRADING":
            continue
        tx_type = row.get("type", "")
        if tx_type not in ("BUY", "SELL"):
            continue

        symbol = row.get("symbol", "").strip()
        if not symbol:
            continue

        try:
            shares = float(row["shares"])
            amount = float(row["amount"])   # negative for BUY, positive for SELL
        except (ValueError, KeyError):
            continue

        pos = positions[symbol]
        pos["name"] = row.get("name", symbol).strip()
        pos["net_shares"] += shares  # already signed (+buy, -sell)

        if tx_type == "BUY":
            pos["total_cost_eur"] += abs(amount)
            pos["total_shares_bought"] += abs(shares)

    return dict(positions)


def _open_positions(aggregated: dict[str, dict], min_shares: float = 1e-6) -> dict[str, dict]:
    """Filter out fully-closed positions."""
    return {k: v for k, v in aggregated.items() if abs(v["net_shares"]) >= min_shares}


MIN_POSITION_VALUE_EUR = 50.0  # positions below this market value are excluded from the report

# ---------------------------------------------------------------------------
# OpenFIGI auto-resolution
# Cache lives alongside the CSV so it can be committed alongside it.
# ---------------------------------------------------------------------------

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "ticker_cache.json"

# Exchange code → (yfinance suffix, price currency)
EXCH_TO_YFINANCE: dict[str, tuple[str, str]] = {
    "US": ("",    "USD"),   # NYSE misc
    "UW": ("",    "USD"),   # NASDAQ
    "UN": ("",    "USD"),   # NYSE
    "UA": ("",    "USD"),   # NYSE American
    "GY": (".DE", "EUR"),   # Xetra
    "FP": (".PA", "EUR"),   # Euronext Paris
    "LN": (".L",  "GBP"),   # London
    "SW": (".SW", "CHF"),   # SIX Swiss
    "HK": (".HK", "HKD"),   # Hong Kong
    "SM": (".MI", "EUR"),   # Milan
    "BB": (".BR", "EUR"),   # Brussels
    "AV": (".VI", "EUR"),   # Vienna
}

# ISIN country prefix → preferred exchange codes, in priority order
ISIN_PREFIX_EXCH_PREF: dict[str, list[str]] = {
    "US": ["UW", "UN", "US", "UA"],
    "IE": ["GY", "FP", "LN"],      # Irish-domiciled ETFs → EUR exchanges
    "FR": ["FP", "GY"],
    "DE": ["GY", "FP"],
    "NL": ["GY", "FP"],
    "LU": ["GY", "FP"],
    "GB": ["LN"],
    "CH": ["SW"],
    "KY": ["HK", "UW", "UN"],      # Cayman Islands (e.g. Xiaomi)
    "JE": ["LN"],                   # Jersey (e.g. WisdomTree ETCs)
}


def _load_cache() -> dict[str, tuple[str | None, str]]:
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return {k: (v["ticker"], v["currency"]) for k, v in data.items()}
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, tuple[str | None, str]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {k: {"ticker": v[0], "currency": v[1]} for k, v in cache.items()}
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _openfigi_resolve(isin: str) -> tuple[str | None, str] | None:
    """
    Query OpenFIGI to resolve an ISIN to a (yfinance_ticker, currency) pair.
    Returns None if the ISIN cannot be resolved.
    Free tier: 25 req/min without API key.
    """
    try:
        resp = requests.post(
            OPENFIGI_URL,
            json=[{"idType": "ID_ISIN", "idValue": isin}],
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results or "data" not in results[0]:
            return None

        candidates = [c for c in results[0]["data"] if c.get("marketSector") == "Equity"]
        if not candidates:
            return None

        # Pick exchange using ISIN country prefix preference
        isin_prefix = isin[:2].upper()
        pref_exchs = ISIN_PREFIX_EXCH_PREF.get(isin_prefix, [])

        for exch in pref_exchs:
            for c in candidates:
                if c.get("exchCode") == exch and c.get("ticker"):
                    suffix, currency = EXCH_TO_YFINANCE.get(exch, ("", "USD"))
                    return (c["ticker"] + suffix, currency)

        # Fallback: first candidate on any known exchange
        for c in candidates:
            exch = c.get("exchCode", "")
            if exch in EXCH_TO_YFINANCE and c.get("ticker"):
                suffix, currency = EXCH_TO_YFINANCE[exch]
                return (c["ticker"] + suffix, currency)

        return None
    except Exception as exc:
        print(f"  Warning: OpenFIGI lookup failed for {isin}: {exc}", file=sys.stderr)
        return None


def _get_ticker_info(
    symbol: str, cache: dict[str, tuple[str | None, str]]
) -> tuple[str | None, str]:
    """
    Resolve symbol → (yfinance_ticker, currency) using:
      1. Hardcoded ISIN_TO_TICKER (crypto, bonds, known ETFs, manual overrides)
      2. Local cache (data/ticker_cache.json)
      3. OpenFIGI API (real ISINs only — 12-char alphanumeric starting with 2 letters)
    Falls back to (None, 'EUR') if all resolution methods fail.
    """
    if symbol in ISIN_TO_TICKER:
        return ISIN_TO_TICKER[symbol]

    if symbol in cache:
        return cache[symbol]

    # Only attempt OpenFIGI for real ISINs (not BTC/ETH/SOL crypto shortcodes)
    if len(symbol) == 12 and symbol[:2].isalpha() and not symbol[2:].isdigit():
        result = _openfigi_resolve(symbol)
        if result:
            cache[symbol] = result
            _save_cache(cache)
            print(
                f"  Auto-resolved {symbol} → {result[0]} ({result[1]}) via OpenFIGI",
                file=sys.stderr,
            )
            return result
        else:
            print(f"  Warning: could not resolve {symbol} via OpenFIGI — will retry next run", file=sys.stderr)

    return (None, "EUR")


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def _fetch_prices(
    open_pos: dict[str, dict],
    resolved: dict[str, tuple[str | None, str]],
) -> dict[str, float | None]:
    """
    Fetch current EUR price for each open position.
    USD-denominated tickers are converted using EURUSD=X.
    Returns {symbol: eur_price_or_None}.
    """
    # Group tickers to fetch
    tickers_to_fetch: set[str] = set()
    needs_usd_conversion = False

    for symbol in open_pos:
        ticker_info = resolved.get(symbol)
        if ticker_info and ticker_info[0]:
            tickers_to_fetch.add(ticker_info[0])
            if ticker_info[1] == "USD":
                needs_usd_conversion = True

    if needs_usd_conversion:
        tickers_to_fetch.add("EURUSD=X")

    if not tickers_to_fetch:
        return {}

    try:
        raw = yf.download(
            list(tickers_to_fetch),
            period="5d",   # 5d ensures we reach the last trading day over weekends
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        print(f"  Warning: yfinance price fetch failed: {exc}", file=sys.stderr)
        return {}

    def _last_close(ticker: str) -> float | None:
        """Return most recent non-NaN close for ticker, handling both single/multi-ticker DataFrames."""
        try:
            close_col = raw["Close"]
            series = close_col[ticker].dropna() if hasattr(close_col, "columns") else close_col.dropna()
            return float(series.iloc[-1]) if not series.empty else None
        except (KeyError, IndexError, TypeError):
            return None

    eurusd: float | None = _last_close("EURUSD=X") or None
    if needs_usd_conversion and eurusd is None:
        print("  Warning: EURUSD=X unavailable — USD positions will show N/A price.", file=sys.stderr)

    prices: dict[str, float | None] = {}
    for symbol in open_pos:
        ticker_info = resolved.get(symbol)
        if not ticker_info or not ticker_info[0]:
            prices[symbol] = None
            continue

        ticker, currency = ticker_info
        raw_price = _last_close(ticker)
        if raw_price is None:
            prices[symbol] = None
            continue

        if currency == "USD":
            prices[symbol] = raw_price / eurusd if eurusd else None
        elif currency == "HKD":
            hkdusd = 0.128  # approximate; fetch HKDUSD=X for precision if needed
            prices[symbol] = (raw_price * hkdusd / eurusd) if eurusd else None
        else:
            prices[symbol] = raw_price

    return prices


# ---------------------------------------------------------------------------
# Portfolio summary builder
# ---------------------------------------------------------------------------

def get_portfolio_summary(csv_path: str | None = None) -> dict | None:
    """
    Parse the TR positions CSV and return a portfolio summary dict.

    Returns None if the file doesn't exist or contains no open positions.

    Return structure:
    {
        "positions": [
            {
                "name": str,
                "symbol": str,
                "net_shares": float,
                "avg_cost_eur": float | None,    # avg EUR price paid per share
                "current_price_eur": float | None,
                "market_value_eur": float | None,
                "unrealized_pnl_eur": float | None,
                "unrealized_pnl_pct": float | None,
                "cost_basis_eur": float,          # total EUR invested in current holding
                "allocation_pct": float | None,
            },
            ...
        ],
        "total_market_value_eur": float | None,
        "total_cost_eur": float,
        "total_unrealized_pnl_eur": float | None,
    }
    """
    if csv_path is None:
        csv_path = os.environ.get("POSITIONS_CSV", "data/tr_positions.csv")

    if not os.path.exists(csv_path):
        print(f"  Info: {csv_path} not found — skipping portfolio context.", file=sys.stderr)
        return None

    rows = _parse_csv(csv_path)
    aggregated = _aggregate_positions(rows)
    open_pos = _open_positions(aggregated)

    if not open_pos:
        return None

    # Resolve tickers: hardcoded dict → cache → OpenFIGI
    cache = _load_cache()
    resolved: dict[str, tuple[str | None, str]] = {
        symbol: _get_ticker_info(symbol, cache) for symbol in open_pos
    }

    prices = _fetch_prices(open_pos, resolved)

    positions = []
    total_cost = 0.0
    total_market_value = 0.0
    has_all_prices = True

    for symbol, pos in open_pos.items():
        net_shares = pos["net_shares"]
        total_bought = pos["total_shares_bought"]

        # Avg cost: total EUR spent on buys / total shares bought
        avg_cost = pos["total_cost_eur"] / total_bought if total_bought > 0 else None

        # Cost basis for current holding: avg_cost * net_shares (FIFO approximation)
        cost_basis = avg_cost * net_shares if avg_cost else pos["total_cost_eur"]

        current_price = prices.get(symbol)
        if current_price is not None:
            market_value = current_price * net_shares
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else None
        else:
            market_value = None
            pnl = None
            pnl_pct = None

        # Skip minor positions below threshold before touching any running totals
        effective_value = market_value if market_value is not None else cost_basis
        if effective_value < MIN_POSITION_VALUE_EUR:
            continue

        total_cost += cost_basis
        if market_value is not None:
            total_market_value += market_value
        else:
            has_all_prices = False

        name = DISPLAY_NAMES.get(symbol, pos["name"])
        positions.append({
            "name": name,
            "symbol": symbol,
            "net_shares": net_shares,
            "avg_cost_eur": avg_cost,
            "current_price_eur": current_price,
            "market_value_eur": market_value,
            "unrealized_pnl_eur": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "cost_basis_eur": cost_basis,
            "allocation_pct": None,  # computed after totals
        })

    # Compute allocation %
    if has_all_prices and total_market_value > 0:
        for p in positions:
            if p["market_value_eur"] is not None:
                p["allocation_pct"] = p["market_value_eur"] / total_market_value * 100

    positions.sort(key=lambda p: (p["market_value_eur"] or 0), reverse=True)

    return {
        "positions": positions,
        "total_market_value_eur": total_market_value if has_all_prices else None,
        "total_cost_eur": total_cost,
        "total_unrealized_pnl_eur": (total_market_value - total_cost) if has_all_prices else None,
    }


# ---------------------------------------------------------------------------
# Prompt-ready formatter
# ---------------------------------------------------------------------------

def format_portfolio_for_prompt(summary: dict) -> str:
    """
    Render portfolio summary as a Markdown block for injection into the Claude prompt.
    """
    lines = ["## Portfolio Positions\n"]

    total_mv = summary.get("total_market_value_eur")
    total_cost = summary.get("total_cost_eur", 0)
    total_pnl = summary.get("total_unrealized_pnl_eur")

    if total_mv is not None:
        pnl_sign = "+" if (total_pnl or 0) >= 0 else ""
        lines.append(
            f"**Total Market Value:** €{total_mv:,.0f}  |  "
            f"**Total Cost:** €{total_cost:,.0f}  |  "
            f"**Unrealized P&L:** {pnl_sign}€{total_pnl:,.0f} "
            f"({pnl_sign}{total_pnl/total_cost*100:.1f}%)\n" if total_pnl is not None and total_cost else ""
        )
    else:
        lines.append(f"**Total Cost Basis:** €{total_cost:,.0f} (current prices partially unavailable)\n")

    lines.append(
        "| Asset | Shares | Avg Cost (€) | Price (€) | Value (€) | P&L (€) | P&L % | Alloc % |"
    )
    lines.append("|-------|--------|-------------|-----------|-----------|---------|-------|---------|")

    for p in summary["positions"]:
        avg = f"{p['avg_cost_eur']:.2f}" if p["avg_cost_eur"] else "—"
        price = f"{p['current_price_eur']:.2f}" if p["current_price_eur"] else "N/A"
        value = f"{p['market_value_eur']:,.0f}" if p["market_value_eur"] is not None else "N/A"
        pnl_e = f"{p['unrealized_pnl_eur']:+,.0f}" if p["unrealized_pnl_eur"] is not None else "N/A"
        pnl_p = f"{p['unrealized_pnl_pct']:+.1f}%" if p["unrealized_pnl_pct"] is not None else "N/A"
        alloc = f"{p['allocation_pct']:.1f}%" if p["allocation_pct"] is not None else "N/A"
        shares = f"{p['net_shares']:.4f}"

        lines.append(
            f"| {p['name']} | {shares} | {avg} | {price} | {value} | {pnl_e} | {pnl_p} | {alloc} |"
        )

    lines.append(
        "\n*Note: USD-priced assets converted to EUR at current spot. "
        "ETF/bond prices marked N/A if no yfinance feed available.*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI quick-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import io
    import json

    # Force UTF-8 output so € symbol prints correctly on Windows terminals
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    csv_file = sys.argv[1] if len(sys.argv) > 1 else "data/tr_positions.csv"
    summary = get_portfolio_summary(csv_file)
    if summary is None:
        print("No open positions found or file missing.")
        sys.exit(0)

    print(format_portfolio_for_prompt(summary))
    print("\n--- Raw summary ---")
    print(json.dumps(summary, indent=2, default=str))
