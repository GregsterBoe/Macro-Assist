"""
sep.py — WP-19.B L0 adapter: FOMC Summary of Economic Projections (the "dot plot").

The **policymaker-consensus** benchmark for the monetary/rates branch (DESIGN §6.5),
the second of the two non-market anchors. Pulled from FRED via the existing adapter
— no new dependency:
  - FEDTARMD   : median projected fed-funds rate at each *target year-end*
  - FEDTARMDLR : median projected fed-funds rate over the *longer run*

The **SPF-vs-SEP gap** (economists' short-rate view vs the Fed's own dots) is the
expectations-tension signal DESIGN §6.5 calls for. It is deliberately a *directional*
read with documented proxy assumptions, not a precise instrument (see `short_rate_gap`).

POINT-IN-TIME: `fred.get_series` returns the **latest** vintage, i.e. the *current*
dot plot — correct for the live/forward branch (the only mode we validate; DESIGN
§6.2). A historical backtest would need ALFRED vintages and is out of scope.

CONFIRM-ON-FIRST-RUN: the exact FEDTARMD index encoding (target-year dates vs
meeting dates) isn't verifiable without a FRED key; `parse_sep_path` groups by
calendar year and takes the latest value per year, which is robust to either. Run
`python -m exogenous.sep` (FRED_API_KEY set) once to confirm the shape.

Pure parsing + gap math (top) are unit-tested; the fetch shell (bottom) needs a
FRED key (user-run, like input_ledger / regime_backtest).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd

SEP_SERIES = {
    "fed_funds_median":         "FEDTARMD",    # median, by target year-end
    "fed_funds_median_longrun": "FEDTARMDLR",  # median, longer run
}

# Gap band: |gap| below this (percentage points) reads as "aligned".
GAP_ALIGNED_BAND = 0.10


# ---------------------------------------------------------------------------
# Pure: parse the SEP path + the SPF-vs-SEP gap (no I/O)
# ---------------------------------------------------------------------------

def parse_sep_path(series: pd.Series) -> dict[int, float]:
    """FEDTARMD Series → {target_year: median_fed_funds}.

    Robust to the index being target-year dates or meeting dates: groups by
    calendar year and takes the latest non-NaN value per year.
    """
    out: dict[int, float] = {}
    s = series.dropna()
    for ts, val in s.items():
        year = pd.Timestamp(ts).year
        out[year] = float(val)   # dict insertion is time-ordered → last wins per year
    return out


def latest_value(series: pd.Series) -> Optional[float]:
    """Most recent non-NaN value (e.g. the current longer-run dot)."""
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def short_rate_gap(
    spf_short_rate: Optional[float],
    sep_path_by_year: dict[int, float],
    year: int,
) -> Optional[dict]:
    """Directional short-rate gap: economists (SPF) vs the Fed's dots (SEP).

    `gap = spf_short_rate − sep_year_end_ff` for the given calendar `year`.
    **+ gap ⇒ economists see higher short rates than the Fed's dots** (the Fed
    projects more easing / economists are relatively hawkish); − is the reverse.

    Approximation, stated plainly: SPF's 3-month T-bill (quarterly average) vs the
    SEP's year-end fed-funds median — different instrument and timing, so read the
    *sign and size* as tension, not a precise basis-point spread.
    """
    sep_val = sep_path_by_year.get(year)
    if spf_short_rate is None or sep_val is None:
        return None
    gap = round(float(spf_short_rate) - float(sep_val), 3)
    read = ("economists above Fed dots" if gap > GAP_ALIGNED_BAND
            else "economists below Fed dots" if gap < -GAP_ALIGNED_BAND
            else "aligned")
    return {
        "year":          year,
        "spf_short_rate": round(float(spf_short_rate), 3),
        "sep_fed_funds":  round(float(sep_val), 3),
        "gap":            gap,
        "read":           read,
        "caveat":         "approx: SPF 3M-bill quarterly avg vs SEP year-end "
                          "fed-funds median — different instrument & timing; "
                          "read sign/size as tension, not a precise spread.",
    }


# ---------------------------------------------------------------------------
# IO shell — fetch SEP from FRED (needs FRED_API_KEY; user-run)
# ---------------------------------------------------------------------------

def fetch_sep(fred=None) -> dict:
    """Pull the current SEP fed-funds dot-plot path + longer-run median from FRED.

    Returns {path_by_year, longer_run, retrieved}. Reuses the pipeline's retrying
    FRED getter; pass a `Fred` instance or let it build one from FRED_API_KEY.
    """
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from collect_and_analyze import _fred_get_with_retry  # reuse retry/backoff
    from fredapi import Fred

    if fred is None:
        fred = Fred(api_key=os.environ["FRED_API_KEY"])

    ff = _fred_get_with_retry(fred, SEP_SERIES["fed_funds_median"], "2015-01-01")
    lr = _fred_get_with_retry(fred, SEP_SERIES["fed_funds_median_longrun"], "2015-01-01")
    return {
        "path_by_year": parse_sep_path(ff),
        "longer_run":   latest_value(lr),
        "retrieved":    datetime.now(timezone.utc).date().isoformat(),
    }


def consensus_gap(fred=None, spf_short_rate: Optional[float] = None,
                  year: Optional[int] = None) -> dict:
    """Assemble the SEP path and, if an SPF short-rate is supplied, the gap.

    `spf_short_rate` is the point-in-time SPF TBILL consensus (from
    `spf.load_spf_file(..., "TBILL")` → `latest_before`); `year` defaults to the
    current calendar year.
    """
    sep = fetch_sep(fred)
    year = year or date.today().year
    gap = short_rate_gap(spf_short_rate, sep["path_by_year"], year)
    return {**sep, "gap": gap}


def _main() -> None:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Fetch the SEP dot-plot path (+ optional SPF gap)")
    ap.add_argument("--spf-tbill", type=str, default="",
                    help="path to Median_TBILL_Level.xlsx to compute the SPF-vs-SEP gap")
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()

    spf_short = None
    if args.spf_tbill:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from exogenous.spf import load_spf_file, latest_before
        s = load_spf_file(args.spf_tbill, "TBILL")
        got = latest_before(s, date.today())
        spf_short = got[1] if got else None
        print(f"SPF TBILL (current-q) as-of today: {got}")

    out = consensus_gap(spf_short_rate=spf_short, year=args.year)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _main()
