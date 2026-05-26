# Prediction Accuracy Report

*Generated: 2026-05-26 | Reports scored: 41 | Feedback-loop reports (v0.3+): 25*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.
>
> The **bias override** (daily pipeline) uses only v0.3+ reports
> (adversarial review era). Earlier reports appear below for historical reference.

## T+5 (1 week)

**Overall accuracy:** 47%  |  **Directional:** 44%  |  **Reports:** 41

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 44% | 35% (n=17) | 40 | 57% |
| Gold | 50% | 50% (n=28) | 41 | 61% |
| WTI Oil | 43% | 31% (n=16) | 41 | 55% |
| 10Y Treasury Yield | 50% | 50% (n=2) | 40 | 56% |
| DXY | 49% | 47% (n=15) | 41 | 56% |
| Bitcoin | 49% | 48% (n=27) | 41 | 55% |

## T+10 (2 weeks)

**Overall accuracy:** 48%  |  **Directional:** 46%  |  **Reports:** 36

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 34% | 18% (n=17) | 35 | 58% |
| Gold | 53% | 54% (n=28) | 36 | 61% |
| WTI Oil | 42% | 31% (n=16) | 36 | 55% |
| 10Y Treasury Yield | 51% | 67% (n=3) | 35 | 56% |
| DXY | 53% | 56% (n=16) | 36 | 56% |
| Bitcoin | 54% | 56% (n=25) | 36 | 56% |

## T+20 (1 month)

**Overall accuracy:** 40%  |  **Directional:** 33%  |  **Reports:** 28

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 16% | 0% (n=19) | 28 | 60% |
| Gold | 32% | 29% (n=24) | 28 | 62% |
| WTI Oil | 34% | 20% (n=15) | 28 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 28 | 57% |
| DXY | 64% | 72% (n=18) | 28 | 56% |
| Bitcoin | 45% | 42% (n=19) | 28 | 57% |

---

## Per-Version Accuracy (latest 2 versions)

Accuracy broken out by the 2 most recently deployed pipeline versions.
Use this to confirm that structural improvements translate into better predictions.

### v0.7  (0 scored / 4 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v0.7 reports.*

### v1.0  (0 scored / 1 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.0 reports.*

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).