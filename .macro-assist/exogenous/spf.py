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

CONFIRMED 2026-07-14 against the published median-level workbooks for **TBOND,
TBILL, and UNEMP** — all identical: sheet `Median_Level`; columns YEAR, QUARTER,
<VAR>1..<VAR>6 (quarterly) + <VAR>A..<VAR>D (annual, ignored). Quarterly mapping
1=T-1, 2=T current, 3..6=T+1..T+4 (see RATE_HORIZONS). The published files carry a
malformed docProps/core.xml timestamp that crashes openpyxl — handled in
`_read_spf_workbook`. Still to verify: RGDP / CPI (growth-vs-level files may use a
different horizon layout). See HORIZON_NOTE.
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

# CONFIRMED against Median_TBOND_Level.xlsx (2026-07-14): the rate variables carry
# six quarterly columns TBOND1..TBOND6 (plus annual TBONDA..TBONDD, which are
# letter-suffixed and thus ignored by _horizon_columns). The quarterly columns map
# relative to the survey quarter T as:
#   1 → T-1 (prior-quarter backcast) · 2 → T (current) · 3..6 → T+1..T+4
# So a bare `horizon=1` is the least-useful backcast; use the named constants below.
RATE_HORIZONS: dict[str, int] = {
    "prev_q":    1,   # quarter before the survey (backcast)
    "current_q": 2,   # quarter of the survey (near-term nowcast)
    "q1_ahead":  3,
    "q2_ahead":  4,
    "q3_ahead":  5,
    "q4_ahead":  6,
}

HORIZON_NOTE = (
    "horizon is a 1-based position into the sorted numeric-suffixed forecast "
    "columns; for the rate variables (TBOND/TBILL) the mapping is CONFIRMED: "
    "1=T-1 backcast, 2=T current, 3..6=T+1..T+4 (use RATE_HORIZONS names). Other "
    "level variables (RGDP/CPI/UNEMP) may differ — verify against the SPF doc PDF."
)


def _resolve_horizon(horizon: "int | str") -> int:
    """Accept a RATE_HORIZONS name or a raw 1-based position."""
    if isinstance(horizon, str):
        if horizon not in RATE_HORIZONS:
            raise ValueError(f"unknown horizon name {horizon!r}; use {list(RATE_HORIZONS)} or an int")
        return RATE_HORIZONS[horizon]
    return horizon


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


def parse_spf(df: pd.DataFrame, var_code: str, horizon: "int | str" = "current_q") -> pd.Series:
    """Median forecast for one variable/horizon, indexed by survey release date.

    `df` is a raw SPF median-level worksheet (columns: YEAR, QUARTER, <VAR>1,
    <VAR>2, ...). `horizon` is a RATE_HORIZONS name (default "current_q") or a raw
    1-based position (see HORIZON_NOTE). NaN / non-numeric forecasts and rows with
    an unparseable year/quarter are dropped. The index is the *availability* date,
    so the series is directly point-in-time safe.
    """
    horizon = _resolve_horizon(horizon)
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


def _read_spf_workbook(path: "str | Path", sheet: "int | str" = 0) -> pd.DataFrame:
    """Read an SPF .xlsx, working around Philly Fed's malformed core.xml timestamp.

    The published median-level workbooks store a bare date (not datetime) in
    docProps/core.xml, which crashes openpyxl's strict property parser. We strip
    those dcterms from an in-memory copy before handing the bytes to pandas.
    """
    import io
    import re
    import warnings
    import zipfile

    with zipfile.ZipFile(path) as zin:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "docProps/core.xml":
                    data = re.sub(
                        rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:(created|modified)>",
                        b"", data,
                    )
                zout.writestr(item, data)
    buf.seek(0)
    with warnings.catch_warnings():
        # SPF workbooks carry an unparseable header/footer; harmless.
        warnings.filterwarnings("ignore", message="Cannot parse header or footer")
        return pd.read_excel(buf, sheet_name=sheet, engine="openpyxl")


def load_spf_file(path: "str | Path", var_code: str, horizon: "int | str" = "current_q",
                  sheet: "int | str" = 0) -> pd.Series:
    """Read a downloaded SPF median-level workbook → point-in-time forecast series."""
    df = _read_spf_workbook(path, sheet)
    return parse_spf(df, var_code, horizon)


def load_spf_snapshot(files: dict[str, "str | Path"], asof,
                      horizon: "int | str" = "current_q") -> dict[str, dict]:
    """Convenience: {our_var: xlsx_path} → point-in-time consensus snapshot for `asof`.

    `files` keys are SPF_VARIABLES codes (e.g. "treasury_10y"); each path is that
    variable's median-level workbook.
    """
    series_by_var = {
        var: load_spf_file(path, SPF_VARIABLES.get(var, var), horizon)
        for var, path in files.items()
    }
    return snapshot_from_series(series_by_var, asof)
