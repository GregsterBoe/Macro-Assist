"""
spf.py — WP-19.B L0 adapter: Philadelphia Fed Survey of Professional Forecasters.

The **economist-consensus** benchmark for the monetary / rates branch (DESIGN §6.5).
Free, quarterly, and **point-in-time**: each survey is dated by the quarter it was
conducted, so we can always ask "what was the consensus *available* on date D?"
without look-ahead — the core requirement from DESIGN §6.2.

Design mirrors the rest of the codebase: the **parsing + point-in-time math is
pure** (operates on a DataFrame, unit-tested with synthetic frames, no I/O), and a
thin **loader** reads the median-level `.xlsx` the user downloads from the Philly
Fed data-files page (needs `openpyxl`). No network in the tested core.

Variables used by the slice (SPF code): TBOND (10Y Treasury), TBILL (3M bill),
UNEMP, CPI, RGDP. TBOND/TBILL anchor the rates path directly; DXY and gold are
*downstream* of the rate path (handled by the L2 analyst, not SPF).

CONFIRM-ON-FIRST-RUN: the exact horizon-column layout differs by variable (rate
variables start at the current quarter; GDP/CPI files may lead with a prior-quarter
backcast). `parse_spf` selects horizon **by position** into the sorted numeric-
suffixed columns; verify the position→quarter mapping once per variable against the
SPF documentation PDF before trusting a specific horizon. See HORIZON_NOTE.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

# Our-concept → SPF variable code (worksheet/column prefix).
SPF_VARIABLES: dict[str, str] = {
    "treasury_10y": "TBOND",
    "treasury_3m":  "TBILL",
    "unemployment": "UNEMP",
    "cpi":          "CPI",
    "rgdp":         "RGDP",
}

# SPF surveys are released roughly mid-quarter (Q1≈mid-Feb, Q2≈mid-May,
# Q3≈mid-Aug, Q4≈mid-Nov). We map a survey (year, quarter) to a conservative
# *availability* date so point-in-time queries never use a survey before it was
# published. Day 15 is a deliberately safe within-month anchor.
_SPF_RELEASE_MONTH: dict[int, int] = {1: 2, 2: 5, 3: 8, 4: 11}
_SPF_RELEASE_DAY = 15

HORIZON_NOTE = (
    "horizon is a 1-based position into the sorted numeric-suffixed forecast "
    "columns (e.g. TBOND1, TBOND2, ...). Rate variables start at the current "
    "quarter; some level variables lead with a prior-quarter backcast. Verify the "
    "position→quarter mapping per variable against the SPF documentation PDF."
)


# ---------------------------------------------------------------------------
# Pure: release-date + parsing + point-in-time selection (no I/O)
# ---------------------------------------------------------------------------

def survey_release_date(year: int, quarter: int) -> date:
    """Conservative availability date for the (year, quarter) SPF survey."""
    if quarter not in _SPF_RELEASE_MONTH:
        raise ValueError(f"quarter must be 1-4, got {quarter!r}")
    return date(int(year), _SPF_RELEASE_MONTH[quarter], _SPF_RELEASE_DAY)


def _find_col(columns: list, target: str):
    """Case-insensitive exact-name column lookup; None if absent."""
    for c in columns:
        if str(c).strip().lower() == target:
            return c
    return None


def _horizon_columns(columns: list, var_code: str) -> list:
    """Numeric-suffixed forecast columns for a variable, sorted by the suffix.

    e.g. for TBOND → [TBOND1, TBOND2, ...] in ascending horizon order.
    """
    var = var_code.upper()
    hits = []
    for c in columns:
        s = str(c).strip().upper()
        if s.startswith(var) and s[len(var):].isdigit():
            hits.append((int(s[len(var):]), c))
    return [c for _, c in sorted(hits, key=lambda t: t[0])]


def parse_spf(df: pd.DataFrame, var_code: str, horizon: int = 1) -> pd.Series:
    """Median forecast for one variable/horizon, indexed by survey release date.

    `df` is a raw SPF median-level worksheet (columns: YEAR, QUARTER, <VAR>1,
    <VAR>2, ...). `horizon` is 1-based (see HORIZON_NOTE). NaN / non-numeric
    forecasts and rows with an unparseable year/quarter are dropped. The index is
    the *availability* date, so the series is directly point-in-time safe.
    """
    cols = list(df.columns)
    ycol = _find_col(cols, "year")
    qcol = _find_col(cols, "quarter")
    if ycol is None or qcol is None:
        raise ValueError("SPF frame must have YEAR and QUARTER columns")
    hz = _horizon_columns(cols, var_code)
    if not hz:
        raise ValueError(f"no numeric-suffixed forecast columns for {var_code!r}")
    if not (1 <= horizon <= len(hz)):
        raise ValueError(f"horizon {horizon} out of range 1..{len(hz)} for {var_code!r}")
    hcol = hz[horizon - 1]

    out: dict[pd.Timestamp, float] = {}
    for _, row in df.iterrows():
        try:
            y, q = int(row[ycol]), int(row[qcol])
        except (ValueError, TypeError):
            continue
        val = pd.to_numeric(row[hcol], errors="coerce")
        if pd.isna(val):
            continue
        out[pd.Timestamp(survey_release_date(y, q))] = float(val)
    return pd.Series(out, name=f"{var_code.upper()}_h{horizon}", dtype=float).sort_index()


def latest_before(series: pd.Series, asof) -> Optional[tuple[date, float]]:
    """Most recent (release_date, value) available on/before `asof` — point-in-time.

    Returns None if no survey had been released by then.
    """
    asof_ts = pd.Timestamp(asof)
    prior = series[series.index <= asof_ts]
    if prior.empty:
        return None
    return (prior.index[-1].date(), float(prior.iloc[-1]))


def snapshot_from_series(series_by_var: dict[str, pd.Series], asof) -> dict[str, dict]:
    """Point-in-time consensus snapshot across variables for `asof`.

    {var: {"as_of_survey": date, "value": float}} — variables with no survey
    released yet are omitted.
    """
    snap: dict[str, dict] = {}
    for var, series in series_by_var.items():
        got = latest_before(series, asof)
        if got is not None:
            release, value = got
            snap[var] = {"as_of_survey": release.isoformat(), "value": value}
    return snap


# ---------------------------------------------------------------------------
# IO shell — reads the downloaded .xlsx (needs openpyxl; user-run)
# ---------------------------------------------------------------------------

# Philly Fed data-files landing page (download median-level files from here).
SPF_DATA_FILES_PAGE = "https://www.philadelphiafed.org/surveys-and-data/data-files"


def load_spf_file(path: "str | Path", var_code: str, horizon: int = 1,
                  sheet: "int | str" = 0) -> pd.Series:
    """Read a downloaded SPF median-level workbook → point-in-time forecast series."""
    df = pd.read_excel(path, sheet_name=sheet)
    return parse_spf(df, var_code, horizon)


def load_spf_snapshot(files: dict[str, "str | Path"], asof, horizon: int = 1) -> dict[str, dict]:
    """Convenience: {our_var: xlsx_path} → point-in-time consensus snapshot for `asof`.

    `files` keys are SPF_VARIABLES codes (e.g. "treasury_10y"); each path is that
    variable's median-level workbook.
    """
    series_by_var = {
        var: load_spf_file(path, SPF_VARIABLES.get(var, var), horizon)
        for var, path in files.items()
    }
    return snapshot_from_series(series_by_var, asof)
