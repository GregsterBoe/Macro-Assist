# Prediction Accuracy Report

*Generated: 2026-05-11 | Reports scored: 30*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 49%  |  **Directional:** 48%  |  **Reports:** 30

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 42% | 35% (n=17) | 30 | 59% |
| Gold | 53% | 54% (n=24) | 30 | 62% |
| WTI Oil | 42% | 33% (n=15) | 30 | 56% |
| 10Y Treasury Yield | 48% | 0% (n=1) | 30 | 57% |
| DXY | 50% | 50% (n=12) | 30 | 56% |
| Bitcoin | 58% | 63% (n=19) | 30 | 57% |

## T+10 (2 weeks)

**Overall accuracy:** 50%  |  **Directional:** 51%  |  **Reports:** 28

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 30% | 18% (n=17) | 28 | 60% |
| Gold | 55% | 56% (n=23) | 28 | 62% |
| WTI Oil | 39% | 31% (n=16) | 28 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 28 | 57% |
| DXY | 62% | 82% (n=11) | 28 | 56% |
| Bitcoin | 62% | 68% (n=19) | 28 | 57% |

## T+20 (1 month)

**Overall accuracy:** 42%  |  **Directional:** 36%  |  **Reports:** 21

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 7% | 0% (n=18) | 21 | 62% |
| Gold | 40% | 39% (n=18) | 21 | 63% |
| WTI Oil | 38% | 27% (n=11) | 21 | 58% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 21 | 59% |
| DXY | 76% | 87% (n=15) | 21 | 57% |
| Bitcoin | 36% | 25% (n=12) | 21 | 56% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).