# Prediction Accuracy Report

*Generated: 2026-05-18 | Reports scored: 35*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 48%  |  **Directional:** 46%  |  **Reports:** 35

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 43% | 35% (n=17) | 35 | 58% |
| Gold | 51% | 52% (n=25) | 35 | 62% |
| WTI Oil | 43% | 33% (n=15) | 35 | 56% |
| 10Y Treasury Yield | 49% | 0% (n=1) | 35 | 56% |
| DXY | 49% | 47% (n=15) | 35 | 56% |
| Bitcoin | 54% | 56% (n=23) | 35 | 56% |

## T+10 (2 weeks)

**Overall accuracy:** 51%  |  **Directional:** 52%  |  **Reports:** 30

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 32% | 18% (n=17) | 30 | 59% |
| Gold | 57% | 58% (n=24) | 30 | 62% |
| WTI Oil | 40% | 31% (n=16) | 30 | 56% |
| 10Y Treasury Yield | 53% | 100% (n=2) | 30 | 57% |
| DXY | 60% | 75% (n=12) | 30 | 56% |
| Bitcoin | 63% | 70% (n=20) | 30 | 57% |

## T+20 (1 month)

**Overall accuracy:** 41%  |  **Directional:** 34%  |  **Reports:** 26

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 14% | 0% (n=19) | 26 | 60% |
| Gold | 35% | 32% (n=22) | 26 | 63% |
| WTI Oil | 33% | 20% (n=15) | 26 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 26 | 57% |
| DXY | 67% | 76% (n=17) | 26 | 56% |
| Bitcoin | 44% | 41% (n=17) | 26 | 57% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).