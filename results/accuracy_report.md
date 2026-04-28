# Prediction Accuracy Report

*Generated: 2026-04-28 | Reports scored: 27*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 48%  |  **Directional:** 47%  |  **Reports:** 27

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 41% | 35% (n=17) | 27 | 60% |
| Gold | 54% | 55% (n=22) | 27 | 62% |
| WTI Oil | 41% | 33% (n=15) | 27 | 57% |
| 10Y Treasury Yield | 48% | 0% (n=1) | 27 | 57% |
| DXY | 48% | 46% (n=11) | 27 | 56% |
| Bitcoin | 59% | 65% (n=17) | 27 | 57% |

## T+10 (2 weeks)

**Overall accuracy:** 52%  |  **Directional:** 53%  |  **Reports:** 22

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 25% | 18% (n=17) | 22 | 62% |
| Gold | 68% | 72% (n=18) | 22 | 63% |
| WTI Oil | 43% | 38% (n=13) | 22 | 58% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 22 | 59% |
| DXY | 68% | 100% (n=8) | 22 | 57% |
| Bitcoin | 52% | 54% (n=13) | 22 | 57% |

## T+20 (1 month)

**Overall accuracy:** 44%  |  **Directional:** 41%  |  **Reports:** 12

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 4% | 0% (n=11) | 12 | 62% |
| Gold | 67% | 70% (n=10) | 12 | 64% |
| WTI Oil | 42% | 33% (n=6) | 12 | 59% |
| 10Y Treasury Yield | 54% | 100% (n=1) | 12 | 60% |
| DXY | 71% | 78% (n=9) | 12 | 58% |
| Bitcoin | 29% | 14% (n=7) | 12 | 56% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).