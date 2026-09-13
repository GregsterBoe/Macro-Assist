"""
aggregator_testing.py — IMP-6: precision at held recall, the aggregator question.

The OR recall mode (`fragility_or.py`, KB-021) fires when ANY of three channels
{composite, absorption ratio, turbulence} is at/above its own point-in-time top
decile. Its operating point is recall ~0.6-0.8 / precision ~0.3 at 5d — roughly
two alarms in three are false. Every "add a channel" route is closed (IMP-2,
IMP-3, KB-018/019); this asks the one question left about what exists: can
precision rise WITHOUT paying recall, by changing only how the three channels are
combined? Three pre-registered variants, one run, one KB entry either way.

  or       the live flag, unchanged — the reference row
  persist  the OR flag on TWO CONSECUTIVE READINGS (the anchor grid is strided,
           so "consecutive" is consecutive readings, not days). The classic
           false-positive filter; its cost is lead time, which is a disqualifier.
  tiers    watch = any channel >= its PIT p90 (today's flag); ALERT = two of
           three >= p90, or any one >= p97. `alert` is what is scored.
  logit    a logistic on the three channels' percentiles (three slopes + an
           intercept), fitted out-of-sample, threshold chosen on training data
           only. The honest floor for "learn the weighting": if this cannot beat
           OR, tree models on ~18 crises will not.

Protocols — the KB-017 pair, on the KB-021 live window (`comp ∩ ETF`,
`fragility_or.build_channels`):

  PIT   expanding-window thresholds; each reading's cut / percentile is fit on
        that channel's own STRICTLY PRIOR readings (warm-up 252). Recall AND
        precision, on the post-warm-up window. The logistic is refit at every
        reading on the readings whose labels had RESOLVED by then (a label at
        horizon h is known h trading days later), so it never sees its own day.
  LOCO  leave-one-crisis-out; the drawdown episodes are the folds. Cuts, the
        percentile transform and the logistic are fit on every reading OUTSIDE
        the held-out crisis and asked whether the flag fires inside it. Recall
        only — KB-017 nuance (3): the held-out spans are too short for an honest
        precision denominator; precision is read from PIT.

The logistic's threshold rule, fixed here before the run: on the training set,
the threshold is set so the logistic fires on the SAME FRACTION of readings as
the OR flag does on that training set (equal alarm budget). The comparison is
then purely "does the fitted weighting RANK days better than OR" — which is the
question. Any other rule (max-F1, recall-matched) picks the threshold by looking
at the outcome it is scored on.

Each variant is scored against the OR flag ON ITS OWN EVALUABLE WINDOW (persist
drops the first reading; logit needs `LOGIT_MIN_TRAIN` resolved readings), so
window-shrink is never mistaken for skill — the IMP-5.3 discipline.

The bar (improvement-track.md IMP-6, written 2026-09-13 before any variant ran)
is `verdict()`. Disqualifiers are evaluated FIRST, each with its own named
verdict, and the pass clause is unreachable until all have been checked —
[KB-027]'s structure. Fixed config, no sweeps. Run: `python aggregator_testing.py`.
"""
from __future__ import annotations

import pickle
from typing import Optional

import numpy as np
import pandas as pd

from fragility_backtest import (
    drawdown_label, episode_scoring, collapse_episodes, lead_time_stats,
)
from fragility_or import build_channels, _CH_KEYS, _Q, _MIN_WARMUP

# --- Pre-registered constants. Fixed, NOT swept (KB-017/018 discipline). -------
Q_WATCH = _Q            # 0.90 — the live per-channel cut (unchanged)
Q_ALERT = 0.97          # tiers: a single channel this deep is an alert on its own
K_OF_N = 2              # tiers: this many channels at/above p90 is an alert
PERSIST = 2             # persist: consecutive readings the OR must be set on
LOGIT_C = 100.0         # logit: near-unregularised — the floor, not a tuned model
LOGIT_MIN_TRAIN = 100   # logit (PIT): resolved training readings before it is evaluable
LOCO_MIN_TRAIN = 60     # LOCO: training readings a fold needs (as input_testing._loco_recall)
HORIZONS = (5, 10)
DD_THRESHOLD = 0.05
VARIANTS = ("persist", "tiers", "logit")

# --- The bar. --------------------------------------------------------------------
MIN_ALARMS = 10         # underpowered: fewer distinct alarms than this on the PIT window
MIN_LEAD_5D = 2.0       # too_late: median lead to trough (5d, PIT true positives) below this
MAX_RECALL_LOST = 1     # recall_lost: more crises than this lost vs OR under LOCO, either h
PASS_PREC_GAIN = 0.05   # route 1: PIT precision gain, absolute, at BOTH horizons ...
PASS_RECALL_TOL = 1     #          ... with PIT recall within this many crises of OR
PASS_LOCO_GAIN = 2      # route 2: LOCO recall gain in crises at BOTH horizons ...
PASS_PREC_TOL = 0.02    #          ... with PIT precision within this of OR (absolute)


# ---------------------------------------------------------------------------
# PIT feature table — one row per evaluable reading
# ---------------------------------------------------------------------------

def pit_channel_table(
    channels: dict,
    q_watch: float = Q_WATCH,
    q_alert: float = Q_ALERT,
    min_warmup: int = _MIN_WARMUP,
    keys: tuple = _CH_KEYS,
) -> pd.DataFrame:
    """Per reading, per channel: the value's percentile in that channel's own
    STRICTLY PRIOR finite readings (`<k>_pct`, 0-1), and whether it is at/above
    the prior q_watch (`<k>_w`) and q_alert (`<k>_a`) quantiles. A reading is
    evaluable only once EVERY channel has `min_warmup` finite priors — the same
    admission rule as `input_testing._pit_decile_or_flags`, so `_w` OR-ed across
    channels IS the live flag. A NaN reading (degraded composite, KB-029) neither
    fires nor enters its channel's history; its percentile is NaN.
    """
    idx = channels["comp"].index
    arrs = {k: channels[k].reindex(idx).to_numpy(dtype=float) for k in keys}
    rows, keep = [], []
    for i in range(len(idx)):
        if i < min_warmup:
            continue
        row, ok = {}, True
        for k in keys:
            past = arrs[k][:i]
            past = past[np.isfinite(past)]
            if len(past) < min_warmup:
                ok = False
                break
            cur = arrs[k][i]
            if np.isfinite(cur):
                row[f"{k}_pct"] = float((past < cur).mean())
                row[f"{k}_w"] = bool(cur >= np.quantile(past, q_watch))
                row[f"{k}_a"] = bool(cur >= np.quantile(past, q_alert))
            else:
                row[f"{k}_pct"] = np.nan
                row[f"{k}_w"] = False
                row[f"{k}_a"] = False
        if not ok:
            continue
        keep.append(idx[i])
        rows.append(row)
    out = pd.DataFrame(rows, index=pd.DatetimeIndex(keep))
    if out.empty:
        cols = [f"{k}_{s}" for k in keys for s in ("pct", "w", "a")]
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([]))
    return out


# ---------------------------------------------------------------------------
# The rule-based aggregators, on a feature table (PIT or train-fit)
# ---------------------------------------------------------------------------

def _or_flag(table: pd.DataFrame, keys: tuple = _CH_KEYS) -> pd.Series:
    f = table[[f"{k}_w" for k in keys]].astype(bool)
    return f.any(axis=1)


def _persist_flag(table: pd.DataFrame, keys: tuple = _CH_KEYS, n: int = PERSIST) -> pd.Series:
    """The OR flag set on `n` consecutive readings. The first n-1 readings cannot
    qualify and are DROPPED (the variant's evaluable window), not scored False."""
    o = _or_flag(table, keys)
    out = o.copy()
    for lag in range(1, n):
        out = out & o.shift(lag, fill_value=False).astype(bool)
    return out.iloc[n - 1:]


def _tiers_flag(table: pd.DataFrame, keys: tuple = _CH_KEYS,
                k_of_n: int = K_OF_N) -> pd.Series:
    """ALERT tier: `k_of_n` channels at/above p90, or any one at/above p97."""
    w = table[[f"{k}_w" for k in keys]].astype(bool).sum(axis=1)
    a = table[[f"{k}_a" for k in keys]].astype(bool).any(axis=1)
    return (w >= k_of_n) | a


def aggregate(table: pd.DataFrame, variant: str, keys: tuple = _CH_KEYS) -> pd.Series:
    if variant == "or":
        return _or_flag(table, keys)
    if variant == "persist":
        return _persist_flag(table, keys)
    if variant == "tiers":
        return _tiers_flag(table, keys)
    raise ValueError(f"aggregate: unknown rule-based variant {variant!r}")


# ---------------------------------------------------------------------------
# The fitted aggregator
# ---------------------------------------------------------------------------

def _fit_logit(X: np.ndarray, y: np.ndarray, C: float = LOGIT_C):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=C, solver="lbfgs", max_iter=1000)
    m.fit(X, y)
    return m


def _budget_threshold(p_train: np.ndarray, fire_rate: float) -> float:
    """The probability cut that fires on `fire_rate` of the training readings —
    the OR flag's own alarm budget on that set. fire_rate 0 → never fires."""
    if fire_rate <= 0:
        return np.inf
    return float(np.quantile(p_train, 1.0 - fire_rate))


def logit_pit_flag(
    table: pd.DataFrame,
    gspc: pd.Series,
    horizon: int,
    threshold: float = DD_THRESHOLD,
    min_train: int = LOGIT_MIN_TRAIN,
    keys: tuple = _CH_KEYS,
    C: float = LOGIT_C,
) -> pd.Series:
    """Expanding-window logistic on the PIT percentiles. At reading i the model is
    fit on the evaluable readings whose `horizon`-day label had RESOLVED by i
    (label date + horizon trading days <= date i), and the cut is the OR flag's
    firing rate on that same training set. Readings with fewer than `min_train`
    resolved training rows are DROPPED (not evaluable). NaN features (a degraded
    composite) are not trained on and read as non-firing.
    """
    close = pd.Series(gspc).astype(float)
    y_all = drawdown_label(close, threshold, horizon)
    y = y_all.reindex(table.index)
    pos = pd.Series(np.arange(len(close)), index=close.index).reindex(table.index)
    feats = table[[f"{k}_pct" for k in keys]].to_numpy(dtype=float)
    orf = _or_flag(table, keys).to_numpy()
    yv = y.to_numpy(dtype=float)
    posv = pos.to_numpy(dtype=float)
    finite = np.isfinite(feats).all(axis=1)

    out_idx, out_val = [], []
    for i in range(len(table)):
        resolved = (posv + horizon <= posv[i]) & np.isfinite(yv) & finite
        n_tr = int(resolved.sum())
        if n_tr < min_train:
            continue
        ytr = yv[resolved].astype(bool)
        if ytr.all() or not ytr.any():
            continue                      # degenerate training labels — not evaluable
        m = _fit_logit(feats[resolved], ytr, C)
        p_tr = m.predict_proba(feats[resolved])[:, 1]
        thr = _budget_threshold(p_tr, float(orf[resolved].mean()))
        if finite[i]:
            p_i = float(m.predict_proba(feats[i:i + 1])[:, 1][0])
            fired = bool(p_i >= thr)
        else:
            fired = False
        out_idx.append(table.index[i])
        out_val.append(fired)
    return pd.Series(out_val, index=pd.DatetimeIndex(out_idx), dtype=bool)


# ---------------------------------------------------------------------------
# LOCO — fit everything on the readings outside the held-out crisis
# ---------------------------------------------------------------------------

def _train_table(channels: dict, train: np.ndarray, keys: tuple,
                 q_watch: float, q_alert: float) -> pd.DataFrame:
    """Feature table for ALL readings with the transform fit on `train` only:
    percentile = ECDF of the training values, cuts = training quantiles."""
    idx = channels["comp"].index
    cols = {}
    for k in keys:
        v = channels[k].reindex(idx).to_numpy(dtype=float)
        tr = v[train]
        tr = tr[np.isfinite(tr)]
        srt = np.sort(tr)
        pct = np.searchsorted(srt, v, side="left") / max(len(srt), 1)
        cols[f"{k}_pct"] = np.where(np.isfinite(v), pct, np.nan)
        cols[f"{k}_w"] = np.isfinite(v) & (v >= np.quantile(tr, q_watch))
        cols[f"{k}_a"] = np.isfinite(v) & (v >= np.quantile(tr, q_alert))
    return pd.DataFrame(cols, index=idx)


def loco_recall(
    channels: dict,
    gspc: pd.Series,
    variant: str,
    horizon: int,
    threshold: float = DD_THRESHOLD,
    q_watch: float = Q_WATCH,
    q_alert: float = Q_ALERT,
    min_train: int = LOCO_MIN_TRAIN,
    keys: tuple = _CH_KEYS,
    C: float = LOGIT_C,
) -> dict:
    """Leave-one-crisis-out recall for one aggregator. Folds = the drawdown
    episodes on the common window (`input_testing._loco_recall`'s definition, so
    the OR row here reproduces it). Per fold: cuts / percentile transform / the
    logistic are fit on every reading outside the crisis span; the variant's flag
    is computed on the whole series with those and asked whether it fires
    anywhere inside the span. The logistic's cut is the OR flag's firing rate on
    the training readings (the equal-budget rule).
    """
    idx = channels["comp"].index
    close = pd.Series(gspc).astype(float)
    labels = drawdown_label(close, threshold, horizon)
    y = labels.reindex(idx)
    eps = collapse_episodes(y.dropna().astype(bool))
    yv = y.to_numpy(dtype=float)

    folds, caught = [], 0
    for (s, e) in eps:
        test = (idx >= s) & (idx <= e)
        train = ~test
        n_tr = sum(np.isfinite(channels[k].reindex(idx).to_numpy(dtype=float)[train]).sum()
                   >= min_train for k in keys)
        if n_tr < len(keys):
            continue
        tab = _train_table(channels, train, keys, q_watch, q_alert)
        if variant == "logit":
            feats = tab[[f"{k}_pct" for k in keys]].to_numpy(dtype=float)
            finite = np.isfinite(feats).all(axis=1)
            tr = train & np.isfinite(yv) & finite
            ytr = yv[tr].astype(bool)
            if tr.sum() < min_train or ytr.all() or not ytr.any():
                continue
            m = _fit_logit(feats[tr], ytr, C)
            thr = _budget_threshold(m.predict_proba(feats[tr])[:, 1],
                                    float(_or_flag(tab, keys).to_numpy()[tr].mean()))
            p = np.where(finite, m.predict_proba(np.nan_to_num(feats))[:, 1], -np.inf)
            flag = pd.Series(p >= thr, index=idx)
        else:
            flag = aggregate(tab, variant, keys).reindex(idx, fill_value=False).astype(bool)
        fired = bool(flag[test].any())
        caught += fired
        folds.append((s.date(), e.date(), fired))
    n = len(folds)
    return {"n_crises": n, "caught": caught,
            "recall": (round(caught / n, 3) if n else None), "folds": folds}


# ---------------------------------------------------------------------------
# Scoring one variant against OR on the variant's own window
# ---------------------------------------------------------------------------

def _score(flag: pd.Series, gspc: pd.Series, horizon: int,
           threshold: float = DD_THRESHOLD) -> dict:
    close = pd.Series(gspc).astype(float)
    y = drawdown_label(close, threshold, horizon).reindex(flag.index).dropna()
    f = flag.reindex(y.index, fill_value=False).astype(bool)
    m = episode_scoring(f, y)
    lead = lead_time_stats(close, pd.DataFrame({"flag": f}), threshold, horizon,
                           flag_col="flag", flag_val=True)
    m["median_lead"] = lead["median_lead"]
    m["n_true_pos_days"] = lead["n_true_pos"]
    return m


def score_variant(
    variant: str,
    table: pd.DataFrame,
    channels: dict,
    gspc: pd.Series,
    horizons: tuple = HORIZONS,
    threshold: float = DD_THRESHOLD,
) -> dict:
    """PIT + LOCO for one variant, each beside the OR reference on the SAME
    readings / folds. Returns the row `verdict()` reads."""
    row = {"variant": variant, "pit": {}, "loco": {}}
    for h in horizons:
        if variant == "logit":
            flag = logit_pit_flag(table, gspc, h, threshold)
        else:
            flag = aggregate(table, variant)
        ref = _or_flag(table).reindex(flag.index, fill_value=False).astype(bool)
        v = _score(flag, gspc, h, threshold)
        r = _score(ref, gspc, h, threshold)
        row["pit"][h] = {
            "window": (len(flag), (flag.index[0].date() if len(flag) else None),
                       (flag.index[-1].date() if len(flag) else None)),
            "n_episodes": v["n_episodes"],
            "caught": v["n_caught"], "ref_caught": r["n_caught"],
            "n_alarms": v["n_alarms"], "ref_n_alarms": r["n_alarms"],
            "precision": v["alarm_precision"], "ref_precision": r["alarm_precision"],
            "recall": v["episode_recall"], "ref_recall": r["episode_recall"],
            "median_lead": v["median_lead"], "ref_median_lead": r["median_lead"],
        }
        lv = loco_recall(channels, gspc, variant, h, threshold)
        lr = loco_recall(channels, gspc, "or", h, threshold)
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
    """Apply the pre-registered IMP-6 bar to one variant's row.

      ``underpowered``  fewer than MIN_ALARMS distinct alarms on the PIT window
                        at any horizon
      ``too_late``      median lead to trough (PIT true positives, 5d) below
                        MIN_LEAD_5D — or undefined because nothing was caught
      ``recall_lost``   more than MAX_RECALL_LOST crises lost vs OR under LOCO
                        at either horizon
      ``pass``          route 1: PIT precision >= OR + PASS_PREC_GAIN at BOTH
                        horizons with PIT recall within PASS_RECALL_TOL crises of
                        OR at both; or route 2: LOCO recall >= OR + PASS_LOCO_GAIN
                        crises at BOTH horizons with PIT precision >= OR −
                        PASS_PREC_TOL at both
      ``no_edge``       cleared every disqualifier, cleared neither route

    Disqualifiers are evaluated in that order and each returns immediately; the
    pass clause is unreachable until all three have been checked.
    """
    pit, loco = row["pit"], row["loco"]

    # --- Disqualifier 1: power --------------------------------------------
    for h in horizons:
        n = pit[h]["n_alarms"]
        if n < MIN_ALARMS:
            return {"verdict": "underpowered",
                    "reason": f"{n} alarms on the PIT window at {h}d < {MIN_ALARMS}"}

    # --- Disqualifier 2: lead time ----------------------------------------
    h0 = horizons[0]
    lead = pit[h0]["median_lead"]
    if lead is None or lead < MIN_LEAD_5D:
        return {"verdict": "too_late",
                "reason": f"median lead to trough at {h0}d is {lead} < {MIN_LEAD_5D} days"}

    # --- Disqualifier 3: recall under LOCO --------------------------------
    for h in horizons:
        lost = loco[h]["ref_caught"] - loco[h]["caught"]
        if lost > MAX_RECALL_LOST:
            return {"verdict": "recall_lost",
                    "reason": f"LOCO {h}d catches {loco[h]['caught']} vs OR "
                              f"{loco[h]['ref_caught']} — {lost} crises lost > "
                              f"{MAX_RECALL_LOST}"}

    # --- Only now, the pass clause ----------------------------------------
    def _p(x):
        return -np.inf if x is None else float(x)

    route1 = all(
        _p(pit[h]["precision"]) >= _p(pit[h]["ref_precision"]) + PASS_PREC_GAIN
        and pit[h]["caught"] >= pit[h]["ref_caught"] - PASS_RECALL_TOL
        for h in horizons)
    route2 = all(
        loco[h]["caught"] >= loco[h]["ref_caught"] + PASS_LOCO_GAIN
        and _p(pit[h]["precision"]) >= _p(pit[h]["ref_precision"]) - PASS_PREC_TOL
        for h in horizons)
    if route1 or route2:
        return {"verdict": "pass",
                "reason": ("PIT precision +%.2f or more at both horizons at held recall"
                           % PASS_PREC_GAIN) if route1 else
                          ("LOCO recall +%d crises or more at both horizons at held "
                           "precision" % PASS_LOCO_GAIN),
                "route": 1 if route1 else 2}
    return {"verdict": "no_edge",
            "reason": "cleared every disqualifier; cleared neither pass route"}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run_aggregator_gate(
    channels: Optional[dict] = None,
    horizons: tuple = HORIZONS,
    threshold: float = DD_THRESHOLD,
    min_warmup: int = _MIN_WARMUP,
    cache: Optional[str] = None,
) -> dict:
    """IMP-6, one run. Builds (or loads) the KB-021 live channels, checks the OR
    reference row reproduces `fragility_or._pit_backtest` (the regression guard),
    scores each variant under PIT + LOCO beside OR on its own window, and applies
    `verdict()`. Prints the table; returns {variant: row + verdict}."""
    if channels is None:
        if cache:
            with open(cache, "rb") as f:
                channels = pickle.load(f)
        else:
            channels = build_channels(refresh=True)
    common, gspc = channels["common"], channels["gspc"]
    print(f"IMP-6 aggregator gate — live window {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()}")

    table = pit_channel_table(channels, min_warmup=min_warmup)
    print(f"  PIT evaluable: {len(table)} readings "
          f"{table.index[0].date()}..{table.index[-1].date()} (warm-up {min_warmup})")

    # Regression guard: the OR row from this table == the live engine's self-check.
    from fragility_or import _pit_backtest
    ref = _pit_backtest(channels, Q_WATCH, min_warmup)
    orf = _or_flag(table)
    for h in horizons:
        mine = _score(orf, gspc, h, threshold)
        theirs = ref["horizons"][h]["or"]
        same = all(mine[k] == theirs[k] for k in ("n_episodes", "n_caught", "n_alarms"))
        print(f"  OR reference h={h:>2}d: {mine['n_caught']}/{mine['n_episodes']} "
              f"alarms={mine['n_alarms']} prec={mine['alarm_precision']} "
              f"lead={mine['median_lead']}  "
              f"[{'reproduces' if same else 'DIFFERS FROM'} fragility_or._pit_backtest]")

    out = {}
    for v in VARIANTS:
        row = score_variant(v, table, channels, gspc, horizons, threshold)
        row["verdict"] = verdict(row, horizons)
        out[v] = row
        print(f"\n=== {v} ===")
        for h in horizons:
            p, l = row["pit"][h], row["loco"][h]
            print(f"  PIT  h={h:>2}d  window={p['window'][0]:>4}  "
                  f"recall {p['caught']}/{p['n_episodes']} (OR {p['ref_caught']})  "
                  f"alarms {p['n_alarms']} (OR {p['ref_n_alarms']})  "
                  f"prec {p['precision']} (OR {p['ref_precision']})  "
                  f"lead {p['median_lead']} (OR {p['ref_median_lead']})")
            print(f"  LOCO h={h:>2}d  {l['n_crises']} folds  "
                  f"caught {l['caught']} (OR {l['ref_caught']})")
            for (s, e, hit) in l["differs"]:
                print(f"        differs {s}..{e}: {'variant only' if hit else 'OR only'}")
        print(f"  VERDICT: {row['verdict']['verdict']} — {row['verdict']['reason']}")
    return out


if __name__ == "__main__":
    import sys
    run_aggregator_gate(cache=(sys.argv[1] if len(sys.argv) > 1 else None))
