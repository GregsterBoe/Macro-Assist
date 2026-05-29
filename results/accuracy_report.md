# Prediction Accuracy Report

*Generated: 2026-05-29 | Reports scored: 44 | Feedback-loop reports (v0.3+): 28*

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.
>
> The **bias override** (daily pipeline) uses only v0.3+ reports
> (adversarial review era). Earlier reports appear below for historical reference.

## T+5 (1 week)

**Overall accuracy:** 47%  |  **Directional:** 44%  |  **Reports:** 44

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 49% | 48% (n=21) | 44 | 57% |
| Gold | 50% | 50% (n=28) | 44 | 60% |
| WTI Oil | 41% | 28% (n=18) | 44 | 54% |
| 10Y Treasury Yield | 47% | 38% (n=13) | 44 | 55% |
| DXY | 49% | 47% (n=15) | 44 | 56% |
| Bitcoin | 46% | 45% (n=29) | 43 | 55% |

## T+10 (2 weeks)

**Overall accuracy:** 46%  |  **Directional:** 42%  |  **Reports:** 39

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 36% | 18% (n=17) | 39 | 57% |
| Gold | 50% | 50% (n=30) | 39 | 61% |
| WTI Oil | 42% | 31% (n=16) | 39 | 55% |
| 10Y Treasury Yield | 44% | 35% (n=17) | 39 | 56% |
| DXY | 53% | 56% (n=16) | 39 | 56% |
| Bitcoin | 51% | 52% (n=27) | 39 | 56% |

## T+20 (1 month)

**Overall accuracy:** 41%  |  **Directional:** 36%  |  **Reports:** 29

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 17% | 0% (n=19) | 29 | 59% |
| Gold | 31% | 28% (n=25) | 29 | 62% |
| WTI Oil | 34% | 20% (n=15) | 29 | 57% |
| 10Y Treasury Yield | 59% | 69% (n=13) | 29 | 57% |
| DXY | 62% | 68% (n=19) | 29 | 56% |
| Bitcoin | 45% | 42% (n=19) | 29 | 57% |

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

### v0.7  (3 scored / 4 total reports in this version)

**T+5 (1 week)** — overall: 47% | directional: 43% | reports: 3

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 100% | 100% (n=3) | 3 | 52% |
| Gold | 50% | — (n=0) | 3 | 51% |
| WTI Oil | 17% | 0% (n=2) | 3 | 50% |
| 10Y Treasury Yield | 50% | — (n=0) | 3 | 50% |
| DXY | 50% | — (n=0) | 3 | 57% |
| Bitcoin | 0% | 0% (n=2) | 2 | 52% |

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