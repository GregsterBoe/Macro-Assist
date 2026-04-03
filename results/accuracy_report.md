# Prediction Accuracy Report

*Generated: 2026-04-03 | Reports scored: 10*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 55%  |  **Directional:** 60%  |  **Reports:** 10

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 75% | 86% (n=7) | 10 | 61% |
| Gold | 50% | 50% (n=8) | 10 | 63% |
| WTI Oil | 55% | 60% (n=5) | 10 | 59% |
| 10Y Treasury Yield | 45% | 0% (n=1) | 10 | 60% |
| DXY | 30% | 0% (n=4) | 10 | 57% |
| Bitcoin | 75% | 100% (n=5) | 10 | 55% |

## T+10 (2 weeks)

**Overall accuracy:** 60%  |  **Directional:** 71%  |  **Reports:** 5

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 80% | 100% (n=3) | 5 | 59% |
| Gold | 20% | 0% (n=3) | 5 | 61% |
| WTI Oil | 60% | 67% (n=3) | 5 | 60% |
| 10Y Treasury Yield | 60% | 100% (n=1) | 5 | 59% |
| DXY | 60% | 100% (n=1) | 5 | 55% |
| Bitcoin | 80% | 100% (n=3) | 5 | 55% |

## T+20 (1 month)

*No data yet.*

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).