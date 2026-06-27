#!/usr/bin/env python3
"""
input_ledger.py — WP-18.2: cheap input-quality proxies (zero-cost, no LLM).

Phase 18 points Phase-17's keep/cut discipline at the LLM *input payload*. This
module is the first, cheapest screen: per input series it computes

  - staleness     days since the last observation (a stale series is low-value)
  - robust sigma  MAD-scaled dispersion in the series' own units (human-readable)
  - entropy       normalised Shannon entropy of the (clipped) level distribution
                  in [0, 1]; a near-constant / dead series → ~0
  - redundancy    max |corr| with any *other* input, computed on first
                  differences (not levels — trending levels correlate spuriously)

and ranks inputs by a transparent information-density score so the stale / dead /
redundant payload floats to the top as prune candidates for the expensive
outcome-grounded ablation (WP-18.4).

**This is a SCREEN, not a verdict.** Low score ⇒ *candidate* for ablation; it does
not by itself prove an input is worthless (the model may combine weak inputs, or a
redundant series may still be the cleaner of a pair). Verdicts come from WP-18.4.

The math (top of file) is pure and unit-tested with synthetic series — no network.
The IO shell (bottom) reuses the live fetchers to build the real FRED + market +
sector panel, so it needs FRED_API_KEY (run it yourself, like regime_backtest.py):

    FRED_API_KEY=... python .macro-assist/input_ledger.py
    FRED_API_KEY=... python .macro-assist/input_ledger.py --years 7 --corr-threshold 0.85
    # optional section token-cost table from a payload preview:
    FRED_API_KEY=... python .macro-assist/input_ledger.py --preview results/llm_payload_preview/2026-06-26.md

Writes results/input_ledger/<date>.md and .json.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# A series is "stale" once it exceeds the cadence-appropriate age. Generous —
# meant to catch genuinely dropped/abandoned feeds, not a late print.
FRESHNESS_LIMIT_DAYS: dict[str, int] = {
    "daily":     5,
    "weekly":    12,
    "monthly":   45,
    "quarterly": 100,
    "unknown":   45,
}

ENTROPY_BINS = 10            # histogram bins for the level-distribution entropy
DEAD_ENTROPY = 0.15          # below this the series is ~constant → "dead"
DEFAULT_CORR_THRESHOLD = 0.80  # |corr| on changes at/above which two inputs are "redundant"


# ---------------------------------------------------------------------------
# Pure proxy math — no I/O, fully unit-testable on synthetic series
# ---------------------------------------------------------------------------

def staleness_days(last_obs: date, asof: date) -> int:
    """Calendar days between the last observation and the as-of date."""
    return (asof - last_obs).days


def is_stale(days: int, frequency: str) -> bool:
    return days > FRESHNESS_LIMIT_DAYS.get(frequency, FRESHNESS_LIMIT_DAYS["unknown"])


def robust_sigma(values: "pd.Series | np.ndarray") -> float:
    """MAD-scaled robust standard deviation (1.4826 · MAD). 0 for a constant series.

    Robust to the outliers that wreck a plain std on macro series (COVID prints).
    """
    arr = np.asarray(pd.Series(values).dropna(), dtype=float)
    if arr.size == 0:
        return 0.0
    med = np.median(arr)
    mad = np.median(np.abs(arr - med))
    return float(1.4826 * mad)


def normalized_entropy(values: "pd.Series | np.ndarray", bins: int = ENTROPY_BINS) -> float:
    """Normalised Shannon entropy of the level distribution, in [0, 1].

    Values are clipped to the [1st, 99th] percentile before equal-width binning so
    a single outlier can't collapse everything into one bin and fake a dead series.
    A constant (or all-but-constant) series → 0; a richly varying one → ~1.
    """
    arr = np.asarray(pd.Series(values).dropna(), dtype=float)
    if arr.size < 2:
        return 0.0
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return 0.0  # no spread → dead
    clipped = np.clip(arr, lo, hi)
    counts, _ = np.histogram(clipped, bins=bins, range=(lo, hi))
    total = counts.sum()
    if total == 0:
        return 0.0
    p = counts[counts > 0] / total
    h = -np.sum(p * np.log(p))
    return float(h / math.log(bins))


def correlation_redundancy(
    panel: pd.DataFrame,
    threshold: float = DEFAULT_CORR_THRESHOLD,
    min_nonzero_frac: float = 0.6,
) -> dict:
    """Redundancy from pairwise correlation of first differences.

    Levels of macro series are non-stationary and correlate spuriously, so we
    correlate *changes* (diff). But a low-frequency series forward-filled to a
    daily panel has a mostly-zero change vector, and correlating that against a
    genuinely daily series manufactures artifacts. So we assess redundancy **only
    among series that actually move at the panel frequency** (non-zero change
    fraction ≥ `min_nonzero_frac`); the rest are marked *not assessed* and judged
    by staleness + entropy instead. Returns:
      - corr:      the (signed) correlation matrix (active series) as a nested dict
      - max_abs:   {series: {"value": float|None, "partner": str|None,
                   "assessed": bool}} — strongest |corr| with any *other* active
                   input (the per-series redundancy score)
      - pairs:     [(a, b, corr)] above threshold, sorted by |corr| desc
      - assessed:  the list of daily-active series the matrix was computed over
    """
    cols = list(panel.columns)
    changes = panel.diff()
    active = [
        s for s in cols
        if (ch := changes[s].dropna()).size and float((ch != 0).mean()) >= min_nonzero_frac
    ]
    # Need overlapping observations; require at least 3 joint points per pair.
    corr = (changes[active].dropna(how="all").corr(min_periods=3)
            if active else pd.DataFrame())

    max_abs: dict[str, dict] = {}
    for s in cols:
        if s not in active or s not in corr.columns:
            max_abs[s] = {"value": None, "partner": None, "assessed": False}
            continue
        row = corr[s].drop(labels=[s], errors="ignore").dropna()
        if row.empty:
            max_abs[s] = {"value": 0.0, "partner": None, "assessed": True}
            continue
        partner = row.abs().idxmax()
        max_abs[s] = {"value": round(float(row[partner]), 4),
                      "partner": partner, "assessed": True}

    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a in corr.columns and b in corr.index:
                r = corr.at[b, a]
                if pd.notna(r) and abs(r) >= threshold:
                    pairs.append((a, b, round(float(r), 4)))
    pairs.sort(key=lambda t: abs(t[2]), reverse=True)

    corr_dict = {a: {b: (round(float(corr.at[b, a]), 4) if pd.notna(corr.at[b, a]) else None)
                     for b in active} for a in active}
    return {"corr": corr_dict, "max_abs": max_abs, "pairs": pairs, "assessed": active}


def token_estimate(text: str) -> int:
    """Cheap, tokenizer-free token estimate (~4 chars/token for English prose)."""
    return max(0, round(len(text) / 4))


def info_score(entropy: float, max_abs_corr: float) -> float:
    """Transparent information-density screen in [0, 1].

    High when the series carries variation (entropy) that is *not* duplicated by a
    sibling input (1 − redundancy). Deliberately simple — the components stay
    visible in the ledger so the score is never a black box.
    """
    return round(entropy * (1.0 - min(abs(max_abs_corr), 1.0)), 4)


# ---------------------------------------------------------------------------
# Ledger assembly
# ---------------------------------------------------------------------------

@dataclass
class SeriesEntry:
    name: str
    group: str          # fred | market | sector
    n_obs: int
    last_obs: str
    days_stale: int
    frequency: str
    stale: bool
    robust_sigma: float
    entropy: float
    max_abs_corr: Optional[float]
    redundant_with: Optional[str]
    redundant: bool
    redundancy_assessed: bool
    info_score: float

    def flags(self) -> str:
        f = []
        if self.stale:
            f.append("STALE")
        if self.entropy < DEAD_ENTROPY:
            f.append("DEAD")
        if self.redundant:
            f.append("REDUNDANT")
        if not self.redundancy_assessed:
            f.append("redund-n/a")
        return ",".join(f) or "-"


def build_ledger(
    panel: pd.DataFrame,
    groups: dict[str, str],
    frequency_map: dict[str, str],
    asof: date,
    corr_threshold: float = DEFAULT_CORR_THRESHOLD,
    section_costs: Optional[dict[str, int]] = None,
    last_obs_map: Optional[dict[str, date]] = None,
) -> dict:
    """Assemble the input ledger from an aligned level panel.

    `panel` columns are input names; `groups` maps name -> group;
    `frequency_map` maps name -> cadence; `section_costs` (optional) maps a
    payload section name -> char count (for the prompt-economy view).
    `last_obs_map` (optional) gives each series' **true** last-observation date —
    pass it when the panel was forward-filled, or staleness collapses to ~0 for
    every series. Falls back to the panel's last index per column.
    """
    redun = correlation_redundancy(panel, corr_threshold)
    last_obs_map = last_obs_map or {}
    entries: list[SeriesEntry] = []

    for name in panel.columns:
        col = panel[name].dropna()
        if col.empty:
            continue
        if name in last_obs_map:
            last_obs_date = last_obs_map[name]
        else:
            last_obs = col.index[-1]
            last_obs_date = last_obs.date() if hasattr(last_obs, "date") else last_obs
        freq = frequency_map.get(name, "unknown")
        days = staleness_days(last_obs_date, asof)
        ent = normalized_entropy(col)
        mac = redun["max_abs"].get(name, {"value": None, "partner": None, "assessed": False})
        assessed = mac.get("assessed", True)
        corr_val = mac["value"]
        redundant = assessed and corr_val is not None and abs(corr_val) >= corr_threshold
        score = info_score(ent, corr_val) if (assessed and corr_val is not None) else round(ent, 4)
        entries.append(SeriesEntry(
            name=name,
            group=groups.get(name, "unknown"),
            n_obs=int(col.size),
            last_obs=last_obs_date.isoformat(),
            days_stale=days,
            frequency=freq,
            stale=is_stale(days, freq),
            robust_sigma=round(robust_sigma(col), 4),
            entropy=round(ent, 4),
            max_abs_corr=corr_val,
            redundant_with=mac["partner"],
            redundant=redundant,
            redundancy_assessed=assessed,
            info_score=score,
        ))

    # Worst (most prunable) first: lowest info density.
    entries.sort(key=lambda e: e.info_score)

    return {
        "as_of": asof.isoformat(),
        "corr_threshold": corr_threshold,
        "n_inputs": len(entries),
        "entries": [asdict(e) | {"flags": e.flags()} for e in entries],
        "redundant_pairs": redun["pairs"],
        "section_costs": section_costs or {},
    }


def render_ledger_md(ledger: dict) -> list[str]:
    """Render the ledger dict as scannable markdown lines."""
    lines = [
        f"# Input Ledger — {ledger['as_of']}",
        "",
        "WP-18.2 cheap input-quality proxies (zero LLM cost). **A screen, not a "
        "verdict** — low-density / flagged inputs are *candidates* for the WP-18.4 "
        "ablation, not proven dead weight.",
        "",
        f"- {ledger['n_inputs']} inputs scored · redundancy threshold "
        f"|corr|≥{ledger['corr_threshold']} (on first differences)",
        "- `info_score = entropy · (1 − max|corr|)` — lower = more prunable. "
        "Flags: STALE (past cadence), DEAD (entropy<"
        f"{DEAD_ENTROPY}), REDUNDANT (≥threshold), redund-n/a (sub-daily series — "
        "redundancy not assessed; ffilling makes its change-correlations unreliable, "
        "so it is ranked by entropy alone).",
        "",
        "## Inputs ranked by information density (most prunable first)",
        "",
        "| Input | Group | Score | Entropy | Max|corr| | Redundant w/ | Stale(d) | Flags |",
        "|-------|-------|------:|--------:|----------:|--------------|---------:|-------|",
    ]
    for e in ledger["entries"]:
        corr = e["max_abs_corr"]
        corr_str = f"{corr:.3f}" if corr is not None else "n/a"
        lines.append(
            f"| {e['name']} | {e['group']} | {e['info_score']:.3f} | "
            f"{e['entropy']:.3f} | {corr_str} | "
            f"{e['redundant_with'] or '—'} | {e['days_stale']} | {e['flags']} |"
        )

    pairs = ledger.get("redundant_pairs") or []
    lines += ["", "## High-redundancy pairs (|corr| on changes ≥ threshold)", ""]
    if pairs:
        lines.append("| A | B | corr |")
        lines.append("|---|---|-----:|")
        for a, b, r in pairs:
            lines.append(f"| {a} | {b} | {r:+.3f} |")
    else:
        lines.append("_None above threshold._")

    costs = ledger.get("section_costs") or {}
    if costs:
        total = sum(costs.values()) or 1
        lines += ["", "## Payload section token cost (prompt economy)", "",
                  "| Section | Chars | ~Tokens | % |",
                  "|---------|------:|--------:|--:|"]
        for name, chars in sorted(costs.items(), key=lambda kv: -kv[1]):
            lines.append(
                f"| {name} | {chars} | {token_estimate('x' * chars)} | "
                f"{100 * chars / total:.0f}% |"
            )
    return lines


# ---------------------------------------------------------------------------
# IO shell — builds the real panel (needs FRED_API_KEY + network)
# ---------------------------------------------------------------------------

def _parse_preview_section_costs(path: Path) -> dict[str, int]:
    """Parse '- <section>: <n> lines / <m> chars' rows from a payload preview."""
    costs: dict[str, int] = {}
    if not path.exists():
        return costs
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"-\s+(.+?):\s+\d+\s+lines\s*/\s*(\d+)\s+chars", line)
        if m:
            costs[m.group(1).strip()] = int(m.group(2))
    return costs


def collect_panel(
    years: int = 5,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, date]]:
    """Build an aligned daily level panel across FRED + market + sector inputs.

    Reuses the live fetch helpers so the ledger scores the *same* universe the
    pipeline feeds the model. Returns (panel, groups, frequency_map, last_obs) —
    `last_obs` carries each series' **true** last-print date (captured before the
    forward-fill) so staleness is real rather than the ffilled panel's last day.
    """
    from fredapi import Fred
    import yfinance as yf
    from collect_and_analyze import (
        FRED_SERIES, FRED_SERIES_FREQUENCY, MARKET_TICKERS, SECTOR_TICKERS,
        _fred_get_with_retry,
    )

    import os
    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    start = (datetime.now(timezone.utc).date() - timedelta(days=365 * years)).isoformat()

    series: dict[str, pd.Series] = {}
    groups: dict[str, str] = {}
    freq: dict[str, str] = {}
    last_obs: dict[str, date] = {}

    for name, sid in FRED_SERIES.items():
        try:
            s = _fred_get_with_retry(fred, sid, start)
            if s is not None and not s.empty:
                s.index = pd.to_datetime(s.index)
                series[name] = s
                groups[name] = "fred"
                freq[name] = FRED_SERIES_FREQUENCY.get(name, "unknown")
                last_obs[name] = s.index[-1].date()
        except Exception as e:  # noqa: BLE001 — CLI convenience
            print(f"  warn: FRED {sid} ({name}) failed: {e}")

    for grp, tickers in (("market", MARKET_TICKERS), ("sector", SECTOR_TICKERS)):
        for name, tk in tickers.items():
            try:
                hist = yf.Ticker(tk).history(start=start)
                if not hist.empty:
                    close = hist["Close"]
                    close.index = close.index.tz_localize(None)
                    series[name] = close
                    groups[name] = grp
                    freq[name] = "daily"
                    last_obs[name] = close.index[-1].date()
            except Exception as e:  # noqa: BLE001
                print(f"  warn: {tk} ({name}) failed: {e}")

    # Align on a shared business-day index, forward-filling each series from its
    # own first valid print (so monthly/weekly series carry between releases).
    # NB: ffill is for the entropy/correlation panel only — staleness uses the
    # pre-ffill `last_obs` dates above.
    panel = pd.DataFrame(series).sort_index()
    panel = panel.resample("B").last().ffill()
    return panel, groups, freq, last_obs


def main() -> None:
    ap = argparse.ArgumentParser(description="WP-18.2 input-quality ledger")
    ap.add_argument("--years", type=int, default=5, help="history window (default 5)")
    ap.add_argument("--corr-threshold", type=float, default=DEFAULT_CORR_THRESHOLD)
    ap.add_argument("--preview", type=str, default="",
                    help="optional payload-preview .md to add a section token-cost table")
    args = ap.parse_args()

    print(f"Building input panel ({args.years}y history) …")
    panel, groups, freq, last_obs = collect_panel(args.years)
    print(f"  panel: {panel.shape[1]} inputs × {panel.shape[0]} business days")

    repo_root = Path(__file__).resolve().parent.parent
    section_costs = (
        _parse_preview_section_costs(repo_root / args.preview) if args.preview else {}
    )

    asof = datetime.now(timezone.utc).date()
    ledger = build_ledger(panel, groups, freq, asof, args.corr_threshold,
                          section_costs, last_obs_map=last_obs)

    out_dir = repo_root / "results" / "input_ledger"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{asof.isoformat()}.md"
    json_path = out_dir / f"{asof.isoformat()}.json"
    md_path.write_text("\n".join(render_ledger_md(ledger)) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    print(f"\nLedger written to: {md_path}")
    print(f"JSON written to:   {json_path}\n")
    print("\n".join(render_ledger_md(ledger)))


if __name__ == "__main__":
    main()
