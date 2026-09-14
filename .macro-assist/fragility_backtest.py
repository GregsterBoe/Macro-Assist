"""
fragility_backtest.py — WP-16.A.2: does the fragility index lead drawdowns?

This is the DECISION GATE for the whole Phase 16 / emergence track. It is a
pure-numerical validation: the fragility index (fragility.py) is computed only
from price / vol series, so this harness makes ZERO LLM API calls. The only
external dependency is yfinance (free) for historical prices.

Method (look-ahead-safe by construction):
  1. Pull full daily history once for the tracked assets + VIX/VIX3M.
  2. Walk forward day by day. On each date d, compute the fragility index using
     ONLY data with index <= d (a trailing slice), exactly as the live pipeline
     would have seen it. Prices are not revised, so this is point-in-time clean.
  3. Label each date with whether a >threshold S&P 500 drawdown occurs within
     the next `horizon` trading days (forward-looking — used ONLY for scoring).
  4. Score the signal: base rate vs. conditional rate (lift), precision/recall
     of the Elevated / Rising flags, lead time, and a threshold-free AUC of the
     composite (and each component) against the forward-drawdown label.

The honest verdict:
  - AUC ~ 0.50 and lift ~ 1.0  => no skill. The direction is dead; do NOT spend
    money on the LLM-pipeline backtest. Stop here.
  - AUC > ~0.60 with lift > ~1.5 and a usable lead time => the signal is real;
    proceed to wire it in (WP-16.A.3 calibration, then WP-16.A.4 pipeline).

The component-by-component AUC is the key diagnostic: the Phase 16 thesis is
that variance-trend / correlation carry the signal and lag-1 autocorrelation
(critical slowing down) does not. This harness tests that directly.

Public functions
----------------
(feeds, the walk and the drawdown target: see fragility_panel.py — re-exported here)
auc(scores, labels)                          -> float
evaluate(frag_df, labels, ...)               -> dict
run_backtest(...)                            -> dict   (fetches yfinance, prints)
pit_elevated_flag(composite)                -> DataFrame  (IMP-5.3 PIT Elevated cut)
run_pit_cut_check(...)                      -> dict   (IMP-5.3 gate; `python fragility_backtest.py pit-cut`)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from fragility import pit_label_cuts, _VOL_KEYS, _LABEL_ELEVATED, _PIT_WARMUP
# The feeds, the walk and the drawdown target live in the product tier
# (`fragility_panel.py`, ADR-0021 / todo #20) so the live OR flag does not
# import this harness. Re-exported here so every research caller and test that
# spells `fragility_backtest.fetch_sector_etfs` etc. is unchanged.
from fragility_panel import (  # noqa: F401 — re-exports
    _LOOKBACK, _MIN_HISTORY,
    forward_worst_return, drawdown_label, walk_forward_fragility,
    collapse_episodes, _intervals_overlap, episode_scoring,
    _TICKERS, _CBOE_SYMBOLS, _CBOE_URL, _CBOE_TIMEOUT, fetch_cboe_index,
    freshen_vol_indices, fetch_histories, _SECTOR_ETFS, _ETF_CACHE, fetch_sector_etfs,
)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def auc(scores: pd.Series, labels: pd.Series) -> Optional[float]:
    """Threshold-free skill: Mann-Whitney AUC of `scores` predicting boolean
    `labels`. 0.5 = no skill, 1.0 = perfect, <0.5 = inverted. Ties handled via
    average ranks. None if a class is empty or all scores are NaN.
    """
    s = pd.Series(scores).astype(float)
    y = pd.Series(labels).astype(bool).reindex(s.index)
    mask = s.notna() & y.notna()
    s, y = s[mask], y[mask].astype(bool)
    n_pos = int(y.sum())
    n_neg = int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = s.rank().to_numpy()
    rank_sum_pos = float(ranks[y.to_numpy()].sum())
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _flag_stats(flag: pd.Series, labels: pd.Series, base_rate: float) -> dict:
    """Precision / lift for a boolean signal flag against the drawdown labels."""
    flag = pd.Series(flag).astype(bool)
    y = pd.Series(labels).astype(bool).reindex(flag.index)
    mask = flag.notna() & y.notna()
    flag, y = flag[mask], y[mask].astype(bool)
    n_flagged = int(flag.sum())
    if n_flagged == 0:
        return {"n_flagged": 0, "precision": None, "lift": None, "recall": None}
    hits = int((flag & y).sum())
    precision = hits / n_flagged
    total_events = int(y.sum())
    return {
        "n_flagged": n_flagged,
        "precision": round(precision, 3),
        "lift":      round(precision / base_rate, 2) if base_rate > 0 else None,
        "recall":    round(hits / total_events, 3) if total_events else None,
    }


def lead_time_stats(
    close: pd.Series,
    frag_df: pd.DataFrame,
    threshold: float = 0.05,
    horizon: int = 10,
    flag_col: str = "label",
    flag_val: str = "Elevated",
) -> dict:
    """How many trading days of warning does the flag actually give?

    For each flagged day that is a true positive (a >=threshold drawdown does
    occur within `horizon`), measure the offset to the drawdown TROUGH (the
    worst forward day). This is the question behind "reacts vs. predicts": a
    median lead of 1 day is coincident; 4-6 days is a genuine head start.
    """
    close = pd.Series(close).astype(float)
    flagged = frag_df.index[frag_df[flag_col] == flag_val]
    leads: list[int] = []
    for d in flagged:
        if d not in close.index:
            continue
        i = close.index.get_loc(d)
        end = min(i + horizon + 1, len(close))
        if end <= i + 1:
            continue
        fut = close.iloc[i + 1:end].to_numpy() / float(close.iloc[i]) - 1.0
        if fut.min() <= -abs(threshold):
            leads.append(int(np.argmin(fut)) + 1)  # trading days to the trough
    if not leads:
        return {"n_true_pos": 0, "median_lead": None, "mean_lead": None,
                "pct_lead_ge_3": None}
    arr = np.array(leads)
    return {
        "n_true_pos":   len(arr),
        "median_lead":  float(np.median(arr)),
        "mean_lead":    round(float(arr.mean()), 2),
        "pct_lead_ge_3": round(float((arr >= 3).mean()), 3),
    }


def subsample_auc(scores: pd.Series, labels: pd.Series, step: int) -> Optional[float]:
    """AUC on a non-overlapping subsample (every `step`-th aligned observation).

    Removes the forward-window overlap that correlates adjacent days, so the
    AUC point estimate rests on independent observations. `step` should be the
    drawdown horizon (the span each label looks across).
    """
    s = pd.Series(scores).astype(float)
    y = pd.Series(labels).astype(bool).reindex(s.index)
    mask = s.notna() & y.notna()
    s, y = s[mask], y[mask].astype(bool)
    if len(s) == 0:
        return None
    sub = slice(None, None, max(1, step))
    return auc(s.iloc[sub], y.iloc[sub])


def evaluate(
    frag_df: pd.DataFrame,
    labels: pd.Series,
    elevated_threshold: float = 65.0,
    top_quantile: float = 0.90,
    horizon: Optional[int] = None,
) -> dict:
    """Score the walk-forward fragility series against drawdown labels.

    Returns a dict with the base rate, per-signal flag stats (Elevated label,
    Rising trend, top-decile composite, Elevated AND Rising), and the AUC of
    the composite and each component.

    If `horizon` is given, also returns de-overlapped metrics (WP-16.A.3): a
    non-overlapping (every `horizon`-th day) composite/component AUC, and
    episode-level recall/precision for the Elevated and top-decile flags.
    """
    df = frag_df.copy()
    y = pd.Series(labels).astype(bool).reindex(df.index)
    mask = y.notna()
    df, y = df[mask], y[mask].astype(bool)
    if df.empty:
        return {}

    n = len(df)
    base_rate = float(y.mean())

    elevated = df["label"] == "Elevated"
    rising = df["trend"] == "Rising"
    top_cut = float(df["composite"].quantile(top_quantile))
    top_decile = df["composite"] >= top_cut

    flags = {
        "elevated_label":     _flag_stats(elevated, y, base_rate),
        "rising_trend":       _flag_stats(rising, y, base_rate),
        f"top_decile(>={top_cut:.0f})": _flag_stats(top_decile, y, base_rate),
        "elevated_and_rising": _flag_stats(elevated & rising, y, base_rate),
    }

    aucs = {
        "composite":      auc(df["composite"], y),
        "variance_trend": auc(df["variance_trend"], y),
        "correlation":    auc(df["correlation"], y),
        "absorption":     auc(df["absorption"], y),
        "vix_term":       auc(df["vix_term"], y),
        "autocorr":       auc(df["autocorr"], y),
    }

    report = {
        "n_days":      n,
        "n_events":    int(y.sum()),
        "base_rate":   round(base_rate, 4),
        "elevated_threshold": elevated_threshold,
        "flags":       flags,
        "auc":         {k: (round(v, 3) if v is not None else None) for k, v in aucs.items()},
    }

    if horizon is not None:
        sub_aucs = {k: subsample_auc(df[k], y, horizon)
                    for k in ("composite", "variance_trend", "correlation",
                              "absorption", "vix_term", "autocorr")}
        report["auc_nonoverlap"] = {
            k: (round(v, 3) if v is not None else None) for k, v in sub_aucs.items()
        }
        report["episodes"] = {
            "elevated_label": episode_scoring(elevated, y),
            f"top_decile(>={top_cut:.0f})": episode_scoring(top_decile, y),
        }

    return report



def run_backtest(
    histories: Optional[dict] = None,
    threshold: float = 0.05,
    horizons: tuple[int, ...] = (5, 10),
    start: str | None = "2008-01-01",
) -> dict:
    """Run the full walk-forward validation and print a verdict.

    If `histories` is None, fetches real data from yfinance (free, no LLM).
    Returns {horizon: evaluate(...) dict}.
    """
    if histories is None:
        print(f"Fetching daily history from yfinance (start={start}, no API cost)...")
        histories = fetch_histories(start=start)
    available = [k for k in histories if k not in _VOL_KEYS]
    print(f"Assets: {sorted(histories)}  ({len(available)} non-vol)\n")

    print("Walking fragility index forward (this is pure compute, no LLM)...")
    frag_df = walk_forward_fragility(histories)
    if frag_df.empty:
        print("No fragility readings could be computed — insufficient history.")
        return {}
    print(f"  {len(frag_df)} daily readings "
          f"from {frag_df.index[0].date()} to {frag_df.index[-1].date()}\n")

    results: dict = {}
    sp500 = histories["sp500"]
    for h in horizons:
        labels = drawdown_label(sp500, threshold=threshold, horizon=h)
        report = evaluate(frag_df, labels, horizon=h)
        report["lead_time"] = lead_time_stats(sp500, frag_df, threshold, h)
        results[h] = report

        print(f"=== Horizon {h} trading days, drawdown >= {threshold:.0%} ===")
        print(f"  days evaluated : {report['n_days']}")
        print(f"  drawdown events: {report['n_events']}  "
              f"(base rate {report['base_rate']:.1%})")
        print("  AUC (0.50 = no skill)        [overlap]  [non-overlap, honest n]:")
        nov = report.get("auc_nonoverlap", {})
        for name, val in report["auc"].items():
            tag = "  <-- key signal" if name in ("variance_trend", "correlation", "absorption") else ""
            ov = "n/a" if val is None else f"{val:.3f}"
            nv = nov.get(name)
            nvs = "n/a" if nv is None else f"{nv:.3f}"
            print(f"    {name:<15} {ov:>7}      {nvs:>7}{tag}")
        print("  Flags (precision / lift over base rate):")
        for fname, fs in report["flags"].items():
            if fs["n_flagged"] == 0:
                print(f"    {fname:<22} never fired")
            else:
                print(f"    {fname:<22} n={fs['n_flagged']:<5} "
                      f"precision={fs['precision']}  lift={fs['lift']}  recall={fs['recall']}")
        eps = report.get("episodes", {})
        if eps:
            print("  Episodes (de-overlapped — distinct crises vs. distinct alarms):")
            for fname, es in eps.items():
                if es["n_episodes"]:
                    print(f"    {fname:<22} caught {es['n_caught']}/{es['n_episodes']} crises "
                          f"(recall={es['episode_recall']}), {es['n_alarms']} alarms "
                          f"precision={es['alarm_precision']}")
        lt = report["lead_time"]
        if lt["n_true_pos"]:
            print(f"  Lead time (Elevated -> trough): median {lt['median_lead']:.0f}d, "
                  f"mean {lt['mean_lead']}d, {lt['pct_lead_ge_3']:.0%} give >=3d warning "
                  f"(n={lt['n_true_pos']})")
        print()

    _print_verdict(results)
    return results


# ---------------------------------------------------------------------------
# Weight ablation (WP-16.A.3) — let the data choose the composite weights.
# Note: the yfinance-only backtest never computes `acceleration` (no HY/NFCI),
# so its weight is renormalised away here; it is kept in the scheme for the
# live config. Effective backtest weights span {variance_trend, correlation,
# vix_term, autocorr}.
# ---------------------------------------------------------------------------

WEIGHT_SCHEMES: dict[str, dict] = {
    # A.2 baseline — what we scored last time.
    "baseline": {"variance_trend": 0.35, "correlation": 0.30, "vix_term": 0.20,
                 "acceleration": 0.10, "autocorr": 0.05},
    # Drop the no-skill autocorr; keep the rest proportional.
    "drop_autocorr": {"variance_trend": 0.37, "correlation": 0.31, "vix_term": 0.21,
                      "acceleration": 0.11, "autocorr": 0.0},
    # Drop autocorr AND the near-chance correlation.
    "drop_corr_ac": {"variance_trend": 0.55, "correlation": 0.0, "vix_term": 0.30,
                     "acceleration": 0.15, "autocorr": 0.0},
    # Variance-led, vix capped so the semi-circular component can't dominate,
    # correlation kept small (transparency/ablation), autocorr dropped.
    "var_led_capvix": {"variance_trend": 0.50, "correlation": 0.10, "vix_term": 0.25,
                       "acceleration": 0.15, "autocorr": 0.0},
    # Middle ground: variance still leads, vix gets honest weight (it is the
    # strongest component) without parity, a token correlation weight for
    # graceful degradation, autocorr dropped.
    "var_led_vix35": {"variance_trend": 0.45, "correlation": 0.05, "vix_term": 0.35,
                      "acceleration": 0.15, "autocorr": 0.0},
    # Two-signal core only (the two that earned their AUC), vix capped at parity.
    "core_two": {"variance_trend": 0.50, "correlation": 0.0, "vix_term": 0.50,
                 "acceleration": 0.0, "autocorr": 0.0},
    # --- WP-16.A.6: absorption-ratio candidates (PCA upgrade to correlation) ---
    # Give absorption the weight the dead `correlation` never earned, in place of
    # both it and the (backtest-inert) acceleration slot.
    "absorp_for_corr": {"variance_trend": 0.45, "vix_term": 0.35, "absorption": 0.20,
                        "correlation": 0.0, "acceleration": 0.0, "autocorr": 0.0},
    # Absorption at parity with vix, variance still leads.
    "absorp_balanced": {"variance_trend": 0.40, "vix_term": 0.30, "absorption": 0.30,
                        "correlation": 0.0, "acceleration": 0.0, "autocorr": 0.0},
    # Conservative add-on: the chosen var_led_vix35 plus a light absorption weight
    # carved out of acceleration; keeps the token correlation for degradation.
    "absorp_light":    {"variance_trend": 0.45, "vix_term": 0.35, "absorption": 0.10,
                        "correlation": 0.05, "acceleration": 0.0, "autocorr": 0.0},
    # Absorption replaces variance as the lead (stress test — is co-movement or
    # variance the stronger cross-asset signal?).
    "absorp_led":      {"variance_trend": 0.30, "vix_term": 0.30, "absorption": 0.40,
                        "correlation": 0.0, "acceleration": 0.0, "autocorr": 0.0},
}


def run_weight_ablation(
    histories: Optional[dict] = None,
    threshold: float = 0.05,
    horizon: int = 10,
    start: str | None = "2008-01-01",
    schemes: Optional[dict] = None,
) -> dict:
    """Re-walk the index under each weight scheme and compare on DE-OVERLAPPED
    metrics (non-overlapping AUC + episode recall/precision), the honest basis
    for choosing weights. Returns {scheme_name: report}.
    """
    if histories is None:
        print(f"Fetching daily history from yfinance (start={start}, no API cost)...")
        histories = fetch_histories(start=start)
    schemes = schemes or WEIGHT_SCHEMES
    sp500 = histories["sp500"]
    labels = drawdown_label(sp500, threshold=threshold, horizon=horizon)

    print(f"\nWeight ablation @ horizon {horizon}d, drawdown >= {threshold:.0%} "
          f"(de-overlapped metrics)\n")
    header = (f"  {'scheme':<16} {'AUC ov':>7} {'AUC nov':>8} "
              f"{'crises':>7} {'recall':>7} {'alarms':>7} {'prec':>6}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    out: dict = {}
    for name, w in schemes.items():
        frag_df = walk_forward_fragility(histories, weights=w)
        if frag_df.empty:
            continue
        report = evaluate(frag_df, labels, horizon=horizon)
        out[name] = report
        ov = report["auc"]["composite"]
        nov = report.get("auc_nonoverlap", {}).get("composite")
        td_key = next(k for k in report["episodes"] if k.startswith("top_decile"))
        es = report["episodes"][td_key]
        nov_s = "n/a" if nov is None else f"{nov:.3f}"
        rec_s = "n/a" if es["episode_recall"] is None else f"{es['episode_recall']:.3f}"
        prec_s = "n/a" if es["alarm_precision"] is None else f"{es['alarm_precision']:.3f}"
        print(f"  {name:<16} {ov:>7.3f} {nov_s:>8} "
              f"{es['n_episodes']:>7} {rec_s:>7} {es['n_alarms']:>7} {prec_s:>6}")
    print()
    return out


# ---------------------------------------------------------------------------
# IMP-5.3 — the composite label cut in expanding-PIT form.
# The Elevated label is a static 56.5 (the 90th pct of the whole 2008-2026
# composite, KB-002); the OR flag's channels each fire against the 90th pct of
# their OWN prior readings (fragility_or). Two flags in one note on two
# threshold methods. The gate, written before the run: re-walk 2008-2026 with
# the PIT cut (warm-up 252) and the episode recall/precision must reproduce the
# static cut within ±1 crisis per horizon on the same evaluable window — the
# KB-017 [2]-vs-[3] comparison, applied to the composite label. If it does not,
# the static cut stays and the discrepancy is a KB entry.
# ---------------------------------------------------------------------------

def pit_elevated_flag(
    composite: pd.Series,
    min_warmup: int = _PIT_WARMUP,
) -> pd.DataFrame:
    """Expanding-PIT Elevated flag on a walked composite series.

    Day i fires if its reading is at/above `fragility.pit_label_cuts` fitted on
    all finite readings strictly before i. NaN readings (degraded days) are
    neither labelled nor admitted to the history. Returns a DataFrame on the
    evaluable window only (days with >= `min_warmup` prior readings) with
    columns `cut` (that day's PIT Elevated threshold) and `elevated` (bool).
    """
    comp = pd.Series(composite).astype(float)
    arr = comp.to_numpy(dtype=float)
    rows: list[tuple] = []
    for i in range(len(arr)):
        if not np.isfinite(arr[i]):
            continue
        cuts = pit_label_cuts(arr[:i], warmup=min_warmup)
        if cuts is None:
            continue
        rows.append((comp.index[i], cuts["elevated"], bool(arr[i] >= cuts["elevated"])))
    if not rows:
        return pd.DataFrame(columns=["cut", "elevated"])
    out = pd.DataFrame(rows, columns=["date", "cut", "elevated"]).set_index("date")
    out["elevated"] = out["elevated"].astype(bool)
    return out


def run_pit_cut_check(
    histories: Optional[dict] = None,
    threshold: float = 0.05,
    horizons: tuple[int, ...] = (5, 10),
    start: str | None = "2008-01-01",
    min_warmup: int = _PIT_WARMUP,
    tolerance: int = 1,
) -> dict:
    """IMP-5.3 gate: does the expanding-PIT Elevated cut reproduce the static
    (KB-002) cut's episode recall/precision? Three rows per horizon:

      [1] static cut, full window      — the KB-002 reference (14/46, 17/58 as run 2026-06)
      [2] static cut, PIT window       — same cut, restricted to the days the PIT
                                          protocol can label (isolates window-shrink)
      [3] PIT cut,    PIT window       — the candidate

    The gate compares [2] and [3]: `pass` iff |caught[3] - caught[2]| <= `tolerance`
    at every horizon. Also reports label agreement day-by-day and where the PIT
    cut sits today against the static 56.5. Returns the full report dict.
    """
    if histories is None:
        print(f"Fetching daily history from yfinance (start={start}, no API cost)...")
        histories = fetch_histories(start=start)

    print("Walking fragility index forward (pure compute, no LLM)...")
    walk = walk_forward_fragility(histories)
    if walk.empty:
        print("No fragility readings could be computed — insufficient history.")
        return {}
    comp = walk["composite"].astype(float)
    if "degraded" in walk.columns:
        comp = comp.where(~walk["degraded"].astype(bool))
    n_degraded = int(walk["degraded"].astype(bool).sum()) if "degraded" in walk.columns else 0

    pit = pit_elevated_flag(comp, min_warmup=min_warmup)
    if pit.empty:
        print("PIT window is empty — not enough readings to warm the cut.")
        return {}
    static_full = (walk["label"] == "Elevated")
    static_win = static_full.reindex(pit.index).fillna(False).astype(bool)
    pit_win = pit["elevated"]

    agree = float((static_win == pit_win).mean())
    print(f"  {len(walk)} readings {walk.index[0].date()}..{walk.index[-1].date()} "
          f"({n_degraded} degraded, masked)")
    print(f"  PIT evaluable window: {len(pit)} readings from {pit.index[0].date()} "
          f"(first {min_warmup} warm the cut)")
    print(f"  PIT Elevated cut today: {pit['cut'].iloc[-1]:.1f}  "
          f"(range {pit['cut'].min():.1f}..{pit['cut'].max():.1f}; static {_LABEL_ELEVATED})")
    print(f"  Day-level label agreement (static vs PIT, Elevated or not): {agree:.1%}  "
          f"static fires {int(static_win.sum())} days, PIT fires {int(pit_win.sum())} days\n")

    sp500 = pd.Series(histories["sp500"]).astype(float)
    report: dict = {
        "n_readings": int(len(walk)), "n_degraded": n_degraded,
        "n_pit_window": int(len(pit)), "pit_window_start": str(pit.index[0].date()),
        "pit_cut_today": float(pit["cut"].iloc[-1]),
        "pit_cut_min": float(pit["cut"].min()), "pit_cut_max": float(pit["cut"].max()),
        "static_cut": _LABEL_ELEVATED, "label_agreement": round(agree, 4),
        "horizons": {}, "tolerance": tolerance,
    }
    all_pass = True
    for h in horizons:
        labels = drawdown_label(sp500, threshold=threshold, horizon=h)
        rows = {
            "static_full":   episode_scoring(static_full, labels),
            "static_window": episode_scoring(static_win, labels),
            "pit_window":    episode_scoring(pit_win, labels),
        }
        pit_df = walk.reindex(pit.index).copy()
        pit_df["label"] = np.where(pit_win.to_numpy(), "Elevated", "Normal")
        leads = {
            "static_window": lead_time_stats(sp500, walk.reindex(pit.index), threshold, h),
            "pit_window":    lead_time_stats(sp500, pit_df, threshold, h),
        }
        d_caught = rows["pit_window"]["n_caught"] - rows["static_window"]["n_caught"]
        ok = abs(d_caught) <= tolerance
        all_pass = all_pass and ok
        report["horizons"][h] = {"episodes": rows, "lead_time": leads,
                                 "delta_caught": int(d_caught), "pass": bool(ok)}

        print(f"=== Horizon {h} trading days, drawdown >= {threshold:.0%} ===")
        for tag, es in rows.items():
            lt = leads.get(tag)
            lead_s = ""
            if lt and lt["n_true_pos"]:
                lead_s = f"  median lead {lt['median_lead']:.0f}d ({lt['pct_lead_ge_3']:.0%} >=3d)"
            print(f"  {tag:<14} caught {es['n_caught']:>2}/{es['n_episodes']:<2} "
                  f"recall={es['episode_recall']}  alarms={es['n_alarms']:<3} "
                  f"precision={es['alarm_precision']}{lead_s}")
        print(f"  -> PIT vs static on the same window: {d_caught:+d} crises "
              f"({'within' if ok else 'OUTSIDE'} ±{tolerance})\n")

    report["pass"] = bool(all_pass)
    print("------------------------------------------------------------")
    print("IMP-5.3 GATE: " + ("PASS — the PIT cut reproduces the static cut; the label "
                              "can move to the OR flag's method."
                              if all_pass else
                              "FAIL — the static cut stays; log the discrepancy as a KB entry."))
    print("------------------------------------------------------------")
    return report


def _print_verdict(results: dict) -> None:
    """Plain-English go/no-go based on composite AUC and best flag lift."""
    aucs = [r["auc"]["composite"] for r in results.values() if r.get("auc", {}).get("composite") is not None]
    lifts = []
    for r in results.values():
        for fs in r.get("flags", {}).values():
            if fs.get("lift") is not None:
                lifts.append(fs["lift"])
    best_auc = max(aucs) if aucs else None
    best_lift = max(lifts) if lifts else None

    print("------------------------------------------------------------")
    print("VERDICT")
    if best_auc is None:
        print("  Inconclusive — no scorable days. Widen the date range.")
    elif best_auc >= 0.60 and (best_lift or 0) >= 1.5:
        print(f"  SIGNAL PRESENT (best composite AUC {best_auc:.3f}, best lift {best_lift}).")
        print("  Worth proceeding: WP-16.A.3 (calibrate thresholds), then wire in.")
    elif best_auc >= 0.55:
        print(f"  WEAK SIGNAL (best composite AUC {best_auc:.3f}, best lift {best_lift}).")
        print("  Marginal. Try ablating to the strongest component before spending on")
        print("  the LLM-pipeline backtest.")
    else:
        print(f"  NO SKILL (best composite AUC {best_auc:.3f}, best lift {best_lift}).")
        print("  Do NOT spend on the LLM-pipeline backtest on this basis. Rethink the")
        print("  components or abandon the phase-transition framing.")
    print("------------------------------------------------------------")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "pit-cut":
        run_pit_cut_check()
    else:
        run_backtest()
