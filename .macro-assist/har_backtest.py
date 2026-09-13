"""
har_backtest.py — WP-17.5 (second half): walk-forward skill read of the HAR-RV
vol forecast as it is wired into the note and the sizer.

The wiring described below is the one this read measured ([KB-033]) and is
kept verbatim as its record. It was changed on 2026-09-13 (`todo.md` #17 →
`resolved.md`): the note fits on a separate 5y fetch
(`market_data.fetch_vol_histories`), the sizer on 1600 calendar days
(`rebalance.HAR_LOOKBACK_DAYS`), and `vol_forecast.har_forecast_or_none`
refuses fewer than `HAR_MIN_RETURNS` = 1000 returns or a non-positive forecast.
The `FIT_WINDOWS` here still cover the old wired range so the read reproduces.

Why this exists
---------------
`vol_forecast.har_rv_forecast` has been in the note since Phase 9, became the
`har_gaussian` comparator in `score_distributions.py` (Phase 22) and sizes
every position in `portfolio/rebalance.py` (Phase 20) — and no skill number has
ever been measured behind it. Its only tests fit it on 1,500 observations and
beat "yesterday's r²", which is neither the wiring nor a real rival. Three
facts about the wiring, read off the callers, drive the design:

  1. The note's forecast is a 4-parameter OLS on a few dozen rows.
     `market_data` fetches `period="90d"` — 74 to 90 closes depending on the
     ticker and the yfinance version, not pinned — and `quant_context` hands
     the whole thing to `har_rv_forecast`, whose design matrix starts at lag
     21: ~50 to ~70 rows. The sizer's `fetch_prices_and_har` uses 130 calendar
     days (~90 closes; ~130 for Bitcoin). The textbook HAR is fit on years.
     `FIT_WINDOWS` reads 62 / 90 / 130 (the wired range) and 252 / 1000 as the
     counterfactual.

  2. The forecast is ONE-STEP-AHEAD daily variance. `har_gaussian` scales it
     to 5- and 20-day intervals as IID (`sigma * sqrt(h/252)`) and the sizer
     treats it as the annualised sigma for the coming week. Whether a 1-day
     forecast is calibrated at those horizons is a question about the *use*,
     measured here separately from the model's skill (`var_ratio`,
     `coverage`).

  3. `max(0, params @ x_new)` can return a zero forecast. Both consumers then
     silently skip the asset (`logged_har_sigma` returns None; the sizer's
     inverse-vol drops any sigma <= 0). A zero forecast is therefore an
     abstention, counted here and excluded from the loss (pre-registered).

Everything is look-ahead-safe by construction: the forecast at date t is
computed from the returns in (t - fit_window, t] only, and every benchmark is a
trailing statistic through t. The pre-registration — benchmark, loss, bar,
disqualifier, the two secondary reads and the prior — is in `roadmap.md`
(WP-17.5) and was written before this ran.

Result → [KB-033] (2026-09-13): `degenerate` on every instrument at every wired
window; the 1000-day fit is `skill` on SP500 / Gold / Bitcoin, so the fetch
period is a wiring defect → `todo.md` #17, landed 2026-09-13 (see the note at
the top; `resolved.md` #17). Not fixed *here*: it changed published numbers,
the sizer's σ and Phase 22's sealed `har_gaussian` comparator, and was dated
against the seal in WP-22.C.

Public functions
----------------
walk_forward_har(returns, fit_window)      -> Series   (1-step daily variance forecast at t)
trailing_benchmarks(returns)               -> DataFrame (rv5, rv22, rv60, ewma94 through t)
realized_forward(returns, h)               -> (RV_h, forward h-day log return)
score_arms(forecast, bench, realized, fret, h) -> dict  (losses, skill, CI, calibration, verdict)
verdict(row)                               -> str      (degenerate | skill | worse | parity)
score_asset(close, fit_windows, horizons)  -> dict     (per fit window, per horizon)
wiring_read(results), horizon_read(results) -> dict    (the two secondary reads)
run_har_read(closes)                       -> dict     [CLI: fetches via yfinance]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from vol_forecast import har_rv_forecast

# --- the wiring, as read off the callers (see module docstring) --------------
# The note: market_data fetches `period="90d"`. What that returns is NOT pinned —
# on 2026-09-13 (yfinance 1.4.1) it was 90 closes for ^GSPC and BTC-USD and 74
# for GC=F, and the live log's zero-forecast rate exceeds the backtest's at any
# of these windows, so the CI window was likely shorter still. 90 is read as the
# wired note window; 62 brackets the short end. The sizer: 130 calendar days =
# ~90 trading closes for the equity-hours instruments, ~130 for Bitcoin.
WIRED_NOTE_WINDOW = 90
WIRED_SIZER_WINDOW = 90     # rebalance.fetch_prices_and_har(lookback_days=130); 130 for BTC-USD
FIT_WINDOWS: tuple[int, ...] = (62, WIRED_NOTE_WINDOW, 130, 252, 1000)
HORIZONS: tuple[int, ...] = (1, 5, 20)
CONSUMER_HORIZON = 5        # the sizer's week; the table's first horizon

# --- pre-registered bar (roadmap.md, WP-17.5) --------------------------------
BENCHMARK = "rv22"          # the verdict is against this one only
BENCHMARKS: tuple[str, ...] = ("rv5", "rv22", "rv60", "ewma94")
EWMA_LAMBDA = 0.94          # RiskMetrics
MIN_SKILL = 0.02            # ADR-0020 / ADR-0016 margin
DEGENERATE_SHARE = 0.01     # > 1 % zero-or-wild forecasts disqualifies
DEGENERATE_RATIO = 10.0     # forecast variance > 10x rv22 is "wild"
VAR_RATIO_BAND = (0.75, 1.33)
COVERAGE_BAND: dict[float, tuple[float, float]] = {0.50: (0.45, 0.55), 0.90: (0.86, 0.94)}
WIRING_MIN_ASSETS = 3       # of the four published assets

BLOCK_DAYS = 21
N_BOOT = 2000
SEED = 7
TRADING_DAYS = 252
_Z = {0.50: 0.6744897501960817, 0.90: 1.6448536269514722}   # two-sided central bands

TICKERS: dict[str, str] = {
    "SP500": "^GSPC", "Gold": "GC=F", "WTI Oil": "CL=F", "Bitcoin": "BTC-USD",
    "IEF": "IEF",
}
PUBLISHED: tuple[str, ...] = ("SP500", "Gold", "WTI Oil", "Bitcoin")   # quant_context._VOL_ASSETS
HISTORY_START = "2007-01-01"


# ---------------------------------------------------------------------------
# Forecasts and targets (all look-ahead-safe)
# ---------------------------------------------------------------------------

def log_returns(close: pd.Series) -> pd.Series:
    close = pd.Series(close).astype(float).dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    return np.log(close / close.shift(1)).dropna()


def har_variance(returns_window) -> float:
    """`har_rv_forecast` on one window, inverted back to daily variance.

    `forecast_daily_vol = sqrt(rv * 252) * 100`, so `(v/100)**2 / 252` is
    exactly the clipped `rv_forecast` the function computed. NaN when the
    function refuses the window (too short).
    """
    try:
        fc = har_rv_forecast(pd.Series(np.asarray(returns_window, dtype=float)))
    except ValueError:
        return float("nan")
    return (fc["forecast_daily_vol"] / 100.0) ** 2 / TRADING_DAYS


def walk_forward_har(returns: pd.Series, fit_window: int, stride: int = 1) -> pd.Series:
    """1-step-ahead daily variance forecast at every date t, fit on the
    `fit_window` returns ending at t (inclusive). Nothing after t is touched."""
    r = pd.Series(returns).astype(float)
    vals = r.to_numpy()
    out = np.full(len(vals), np.nan)
    for t in range(fit_window - 1, len(vals), stride):
        out[t] = har_variance(vals[t - fit_window + 1: t + 1])
    return pd.Series(out, index=r.index, name=f"har{fit_window}")


def trailing_benchmarks(returns: pd.Series) -> pd.DataFrame:
    """Trailing daily-variance estimators through t: rv5 / rv22 / rv60 (means
    of r²) and RiskMetrics EWMA (lambda 0.94)."""
    r2 = pd.Series(returns).astype(float) ** 2
    return pd.DataFrame({
        "rv5":    r2.rolling(5).mean(),
        "rv22":   r2.rolling(22).mean(),
        "rv60":   r2.rolling(60).mean(),
        "ewma94": r2.ewm(alpha=1.0 - EWMA_LAMBDA, adjust=False).mean(),
    })


def realized_forward(returns: pd.Series, horizon: int) -> tuple[pd.Series, pd.Series]:
    """At t: RV_h = mean(r²_{t+1..t+h}) and the h-day forward log return
    sum(r_{t+1..t+h}). NaN where the window is incomplete."""
    r = pd.Series(returns).astype(float)
    r2 = r ** 2
    rv = r2[::-1].rolling(horizon).mean()[::-1].shift(-1)
    fret = r[::-1].rolling(horizon).sum()[::-1].shift(-1)
    return rv.rename(f"rv_fwd{horizon}"), fret.rename(f"fret{horizon}")


# ---------------------------------------------------------------------------
# Losses, interval, verdict
# ---------------------------------------------------------------------------

def qlike(forecast: np.ndarray, realized: np.ndarray) -> np.ndarray:
    """Patton (2011) QLIKE: RV/σ̂² − log(RV/σ̂²) − 1. Zero at a perfect forecast,
    consistent for the true variance under a noisy proxy (unlike MSE on a
    log or vol scale). Requires both arguments > 0."""
    ratio = np.asarray(realized, float) / np.asarray(forecast, float)
    return ratio - np.log(ratio) - 1.0


def _skill(l_arm: np.ndarray, l_bench: np.ndarray) -> float:
    return float(1.0 - l_arm.mean() / l_bench.mean())


def block_bootstrap_skill(l_arm: np.ndarray, l_bench: np.ndarray,
                          block: int = BLOCK_DAYS, n_boot: int = N_BOOT,
                          seed: int = SEED, alpha: float = 0.05) -> dict | None:
    """95 % interval for `1 − mean(l_arm)/mean(l_bench)`, resampling whole
    contiguous `block`-day blocks so overlapping h-day targets keep their
    dependence (an iid interval here would be ~sqrt(h) too narrow)."""
    n = len(l_arm)
    blocks = [slice(i, min(i + block, n)) for i in range(0, n, block)]
    if len(blocks) < 2:
        return None
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        idx = np.concatenate([np.arange(blocks[k].start, blocks[k].stop) for k in pick])
        draws[b] = _skill(l_arm[idx], l_bench[idx])
    draws.sort()
    return {"lo": round(float(draws[int(alpha / 2 * n_boot)]), 4),
            "hi": round(float(draws[min(int((1 - alpha / 2) * n_boot), n_boot - 1)]), 4),
            "n_blocks": len(blocks), "n_boot": n_boot}


def verdict(row: dict) -> str:
    """Pre-registered order: the disqualifier first, then the skill bar.

    degenerate  > DEGENERATE_SHARE of readings were a zero or a wild forecast
    skill       skill vs rv22 > MIN_SKILL and the interval's low end > 0
    worse       skill < −MIN_SKILL and the interval's high end < 0
    parity      anything else
    """
    if row.get("degenerate_share", 0.0) > DEGENERATE_SHARE:
        return "degenerate"
    s, ci = row.get("skill"), row.get("skill_ci")
    if s is None or ci is None:
        return "parity"
    if s > MIN_SKILL and ci["lo"] > 0:
        return "skill"
    if s < -MIN_SKILL and ci["hi"] < 0:
        return "worse"
    return "parity"


def score_arms(forecast: pd.Series, bench: pd.DataFrame, realized: pd.Series,
               fret: pd.Series, horizon: int) -> dict:
    """Score one forecast series against the benchmarks at one horizon.

    Sample = dates where the forecast exists (zero included, for the count),
    every benchmark exists and RV_h > 0. The loss sample then drops the zero
    forecasts (counted as `n_zero`) — QLIKE is undefined at σ̂² = 0 and both
    consumers treat that reading as "no forecast".
    """
    df = pd.concat([forecast.rename("har"), bench, realized.rename("rv"),
                    fret.rename("fret")], axis=1)
    df = df[df["har"].notna() & df[list(BENCHMARKS)].notna().all(axis=1) & (df["rv"] > 0)]
    n = int(len(df))
    if n == 0:
        return {"n": 0, "verdict": "parity", "skill": None, "skill_ci": None,
                "degenerate_share": 0.0}
    zero = df["har"] <= 0
    wild = df["har"] > DEGENERATE_RATIO * df["rv22"]
    n_zero, n_wild = int(zero.sum()), int(wild.sum())
    degenerate_share = (n_zero + n_wild) / n

    d = df[~zero]
    rv = d["rv"].to_numpy()
    losses = {"har": qlike(d["har"].to_numpy(), rv)}
    mse = {"har": (d["har"].to_numpy() - rv) ** 2}
    for b in BENCHMARKS:
        losses[b] = qlike(d[b].to_numpy(), rv)
        mse[b] = (d[b].to_numpy() - rv) ** 2

    skill = _skill(losses["har"], losses[BENCHMARK]) if len(d) else None
    ci = block_bootstrap_skill(losses["har"], losses[BENCHMARK]) if len(d) else None

    # The consumers' IID scaling: variance ratio and Gaussian band coverage.
    var_ratio = float(rv.mean() / d["har"].mean()) if len(d) else None
    sig_h = np.sqrt(d["har"].to_numpy() * horizon)
    coverage = {q: float(np.mean(np.abs(d["fret"].to_numpy()) <= z * sig_h))
                for q, z in _Z.items()} if len(d) else {}
    rank = (float(pd.Series(d["har"].to_numpy()).corr(pd.Series(rv), method="spearman"))
            if len(d) > 2 and d["har"].nunique() > 1 else None)

    row = {
        "n": n, "n_loss": int(len(d)), "n_zero": n_zero, "n_wild": n_wild,
        "degenerate_share": round(degenerate_share, 4),
        "first": str(d.index[0].date()) if len(d) else None,
        "last": str(d.index[-1].date()) if len(d) else None,
        "qlike": {k: round(float(v.mean()), 4) for k, v in losses.items()},
        "mse_x1e8": {k: round(float(v.mean()) * 1e8, 4) for k, v in mse.items()},
        "skill": None if skill is None else round(skill, 4),
        "skill_ci": ci,
        "skill_vs": {b: round(_skill(losses["har"], losses[b]), 4) for b in BENCHMARKS},
        "mse_skill": round(_skill(mse["har"], mse[BENCHMARK]), 4) if len(d) else None,
        "rank_corr": None if rank is None else round(rank, 3),
        "var_ratio": None if var_ratio is None else round(var_ratio, 3),
        "coverage": {q: round(v, 3) for q, v in coverage.items()},
    }
    row["verdict"] = verdict(row)
    row["horizon_ok"] = horizon_ok(row)
    return row


def horizon_ok(row: dict) -> bool | None:
    """The pre-registered calibration read of the consumers' IID scaling:
    variance ratio inside VAR_RATIO_BAND and both Gaussian bands inside
    COVERAGE_BAND. None when there is nothing to read."""
    vr, cov = row.get("var_ratio"), row.get("coverage") or {}
    if vr is None or not cov:
        return None
    lo, hi = VAR_RATIO_BAND
    if not (lo <= vr <= hi):
        return False
    return all(COVERAGE_BAND[q][0] <= cov[q] <= COVERAGE_BAND[q][1] for q in COVERAGE_BAND)


# ---------------------------------------------------------------------------
# Per asset, and the two secondary reads
# ---------------------------------------------------------------------------

def score_asset(close: pd.Series, fit_windows=FIT_WINDOWS, horizons=HORIZONS,
                stride: int = 1) -> dict:
    r = log_returns(close)
    bench = trailing_benchmarks(r)
    targets = {h: realized_forward(r, h) for h in horizons}
    out: dict = {"n_returns": int(len(r)), "windows": {}}
    for w in fit_windows:
        fc = walk_forward_har(r, w, stride=stride)
        out["windows"][w] = {h: score_arms(fc, bench, targets[h][0], targets[h][1], h)
                             for h in horizons}
    return out


def wiring_read(results: dict, long_window: int = 1000,
                wired_window: int = WIRED_NOTE_WINDOW, h: int = CONSUMER_HORIZON) -> dict:
    """Secondary read (i): is the fetch period a wiring defect? Yes if the
    long window is `skill` where the wired one is not, on >= WIRING_MIN_ASSETS
    of the published assets."""
    flipped = []
    for a in PUBLISHED:
        w = results.get(a, {}).get("windows", {})
        if long_window not in w or wired_window not in w:
            continue
        if w[long_window][h]["verdict"] == "skill" and w[wired_window][h]["verdict"] != "skill":
            flipped.append(a)
    return {"assets": flipped, "wiring_defect": len(flipped) >= WIRING_MIN_ASSETS}


def horizon_read(results: dict, wired_window: int = WIRED_NOTE_WINDOW) -> dict:
    """Secondary read (ii): at the wired window, which (asset, h) pairs fail
    the IID-scaling calibration bands."""
    out = {}
    for a, res in results.items():
        w = res["windows"].get(wired_window, {})
        out[a] = {h: {"ok": row.get("horizon_ok"), "var_ratio": row.get("var_ratio"),
                      "coverage": row.get("coverage")} for h, row in w.items()}
    return out


# ---------------------------------------------------------------------------
# IO + CLI
# ---------------------------------------------------------------------------

def fetch_closes(start: str = HISTORY_START, tickers: dict[str, str] = TICKERS) -> dict[str, pd.Series]:
    import yfinance as yf
    out = {}
    for key, tk in tickers.items():
        raw = yf.download(tk, start=start, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            print(f"  WARN {key} ({tk}): empty")
            continue
        close = raw["Close"].squeeze().dropna()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        out[key] = close[~close.index.duplicated(keep="last")].sort_index()
        print(f"  {key}: {len(out[key])} closes {out[key].index[0].date()} -> {out[key].index[-1].date()}")
    return out


def _fmt_ci(ci) -> str:
    return "—" if not ci else f"[{ci['lo']:+.3f}, {ci['hi']:+.3f}]"


def print_report(results: dict) -> None:
    print("\n=== WP-17.5 — HAR-RV walk-forward read (QLIKE skill vs rv22; per fit window) ===")
    for a, res in results.items():
        print(f"\n{a}  ({res['n_returns']} returns)")
        print(f"  {'W':>5} {'h':>3} {'n':>5} {'zero':>4} {'wild':>4} | "
              f"{'QL har':>7} {'rv5':>7} {'rv22':>7} {'rv60':>7} {'ewma':>7} | "
              f"{'skill':>7} {'95% CI':>17} {'mse-sk':>7} | {'vr':>5} {'c50':>5} {'c90':>5} | verdict")
        for w, hs in res["windows"].items():
            for h, r in hs.items():
                q = r.get("qlike", {})
                cov = r.get("coverage", {})
                print(f"  {w:>5} {h:>3} {r['n']:>5} {r.get('n_zero',0):>4} {r.get('n_wild',0):>4} | "
                      f"{q.get('har', float('nan')):>7.4f} {q.get('rv5', float('nan')):>7.4f} "
                      f"{q.get('rv22', float('nan')):>7.4f} {q.get('rv60', float('nan')):>7.4f} "
                      f"{q.get('ewma94', float('nan')):>7.4f} | "
                      f"{(r['skill'] if r['skill'] is not None else float('nan')):>+7.3f} "
                      f"{_fmt_ci(r['skill_ci']):>17} "
                      f"{(r.get('mse_skill') if r.get('mse_skill') is not None else float('nan')):>+7.3f} | "
                      f"{(r.get('var_ratio') or float('nan')):>5.2f} "
                      f"{cov.get(0.5, float('nan')):>5.3f} {cov.get(0.9, float('nan')):>5.3f} | "
                      f"{r['verdict']}{'' if r.get('horizon_ok') else '  (horizon: biased)'}")
    wr = wiring_read(results)
    print(f"\nWiring read (1000-day skill where the wired {WIRED_NOTE_WINDOW}-day is not, h={CONSUMER_HORIZON}): "
          f"{wr['assets'] or 'none'} -> {'WIRING DEFECT' if wr['wiring_defect'] else 'not a wiring defect'}")
    print("\nHeadline (wired note window, h=5, published assets):")
    for a in PUBLISHED:
        if a in results:
            r = results[a]["windows"][WIRED_NOTE_WINDOW][CONSUMER_HORIZON]
            print(f"  {a:<8} {r['verdict']:<10} skill {r['skill']:+.3f} {_fmt_ci(r['skill_ci'])}  "
                  f"vr {r['var_ratio']:.2f} c50 {r['coverage'][0.5]:.3f} c90 {r['coverage'][0.9]:.3f}"
                  f"{'' if r['horizon_ok'] else '  horizon: biased'}")


def run_har_read(closes: dict[str, pd.Series] | None = None, fit_windows=FIT_WINDOWS,
                 horizons=HORIZONS, stride: int = 1) -> dict:
    closes = closes or fetch_closes()
    results = {a: score_asset(c, fit_windows, horizons, stride) for a, c in closes.items()}
    print_report(results)
    return results


if __name__ == "__main__":
    import pickle
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if cache and cache.exists():
        closes = pickle.load(open(cache, "rb"))
    else:
        closes = fetch_closes()
        if cache:
            pickle.dump(closes, open(cache, "wb"))
    run_har_read(closes)
