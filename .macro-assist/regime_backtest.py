"""
regime_backtest.py — WP-17.1: look-ahead audit + walk-forward harness for the
HMM macro-regime layer (Phase 17, Goal 2).

Why this exists
---------------
The fragility index earned its place via a look-ahead-safe backtest (Phase 16.A).
The HMM regime layer (Phase 10) never got the same scrutiny. This module is the
audit harness. Two findings from reading regime.py / refit_models.py /
regime_features.py drive its design:

  1. LIVE labeling is look-ahead-safe. The weekly `refit_models.py` fits the HMM
     on the trailing ~5y window, persists it, and the daily pipeline labels
     *today* with it — today is the last point, so no future leaks in.

  2. VALIDATION must NOT reuse the persisted full-sample model. Baum-Welch fits
     on the whole window (forward-backward over the entire sequence), so the
     in-sample state at any past date is informed by its future. Scoring "did
     regime labels separate forward returns" on the full-sample model is
     therefore leaky. The honest test refits walk-forward: at each date, fit on
     data < d and label d. `walk_forward_regime` does exactly that.

  3. Inference is SINGLE-POINT. `regime_features` returns one (4,) vector and
     `predict_regime` is called on it, so the transition matrix is unused at
     inference — live labeling is effectively a Gaussian-mixture point
     classification weighted by `startprob_`. The HMM's temporal structure only
     shapes the fitted emissions, not the live call. This harness replicates
     single-point inference so its labels match production; WP-17.3 will test
     whether sequence (Viterbi) inference would change anything.

This module is pure-numerical and makes no LLM calls. The walk-forward refit
needs FRED (NFCI / yields / HY) + yfinance, so the CLI requires FRED_API_KEY;
the core functions operate on an injected feature matrix and so are unit-tested
on synthetic data with no network.

Public functions
----------------
walk_forward_regime(features, dates, ...)   -> DataFrame  (point-in-time labels)
full_sample_regime(features, dates, ...)     -> DataFrame  (leaky baseline)
label_divergence(pit_df, full_df)            -> dict
fetch_regime_inputs(years)                    -> (features, dates)   [needs FRED]
run_regime_audit(...)                         -> dict                [CLI]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from regime import label_states

# Production refit cadence is weekly (macro_weekly_refit.yml) on a trailing ~5y
# window; mirror that so the harness reflects what the live system actually does.
_REFIT_EVERY = 5          # trading days between refits (~weekly)
_TRAIN_WINDOW = 1260      # ~5 trading years
_MIN_TRAIN = 252          # need at least 1y before emitting a reading
_N_STATES = 4
_RANDOM_STATE = 42
_N_ITER = 200             # match refit_models.fit_regime_model

# Covariance regularisation: a short / collinear training window can drive a
# full-covariance GaussianHMM to a non-positive-definite covariance (Cholesky
# fails). A small inverse-Wishart-style prior keeps the matrices conditioned.
_COVARS_PRIOR = 1e-2


# ---------------------------------------------------------------------------
# Fitting (local, so n_iter / covariance_type are tunable; defaults match prod)
# ---------------------------------------------------------------------------

def _fit(features: np.ndarray, n_states: int, random_state: int, n_iter: int,
         covariance_type: str = "full"):
    from hmmlearn.hmm import GaussianHMM

    X = np.asarray(features, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    model = GaussianHMM(
        n_components=n_states,
        covariance_type=covariance_type,
        n_iter=n_iter,
        random_state=random_state,
        tol=1e-4,
        covars_prior=_COVARS_PRIOR,
    )
    model.fit(X)
    return model


def _fit_robust(features: np.ndarray, n_states: int, random_state: int,
                n_iter: int, prefer: str = "full") -> tuple:
    """Fit with a fallback ladder so one ill-conditioned window never aborts a
    multi-year walk-forward. Tries `prefer` covariance, then 'diag' (which can't
    go non-positive-definite the way 'full' can). Returns (model, cov_used) or
    (None, None) if every attempt fails — callers carry forward the last model.
    """
    from numpy.linalg import LinAlgError

    X = np.asarray(features, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    ladder = [prefer] + [c for c in ("diag",) if c != prefer]
    for cov in ladder:
        try:
            model = _fit(X, n_states, random_state, n_iter, covariance_type=cov)
            # A degenerate full-covariance model can finish .fit() but then raise
            # inside predict_proba (Cholesky); probe inference before accepting it.
            model.predict_proba(X[-1:])
            return model, cov
        except (LinAlgError, ValueError):
            continue
    return None, None


def _point_label(model, x: np.ndarray, labels: dict) -> tuple[int, str, float]:
    """Single-point classification, matching production's predict_regime call."""
    post = model.predict_proba(np.asarray(x, dtype=float).reshape(1, -1))[-1]
    s = int(np.argmax(post))
    return s, labels.get(s, f"State {s}"), float(post[s])


# ---------------------------------------------------------------------------
# Walk-forward (look-ahead-safe) regime path
# ---------------------------------------------------------------------------

def walk_forward_regime(
    features: np.ndarray,
    dates: pd.DatetimeIndex,
    n_states: int = _N_STATES,
    train_window: int = _TRAIN_WINDOW,
    min_train: int = _MIN_TRAIN,
    refit_every: int = _REFIT_EVERY,
    random_state: int = _RANDOM_STATE,
    n_iter: int = _N_ITER,
    covariance_type: str = "full",
) -> pd.DataFrame:
    """Point-in-time regime labels: at date d, fit on the trailing `train_window`
    of features STRICTLY BEFORE d (refit every `refit_every` days, as production
    does weekly), then classify d with single-point inference.

    The fit uses a fallback ladder (`covariance_type` → 'diag' → carry forward
    the last good model) so an ill-conditioned window never aborts the run.

    Returns a DataFrame indexed by date with columns:
        state_pit (int, that fit's state index), label (economic string),
        top_posterior (float), refit (bool — refit attempted on this date),
        fit_cov (str — covariance type that succeeded, or 'carry' when the fit
        failed and the previous model was reused).
    """
    features = np.asarray(features, dtype=float)
    dates = pd.DatetimeIndex(dates)
    if len(features) != len(dates):
        raise ValueError("features and dates must align")

    rows: list[dict] = []
    model = None
    labels: dict = {}
    fit_cov = None
    last_fit = -10**9

    for i, d in enumerate(dates):
        if i < min_train:
            continue
        refit = False
        if model is None or (i - last_fit) >= refit_every:
            lo = max(0, i - train_window)
            X_train = features[lo:i]              # strictly before d → no leak
            if len(X_train) < min_train:
                continue
            new_model, cov_used = _fit_robust(X_train, n_states, random_state,
                                               n_iter, prefer=covariance_type)
            last_fit = i
            refit = True
            if new_model is not None:
                model, labels, fit_cov = new_model, label_states(new_model), cov_used
            elif model is None:
                continue                          # no usable model yet — skip
            else:
                fit_cov = "carry"                 # reuse previous model

        s, lbl, post = _point_label(model, features[i], labels)
        rows.append({"date": d, "state_pit": s, "label": lbl,
                     "top_posterior": post, "refit": refit, "fit_cov": fit_cov})

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


# ---------------------------------------------------------------------------
# Full-sample (leaky) baseline — what reusing the persisted model would give
# ---------------------------------------------------------------------------

def full_sample_regime(
    features: np.ndarray,
    dates: pd.DatetimeIndex,
    n_states: int = _N_STATES,
    min_train: int = _MIN_TRAIN,
    random_state: int = _RANDOM_STATE,
    n_iter: int = _N_ITER,
) -> pd.DataFrame:
    """Leaky baseline: fit ONCE on the whole feature matrix, then label every
    date (single-point inference, so the only difference vs walk_forward_regime
    is the training data — this isolates Baum-Welch fit leakage). Emits over the
    same date range as the walk-forward (>= min_train) for a fair comparison.
    """
    features = np.asarray(features, dtype=float)
    dates = pd.DatetimeIndex(dates)
    model, _ = _fit_robust(features, n_states, random_state, n_iter)
    if model is None:
        return pd.DataFrame()
    labels = label_states(model)

    rows: list[dict] = []
    for i, d in enumerate(dates):
        if i < min_train:
            continue
        s, lbl, post = _point_label(model, features[i], labels)
        rows.append({"date": d, "state_full": s, "label": lbl, "top_posterior": post})

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


def label_divergence(pit_df: pd.DataFrame, full_df: pd.DataFrame) -> dict:
    """How often does the look-ahead-safe path disagree with the full-sample
    (leaky) path? A high rate means the persisted model's historical labels are
    NOT what the live system would actually have produced — i.e. validating on
    the persisted model would be misleading.
    """
    if pit_df.empty or full_df.empty:
        return {"n": 0, "disagreement_rate": None}
    idx = pit_df.index.intersection(full_df.index)
    if len(idx) == 0:
        return {"n": 0, "disagreement_rate": None}
    a = pit_df.loc[idx, "label"].to_numpy()
    b = full_df.loc[idx, "label"].to_numpy()
    disagree = a != b
    return {
        "n": int(len(idx)),
        "disagreement_rate": round(float(disagree.mean()), 4),
        "n_pit_labels": int(pd.Series(a).nunique()),
        "n_full_labels": int(pd.Series(b).nunique()),
    }


# ---------------------------------------------------------------------------
# WP-17.2 — skill gate: do the (walk-forward) regime labels separate the future?
#
# Scored ONLY on the walk-forward label path (KB-003: the persisted/full-sample
# model is degenerate and 70.5% divergent, so it must never be the basis). The
# 'High-Vol' axis predicting forward vol is partly circular (the vol-percentile
# feature is an input), like fragility's vix_term — the less-circular, more
# decision-relevant test is whether 'Risk-Off' (NFCI/credit axis) leads
# drawdowns and worse forward returns.
# ---------------------------------------------------------------------------

def forward_metrics(close: pd.Series, horizon: int) -> tuple[pd.Series, pd.Series]:
    """For each date: forward cumulative return and forward annualised realized
    vol over the next `horizon` trading days. NaN where the window is incomplete.
    """
    close = pd.Series(close).astype(float)
    arr = close.to_numpy()
    n = len(arr)
    logret = np.diff(np.log(arr))           # logret[i] = i -> i+1
    fret = np.full(n, np.nan)
    fvol = np.full(n, np.nan)
    for i in range(n):
        end = min(i + horizon, n - 1)
        if end > i:
            fret[i] = arr[end] / arr[i] - 1.0
            seg = logret[i:end]
            if len(seg) >= 2:
                fvol[i] = float(np.std(seg, ddof=1)) * np.sqrt(252)
    return pd.Series(fret, index=close.index), pd.Series(fvol, index=close.index)


def regime_skill(
    pit_df: pd.DataFrame,
    sp500_close: pd.Series,
    horizons: tuple[int, ...] = (5, 10, 20),
    drawdown_threshold: float = 0.05,
) -> dict:
    """Score the walk-forward regime labels against forward SP500 outcomes.

    Per horizon: a label→forward-outcome separation table, the AUC of the
    Risk-Off label predicting a forward drawdown, the AUC of the High-Vol label
    predicting top-tercile forward vol, and the Risk-Off→drawdown AUC restricted
    to high-posterior (>=0.8) days as a confidence/calibration check.
    """
    from fragility_backtest import auc, drawdown_label

    labels = pit_df["label"].astype(str)
    risk_off = labels.str.contains("Risk-Off").astype(float)
    high_vol = labels.str.contains("High-Vol").astype(float)
    hi_conf = pit_df["top_posterior"] >= 0.8

    close = pd.Series(sp500_close).astype(float)
    close = close[~close.index.duplicated(keep="last")]
    aligned = close.reindex(pit_df.index, method="ffill")

    out: dict = {}
    for h in horizons:
        fret, fvol = forward_metrics(aligned, h)
        dd = drawdown_label(aligned, threshold=drawdown_threshold, horizon=h).reindex(pit_df.index)

        grp = pd.DataFrame({"label": labels, "fret": fret, "fvol": fvol}).groupby("label")
        separation = {
            lbl: {
                "n": int(g["fret"].notna().sum()),
                "mean_fret": round(float(g["fret"].mean()), 4),
                "median_fret": round(float(g["fret"].median()), 4),
                "mean_fwd_vol": round(float(g["fvol"].mean()), 4),
            }
            for lbl, g in grp
        }

        vol_hi = (fvol >= fvol.quantile(2.0 / 3.0)).astype(float)
        auc_ro_dd_hi = (auc(risk_off[hi_conf], dd[hi_conf])
                        if int(hi_conf.sum()) > 20 else None)

        out[h] = {
            "separation": separation,
            "auc_riskoff_drawdown": _round(auc(risk_off, dd)),
            "auc_highvol_fwdvol":   _round(auc(high_vol, vol_hi)),
            "auc_riskoff_drawdown_hiconf": _round(auc_ro_dd_hi),
            "n_hiconf": int(hi_conf.sum()),
        }
    return out


def _round(v, nd: int = 3):
    return None if v is None else round(float(v), nd)


# ---------------------------------------------------------------------------
# WP-17.3 — inference path vs. concept.
#
# KB-004: the production label path (single-point predict_proba) is dominated by
# startprob_ and carries no skill — the labels don't even track their own input
# features. Before declaring the regime CONCEPT dead, test whether a different
# INFERENCE recovers skill on the SAME fitted models:
#   point    — single current vector (production; startprob-dominated)
#   viterbi  — Viterbi over the trailing window, take the last state
#   smoothed — forward-backward posterior at the last step of the window
#   gmm      — plain Gaussian mixture (no temporal structure) baseline
# One walk-forward pass fits HMM+GMM once per weekly refit and labels every day
# under all four (the fit is the cost; inference is cheap).
# ---------------------------------------------------------------------------

def _fit_gmm_robust(features, n_states, random_state):
    """Fit a GaussianMixture with a fallback ladder mirroring _fit_robust."""
    from sklearn.mixture import GaussianMixture
    from numpy.linalg import LinAlgError
    X = np.asarray(features, dtype=float)
    for cov in ("full", "diag"):
        try:
            g = GaussianMixture(n_components=n_states, covariance_type=cov,
                                reg_covar=1e-4, random_state=random_state,
                                max_iter=200)
            g.fit(X)
            return g
        except (LinAlgError, ValueError):
            continue
    return None


def walk_forward_inference_compare(
    features: np.ndarray,
    dates: pd.DatetimeIndex,
    n_states: int = _N_STATES,
    train_window: int = _TRAIN_WINDOW,
    min_train: int = _MIN_TRAIN,
    refit_every: int = _REFIT_EVERY,
    infer_window: int = 120,
    random_state: int = _RANDOM_STATE,
    n_iter: int = _N_ITER,
    covariance_type: str = "full",
) -> pd.DataFrame:
    """Walk forward (look-ahead-safe), refitting HMM + GMM weekly on the trailing
    window strictly before each date, and label every day under four inference
    methods. Returns a DataFrame indexed by date with columns:
        label_point, label_viterbi, label_smoothed, label_gmm, post_point.
    """
    features = np.asarray(features, dtype=float)
    dates = pd.DatetimeIndex(dates)
    if len(features) != len(dates):
        raise ValueError("features and dates must align")

    rows: list[dict] = []
    hmm = gmm = None
    hmm_labels: dict = {}
    gmm_labels: dict = {}
    last_fit = -10**9

    for i, d in enumerate(dates):
        if i < min_train:
            continue
        if hmm is None or (i - last_fit) >= refit_every:
            X_train = features[max(0, i - train_window):i]   # strictly before d
            if len(X_train) < min_train:
                continue
            new_hmm, _ = _fit_robust(X_train, n_states, random_state, n_iter,
                                     prefer=covariance_type)
            new_gmm = _fit_gmm_robust(X_train, n_states, random_state)
            last_fit = i
            if new_hmm is not None:
                hmm, hmm_labels = new_hmm, label_states(new_hmm)
            if new_gmm is not None:
                gmm, gmm_labels = new_gmm, label_states(new_gmm)
            if hmm is None:
                continue

        x = features[i].reshape(1, -1)
        seq = features[max(0, i - infer_window + 1):i + 1]
        row = {"date": d}

        # point (production)
        s_pt, lbl_pt, post_pt = _point_label(hmm, features[i], hmm_labels)
        row["label_point"], row["post_point"] = lbl_pt, post_pt
        # sequence inference (transition matrix acts)
        try:
            vit = int(hmm.predict(seq)[-1])
            row["label_viterbi"] = hmm_labels.get(vit, f"State {vit}")
            sm = int(np.argmax(hmm.predict_proba(seq)[-1]))
            row["label_smoothed"] = hmm_labels.get(sm, f"State {sm}")
        except (ValueError, np.linalg.LinAlgError):
            row["label_viterbi"] = lbl_pt
            row["label_smoothed"] = lbl_pt
        # gmm baseline (no temporal structure)
        if gmm is not None:
            try:
                g = int(gmm.predict(x)[0])
                row["label_gmm"] = gmm_labels.get(g, f"State {g}")
            except (ValueError, np.linalg.LinAlgError):
                row["label_gmm"] = lbl_pt
        else:
            row["label_gmm"] = lbl_pt

        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date")


_INFERENCE_METHODS = ("point", "viterbi", "smoothed", "gmm")


def compare_inference_skill(
    cmp_df: pd.DataFrame,
    sp500_close: pd.Series,
    horizon: int = 10,
    drawdown_threshold: float = 0.05,
) -> dict:
    """Re-score the 17.2 skill metric for each inference method's label path.
    Returns {method: {auc_riskoff_drawdown, auc_highvol_fwdvol, n_labels}}.
    The High-Vol→fwd-vol AUC is the floor test: a working inference should make
    the High-Vol label track forward vol (well above 0.50)."""
    out: dict = {}
    for method in _INFERENCE_METHODS:
        col = f"label_{method}"
        if col not in cmp_df.columns:
            continue
        mini = pd.DataFrame({"label": cmp_df[col], "top_posterior": 1.0},
                            index=cmp_df.index)
        skill = regime_skill(mini, sp500_close, horizons=(horizon,),
                             drawdown_threshold=drawdown_threshold)[horizon]
        out[method] = {
            "auc_riskoff_drawdown": skill["auc_riskoff_drawdown"],
            "auc_highvol_fwdvol":   skill["auc_highvol_fwdvol"],
            "n_labels": int(cmp_df[col].nunique()),
        }
    return out


# ---------------------------------------------------------------------------
# WP-17.4 — incremental value over the simpler bucket.
#
# Does the HMM regime add drawdown-prediction skill beyond simply conditioning on
# the same macro inputs? The real Phase-11 bucket (conditional.assign_bucket)
# keys off the truncated HY-OAS series (WP-17.5), so it isn't computable over
# full history; instead compare the HMM (in its best Viterbi inference, KB-005)
# against a transparent rule-based stress score on the same 4 features. If the
# HMM doesn't beat the rule and adds nothing within stress strata, it is
# redundant — keep the rule, drop the HMM.
# ---------------------------------------------------------------------------

def feature_stress_score(features: np.ndarray) -> np.ndarray:
    """Transparent rule-based macro-stress score on the 4 regime features:
    +nfci_pct, −yc_slope, +credit_z, +vol_pct (each standardised, equal weight).
    Higher = more stressed. AUC is rank-based, so the standardisation scale is
    irrelevant — only the (fixed, equal) cross-feature weighting matters."""
    X = np.asarray(features, dtype=float)
    z = (X - np.nanmean(X, axis=0)) / (np.nanstd(X, axis=0) + 1e-9)
    signs = np.array([1.0, -1.0, 1.0, 1.0])    # stress direction per feature
    return (z * signs).sum(axis=1)


def regime_vs_bucket(
    cmp_df: pd.DataFrame,
    features: np.ndarray,
    dates: pd.DatetimeIndex,
    sp500_close: pd.Series,
    horizon: int = 10,
    drawdown_threshold: float = 0.05,
    regime_col: str = "label_viterbi",
) -> dict:
    """Compare the HMM regime (best inference) vs the rule-based stress score at
    predicting forward drawdowns, plus a redundancy + within-stratum check.
    Returns auc_bucket, auc_regime, spearman (redundancy), within-tercile regime
    AUCs and their mean (incremental value)."""
    from fragility_backtest import auc, drawdown_label

    stress = pd.Series(feature_stress_score(features),
                       index=pd.DatetimeIndex(dates)).reindex(cmp_df.index)
    close = pd.Series(sp500_close).astype(float)
    close = close[~close.index.duplicated(keep="last")]
    aligned = close.reindex(cmp_df.index, method="ffill")
    dd = drawdown_label(aligned, threshold=drawdown_threshold, horizon=horizon).reindex(cmp_df.index)
    risk_off = cmp_df[regime_col].astype(str).str.contains("Risk-Off").astype(float)

    terc = pd.qcut(stress.rank(method="first"), 3, labels=["low", "mid", "high"])
    within = {}
    for t in ("low", "mid", "high"):
        m = (terc == t).to_numpy()
        within[t] = _round(auc(risk_off[m], dd[m])) if int(m.sum()) > 30 else None
    vals = [v for v in within.values() if v is not None]

    return {
        "auc_bucket_stress": _round(auc(stress, dd)),
        "auc_regime":        _round(auc(risk_off, dd)),
        "redundancy_spearman": _round(float(pd.Series(stress).corr(risk_off, method="spearman"))),
        "within_tercile_regime_auc": within,
        "within_tercile_mean": _round(float(np.mean(vals))) if vals else None,
    }


# ---------------------------------------------------------------------------
# Real-data fetch + CLI (needs FRED_API_KEY; reuses refit_models feature logic)
# ---------------------------------------------------------------------------

def _fetch_raw_inputs(years: int = 12) -> tuple[dict, pd.Series]:
    """Fetch the raw FRED series + SP500 close used to build regime features.
    Requires FRED_API_KEY. The yfinance index is tz-normalised to naive so it
    aligns with the tz-naive FRED business-day reindex (mirrors
    fragility_backtest.fetch_histories)."""
    import os
    from datetime import date, timedelta

    import yfinance as yf
    from fredapi import Fred

    from refit_models import _FRED_SERIES

    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY not set — regime features need FRED data.")
    fred = Fred(api_key=key)

    start = (date.today() - timedelta(days=365 * years + 60)).isoformat()
    fred_series: dict[str, pd.Series] = {}
    for k, sid in _FRED_SERIES.items():
        s = fred.get_series(sid, observation_start=start)
        if s is not None and not s.empty:
            fred_series[k] = s.dropna()

    hist = yf.download("^GSPC", start=start, progress=False, auto_adjust=True)
    sp500_close = hist["Close"].squeeze().ffill().dropna()
    if getattr(sp500_close.index, "tz", None) is not None:
        sp500_close.index = sp500_close.index.tz_localize(None)

    return fred_series, sp500_close


def fetch_regime_inputs(years: int = 12) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Fetch FRED + yfinance and build the (n_days, 4) feature matrix used by the
    HMM, reusing refit_models._build_feature_matrix. Requires FRED_API_KEY.
    """
    from refit_models import _build_feature_matrix

    fred_series, sp500_close = _fetch_raw_inputs(years)
    return _build_feature_matrix(fred_series, sp500_close)


def diagnose_features(years: int = 12) -> dict:
    """WP-17.1 diagnostic: explain the feature-matrix truncation.

    Prints the date span / count of each raw input (FRED series + SP500), the
    business-day window, and — per feature column, BEFORE the all-NaN row drop —
    how many days are valid and the first/last valid date. This pinpoints which
    input (or rolling warmup) collapses the valid range. Requires FRED_API_KEY.
    """
    from refit_models import _build_feature_matrix

    fred_series, sp500_close = _fetch_raw_inputs(years)

    print("=== Raw inputs ===")
    print(f"  SP500 close: {len(sp500_close)} rows  "
          f"{sp500_close.index[0].date()}..{sp500_close.index[-1].date()}")
    for k, s in fred_series.items():
        print(f"  FRED {k:<13}: {len(s)} rows  {s.index[0].date()}..{s.index[-1].date()}")

    # Per-feature validity before the dropna (mirror _build_feature_matrix order).
    feats, dates = _build_feature_matrix(fred_series, sp500_close)
    names = ["nfci_pct", "yc_slope", "hy_zscore", "vol_pct"]
    print("\n=== Feature matrix (post-build, post-dropna) ===")
    if len(feats) == 0:
        print("  EMPTY — every business day had at least one NaN feature.")
    else:
        print(f"  {len(feats)} valid days  {dates[0].date()}..{dates[-1].date()}")
        for j, nm in enumerate(names):
            col = feats[:, j]
            ok = ~np.isnan(col)
            print(f"    [{j}] {nm:<10} non-NaN {int(ok.sum())}/{len(col)}")
    print("\nIf one FRED series above starts ~2 years ago, that is the truncation"
          "\nculprit; if all inputs are full-length but valid days are few, the"
          "\ncause is in the rolling/align logic of _build_feature_matrix.")
    return {"n_valid": int(len(feats)),
            "first": (dates[0].date().isoformat() if len(feats) else None),
            "last": (dates[-1].date().isoformat() if len(feats) else None)}


def run_regime_audit(years: int = 12, n_states: int = _N_STATES) -> dict:
    """Fetch real data, run the walk-forward and full-sample paths, and report
    how far the look-ahead-safe regime path diverges from the leaky baseline."""
    print(f"Fetching regime inputs (FRED + yfinance, {years}y)...")
    features, dates = fetch_regime_inputs(years)
    print(f"  {len(features)} valid feature-days {dates[0].date()}..{dates[-1].date()}")
    if len(features) < 252 * (years - 2):
        print(f"  WARNING: far fewer valid days than ~{years}y implies — run "
              "diagnose_features() to find the truncation.")
    print()

    print("Walk-forward refit (look-ahead-safe; this is the slow part)...")
    pit = walk_forward_regime(features, dates, n_states=n_states)
    n_refit = int(pit["refit"].sum()) if not pit.empty else 0
    n_fallback = int((pit.loc[pit["refit"], "fit_cov"] != "full").sum()) if not pit.empty else 0
    print(f"  {len(pit)} point-in-time readings, {n_refit} refits "
          f"({n_fallback} used a diag/carry fallback)\n")

    print("Full-sample fit (leaky baseline)...")
    full = full_sample_regime(features, dates, n_states=n_states)

    div = label_divergence(pit, full)
    print("------------------------------------------------------------")
    print("LOOK-AHEAD AUDIT")
    print(f"  compared days        : {div['n']}")
    print(f"  label disagreement   : {div['disagreement_rate']:.1%}"
          if div["disagreement_rate"] is not None else "  label disagreement   : n/a")
    print(f"  distinct labels  PIT : {div.get('n_pit_labels')}  | full-sample: {div.get('n_full_labels')}")
    print("  (high disagreement => the persisted full-sample model's historical")
    print("   labels are NOT what the live system produced; validate walk-forward.)")
    print("------------------------------------------------------------")
    return {"divergence": div, "pit": pit, "full": full}


def run_regime_skill(years: int = 18, n_states: int = _N_STATES,
                     drawdown_threshold: float = 0.05) -> dict:
    """WP-17.2 skill gate: walk forward (look-ahead-safe), then score whether the
    regime labels separate forward SP500 returns / vol / drawdowns. Default 18y
    so the 2008 GFC is in sample. Needs FRED_API_KEY."""
    print(f"Fetching regime inputs (FRED + yfinance, {years}y)...")
    fred_series, sp500_close = _fetch_raw_inputs(years)
    from refit_models import _build_feature_matrix
    features, dates = _build_feature_matrix(fred_series, sp500_close)
    print(f"  {len(features)} valid feature-days {dates[0].date()}..{dates[-1].date()}\n")

    print("Walk-forward refit (look-ahead-safe)...")
    pit = walk_forward_regime(features, dates, n_states=n_states)
    if pit.empty:
        print("No readings — insufficient history.")
        return {}
    print(f"  {len(pit)} readings, {int(pit['refit'].sum())} refits\n")

    skill = regime_skill(pit, sp500_close, drawdown_threshold=drawdown_threshold)

    print("============================================================")
    print(f"REGIME SKILL GATE (walk-forward labels; drawdown >= {drawdown_threshold:.0%})")
    for h, r in skill.items():
        print(f"\n--- Horizon {h} trading days ---")
        print("  Forward outcome by regime label:")
        for lbl, s in sorted(r["separation"].items()):
            print(f"    {lbl:<22} n={s['n']:<5} mean_ret={s['mean_fret']:+.4f} "
                  f"med_ret={s['median_fret']:+.4f} mean_fwd_vol={s['mean_fwd_vol']:.3f}")
        print("  AUC (0.50 = no skill):")
        print(f"    Risk-Off  -> drawdown      : {r['auc_riskoff_drawdown']}")
        print(f"    Risk-Off  -> drawdown (hi-conf, n={r['n_hiconf']}): {r['auc_riskoff_drawdown_hiconf']}")
        print(f"    High-Vol  -> top-tercile fwd vol (partly circular): {r['auc_highvol_fwdvol']}")

    _print_skill_verdict(skill)
    return {"pit": pit, "skill": skill}


def _print_skill_verdict(skill: dict) -> None:
    aucs = [r["auc_riskoff_drawdown"] for r in skill.values()
            if r["auc_riskoff_drawdown"] is not None]
    best = max(aucs) if aucs else None
    print("\n------------------------------------------------------------")
    print("VERDICT (Risk-Off -> drawdown is the least-circular skill test)")
    if best is None:
        print("  Inconclusive — no scorable days.")
    elif best >= 0.58:
        print(f"  SEPARATES THE FUTURE (best Risk-Off->drawdown AUC {best:.3f}).")
        print("  The regime layer earns its place; proceed to 17.3 (model selection).")
    elif best >= 0.53:
        print(f"  WEAK (best AUC {best:.3f}). Marginal — compare against the simpler")
        print("  conditional bucket (17.4) before keeping the HMM.")
    else:
        print(f"  NO SKILL (best AUC {best:.3f}). The regime layer is decorative;")
        print("  simplify or drop it (and revisit the startprob-dominated inference).")
    print("------------------------------------------------------------")


def run_inference_comparison(years: int = 18, n_states: int = _N_STATES,
                             horizon: int = 10, drawdown_threshold: float = 0.05) -> dict:
    """WP-17.3: does a different inference path recover skill the production
    single-point path lacks (KB-004)? Compares point / viterbi / smoothed / gmm
    on the same walk-forward fits. Needs FRED_API_KEY."""
    print(f"Fetching regime inputs (FRED + yfinance, {years}y)...")
    fred_series, sp500_close = _fetch_raw_inputs(years)
    from refit_models import _build_feature_matrix
    features, dates = _build_feature_matrix(fred_series, sp500_close)
    print(f"  {len(features)} valid feature-days {dates[0].date()}..{dates[-1].date()}\n")

    print("Walk-forward refit (HMM + GMM, all inference methods)...")
    cmp_df = walk_forward_inference_compare(features, dates, n_states=n_states)
    if cmp_df.empty:
        print("No readings — insufficient history.")
        return {}
    print(f"  {len(cmp_df)} readings\n")

    res = compare_inference_skill(cmp_df, sp500_close, horizon=horizon,
                                  drawdown_threshold=drawdown_threshold)
    print("============================================================")
    print(f"INFERENCE COMPARISON @ {horizon}d (drawdown >= {drawdown_threshold:.0%})")
    print(f"  {'method':<10} {'RiskOff->DD':>12} {'HighVol->vol':>13} {'labels':>7}")
    print("  " + "-" * 46)
    for m in _INFERENCE_METHODS:
        if m not in res:
            continue
        r = res[m]
        dd = "n/a" if r["auc_riskoff_drawdown"] is None else f"{r['auc_riskoff_drawdown']:.3f}"
        hv = "n/a" if r["auc_highvol_fwdvol"] is None else f"{r['auc_highvol_fwdvol']:.3f}"
        print(f"  {m:<10} {dd:>12} {hv:>13} {r['n_labels']:>7}")
    _print_inference_verdict(res)
    return {"cmp": cmp_df, "skill": res}


def _print_inference_verdict(res: dict) -> None:
    # Floor test: does any non-point method make High-Vol track forward vol?
    floor = [(m, res[m]["auc_highvol_fwdvol"]) for m in ("viterbi", "smoothed", "gmm")
             if res.get(m, {}).get("auc_highvol_fwdvol") is not None]
    best_floor = max((v for _, v in floor), default=None)
    dd = [(m, res[m]["auc_riskoff_drawdown"]) for m in _INFERENCE_METHODS
          if res.get(m, {}).get("auc_riskoff_drawdown") is not None]
    best_dd = max((v for _, v in dd), default=None)
    print("\n------------------------------------------------------------")
    print("VERDICT (is it the inference path or the concept?)")
    if best_floor is None:
        print("  Inconclusive — no scorable labels.")
    elif best_floor >= 0.60:
        print(f"  INFERENCE WAS THE PROBLEM (best High-Vol→vol AUC {best_floor:.3f}).")
        print("  A sequence/GMM inference makes labels track features again — fix the")
        print("  live inference path, then re-run the skill gate + model selection.")
        if best_dd is not None and best_dd >= 0.55:
            print(f"  Risk-Off→drawdown also recovers (best {best_dd:.3f}) — regime layer salvageable.")
    else:
        print(f"  CONCEPT LOOKS DEAD (best High-Vol→vol AUC {best_floor:.3f}).")
        print("  Even sequence/GMM inference can't make the labels track features or")
        print("  the future on these 4 features. Simplify or drop the regime layer.")
    print("------------------------------------------------------------")


def run_regime_vs_bucket(years: int = 18, n_states: int = _N_STATES,
                         horizon: int = 10, drawdown_threshold: float = 0.05) -> dict:
    """WP-17.4 keep/cut gate: does the HMM regime (best Viterbi inference) add
    drawdown skill over a simple rule-based stress score on the same features?
    Needs FRED_API_KEY."""
    print(f"Fetching regime inputs (FRED + yfinance, {years}y)...")
    fred_series, sp500_close = _fetch_raw_inputs(years)
    from refit_models import _build_feature_matrix
    features, dates = _build_feature_matrix(fred_series, sp500_close)
    print(f"  {len(features)} valid feature-days {dates[0].date()}..{dates[-1].date()}\n")

    print("Walk-forward (HMM sequence inference) + rule-based bucket...")
    cmp_df = walk_forward_inference_compare(features, dates, n_states=n_states)
    if cmp_df.empty:
        print("No readings — insufficient history.")
        return {}
    # Align the feature matrix to the emitted (post-warmup) dates.
    pos = {d: k for k, d in enumerate(pd.DatetimeIndex(dates))}
    keep = [pos[d] for d in cmp_df.index]
    feats_aligned = np.asarray(features)[keep]

    r = regime_vs_bucket(cmp_df, feats_aligned, cmp_df.index, sp500_close,
                         horizon=horizon, drawdown_threshold=drawdown_threshold)

    print("============================================================")
    print(f"REGIME vs SIMPLE BUCKET @ {horizon}d (drawdown >= {drawdown_threshold:.0%})")
    print(f"  rule-based stress score -> drawdown AUC : {r['auc_bucket_stress']}")
    print(f"  HMM regime (Viterbi)    -> drawdown AUC : {r['auc_regime']}")
    print(f"  redundancy (Spearman regime vs rule)    : {r['redundancy_spearman']}")
    print(f"  regime AUC within stress terciles       : {r['within_tercile_regime_auc']}"
          f"  (mean {r['within_tercile_mean']})")
    _print_bucket_verdict(r)
    return {"cmp": cmp_df, "result": r}


def _print_bucket_verdict(r: dict) -> None:
    ab, ar = r["auc_bucket_stress"], r["auc_regime"]
    wm = r["within_tercile_mean"]
    print("\n------------------------------------------------------------")
    print("VERDICT (does the HMM earn its complexity over a simple rule?)")
    if ab is None or ar is None:
        print("  Inconclusive — no scorable days.")
    elif ar > ab + 0.02 and (wm or 0) >= 0.52:
        print(f"  REGIME ADDS VALUE (regime {ar:.3f} > rule {ab:.3f}; within-stratum {wm}).")
        print("  Worth fixing the live inference path (WP-17.3b) and keeping the layer.")
    elif ar <= ab and (wm or 0.5) <= 0.52:
        print(f"  REDUNDANT (regime {ar:.3f} <= rule {ab:.3f}; within-stratum {wm}).")
        print("  The HMM adds nothing over a trivial rule on the same inputs — simplify:")
        print("  drop the HMM, keep the rule/bucket. Don't spend on WP-17.3b.")
    else:
        print(f"  MARGINAL (regime {ar:.3f} vs rule {ab:.3f}; within-stratum {wm}).")
        print("  Weak incremental value — keep only if the live fix is cheap.")
    print("------------------------------------------------------------")


if __name__ == "__main__":
    import sys
    if "--diagnose" in sys.argv:
        diagnose_features()
    elif "--skill" in sys.argv:
        run_regime_skill()
    elif "--infer" in sys.argv:
        run_inference_comparison()
    elif "--bucket" in sys.argv:
        run_regime_vs_bucket()
    else:
        run_regime_audit()
