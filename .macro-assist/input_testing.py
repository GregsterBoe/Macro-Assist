"""
input_testing.py — IMP-1: the "step in between" for fragility inputs.

A generic, zero-LLM-cost harness for vetting a NEW candidate fragility input
BEFORE it ever touches the live pipeline. You give it a way to compute a signal
from a trailing data slice; it walks that signal forward look-ahead-safe and
scores it against forward equity drawdowns with the same de-overlapped metrics
the fragility backtest uses (KB-002 discipline): non-overlapping AUC + episode
recall/precision + lead time. Only inputs that clear the gate graduate to a
shadow wiring in fragility.py.

See Project_Improvement.md (IMP-1). Findings from anything run here are logged as
Knowledge_Base.md (KB-###) entries — negatives included.

IMP-1's first data source is a BROAD HOMOGENEOUS CROSS-SECTION (Fama-French daily
industry portfolios, free, decades deep), which KB-012 identified as the missing
ingredient for cross-sectional co-movement measures (absorption ratio, turbulence)
that were untestable on the ~5 heterogeneous live assets.

Public surface
--------------
fetch_ff_industries(n, weighting)        -> DataFrame daily returns (decimal)
fetch_ff_market()                        -> Series synthetic market Close (levels)
returns_to_histories(returns_df)         -> dict name->Close (for fragility fns)
walk_forward_signal(signal_fn, ...)      -> Series (one value per date, PIT-safe)
evaluate_signal(signal, market_close, .) -> dict (+ pretty print)  the GATE
"""
from __future__ import annotations

import io
import os
import re
import zipfile
import urllib.request
from typing import Callable, Optional

import numpy as np
import pandas as pd

# Reuse the validated scorers — do not reimplement them.
from fragility_backtest import (
    drawdown_label, auc, subsample_auc, episode_scoring, collapse_episodes,
)

_KF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_MISSING = {-99.99, -999.0, -99.99}     # Ken French missing-data codes

_DEFAULT_CACHE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "macro-assist", "ff",
)


# ---------------------------------------------------------------------------
# Fama-French fetch (free, cached)
# ---------------------------------------------------------------------------

def _download_zip_text(url: str, cache_dir: str) -> str:
    """Download a Ken French _CSV.zip, return the inner CSV text. Cached to disk
    so repeated backtests are offline and instant.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, re.sub(r"[^\w.-]", "_", url.split("/")[-1]) + ".txt")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="latin-1") as fh:
            return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    blob = urllib.request.urlopen(req, timeout=60).read()
    z = zipfile.ZipFile(io.BytesIO(blob))
    text = z.read(z.namelist()[0]).decode("latin-1")
    with open(cache_path, "w", encoding="latin-1") as fh:
        fh.write(text)
    return text


def _parse_ff_block(text: str, section_regex: str) -> pd.DataFrame:
    """Parse one section of a Ken French CSV into a daily-returns DataFrame
    (decimal). A section starts at a header line matching `section_regex`, then a
    ",Col,Col,..." column line, then YYYYMMDD data rows until a blank/non-date
    line. Missing codes -> NaN.
    """
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if re.search(section_regex, ln))
    # The column header is a line beginning with ",". In the industry files it is
    # a separate line after a titled section header; in the factors file the
    # matched section line already IS the ",Mkt-RF,..." column header.
    hdr_i = (start if lines[start].startswith(",")
             else next(i for i in range(start + 1, len(lines)) if lines[i].startswith(",")))
    cols = [c.strip() for c in lines[hdr_i].split(",")[1:]]

    dates, rows = [], []
    for ln in lines[hdr_i + 1:]:
        m = re.match(r"^\s*(\d{8})\s*,(.*)$", ln)
        if not m:
            break                                   # end of this daily section
        dates.append(pd.to_datetime(m.group(1), format="%Y%m%d"))
        rows.append([float(x) for x in m.group(2).split(",")])
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=cols)
    df = df.mask(df.isin(_MISSING))
    return df / 100.0                                # percent -> decimal


def fetch_ff_industries(
    n: int = 30,
    weighting: str = "vw",
    cache_dir: str = _DEFAULT_CACHE,
) -> pd.DataFrame:
    """Fama-French `n`-industry daily portfolio returns (decimal), homogeneous
    cross-section for co-movement measures. n in {5,10,12,17,30,38,48,49};
    weighting 'vw' (value-weighted) or 'ew'. Free, cached.
    """
    text = _download_zip_text(f"{_KF_BASE}{n}_Industry_Portfolios_daily_CSV.zip", cache_dir)
    section = ("Average Value Weighted Returns" if weighting == "vw"
               else "Average Equal Weighted Returns")
    return _parse_ff_block(text, re.escape(section) + r".*Daily")


def fetch_ff_market(cache_dir: str = _DEFAULT_CACHE) -> pd.Series:
    """Synthetic market Close level from the FF daily market factor (Mkt-RF + RF),
    for building drawdown labels over the SAME deep history as the industries.
    """
    text = _download_zip_text(f"{_KF_BASE}F-F_Research_Data_Factors_daily_CSV.zip", cache_dir)
    fac = _parse_ff_block(text, r"^\s*,Mkt-RF")      # single block; header line
    mkt_ret = fac["Mkt-RF"] + fac["RF"]              # total market return, decimal
    return 100.0 * (1.0 + mkt_ret).cumprod()         # arbitrary level; only shape matters


def returns_to_histories(returns_df: pd.DataFrame) -> dict:
    """Turn a returns panel into a {name: Close Series} dict so the existing
    fragility.py components (which expect prices) run on it unchanged.
    """
    prices = 100.0 * (1.0 + returns_df).cumprod()
    return {col: prices[col].dropna() for col in prices.columns}


# ---------------------------------------------------------------------------
# Generic walk-forward — the reusable "step in between"
# ---------------------------------------------------------------------------

def walk_forward_signal(
    signal_fn: Callable[[dict], Optional[float]],
    histories: dict,
    anchor_index: pd.DatetimeIndex,
    lookback: int = 450,
    min_history: int = 260,
    stride: int = 1,
) -> pd.Series:
    """Walk `signal_fn` forward, look-ahead-safe.

    On each anchor date d, hand `signal_fn` a dict of every asset's trailing
    `lookback` observations known as of d (>= min_history required), and record
    its scalar output. `signal_fn` should return a float score (higher = more
    fragile) or None. `stride` subsamples anchor dates to speed up long histories.
    """
    names = list(histories.keys())
    series = {name: pd.Series(histories[name]) for name in names}
    out: dict = {}
    for d in anchor_index[::stride]:
        sliced = {}
        for name in names:
            past = series[name][series[name].index <= d].tail(lookback)
            if len(past) >= 2:
                sliced[name] = past
        n_ready = sum(len(v) >= min_history for v in sliced.values())
        if n_ready < 3:
            continue
        val = signal_fn(sliced)
        if val is not None and np.isfinite(val):
            out[d] = float(val)
    return pd.Series(out, name="signal")


# ---------------------------------------------------------------------------
# The GATE — score a candidate signal against forward drawdowns
# ---------------------------------------------------------------------------

def _lead_stats(signal_flag: pd.Series, market: pd.Series,
                threshold: float, horizon: int) -> dict:
    """Median trading-day lead from a flagged day to the drawdown trough."""
    market = pd.Series(market).astype(float)
    leads = []
    for d in signal_flag.index[signal_flag.astype(bool)]:
        if d not in market.index:
            continue
        i = market.index.get_loc(d)
        end = min(i + horizon + 1, len(market))
        if end <= i + 1:
            continue
        fut = market.iloc[i + 1:end].to_numpy() / float(market.iloc[i]) - 1.0
        if fut.min() <= -abs(threshold):
            leads.append(int(np.argmin(fut)) + 1)
    if not leads:
        return {"n_true_pos": 0, "median_lead": None}
    return {"n_true_pos": len(leads), "median_lead": float(np.median(leads))}


def evaluate_signal(
    signal: pd.Series,
    market_close: pd.Series,
    threshold: float = 0.05,
    horizons: tuple[int, ...] = (5, 10),
    top_quantile: float = 0.90,
    name: str = "candidate",
    verbose: bool = True,
) -> dict:
    """The input-testing GATE. Score a candidate `signal` (higher = more fragile)
    against >=`threshold` `market_close` drawdowns over each horizon, using the
    de-overlapped metrics. Returns {horizon: {...}}; prints a verdict if verbose.

    GO (reuse KB-002 bar): non-overlap AUC > ~0.60 AND top-decile episode
    recall/precision that beat the fragility baseline. Otherwise NO-GO -> log the
    negative (KB), stop.
    """
    signal = pd.Series(signal).astype(float).dropna()
    results: dict = {}
    if verbose:
        print(f"\n=== GATE: {name} vs >= {threshold:.0%} drawdowns "
              f"(n={len(signal)} readings) ===")
    for h in horizons:
        labels = drawdown_label(pd.Series(market_close).astype(float), threshold, h)
        y = labels.reindex(signal.index).dropna()
        s = signal.reindex(y.index)
        base = float(y.mean()) if len(y) else float("nan")

        top_cut = float(s.quantile(top_quantile))
        flag = s >= top_cut
        eps = episode_scoring(flag, y)
        lead = _lead_stats(flag, market_close, threshold, h)
        rep = {
            "n": int(len(y)),
            "base_rate": round(base, 4),
            "auc_overlap": auc(s, y),
            "auc_nonoverlap": subsample_auc(s, y, h),
            "episode_recall": eps["episode_recall"],
            "alarm_precision": eps["alarm_precision"],
            "n_crises": eps["n_episodes"],
            "n_alarms": eps["n_alarms"],
            "median_lead": lead["median_lead"],
        }
        results[h] = rep
        if verbose:
            ov = "n/a" if rep["auc_overlap"] is None else f"{rep['auc_overlap']:.3f}"
            nv = "n/a" if rep["auc_nonoverlap"] is None else f"{rep['auc_nonoverlap']:.3f}"
            print(f"  h={h:>2}d base={base:.1%}  AUC ov={ov} nov={nv}  "
                  f"crises caught={eps['n_caught']}/{eps['n_episodes']} "
                  f"(recall={rep['episode_recall']})  "
                  f"alarms={eps['n_alarms']} prec={rep['alarm_precision']}  "
                  f"lead={rep['median_lead']}")
    return results


# ---------------------------------------------------------------------------
# IMP-1.3 — retest the absorption ratio on the FF homogeneous cross-section
# ---------------------------------------------------------------------------

def run_absorption_gate(
    n_industries: int = 30,
    start: str = "1970-01-01",
    cov_windows: tuple[int, ...] = (60, 120, 252),
    stride: int = 1,
) -> dict:
    """IMP-1.3: does the absorption ratio have skill on a BROAD HOMOGENEOUS
    cross-section (the question KB-012 left open)? Walks AR forward on the FF
    industry panel for a small cov_window grid and prints the gate for each.
    """
    from fragility import absorption_ratio

    print(f"Fetching FF {n_industries}-industry daily returns + market (cached)...")
    ind = fetch_ff_industries(n_industries)
    ind = ind[ind.index >= pd.Timestamp(start)]
    market = fetch_ff_market()
    market = market[market.index >= pd.Timestamp(start)]
    histories = returns_to_histories(ind)
    anchor = market.index
    print(f"  {ind.shape[1]} industries, {len(ind)} days "
          f"{ind.index[0].date()}..{ind.index[-1].date()}\n")

    out: dict = {}
    for cw in cov_windows:
        # AR_long baseline ~1yr; give the slice room for cov_window + baseline.
        lookback = cw + 300
        sig = walk_forward_signal(
            lambda sl, cw=cw: (
                r["score"] if (r := absorption_ratio(
                    sl, cov_window=cw, short_window=15, min_baseline=252)) else None),
            histories, anchor, lookback=lookback, min_history=cw + 260, stride=stride,
        )
        out[cw] = evaluate_signal(sig, market, name=f"absorption(cov={cw})")
    return out


# ---------------------------------------------------------------------------
# IMP-1.4 — financial turbulence (Mahalanobis distance) on the same panel
# ---------------------------------------------------------------------------

def turbulence_signal(
    sliced: dict,
    cov_window: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    min_baseline: int = 252,
) -> Optional[float]:
    """Financial-turbulence score (Kritzman & Li 2010, "Skulls, Financial
    Turbulence, and Risk Management"): the Mahalanobis distance of the most
    recent return vector from the trailing cross-sectional mean, measured in the
    metric of the trailing covariance,
        d_t = (r_t - mu)' Sigma^-1 (r_t - mu).
    A large d_t means today's return pattern is statistically unusual GIVEN the
    recent volatilities AND correlations — the co-movement structure is under
    stress. Unlike the absorption ratio (which reads the eigenstructure), this
    reads the *surprise* of the latest observation against it; the two are
    designed to be complementary, which is exactly what IMP-1.5 will test.

    Estimation notes for a ~30-name panel:
      * covariance is Ledoit-style shrunk toward its diagonal (`shrink`) so the
        30x30 inverse is stable even from a ~year window;
      * the score averages the last `smooth` daily distances (single-day
        turbulence is very spiky), all against the SAME window mu/Sigma;
      * everything uses only observations up to the anchor date (PIT-safe).
    Returns None if the panel is too short/narrow to condition on.
    """
    rets = {}
    for name, prices in sliced.items():
        p = pd.Series(prices).astype(float)
        p = p.where(p > 0)
        r = np.log(p / p.shift(1)).dropna()
        if len(r):
            rets[name] = r
    if len(rets) < 3:
        return None
    R = pd.DataFrame(rets).dropna()
    if R.shape[0] < min_baseline or R.shape[1] < 3:
        return None

    win = R.tail(cov_window)
    n_obs, n_assets = win.shape
    if n_obs < max(60, n_assets + 5):          # need the inverse to be sane
        return None

    mu = win.mean().to_numpy()
    X = win.to_numpy() - mu
    cov = np.cov(X, rowvar=False)
    diag = np.diag(np.diag(cov))               # shrink toward pure-variance target
    cov_s = (1.0 - shrink) * cov + shrink * diag
    try:
        inv = np.linalg.inv(cov_s)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(cov_s)

    k = min(smooth, len(X))
    dists = [float(row @ inv @ row) for row in X[-k:]]
    dists = [d for d in dists if np.isfinite(d) and d >= 0]
    if not dists:
        return None
    return float(np.mean(dists))               # rank-scored downstream; raw is fine


def run_turbulence_gate(
    n_industries: int = 30,
    start: str = "1970-01-01",
    cov_windows: tuple[int, ...] = (120, 252),
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
) -> dict:
    """IMP-1.4: run financial turbulence through the same gate as the absorption
    ratio, on the FF industry panel, for a small cov_window grid.
    """
    print(f"Fetching FF {n_industries}-industry daily returns + market (cached)...")
    ind = fetch_ff_industries(n_industries)
    ind = ind[ind.index >= pd.Timestamp(start)]
    market = fetch_ff_market()
    market = market[market.index >= pd.Timestamp(start)]
    histories = returns_to_histories(ind)
    anchor = market.index
    print(f"  {ind.shape[1]} industries, {len(ind)} days "
          f"{ind.index[0].date()}..{ind.index[-1].date()}  "
          f"(shrink={shrink}, smooth={smooth})\n")

    out: dict = {}
    for cw in cov_windows:
        lookback = cw + 300
        sig = walk_forward_signal(
            lambda sl, cw=cw: turbulence_signal(
                sl, cov_window=cw, shrink=shrink, smooth=smooth, min_baseline=cw),
            histories, anchor, lookback=lookback, min_history=cw, stride=stride,
        )
        out[cw] = evaluate_signal(sig, market, name=f"turbulence(cov={cw})")
    return out


# ---------------------------------------------------------------------------
# IMP-1.5 — orthogonality / ensemble test: do AR & turbulence ADD to a
# variance-led baseline on a COMMON window and label?
# ---------------------------------------------------------------------------

def _walk_single(signal_fn, close, anchor, lookback, min_history, stride):
    """Walk a single-series fragility component (e.g. variance-trend) forward,
    look-ahead-safe, returning its 0-100 score per anchor date."""
    s = pd.Series(close).astype(float)
    out: dict = {}
    for d in anchor[::stride]:
        past = s[s.index <= d].tail(lookback)
        if len(past) < min_history:
            continue
        r = signal_fn(past)
        if r is not None and np.isfinite(r.get("score", np.nan)):
            out[d] = float(r["score"])
    return pd.Series(out, name="signal")


def run_ensemble_gate(
    n_industries: int = 30,
    start: str = "1970-01-01",
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
) -> dict:
    """IMP-1.5 — the adoption gate. Build three signals on the SAME FF panel and
    the SAME FF-market drawdown label, over a COMMON date index:

      * B    = variance-trend on the FF market Close — a proxy for the live
               composite's *leading* (0.45) component; the honest, non-circular
               baseline (the VIX-term 0.35 arm has no FF analogue, so this baseline
               is deliberately conservative — see the KB caveat).
      * AR   = absorption ratio on the industry panel (KB-013).
      * TURB = turbulence on the industry panel (KB-014).

    Then score B alone vs rank-blended ensembles (B+AR, B+TURB, B+AR+TURB) and an
    OR-of-channels flag, to answer: does the cross-section add ORTHOGONAL skill the
    variance-led baseline does not already have?
    """
    from fragility import realized_variance_trend, absorption_ratio

    print(f"Fetching FF {n_industries}-industry panel + market (cached)...")
    ind = fetch_ff_industries(n_industries)
    ind = ind[ind.index >= pd.Timestamp(start)]
    market = fetch_ff_market()
    market = market[market.index >= pd.Timestamp(start)]
    histories = returns_to_histories(ind)
    anchor = market.index
    print(f"  {ind.shape[1]} industries, {len(ind)} days "
          f"{ind.index[0].date()}..{ind.index[-1].date()}  "
          f"(AR cov={cov_ar}, TURB cov={cov_turb}, stride={stride})\n")

    B = _walk_single(realized_variance_trend, market, anchor,
                     lookback=300, min_history=90, stride=stride)
    AR = walk_forward_signal(
        lambda sl: (r["score"] if (r := absorption_ratio(
            sl, cov_window=cov_ar, short_window=15, min_baseline=252)) else None),
        histories, anchor, lookback=cov_ar + 300, min_history=cov_ar + 260, stride=stride)
    TURB = walk_forward_signal(
        lambda sl: turbulence_signal(
            sl, cov_window=cov_turb, shrink=shrink, smooth=smooth, min_baseline=cov_turb),
        histories, anchor, lookback=cov_turb + 300, min_history=cov_turb, stride=stride)

    # common window so every comparison is apples-to-apples (same n, same dates)
    common = B.index.intersection(AR.index).intersection(TURB.index)
    B, AR, TURB = B.reindex(common), AR.reindex(common), TURB.reindex(common)
    print(f"Common window: {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()}\n")

    # rank-transform to a common [0,1] scale, then blend (equal weight)
    rB, rAR, rT = B.rank(pct=True), AR.rank(pct=True), TURB.rank(pct=True)
    blends = {
        "B (variance-trend, baseline)": rB,
        "AR only":                      rAR,
        "TURB only":                    rT,
        "B + AR":                       (rB + rAR) / 2,
        "B + TURB":                     (rB + rT) / 2,
        "B + AR + TURB":                (rB + rAR + rT) / 3,
    }
    results: dict = {}
    for label, sig in blends.items():
        results[label] = evaluate_signal(sig, market, name=label)

    # OR-of-channels: fire if ANY channel is in its own top decile (recall knob)
    q = 0.90
    or_flag = (rB >= q) | (rAR >= q) | (rT >= q)
    print(f"\n=== OR-of-channels (any of B/AR/TURB in top decile) ===")
    for h in (5, 10):
        labels = drawdown_label(pd.Series(market).astype(float), 0.05, h)
        y = labels.reindex(common).dropna()
        flag = or_flag.reindex(y.index).fillna(False)
        eps = episode_scoring(flag, y)
        print(f"  h={h:>2}d  crises caught={eps['n_caught']}/{eps['n_episodes']} "
              f"(recall={eps['episode_recall']})  alarms={eps['n_alarms']} "
              f"prec={eps['alarm_precision']}")
    return results


# ---------------------------------------------------------------------------
# IMP-1.6 — the real adoption gate: does the cross-section add to the ACTUAL
# live composite (var_led_vix35 on the traded assets), not just to a proxy?
# ---------------------------------------------------------------------------

def _episode_flag_metrics(flag: pd.Series, market_close: pd.Series,
                          threshold: float, horizon: int) -> dict:
    """Episode recall/precision for a boolean flag against forward drawdowns."""
    labels = drawdown_label(pd.Series(market_close).astype(float), threshold, horizon)
    y = labels.reindex(flag.index).dropna()
    f = flag.reindex(y.index).fillna(False)
    return episode_scoring(f, y)


def run_real_composite_gate(
    n_industries: int = 30,
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
) -> dict:
    """IMP-1.6 — the honest adoption test KB-015 said was still owed. Instead of a
    variance-trend proxy, the baseline here is the **real production composite**
    `var_led_vix35`, walked forward on the actual traded assets (SP500/VIX/VIX3M/
    gold/oil/DXY) with the real ^GSPC drawdown label. We then ask whether the
    industry-panel channels (AR, turbulence) — an ORTHOGONAL data source — still
    add recall/AUC on top of the *full* composite (which already has the VIX arm
    the IMP-1.5 proxy lacked).
    """
    import fragility_backtest as fb

    print("Fetching traded assets (yfinance) + FF industry panel (cached)...")
    traded = fb.fetch_histories(start="2008-01-01")
    gspc = pd.Series(traded["sp500"]).astype(float)

    # Real live composite, walked forward look-ahead-safe (var_led_vix35 default).
    frag = fb.walk_forward_fragility(traded, anchor="sp500")
    comp = frag["composite"].astype(float)

    # Industry-panel channels over their own calendar, then align.
    ind = fetch_ff_industries(n_industries)
    histories = returns_to_histories(ind)
    ff_anchor = ind.index
    from fragility import absorption_ratio
    AR = walk_forward_signal(
        lambda sl: (r["score"] if (r := absorption_ratio(
            sl, cov_window=cov_ar, short_window=15, min_baseline=252)) else None),
        histories, ff_anchor, lookback=cov_ar + 300, min_history=cov_ar + 260, stride=stride)
    TURB = walk_forward_signal(
        lambda sl: turbulence_signal(
            sl, cov_window=cov_turb, shrink=shrink, smooth=smooth, min_baseline=cov_turb),
        histories, ff_anchor, lookback=cov_turb + 300, min_history=cov_turb, stride=stride)

    common = comp.index.intersection(AR.index).intersection(TURB.index)
    comp, AR, TURB = comp.reindex(common), AR.reindex(common), TURB.reindex(common)
    print(f"  common window: {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()} "
          f"(composite ∩ industry channels, stride={stride})\n")

    rC, rAR, rT = comp.rank(pct=True), AR.rank(pct=True), TURB.rank(pct=True)
    blend = (rC + rAR + rT) / 3

    # 1) baseline vs blend, threshold-free + episode (all on the SAME window/label)
    print("--- Composite ALONE (the real var_led_vix35 baseline) ---")
    base_res = evaluate_signal(rC, gspc, name="composite")
    print("\n--- Composite + AR + TURB (rank blend) ---")
    blend_res = evaluate_signal(blend, gspc, name="composite+AR+TURB")

    # 2) the recall knob: OR-of-channels vs composite's own top-decile flag
    q = 0.90
    comp_flag = rC >= q
    or_flag = (rC >= q) | (rAR >= q) | (rT >= q)
    print("\n=== Recall knob: composite top-decile vs OR-of-channels ===")
    for h in (5, 10):
        cb = _episode_flag_metrics(comp_flag, gspc, 0.05, h)
        orr = _episode_flag_metrics(or_flag, gspc, 0.05, h)
        print(f"  h={h:>2}d  composite : caught {cb['n_caught']}/{cb['n_episodes']} "
              f"(recall={cb['episode_recall']})  alarms={cb['n_alarms']} "
              f"prec={cb['alarm_precision']}")
        print(f"         OR-channels: caught {orr['n_caught']}/{orr['n_episodes']} "
              f"(recall={orr['episode_recall']})  alarms={orr['n_alarms']} "
              f"prec={orr['alarm_precision']}")
    return {"baseline": base_res, "blend": blend_res}


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "absorption"
    if which == "turbulence":
        run_turbulence_gate()
    elif which == "ensemble":
        run_ensemble_gate()
    elif which == "real":
        run_real_composite_gate()
    elif which == "absorption":
        run_absorption_gate()
    else:
        run_absorption_gate()
        run_turbulence_gate()
        run_ensemble_gate()
