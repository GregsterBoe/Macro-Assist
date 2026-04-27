# Prediction Accuracy Report

*Generated: 2026-04-27 | Reports scored: 26*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.

## T+5 (1 week)

**Overall accuracy:** 48%  |  **Directional:** 47%  |  **Reports:** 26

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 40% | 35% (n=17) | 26 | 60% |
| Gold | 56% | 57% (n=21) | 26 | 63% |
| WTI Oil | 40% | 33% (n=15) | 26 | 57% |
| 10Y Treasury Yield | 48% | 0% (n=1) | 26 | 57% |
| DXY | 48% | 46% (n=11) | 26 | 56% |
| Bitcoin | 58% | 62% (n=16) | 26 | 57% |

## T+10 (2 weeks)

**Overall accuracy:** 53%  |  **Directional:** 56%  |  **Reports:** 21

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 26% | 19% (n=16) | 21 | 62% |
| Gold | 71% | 76% (n=17) | 21 | 63% |
| WTI Oil | 45% | 42% (n=12) | 21 | 58% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 21 | 59% |
| DXY | 69% | 100% (n=8) | 21 | 57% |
| Bitcoin | 55% | 58% (n=12) | 21 | 56% |

## T+20 (1 month)

**Overall accuracy:** 45%  |  **Directional:** 42%  |  **Reports:** 11

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 4% | 0% (n=10) | 11 | 61% |
| Gold | 64% | 67% (n=9) | 11 | 63% |
| WTI Oil | 41% | 33% (n=6) | 11 | 59% |
| 10Y Treasury Yield | 55% | 100% (n=1) | 11 | 60% |
| DXY | 73% | 78% (n=9) | 11 | 58% |
| Bitcoin | 32% | 17% (n=6) | 11 | 55% |

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).