"""
filter_testing.py — IMP-9: an outside input as a FILTER on the OR flag.

Goal 2 asks the OR flag for precision 0.4 at 5d at recall no worse than today
(~0.3). Adding channels (KB-018/019/032) and recombining the trio (KB-031) are
closed. This asks the one role not yet tried: a firing stands only when an
input from OUTSIDE the equity panel and the VIX term structure agrees. A filter
can only remove firings, so its way to fail is losing a crisis — and that
disqualifier is checked before precision is read.

9.A — CBOE SKEW (the bar: improvement-track.md IMP-9 §9.A, written 2026-10-01
before any SKEW value was read). The input on reading date t:

  x_t = mean(SKEW, the 5 CBOE days ending the CBOE day strictly before t)
        − median(SKEW, the 252 closes ending that same day)

  filtered flag = OR ∧ (x_t ≥ 0)

  - one day's lag (ADR-0014's shift; the note runs before the US open);
  - measured against its own trailing year, because SKEW's level has drifted
    up over decades and a whole-history percentile would read "high" in every
    recent year;
  - stale fails OPEN: no SKEW print in the 10 calendar days before t lets the
    firing stand — a missing feed never silences a warning (KB-029);
  - fewer than 252 + 5 prior closes drops the reading from the window; the
    unfiltered reference is scored on the same readings.

Two windows, both must pass:
  live  the KB-021 trio (composite ∨ AR ∨ TURB), `fragility_or.build_channels`,
        labelled on ^GSPC — the flag goal 2 names;
  long  the panel-only flag (AR ∨ TURB on the Fama-French 30 industries,
        `fragility_or`'s constants — H-009's flag), labelled on the FF market,
        from where it and SKEW are warmed up. It exists for power.

Scored with `fragility_backtest`'s de-overlapped episode metrics under PIT and
LOCO, as IMP-6 (`aggregator_testing`), against the unfiltered flag on the same
readings. In LOCO the trio's cuts are fit outside the held-out crisis; the
filter fits nothing (trailing by construction). Decisive horizon 5d.

The verdict is `verdict()`: disqualifiers first, each returning at once, the
pass clause unreachable until all are checked ([KB-027]'s structure). Fixed
config, no sweeps. Run: `python filter_testing.py` (`--cached` reuses the
channels and the SKEW file under results/filter_testing/).
"""
from __future__ import annotations

import argparse
import io
import json
import pickle
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import aggregator_testing as at
from fragility_backtest import collapse_episodes, drawdown_label, episode_scoring
from fragility_or import (
    _CH_KEYS, _COV_AR, _COV_TURB, _MIN_WARMUP, _Q, _SHRINK, _SMOOTH, _STRIDE,
)

# --- Pre-registered constants (IMP-9 §9.A). Fixed, NOT swept. ---------------------
SKEW_SYMBOL = "SKEW"
SMOOTH = 5              # x_t: trailing mean of this many CBOE closes
BASE = 252              # ... minus the median of this many closes (the trailing year)
LAG_STRICT = True       # the CBOE day used is strictly before the reading date
STALE_DAYS = 10         # no print within this many calendar days → the filter fails open
HORIZONS = (5, 10)
DECISIVE = 5            # goal 2's horizon; 10d is reported
DD_THRESHOLD = 0.05
LONG_START = "1980-01-01"   # FF industries from here: channels warm up before SKEW does

# --- The bar. ---------------------------------------------------------------------
MIN_ALARMS = 10         # underpowered: filtered alarm episodes at 5d (PIT)
MIN_LEAD_5D = 2.0       # too_late: median lead to trough at 5d (PIT true positives)
MAX_RECALL_LOST = 0     # recall_lost: crises lost vs the unfiltered flag at 5d, PIT or LOCO
PASS_PREC_GAIN = 0.05   # no_edge: PIT precision at 5d below the unfiltered + this
LIVE_PREC_FLOOR = 0.40  # no_edge (live window only): goal 2's target
N_SHIFT = 200           # luck: shifted filters in the null
LUCK_Q = 0.90           # luck: precision must beat this quantile of the null
MIN_SHIFT = 52          # luck: shifts run from this many readings to n − this
SEED = 20261001

VERDICTS = ("underpowered", "too_late", "recall_lost", "no_edge", "luck", "pass")

_RESULTS = Path(__file__).resolve().parent.parent / "results" / "filter_testing"
_CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"


# ---------------------------------------------------------------------------
# the input
# ---------------------------------------------------------------------------

def parse_cboe(text: str) -> pd.Series:
    """A CBOE single-value index file (DATE,<SYMBOL>) or an OHLC one (…,CLOSE)
    as a float Series on a sorted, de-duplicated date index."""
    df = pd.read_csv(io.StringIO(text))
    col = "CLOSE" if "CLOSE" in df.columns else df.columns[-1]
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[df.columns[0]]), dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if s.empty:
        raise ValueError("parse_cboe: no values")
    return s


def fetch_skew(timeout: int = 30) -> pd.Series:
    req = urllib.request.Request(_CBOE_URL.format(symbol=SKEW_SYMBOL),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_cboe(r.read().decode())


def skew_filter(skew: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Per reading date: `x` (the 9.A input), `ready` (enough prior closes),
    `stale` (no print within STALE_DAYS before the date) and `passes` (the
    firing stands: ready and (stale or x ≥ 0)). Only CBOE days strictly before
    the date are read."""
    s = pd.Series(skew).astype(float).dropna().sort_index()
    x_cboe = (s.rolling(SMOOTH, min_periods=SMOOTH).mean()
              - s.rolling(BASE, min_periods=BASE).median())
    vals, cidx = x_cboe.to_numpy(), s.index
    rows = []
    for t in dates:
        pos = cidx.searchsorted(t, side="left") - 1          # last CBOE day < t
        n_prior = pos + 1
        if pos < 0 or n_prior < BASE + SMOOTH:
            rows.append((np.nan, False, False, False))
            continue
        stale = (t - cidx[pos]).days > STALE_DAYS
        x = float(vals[pos])
        rows.append((np.nan if stale else x, True, stale, bool(stale or x >= 0)))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates),
                        columns=["x", "ready", "stale", "passes"])


# ---------------------------------------------------------------------------
# the windows
# ---------------------------------------------------------------------------

def live_window(cache: Optional[Path] = None) -> dict:
    """The KB-021 trio, labelled on ^GSPC."""
    from fragility_or import build_channels
    if cache and cache.exists():
        ch = pickle.loads(cache.read_bytes())
    else:
        ch = build_channels(refresh=True)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(pickle.dumps(ch))
    return {"name": "live", "channels": {k: ch[k] for k in _CH_KEYS},
            "keys": _CH_KEYS, "close": pd.Series(ch["gspc"]).astype(float),
            "floor": LIVE_PREC_FLOOR,
            "what": "composite ∨ AR ∨ TURB (KB-021, sector ETFs), labelled on ^GSPC"}


def long_window(cache: Optional[Path] = None) -> dict:
    """The panel-only flag on the FF 30 industries, labelled on the FF market."""
    from input_testing import (_panel_ar_turb, fetch_ff_industries, fetch_ff_market,
                               returns_to_histories)
    if cache and cache.exists():
        got = pickle.loads(cache.read_bytes())
    else:
        ind = fetch_ff_industries(30, "vw")
        ind = ind[ind.index >= pd.Timestamp(LONG_START)]
        AR, TURB = _panel_ar_turb(returns_to_histories(ind), ind.index,
                                  cov_ar=_COV_AR, cov_turb=_COV_TURB, shrink=_SHRINK,
                                  smooth=_SMOOTH, stride=_STRIDE)
        common = AR.index.intersection(TURB.index)
        got = {"AR": AR.reindex(common), "TURB": TURB.reindex(common),
               "close": fetch_ff_market()}
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(pickle.dumps(got))
    return {"name": "long", "channels": {"AR": got["AR"], "TURB": got["TURB"]},
            "keys": ("AR", "TURB"), "close": pd.Series(got["close"]).astype(float),
            "floor": None,
            "what": "AR ∨ TURB (Fama-French 30 industries, H-009's flag), labelled on the FF market"}


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _label(close: pd.Series, h: int, on: pd.DatetimeIndex) -> pd.Series:
    return drawdown_label(close, DD_THRESHOLD, h).reindex(on)


def precision_at(flag: pd.Series, close: pd.Series, h: int) -> Optional[float]:
    y = _label(close, h, flag.index).dropna()
    return episode_scoring(flag.reindex(y.index, fill_value=False).astype(bool), y)["alarm_precision"]


def loco_caught(channels: dict, keys: tuple, close: pd.Series, h: int,
                window: pd.DatetimeIndex, passes: Optional[pd.Series]) -> dict:
    """Leave-one-crisis-out on the crises inside `window`. Per fold the trio's
    cuts are fit on every reading of the whole channel history outside the
    crisis (`aggregator_testing._train_table`), the OR is taken, and — when
    `passes` is given — filtered. The filter itself fits nothing."""
    idx = channels[keys[0]].index
    y = _label(close, h, window).dropna().astype(bool)
    folds = []
    for (s, e) in collapse_episodes(y):
        test = (idx >= s) & (idx <= e)
        train = ~test
        if any(np.isfinite(channels[k].reindex(idx).to_numpy(dtype=float)[train]).sum()
               < at.LOCO_MIN_TRAIN for k in keys):
            continue
        tab = at._train_table(channels, train, keys, _Q, at.Q_ALERT)
        f = at._or_flag(tab, keys).reindex(window, fill_value=False).astype(bool)
        if passes is not None:
            f = f & passes.reindex(window, fill_value=False).astype(bool)
        folds.append((s.date(), e.date(), bool(f[(window >= s) & (window <= e)].any())))
    return {"n_crises": len(folds), "caught": sum(hit for *_, hit in folds), "folds": folds}


def shift_null(orf: pd.Series, passes: pd.Series, close: pd.Series, h: int = DECISIVE,
               n: int = N_SHIFT, seed: int = SEED) -> np.ndarray:
    """PIT precision of OR ∧ (the filter's pass series rolled by k readings),
    k uniform in [MIN_SHIFT, len − MIN_SHIFT]. Keeps the filter's rate and runs,
    breaks its timing. None (no alarms) reads 0."""
    m = len(passes)
    if m <= 2 * MIN_SHIFT:
        return np.array([])
    rng = np.random.default_rng(seed)
    p = passes.to_numpy(dtype=bool)
    o = orf.reindex(passes.index, fill_value=False).to_numpy(dtype=bool)
    out = []
    for k in rng.integers(MIN_SHIFT, m - MIN_SHIFT + 1, size=n):
        prec = precision_at(pd.Series(o & np.roll(p, k), index=passes.index), close, h)
        out.append(0.0 if prec is None else prec)
    return np.asarray(out)


def score_window(win: dict, skew: pd.Series, horizons: tuple = HORIZONS) -> dict:
    """PIT + LOCO for the filtered flag beside the unfiltered one on the same
    readings, the shift null at 5d, and the reported-only channel role."""
    ch, keys, close = win["channels"], win["keys"], win["close"]
    table = at.pit_channel_table(ch, keys=keys)
    filt_all = skew_filter(skew, ch[keys[0]].index)    # per date, so the same values on any subset
    filt = filt_all.loc[table.index]
    window = filt.index[filt["ready"].to_numpy()]
    passes = filt.loc[window, "passes"].astype(bool)
    orf = at._or_flag(table.loc[window], keys)
    ff = orf & passes
    row = {"window": win["name"], "what": win["what"], "floor": win["floor"],
           "n_readings": len(window),
           "first": (str(window[0].date()) if len(window) else None),
           "last": (str(window[-1].date()) if len(window) else None),
           "or_firings": int(orf.sum()), "blocked": int((orf & ~passes).sum()),
           "stale_open": int((orf & filt.loc[window, "stale"]).sum()),
           "pit": {}, "loco": {}}
    for h in horizons:
        v, r = at._score(ff, close, h, DD_THRESHOLD), at._score(orf, close, h, DD_THRESHOLD)
        row["pit"][h] = {
            "n_episodes": v["n_episodes"], "caught": v["n_caught"], "ref_caught": r["n_caught"],
            "n_alarms": v["n_alarms"], "ref_n_alarms": r["n_alarms"],
            "precision": v["alarm_precision"], "ref_precision": r["alarm_precision"],
            "median_lead": v["median_lead"], "ref_median_lead": r["median_lead"],
        }
        lv = loco_caught(ch, keys, close, h, window, passes)
        lr = loco_caught(ch, keys, close, h, window, None)
        row["loco"][h] = {
            "n_crises": lv["n_crises"], "caught": lv["caught"], "ref_caught": lr["caught"],
            "lost": [(str(s), str(e)) for (s, e, hit), (_, _, rhit)
                     in zip(lv["folds"], lr["folds"]) if rhit and not hit],
        }
    if tuple(keys) == tuple(_CH_KEYS):       # the regression guard, as IMP-6's
        from fragility_or import _pit_backtest
        ref = _pit_backtest(dict(ch, gspc=close), _Q, _MIN_WARMUP)
        full = at._or_flag(table, keys)
        row["reproduces_live"] = all(
            at._score(full, close, h, DD_THRESHOLD)[k] == ref["horizons"][h]["or"][k]
            for h in horizons for k in ("n_episodes", "n_caught", "n_alarms"))
    null = shift_null(orf, passes, close)
    row["luck"] = {"n": len(null),
                   "q": (round(float(np.quantile(null, LUCK_Q)), 3) if len(null) else None),
                   "median": (round(float(np.median(null)), 3) if len(null) else None)}
    row["channel_role"] = channel_role(win, filt_all, horizons)
    return row


def channel_role(win: dict, filt: pd.DataFrame, horizons: tuple = HORIZONS) -> dict:
    """Reported, not read: x_t as one more OR channel at its own PIT p90 (the
    KB-019 admission protocol), beside the unfiltered flag on the same readings."""
    keys = tuple(win["keys"]) + ("SKEW",)
    idx = win["channels"][win["keys"][0]].index
    x = skew_filter_x(filt, idx)
    ch = dict(win["channels"], SKEW=x)
    table = at.pit_channel_table(ch, keys=keys)
    if table.empty:
        return {"n_readings": 0}
    with_s, without = at._or_flag(table, keys), at._or_flag(table, win["keys"])
    out = {"n_readings": len(table), "first": str(table.index[0].date())}
    for h in horizons:
        a = at._score(with_s, win["close"], h, DD_THRESHOLD)
        b = at._score(without, win["close"], h, DD_THRESHOLD)
        la = at.loco_recall(ch, win["close"], "or", h, DD_THRESHOLD, keys=keys)
        lb = at.loco_recall(ch, win["close"], "or", h, DD_THRESHOLD, keys=win["keys"])
        out[h] = {"caught": a["n_caught"], "ref_caught": b["n_caught"], "n_episodes": a["n_episodes"],
                  "precision": a["alarm_precision"], "ref_precision": b["alarm_precision"],
                  "loco_caught": la["caught"], "loco_ref_caught": lb["caught"],
                  "loco_n": la["n_crises"]}
    return out


def skew_filter_x(filt: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    """`x` on the channel grid; NaN where not ready or stale (a degraded
    reading: neither fires nor enters the channel's history)."""
    return filt["x"].where(filt["ready"]).reindex(idx)


# ---------------------------------------------------------------------------
# the bar
# ---------------------------------------------------------------------------

def verdict(row: dict, h: int = DECISIVE) -> dict:
    """Apply IMP-9 §9.A's bar to one window's row.

      ``underpowered``  fewer than MIN_ALARMS filtered alarm episodes (PIT)
      ``too_late``      median lead to trough below MIN_LEAD_5D, or undefined
      ``recall_lost``   more than MAX_RECALL_LOST crises lost vs the unfiltered
                        flag, under PIT or under LOCO
      ``no_edge``       PIT precision below the unfiltered + PASS_PREC_GAIN, or
                        below the window's floor (live: goal 2's 0.40)
      ``luck``          precision not above the LUCK_Q quantile of the shifted
                        filters
      ``pass``

    All at the decisive horizon. In that order; each returns at once, and the
    pass clause is unreachable until every disqualifier has been checked.
    """
    pit, loco = row["pit"][h], row["loco"][h]

    if pit["n_alarms"] < MIN_ALARMS:
        return {"verdict": "underpowered",
                "reason": f"{pit['n_alarms']} filtered alarms at {h}d < {MIN_ALARMS}"}

    lead = pit["median_lead"]
    if lead is None or lead < MIN_LEAD_5D:
        return {"verdict": "too_late",
                "reason": f"median lead to trough at {h}d is {lead} < {MIN_LEAD_5D} days"}

    lost_pit = pit["ref_caught"] - pit["caught"]
    lost_loco = loco["ref_caught"] - loco["caught"]
    if lost_pit > MAX_RECALL_LOST or lost_loco > MAX_RECALL_LOST:
        return {"verdict": "recall_lost",
                "reason": f"at {h}d the filter loses {lost_pit} crisis(es) under PIT "
                          f"({pit['caught']} vs {pit['ref_caught']}) and {lost_loco} under LOCO "
                          f"({loco['caught']} vs {loco['ref_caught']}); allowed {MAX_RECALL_LOST}"}

    prec = -np.inf if pit["precision"] is None else float(pit["precision"])
    ref = -np.inf if pit["ref_precision"] is None else float(pit["ref_precision"])
    need = ref + PASS_PREC_GAIN
    if row.get("floor") is not None:
        need = max(need, float(row["floor"]))
    if prec < need - 1e-12:
        return {"verdict": "no_edge",
                "reason": f"precision at {h}d {pit['precision']} vs unfiltered "
                          f"{pit['ref_precision']}; needs ≥ {round(need, 3)}"}

    q = row["luck"]["q"]
    if q is None or not prec > q:
        return {"verdict": "luck",
                "reason": f"precision {pit['precision']} does not beat the {LUCK_Q:.0%} "
                          f"quantile of {row['luck']['n']} shifted filters ({q})"}

    return {"verdict": "pass",
            "reason": f"no crisis lost at {h}d; precision {pit['precision']} vs "
                      f"{pit['ref_precision']}, above {q} from the shifted filters"}


def overall(rows: dict) -> str:
    """9.A passes only if every window reads `pass`."""
    return "pass" if rows and all(r["verdict"]["verdict"] == "pass" for r in rows.values()) else "fail"


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _fmt(x):
    return "—" if x is None else x


def render(rows: dict, skew_span: tuple) -> str:
    lines = ["# IMP-9 §9.A — CBOE SKEW as a filter on the OR flag", "",
             f"Overall: **{overall(rows)}** (both windows must pass). "
             f"SKEW {skew_span[0]} → {skew_span[1]}. Decisive horizon {DECISIVE}d; "
             f"bar in `improvement-track.md` IMP-9 §9.A, written before this run.", ""]
    for name, r in rows.items():
        v = r["verdict"]
        lines += [f"## {name} — {r['what']}", "",
                  f"Verdict: **{v['verdict']}** — {v['reason']}", "",
                  f"Readings {r['n_readings']} ({r['first']} → {r['last']}). "
                  f"The unfiltered flag fired on {r['or_firings']}; the filter blocked "
                  f"{r['blocked']} ({(r['blocked'] / r['or_firings'] if r['or_firings'] else 0):.0%}); "
                  f"{r['stale_open']} stood because SKEW was stale."
                  + ("" if "reproduces_live" not in r else
                     f" Unfiltered row {'reproduces' if r['reproduces_live'] else 'DIFFERS FROM'} "
                     "`fragility_or._pit_backtest`."), "",
                  "| horizon | crises | caught (unfiltered) | alarms (unfiltered) | precision (unfiltered) "
                  "| median lead (unfiltered) | LOCO caught (unfiltered) of crises |",
                  "|---|---|---|---|---|---|---|"]
        for h, p in r["pit"].items():
            l = r["loco"][h]
            lines.append(f"| {h}d | {p['n_episodes']} | {p['caught']} ({p['ref_caught']}) | "
                         f"{p['n_alarms']} ({p['ref_n_alarms']}) | {_fmt(p['precision'])} "
                         f"({_fmt(p['ref_precision'])}) | {_fmt(p['median_lead'])} "
                         f"({_fmt(p['ref_median_lead'])}) | {l['caught']} ({l['ref_caught']}) of {l['n_crises']} |")
        for h, l in r["loco"].items():
            if l["lost"]:
                lines.append(f"\nLOCO {h}d, crises the filter lost: "
                             + ", ".join(f"{s} → {e}" for s, e in l["lost"]))
        lk = r["luck"]
        lines += ["", f"Shifted filters ({lk['n']}): median precision {lk['median']}, "
                      f"{LUCK_Q:.0%} quantile {lk['q']}.", ""]
        c = r["channel_role"]
        if c.get("n_readings"):
            lines += [f"Reported, not read — SKEW as a fourth OR channel at its PIT p90 "
                      f"({c['n_readings']} readings from {c['first']}):", ""]
            for h in HORIZONS:
                ch = c[h]
                lines.append(f"- {h}d: caught {ch['caught']} vs {ch['ref_caught']} of {ch['n_episodes']}, "
                             f"precision {_fmt(ch['precision'])} vs {_fmt(ch['ref_precision'])}; "
                             f"LOCO {ch['loco_caught']} vs {ch['loco_ref_caught']} of {ch['loco_n']}")
            lines.append("")
    lines.append("An improvement-track gate: the result goes to the KB either way.")
    return "\n".join(lines) + "\n"


def run(out_dir: Path = _RESULTS, cached: bool = False,
        skew: Optional[pd.Series] = None, windows: Optional[list] = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    skew_file = out_dir / "skew.csv"
    if skew is None:
        if cached and skew_file.exists():
            skew = parse_cboe(skew_file.read_text())
        else:
            skew = fetch_skew()
            pd.DataFrame({"DATE": skew.index.strftime("%Y-%m-%d"), "SKEW": skew.values}) \
              .to_csv(skew_file, index=False)
    if windows is None:
        windows = [live_window(out_dir / "channels_live.pkl" if cached else None),
                   long_window(out_dir / "channels_long.pkl" if cached else None)]
    rows = {}
    for win in windows:
        row = score_window(win, skew)
        row["verdict"] = verdict(row)
        rows[win["name"]] = row
        print(f"{win['name']}: {row['verdict']['verdict']} — {row['verdict']['reason']}")
    span = (str(skew.index[0].date()), str(skew.index[-1].date()))
    report = render(rows, span)
    (out_dir / "report.md").write_text(report)
    (out_dir / "summary.json").write_text(json.dumps(
        {"overall": overall(rows), "skew_span": span, "rows": rows,
         "run_at": datetime.now().astimezone().isoformat(timespec="seconds")},
        indent=1, default=str))
    print(f"overall: {overall(rows)}")
    return {"overall": overall(rows), "rows": rows}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cached", action="store_true",
                    help="reuse (or write) the channels and the SKEW file under results/filter_testing/")
    args = ap.parse_args(argv)
    run(cached=args.cached)


if __name__ == "__main__":
    main()
