"""
fragility_panel.py — the data the fragility layer reads, the walk that turns it
into a channel history, and the target the channels are held to.

Product code (ADR-0021). Everything here is on the live path of the OR flag
(`fragility_or.py`) or of the daily note's vol legs (`quant_context.py`), or is
what the live path checks itself against — `fragility_or.py`'s self-check
reproduces the KB-020 recall/precision from these functions and nothing else.
It was carved out of `fragility_backtest.py` (todo #20) so the note no longer
imports a harness; the harness imports this and re-exports the names, so every
research caller is unchanged.

Contents
--------
Feeds
    fetch_histories(period, start)          -> dict   the traded assets + VIX/VIX3M (yfinance)
    fetch_cboe_index(symbol)                -> Series CBOE's own CSV for a vol index
    cboe_error(symbol)                      -> str    why the last such fetch failed
    freshen_vol_indices(histories, ...)     -> dict   splice CBOE under a stale VIX/VIX3M leg (KB-029)
    fetch_sector_etfs(start, ...)           -> DataFrame  the live nine-sector SPDR panel (IMP-4.2, KB-020)
The walk
    walk_forward_fragility(histories, ...)  -> DataFrame  composite + components per day, PIT by slicing
The target
    forward_worst_return(close, horizon)    -> Series
    drawdown_label(close, threshold, horizon) -> Series[bool]   ≥threshold drawdown within horizon
    collapse_episodes(flag, merge_gap)      -> list[(start, end)]
    episode_scoring(flag, labels, merge_gap)-> dict   episode-level recall / precision (KB-002 discipline)

Nothing here fits, scores an AUC, ablates or prints a verdict — that is the
harness's job and stays in `fragility_backtest.py`.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

import numpy as np
import pandas as pd

from pipeline_common import yf_history_with_retry

from fragility import fragility_index

# Trailing window passed to fragility_index each step. Was 180 (correlation's
# 2*window=120 + buffer). Raised to 300 for WP-16.A.6: the absorption_ratio
# component needs a longer trailing baseline (cov_window 60 + a ~200-day AR
# baseline) to standardize its shift. This does NOT change any pre-existing
# component's reading — each slices its own fixed recent tail — so the KB-002
# baseline reproduces identically; it only gives absorption room to mature.
_LOOKBACK = 300

# Minimum trailing history before we start emitting a reading.
_MIN_HISTORY = 130


# ---------------------------------------------------------------------------
# Drawdown labelling (forward-looking — evaluation only)
# ---------------------------------------------------------------------------

def forward_worst_return(close: pd.Series, horizon: int = 10) -> pd.Series:
    """For each date, the worst (most negative) cumulative return over the next
    `horizon` trading days. NaN where the forward window is incomplete.
    """
    close = pd.Series(close).astype(float)
    arr = close.to_numpy()
    out = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        end = min(i + horizon + 1, len(arr))
        if end > i + 1:
            fut = arr[i + 1:end] / arr[i] - 1.0
            out[i] = float(fut.min())
    return pd.Series(out, index=close.index)


def drawdown_label(
    close: pd.Series,
    threshold: float = 0.05,
    horizon: int = 10,
) -> pd.Series:
    """Boolean Series: does a drawdown of at least `threshold` (e.g. 0.05 = 5%)
    occur within the next `horizon` trading days? NaN tail is dropped.
    """
    worst = forward_worst_return(close, horizon).dropna()
    return worst <= -abs(threshold)


# ---------------------------------------------------------------------------
# Walk-forward fragility series
# ---------------------------------------------------------------------------

def walk_forward_fragility(
    histories: dict,
    anchor: str = "sp500",
    lookback: int = _LOOKBACK,
    min_history: int = _MIN_HISTORY,
    weights: Optional[dict] = None,
) -> pd.DataFrame:
    """Compute the fragility index on each trading day of `anchor`'s history,
    using only data known up to that day.

    Returns a DataFrame indexed by date with columns:
        composite, label, trend, degraded (bool — a required component was
        missing that day, so `label` is 'Unavailable' and the composite is not
        on its calibrated distribution; see fragility._LABEL_REQUIRES), and one
        column per component score (variance_trend, correlation, vix_term,
        autocorr).
    """
    if anchor not in histories:
        raise ValueError(f"anchor asset {anchor!r} not in histories")

    anchor_idx = pd.Series(histories[anchor]).index
    rows: list[dict] = []

    for d in anchor_idx:
        # Trailing slice known as of date d for every asset.
        sliced: dict = {}
        for name, s in histories.items():
            if s is None:
                continue
            s = pd.Series(s)
            past = s[s.index <= d].tail(lookback)
            if len(past) >= 2:
                sliced[name] = past

        # Need enough anchor history before emitting a reading.
        if anchor not in sliced or len(sliced[anchor]) < min_history:
            continue

        res = fragility_index(sliced, weights=weights)
        if res is None:
            continue

        comps = res["components"]
        rows.append({
            "date":           d,
            "composite":      res["composite"],
            "label":          res["label"],
            "trend":          res["trend"],
            "degraded":       bool(res.get("degraded")),
            "variance_trend": comps.get("variance_trend", {}).get("score", np.nan),
            "correlation":    comps.get("correlation", {}).get("score", np.nan),
            "absorption":     comps.get("absorption", {}).get("score", np.nan),
            "vix_term":       comps.get("vix_term", {}).get("score", np.nan),
            "autocorr":       comps.get("autocorr", {}).get("score", np.nan),
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


# ---------------------------------------------------------------------------
# Episodes (WP-16.A.3) — the A.2 caveat: 4,513 daily readings inside a handful
# of real crises are NOT independent observations. Collapse both the drawdown
# label and the alarm flag into distinct runs, then count caught crises / true
# alarms. The counts become small integers (one per crisis), removing the
# inflation. (The other honest fix, non-overlapping AUC, is in the harness.)
# ---------------------------------------------------------------------------

def collapse_episodes(flag: pd.Series, merge_gap: int = 3) -> list[tuple]:
    """Collapse a boolean Series into a list of (start_date, end_date) runs.

    Consecutive True days are one episode; runs separated by <= `merge_gap`
    False days are merged (a brief dip below threshold mid-crisis is still one
    crisis). Returns [] if nothing is True.
    """
    flag = pd.Series(flag).astype(bool)
    flag = flag[flag.notna()]
    pos = np.where(flag.to_numpy())[0]
    if len(pos) == 0:
        return []
    idx = flag.index
    episodes: list[tuple] = []
    start = prev = pos[0]
    for p in pos[1:]:
        if p - prev <= merge_gap + 1:
            prev = p
        else:
            episodes.append((idx[start], idx[prev]))
            start = prev = p
    episodes.append((idx[start], idx[prev]))
    return episodes


def _intervals_overlap(a: tuple, b: tuple) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def episode_scoring(
    flag: pd.Series,
    labels: pd.Series,
    merge_gap: int = 3,
) -> dict:
    """Score a boolean alarm flag against drawdown labels at the EPISODE level.

    Collapses both series into runs, then:
      episode_recall = fraction of distinct drawdown episodes an alarm overlaps
      alarm_precision = fraction of distinct alarms that overlap a real episode
    Counts (n_episodes, n_alarms) are small independent integers — the honest
    denominator the day-level lift inflates.
    """
    flag = pd.Series(flag).astype(bool)
    y = pd.Series(labels).astype(bool).reindex(flag.index)
    mask = flag.notna() & y.notna()
    flag, y = flag[mask], y[mask].astype(bool)

    label_eps = collapse_episodes(y, merge_gap)
    alarm_eps = collapse_episodes(flag, merge_gap)
    if not label_eps:
        return {"n_episodes": 0, "n_alarms": len(alarm_eps),
                "n_caught": 0, "episode_recall": None, "alarm_precision": None}

    caught = sum(any(_intervals_overlap(le, ae) for ae in alarm_eps) for le in label_eps)
    if alarm_eps:
        true_alarms = sum(any(_intervals_overlap(ae, le) for le in label_eps) for ae in alarm_eps)
        precision = round(true_alarms / len(alarm_eps), 3)
    else:
        precision = None
    return {
        "n_episodes":      len(label_eps),
        "n_alarms":        len(alarm_eps),
        "n_caught":        caught,
        "episode_recall":  round(caught / len(label_eps), 3),
        "alarm_precision": precision,
    }


# ---------------------------------------------------------------------------
# Feeds — free daily history (yfinance) with CBOE's own file under the vol legs
# ---------------------------------------------------------------------------

_TICKERS = {
    "sp500": "^GSPC", "nasdaq": "^IXIC", "gold": "GC=F",
    "wti_oil": "CL=F", "dxy": "DX-Y.NYB",
    "vix": "^VIX", "vix3m": "^VIX3M",
}


# CBOE publishes its own daily index history as plain CSV (DATE,OPEN,HIGH,LOW,
# CLOSE; VIX from 1990, VIX3M from 2009-09). It is the issuer's record and the
# fallback for the term-structure legs: yfinance's ^VIX3M silently stopped
# updating on 2026-07-17, which froze the live `vix_term` component and then
# dropped it for ten trading days — the composite's first live Elevated came
# out of that gap, not out of the market (KB-029). The yfinance ^VIX3M history
# (VXV, from 2007) still seeds the pre-2009 backtest window; the CBOE file
# takes over from its own first date.
_CBOE_SYMBOLS: dict[str, str] = {"vix": "VIX", "vix3m": "VIX3M"}
_CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"
_CBOE_TIMEOUT = 20


# The fallback's own failure used to be invisible: `fetch_cboe_index` returned
# None for a 403, a CDN outage, a renamed column and a parked file alike, and
# `freshen_vol_indices` then left the leg as it found it. The composite went
# `Unavailable` and nothing anywhere said which feed had died. This dict holds
# the last failure per symbol so the caller can report one (IMP-5.4). It is a
# diagnostic, never control flow — nothing reads it to decide anything.
_LAST_CBOE_ERROR: dict[str, str] = {}

# One retry, because the observed failures are transient far more often than
# structural. Two attempts and a named reason is the whole budget: a feed that
# is genuinely down should be reported, not hammered.
_CBOE_ATTEMPTS = 2


def fetch_cboe_index(symbol: str, timeout: int = _CBOE_TIMEOUT,
                     attempts: int = _CBOE_ATTEMPTS) -> Optional[pd.Series]:
    """Daily Close for a CBOE index (e.g. 'VIX3M') from CBOE's own CSV, as a
    tz-naive Series indexed by date. None on any failure — the caller decides
    whether the yfinance leg is fresh enough to stand alone. The reason for a
    failure is recorded in `_LAST_CBOE_ERROR[symbol]` and cleared on success;
    `cboe_error(symbol)` reads it."""
    import io
    import urllib.request

    last: Optional[str] = None
    for _attempt in range(max(1, attempts)):
        try:
            with urllib.request.urlopen(_CBOE_URL.format(symbol=symbol), timeout=timeout) as resp:
                df = pd.read_csv(io.StringIO(resp.read().decode("utf-8")))
            df.columns = [c.strip().upper() for c in df.columns]
            out = pd.Series(df["CLOSE"].astype(float).to_numpy(),
                            index=pd.to_datetime(df["DATE"]), name=symbol)
            out = out[~out.index.duplicated(keep="last")].sort_index().dropna()
            if len(out):
                _LAST_CBOE_ERROR.pop(symbol, None)
                return out
            last = "CBOE csv parsed but held no usable Close rows"
        except Exception as exc:   # noqa: BLE001 — the reason is the product here
            last = f"{type(exc).__name__}: {exc}"
    _LAST_CBOE_ERROR[symbol] = last or "unknown failure"
    return None


def cboe_error(symbol: str) -> Optional[str]:
    """The last recorded failure for `symbol`, or None if its last fetch worked
    (or none has been attempted in this process)."""
    return _LAST_CBOE_ERROR.get(symbol)


def freshen_vol_indices(
    histories: dict,
    anchor: str = "sp500",
    max_stale: int = 5,
    fetch: "Callable[[str], Optional[pd.Series]]" = fetch_cboe_index,
    report: Optional[dict] = None,
) -> dict:
    """Splice CBOE's own history under any VIX / VIX3M leg that is missing or
    has fallen more than `max_stale` anchor observations behind the anchor's
    last date. Legs that are fresh are left exactly as fetched, so on a normal
    day this is a no-op and the backtest is unchanged. Never raises.

    Pass a dict as `report` to have the outcome per leg written into it:
    `{leg: {"source": "yfinance"|"cboe"|"none", "stale_obs": int|None,
    "last": "YYYY-MM-DD"|None, "error": str|None}}`. The splice behaves
    identically whether or not a report is asked for — this is the record of
    what happened, which the live path had no way to produce before IMP-5.4.
    """
    out = dict(histories)
    anchor_s = out.get(anchor)
    if anchor_s is None or len(anchor_s) == 0:
        if report is not None:
            report["anchor"] = {"source": "none", "stale_obs": None, "last": None,
                                "error": f"anchor '{anchor}' absent — no leg could be judged stale"}
        return out
    anchor_idx = pd.Series(anchor_s).index
    for name, symbol in _CBOE_SYMBOLS.items():
        cur = out.get(name)
        stale_obs = None
        if cur is not None and len(cur):
            stale_obs = int((anchor_idx > pd.Series(cur).index[-1]).sum())
        stale = stale_obs is None or stale_obs > max_stale
        if not stale:
            _note(report, name, "yfinance", stale_obs, out[name], None)
            continue
        try:
            cboe = fetch(symbol)
        except Exception as exc:   # noqa: BLE001 — an injected fetch may raise
            cboe = None
            _LAST_CBOE_ERROR[symbol] = f"{type(exc).__name__}: {exc}"
        if cboe is None:
            # The leg stays as it was found — missing, or stale and therefore
            # about to be treated as missing. This is the branch that produced
            # three silent Unavailable days in September 2026.
            _note(report, name, "yfinance" if cur is not None and len(cur) else "none",
                  stale_obs, cur, cboe_error(symbol) or "CBOE fallback returned no data")
            continue
        if cur is not None and len(cur) and pd.Series(cur).index[0] < cboe.index[0]:
            # keep the older yfinance history where CBOE's file does not reach
            head = pd.Series(cur)[pd.Series(cur).index < cboe.index[0]]
            cboe = pd.concat([head, cboe])
        out[name] = cboe.astype(float)
        _note(report, name, "cboe",
              int((anchor_idx > cboe.index[-1]).sum()), out[name], None)
    return out


def _note(report: Optional[dict], leg: str, source: str,
          stale_obs: Optional[int], series, error: Optional[str]) -> None:
    """Record one leg's outcome in `report`. No-op when no report was asked for."""
    if report is None:
        return
    last = None
    try:
        if series is not None and len(series):
            last = str(pd.Series(series).index[-1].date())
    except Exception:   # noqa: BLE001 — a report must never break a fetch
        last = None
    report[leg] = {"source": source, "stale_obs": stale_obs, "last": last, "error": error}


def fetch_histories(period: str = "max", start: str | None = "2008-01-01") -> dict:
    """Pull daily Close series for the tracked tickers from yfinance (free).
    VIX3M only exists from ~2008, so the default start caps there. The VIX /
    VIX3M legs are freshened from CBOE's own CSV when yfinance's copy is stale
    (`freshen_vol_indices`).
    """
    import yfinance as yf

    histories: dict = {}
    for name, tk in _TICKERS.items():
        # Same two-attempt budget as the CBOE client below, and for the same
        # reason: an empty frame is yfinance's usual way of failing, and this
        # loop used to accept the first one as the answer (todo #26 item 1).
        hist, reason = yf_history_with_retry(
            (lambda tk=tk: yf.Ticker(tk).history(start=start)) if start
            else (lambda tk=tk: yf.Ticker(tk).history(period=period)), tk)
        if hist is None:
            print(f"  warn: {tk} failed: {reason}")
            continue
        try:
            close = hist["Close"]
            close.index = close.index.tz_localize(None)
            histories[name] = close
        except Exception as e:   # noqa: BLE001 — CLI convenience only
            print(f"  warn: {tk} failed: {e}")
    histories = freshen_vol_indices(histories)
    if start:
        for name in _CBOE_SYMBOLS:
            if name in histories:
                histories[name] = histories[name][histories[name].index >= pd.Timestamp(start)]
    return histories


# ---------------------------------------------------------------------------
# IMP-4.2 — the LIVE daily homogeneous cross-section (graduated from the
# input_testing harness once KB-020 validated feed parity). The FF industry
# panel (Ken French library) is monthly-updated with a multi-week lag, so it can
# seed a backtest but cannot drive a daily flag. SPDR Select-Sector ETFs are the
# free, daily-fresh substitute (yfinance, same path as the traded assets). We fix
# the panel to the ORIGINAL NINE sectors, which all trade from Dec-1998 and
# therefore span the whole 2008+ backtest window with no ragged start; XLRE
# (2015, split off XLF) and XLC (2018, split off XLK/XLY) are later refinements OF
# these nine, so the nine still tile the whole market throughout — kept out of the
# validated core to keep the panel membership stable across the backtest.
_SECTOR_ETFS: dict[str, str] = {
    "materials":     "XLB",
    "energy":        "XLE",
    "financials":    "XLF",
    "industrials":   "XLI",
    "technology":    "XLK",
    "staples":       "XLP",
    "utilities":     "XLU",
    "healthcare":    "XLV",
    "discretionary": "XLY",
}

_ETF_CACHE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "macro-assist", "etf",
)


def fetch_sector_etfs(
    start: str = "2007-01-01",
    tickers: Optional[dict] = None,
    cache_dir: str = _ETF_CACHE,
    refresh: bool = False,
) -> pd.DataFrame:
    """IMP-4.2 — the LIVE daily sector-ETF panel (SPDR Select Sectors via yfinance).

    Returns a Close-price DataFrame (columns = sector names, index = trading days),
    the daily-fresh drop-in for the Fama-French backtest feed behind the AR/TURB
    fragility channels. Cached to CSV so backtests are offline/reproducible; pass
    refresh=True to re-pull (a live daily caller wants fresh data, not the cache).

    The nine `_SECTOR_ETFS` all trade from Dec-1998, so a `start` at/after then
    yields a rectangular panel with no ragged membership — the clean cross-section
    the absorption-ratio / turbulence estimators want.
    """
    tickers = tickers or _SECTOR_ETFS
    os.makedirs(cache_dir, exist_ok=True)
    key = "_".join(sorted(tickers.values())) + f"_{start}"
    cache_path = os.path.join(cache_dir, re.sub(r"[^\w.-]", "_", key) + ".csv")
    if os.path.exists(cache_path) and not refresh:
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        return df.loc[df.index >= pd.Timestamp(start)]

    import yfinance as yf

    cols: dict[str, pd.Series] = {}
    for name, tk in tickers.items():
        try:
            hist = yf.Ticker(tk).history(start=start)
            if hist.empty:
                print(f"  warn: {tk} returned no rows")
                continue
            close = hist["Close"]
            try:
                close.index = close.index.tz_localize(None)
            except (TypeError, AttributeError):
                pass
            cols[name] = close.astype(float)
        except Exception as e:   # noqa: BLE001 — fetch convenience
            print(f"  warn: {tk} failed: {e}")
    if not cols:
        raise RuntimeError("fetch_sector_etfs: no ETF series could be fetched")
    df = pd.DataFrame(cols).sort_index()
    df.rename_axis("DATE").to_csv(cache_path)
    return df.loc[df.index >= pd.Timestamp(start)]

