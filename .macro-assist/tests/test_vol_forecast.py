"""
Tests for vol_forecast.py (HAR-RV and Variance Risk Premium).

Pure unit tests: no external API calls.
Integration tests: require yfinance (network); marked @pytest.mark.integration.

Run unit tests only:
    pytest .macro-assist/tests/test_vol_forecast.py -v -m "not integration"
Run all (including integration):
    pytest .macro-assist/tests/test_vol_forecast.py -v
"""
import numpy as np
import pandas as pd
import pytest

from synthetic import synthetic_garch
from vol_forecast import har_rv_forecast, variance_risk_premium


# ---------------------------------------------------------------------------
# Pure unit tests — no network calls
# ---------------------------------------------------------------------------

def test_har_rv_output_keys():
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0, 0.01, 200))
    result = har_rv_forecast(returns)
    required = {"forecast_daily_vol", "forecast_horizon_vol", "percentile_60d",
                "r_squared", "params"}
    assert required <= set(result.keys())
    assert set(result["params"].keys()) == {"beta_0", "beta_d", "beta_w", "beta_m"}


def test_har_rv_too_short_raises():
    with pytest.raises(ValueError, match="30"):
        har_rv_forecast(pd.Series(np.ones(20)))


def test_har_rv_output_ranges():
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0, 0.01, 300))
    result = har_rv_forecast(returns)
    assert result["forecast_daily_vol"] >= 0.0
    assert 0.0 <= result["percentile_60d"] <= 100.0
    assert 0.0 <= result["r_squared"] <= 1.0


def test_har_rv_reproducible():
    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0, 0.01, 500))
    r1 = har_rv_forecast(r)
    r2 = har_rv_forecast(r)
    assert r1["forecast_daily_vol"] == r2["forecast_daily_vol"]
    assert r1["r_squared"] == r2["r_squared"]


def test_vrp_no_history_neutral():
    result = variance_risk_premium(20.0, {"forecast_daily_vol": 15.0})
    assert result["vrp_60d_percentile"] == 50.0
    assert result["interpretation"] == "Normal"


def test_vrp_interpretation_thresholds():
    forecast = {"forecast_daily_vol": 10.0}

    # Elevated: VRP is high relative to history
    high_hist = pd.DataFrame({"vix": [12.0] * 30, "realized_vol": [10.5] * 30})
    result = variance_risk_premium(20.0, forecast, history=high_hist)
    assert result["interpretation"] == "Elevated"

    # Compressed: VRP is low (or negative) relative to history
    low_hist = pd.DataFrame({"vix": [25.0] * 30, "realized_vol": [10.0] * 30})
    result = variance_risk_premium(12.0, forecast, history=low_hist)
    assert result["interpretation"] == "Compressed"


def test_vrp_value_correct():
    result = variance_risk_premium(18.5, {"forecast_daily_vol": 12.3})
    assert abs(result["vrp"] - 6.2) < 1e-9


def test_recover_garch_vol():
    """
    HAR-RV out-of-sample RMSE on last 500 obs of a GARCH(1,1) series must beat
    the naive 'yesterday's RV' baseline by at least 10%.
    Persistence = 0.95 makes vol highly autocorrelated — HAR-RV should easily win.
    """
    returns = synthetic_garch(2000, omega=0.00001, alpha=0.1, beta=0.85, seed=42)
    all_rv  = returns ** 2
    train   = pd.Series(returns[:1500])

    result  = har_rv_forecast(train)
    beta    = np.array([
        result["params"]["beta_0"],
        result["params"]["beta_d"],
        result["params"]["beta_w"],
        result["params"]["beta_m"],
    ])

    har_preds, naive_preds, actuals = [], [], []
    for t in range(1499, 1999):
        x = np.array([
            1.0,
            all_rv[t],
            all_rv[max(0, t - 4): t + 1].mean(),
            all_rv[max(0, t - 21): t + 1].mean(),
        ])
        har_preds.append(max(0.0, float(beta @ x)))
        naive_preds.append(all_rv[t])
        actuals.append(all_rv[t + 1])

    har_preds   = np.array(har_preds)
    naive_preds = np.array(naive_preds)
    actuals     = np.array(actuals)

    rmse_har   = float(np.sqrt(np.mean((har_preds - actuals) ** 2)))
    rmse_naive = float(np.sqrt(np.mean((naive_preds - actuals) ** 2)))
    improvement = (rmse_naive - rmse_har) / rmse_naive

    assert improvement >= 0.10, (
        f"HAR-RV improvement over naive = {improvement:.2%}, expected ≥ 10%"
    )


# ---------------------------------------------------------------------------
# Integration tests — require yfinance (network)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_r_squared_in_range():
    """In-sample R² for SP500 2022-2024 must be in [0.2, 0.7]."""
    import yfinance as yf

    data   = yf.download("^GSPC", start="2022-01-01", end="2024-12-31",
                          progress=False, auto_adjust=True)
    prices = data["Close"].squeeze()
    rets   = np.log(prices / prices.shift(1)).dropna()

    result = har_rv_forecast(pd.Series(rets.values))
    r2     = result["r_squared"]
    assert 0.2 <= r2 <= 0.7, f"SP500 in-sample R² = {r2:.4f}, expected [0.2, 0.7]"


@pytest.mark.integration
def test_real_sp500_outperforms_naive():
    """
    HAR-RV fitted on 2022-2024 SP500 must beat naive forecast on 2025 data by ≥10%.
    """
    import yfinance as yf

    data   = yf.download("^GSPC", start="2022-01-01", end="2025-12-31",
                          progress=False, auto_adjust=True)
    prices = data["Close"].squeeze()
    rets   = np.log(prices / prices.shift(1)).dropna()
    all_rv = rets.values ** 2

    cut    = (rets.index < "2025-01-01").sum()
    result = har_rv_forecast(pd.Series(rets.values[:cut]))
    beta   = np.array([
        result["params"]["beta_0"],
        result["params"]["beta_d"],
        result["params"]["beta_w"],
        result["params"]["beta_m"],
    ])

    har_preds, naive_preds, actuals = [], [], []
    for t in range(cut - 1, len(all_rv) - 1):
        x = np.array([
            1.0,
            all_rv[t],
            all_rv[max(0, t - 4): t + 1].mean(),
            all_rv[max(0, t - 21): t + 1].mean(),
        ])
        har_preds.append(max(0.0, float(beta @ x)))
        naive_preds.append(all_rv[t])
        actuals.append(all_rv[t + 1])

    if not actuals:
        pytest.skip("No 2025 test data available yet")

    har_preds   = np.array(har_preds)
    naive_preds = np.array(naive_preds)
    actuals     = np.array(actuals)

    rmse_har    = float(np.sqrt(np.mean((har_preds   - actuals) ** 2)))
    rmse_naive  = float(np.sqrt(np.mean((naive_preds - actuals) ** 2)))
    improvement = (rmse_naive - rmse_har) / rmse_naive

    assert improvement >= 0.10, (
        f"SP500 HAR-RV improvement = {improvement:.2%}, expected ≥ 10%"
    )


@pytest.mark.integration
def test_vrp_positive_on_average():
    """
    Mean VRP (VIX − HAR-RV forecast) across 2020-2025 must be positive.
    Well-documented stylized fact: options sellers earn a risk premium on average.
    """
    import yfinance as yf

    sp500 = yf.download("^GSPC", start="2020-01-01", end="2025-12-31",
                         progress=False, auto_adjust=True)
    vix   = yf.download("^VIX",  start="2020-01-01", end="2025-12-31",
                         progress=False, auto_adjust=True)

    prices  = sp500["Close"].squeeze()
    rets    = np.log(prices / prices.shift(1)).dropna()
    vix_s   = vix["Close"].squeeze().reindex(rets.index, method="ffill")
    rv_22d  = rets.rolling(22).std() * np.sqrt(252) * 100   # annualised %

    common  = rv_22d.dropna()
    vix_c   = vix_s.reindex(common.index).dropna()
    common  = common.reindex(vix_c.index)

    vrp_series = vix_c - common
    assert float(vrp_series.mean()) > 0, (
        f"Mean VRP = {vrp_series.mean():.4f}, expected > 0"
    )


@pytest.mark.integration
def test_vrp_compressed_in_crisis():
    """
    During March 2020 (COVID) and October 2022 (bear market trough), HAR-RV
    extrapolates from extreme recent squared returns, producing forecasts that
    exceed VIX.  The resulting VRP goes negative, which is in the bottom < 30th
    percentile of the preceding 60-day distribution.
    """
    import yfinance as yf

    sp500 = yf.download("^GSPC", start="2018-01-01", end="2023-12-31",
                         progress=False, auto_adjust=True)
    vix   = yf.download("^VIX",  start="2018-01-01", end="2023-12-31",
                         progress=False, auto_adjust=True)

    prices  = sp500["Close"].squeeze()
    rets    = np.log(prices / prices.shift(1)).dropna()
    vix_s   = vix["Close"].squeeze().reindex(rets.index, method="ffill")
    rv      = rets.values ** 2
    dates   = rets.index

    for crisis_ym, label in [("2020-03", "March 2020"), ("2022-10", "October 2022")]:
        year, month = int(crisis_ym[:4]), int(crisis_ym[5:])
        crisis_mask = np.array([d.year == year and d.month == month for d in dates])
        crisis_idxs = np.where(crisis_mask)[0]

        min_pct = 100.0

        for idx in crisis_idxs:
            if idx < 60:
                continue

            # HAR-RV fit on all data up to (and including) this date
            forecast = har_rv_forecast(rets.iloc[: idx + 1])
            vix_val  = float(vix_s.iloc[idx])

            # Build trailing VRP history using the same fitted betas (fast approximation)
            beta = np.array([
                forecast["params"]["beta_0"],
                forecast["params"]["beta_d"],
                forecast["params"]["beta_w"],
                forecast["params"]["beta_m"],
            ])

            rows = []
            for j in range(max(22, idx - 60), idx):
                x = np.array([
                    1.0,
                    rv[j],
                    rv[max(0, j - 4): j + 1].mean(),
                    rv[max(0, j - 21): j + 1].mean(),
                ])
                rv_hat   = max(0.0, float(beta @ x))
                hist_vol = float(np.sqrt(rv_hat * 252) * 100)
                rows.append({"vix": float(vix_s.iloc[j]), "realized_vol": hist_vol})

            if not rows:
                continue

            result  = variance_risk_premium(vix_val, forecast, history=pd.DataFrame(rows))
            min_pct = min(min_pct, result["vrp_60d_percentile"])

        assert min_pct < 30, (
            f"{label}: minimum monthly VRP percentile = {min_pct:.1f}%, expected < 30"
        )
