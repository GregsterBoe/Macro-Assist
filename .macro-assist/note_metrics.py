"""
note_metrics.py — The note's headline numbers, copied into its frontmatter.

The daily note carries its numbers in markdown tables, which a vault tool
(Obsidian's properties, Dataview, Tracker) cannot read. This module reads the
*rendered* note and writes the numbers it finds back as frontmatter keys, so a
vault can chart them over time.

It reads the note's own text rather than the dicts that built it on purpose:
one code path serves the live note (`collect_and_analyze.build_report`) and the
backfill of past notes (`backfill_note_metrics.py`), and the frontmatter can
never say a number the body does not. A metric the body does not show — a feed
that returned `nan`, a table an older note did not have — is left out, never
written as a blank or a zero.

The keys are a copy for charting, not a new reading: nothing in the pipeline
reads them back.
"""
from __future__ import annotations

import re

_NUM = r"(-?[\d,]*\.?\d+)"

# key → the table row it is copied from. Market rows are anchored on the change
# arrow so they never match the volatility or outlook tables, which reuse the
# same asset names.
METRICS: dict[str, re.Pattern[str]] = {
    "fragility":      re.compile(r"^\| Composite \| " + _NUM + r"/100", re.M),
    "vix":            re.compile(r"^\| VIX \| " + _NUM + r" \| [▲▼]", re.M),
    "sp500":          re.compile(r"^\| S&P 500 \| " + _NUM + r" \| [▲▼]", re.M),
    "nasdaq":         re.compile(r"^\| Nasdaq \| " + _NUM + r" \| [▲▼]", re.M),
    "gold":           re.compile(r"^\| Gold \| " + _NUM + r" \| [▲▼]", re.M),
    "wti_oil":        re.compile(r"^\| WTI Oil \| " + _NUM + r" \| [▲▼]", re.M),
    "dxy":            re.compile(r"^\| DXY \| " + _NUM + r" \| [▲▼]", re.M),
    "bitcoin":        re.compile(r"^\| Bitcoin \| " + _NUM + r" \| [▲▼]", re.M),
    "fed_funds":      re.compile(r"^\| Fed Funds Rate\s*\| " + _NUM + r"%", re.M),
    "us10y":          re.compile(r"^\| 10Y Treasury\s*\| " + _NUM + r"%", re.M),
    "us2y":           re.compile(r"^\| 2Y Treasury\s*\| " + _NUM + r"%", re.M),
    "yield_curve":    re.compile(r"^\| Yield Curve \(10-2Y\)\s*\| " + _NUM + r"%", re.M),
    "cpi_yoy":        re.compile(r"^\| CPI YoY\s*\| " + _NUM + r"%", re.M),
    "unemployment":   re.compile(r"^\| Unemployment\s*\| " + _NUM + r"%", re.M),
    "real_yield_10y": re.compile(r"^\| 10Y Real Yield\s*\| " + _NUM + r"%", re.M),
    "breakeven_10y":  re.compile(r"^\| 10Y Breakeven\s*\| " + _NUM + r"%", re.M),
    "nfci":           re.compile(r"^\| NFCI\s*\| " + _NUM + r" ", re.M),
}

# The frontmatter line the metrics are written above; every note has had it.
_ANCHOR = "tags:"


def extract(note: str) -> dict[str, float]:
    """The metrics the note's body shows, in METRICS order. Missing ones are absent."""
    out: dict[str, float] = {}
    for key, pattern in METRICS.items():
        m = pattern.search(note)
        if m:
            out[key] = float(m.group(1).replace(",", ""))
    return out


def _fmt(v: float) -> str:
    return str(int(v)) if v.is_integer() else repr(v)


def stamp(note: str) -> str:
    """The note with its metrics written into the frontmatter.

    Idempotent: metric lines already there are replaced, not duplicated, and a
    note with no frontmatter or no metrics comes back unchanged.
    """
    if not note.startswith("---\n") or note.find("\n---", 3) == -1:
        return note
    front, body = _split(note)
    metrics = extract(note)
    lines = [ln for ln in front.splitlines()
             if ln.partition(":")[0].strip() not in METRICS]
    if metrics:
        new = [f"{k}: {_fmt(v)}" for k, v in metrics.items()]
        at = next((i for i, ln in enumerate(lines) if ln.startswith(_ANCHOR)), len(lines))
        lines[at:at] = new
    rebuilt = "---\n" + "\n".join(lines) + "\n---" + body
    return rebuilt if rebuilt != note else note


def _split(note: str) -> tuple[str, str]:
    """(frontmatter text between the fences, everything from after the closing fence)."""
    end = note.find("\n---", 3)
    return note[4:end], note[end + 4:]
