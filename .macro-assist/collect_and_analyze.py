"""
Macro-Assist: Daily macro intelligence pipeline.

Fetches FRED + market data, runs Claude analysis, writes a dated
companion note into the Obsidian vault (Journal/YYYY/MM-Month/).

Expects env vars: FRED_API_KEY, ANTHROPIC_API_KEY
"""

import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fredapi import Fred

from versions import PIPELINE_VERSION

# ---------------------------------------------------------------------------
# Module split (2026-08-20): the data-fetch, config, and LLM-analysis layers now
# live in focused modules. They are re-imported here so the historical public API
# (`from collect_and_analyze import fetch_fred_data, FRED_SERIES, run_config, ...`)
# keeps working for point_in_time.py, input_ledger.py, exogenous/, and the tests.
# ---------------------------------------------------------------------------
from pipeline_common import (
    _log, next_review_date, VAULT_ROOT, PROMPTS_DIR, REPO_ROOT, DATA_DIR, ACCURACY_JSON, POSITIONS_CSV,
    AnalysisOutput, AssetPrediction, PortfolioRiskOutput, SectorOpportunityOutput,
    _STRUCTURED_OUTPUT_AVAILABLE,
)
from fred_data import (
    FRED_SERIES, FRED_SERIES_FREQUENCY, _NET_LIQ_KEYS,
    _compute_net_liquidity, _fred_get_with_retry, fetch_fred_data,
)
from market_data import (
    MARKET_TICKERS, MARKET_LABELS, SECTOR_TICKERS, SECTOR_LABELS,
    SECTOR_PE_REFERENCE, SECTOR_HOLDINGS, _TECHNICAL_ASSETS,
    fetch_equity_momentum, fetch_market_data, fetch_sector_data, fetch_sector_fundamentals,
    detect_notable_moves, compute_technicals, format_technicals_block, fetch_cot_data,
)
from calendar_events import fetch_upcoming_events, _check_fomc_dates_expiry
from pipeline_config import (
    run_config, main_model, conviction_floor_on, _render_prompt, load_accuracy_context,
)
from llm_analysis import (
    fetch_youtube_context, adversarial_review, build_payload_preview, analyze_with_claude,
    _build_analysis_markdown,
)

# Public API re-exported for external importers (point_in_time.py, input_ledger.py,
# exogenous/sep.py, and the tests) plus this module's own orchestrator entry points.
# Listing them in __all__ documents the surface and marks the re-exports as "used".
__all__ = [
    # foundation / paths
    "_log", "next_review_date", "VAULT_ROOT", "PROMPTS_DIR", "REPO_ROOT", "DATA_DIR",
    "ACCURACY_JSON", "POSITIONS_CSV", "PIPELINE_VERSION",
    "AnalysisOutput", "AssetPrediction", "PortfolioRiskOutput", "SectorOpportunityOutput",
    "_STRUCTURED_OUTPUT_AVAILABLE",
    # FRED
    "FRED_SERIES", "FRED_SERIES_FREQUENCY", "_NET_LIQ_KEYS",
    "_compute_net_liquidity", "_fred_get_with_retry", "fetch_fred_data",
    # market / sector / technicals / COT
    "MARKET_TICKERS", "MARKET_LABELS", "SECTOR_TICKERS", "SECTOR_LABELS",
    "SECTOR_PE_REFERENCE", "SECTOR_HOLDINGS", "_TECHNICAL_ASSETS",
    "fetch_equity_momentum", "fetch_market_data", "fetch_sector_data", "fetch_sector_fundamentals",
    "detect_notable_moves", "compute_technicals", "format_technicals_block", "fetch_cot_data",
    # calendar
    "fetch_upcoming_events", "_check_fomc_dates_expiry",
    # config
    "run_config", "main_model", "conviction_floor_on", "_render_prompt", "load_accuracy_context",
    # llm analysis
    "fetch_youtube_context", "adversarial_review", "build_payload_preview", "analyze_with_claude",
    "_build_analysis_markdown",
    # local orchestrator
    "get_output_path", "validate_data", "build_note", "main",
]



def get_output_path(today: datetime) -> Path:
    """Return the output path, creating parent dirs as needed."""
    year = today.strftime("%Y")
    month_folder = today.strftime("%m-%B")          # e.g. "03-March"
    filename = today.strftime("%Y-%m-%d-%A") + "-macro.md"
    path = VAULT_ROOT / "Economy" / year / month_folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# Only series where a missing value makes the analysis structurally unsound.
# Monthly/lagging series (unemployment, m2, philly_fed_mfg) are NOT critical —
# they are regularly stale by design and the analysis degrades gracefully without them.
# treasury_2y is not critical — missing it loses the yield curve spread (logged as warning)
# but the 10Y rate and Fed Funds are sufficient for the macro regime read.
_CRITICAL_FRED   = ["fed_funds_rate", "treasury_10y", "cpi"]
_CRITICAL_MARKET = ["sp500", "vix", "gold"]


def validate_data(fred_data: dict, market_data: dict) -> None:
    """Abort on missing critical series; log OK otherwise."""
    missing_f = [k for k in _CRITICAL_FRED   if k not in fred_data]
    missing_m = [k for k in _CRITICAL_MARKET if k not in market_data]
    if missing_f or missing_m:
        if missing_f:
            _log("VALIDATE", "FAIL", f"critical FRED series missing: {', '.join(missing_f)}")
        if missing_m:
            _log("VALIDATE", "FAIL", f"critical market data missing: {', '.join(missing_m)}")
        sys.exit("Aborting — critical data unavailable.")
    _log("VALIDATE", "OK", "core data integrity check passed")


# ---------------------------------------------------------------------------
# Note assembly
# ---------------------------------------------------------------------------

def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def build_note(
    fred_data: dict,
    market_data: dict,
    analysis: "str | AnalysisOutput",
    today: datetime,
    sector_data: dict | None = None,
    quant_raw: dict | None = None,
) -> str:
    """Assemble the daily note.

    `quant_raw` is the raw quant-context dict from collect_quant_raw(); when it
    carries a fragility reading, a Fragility Monitor block is appended to the
    Data Snapshot. Like the rest of the snapshot this is added AFTER the LLM
    call, so the shadow monitor stays invisible to the model.
    """
    # Structured path (MA-1): convert AnalysisOutput → markdown string before assembly.
    # Meta-prompt leakage is impossible here — the model never wrote headings or constraints.
    if _STRUCTURED_OUTPUT_AVAILABLE and isinstance(analysis, AnalysisOutput):
        analysis = _build_analysis_markdown(analysis, today)

    date_str = today.strftime("%Y-%m-%d")
    day_name = today.strftime("%A")

    # Run config (WP-16 experiment arm) — recorded in frontmatter so the scorer
    # can attribute outcomes to the config that produced them.
    _rc = run_config()
    _onoff = lambda b: "on" if b else "off"
    _config_summary = (
        f"{_rc['profile']} · {_rc['model']} · floor={_onoff(_rc['conviction_floor'])} · "
        f"base_rate_first={_onoff(_rc['base_rate_first'])} · prune_rules={_onoff(_rc['prune_rules'])}"
    )

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

    # Fragility Monitor (Phase 16, shadow) — post-analysis, never in the prompt.
    fragility_section = ""
    if quant_raw:
        try:
            from quant_context import build_fragility_snapshot
            _frag_block = build_fragility_snapshot(quant_raw)
            if _frag_block:
                fragility_section = "\n" + _frag_block
        except Exception:
            fragility_section = ""

    return f"""---
date: {date_str}
day: {day_name}
type: macro-intelligence
agent_version: {PIPELINE_VERSION}
config: {_config_summary}
profile: {_rc['profile']}
model: {_rc['model']}
conviction_floor: {_onoff(_rc['conviction_floor'])}
base_rate_first: {_onoff(_rc['base_rate_first'])}
prune_rules: {_onoff(_rc['prune_rules'])}
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
{fragility_section}
---
*Generated by Macro-Assist · {today.strftime("%Y-%m-%d %H:%M")} UTC*
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _run_fetch_check() -> int:
    """
    Run every data-fetch function and report pass/fail for each source.
    Returns 0 if all critical sources succeeded, 1 if any failed.
    Does NOT call the LLM — safe to run without ANTHROPIC_API_KEY.
    """
    today = datetime.now(timezone.utc)
    _t0   = time.monotonic()
    _log("CHECK", "INFO", f"Data fetch check — {today.strftime('%Y-%m-%d %H:%M')} UTC")

    failures: list[str] = []

    # --- FRED ---
    try:
        fred      = Fred(api_key=os.environ["FRED_API_KEY"])
        fred_data = fetch_fred_data(fred)
        stale     = [k for k, v in fred_data.items() if isinstance(v, dict) and v.get("days_stale", 0) > 90]
        _log("CHECK", "WARN" if stale else "OK",
             f"FRED: {len(fred_data)} series" + (f" | stale>90d: {stale}" if stale else ""))
    except Exception as e:
        _log("CHECK", "FAIL", f"FRED: {e}")
        failures.append("FRED")
        fred_data, histories = {}, {}

    # --- Market data ---
    try:
        market_data, histories = fetch_market_data()
        _log("CHECK", "OK", f"Market: {len(market_data)} tickers")
    except Exception as e:
        _log("CHECK", "FAIL", f"Market: {e}")
        failures.append("Market")
        market_data, histories = {}, {}

    # --- Validation ---
    try:
        validate_data(fred_data, market_data)
        _log("CHECK", "OK", "Validation: passed")
    except Exception as e:
        _log("CHECK", "FAIL", f"Validation: {e}")
        failures.append("Validation")

    # --- Sector ETFs ---
    try:
        sector_data = fetch_sector_data()
        ok = len(sector_data)
        _log("CHECK", "OK" if ok == len(SECTOR_TICKERS) else "WARN",
             f"Sector ETFs: {ok}/{len(SECTOR_TICKERS)}")
        if ok == 0:
            failures.append("Sector ETFs")
    except Exception as e:
        _log("CHECK", "FAIL", f"Sector ETFs: {e}")
        failures.append("Sector ETFs")

    # --- Sector fundamentals ---
    try:
        sf = fetch_sector_fundamentals()
        _log("CHECK", "OK" if sf else "WARN", f"Sector fundamentals: {'ok' if sf else 'empty'}")
    except Exception as e:
        _log("CHECK", "WARN", f"Sector fundamentals: {e}")

    # --- COT ---
    try:
        cot = fetch_cot_data()
        _log("CHECK", "OK" if cot else "WARN", f"COT: {'ok' if cot else 'empty — see above'}")
    except Exception as e:
        _log("CHECK", "WARN", f"COT: {e}")

    # --- Technicals ---
    if histories:
        try:
            technicals = compute_technicals(histories)
            _log("CHECK", "OK", f"Technicals: {len(technicals)}/{len(_TECHNICAL_ASSETS)} assets")
        except Exception as e:
            _log("CHECK", "WARN", f"Technicals: {e}")

    # --- Portfolio ---
    try:
        from parse_positions import get_portfolio_summary
        ps = get_portfolio_summary(str(POSITIONS_CSV))
        _log("CHECK", "OK" if ps else "INFO",
             f"Portfolio: {'loaded' if ps else 'no data (POSITIONS_CSV absent or empty)'}")
    except Exception as e:
        _log("CHECK", "WARN", f"Portfolio: {e}")

    # --- Notable moves ---
    if market_data and histories:
        try:
            nm = detect_notable_moves(market_data, histories)
            _n = sum(1 for ln in nm.splitlines() if ln.startswith("- ")) if nm else 0
            _log("CHECK", "OK", f"Notable moves: {_n} detected")
        except Exception as e:
            _log("CHECK", "WARN", f"Notable moves: {e}")

    # --- Quant context ---
    if fred_data and market_data and histories:
        try:
            from quant_context import build_quant_context
            qc = build_quant_context(
                fred_data, today.date(),
                market_data=market_data,
                histories=histories,
            )
            if qc:
                _log("CHECK", "OK", "Quant context: vol forecasts + regime + conditionals built")
            else:
                _log("CHECK", "INFO",
                     "Quant context: no model data yet — run refit_models.py to activate")
        except Exception as e:
            _log("CHECK", "WARN", f"Quant context: {e}")

    _elapsed = int(time.monotonic() - _t0)
    if failures:
        _log("CHECK", "FAIL", f"FAILED sources: {failures} ({_elapsed}s)")
        return 1
    _log("CHECK", "OK", f"All data sources healthy ({_elapsed}s)")
    return 0


def _resolve_asof(raw: str | None) -> datetime:
    """The date this run is *for*, as an aware UTC datetime.

    GitHub's scheduler can deliver a scheduled run many hours late — 12h25m
    measured on 2026-08-28 — so the wall clock when the runner starts is not a
    safe proxy for the day the run belongs to. A run delayed past midnight would
    otherwise write the next day's note and silently leave the intended day empty.

    The pipeline's `plan` stage resolves the date once and passes the same value
    to every stage via --asof. Unset (a bare local run) falls back to the clock.
    The time-of-day is deliberately left as the real one so log timestamps stay
    honest; only the calendar date is pinned.
    """
    now = datetime.now(timezone.utc)
    if not raw:
        return now
    day = date.fromisoformat(raw)
    return now.replace(year=day.year, month=day.month, day=day.day)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="overwrite today's note if it already exists")
    parser.add_argument("--asof", default=None, metavar="YYYY-MM-DD",
                        help="date this run is for (default: today, UTC); pinned by the "
                             "pipeline so a delayed run still writes the right day")
    parser.add_argument("--fetch-only", action="store_true",
                        help="run data fetch checks only — no LLM call, no note written")
    args = parser.parse_args()

    if args.fetch_only:
        sys.exit(_run_fetch_check())

    today = _resolve_asof(args.asof)
    _t0   = time.monotonic()
    _log("PIPELINE", "INFO", f"Macro-Assist starting — {today.strftime('%Y-%m-%d %H:%M')} UTC")
    _check_fomc_dates_expiry(today)

    # Idempotency: skip if today's note already exists (bypass with --force)
    output_path = get_output_path(today)
    if output_path.exists() and not args.force:
        _log("PIPELINE", "INFO", f"note already exists for {today.strftime('%Y-%m-%d')} — skipping")
        sys.exit(0)

    fred      = Fred(api_key=os.environ["FRED_API_KEY"])
    fred_data = fetch_fred_data(fred)

    market_data, histories = fetch_market_data()

    validate_data(fred_data, market_data)

    # VIX term structure ratio: > 1.0 = backwardation (acute stress), < 1.0 = contango (calm)
    if "vix" in market_data and "vix3m" in market_data:
        market_data["vix_term_ratio"] = round(
            market_data["vix"]["price"] / market_data["vix3m"]["price"], 3
        )

    notable_moves = detect_notable_moves(market_data, histories)
    if notable_moves:
        _n_moves = sum(1 for ln in notable_moves.splitlines() if ln.startswith("- "))
        _log("NOTABLE", "WARN", f"{_n_moves} σ-move(s) detected")
    else:
        _log("NOTABLE", "OK", "no notable σ-moves today")

    sector_data = fetch_sector_data()
    _log("SECTORS", "WARN" if len(sector_data) < len(SECTOR_TICKERS) else "OK",
         f"{len(sector_data)}/{len(SECTOR_TICKERS)} sector ETFs fetched")

    # --- Quantitative context (Phase 12) ---
    quant_context = ""
    try:
        from quant_context import build_quant_context
        quant_context = build_quant_context(
            fred_data, today.date(),
            market_data=market_data,
            histories=histories,
        )
        if quant_context:
            _log("QUANT", "OK", "quantitative context block built")
        else:
            _log("QUANT", "INFO", "quantitative context unavailable (no models/data yet)")
    except Exception as _qc_exc:
        _log("QUANT", "WARN", f"quant context skipped: {type(_qc_exc).__name__}: {_qc_exc}")

    # --- Phase 14.3: log raw quant context outputs to JSONL ---
    # `quant_raw` is kept in scope: the fragility reading it carries is echoed to
    # the run log below and appended to the note's Data Snapshot (WP-16.A.5).
    quant_raw: dict = {}
    if quant_context:
        try:
            import json as _json
            from quant_context import collect_quant_raw
            _raw = collect_quant_raw(
                fred_data, today.date(),
                market_data=market_data,
                histories=histories,
            )
            if _raw:
                quant_raw = _raw
                _qlog_dir  = REPO_ROOT / "results" / "quant_context_log"
                _qlog_dir.mkdir(parents=True, exist_ok=True)
                _qlog_path = _qlog_dir / f"{today.strftime('%Y-%m-%d')}.jsonl"
                with open(_qlog_path, "a", encoding="utf-8") as _qlf:
                    _qlf.write(_json.dumps({
                        "date": today.strftime("%Y-%m-%d"),
                        "time": today.strftime("%H:%M:%S"),
                        **_raw,
                    }) + "\n")
                _log("QUANT_LOG", "OK", f"raw outputs → {_qlog_path.name}")
        except Exception as _ql_exc:
            _log("QUANT_LOG", "WARN", f"logging skipped: {type(_ql_exc).__name__}: {_ql_exc}")

    # --- Fragility monitor (Phase 16, shadow) — echo the logged reading ---
    # The monitor runs at FRAGILITY_MODE=log, so it renders nothing in the prompt;
    # without this the daily run gave no sign of it. Reuses the dict already
    # collected above — no extra compute, and it cannot drift from the JSONL.
    try:
        from quant_context import fragility_log_lines
        _frag_lines = fragility_log_lines(quant_raw)
        for _sec, _lvl, _msg in _frag_lines:
            _log(_sec, _lvl, _msg)
        if not _frag_lines:
            _log("FRAGILITY", "INFO", "no reading this run (insufficient history or fetch failed)")
    except Exception as _fg_exc:
        _log("FRAGILITY", "WARN", f"reading unavailable: {type(_fg_exc).__name__}: {_fg_exc}")

    analysis = analyze_with_claude(fred_data, market_data, today, sector_data, notable_moves, histories, quant_context)

    note = build_note(fred_data, market_data, analysis, today, sector_data, quant_raw=quant_raw)
    output_path.write_text(note, encoding="utf-8")
    _elapsed = int(time.monotonic() - _t0)
    _log("OUTPUT", "OK",
         f"note written → {output_path.relative_to(VAULT_ROOT)} ({_elapsed}s)")


if __name__ == "__main__":
    main()
