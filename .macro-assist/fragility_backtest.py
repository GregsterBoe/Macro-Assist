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
forward_worst_return(close, horizon)        -> Series
drawdown_label(close, threshold, horizon)   -> Series[bool]
walk_forward_fragility(histories, ...)       -> DataFrame
auc(scores, labels)                          -> float
evaluate(frag_df, labels, ...)               -> dict
run_backtest(...)                            -> dict   (fetches yfinance, prints)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from fragility import fragility_index, _VOL_KEYS

# Trailing window passed to fragility_index each step. The index's longest
# look-back is correlation's 2*window (=120) plus a small buffer, so 180 is
# ample and keeps every step O(1) instead of O(history).
_LOOKBACK = 180

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
        composite, label, trend, and one column per component score
        (variance_trend, correlation, vix_term, autocorr).
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
            "variance_trend": comps.get("variance_trend", {}).get("score", np.nan),
            "correlation":    comps.get("correlation", {}).get("score", np.nan),
            "vix_term":       comps.get("vix_term", {}).get("score", np.nan),
            "autocorr":       comps.get("autocorr", {}).get("score", np.nan),
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


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


def evaluate(
    frag_df: pd.DataFrame,
    labels: pd.Series,
    elevated_threshold: float = 65.0,
    top_quantile: float = 0.90,
) -> dict:
    """Score the walk-forward fragility series against drawdown labels.

    Returns a dict with the base rate, per-signal flag stats (Elevated label,
    Rising trend, top-decile composite, Elevated AND Rising), and the AUC of
    the composite and each component.
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
        "vix_term":       auc(df["vix_term"], y),
        "autocorr":       auc(df["autocorr"], y),
    }

    return {
        "n_days":      n,
        "n_events":    int(y.sum()),
        "base_rate":   round(base_rate, 4),
        "elevated_threshold": elevated_threshold,
        "flags":       flags,
        "auc":         {k: (round(v, 3) if v is not None else None) for k, v in aucs.items()},
    }


# ---------------------------------------------------------------------------
# CLI — fetch real history (free) and print the verdict
# ---------------------------------------------------------------------------

_TICKERS = {
    "sp500": "^GSPC", "nasdaq": "^IXIC", "gold": "GC=F",
    "wti_oil": "CL=F", "dxy": "DX-Y.NYB",
    "vix": "^VIX", "vix3m": "^VIX3M",
}


def fetch_histories(period: str = "max", start: str | None = "2008-01-01") -> dict:
    """Pull daily Close series for the tracked tickers from yfinance (free).
    VIX3M only exists from ~2008, so the default start caps there.
    """
    import yfinance as yf

    histories: dict = {}
    for name, tk in _TICKERS.items():
        try:
            hist = yf.Ticker(tk).history(start=start) if start else yf.Ticker(tk).history(period=period)
            if not hist.empty:
                close = hist["Close"]
                close.index = close.index.tz_localize(None)
                histories[name] = close
        except Exception as e:   # noqa: BLE001 — CLI convenience only
            print(f"  warn: {tk} failed: {e}")
    return histories


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
        report = evaluate(frag_df, labels)
        report["lead_time"] = lead_time_stats(sp500, frag_df, threshold, h)
        results[h] = report

        print(f"=== Horizon {h} trading days, drawdown >= {threshold:.0%} ===")
        print(f"  days evaluated : {report['n_days']}")
        print(f"  drawdown events: {report['n_events']}  "
              f"(base rate {report['base_rate']:.1%})")
        print("  AUC (0.50 = no skill):")
        for name, val in report["auc"].items():
            tag = "" if val is None else ("  <-- key signal" if name in ("variance_trend", "correlation") else "")
            print(f"    {name:<15} {('n/a' if val is None else f'{val:.3f}')}{tag}")
        print("  Flags (precision / lift over base rate):")
        for fname, fs in report["flags"].items():
            if fs["n_flagged"] == 0:
                print(f"    {fname:<22} never fired")
            else:
                print(f"    {fname:<22} n={fs['n_flagged']:<5} "
                      f"precision={fs['precision']}  lift={fs['lift']}  recall={fs['recall']}")
        lt = report["lead_time"]
        if lt["n_true_pos"]:
            print(f"  Lead time (Elevated -> trough): median {lt['median_lead']:.0f}d, "
                  f"mean {lt['mean_lead']}d, {lt['pct_lead_ge_3']:.0%} give >=3d warning "
                  f"(n={lt['n_true_pos']})")
        print()

    _print_verdict(results)
    return results


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
    run_backtest()
