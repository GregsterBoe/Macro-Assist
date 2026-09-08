"""
assets.py — The canonical asset registry for the conditional-distribution product.

Single source of truth for the four things that were previously spread across
`refit_models.py` (build side), `quant_context.py` (render side) and
`score_predictions.py` (score side), each with its own naming and its own idea of
what a "return" is:

  * the **key** used in `conditional_distributions.json` and the quant log,
  * the **ticker** the series comes from,
  * the **note name** the asset is published under,
  * the **return convention** — and this is the one that actually bites.

Why the convention has to live in one place
-------------------------------------------
`^TNX` reports the 10Y as a *yield level* in percent (4.77 means 4.77%). A
percentage return over a level like that is a percent-of-a-percent: it inflates
the denominator and makes any threshold roughly 13x too large. That bug already
has a home-grown fix in `score_predictions.ABSOLUTE_DIFF_ASSETS`, written for the
directional scorer. Adding the 10Y to the distribution table means the build
side, the render side and the new distribution scorer all need the *same* fix,
computed the *same* way — so it is defined once here, as `forward_change()`, and
imported rather than re-derived.

Stored units are display units
------------------------------
A number in the distribution table is in the unit named by `Asset.unit`:

  * `convention="pct"`   → percent return, e.g. ``1.21`` is +1.21%
  * `convention="level"` → **basis points** of level change, e.g. ``6.0`` is +6bp

So "what does this stored number mean" is answered by the registry and never by
the call site. `format_change()` is the matching renderer.

Compatibility
-------------
The three original keys (`SP500`, `Gold`, `WTI Oil`) are unchanged: the persisted
table, every `results/quant_context_log/*.jsonl` written since 2026-05-29, and
the forward record built on them all key off these strings. Do not rename them.
`score_predictions.py` is deliberately *not* refactored onto this module — it is
frozen legacy that has to keep reproducing [KB-007]/[KB-011]/[KB-022].
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    """One tracked asset and the convention its forward change is measured in."""

    key: str          # stable key in conditional_distributions.json + the quant log
    ticker: str       # yfinance symbol
    note_name: str    # heading used in the note's 5-Day Outlook table
    convention: str   # "pct" (percent return) | "level" (absolute change)
    unit: str         # display suffix for a stored number: "%" | "bp"

    @property
    def is_level(self) -> bool:
        return self.convention == "level"


# ---------------------------------------------------------------------------
# The registry.
#
# Order is the order rows appear in the note. The first three keys predate this
# module and are load-bearing for the existing table and forward record.
# ---------------------------------------------------------------------------
ASSETS: tuple[Asset, ...] = (
    Asset("SP500",   "^GSPC",    "S&P 500",            "pct",   "%"),
    Asset("Gold",    "GC=F",     "Gold",               "pct",   "%"),
    Asset("WTI Oil", "CL=F",     "WTI Oil",            "pct",   "%"),
    Asset("UST10Y",  "^TNX",     "10Y Treasury Yield", "level", "bp"),
    Asset("DXY",     "DX-Y.NYB", "DXY",                "pct",   "%"),
    Asset("Bitcoin", "BTC-USD",  "Bitcoin",            "pct",   "%"),
)

BY_KEY: dict[str, Asset] = {a.key: a for a in ASSETS}
BY_NOTE_NAME: dict[str, Asset] = {a.note_name: a for a in ASSETS}

# Horizons the distribution table is built at, in trading days.
HORIZONS: tuple[int, ...] = (5, 10, 20)

# The three keys that carry a forward record predating this module. Any pooled
# statistic that mixes these with the keys added alongside the distribution
# scorer is mixing record lengths — see `score_distributions` for how that is
# reported rather than hidden.
ORIGINAL_KEYS: frozenset[str] = frozenset({"SP500", "Gold", "WTI Oil"})


def get(key_or_name: str) -> Asset | None:
    """Look an asset up by table key or by note name. Never raises."""
    return BY_KEY.get(key_or_name) or BY_NOTE_NAME.get(key_or_name)


def forward_change(entry: float, exit_: float, asset: Asset | str) -> float:
    """The forward change from `entry` to `exit_`, in `asset`'s stored unit.

    This is the *only* definition of a forward change in the distribution
    product. The build side (`refit_models`) and the score side
    (`score_distributions`) both call it, so a published quantile and the
    realization it is scored against can never be in different units.

      * pct   → ``(exit/entry - 1) * 100``  (percent)
      * level → ``(exit - entry) * 100``    (basis points, from a percent level)

    Raises ValueError on a non-positive entry for a pct asset, where the ratio is
    meaningless — silently returning a number there is how a bad price becomes a
    plausible-looking score.
    """
    a = asset if isinstance(asset, Asset) else get(asset)
    if a is None:
        raise KeyError(f"unknown asset: {asset!r}")

    if a.is_level:
        return (exit_ - entry) * 100.0

    if entry <= 0:
        raise ValueError(f"{a.key}: non-positive entry price {entry!r}")
    return (exit_ / entry - 1.0) * 100.0


def format_change(value: float, asset: Asset | str, decimals: int | None = None) -> str:
    """Render a stored change with its sign and unit, e.g. '+1.2%' or '+6bp'.

    `decimals` defaults to 1 for percent assets and 0 for basis points — a
    tenth of a basis point is noise on a daily yield series.
    """
    a = asset if isinstance(asset, Asset) else get(asset)
    if a is None:
        raise KeyError(f"unknown asset: {asset!r}")
    if decimals is None:
        decimals = 0 if a.is_level else 1
    return f"{value:+.{decimals}f}{a.unit}"


# ---------------------------------------------------------------------------
# Tolerant name resolution for the note's outlook table
#
# Both render paths look the distribution up by the asset string the *model*
# wrote in its table, and a miss renders as "no conditional base rate". While the
# 10Y, DXY and Bitcoin genuinely had no distribution that was harmless. Now that
# they do, an unrecognised spelling would silently hide a real base rate — the
# same class of failure as the three drifting asset lists this module replaced,
# so the matching is done here rather than at each call site.
#
# The prompt template, for instance, labels the row "Bitcoin (proxy for crypto
# risk)"; the model usually trims it to "Bitcoin", but "usually" is not a
# contract.
# ---------------------------------------------------------------------------

_ALIAS_SUBSTRINGS: tuple[tuple[str, str], ...] = (
    # (lowercased substring, asset key) — checked in order, first match wins.
    ("bitcoin", "Bitcoin"),
    ("btc",     "Bitcoin"),
    ("s&p",     "SP500"),
    ("sp500",   "SP500"),
    ("gold",    "Gold"),
    ("wti",     "WTI Oil"),
    ("crude",   "WTI Oil"),
    ("10y",     "UST10Y"),
    ("treasury", "UST10Y"),
    ("dxy",     "DXY"),
    ("dollar index", "DXY"),
)


def resolve_note_name(raw: str) -> str | None:
    """Map an asset string from the note's table onto a canonical note name.

    Exact matches on the note name or the table key win outright; otherwise a
    substring match handles the decorated spellings the model may emit
    ("Bitcoin (proxy for crypto risk)", "10Y Treasury Yield"). Returns None when
    nothing matches, which the caller must treat as "no base rate" rather than
    guessing.
    """
    if not raw:
        return None
    name = raw.strip()
    a = BY_NOTE_NAME.get(name) or BY_KEY.get(name)
    if a is not None:
        return a.note_name

    low = name.lower()
    for needle, key in _ALIAS_SUBSTRINGS:
        if needle in low:
            return BY_KEY[key].note_name
    return None
