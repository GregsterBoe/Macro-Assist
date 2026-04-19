# Prediction Accuracy Report

*Generated: 2026-04-19 | Reports scored: 21*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 51%  |  **Directional:** 52%  |  **Reports:** 21

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 40% | 38% (n=16) | 21 | 62% |
| Gold | 64% | 69% (n=16) | 21 | 63% |
| WTI Oil | 48% | 46% (n=11) | 21 | 58% |
| 10Y Treasury Yield | 48% | 0% (n=1) | 21 | 59% |
| DXY | 52% | 56% (n=9) | 21 | 57% |
| Bitcoin | 55% | 58% (n=12) | 21 | 56% |

## T+10 (2 weeks)

**Overall accuracy:** 54%  |  **Directional:** 58%  |  **Reports:** 17

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 26% | 21% (n=14) | 17 | 62% |
| Gold | 74% | 79% (n=14) | 17 | 64% |
| WTI Oil | 50% | 50% (n=8) | 17 | 58% |
| 10Y Treasury Yield | 53% | 100% (n=1) | 17 | 60% |
| DXY | 68% | 100% (n=6) | 17 | 58% |
| Bitcoin | 56% | 60% (n=10) | 17 | 56% |

## T+20 (1 month)

**Overall accuracy:** 39%  |  **Directional:** 32%  |  **Reports:** 6

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 8% | 0% (n=5) | 6 | 60% |
| Gold | 33% | 25% (n=4) | 6 | 62% |
| WTI Oil | 42% | 33% (n=3) | 6 | 59% |
| 10Y Treasury Yield | 58% | 100% (n=1) | 6 | 59% |
| DXY | 58% | 60% (n=5) | 6 | 57% |
| Bitcoin | 33% | 25% (n=4) | 6 | 55% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).