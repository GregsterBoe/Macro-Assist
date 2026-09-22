"""
explore_conditioner.py — EXPLORE-TIER shadow conditioners on the pre-seal slice.

Research harness (product_surface: RESEARCH). Never touches the published table,
the quant log, or `pipeline.yml`. It exists to look — breadth on the explore
slice, counted — at the two register drafts that share one harness:

    H-004  a fragility-state conditioner vs the macro bucket
    H-002  stress → reversion in Normal tapes, continuation in Elevated ones

and to record what was seen in the hypothesis register, not the KB. The read
goes through `score_distributions.verdict(sealed=False)`, which can only return
`exploratory` — the code, not this docstring, is what keeps a look from becoming
a claim (How we explore §1).

The slice
---------
Report dates STRICTLY BEFORE `numeric_baseline.SEAL_START` (2018-01-01), which is
the seal the directional families faced. Whether that seal governs a promoted
distribution hypothesis is todo #19; nothing here reads the sealed side.

The arms
--------
Every arm quotes P25/P50/P75 of the forward change (`assets.forward_change`
units) for each asset × horizon on each report date, from observations whose
window had CLOSED by that date (snapshot i is known at position i + h). Buckets
with fewer than `MIN_N` known observations collapse to the arm's parent, and
finally to `unconditional`, mirroring `conditional.lookup_distribution`.

    unconditional   every known observation since TABLE_START (the benchmark)
    trailing_250    the last 250 known observations
    macro           the published bucket: NFCI tertile × curve sign × BAA10Y
                    tertile, collapse credit → curve → all (the product)
    frag_or         the live OR flag's state on the report date (Elevated /
                    Normal), PIT top-decile per channel, 252-reading warm-up —
                    exactly `fragility_or._pit_backtest`'s flag, daily
    frag_comp       the composite channel's PIT top-decile alone
    frag_or_x_nfci  OR state × NFCI tertile (the cheapest interaction)
    dd_bin          S&P drawdown from its 252-day high, three bins
                    (H-002's dose-response rival: "Elevated" may just be
                    "more stressed")
    dd_x_frag       drawdown bin × OR state (H-002's split itself)

Four arms added 2026-09-21 as the register's next counted looks on H-002 — the
first look saw the width half and not the location half, and both cells mix
day 1 of a selloff with day 40, and a falling tape with a bounced one:

    dd_x_age        drawdown bin × age of the current spell below DD_EDGES[0]:
                    `fresh` (≤ AGE_EDGE trading days) / `old` — the rival
    dd_x_frag_x_age drawdown bin × OR state × spell age (look A)
    dd_x_sign       drawdown bin × sign of the S&P's trailing SIGN_WINDOW-day
                    return (`down5` / `up5`, the window `turbulence_signal`
                    averages over) — the rival
    dd_x_frag_x_sign  drawdown bin × OR state × that sign (look B)

    Prediction written before looking: if the location half failed because
    the stressed ∧ Elevated cell mixes fresh and exhausted stress, then
    `Elevated ∧ fresh` (A) / `Elevated ∧ down5` (B) sits LEFT of the
    unconditional median and `Elevated ∧ old` / `Elevated ∧ up5` RIGHT, and
    the rival without the OR state does not reproduce the split.

Two OPTIONAL arms (the scorer's rule for `har_gaussian`, WP-21.A.2: quoted
where the product would quote them, scored on their own subsample, never a
reason to drop an observation) — H-006's rival, added 2026-09-14 as the
register's next counted look:

    har_gaussian    the product's comparator exactly: zero-mean Normal scaled
                    by the HAR-RV forecast fitted on the last `HAR_WINDOW`
                    closes at or before the report date, through
                    `vol_forecast.har_forecast_or_none`'s gates, for the
                    assets the product logs a forecast for (`HAR_KEYS`);
                    `score_distributions._gaussian_quantiles` does the rest
    har_scaled      the unconditional empirical quantiles with their width
                    rescaled by HAR sigma / the known sample's sd, about the
                    unconditional median — the same vol forecast, the
                    empirical shape and location kept. Splits H-006's width
                    claim from the Gaussian's zero mean

Scoring
-------
Pinball loss on the three quantiles, `skill_vs` = 1 − loss(arm)/loss(benchmark)
on the paired sample, per asset (unit-free) and equal-weight pooled over
`ORIGINAL_KEYS` and over all six. Block bootstrap on 21-report-date blocks,
seed 7, vectorised here because the explore surface is ~2,000 report dates
(the scorer's Python-loop bootstrap is written for ~50). Coverage of the
quoted P25–P75 and the four-bin PIT histogram per arm.

Mechanism checks (the prediction that is not the score)
-------------------------------------------------------
H-004: `frag_or`'s skill split by the state it was in — the gain, if any,
should sit in Elevated and be ~0 in Normal.
H-002: realized forward-change quantiles on the explore slice by
drawdown bin × OR state — width and median side, against the same table by
drawdown bin alone; then (2026-09-21) the stressed cells split by spell age
and by the sign of the trailing 5-day return, each beside its rival, with the
number of distinct stress spells in every cell.
H-006: on the subsample where `har_gaussian` quotes, `dd_bin` scored against
the HAR arms as benchmark (does the drawdown bin add anything a vol forecast
does not already carry?), and the mean quoted P25–P75 width of each arm by the
drawdown bin the report date was in (does HAR narrow in calm as `dd_bin` does?).

Run
---
    python explore_conditioner.py                # fetch, cache, score, report
    python explore_conditioner.py --cached       # reuse the cached inputs

Writes `results/explore_conditioner/{report.md, summary.json}` and caches the
fetched inputs under the same directory (`inputs.pkl`).
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from assets import ASSETS, BY_KEY, HORIZONS, ORIGINAL_KEYS
from conditional import TABLE_START, assign_bucket, _bucket_drop_credit, _bucket_drop_yc
from fragility_or import build_channels, _Q, _MIN_WARMUP, _CH_KEYS
from numeric_baseline import SEAL_START, DRAWDOWN_WINDOW
from score_distributions import (
    BLOCK_DAYS, N_BOOT, SEED, MIN_POOL_BLOCKS, TRADING_DAYS_PER_YEAR, _VOL_LOG_KEYS,
    _gaussian_quantiles, pinball_loss, pit_bin, skill_vs, verdict,
)
from vol_forecast import har_forecast_or_none

_HERE = Path(__file__).resolve().parent
RESULTS_DIR = _HERE.parent / "results" / "explore_conditioner"

MIN_N = 10                      # conditional.build_distribution_table's default
QUANTILES = (0.25, 0.50, 0.75)
BURN_IN = 252                   # report dates skipped after the flag's first reading
DD_EDGES = (-0.05, -0.10)       # drawdown bins: > −5% | −5..−10% | < −10%
AGE_EDGE = 10                   # a spell below DD_EDGES[0] is `fresh` for its first 10 trading days
SIGN_WINDOW = 5                 # the trailing S&P return whose sign labels the tape (turbulence's window)

ARMS = ("unconditional", "trailing_250", "macro", "frag_or", "frag_comp",
        "frag_or_x_nfci", "dd_bin", "dd_x_frag",
        "dd_x_age", "dd_x_frag_x_age", "dd_x_sign", "dd_x_frag_x_sign")
OPTIONAL_ARMS = ("har_gaussian", "har_scaled")      # quoted where available, own subsample
ALL_ARMS = ARMS + OPTIONAL_ARMS
BENCH = "unconditional"

HAR_WINDOW = 1250               # ≈ the product's 5y close history (market_data.VOL_HISTORY_PERIOD)
HAR_KEYS = frozenset(_VOL_LOG_KEYS)   # the assets the product logs a HAR forecast for


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def fetch_inputs() -> dict:
    """Prices from TABLE_START, the bucket's FRED series, the three fragility
    channels walked DAILY (stride 1 — the live path strides by 5 and this is
    the one place the harness departs from it, so a conditioner can be keyed
    on every report date)."""
    from fredapi import Fred
    from refit_models import _fetch_fred_series, _fetch_price_history

    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise SystemExit("FRED_API_KEY not set")
    prices = _fetch_price_history(TABLE_START)
    fred = _fetch_fred_series(Fred(api_key=key), TABLE_START)
    ch = build_channels(start="2008-01-01", etf_start="2007-01-01", stride=1, refresh=True)
    channels = {k: ch[k] for k in _CH_KEYS}
    return {"prices": prices, "fred": fred, "channels": channels,
            "fetched": date.today().isoformat()}


def pit_flags(channels: dict, q: float = _Q, min_warmup: int = _MIN_WARMUP) -> pd.DataFrame:
    """Per-day PIT flags, the `_pit_backtest` loop returned as a frame: a day is
    evaluable once every channel has `min_warmup` finite prior readings; each
    channel fires when its reading is at/above the q-quantile of those priors."""
    common = channels["comp"].index
    for k in _CH_KEYS:
        common = common.intersection(channels[k].index)
    arrs = {k: channels[k].reindex(common).to_numpy(dtype=float) for k in _CH_KEYS}
    rows = []
    for i in range(len(common)):
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
        rows.append({"date": common[i], **fires, "or": any(fires.values())})
    return pd.DataFrame(rows).set_index("date")


# ---------------------------------------------------------------------------
# Panel: one row per business day, labels for every arm, forward changes
# ---------------------------------------------------------------------------

def build_panel(inputs: dict) -> tuple[pd.DataFrame, dict[str, dict[int, np.ndarray]]]:
    """Business-day frame from TABLE_START to the last close, with the macro
    bucket (strict — a date missing an input is NaN, never 'mid'), the OR /
    composite states where evaluable, the S&P drawdown bin; plus forward
    changes `fr[asset][h]` aligned to the frame (NaN where the window has not
    closed, exactly `refit_models._build_forward_returns`)."""
    from refit_models import _build_forward_returns, _build_snapshot_stubs, _table_dates

    prices, fred = inputs["prices"], inputs["fred"]
    dates = _table_dates(fred, prices)
    stubs, _dropped = _build_snapshot_stubs(fred, dates)
    bucket = pd.Series({pd.Timestamp(d): assign_bucket(s, strict=True) for d, s in stubs})

    frame = pd.DataFrame(index=dates)
    frame["bucket"] = bucket.reindex(dates)
    frame["nfci"] = frame["bucket"].map(lambda b: _bucket_drop_yc(_bucket_drop_credit(b))
                                        if isinstance(b, str) else None)

    flags = pit_flags(inputs["channels"])
    frame["or_state"] = flags["or"].reindex(dates).map({True: "Elevated", False: "Normal"})
    frame["comp_state"] = flags["comp"].reindex(dates).map({True: "Elevated", False: "Normal"})

    sp = prices["SP500"].reindex(dates, method="ffill")
    dd = sp / sp.rolling(DRAWDOWN_WINDOW).max() - 1.0
    frame["drawdown"] = dd
    frame["dd_bin"] = pd.cut(dd, bins=[-np.inf, DD_EDGES[1], DD_EDGES[0], np.inf],
                             labels=["dd<-10", "dd-5..-10", "dd>-5"]).astype(object)
    frame["dd_stressed"] = np.where(dd.isna(), None, np.where(dd <= DD_EDGES[0], "dd<=-5", "dd>-5"))
    spell_id, age = stress_spells(dd)
    frame["spell_id"] = spell_id
    frame["dd_age"] = np.where(dd.isna(), None,
                               np.where(age == 0, "calm", np.where(age <= AGE_EDGE, "fresh", "old")))
    r = sp.pct_change(SIGN_WINDOW)
    frame["sp_sign"] = np.where(r.isna(), None, np.where(r < 0, "down5", "up5"))

    raw = _build_forward_returns(prices, dates)
    fr: dict[str, dict[int, np.ndarray]] = {}
    pos = {ts: i for i, ts in enumerate(dates)}
    for a in ASSETS:
        fr[a.key] = {}
        for h in HORIZONS:
            arr = np.full(len(dates), np.nan)
            for d, per_h in raw.get(a.key, {}).items():
                if h in per_h:
                    arr[pos[pd.Timestamp(d)]] = per_h[h]
            fr[a.key][h] = arr
    return frame, fr


def stress_spells(dd: pd.Series, edge: float = DD_EDGES[0]) -> tuple[np.ndarray, np.ndarray]:
    """Run-length structure of the drawdown series: `spell_id` numbers each
    maximal run of days with dd ≤ `edge` (NaN outside one), `age` is the
    position within the run in trading days (1 on its first day, 0 outside)."""
    stressed = (dd <= edge).to_numpy()
    n = len(stressed)
    spell = np.full(n, np.nan)
    age = np.zeros(n, dtype=int)
    k = 0
    for i in range(n):
        if not stressed[i]:
            continue
        if i == 0 or not stressed[i - 1]:
            k += 1
            age[i] = 1
        else:
            age[i] = age[i - 1] + 1
        spell[i] = k
    return spell, age


def arm_labels(frame: pd.DataFrame) -> dict[str, list[np.ndarray]]:
    """Each arm as a collapse ladder: a list of label arrays, most specific
    first, ending in the all-ones array (= unconditional). A None label means
    the level is undefined on that date; the quote falls through."""
    n = len(frame)
    every = np.array(["all"] * n, dtype=object)

    def col(name: str) -> np.ndarray:
        return frame[name].to_numpy(dtype=object)

    def combine(*cols: np.ndarray) -> np.ndarray:
        out = np.empty(n, dtype=object)
        for i in range(n):
            parts = [c[i] for c in cols]
            out[i] = None if any(p is None or (isinstance(p, float) and np.isnan(p))
                                 for p in parts) else "|".join(parts)
        return out

    bucket = col("bucket")
    parent = np.array([_bucket_drop_credit(b) if isinstance(b, str) else None
                       for b in bucket], dtype=object)
    grand = col("nfci")
    or_s, comp_s, dd = col("or_state"), col("comp_state"), col("dd_bin")
    age, sign = col("dd_age"), col("sp_sign")
    return {
        "unconditional":  [every],
        "trailing_250":   [every],                         # handled by window
        "macro":          [bucket, parent, grand, every],
        "frag_or":        [or_s, every],
        "frag_comp":      [comp_s, every],
        "frag_or_x_nfci": [combine(or_s, grand), or_s, every],
        "dd_bin":         [dd, every],
        "dd_x_frag":      [combine(dd, or_s), dd, every],
        "dd_x_age":       [combine(dd, age), dd, every],
        "dd_x_frag_x_age": [combine(dd, or_s, age), combine(dd, or_s), dd, every],
        "dd_x_sign":      [combine(dd, sign), dd, every],
        "dd_x_frag_x_sign": [combine(dd, or_s, sign), combine(dd, or_s), dd, every],
    }


def har_sigma(closes: pd.Series, asof: pd.Timestamp, window: int = HAR_WINDOW) -> float | None:
    """The product's HAR-RV forecast as of `asof`: annualised vol (percent) from
    the last `window` closes AT OR BEFORE `asof`, log returns, through
    `har_forecast_or_none`'s gates (≥ HAR_MIN_RETURNS returns, positive
    forecast). None where the product would print no forecast."""
    hist = closes.loc[:asof].to_numpy(dtype=float)[-window:]
    if len(hist) < 2:
        return None
    rets = pd.Series(np.log(hist[1:] / hist[:-1]))
    fc = har_forecast_or_none(rets)
    return None if fc is None else float(fc["forecast_daily_vol"])


def har_sigmas(prices: dict[str, pd.Series], dates: pd.DatetimeIndex,
               first: int, stop: int, keys=HAR_KEYS) -> dict[str, np.ndarray]:
    """`sigmas[asset][t]` = `har_sigma` on report date `dates[t]` for
    first <= t < stop, NaN elsewhere and for assets outside `keys`."""
    out = {}
    for key in keys:
        if key not in prices:
            continue
        arr = np.full(len(dates), np.nan)
        for t in range(first, min(stop, len(dates))):
            s = har_sigma(prices[key], dates[t])
            if s is not None:
                arr[t] = s
        out[key] = arr
    return out


def har_scaled_quantiles(uncond: dict[float, float], sigma_annual_pct: float, horizon: int,
                         asset, known_sd: float) -> dict[float, float] | None:
    """The unconditional empirical quantiles, width rescaled by the HAR
    forecast: q' = median + (q − median) × sigma_h / sd(known). None for a
    level asset (the HAR vol is a percent-return vol; same refusal as
    `_gaussian_quantiles`) or a degenerate sample."""
    if asset.is_level or sigma_annual_pct <= 0 or not np.isfinite(known_sd) or known_sd <= 0:
        return None
    r = sigma_annual_pct * np.sqrt(horizon / TRADING_DAYS_PER_YEAR) / known_sd
    med = uncond[0.50]
    return {q: float(med + (v - med) * r) for q, v in uncond.items()}


# ---------------------------------------------------------------------------
# Quoting and scoring
# ---------------------------------------------------------------------------

def _quote(vals: np.ndarray) -> dict[float, float]:
    return {q: float(np.percentile(vals, q * 100)) for q in QUANTILES}


def _score_arm(quantiles: dict[float, float], realized: float, level: str, n: int) -> dict:
    per_q = {str(k): pinball_loss(realized, v, k) for k, v in quantiles.items()}
    return {
        "pinball": per_q,
        "pinball_mean": float(np.mean(list(per_q.values()))),
        "quantiles": quantiles,
        "level": level, "n": n,
        "inside_iqr": bool(quantiles[0.25] <= realized <= quantiles[0.75]),
        "pit_bin": pit_bin(realized, quantiles),
        "width": quantiles[0.75] - quantiles[0.25],
    }


def report_range(frame: pd.DataFrame, seal: date = SEAL_START) -> tuple[int, int]:
    """[first, stop) positions of the explore-slice report dates: BURN_IN
    readings after the first evaluable OR flag, strictly before the seal."""
    evaluable = np.where(frame["or_state"].notna().to_numpy())[0]
    if len(evaluable) == 0:
        raise RuntimeError("no evaluable OR flag dates")
    first = int(evaluable[0] + BURN_IN)
    stop = int(np.searchsorted(frame.index.to_numpy(), np.datetime64(pd.Timestamp(seal))))
    return first, stop


def quote_arm(ladder: list[np.ndarray], fr_h: np.ndarray, t: int, h: int,
              window: int | None = None) -> tuple[dict[float, float], str, int] | None:
    """The arm's quantiles on report date `t` for one asset × horizon, from
    observations known at t (i + h <= t), walking the collapse ladder until a
    level has MIN_N. Returns (quantiles, level_label, n) or None."""
    last = t - h
    if last < 0:
        return None
    known = fr_h[:last + 1]
    finite = np.isfinite(known)
    for level in ladder:
        lab = level[t]
        if lab is None or (isinstance(lab, float) and np.isnan(lab)):
            continue
        mask = finite & (level[:last + 1] == lab)
        vals = known[mask]
        if window is not None:
            vals = vals[-window:]
        if len(vals) >= MIN_N:
            return _quote(vals), str(lab), int(len(vals))
    return None


def build_observations(frame: pd.DataFrame, fr: dict, ladders: dict,
                       seal: date = SEAL_START,
                       sigmas: dict[str, np.ndarray] | None = None) -> list[dict]:
    """One observation per (report date, asset, horizon) on the explore slice,
    every arm in ARMS quoting or the observation is dropped (sample alignment,
    WP-21.A.2). Report dates start BURN_IN readings after the first evaluable
    OR flag. `sigmas` (from `har_sigmas`) adds the OPTIONAL_ARMS where a HAR
    forecast exists; their absence never drops an observation."""
    dates = frame.index
    first, stop = report_range(frame, seal)
    sigmas = sigmas or {}
    obs: list[dict] = []
    for t in range(first, min(stop, len(dates))):
        ts = dates[t]
        if not isinstance(frame["or_state"].iat[t], str) or not isinstance(frame["bucket"].iat[t], str):
            continue
        for a in ASSETS:
            sig = sigmas[a.key][t] if a.key in sigmas else np.nan
            for h in HORIZONS:
                realized = fr[a.key][h][t]
                if not np.isfinite(realized):
                    continue
                arms: dict[str, dict] = {}
                for arm in ARMS:
                    q = quote_arm(ladders[arm], fr[a.key][h], t, h,
                                  window=250 if arm == "trailing_250" else None)
                    if q is None:
                        break
                    quantiles, level, n = q
                    arms[arm] = _score_arm(quantiles, realized, level, n)
                if len(arms) < len(ARMS):
                    continue
                if np.isfinite(sig):
                    gq = _gaussian_quantiles(float(sig), h, a)
                    if gq:
                        arms["har_gaussian"] = _score_arm(gq, realized, "har", HAR_WINDOW)
                    known = fr[a.key][h][:t - h + 1]
                    sq = har_scaled_quantiles(arms[BENCH]["quantiles"], float(sig), h, a,
                                              float(np.nanstd(known)))
                    if sq:
                        arms["har_scaled"] = _score_arm(sq, realized, "har", arms[BENCH]["n"])
                obs.append({
                    "date": ts.date().isoformat(), "asset": a.key, "horizon": h,
                    "unit": a.unit, "realized": float(realized),
                    "or_state": frame["or_state"].iat[t],
                    "comp_state": frame["comp_state"].iat[t],
                    "dd_bin": frame["dd_bin"].iat[t],
                    "bucket": frame["bucket"].iat[t],
                    "arms": arms,
                })
    return obs


# --- a vectorised copy of the scorer's block bootstrap -----------------------

def _block_ids(obs: list[dict]) -> np.ndarray:
    dates = sorted({o["date"] for o in obs})
    blk = {d: i // BLOCK_DAYS for i, d in enumerate(dates)}
    return np.array([blk[o["date"]] for o in obs])


def skill_ci(obs: list[dict], arm: str, benchmark: str = BENCH,
             n_boot: int = N_BOOT, seed: int = SEED) -> dict | None:
    """Block-bootstrap CI of `skill_vs` — whole 21-report-date blocks resampled
    with replacement, the same design as `score_distributions.block_bootstrap`,
    vectorised over the loss arrays so ~10k observations × 2000 draws is
    seconds, not minutes."""
    paired = [o for o in obs if arm in o["arms"] and benchmark in o["arms"]]
    if not paired:
        return None
    la = np.array([o["arms"][arm]["pinball_mean"] for o in paired])
    lb = np.array([o["arms"][benchmark]["pinball_mean"] for o in paired])
    blk = _block_ids(paired)
    nb = blk.max() + 1
    if nb < 2:
        return None
    sa = np.bincount(blk, weights=la, minlength=nb)
    sb = np.bincount(blk, weights=lb, minlength=nb)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nb, size=(n_boot, nb))
    num = sa[draws].sum(axis=1)
    den = sb[draws].sum(axis=1)
    ok = den > 0
    sk = 1.0 - num[ok] / den[ok]
    lo, hi = np.percentile(sk, [2.5, 97.5])
    return {"lo": round(float(lo), 4), "hi": round(float(hi), 4),
            "n_boot": int(ok.sum()), "n_blocks": int(nb)}


def pooled(obs: list[dict], arm: str, keys, benchmark: str = BENCH,
           n_boot: int = N_BOOT, seed: int = SEED) -> dict | None:
    """Equal-weight per-asset skill, `score_distributions.pooled_skill`'s design
    (qualifying set fixed on the real sample; bootstrap re-pools exactly those
    assets on shared blocks) with the vectorised resample."""
    obs = [o for o in obs if arm in o["arms"] and benchmark in o["arms"]]
    if not obs:
        return None
    qualifying = []
    for a in ASSETS:
        if a.key not in keys:
            continue
        sub = [o for o in obs if o["asset"] == a.key]
        if not sub:
            continue
        nb = len({o["date"] for o in sub}) // BLOCK_DAYS + 1
        if nb < MIN_POOL_BLOCKS or skill_vs(sub, arm, benchmark) is None:
            continue
        qualifying.append(a.key)
    if not qualifying:
        return None
    blk_all = _block_ids(obs)
    nb = blk_all.max() + 1
    per_asset_sums = []
    for k in qualifying:
        idx = np.array([i for i, o in enumerate(obs) if o["asset"] == k])
        la = np.array([obs[i]["arms"][arm]["pinball_mean"] for i in idx])
        lb = np.array([obs[i]["arms"][benchmark]["pinball_mean"] for i in idx])
        per_asset_sums.append((np.bincount(blk_all[idx], weights=la, minlength=nb),
                               np.bincount(blk_all[idx], weights=lb, minlength=nb)))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nb, size=(n_boot, nb))
    sk = np.zeros(n_boot)
    for sa, sb in per_asset_sums:
        num, den = sa[draws].sum(axis=1), sb[draws].sum(axis=1)
        sk += 1.0 - num / np.where(den > 0, den, np.nan)
    sk = sk / len(per_asset_sums)
    sk = sk[np.isfinite(sk)]
    point = float(np.mean([skill_vs([o for o in obs if o["asset"] == k], arm, benchmark)
                           for k in qualifying]))
    lo, hi = np.percentile(sk, [2.5, 97.5])
    return {"skill": round(point, 4), "ci": {"lo": round(float(lo), 4), "hi": round(float(hi), 4),
                                             "n_boot": int(len(sk)), "n_blocks": int(nb)},
            "assets": qualifying}


def coverage(obs: list[dict], arm: str) -> float | None:
    v = [o["arms"][arm]["inside_iqr"] for o in obs if arm in o["arms"]]
    return round(float(np.mean(v)), 4) if v else None


def pit_hist(obs: list[dict], arm: str) -> dict[str, float]:
    c: dict[int, int] = defaultdict(int)
    n = 0
    for o in obs:
        if arm in o["arms"]:
            c[o["arms"][arm]["pit_bin"]] += 1
            n += 1
    return {str(b): round(c[b] / n, 3) for b in range(4)} if n else {}


def summarize_arm(obs: list[dict], arm: str, horizon: int) -> dict:
    """The arm's read at one horizon, on the observations it quoted (an optional
    arm's subsample is smaller than the slice; `n_report_dates` says so)."""
    sub = [o for o in obs if o["horizon"] == horizon and arm in o["arms"]]
    dates = sorted({o["date"] for o in sub})
    out = {
        "arm": arm, "horizon": horizon, "n": len(sub), "n_report_dates": len(dates),
        "n_blocks": (len(dates) + BLOCK_DAYS - 1) // BLOCK_DAYS,
        "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
        "coverage_iqr": coverage(sub, arm), "pit_histogram": pit_hist(sub, arm),
        "per_asset": {}, "pooled_skill": pooled(sub, arm, ORIGINAL_KEYS),
        "pooled_skill_all_assets": pooled(sub, arm, {a.key for a in ASSETS}),
    }
    for a in ASSETS:
        s = [o for o in sub if o["asset"] == a.key]
        sk = skill_vs(s, arm, BENCH)
        if sk is None:
            continue
        out["per_asset"][a.key] = {"skill": round(sk, 4), "n": len(s),
                                   "ci": skill_ci(s, arm), "coverage": coverage(s, arm)}
    if not out["per_asset"]:
        out["pooled_skill"] = out["pooled_skill_all_assets"] = None
    out["verdict"] = verdict(out, sealed=False)     # can only be `exploratory`
    return out


# ---------------------------------------------------------------------------
# Mechanism checks
# ---------------------------------------------------------------------------

def skill_by_state(obs: list[dict], arm: str, state_key: str, horizon: int) -> dict:
    """H-004's structure check: the arm's skill vs the benchmark restricted to
    the report dates in each state. Pooled over all six assets, equal weight."""
    out = {}
    for state in sorted({o[state_key] for o in obs if o[state_key] is not None}):
        sub = [o for o in obs if o["horizon"] == horizon and o[state_key] == state]
        if not sub:
            continue
        out[state] = {"n": len(sub), "n_report_dates": len({o["date"] for o in sub}),
                      "pooled": pooled(sub, arm, {a.key for a in ASSETS})}
        for a in ORIGINAL_KEYS:
            s = [o for o in sub if o["asset"] == a]
            out[state][a] = round(skill_vs(s, arm, BENCH), 4) if s else None
    return out


def skill_by_level(obs: list[dict], arm: str, horizon: int) -> dict:
    """H-005's structure check: the arm's skill on the report dates where it
    quoted from each collapse level (full bucket / parent / grandparent /
    'all'). A deficit that lives in the specific levels and vanishes at 'all'
    is over-conditioning; one that lives at the grandparent is the dimension
    itself."""
    sub = [o for o in obs if o["horizon"] == horizon]
    out = {}
    for lvl in ("full", "parent", "grand", "all"):
        def _is(o):
            lab = o["arms"][arm]["level"]
            depth = lab.count("|")
            return (lvl == "all" and lab == "all") or (lvl == "full" and depth == 2) \
                or (lvl == "parent" and depth == 1) or (lvl == "grand" and depth == 0 and lab != "all")
        s = [o for o in sub if _is(o)]
        if not s:
            continue
        out[lvl] = {"n_report_dates": len({o["date"] for o in s}),
                    "pooled_all_6": pooled(s, arm, {a.key for a in ASSETS}),
                    "SP500": round(skill_vs([o for o in s if o["asset"] == "SP500"], arm, BENCH) or 0, 4)}
    return out


def skill_by_year(obs: list[dict], arm: str, asset: str, horizon: int) -> dict:
    """Is a skill number spread over the tape or carried by two or three
    episodes? Per calendar year, one asset, point estimate only."""
    out = {}
    for y in sorted({o["date"][:4] for o in obs}):
        s = [o for o in obs if o["horizon"] == horizon and o["asset"] == asset and o["date"].startswith(y)]
        sk = skill_vs(s, arm, BENCH) if s else None
        if sk is not None:
            out[y] = {"n": len(s), "skill": round(sk, 4),
                      "share_elevated": round(float(np.mean([o["or_state"] == "Elevated" for o in s])), 3),
                      "share_dd_below_5": round(float(np.mean([o["dd_bin"] != "dd>-5" for o in s])), 3)}
    return out


def har_rival(obs: list[dict], horizon: int, keys=ORIGINAL_KEYS) -> dict:
    """H-006's structure check, on the subsample where `har_gaussian` quotes:
    `dd_bin` and the two HAR arms each vs `unconditional`, and `dd_bin` vs each
    HAR arm as benchmark — per asset with a block-bootstrap CI, and pooled
    equal-weight over `keys`. If the drawdown bin's gain is the vol forecast's
    gain, its skill vs the HAR arm is ~0 or negative."""
    sub = [o for o in obs if o["horizon"] == horizon and "har_gaussian" in o["arms"]]
    pairs = (("dd_bin", BENCH), ("har_gaussian", BENCH), ("har_scaled", BENCH),
             ("dd_bin", "har_gaussian"), ("dd_bin", "har_scaled"), ("trailing_250", "har_scaled"))
    out = {"n_report_dates": len({o["date"] for o in sub}), "pairs": {}}
    for arm, bench in pairs:
        name = f"{arm} vs {bench}"
        row = {"pooled": pooled(sub, arm, keys, benchmark=bench)}
        for a in ASSETS:
            s = [o for o in sub if o["asset"] == a.key and arm in o["arms"] and bench in o["arms"]]
            sk = skill_vs(s, arm, bench) if s else None
            if sk is not None:
                row[a.key] = {"skill": round(sk, 4), "ci": skill_ci(s, arm, benchmark=bench)}
        out["pairs"][name] = row
    return out


def width_by_bin(obs: list[dict], asset: str, horizon: int,
                 arms=(BENCH, "trailing_250", "dd_bin", "har_gaussian", "har_scaled")) -> dict:
    """Mean quoted P25–P75 width per arm by the drawdown bin the report date was
    in, one asset, on the subsample where every listed arm quoted. Does the vol
    forecast narrow in calm the way the drawdown bin does?"""
    sub = [o for o in obs if o["asset"] == asset and o["horizon"] == horizon
           and all(a in o["arms"] for a in arms)]
    out = {}
    for b in sorted({o["dd_bin"] for o in sub}):
        s = [o for o in sub if o["dd_bin"] == b]
        out[b] = {"n_report_dates": len(s),
                  **{a: round(float(np.mean([o["arms"][a]["width"] for o in s])), 3) for a in arms},
                  "realized_iqr": round(float(np.subtract(*np.percentile([o["realized"] for o in s], [75, 25]))), 3)}
    return out


def realized_by_cell(frame: pd.DataFrame, fr: dict, asset: str, horizon: int,
                     keys: list[str], seal: date = SEAL_START,
                     where: pd.Series | None = None) -> pd.DataFrame:
    """H-002's structure check: realized forward-change quantiles on the explore
    slice, grouped by the given frame columns. Width = P75 − P25; 'side' is the
    median relative to the slice's unconditional median — the WHOLE slice's,
    also when `where` restricts the rows tabulated. `spells` counts the
    distinct runs below DD_EDGES[0] in the cell: n = 70 can be two episodes."""
    ts = frame.index
    mask = (ts < pd.Timestamp(seal)) & frame["or_state"].notna().to_numpy()
    vals = fr[asset][horizon]
    med_all = float(np.nanmedian(vals[mask]))
    if where is not None:
        mask = mask & where.reindex(frame.index).fillna(False).to_numpy(dtype=bool)
    df = frame.loc[mask, keys + ["spell_id"]].copy()
    df["y"] = vals[mask]
    df = df.dropna(subset=keys + ["y"])
    g = df.groupby(keys, observed=True)
    out = pd.DataFrame({
        "n": g["y"].size(), "spells": g["spell_id"].nunique(),
        "p25": g["y"].quantile(0.25), "p50": g["y"].median(), "p75": g["y"].quantile(0.75),
    })
    out["width"] = out["p75"] - out["p25"]
    out["side"] = np.where(out["p50"] > med_all, "right", "left")
    out["uncond_p50"] = med_all
    return out.round(3)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _md_table(df: pd.DataFrame) -> str:
    """A plain markdown table (no `tabulate` dependency)."""
    d = df.reset_index()
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "|" + "---|" * len(d.columns)
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def _ci(ci: dict | None) -> str:
    return f"[{ci['lo']:+.3f}, {ci['hi']:+.3f}]" if ci else "n/a"


def report_md(summary: dict, cells: dict[str, pd.DataFrame], meta: dict) -> str:
    L = [f"# Explore-tier shadow conditioners — pre-seal slice",
         "",
         f"**Slice:** report dates {meta['first_date']} → {meta['last_date']} "
         f"(< `SEAL_START` {SEAL_START}) · {meta['n_report_dates']} report dates · "
         f"{meta['n_obs']} observations · inputs fetched {meta['fetched']}",
         f"**Verdict on every arm:** `exploratory` — `verdict(sealed=False)`; nothing here can pass.",
         f"**Multiplicity:** {len(ALL_ARMS) - 1} arms ({len(OPTIONAL_ARMS)} optional, own subsample) × "
         f"{len(HORIZONS)} horizons × {len(ASSETS)} assets looked at, all reported.",
         "",
         "## Skill vs `unconditional` (pinball, P25/P50/P75), pooled equal-weight",
         "",
         "| arm | h | n dates | pooled (SP500/Gold/WTI) | 95% CI | pooled (all 6) | 95% CI | coverage P25–P75 |",
         "|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        for arm in ALL_ARMS:
            if arm == BENCH:
                continue
            s = summary[str(h)][arm]
            p, pa = s["pooled_skill"], s["pooled_skill_all_assets"]
            if not p:
                L.append(f"| `{arm}` | {h} | {s['n_report_dates']} | n/a | n/a | n/a | n/a | n/a |")
                continue
            L.append(f"| `{arm}` | {h} | {s['n_report_dates']} | {p['skill']:+.4f} | {_ci(p['ci'])} | "
                     f"{pa['skill']:+.4f} | {_ci(pa['ci'])} | {s['coverage_iqr']:.3f} |")
    L += ["", "## Per-asset skill vs `unconditional`", "",
          "Optional arms (`har_*`) score on their own subsample — the assets the product "
          "logs a HAR forecast for, where the 1000-return gate passes — so their "
          "'pooled (all 6)' above is over the assets that qualified, not six.", ""]
    L.append("| arm | h | " + " | ".join(a.key for a in ASSETS) + " |")
    L.append("|---|---|" + "---|" * len(ASSETS))
    for h in HORIZONS:
        for arm in ALL_ARMS:
            if arm == BENCH:
                continue
            s = summary[str(h)][arm]["per_asset"]
            cells_ = []
            for a in ASSETS:
                v = s.get(a.key)
                cells_.append(f"{v['skill']:+.3f} {_ci(v['ci'])}" if v else "—")
            L.append(f"| `{arm}` | {h} | " + " | ".join(cells_) + " |")
    L += ["", "## H-004 structure check — `frag_or` skill by the state it was in", "",
          "| h | state | n dates | pooled all 6 | 95% CI | SP500 | Gold | WTI |", "|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        for state, v in summary["by_state"][str(h)].items():
            p = v["pooled"]
            L.append(f"| {h} | {state} | {v['n_report_dates']} | {p['skill']:+.4f} | {_ci(p['ci'])} | "
                     f"{v.get('SP500', float('nan')):+.3f} | {v.get('Gold', float('nan')):+.3f} | "
                     f"{v.get('WTI Oil', float('nan')):+.3f} |")
    L += ["", "## Where `dd_bin`'s gain lives — skill by the drawdown bin it was in", "",
          "| h | bin | n dates | pooled all 6 | 95% CI | SP500 | Gold | WTI |", "|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        for state, v in summary["dd_by_bin"][str(h)].items():
            p = v["pooled"]
            L.append(f"| {h} | {state} | {v['n_report_dates']} | {p['skill']:+.4f} | {_ci(p['ci'])} | "
                     f"{v.get('SP500', float('nan')):+.3f} | {v.get('Gold', float('nan')):+.3f} | "
                     f"{v.get('WTI Oil', float('nan')):+.3f} |")
    L += ["", "## Where `macro`'s deficit lives — skill by the collapse level it quoted from", "",
          "| h | level | n dates | pooled all 6 | 95% CI | SP500 |", "|---|---|---|---|---|---|"]
    for h in HORIZONS:
        for lvl, v in summary["macro_by_level"][str(h)].items():
            p = v["pooled_all_6"]
            L.append(f"| {h} | {lvl} | {v['n_report_dates']} | "
                     f"{(p['skill'] if p else float('nan')):+.4f} | {_ci(p['ci']) if p else 'n/a'} | {v['SP500']:+.3f} |")
    L += ["", "## Is the S&P skill spread over the tape? — per year, h=5 and h=10", "",
          "| year | n | `dd_bin` h5 | `dd_bin` h10 | `macro` h5 | `macro` h10 | `frag_or` h5 | share Elevated | share dd<−5% |",
          "|---|---|---|---|---|---|---|---|---|"]
    by = summary["by_year"]
    for y in by["dd_bin"]["5"]:
        r = by["dd_bin"]["5"][y]
        L.append(f"| {y} | {r['n']} | {r['skill']:+.3f} | {by['dd_bin']['10'][y]['skill']:+.3f} | "
                 f"{by['macro']['5'][y]['skill']:+.3f} | {by['macro']['10'][y]['skill']:+.3f} | "
                 f"{by['frag_or']['5'][y]['skill']:+.3f} | {r['share_elevated']:.2f} | {r['share_dd_below_5']:.2f} |")
    L += ["", "## H-006 rival check — does the HAR forecast already carry `dd_bin`'s gain?", "",
          "On the subsample where `har_gaussian` quotes. `a vs b` = skill of arm a with b as benchmark. "
          "If the drawdown bin's gain is the vol forecast's gain, `dd_bin vs har_*` is ~0 or negative.", "",
          "| h | n dates | pair | pooled (SP500/Gold/WTI) | 95% CI | SP500 | 95% CI | Gold | WTI |",
          "|---|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        r = summary["har_rival"][str(h)]
        for name, row in r["pairs"].items():
            p = row["pooled"]
            sp = row.get("SP500")
            L.append(f"| {h} | {r['n_report_dates']} | `{name}` | "
                     f"{(p['skill'] if p else float('nan')):+.4f} | {_ci(p['ci']) if p else 'n/a'} | "
                     f"{(sp['skill'] if sp else float('nan')):+.3f} | {_ci(sp['ci']) if sp else 'n/a'} | "
                     f"{(row['Gold']['skill'] if row.get('Gold') else float('nan')):+.3f} | "
                     f"{(row['WTI Oil']['skill'] if row.get('WTI Oil') else float('nan')):+.3f} |")
    L += ["", "### Mean quoted P25–P75 width by drawdown bin — SP500", "",
          "Does the vol forecast narrow in calm the way the drawdown bin does? `realized_iqr` is the "
          "realized forward change's IQR in that bin on the same dates.", "",
          "| h | bin | n dates | `unconditional` | `trailing_250` | `dd_bin` | `har_gaussian` | `har_scaled` | realized IQR |",
          "|---|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        for b, v in summary["width_by_bin"][str(h)].items():
            L.append(f"| {h} | {b} | {v['n_report_dates']} | {v['unconditional']:.3f} | {v['trailing_250']:.3f} | "
                     f"{v['dd_bin']:.3f} | {v['har_gaussian']:.3f} | {v['har_scaled']:.3f} | {v['realized_iqr']:.3f} |")
    L += ["", "## H-002 structure check — S&P realized forward change by drawdown bin × OR state", "",
          "Width = P75 − P25 (pct). `side` = median vs the slice's unconditional median. "
          "The dose-response rival (drawdown bin alone) follows each table. `spells` = distinct "
          "runs below −5% in the cell. Looks A and B (2026-09-21) split the stressed cells by "
          f"spell age (`fresh` ≤ {AGE_EDGE} trading days) and by the sign of the trailing "
          f"{SIGN_WINDOW}-day S&P return; each has its rival without the OR state beside it.", ""]
    for name, df in cells.items():
        L += [f"### {name}", "", _md_table(df), ""]
    L += ["## Reproduce", "", "```", "cd .macro-assist && python explore_conditioner.py --cached",
          "```", "", "Inputs: `refit_models._fetch_price_history(TABLE_START)`, "
          "`refit_models._fetch_fred_series`, `fragility_or.build_channels(stride=1)`; "
          f"flags `pit_flags(q={_Q}, min_warmup={_MIN_WARMUP})`; MIN_N={MIN_N}; "
          f"BURN_IN={BURN_IN}; DD_EDGES={DD_EDGES}; AGE_EDGE={AGE_EDGE}; SIGN_WINDOW={SIGN_WINDOW}; HAR_WINDOW={HAR_WINDOW}; "
          f"HAR_KEYS={sorted(HAR_KEYS)}; N_BOOT={N_BOOT}; SEED={SEED}."]
    return "\n".join(L) + "\n"


def run(cached: bool = False, out_dir: Path = RESULTS_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "inputs.pkl"
    if cached and cache.exists():
        inputs = pickle.loads(cache.read_bytes())
    else:
        inputs = fetch_inputs()
        cache.write_bytes(pickle.dumps(inputs))
    frame, fr = build_panel(inputs)
    ladders = arm_labels(frame)
    first, stop = report_range(frame)
    sigmas = har_sigmas(inputs["prices"], frame.index, first, stop)
    obs = build_observations(frame, fr, ladders, sigmas=sigmas)
    if not obs:
        raise SystemExit("no observations on the explore slice")

    summary: dict = {}
    for h in HORIZONS:
        summary[str(h)] = {arm: summarize_arm(obs, arm, h) for arm in ALL_ARMS if arm != BENCH}
    summary["har_rival"] = {str(h): har_rival(obs, h) for h in HORIZONS}
    summary["width_by_bin"] = {str(h): width_by_bin(obs, "SP500", h) for h in HORIZONS}
    summary["by_state"] = {str(h): skill_by_state(obs, "frag_or", "or_state", h) for h in HORIZONS}
    summary["dd_by_bin"] = {str(h): skill_by_state(obs, "dd_bin", "dd_bin", h) for h in HORIZONS}
    summary["macro_by_level"] = {str(h): skill_by_level(obs, "macro", h) for h in HORIZONS}
    summary["by_year"] = {arm: {str(h): skill_by_year(obs, arm, "SP500", h) for h in (5, 10)}
                          for arm in ("dd_bin", "macro", "frag_or")}

    cells = {}
    for h in HORIZONS:
        cells[f"SP500 h={h}: drawdown × OR state"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_bin", "or_state"])
        cells[f"SP500 h={h}: drawdown alone"] = realized_by_cell(frame, fr, "SP500", h, ["dd_bin"])
    for h in (5, 20):
        cells[f"SP500 h={h}: OR state alone"] = realized_by_cell(frame, fr, "SP500", h, ["or_state"])
    stressed = frame["dd_stressed"] == "dd<=-5"
    for h in HORIZONS:
        cells[f"SP500 h={h}: stressed (dd ≤ −5%) × OR state × spell age — look A"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_stressed", "or_state", "dd_age"], where=stressed)
        cells[f"SP500 h={h}: stressed × spell age alone — A's rival"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_stressed", "dd_age"], where=stressed)
        cells[f"SP500 h={h}: stressed × OR state × trailing-5d sign — look B"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_stressed", "or_state", "sp_sign"], where=stressed)
        cells[f"SP500 h={h}: stressed × trailing-5d sign alone — B's rival"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_stressed", "sp_sign"], where=stressed)
    for h in (5, 20):
        cells[f"SP500 h={h}: drawdown bin × OR state × spell age — look A, fine bins"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_bin", "or_state", "dd_age"], where=stressed)
        cells[f"SP500 h={h}: drawdown bin × OR state × trailing-5d sign — look B, fine bins"] = realized_by_cell(
            frame, fr, "SP500", h, ["dd_bin", "or_state", "sp_sign"], where=stressed)

    dates = sorted({o["date"] for o in obs})
    meta = {"first_date": dates[0], "last_date": dates[-1], "n_report_dates": len(dates),
            "n_obs": len(obs), "fetched": inputs["fetched"],
            "or_elevated_share": round(float(np.mean([o["or_state"] == "Elevated" for o in obs
                                                      if o["horizon"] == 5])), 4)}
    summary["meta"] = meta
    summary["cells"] = {k: json.loads(v.reset_index().to_json(orient="records")) for k, v in cells.items()}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    md = report_md(summary, cells, meta)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cached", action="store_true", help="reuse results/explore_conditioner/inputs.pkl")
    args = ap.parse_args()
    run(cached=args.cached)


if __name__ == "__main__":
    main()
