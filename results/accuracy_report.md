# Prediction Accuracy Report

*Generated: 2026-05-30 | Reports scored: 45 | Feedback-loop reports (v0.3+): 29*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.
>
> The **bias override** (daily pipeline) uses only v0.3+ reports
> (adversarial review era). Earlier reports appear below for historical reference.

## T+5 (1 week)

**Overall accuracy:** 47%  |  **Directional:** 43%  |  **Reports:** 45

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=22) | 45 | 57% |
| Gold | 50% | 50% (n=28) | 45 | 60% |
| WTI Oil | 40% | 26% (n=19) | 45 | 54% |
| 10Y Treasury Yield | 46% | 25% (n=8) | 45 | 55% |
| DXY | 49% | 47% (n=15) | 45 | 56% |
| Bitcoin | 46% | 43% (n=30) | 44 | 55% |

## T+10 (2 weeks)

**Overall accuracy:** 46%  |  **Directional:** 43%  |  **Reports:** 40

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 36% | 18% (n=17) | 40 | 57% |
| Gold | 50% | 50% (n=30) | 40 | 61% |
| WTI Oil | 42% | 31% (n=16) | 40 | 55% |
| 10Y Treasury Yield | 48% | 38% (n=8) | 40 | 56% |
| DXY | 52% | 56% (n=16) | 40 | 56% |
| Bitcoin | 50% | 50% (n=28) | 40 | 55% |

## T+20 (1 month)

**Overall accuracy:** 41%  |  **Directional:** 34%  |  **Reports:** 30

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 18% | 0% (n=19) | 30 | 59% |
| Gold | 32% | 28% (n=25) | 30 | 62% |
| WTI Oil | 35% | 20% (n=15) | 30 | 56% |
| 10Y Treasury Yield | 53% | 60% (n=10) | 30 | 57% |
| DXY | 62% | 68% (n=19) | 30 | 56% |
| Bitcoin | 43% | 40% (n=20) | 30 | 57% |

---

## Per-Version Accuracy (latest 5 versions)

Accuracy broken out by the 5 most recently deployed pipeline versions.
Use this to confirm that structural improvements translate into better predictions.

### v0.6  (1 scored / 1 total reports in this version)

**T+5 (1 week)** — overall: 50% | directional: 50% | reports: 1

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 100% | 100% (n=1) | 1 | 52% |
| Gold | 50% | — (n=0) | 1 | 53% |
| WTI Oil | 0% | 0% (n=1) | 1 | 51% |
| 10Y Treasury Yield | 50% | — (n=0) | 1 | 50% |
| DXY | 50% | — (n=0) | 1 | 62% |
| Bitcoin | 50% | — (n=0) | 1 | 50% |

### v0.7  (4 scored / 4 total reports in this version)

**T+5 (1 week)** — overall: 46% | directional: 40% | reports: 4

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 100% | 100% (n=4) | 4 | 52% |
| Gold | 50% | — (n=0) | 4 | 50% |
| WTI Oil | 12% | 0% (n=3) | 4 | 50% |
| 10Y Treasury Yield | 50% | — (n=0) | 4 | 50% |
| DXY | 50% | — (n=0) | 4 | 57% |
| Bitcoin | 0% | 0% (n=3) | 3 | 52% |

### v1.0  (0 scored / 1 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.0 reports.*

### v1.1  (0 scored / 2 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.1 reports.*

### v1.4  (0 scored / 1 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.4 reports.*

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).