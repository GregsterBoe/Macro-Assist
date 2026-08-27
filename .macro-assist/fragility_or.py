"""
fragility_or.py — IMP-4.3: the live OR-of-channels recall MODE.

A DISTINCT high-recall fragility flag, kept separate from the composite
`var_led_vix35` Elevated label. It fires when ANY of three channels is at/above
its own point-in-time top-decile threshold:

    OR = (composite >= its PIT 90th pct)
       | (absorption ratio >= its PIT 90th pct)   [live sector-ETF panel]
       | (turbulence       >= its PIT 90th pct)   [live sector-ETF panel]

This is the operating point IMP-1/IMP-4 validated (KB-016 → KB-017 → KB-020): the
OR roughly *doubles* crisis recall vs the composite alone, at a modest precision
cost — a good trade for a tail-risk gauge, a bad one for a directional call. It is
adopted as an explicit MODE, NOT a composite weight and NOT an equal blend: KB-016
showed a blended weight lifts AUC but DEGRADES the validated top-decile flag, so
the channels stay separate and are OR-ed at the flag level.

Why PIT top-decile per channel (not a fixed cut): each channel is on its own raw
scale (the composite is 0-100; AR and turbulence are raw ratios/distances), and
the validated flag is "top decile of this channel's OWN history". Live, the
threshold for each channel is the 90th percentile of all of its readings STRICTLY
BEFORE today (an expanding window), and today fires if the latest reading clears
it — exactly `input_testing._pit_decile_or_flags` evaluated at the final day.

The cross-section feed is the live daily SPDR sector-ETF panel
(`fragility_backtest.fetch_sector_etfs`), the daily-fresh drop-in KB-020 proved
reproduces the Fama-French backtest feed at this operating point.

This module is COMPUTED-ONLY here; wiring into the daily note is governed by the
`FRAGILITY_OR_MODE` ladder in quant_context.py (default off), mirroring the
existing FRAGILITY_MODE shadow pattern. Run `python fragility_or.py` for today's
reading plus a self-check that the live path reproduces the KB-020 numbers.

Public surface
--------------
build_channels(...)   -> dict {common, gspc, comp, AR, TURB}  (walked histories)
or_mode_reading(...)  -> dict today's flag + per-channel value/threshold/fired
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from fragility import absorption_ratio, turbulence_signal
from fragility_backtest import (
    fetch_histories, walk_forward_fragility, fetch_sector_etfs,
    drawdown_label, collapse_episodes, episode_scoring,
)

# --- The validated operating point (KB-016 / KB-017 / KB-020). NOT swept: the
# ~7-18 crisis episodes cannot support tuning these without overfitting the OR
# knob (KB-017/018 discipline). Treated as fixed constants, not free params.
_Q = 0.90            # top-decile flag per channel
_COV_AR = 120        # absorption-ratio covariance window
_COV_TURB = 252      # turbulence covariance window
_SHRINK = 0.2        # turbulence covariance shrinkage
_SMOOTH = 5          # turbulence daily-distance smoothing
_STRIDE = 5          # anchor subsampling for the historical threshold distribution
_MIN_WARMUP = 252    # min prior readings before a channel's PIT cut is trusted
_CH_KEYS = ("comp", "AR", "TURB")


def _walk_panel_signal(
    signal_fn: Callable[[dict], Optional[float]],
    histories: dict,
    anchor_index: pd.DatetimeIndex,
    lookback: int,
    min_history: int,
) -> pd.Series:
    """Walk `signal_fn` forward on a cross-section panel, look-ahead-safe. A lean
    copy of input_testing.walk_forward_signal (stride handled by the caller via a
    pre-strided anchor) so the live channels are computed by the exact same PIT
    logic the harness validated, without the live layer importing the harness.
    """
    names = list(histories.keys())
    series = {name: pd.Series(histories[name]) for name in names}
    out: dict = {}
    for d in anchor_index:
        sliced = {}
        for name in names:
            past = series[name][series[name].index <= d].tail(lookback)
            if len(past) >= 2:
                sliced[name] = past
        if sum(len(v) >= min_history for v in sliced.values()) < 3:
            continue
        val = signal_fn(sliced)
        if val is not None and np.isfinite(val):
            out[d] = float(val)
    return pd.Series(out, name="signal")


def _panel_channels(px: pd.DataFrame, anchor: pd.DatetimeIndex) -> tuple:
    """Absorption-ratio and turbulence channels on the sector-ETF panel, walked on
    `anchor`. Same estimators/params as input_testing._panel_ar_turb."""
    etf_hist = {c: px[c].dropna() for c in px.columns}
    AR = _walk_panel_signal(
        lambda sl: (r["score"] if (r := absorption_ratio(
            sl, cov_window=_COV_AR, short_window=15, min_baseline=252)) else None),
        etf_hist, anchor, lookback=_COV_AR + 300, min_history=_COV_AR + 260)
    TURB = _walk_panel_signal(
        lambda sl: turbulence_signal(
            sl, cov_window=_COV_TURB, shrink=_SHRINK, smooth=_SMOOTH, min_baseline=_COV_TURB),
        etf_hist, anchor, lookback=_COV_TURB + 300, min_history=_COV_TURB)
    return AR, TURB


def build_channels(
    start: str = "2008-01-01",
    etf_start: str = "2007-01-01",
    stride: int = _STRIDE,
    refresh: bool = True,
) -> dict:
    """Walk all three channels forward and align them on one shared, pre-strided
    anchor grid (composite ∩ ETF calendar), with the latest common date always
    appended so today's reading is real (not up to `stride` days stale). `refresh`
    re-pulls the ETF panel — the default for a live daily caller. Returns raw
    (un-ranked) channel series plus the ^GSPC level for labels.
    """
    traded = fetch_histories(start=start)
    comp = walk_forward_fragility(traded)["composite"].astype(float)
    gspc = pd.Series(traded["sp500"]).astype(float)

    px = fetch_sector_etfs(start=etf_start, refresh=refresh)

    full = comp.index.intersection(px.index)
    if len(full) == 0:
        raise RuntimeError("build_channels: no overlap between composite and ETF calendars")
    anchor = full[::stride]
    if len(anchor) == 0 or anchor[-1] != full[-1]:      # keep today's real reading
        anchor = anchor.append(full[-1:])

    AR, TURB = _panel_channels(px, anchor)
    common = comp.index.intersection(AR.index).intersection(TURB.index)
    return {
        "common": common,
        "gspc":   gspc,
        "comp":   comp.reindex(common),
        "AR":     AR.reindex(common),
        "TURB":   TURB.reindex(common),
    }


def or_mode_reading(
    channels: Optional[dict] = None,
    q: float = _Q,
    min_warmup: int = _MIN_WARMUP,
    **build_kw,
) -> Optional[dict]:
    """Today's OR-mode flag: is the LATEST reading of any channel at/above its own
    expanding-window (PIT) top-decile threshold, computed from all PRIOR readings?

    Returns None if the channels could not be built or lack a usable history.
    Otherwise a dict:
        asof            : latest common date (the reading date)
        flag            : bool — OR fired today
        fired_channels  : which channels are at/above their own PIT cut
        q               : the decile used
        channels        : {name: {value, pit_threshold, fired, percentile, n_prior}}
    `percentile` is where today's value sits in its own prior distribution (0-1).
    """
    ch = channels if channels is not None else build_channels(**build_kw)
    common = ch["common"]
    if common is None or len(common) == 0:
        return None

    asof = common[-1]
    latest: dict = {}
    fired_any = False
    for k in _CH_KEYS:
        s = ch[k].reindex(common).dropna()
        if len(s) == 0 or s.index[-1] != asof:
            # no live reading for this channel today — treat as non-firing but record
            latest[k] = {"value": None, "pit_threshold": None, "fired": False,
                         "percentile": None, "n_prior": 0}
            continue
        cur = float(s.iloc[-1])
        past = s.iloc[:-1].to_numpy(dtype=float)
        past = past[np.isfinite(past)]
        thr = float(np.quantile(past, q)) if len(past) >= min_warmup else None
        fired = bool(thr is not None and cur >= thr)
        pct = float((past < cur).mean()) if len(past) else None
        latest[k] = {"value": cur, "pit_threshold": thr, "fired": fired,
                     "percentile": pct, "n_prior": int(len(past))}
        fired_any = fired_any or fired

    return {
        "asof": asof,
        "flag": fired_any,
        "fired_channels": [k for k in _CH_KEYS if latest[k]["fired"]],
        "q": q,
        "channels": latest,
    }


# ---------------------------------------------------------------------------
# Self-check CLI — today's reading + proof the live path reproduces KB-020
# ---------------------------------------------------------------------------

def _pit_backtest(ch: dict, q: float, min_warmup: int) -> dict:
    """Reproduce the KB-020 PIT OR recall/precision over the whole common window
    from THIS module's channels, as a live-path sanity check against the harness.
    """
    arrs = {k: ch[k].to_numpy(dtype=float) for k in _CH_KEYS}
    idx = ch["comp"].index
    keep, or_days, comp_days = [], [], []
    for i in range(len(idx)):
        if i < min_warmup:
            continue
        fires, ok = {}, True
        for k in _CH_KEYS:
            past = arrs[k][:i]
            past = past[np.isfinite(past)]
            if len(past) < min_warmup:
                ok = False
                break
            fires[k] = bool(np.isfinite(arrs[k][i]) and arrs[k][i] >= np.quantile(past, q))
        if not ok:
            continue
        keep.append(idx[i])
        comp_days.append(fires["comp"])
        or_days.append(any(fires.values()))
    ev = pd.DatetimeIndex(keep)
    or_flag = pd.Series(or_days, index=ev)
    comp_flag = pd.Series(comp_days, index=ev)
    out = {}
    for h in (5, 10):
        labels = drawdown_label(pd.Series(ch["gspc"]).astype(float), 0.05, h)
        y = labels.reindex(ev).dropna()
        out[h] = {
            "or":   episode_scoring(or_flag.reindex(y.index).fillna(False).astype(bool), y),
            "comp": episode_scoring(comp_flag.reindex(y.index).fillna(False).astype(bool), y),
        }
    return {"n_eval": len(ev), "horizons": out}


def _cli() -> None:
    print("Building live OR-mode channels (composite + live sector-ETF AR/TURB)...")
    ch = build_channels(refresh=True)
    common = ch["common"]
    print(f"  common window: {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()}\n")

    r = or_mode_reading(ch)
    print(f"=== OR-mode reading as of {r['asof'].date()} ===")
    print(f"  FLAG: {'FIRING' if r['flag'] else 'quiet'}"
          + (f"  (channels: {', '.join(r['fired_channels'])})" if r['flag'] else ""))
    for k in _CH_KEYS:
        c = r["channels"][k]
        val = "n/a" if c["value"] is None else f"{c['value']:.3f}"
        thr = "n/a" if c["pit_threshold"] is None else f"{c['pit_threshold']:.3f}"
        pct = "n/a" if c["percentile"] is None else f"{100*c['percentile']:.0f}th pct"
        print(f"  {k:<5} value={val:<9} PIT90={thr:<9} {pct:<10} "
              f"{'FIRED' if c['fired'] else '-'}")

    print("\n=== Self-check: live-path PIT backtest (should match KB-020) ===")
    bt = _pit_backtest(ch, _Q, _MIN_WARMUP)
    print(f"  PIT evaluable window: {bt['n_eval']} readings")
    for h in (5, 10):
        o, c = bt["horizons"][h]["or"], bt["horizons"][h]["comp"]
        print(f"  h={h:>2}d  OR recall={o['episode_recall']} "
              f"({o['n_caught']}/{o['n_episodes']}) prec={o['alarm_precision']} "
              f"| composite recall={c['episode_recall']} "
              f"({c['n_caught']}/{c['n_episodes']}) prec={c['alarm_precision']}")


if __name__ == "__main__":
    _cli()
