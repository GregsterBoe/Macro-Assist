# Prediction Accuracy Report

*Generated: 2026-05-04 | Reports scored: 28*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 48%  |  **Directional:** 46%  |  **Reports:** 28

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 41% | 35% (n=17) | 28 | 60% |
| Gold | 52% | 52% (n=23) | 28 | 62% |
| WTI Oil | 41% | 33% (n=15) | 28 | 57% |
| 10Y Treasury Yield | 48% | 0% (n=1) | 28 | 57% |
| DXY | 50% | 50% (n=12) | 28 | 56% |
| Bitcoin | 57% | 61% (n=18) | 28 | 57% |

## T+10 (2 weeks)

**Overall accuracy:** 50%  |  **Directional:** 49%  |  **Reports:** 26

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 29% | 18% (n=17) | 26 | 60% |
| Gold | 58% | 59% (n=22) | 26 | 63% |
| WTI Oil | 38% | 31% (n=16) | 26 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 26 | 57% |
| DXY | 62% | 80% (n=10) | 26 | 56% |
| Bitcoin | 60% | 65% (n=17) | 26 | 57% |

## T+20 (1 month)

**Overall accuracy:** 42%  |  **Directional:** 36%  |  **Reports:** 17

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 3% | 0% (n=16) | 17 | 62% |
| Gold | 47% | 47% (n=15) | 17 | 64% |
| WTI Oil | 41% | 29% (n=7) | 17 | 58% |
| 10Y Treasury Yield | 53% | 100% (n=1) | 17 | 60% |
| DXY | 74% | 83% (n=12) | 17 | 58% |
| Bitcoin | 32% | 20% (n=10) | 17 | 56% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).