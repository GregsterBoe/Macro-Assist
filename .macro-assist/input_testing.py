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
    fetch_sector_etfs, _SECTOR_ETFS, _ETF_CACHE,
)
# turbulence_signal graduated into the library layer (fragility.py) once KB-020
# validated it on the live sector-ETF panel; the harness now consumes it there.
from fragility import turbulence_signal

_KF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_MISSING = {-99.99, -999.0, -99.99}     # Ken French missing-data codes

_DEFAULT_CACHE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "macro-assist", "ff",
)

# The live sector-ETF panel (_SECTOR_ETFS / _ETF_CACHE / fetch_sector_etfs) now
# lives in fragility_backtest.py (the data layer, next to fetch_histories) and is
# imported above; it graduated out of this harness with KB-020 (IMP-4.2).


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
# IMP-1.4 — financial turbulence (Mahalanobis distance) on the same panel.
# `turbulence_signal` graduated into fragility.py (imported at the top of this
# module); only its gate driver stays here.
# ---------------------------------------------------------------------------

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


def _composite_channel(start: str = "2008-01-01") -> dict:
    """The real production composite (`var_led_vix35`) walked forward on the traded
    assets, plus the ^GSPC level for labels. Extracted so the FF and ETF feeds share
    ONE composite computation (the expensive part) instead of refetching it."""
    import fragility_backtest as fb
    traded = fb.fetch_histories(start=start)
    gspc = pd.Series(traded["sp500"]).astype(float)
    frag = fb.walk_forward_fragility(traded, anchor="sp500")
    comp = frag["composite"].astype(float)
    return {"gspc": gspc, "comp": comp}


def _panel_histories(panel: str, n_industries: int, start: str) -> tuple:
    """Resolve a homogeneous cross-section feed to (histories dict, anchor index).

    panel='ff'  -> Fama-French `n_industries` daily portfolios (deep backtest feed).
    panel='etf' -> the live daily SPDR sector panel (IMP-4.2), the daily-fresh
                   substitute the live OR flag (IMP-4.3) will actually read.
    """
    if panel == "etf":
        px = fetch_sector_etfs(start=start)
        histories = {c: px[c].dropna() for c in px.columns}
        return histories, px.index
    ind = fetch_ff_industries(n_industries)
    return returns_to_histories(ind), ind.index


def _panel_ar_turb(histories: dict, anchor: pd.DatetimeIndex,
                   cov_ar: int, cov_turb: int, shrink: float,
                   smooth: int, stride: int) -> tuple:
    """Walk the absorption-ratio and turbulence channels forward on a cross-section
    panel, look-ahead-safe. ONE code path so the FF backtest feed and the live ETF
    feed compute identical channels — the whole point of IMP-4.2's parity check."""
    from fragility import absorption_ratio
    AR = walk_forward_signal(
        lambda sl: (r["score"] if (r := absorption_ratio(
            sl, cov_window=cov_ar, short_window=15, min_baseline=252)) else None),
        histories, anchor, lookback=cov_ar + 300, min_history=cov_ar + 260, stride=stride)
    TURB = walk_forward_signal(
        lambda sl: turbulence_signal(
            sl, cov_window=cov_turb, shrink=shrink, smooth=smooth, min_baseline=cov_turb),
        histories, anchor, lookback=cov_turb + 300, min_history=cov_turb, stride=stride)
    return AR, TURB


def _build_real_channels(
    n_industries: int = 30,
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
    start: str = "2008-01-01",
    panel: str = "ff",
) -> dict:
    """Build the three RAW channels IMP-1.6 / IMP-4 share, aligned on a common
    date index: the real production composite (`var_led_vix35` on the traded
    assets), plus the cross-section absorption ratio and turbulence. Returns raw
    (un-ranked) series so callers can rank in-sample (the gate) OR fit PIT/holdout
    thresholds on them (the CV). Extracted so run_real_composite_gate and
    run_holdout_cv construct identical channels from one code path. `panel` selects
    the cross-section feed ('ff' backtest / 'etf' live), unchanged for existing callers.
    """
    feed = "FF industry panel (cached)" if panel != "etf" else "SPDR sector-ETF panel (yfinance)"
    print(f"Fetching traded assets (yfinance) + {feed}...")
    cc = _composite_channel(start)
    gspc, comp = cc["gspc"], cc["comp"]

    histories, anchor = _panel_histories(panel, n_industries, start)
    AR, TURB = _panel_ar_turb(histories, anchor, cov_ar, cov_turb, shrink, smooth, stride)

    common = comp.index.intersection(AR.index).intersection(TURB.index)
    comp, AR, TURB = comp.reindex(common), AR.reindex(common), TURB.reindex(common)
    print(f"  common window: {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()} "
          f"(composite ∩ {panel} channels, stride={stride})\n")
    return {"common": common, "gspc": gspc, "comp": comp, "AR": AR, "TURB": TURB}


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
    ch = _build_real_channels(n_industries, cov_ar, cov_turb, shrink, smooth, stride)
    gspc, comp, AR, TURB = ch["gspc"], ch["comp"], ch["AR"], ch["TURB"]

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


# ---------------------------------------------------------------------------
# IMP-4 — the honest yardstick. KB-016's "OR-of-channels doubles recall" number
# used a decile cut ranked over the WHOLE window, so the thresholds had already
# seen the test crises. Before we trust that doubling — let alone OR more channels
# (IMP-2/3) into the flag — we need to know how much survives when the thresholds
# have NOT seen the crisis they are judged on. Two honest protocols:
#
#   PIT  = expanding-window thresholds (the realistic LIVE operating point): each
#          day's decile cut is fit only on that channel's own past. Gives both
#          recall and precision, but on the post-warmup window only.
#   LOCO = leave-one-crisis-out (the GENERALIZATION headline): fit each channel's
#          cut on every day EXCEPT the held-out crisis, ask if the OR flag still
#          fires inside it. Recall only (n crises are the folds); precision is
#          read from PIT. The label episodes ARE the folds (drawdown_label already
#          spans the pre-drawdown warning days), so this reuses the gate's crisis
#          definition exactly.
#
# For each protocol we print OR-of-channels beside composite-alone, so the real
# question is visible: does the cross-section's recall ADVANTAGE persist, or was
# the whole gap an artifact of in-sample thresholds?
# ---------------------------------------------------------------------------

def _fixed_decile_or_flags(channels: dict, q: float = 0.90,
                           keys: Optional[list] = None) -> dict:
    """In-sample reference: fix each channel's decile cut over the WHOLE window
    (the KB-016 protocol). Returns {'or', 'comp'} boolean flags on the full index.
    `keys` selects which channels the OR fires over (default the IMP-1 trio); a
    4th channel (IMP-2 credit) is tested by passing an extended list."""
    keys = keys or ["comp", "AR", "TURB"]
    cuts = {k: float(channels[k].quantile(q)) for k in keys}
    fires = {k: (channels[k] >= cuts[k]) for k in keys}
    or_flag = fires[keys[0]].copy()
    for k in keys[1:]:
        or_flag = or_flag | fires[k]
    return {"or": or_flag, "comp": fires["comp"]}


def _pit_decile_or_flags(channels: dict, q: float = 0.90,
                         min_warmup: int = 252,
                         keys: Optional[list] = None) -> dict:
    """Expanding-window PIT protocol. For each day i past `min_warmup`, each
    channel's threshold is the q-quantile of its OWN values strictly before i.
    OR fires if any channel is at/above its own PIT cut; composite-alone fires on
    the composite cut only. Returns boolean flags on the evaluable (post-warmup)
    window — early days are dropped, so denominators shrink to crises we could
    actually have called live. `keys` selects the OR channels (default IMP-1 trio).
    """
    keys = keys or ["comp", "AR", "TURB"]
    arrs = {k: channels[k].to_numpy(dtype=float) for k in keys}
    idx = channels["comp"].index
    n = len(idx)
    or_days, comp_days, keep = [], [], []
    for i in range(n):
        if i < min_warmup:
            continue
        fires = {}
        ok = True
        for k in keys:
            past = arrs[k][:i]
            past = past[np.isfinite(past)]
            if len(past) < min_warmup:
                ok = False
                break
            thr = float(np.quantile(past, q))
            cur = arrs[k][i]
            fires[k] = bool(np.isfinite(cur) and cur >= thr)
        if not ok:
            continue
        keep.append(idx[i])
        comp_days.append(fires["comp"])
        or_days.append(any(fires[k] for k in keys))
    ev = pd.DatetimeIndex(keep)
    return {"or": pd.Series(or_days, index=ev),
            "comp": pd.Series(comp_days, index=ev)}


def _loco_recall(channels: dict, gspc: pd.Series, q: float,
                 horizon: int, keys: Optional[list] = None) -> dict:
    """Leave-one-crisis-out recall. The drawdown-label episodes are the folds;
    for each, fit every channel's q-cut on all days OUTSIDE the crisis span and
    ask whether the OR flag (and composite-alone) fires anywhere inside it. Honest
    out-of-sample recall: the threshold never saw the crisis it is judged on.
    `keys` selects the OR channels (default IMP-1 trio).
    """
    keys = keys or ["comp", "AR", "TURB"]
    common = channels["comp"].index
    labels = drawdown_label(pd.Series(gspc).astype(float), 0.05, horizon)
    y = labels.reindex(common).dropna().astype(bool)
    eps = collapse_episodes(y)
    vals = {k: channels[k].reindex(common) for k in keys}

    per_fold = []
    or_caught = comp_caught = 0
    for (s, e) in eps:
        test = (common >= s) & (common <= e)
        train = ~test
        cut = {}
        ok = True
        for k in keys:
            tr = vals[k][train].dropna()
            if len(tr) < 60:
                ok = False
                break
            cut[k] = float(tr.quantile(q))
        if not ok:
            continue
        seg = {k: vals[k][test] for k in keys}
        fire_comp = bool((seg["comp"] >= cut["comp"]).any())
        fire_or = any(bool((seg[k] >= cut[k]).any()) for k in keys)
        or_caught += fire_or
        comp_caught += fire_comp
        per_fold.append((s.date(), e.date(), fire_comp, fire_or))
    n = len(per_fold)
    return {
        "n_crises": n,
        "comp_recall": (round(comp_caught / n, 3) if n else None),
        "or_recall": (round(or_caught / n, 3) if n else None),
        "comp_caught": comp_caught, "or_caught": or_caught,
        "folds": per_fold,
    }


def run_holdout_cv(
    n_industries: int = 30,
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
    q: float = 0.90,
    min_warmup: int = 252,
) -> dict:
    """IMP-4 CV spine. Re-score the OR-of-channels flag (composite | AR | TURB top
    decile) under thresholds that have NOT seen the crisis they are judged on, and
    print it beside composite-alone and beside the in-sample (KB-016) number, so
    the leakage-adjusted recall advantage is legible. This is the yardstick every
    NEW channel (IMP-2 credit/funding, IMP-3 semivariance) must clear before it is
    allowed into the OR set — otherwise "recall doubled again" is just the
    mechanical artifact of OR-ing more signals on ~7 crises.
    """
    ch = _build_real_channels(n_industries, cov_ar, cov_turb, shrink, smooth, stride)
    gspc = ch["gspc"]
    channels = {"comp": ch["comp"], "AR": ch["AR"], "TURB": ch["TURB"]}

    fixed = _fixed_decile_or_flags(channels, q)
    pit = _pit_decile_or_flags(channels, q, min_warmup)
    print(f"PIT evaluable window: {len(pit['or'])} of {len(ch['common'])} readings "
          f"(first {min_warmup} dropped to warm the expanding thresholds)\n")

    def _row(tag, flag, restrict_index=None):
        for h in (5, 10):
            f = flag if restrict_index is None else flag.reindex(restrict_index).dropna()
            m = _episode_flag_metrics(f.astype(bool), gspc, 0.05, h)
            print(f"  {tag:<26} h={h:>2}d  recall={m['episode_recall']} "
                  f"({m['n_caught']}/{m['n_episodes']})  "
                  f"alarms={m['n_alarms']} prec={m['alarm_precision']}")

    print("=== Composite-alone vs OR-of-channels — three evaluation protocols ===\n")
    print("[1] In-sample decile (KB-016 protocol — thresholds saw the crises):")
    _row("composite (in-sample)", fixed["comp"])
    _row("OR-channels (in-sample)", fixed["or"])
    print("\n[2] In-sample, but on the PIT evaluable window (isolates window-shrink):")
    _row("composite (in-sample*)", fixed["comp"], pit["or"].index)
    _row("OR-channels (in-sample*)", fixed["or"], pit["or"].index)
    print("\n[3] PIT expanding-window thresholds (the realistic LIVE operating point):")
    _row("composite (PIT)", pit["comp"])
    _row("OR-channels (PIT)", pit["or"])

    print("\n=== Leave-one-crisis-out recall (generalization headline) ===")
    loco = {}
    for h in (5, 10):
        r = _loco_recall(channels, gspc, q, h)
        loco[h] = r
        print(f"  h={h:>2}d  {r['n_crises']} crisis folds  "
              f"composite recall={r['comp_recall']} ({r['comp_caught']}/{r['n_crises']})  "
              f"OR-channels recall={r['or_recall']} ({r['or_caught']}/{r['n_crises']})")
    return {"fixed": fixed, "pit": pit, "loco": loco}


# ---------------------------------------------------------------------------
# IMP-4.2 — swap the cross-section feed under the AR/TURB channels from the
# Fama-French backtest panel (monthly-lagged, unusable live) to the daily-fresh
# SPDR sector-ETF panel, and CHECK the swap does not degrade the validated
# operating point. The FF panel proved the channels (KB-013..017); this asks the
# one question that blocks a live wiring (IMP-4.3): does the coarser, live feed
# (9 sectors vs 30 industries) reproduce the FF-fed OR flag's PIT + LOCO recall
# without collapsing precision? Both feeds are scored on ONE shared window (comp ∩
# FF-channels ∩ ETF-channels) so the ONLY thing that changes is the feed, not the
# dates. GO -> hand the live panel to IMP-4.3; NO-GO / degradation -> a KB negative.
# ---------------------------------------------------------------------------

def run_etf_panel_gate(
    n_industries: int = 30,
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
    q: float = 0.90,
    min_warmup: int = 252,
    start: str = "2008-01-01",
) -> dict:
    """IMP-4.2 — feed-parity gate: FF industry panel vs live SPDR sector-ETF panel
    behind the SAME AR/TURB channels, composite held fixed, on one shared window."""
    print("Fetching traded assets + composite once, then BOTH cross-section feeds...\n")
    cc = _composite_channel(start)
    gspc, comp = cc["gspc"], cc["comp"]

    hist_ff, cal_ff = _panel_histories("ff", n_industries, start)
    hist_etf, cal_etf = _panel_histories("etf", n_industries, start)

    # Compute BOTH feeds' channels on ONE shared anchor grid, so AR_ff/AR_etf land
    # on identical dates (independently strided grids off different trading
    # calendars almost never coincide). Pre-stride the shared anchor, then walk each
    # feed with stride=1 over it — the feed is then the only moving part.
    shared = comp.index.intersection(cal_ff).intersection(cal_etf)[::stride]
    print(f"  ETF panel: {len(hist_etf)} sectors, "
          f"{cal_etf[0].date()}..{cal_etf[-1].date()}  (FF industries: {n_industries})")
    print(f"  shared anchor: {len(shared)} dates "
          f"{shared[0].date()}..{shared[-1].date()} (stride={stride})")

    AR_ff, TURB_ff = _panel_ar_turb(hist_ff, shared, cov_ar, cov_turb, shrink, smooth, 1)
    AR_etf, TURB_etf = _panel_ar_turb(hist_etf, shared, cov_ar, cov_turb, shrink, smooth, 1)

    # ONE shared window so the feed is the only moving part.
    common = comp.index
    for s in (AR_ff, TURB_ff, AR_etf, TURB_etf):
        common = common.intersection(s.index)
    comp_c = comp.reindex(common)
    ch_ff = {"comp": comp_c, "AR": AR_ff.reindex(common), "TURB": TURB_ff.reindex(common)}
    ch_etf = {"comp": comp_c, "AR": AR_etf.reindex(common), "TURB": TURB_etf.reindex(common)}
    print(f"  shared window: {len(common)} readings "
          f"{common[0].date()}..{common[-1].date()} "
          f"(comp ∩ FF ∩ ETF channels)\n")

    # 1) Standalone channel skill — does each ETF-fed channel still clear the gate?
    print("=== [A] Standalone channel skill (raw AR / TURB vs >=5% drawdowns) ===")
    for tag, ch in (("FF", ch_ff), ("ETF", ch_etf)):
        for cname in ("AR", "TURB"):
            evaluate_signal(ch[cname], gspc, name=f"{cname} ({tag} feed)")

    # 2) The operating point — PIT + LOCO for the OR trio under each feed.
    def _pit_row(tag, ch):
        pit = _pit_decile_or_flags(ch, q, min_warmup)
        for h in (5, 10):
            m = _episode_flag_metrics(pit["or"].astype(bool), gspc, 0.05, h)
            print(f"  OR ({tag:<3} PIT)  h={h:>2}d  recall={m['episode_recall']} "
                  f"({m['n_caught']}/{m['n_episodes']})  alarms={m['n_alarms']} "
                  f"prec={m['alarm_precision']}")
        return pit

    print("\n=== [B] OR-of-channels at the LIVE PIT operating point (feed swap) ===")
    cpit = _pit_decile_or_flags(ch_ff, q, min_warmup)   # composite-alone identical either feed
    for h in (5, 10):
        m = _episode_flag_metrics(cpit["comp"].astype(bool), gspc, 0.05, h)
        print(f"  composite     h={h:>2}d  recall={m['episode_recall']} "
              f"({m['n_caught']}/{m['n_episodes']})  alarms={m['n_alarms']} "
              f"prec={m['alarm_precision']}")
    _pit_row("FF", ch_ff)
    _pit_row("ETF", ch_etf)

    print("\n=== [C] Leave-one-crisis-out recall (generalization) ===")
    loco = {}
    for h in (5, 10):
        rf = _loco_recall(ch_ff, gspc, q, h)
        re_ = _loco_recall(ch_etf, gspc, q, h)
        loco[h] = {"ff": rf, "etf": re_}
        print(f"  h={h:>2}d  {rf['n_crises']} folds  "
              f"composite={rf['comp_recall']} ({rf['comp_caught']}/{rf['n_crises']})  "
              f"OR-FF={rf['or_recall']} ({rf['or_caught']}/{rf['n_crises']})  "
              f"OR-ETF={re_['or_recall']} ({re_['or_caught']}/{re_['n_crises']})")
        # which crises differ between the two feeds
        diff = [(s, e, ff_hit, et_hit)
                for (s, e, _c, ff_hit), (_s2, _e2, _c2, et_hit)
                in zip(rf["folds"], re_["folds"]) if ff_hit != et_hit]
        for (s, e, ff_hit, et_hit) in diff:
            only = "FF only" if ff_hit else "ETF only"
            print(f"        differs {s}..{e}: {only}")
    return {"ff": ch_ff, "etf": ch_etf, "loco": loco, "common": common}


# ---------------------------------------------------------------------------
# IMP-3 — downside asymmetry in the variance-trend channel. The live B channel
# (realized_variance_trend) trends SYMMETRIC realized vol, which also rises in
# melt-ups. Hypothesis: a DOWNSIDE-only vol estimator (semi-deviation), or the
# signed downside-minus-upside asymmetry, is a sharper stress lead. This sharpens
# the EXISTING channel (it does NOT add a new OR channel), so the honest test is
# the standalone gate: does the downside variant beat the symmetric baseline on
# the same series/label? Kept in the harness (measure first, wire into
# fragility.py only if it clears) exactly like the AR/turbulence candidates.
# ---------------------------------------------------------------------------

def _vol_trend_score(vseries, trend_window: int = 60, scale_series=None):
    """The slope/normalize/squash pipeline shared by every variance-trend variant
    — identical arithmetic to fragility.realized_variance_trend, factored so the
    'sym' mode reproduces the live channel to the digit (the regression check).

    Fits a least-squares slope to the trailing `trend_window` of `vseries`,
    normalises by a positive level (the series' own mean, or the mean of a
    companion `scale_series` when `vseries` is a signed quantity that can cross
    zero), and squashes to 0-100 with the same k=2.5.
    """
    vseries = pd.Series(vseries).dropna()
    if len(vseries) < 10:
        return None
    window = vseries.iloc[-min(trend_window, len(vseries)):]
    y = window.to_numpy()
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    if scale_series is None:
        level = float(y.mean())
    else:
        level = float(pd.Series(scale_series).reindex(window.index).mean())
    if not np.isfinite(level) or level <= 0:
        return None
    from fragility import _squash
    norm_slope = slope * len(y) / level
    return {"score": _squash(norm_slope, k=2.5), "norm_slope": norm_slope,
            "current": float(y[-1]), "level": level, "n": int(len(y))}


def semivariance_trend(
    close: pd.Series,
    vol_window: int = 20,
    trend_window: int = 60,
    mode: str = "down",
) -> Optional[dict]:
    """IMP-3 candidate: the variance-trend on a one-sided / signed realized-vol
    series — the downside-asymmetry analogue of realized_variance_trend.

    mode:
      'sym'    — symmetric rolling std (reproduces the live B channel; baseline).
      'down'   — downside semi-deviation sqrt(mean(min(r,0)^2)): trends DOWNSIDE
                 vol only, so a melt-up in symmetric vol does not light it.
      'signed' — downside-minus-upside realized variance (a signed asymmetry that
                 can cross zero), normalised by mean TOTAL realized variance so the
                 slope stays dimensionless and sign-meaningful.
    """
    from fragility import _to_log_returns
    rets = _to_log_returns(close)
    if len(rets) < vol_window + 5:
        return None
    neg = rets.where(rets < 0, 0.0)
    pos = rets.where(rets > 0, 0.0)

    if mode == "sym":
        return _vol_trend_score(rets.rolling(vol_window).std(), trend_window)
    if mode == "down":
        semidev = np.sqrt((neg ** 2).rolling(vol_window).mean())
        return _vol_trend_score(semidev, trend_window)
    if mode == "signed":
        down_var = (neg ** 2).rolling(vol_window).mean()
        up_var = (pos ** 2).rolling(vol_window).mean()
        tot_var = (rets ** 2).rolling(vol_window).mean()
        return _vol_trend_score(down_var - up_var, trend_window, scale_series=tot_var)
    raise ValueError(f"unknown mode {mode!r}")


def run_semivariance_gate(
    start: str = "1970-01-01",
    stride: int = 5,
    also_real: bool = True,
) -> dict:
    """IMP-3 gate: symmetric baseline vs downside semi-deviation vs signed
    asymmetry, each walked forward look-ahead-safe and scored with the de-overlapped
    metrics. Primary run on the FF market (deep history = a real crisis count);
    optional confirmation on the production ^GSPC (2008+). A downside variant only
    graduates if it BEATS the symmetric baseline's episode recall/precision + AUC.
    """
    modes = [("B symmetric (baseline)", "sym"),
             ("downside semi-deviation", "down"),
             ("signed semivar asymmetry", "signed")]

    print("Fetching FF market (cached) for the deep-history gate...")
    market = fetch_ff_market()
    market = market[market.index >= pd.Timestamp(start)]
    anchor = market.index
    print(f"  FF market {len(market)} days {anchor[0].date()}..{anchor[-1].date()} "
          f"(stride={stride})\n")

    out: dict = {}
    print("=== IMP-3 on the FF market (deep history) ===")
    for label, mode in modes:
        sig = _walk_single(lambda past, m=mode: semivariance_trend(past, mode=m),
                           market, anchor, lookback=300, min_history=90, stride=stride)
        out[label] = evaluate_signal(sig, market, name=label)

    if also_real:
        import fragility_backtest as fb
        print("\n=== IMP-3 confirmation on the production ^GSPC (2008+) ===")
        traded = fb.fetch_histories(start="2008-01-01")
        gspc = pd.Series(traded["sp500"]).astype(float)
        for label, mode in modes:
            sig = _walk_single(lambda past, m=mode: semivariance_trend(past, mode=m),
                               gspc, gspc.index, lookback=300, min_history=90, stride=stride)
            out[f"{label} [^GSPC]"] = evaluate_signal(sig, gspc, name=f"{label} [^GSPC]")
    return out


# ---------------------------------------------------------------------------
# IMP-2 — credit / funding channel. The live composite is entirely equity-market
# (SP500 variance-trend + VIX term structure); its reserved `acceleration` slot
# was always meant for a credit/funding stress signal (see the note in
# fragility_backtest.py: "the yfinance-only backtest never computes acceleration
# — no HY/NFCI"). Credit spreads lead equity stress through a DIFFERENT market, so
# this is the most promising ORTHOGONAL, non-equity channel to lift the ~0.30
# recall ceiling — and, being destined for the OR set, it must clear the KB-017
# holdout gate (PIT + LOCO recall gain WITHOUT collapsing precision) before wiring.
#
# Canonical source = FRED HY OAS (BAMLH0A0HYM2, daily, 1996+, unrevised) and NFCI.
# When FRED is unreachable (some sandboxed networks silently drop it at the WAF),
# a Yahoo-reachable PROXY — HYG-vs-IEF relative strength — stands in: a real
# credit-market stress read, though an HY ETF is more equity-correlated than the
# OAS spread, so the proxy UNDER-states orthogonality (a conservative test). The
# `source=` switch runs the identical gate on either.
# ---------------------------------------------------------------------------

_FRED_CACHE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "macro-assist", "fred",
)


def _fred_api_fetch(series_id: str, api_key: str, timeout: int = 45) -> pd.Series:
    """Full-history pull via the FRED JSON API (`api.stlouisfed.org`). Unlike the
    `fredgraph.csv` graph host, the API host is NOT bot-blocked, and
    `observation_start` guarantees the complete series (the browser CSV silently
    clips to the graph's ~3yr window). "." values -> NaN."""
    import json
    url = ("https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={api_key}&file_type=json"
           "&observation_start=1900-01-01")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    obs = data.get("observations")
    if not obs:
        raise RuntimeError(f"FRED API returned no observations for {series_id}: "
                           f"{data.get('error_message', data)}")
    s = pd.Series(pd.to_numeric(pd.Series([o["value"] for o in obs]), errors="coerce").to_numpy(),
                  index=pd.to_datetime([o["date"] for o in obs]), name=series_id).dropna()
    return s.sort_index()


def fetch_fred_series(series_id: str, cache_dir: str = _FRED_CACHE,
                      refresh: bool = False, api_key: Optional[str] = None) -> pd.Series:
    """Daily FRED series, cached to disk (offline after the first acquire, like the
    FF fetch). "." missing codes -> NaN. Canonical IMP-2 inputs: 'BAMLH0A0HYM2'
    (ICE BofA US HY OAS) and 'NFCI'.

    Acquisition order (cache-first):
      1. If the CSV is already cached, use it offline.
      2. Else, if a FRED **API key** is available (`api_key=` or env `FRED_API_KEY`),
         pull FULL history from `api.stlouisfed.org` — the reliable route. The graph
         host `fred.stlouisfed.org` is behind an Akamai WAF that bot-blocks scripted
         requests (connect succeeds, HTTP request is dropped → timeout) AND its
         browser `fredgraph.csv` export silently clips to ~3yr; the API host has
         NEITHER problem. Get a free key at fredaccount.stlouisfed.org/apikeys.
      3. Else raise with the exact key/manual steps.
    The API branch also writes the normalized CSV to `cache_dir`, so later runs are
    fully offline.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{series_id}.csv")
    key = api_key or os.environ.get("FRED_API_KEY")
    if refresh or not os.path.exists(cache_path):
        if key:
            s = _fred_api_fetch(series_id, key)
            s.rename_axis("DATE").to_csv(cache_path, header=[series_id])  # cache offline
            return s
        raise RuntimeError(
            f"FRED fetch for {series_id} needs a FRED API key (the graph host is "
            f"WAF-blocked and its browser CSV clips to ~3yr — see KB-019).\n"
            f"  1. Get a free key: https://fredaccount.stlouisfed.org/apikeys\n"
            f"  2. export FRED_API_KEY=your_key_here\n"
            f"  3. re-run — full history is pulled from api.stlouisfed.org and cached.\n"
            f"(Or drop a FULL-history CSV at {cache_path} yourself.)"
        )
    df = pd.read_csv(cache_path)                      # cols: DATE, <ID>; "."=missing
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df.iloc[:, 0]), name=series_id).dropna()
    return s.sort_index()


def fetch_credit_proxy(start: str = "2007-01-01") -> dict:
    """Yahoo (free) HYG & IEF adjusted closes — the market-based credit-stress
    proxy usable when FRED is blocked. HYG = iShares iBoxx HY corporates (credit
    risk + duration); IEF = 7-10y Treasuries (duration only). Their ratio isolates
    the HY *credit* premium, so it falls exactly when spreads widen.
    """
    import yfinance as yf
    out: dict = {}
    for tk in ("HYG", "IEF"):
        h = yf.Ticker(tk).history(start=start)
        c = h["Close"].astype(float)
        c.index = c.index.tz_localize(None)
        out[tk] = c.dropna()
    return out


def credit_stress_raw(source: str = "proxy", start: str = "2007-01-01",
                      vel_window: int = 20, fred_series: str = "BAA10Y") -> dict:
    """Build a daily 'spread-like' credit-stress series (higher = more stress),
    PIT-safe by construction, plus its widening VELOCITY (the leading form for the
    reserved `acceleration` slot). Returns {'spread','level','velocity'}.

      source='proxy' : spread = -log(HYG/IEF) — a synthetic HY spread that rises
                       when HY underperforms duration-matched Treasuries (2007+).
      source='fred'  : `fred_series` LEVEL, in percent (already a spread). Default
                       **BAA10Y** (Moody's Baa − 10Y Treasury, daily, 1986+): a
                       canonical, unrevised, deep-history credit spread. NOTE: the
                       ICE HY/IG OAS series (BAMLH0A0HYM2 / BAMLC0A0CM) are
                       LICENSE-TRUNCATED on free FRED to ~2023+, so they are NOT
                       usable for a 2008+ backtest — BAA10Y is the deep substitute.

    'level' is the raw spread (classic FCI stress gauge, but it drifts with
    regime); 'velocity' = spread.diff(vel_window) is the drift-robust, leading
    widening signal analogous to the composite's variance-TREND philosophy.
    """
    if source == "proxy":
        px = fetch_credit_proxy(start=start)
        common = px["HYG"].index.intersection(px["IEF"].index)
        ratio = (px["HYG"].reindex(common) / px["IEF"].reindex(common)).dropna()
        spread = -np.log(ratio)
    elif source == "fred":
        spread = fetch_fred_series(fred_series)
        spread = spread[spread.index >= pd.Timestamp(start)]
    else:
        raise ValueError(f"unknown credit source {source!r}")
    spread = pd.Series(spread).astype(float).sort_index()
    return {"spread": spread, "level": spread, "velocity": spread.diff(vel_window)}


def run_credit_gate(
    source: str = "proxy",
    n_industries: int = 30,
    cov_ar: int = 120,
    cov_turb: int = 252,
    shrink: float = 0.2,
    smooth: int = 5,
    stride: int = 5,
    q: float = 0.90,
    min_warmup: int = 252,
    vel_window: int = 20,
    fred_series: str = "BAA10Y",
) -> dict:
    """IMP-2 gate. Two questions, in order:

      (1) STANDALONE — does credit stress lead ^GSPC drawdowns at all? Score the
          credit level and widening-velocity through the de-overlapped gate.
      (2) OR-SET ADMISSION (the KB-017 bar) — added as a 4th OR channel beside the
          composite/AR/TURB trio, does credit LIFT recall under the honest holdout
          (in-sample -> PIT -> LOCO) WITHOUT collapsing precision, and does it
          catch crises the other three MISS (the orthogonality signature)?

    Runs on the canonical FRED HY OAS (`source='fred'`) or the Yahoo HYG/IEF proxy
    (`source='proxy'`, the fallback when FRED's WAF blocks this network).
    """
    keys3 = ["comp", "AR", "TURB"]
    keys4 = ["comp", "AR", "TURB", "CREDIT"]

    ch = _build_real_channels(n_industries, cov_ar, cov_turb, shrink, smooth, stride)
    gspc, comp, AR, TURB, common = (
        ch["gspc"], ch["comp"], ch["AR"], ch["TURB"], ch["common"])

    tag = fred_series if source == "fred" else "HYG/IEF"
    print(f"Building credit-stress channel (source={source!r} [{tag}], vel_window={vel_window})...")
    cs = credit_stress_raw(source=source, vel_window=vel_window, fred_series=fred_series)
    vel = cs["velocity"]
    print(f"  credit spread {len(cs['spread'])} days "
          f"{cs['spread'].index[0].date()}..{cs['spread'].index[-1].date()}\n")

    # Truncation guard: a credit series that starts well after the composite window
    # (e.g. a fredgraph.csv clipped to the last ~3yr) silently collapses the OR-set
    # window and produces noise-level crisis counts — refuse rather than mislead.
    if cs["spread"].index[0] > common[0] + pd.Timedelta(days=400):
        raise RuntimeError(
            f"credit history starts {cs['spread'].index[0].date()} but the composite "
            f"window starts {common[0].date()} — the {source!r} series looks TRUNCATED. "
            f"For FRED, re-download the FULL range (URL now carries cosd=1900-01-01) and "
            f"overwrite the cache CSV; the 3yr-clipped file gives a meaningless n≈2-crisis run."
        )

    # (1) standalone gate on the full ^GSPC window (independent of the FF strided grid)
    print("=== (1) STANDALONE: credit stress vs ^GSPC drawdowns ===")
    evaluate_signal(cs["level"].reindex(gspc.index).ffill(), gspc,
                    name=f"credit LEVEL [{source}]")
    evaluate_signal(vel.reindex(gspc.index).ffill(), gspc,
                    name=f"credit VELOCITY d{vel_window} [{source}]")

    # (2) OR-set admission — align CREDIT (velocity) onto the shared composite grid
    CREDIT = vel.reindex(common, method="ffill")
    finite = CREDIT.notna()
    common2 = common[finite.to_numpy()]
    ch4 = {"comp": comp.reindex(common2), "AR": AR.reindex(common2),
           "TURB": TURB.reindex(common2), "CREDIT": CREDIT.reindex(common2)}
    ch3 = {k: ch4[k] for k in keys3}
    print(f"\nOR-set window: {len(common2)} readings "
          f"{common2[0].date()}..{common2[-1].date()} "
          f"(composite ∩ industry ∩ credit)\n")

    fixed3 = _fixed_decile_or_flags(ch3, q, keys3)
    fixed4 = _fixed_decile_or_flags(ch4, q, keys4)
    pit3 = _pit_decile_or_flags(ch3, q, min_warmup, keys3)
    pit4 = _pit_decile_or_flags(ch4, q, min_warmup, keys4)
    print(f"PIT evaluable window: {len(pit4['or'])} of {len(common2)} readings\n")

    def _row(tag, flag, restrict_index=None):
        for h in (5, 10):
            f = flag if restrict_index is None else flag.reindex(restrict_index).dropna()
            m = _episode_flag_metrics(f.astype(bool), gspc, 0.05, h)
            print(f"  {tag:<30} h={h:>2}d  recall={m['episode_recall']} "
                  f"({m['n_caught']}/{m['n_episodes']})  "
                  f"alarms={m['n_alarms']} prec={m['alarm_precision']}")

    print("=== (2) Does CREDIT lift the OR set? composite | 3-ch OR | 4-ch OR ===\n")
    print("[1] In-sample decile (thresholds saw the crises):")
    _row("composite alone", fixed3["comp"])
    _row("OR 3-ch (comp/AR/TURB)", fixed3["or"])
    _row("OR 4-ch (+CREDIT)", fixed4["or"])
    print("\n[3] PIT expanding-window thresholds (the live operating point):")
    _row("composite alone (PIT)", pit3["comp"])
    _row("OR 3-ch (PIT)", pit3["or"])
    _row("OR 4-ch +CREDIT (PIT)", pit4["or"])

    print("\n=== Leave-one-crisis-out recall (generalization headline) ===")
    loco: dict = {}
    for h in (5, 10):
        r3 = _loco_recall(ch3, gspc, q, h, keys3)
        r4 = _loco_recall(ch4, gspc, q, h, keys4)
        rc = _loco_recall(ch4, gspc, q, h, ["comp", "CREDIT"])  # credit's own adds
        loco[h] = {"or3": r3, "or4": r4, "credit": rc}
        print(f"  h={h:>2}d  {r3['n_crises']} folds  "
              f"comp={r3['comp_recall']} ({r3['comp_caught']})  "
              f"OR3={r3['or_recall']} ({r3['or_caught']})  "
              f"OR4+CREDIT={r4['or_recall']} ({r4['or_caught']})")
        gained = [f3[:2] for f3, f4 in zip(r3["folds"], r4["folds"])
                  if f4[3] and not f3[3]]
        if gained:
            print(f"        crises CREDIT newly catches: "
                  + ", ".join(f"{a}..{b}" for a, b in gained))
    return {"fixed3": fixed3, "fixed4": fixed4, "pit3": pit3, "pit4": pit4,
            "loco": loco}


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "absorption"
    if which == "credit":
        src = sys.argv[2] if len(sys.argv) > 2 else "proxy"
        run_credit_gate(source=src)
    elif which == "semivariance":
        run_semivariance_gate()
    elif which == "turbulence":
        run_turbulence_gate()
    elif which == "ensemble":
        run_ensemble_gate()
    elif which == "real":
        run_real_composite_gate()
    elif which == "holdout":
        run_holdout_cv()
    elif which == "etf":
        run_etf_panel_gate()
    elif which == "absorption":
        run_absorption_gate()
    else:
        run_absorption_gate()
        run_turbulence_gate()
        run_ensemble_gate()
