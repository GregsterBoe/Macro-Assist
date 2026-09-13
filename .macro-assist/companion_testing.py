"""
companion_testing.py — IMP-7: the companion measures IMP-1 listed and never ran.

IMP-1 named cross-sectional dispersion, average pairwise correlation and breadth
as "cheap companions computable from the same panel" as the absorption ratio and
turbulence; the arc went AR -> turbulence -> OR and never ran them. Eigenvector
loading concentration (from the 2026-09 review) rides along as a fourth. Each is
asked the two questions every OR-channel candidate has been asked (IMP-2 credit,
KB-019): does it lead >=5% drawdowns standalone, and does it add PIT recall to the
live OR trio at held precision? One run, one KB entry for all four, either way.

CLOSED 2026-09-13, negative -> KB-032. All four have standalone skill; DISP
`precision_lost`, BREADTH and EIGC `redundant`, CORR `admit` by the letter of
the bar on one post-crash aftershock (two trio-silent readings in 664). Not
wired (todo.md #16). The bar below is kept as written; its missing lead clause
is recorded in KB-032 for the next one.

The four measures — definitions and SIGNS fixed in improvement-track.md (IMP-7)
before any were computed; higher = more fragile throughout:

  DISP     std across the nine sectors' daily log returns, mean of the last
           DISP_SMOOTH days
  CORR     mean upper-triangle pairwise correlation of daily log returns over
           CORR_WINDOW days (signed; sectors correlate positively)
  BREADTH  fraction of sectors closing BELOW their own BREADTH_SMA-day simple
           moving average, mean of the last BREADTH_SMOOTH days
  EIGC     participation ratio 1 / sum(v_i^4) of the unit-norm top eigenvector of
           the EIGC_WINDOW-day correlation matrix — the effective number of
           sectors the dominant factor loads on (1..n)

All are walked on the KB-021 live anchor grid (`fragility_or.build_channels`'s
`common`) from the ETF panel's history up to each anchor date only, through the
same `_walk_panel_signal` the live AR/TURB channels use.

The bar (`verdict()`), disqualifiers first, each its own named verdict:

  no_standalone_skill  5d non-overlap AUC <= AUC_BAR on the anchor-grid readings
                       (`input_testing.evaluate_signal`, the KB-002 bar as IMP-1
                       and IMP-2 applied it). Step 2 still runs so the KB has
                       the number; the companion cannot be admitted.
  underpowered         fewer than MIN_EPISODES drawdown episodes at 5d on the
                       shared PIT window
  precision_lost       4-channel PIT precision below the 3-channel's by more
                       than PREC_TOL at either horizon
  admit                PIT recall up by >= ADMIT_RECALL_GAIN crises at BOTH
                       horizons, AND LOCO recall not below the trio's at either
  redundant            everything else — the KB-019 outcome

Trio and trio-plus-companion are scored on the SHARED evaluable window (a
companion with fewer finite readings shrinks the window for both rows — the
IMP-5.3 discipline), and the trio row is checked against
`fragility_or._pit_backtest` on the full window as the regression guard. Fixed
config, no sweeps. Run: `python companion_testing.py [channels.pkl]`.
"""
from __future__ import annotations

import pickle
from typing import Callable, Optional

import numpy as np
import pandas as pd

from fragility import _to_log_returns
from fragility_backtest import fetch_sector_etfs
from fragility_or import build_channels, _walk_panel_signal, _CH_KEYS, _Q, _MIN_WARMUP
from aggregator_testing import pit_channel_table, _or_flag, _score, loco_recall
from input_testing import evaluate_signal

# --- Pre-registered constants. Fixed, NOT swept (KB-017/018 discipline). -------
DISP_SMOOTH = 20
CORR_WINDOW = 60
BREADTH_SMA = 50
BREADTH_SMOOTH = 20
EIGC_WINDOW = 120
COMPANIONS = ("DISP", "CORR", "BREADTH", "EIGC")
HORIZONS = (5, 10)
DD_THRESHOLD = 0.05

# The bar (improvement-track.md IMP-7, written 2026-09-13 before the run).
AUC_BAR = 0.60            # no_standalone_skill: 5d non-overlap AUC must exceed this
MIN_EPISODES = 10         # underpowered: 5d drawdown episodes on the shared PIT window
PREC_TOL = 0.02           # precision_lost: 4-ch PIT precision below 3-ch by more than this
ADMIT_RECALL_GAIN = 1     # admit: PIT crises caught above the trio, at BOTH horizons


# ---------------------------------------------------------------------------
# The four measures — each takes the `_walk_panel_signal` slice dict
# ---------------------------------------------------------------------------

def _returns_frame(sliced: dict, min_rows: int) -> Optional[pd.DataFrame]:
    """Aligned daily log-return panel from the sliced close histories, or None
    if fewer than three names / rows than `min_rows`."""
    cols = {}
    for name, close in sliced.items():
        if close is None:
            continue
        r = _to_log_returns(close)
        if len(r):
            cols[name] = r
    if len(cols) < 3:
        return None
    frame = pd.DataFrame(cols).dropna()
    if len(frame) < min_rows or frame.shape[1] < 3:
        return None
    return frame


def dispersion_signal(sliced: dict, smooth: int = DISP_SMOOTH) -> Optional[float]:
    """DISP — cross-sectional std of daily log returns, mean over the last `smooth` days."""
    R = _returns_frame(sliced, smooth)
    if R is None:
        return None
    xs = R.tail(smooth).std(axis=1, ddof=1)
    return float(xs.mean())


def pairwise_corr_signal(sliced: dict, window: int = CORR_WINDOW) -> Optional[float]:
    """CORR — mean pairwise (signed) correlation over the trailing `window` days."""
    R = _returns_frame(sliced, window)
    if R is None:
        return None
    win = R.tail(window)
    if np.any(win.std(axis=0).to_numpy() <= 0):
        return None
    c = win.corr().to_numpy()
    iu = np.triu_indices_from(c, k=1)
    vals = c[iu]
    if not np.all(np.isfinite(vals)):
        return None
    return float(vals.mean())


def breadth_signal(sliced: dict, sma: int = BREADTH_SMA,
                   smooth: int = BREADTH_SMOOTH) -> Optional[float]:
    """BREADTH — fraction of sectors closing BELOW their own `sma`-day simple
    moving average, mean of the last `smooth` days. Higher = narrower participation."""
    cols = {}
    for name, close in sliced.items():
        if close is None:
            continue
        p = pd.Series(close).astype(float)
        p = p.where(p > 0).dropna()
        if len(p) >= sma + smooth:
            cols[name] = p
    if len(cols) < 3:
        return None
    px = pd.DataFrame(cols).dropna()
    if len(px) < sma + smooth:
        return None
    below = (px < px.rolling(sma).mean()).astype(float)
    frac = below.iloc[sma - 1:].mean(axis=1)
    return float(frac.tail(smooth).mean())


def eigen_concentration_signal(sliced: dict, window: int = EIGC_WINDOW) -> Optional[float]:
    """EIGC — participation ratio of the top eigenvector of the trailing
    `window`-day correlation matrix: 1 / sum(v_i^4), the effective number of
    sectors the dominant factor loads on. Higher = the factor is everyone's."""
    R = _returns_frame(sliced, window)
    if R is None:
        return None
    win = R.tail(window).to_numpy()
    if np.any(win.std(axis=0) <= 0):
        return None
    c = np.corrcoef(win, rowvar=False)
    if not np.all(np.isfinite(c)):
        return None
    w, v = np.linalg.eigh(c)                    # ascending
    top = v[:, -1]
    top = top / np.linalg.norm(top)
    return float(1.0 / np.sum(top ** 4))


SIGNAL_FNS: dict[str, Callable[[dict], Optional[float]]] = {
    "DISP":    dispersion_signal,
    "CORR":    pairwise_corr_signal,
    "BREADTH": breadth_signal,
    "EIGC":    eigen_concentration_signal,
}

# Slice depth / readiness per measure, chosen so each has its window plus slack.
_WALK_KW = {
    "DISP":    dict(lookback=DISP_SMOOTH + 60, min_history=DISP_SMOOTH + 5),
    "CORR":    dict(lookback=CORR_WINDOW + 60, min_history=CORR_WINDOW + 5),
    "BREADTH": dict(lookback=BREADTH_SMA + BREADTH_SMOOTH + 60,
                    min_history=BREADTH_SMA + BREADTH_SMOOTH + 5),
    "EIGC":    dict(lookback=EIGC_WINDOW + 60, min_history=EIGC_WINDOW + 5),
}


def build_companions(px: pd.DataFrame, anchor: pd.DatetimeIndex,
                     names: tuple = COMPANIONS) -> dict:
    """Walk each companion forward on the ETF panel `px` over `anchor`, through
    the same look-ahead-safe walker the live AR/TURB channels use."""
    hist = {c: px[c].dropna() for c in px.columns}
    return {n: _walk_panel_signal(SIGNAL_FNS[n], hist, anchor, **_WALK_KW[n])
            for n in names}


# ---------------------------------------------------------------------------
# Scoring one companion: standalone gate, then OR admission on the shared window
# ---------------------------------------------------------------------------

def _shared_channels(channels: dict, name: str, series: pd.Series) -> dict:
    """The trio plus the companion, all on the readings where the companion is
    finite — the SHARED window both rows are scored on."""
    common = channels["common"]
    x = series.reindex(common)
    keep = common[x.notna().to_numpy()]
    out = {k: channels[k].reindex(keep) for k in _CH_KEYS}
    out[name] = x.reindex(keep)
    out["common"] = keep
    out["gspc"] = channels["gspc"]
    return out


def score_companion(
    name: str,
    series: pd.Series,
    channels: dict,
    horizons: tuple = HORIZONS,
    threshold: float = DD_THRESHOLD,
    q: float = _Q,
    min_warmup: int = _MIN_WARMUP,
    verbose: bool = True,
) -> dict:
    """Standalone gate + OR-admission (PIT and LOCO, trio vs trio+companion on
    the shared window). Returns the row `verdict()` reads."""
    gspc = channels["gspc"]
    row = {"companion": name, "standalone": {}, "pit": {}, "loco": {}}

    # (1) standalone — on the anchor-grid readings, as [A] of run_etf_panel_gate
    sa = evaluate_signal(series.dropna(), gspc, threshold, horizons, name=name,
                         verbose=verbose)
    row["standalone"] = {h: {"auc_nonoverlap": sa[h]["auc_nonoverlap"],
                             "auc_overlap": sa[h]["auc_overlap"],
                             "episode_recall": sa[h]["episode_recall"],
                             "alarm_precision": sa[h]["alarm_precision"],
                             "n_crises": sa[h]["n_crises"],
                             "n_alarms": sa[h]["n_alarms"],
                             "median_lead": sa[h]["median_lead"]}
                         for h in horizons}

    # (2) OR admission on the shared window
    ch = _shared_channels(channels, name, series)
    keys3, keys4 = tuple(_CH_KEYS), tuple(_CH_KEYS) + (name,)
    t4 = pit_channel_table(ch, q_watch=q, min_warmup=min_warmup, keys=keys4)
    t3 = pit_channel_table(ch, q_watch=q, min_warmup=min_warmup, keys=keys3)
    f4 = _or_flag(t4, keys4)
    f3 = _or_flag(t3, keys3).reindex(f4.index, fill_value=False).astype(bool)
    row["window"] = (len(ch["common"]), len(f4),
                     (f4.index[0].date() if len(f4) else None),
                     (f4.index[-1].date() if len(f4) else None))
    for h in horizons:
        v, r = _score(f4, gspc, h, threshold), _score(f3, gspc, h, threshold)
        row["pit"][h] = {
            "n_episodes": v["n_episodes"],
            "caught": v["n_caught"], "ref_caught": r["n_caught"],
            "n_alarms": v["n_alarms"], "ref_n_alarms": r["n_alarms"],
            "precision": v["alarm_precision"], "ref_precision": r["alarm_precision"],
            "recall": v["episode_recall"], "ref_recall": r["episode_recall"],
            "median_lead": v["median_lead"], "ref_median_lead": r["median_lead"],
        }
        lv = loco_recall(ch, gspc, "or", h, threshold, q_watch=q, keys=keys4)
        lr = loco_recall(ch, gspc, "or", h, threshold, q_watch=q, keys=keys3)
        row["loco"][h] = {
            "n_crises": lv["n_crises"],
            "caught": lv["caught"], "ref_caught": lr["caught"],
            "recall": lv["recall"], "ref_recall": lr["recall"],
            "differs": [(s, e, hit) for (s, e, hit), (_s, _e, rhit)
                        in zip(lv["folds"], lr["folds"]) if hit != rhit],
        }
    return row


# ---------------------------------------------------------------------------
# The bar
# ---------------------------------------------------------------------------

def verdict(row: dict, horizons: tuple = HORIZONS) -> dict:
    """Apply the pre-registered IMP-7 bar to one companion's row.

      ``no_standalone_skill``  5d non-overlap AUC <= AUC_BAR (or undefined)
      ``underpowered``         fewer than MIN_EPISODES 5d episodes on the shared
                               PIT window
      ``precision_lost``       4-ch PIT precision < 3-ch − PREC_TOL at either h
      ``admit``                PIT caught >= trio + ADMIT_RECALL_GAIN at BOTH h,
                               and LOCO caught >= trio at both
      ``redundant``            cleared every disqualifier, did not admit

    Disqualifiers are evaluated in that order and each returns immediately; the
    admit clause is unreachable until all three have been checked.
    """
    h0 = horizons[0]
    sa, pit, loco = row["standalone"], row["pit"], row["loco"]

    # --- Disqualifier 1: standalone skill ---------------------------------
    a = sa[h0]["auc_nonoverlap"]
    if a is None or not np.isfinite(a) or a <= AUC_BAR:
        return {"verdict": "no_standalone_skill",
                "reason": f"{h0}d non-overlap AUC {a} <= {AUC_BAR}"}

    # --- Disqualifier 2: power --------------------------------------------
    n = pit[h0]["n_episodes"]
    if n < MIN_EPISODES:
        return {"verdict": "underpowered",
                "reason": f"{n} drawdown episodes at {h0}d on the shared PIT window "
                          f"< {MIN_EPISODES}"}

    # --- Disqualifier 3: precision ----------------------------------------
    def _p(x):
        return -np.inf if x is None else float(x)

    for h in horizons:
        if _p(pit[h]["precision"]) < _p(pit[h]["ref_precision"]) - PREC_TOL:
            return {"verdict": "precision_lost",
                    "reason": f"PIT {h}d precision {pit[h]['precision']} vs trio "
                              f"{pit[h]['ref_precision']} — below by more than {PREC_TOL}"}

    # --- Only now, the admit clause ---------------------------------------
    recall_up = all(pit[h]["caught"] >= pit[h]["ref_caught"] + ADMIT_RECALL_GAIN
                    for h in horizons)
    loco_held = all(loco[h]["caught"] >= loco[h]["ref_caught"] for h in horizons)
    if recall_up and loco_held:
        return {"verdict": "admit",
                "reason": f"PIT recall +{ADMIT_RECALL_GAIN} crisis or more at both "
                          f"horizons at held precision; LOCO recall held"}
    return {"verdict": "redundant",
            "reason": ("cleared every disqualifier; PIT recall did not rise at both "
                       "horizons" if not recall_up else
                       "cleared every disqualifier; PIT recall rose but LOCO recall fell")}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run_companion_gate(
    channels: Optional[dict] = None,
    px: Optional[pd.DataFrame] = None,
    names: tuple = COMPANIONS,
    horizons: tuple = HORIZONS,
    threshold: float = DD_THRESHOLD,
    min_warmup: int = _MIN_WARMUP,
    cache: Optional[str] = None,
) -> dict:
    """IMP-7, one run. Builds (or loads) the KB-021 live channels, walks the four
    companions on the same anchor grid, checks the trio row reproduces
    `fragility_or._pit_backtest` (the regression guard), scores each companion
    standalone and as a fourth OR channel, applies `verdict()`. Prints the
    table; returns {name: row + verdict}."""
    if channels is None:
        if cache:
            with open(cache, "rb") as f:
                channels = pickle.load(f)
        else:
            channels = build_channels(refresh=True)
    if px is None:
        px = fetch_sector_etfs(start="2007-01-01")
    common, gspc = channels["common"], channels["gspc"]
    print(f"IMP-7 companion gate — live window {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()}; ETF panel {px.shape[1]} sectors")

    # Regression guard: the trio row on the full window == the live self-check.
    from fragility_or import _pit_backtest
    ref = _pit_backtest(channels, _Q, min_warmup)
    t3 = pit_channel_table(channels, min_warmup=min_warmup)
    f3 = _or_flag(t3)
    for h in horizons:
        mine = _score(f3, gspc, h, threshold)
        theirs = ref["horizons"][h]["or"]
        same = all(mine[k] == theirs[k] for k in ("n_episodes", "n_caught", "n_alarms"))
        print(f"  trio OR reference h={h:>2}d: {mine['n_caught']}/{mine['n_episodes']} "
              f"alarms={mine['n_alarms']} prec={mine['alarm_precision']}  "
              f"[{'reproduces' if same else 'DIFFERS FROM'} fragility_or._pit_backtest]")

    print("\nWalking companions on the anchor grid...")
    comps = build_companions(px, common, names)
    for n in names:
        s = comps[n]
        print(f"  {n:<8} {len(s)} readings {s.index[0].date()}..{s.index[-1].date()}  "
              f"mean={s.mean():.4f} sd={s.std():.4f}")

    out = {}
    for n in names:
        print(f"\n=== {n} ===")
        row = score_companion(n, comps[n], channels, horizons, threshold,
                              min_warmup=min_warmup, verbose=True)
        row["verdict"] = verdict(row, horizons)
        out[n] = row
        w = row["window"]
        print(f"  shared window {w[0]} readings; PIT evaluable {w[1]} {w[2]}..{w[3]}")
        for h in horizons:
            p, l = row["pit"][h], row["loco"][h]
            print(f"  PIT  h={h:>2}d  recall {p['caught']}/{p['n_episodes']} "
                  f"(trio {p['ref_caught']})  alarms {p['n_alarms']} (trio {p['ref_n_alarms']})  "
                  f"prec {p['precision']} (trio {p['ref_precision']})  "
                  f"lead {p['median_lead']} (trio {p['ref_median_lead']})")
            print(f"  LOCO h={h:>2}d  {l['n_crises']} folds  caught {l['caught']} "
                  f"(trio {l['ref_caught']})")
            for (s, e, hit) in l["differs"]:
                print(f"        differs {s}..{e}: {'+companion only' if hit else 'trio only'}")
        print(f"  VERDICT: {row['verdict']['verdict']} — {row['verdict']['reason']}")
    return out


if __name__ == "__main__":
    import sys
    run_companion_gate(cache=(sys.argv[1] if len(sys.argv) > 1 else None))
