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


if __name__ == "__main__":
    import sys
    if "--diagnose" in sys.argv:
        diagnose_features()
    else:
        run_regime_audit()
