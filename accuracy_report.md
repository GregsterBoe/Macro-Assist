# Prediction Accuracy Report

*Generated: 2026-09-07 | Arm: `market` | Reports scored: 114 | Feedback-loop reports (v0.3+): 98*

> **Scope: the `market` arm only.** Several prediction arms write score files
> and sibling arms share a `report_date`, so a pooled figure would average
> different systems and a date-keyed join would mix their metadata outright
> [KB-023]. Cross-arm comparison lives in the arm A/B further down.

> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.
> **Directional accuracy** excludes flat moves and Neutral calls — it is the
> signal quality metric. Anything above ~60% with n > 10 is meaningful.
>
> The **bias override** (daily pipeline) uses only v0.3+ reports
> (adversarial review era). Earlier reports appear below for historical reference.

| Arm | reports | resolved calls | span | in this report |
|-----|--------:|---------------:|------|:--------------:|
| `exogenous` | 5 | 33 | 2026-07-27 → 2026-08-24 | — |
| `kimi` | 20 | 240 | 2026-08-03 → 2026-08-28 | — |
| `market` | 114 | 1927 | 2026-03-13 → 2026-08-28 | ✅ |

## T+5 (1 week)

**Overall accuracy:** 49%  |  **Directional:** 46%  |  **Reports:** 114

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=40) | 113 | 55% |
| Gold | 51% | 52% (n=63) | 114 | 57% |
| WTI Oil | 46% | 30% (n=23) | 114 | 55% |
| 10Y Treasury Yield | 49% | 42% (n=19) | 114 | 55% |
| DXY | 50% | 48% (n=23) | 114 | 55% |
| Bitcoin | 46% | 41% (n=46) | 113 | 54% |

## T+10 (2 weeks)

**Overall accuracy:** 46%  |  **Directional:** 40%  |  **Reports:** 109

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 44% | 35% (n=43) | 108 | 55% |
| Gold | 48% | 47% (n=68) | 109 | 58% |
| WTI Oil | 44% | 25% (n=24) | 109 | 55% |
| 10Y Treasury Yield | 49% | 44% (n=16) | 109 | 55% |
| DXY | 46% | 37% (n=30) | 109 | 55% |
| Bitcoin | 47% | 44% (n=48) | 108 | 54% |

## T+20 (1 month)

**Overall accuracy:** 44%  |  **Directional:** 35%  |  **Reports:** 99

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 44% | 34% (n=38) | 99 | 55% |
| Gold | 42% | 38% (n=63) | 99 | 58% |
| WTI Oil | 42% | 17% (n=23) | 99 | 55% |
| 10Y Treasury Yield | 54% | 64% (n=25) | 99 | 55% |
| DXY | 45% | 37% (n=38) | 99 | 55% |
| Bitcoin | 37% | 23% (n=48) | 98 | 54% |

---

## Per-Version Accuracy (latest 5 versions)

Accuracy broken out by the 5 most recently deployed pipeline versions.
Use this to confirm that structural improvements translate into better predictions.

### v1.1  (2 scored / 2 total reports in this version)

**T+5 (1 week)** — overall: 50% | directional: 50% | reports: 2

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | — (n=0) | 2 | 55% |
| Gold | 50% | — (n=0) | 2 | 52% |
| WTI Oil | 75% | 100% (n=1) | 2 | 52% |
| 10Y Treasury Yield | 50% | — (n=0) | 2 | 55% |
| DXY | 50% | — (n=0) | 2 | 52% |
| Bitcoin | 25% | 0% (n=1) | 2 | 54% |

**T+10 (2 weeks)** — overall: 33% | directional: 0% | reports: 2

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | — (n=0) | 2 | 55% |
| Gold | 50% | — (n=0) | 2 | 52% |
| WTI Oil | 25% | 0% (n=1) | 2 | 52% |
| 10Y Treasury Yield | 25% | 0% (n=1) | 2 | 55% |
| DXY | 25% | 0% (n=1) | 2 | 52% |
| Bitcoin | 25% | 0% (n=1) | 2 | 54% |

**T+20 (1 month)** — overall: 46% | directional: 40% | reports: 2

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | — (n=0) | 2 | 55% |
| Gold | 50% | — (n=0) | 2 | 52% |
| WTI Oil | 25% | 0% (n=1) | 2 | 52% |
| 10Y Treasury Yield | 100% | 100% (n=2) | 2 | 55% |
| DXY | 25% | 0% (n=1) | 2 | 52% |
| Bitcoin | 25% | 0% (n=1) | 2 | 54% |

### v1.2  (1 scored / 1 total reports in this version)

**T+5 (1 week)** — overall: 58% | directional: 100% | reports: 1

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 100% | 100% (n=1) | 1 | 57% |
| Gold | 50% | — (n=0) | 1 | 60% |
| WTI Oil | 50% | — (n=0) | 1 | 52% |
| 10Y Treasury Yield | 50% | — (n=0) | 1 | 55% |
| DXY | 50% | — (n=0) | 1 | 57% |
| Bitcoin | 50% | — (n=0) | 1 | 53% |

**T+10 (2 weeks)** — overall: 25% | directional: 0% | reports: 1

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 0% | 0% (n=1) | 1 | 57% |
| Gold | 0% | 0% (n=1) | 1 | 60% |
| WTI Oil | 50% | — (n=0) | 1 | 52% |
| 10Y Treasury Yield | 50% | — (n=0) | 1 | 55% |
| DXY | 0% | 0% (n=1) | 1 | 57% |
| Bitcoin | 50% | — (n=0) | 1 | 53% |

**T+20 (1 month)** — overall: 25% | directional: 0% | reports: 1

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 0% | 0% (n=1) | 1 | 57% |
| Gold | 0% | 0% (n=1) | 1 | 60% |
| WTI Oil | 50% | — (n=0) | 1 | 52% |
| 10Y Treasury Yield | 50% | — (n=0) | 1 | 55% |
| DXY | 0% | 0% (n=1) | 1 | 57% |
| Bitcoin | 50% | — (n=0) | 1 | 53% |

### v1.4  (20 scored / 21 total reports in this version)

**T+5 (1 week)** — overall: 48% | directional: 44% | reports: 20

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=2) | 20 | 51% |
| Gold | 42% | 41% (n=17) | 20 | 56% |
| WTI Oil | 45% | 0% (n=2) | 20 | 52% |
| 10Y Treasury Yield | 48% | 44% (n=9) | 20 | 55% |
| DXY | 48% | 43% (n=7) | 20 | 52% |
| Bitcoin | 52% | 55% (n=11) | 20 | 52% |

**T+10 (2 weeks)** — overall: 44% | directional: 35% | reports: 20

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=2) | 20 | 51% |
| Gold | 28% | 24% (n=17) | 20 | 56% |
| WTI Oil | 45% | 0% (n=2) | 20 | 52% |
| 10Y Treasury Yield | 48% | 40% (n=5) | 20 | 55% |
| DXY | 38% | 22% (n=9) | 20 | 52% |
| Bitcoin | 57% | 64% (n=11) | 20 | 52% |

**T+20 (1 month)** — overall: 40% | directional: 25% | reports: 20

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=2) | 20 | 51% |
| Gold | 25% | 19% (n=16) | 20 | 56% |
| WTI Oil | 45% | 0% (n=2) | 20 | 52% |
| 10Y Treasury Yield | 52% | 55% (n=11) | 20 | 55% |
| DXY | 32% | 0% (n=7) | 20 | 52% |
| Bitcoin | 35% | 20% (n=10) | 20 | 52% |

### v1.5  (45 scored / 50 total reports in this version)

**T+5 (1 week)** — overall: 51% | directional: 56% | reports: 45

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 48% | 43% (n=14) | 44 | 56% |
| Gold | 57% | 67% (n=18) | 45 | 56% |
| WTI Oil | 51% | 100% (n=1) | 45 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=2) | 45 | 56% |
| DXY | 51% | 100% (n=1) | 45 | 55% |
| Bitcoin | 47% | 0% (n=3) | 45 | 55% |

**T+10 (2 weeks)** — overall: 50% | directional: 52% | reports: 40

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 46% | 41% (n=17) | 39 | 56% |
| Gold | 57% | 65% (n=20) | 40 | 56% |
| WTI Oil | 51% | 100% (n=1) | 40 | 58% |
| 10Y Treasury Yield | 52% | 100% (n=2) | 40 | 56% |
| DXY | 49% | 0% (n=1) | 40 | 55% |
| Bitcoin | 46% | 0% (n=3) | 40 | 54% |

**T+20 (1 month)** — overall: 55% | directional: 76% | reports: 30

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 60% | 75% (n=12) | 30 | 56% |
| Gold | 68% | 87% (n=15) | 30 | 56% |
| WTI Oil | 52% | 100% (n=1) | 30 | 58% |
| 10Y Treasury Yield | 52% | 100% (n=1) | 30 | 56% |
| DXY | 52% | 100% (n=1) | 30 | 55% |
| Bitcoin | 47% | 25% (n=4) | 30 | 54% |

### v1.6  (0 scored / 1 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.6 reports.*

---

## Calibration — Brier / Reliability *(WP-16.B.2)*

> **Brier**: mean squared error of stated confidence vs outcome — lower is better (0 = perfect, 0.25 = always guessing 50/50).
> **BSS** (Brier Skill Score) > 0 ⇒ the confidence numbers beat simply predicting the base rate.
> **Gap** = actual hit-rate − predicted confidence: **+ underconfident**, **− overconfident**.
> Decisive directional calls only (Neutral / flat excluded — no binary outcome to calibrate).

**Overall (all windows):** Brier **0.268** | BSS -0.117 | ECE 0.169 | base-rate 40% | n=678 — *overconfident*

**Profile A/B (WP-16 — control vs loosened):**

- **baseline**: Brier 0.274 | BSS -0.194 | ECE 0.214 | base-rate 36% | n=561
- **loosened**: Brier 0.239 | BSS -0.002 | ECE 0.058 | base-rate 61% | n=117

> ⛔ **The profile A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-08-28). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

**Arm A/B (market vs exogenous vs kimi):**

- **exogenous**: Brier 0.203 | BSS -0.458 | ECE 0.261 | base-rate 17% | n=18
- **kimi**: Brier 0.289 | BSS -0.251 | ECE 0.227 | base-rate 64% | n=83
- **market**: Brier 0.268 | BSS -0.117 | ECE 0.169 | base-rate 40% | n=678

### T+5 (1 week) — Brier 0.263 | BSS -0.059 | ECE 0.112 | n=214 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 134 | 54% | 47% | -7% (over) |
| 60-70 | 76 | 62% | 43% | -18% (over) |
| 70-80 | 4 | 70% | 50% | -20% (over) |

### T+10 (2 weeks) — Brier 0.266 | BSS -0.106 | ECE 0.177 | n=229 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 148 | 54% | 37% | -17% (over) |
| 60-70 | 77 | 62% | 43% | -19% (over) |
| 70-80 | 4 | 70% | 100% | +30% (under) |

### T+20 (1 month) — Brier 0.276 | BSS -0.213 | ECE 0.222 | n=235 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 147 | 54% | 36% | -18% (over) |
| 60-70 | 83 | 62% | 31% | -31% (over) |
| 70-80 | 5 | 70% | 60% | -10% (over) |

---

## Commitment — does the loosened arm commit *less* and *better*? *(WP-16.B.1 reframe)*

> KB-007: decisive calls are below chance, so the loosened arm (floor off) aims to **commit less**. This scores the commitment decision over *all* resolved calls (usable at low n, unlike the decisive-only Brier).
> **commit-rate** = calls made directional (not Neutral). **bull / bear** = share of *all* resolved calls made Bullish / Bearish. **bear-share** = bearish ÷ directional (~50% = symmetric; near 0 = a one-sided 'long or abstain' book that cannot call a decline — looks calibrated only while markets rise). **wrong/right-decisive** = per resolved call, a commitment that resolved wrong/right. **net edge** = right − wrong per call (KB-007 baseline < 0; higher is better).

| Arm | n resolved | commit-rate | bull | bear | bear-share | wrong-dec | right-dec | net edge | hit-rate\|decisive |
|-----|-----------:|------------:|-----:|-----:|-----------:|----------:|----------:|---------:|-------------------:|
| baseline | 1239 | 56% | 29% | 27% | 48% | 29% | 16% | -0.128 | 36% (n=561) |
| loosened | 688 | 21% | 20% | 2% | 8% | 7% | 10% | +0.036 | 61% (n=117) |

Loosened vs baseline: commit-rate -35%, wrong-decisive -22%, net edge +0.164 — _**not attributable to the arm** — the profiles share no dates, so this is a before/after on the market as much as an A/B._

> ⛔ **The commitment A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-08-28). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

> ⚠️ **One-sided book**: only 8% of the loosened arm's 146 directional calls were Bearish (11 bear / 135 bull). It abstains from the downside rather than calling it, so any decisive hit-rate is inflated by a rising-market regime and untested against a drawdown. The target arm is abstain-capable **and** symmetric — watch bear-share into the next risk-off.

> Directional read only — small loosened n. Confirm with the decisive-only Brier A/B above once it reaches n≥30.

---

## Bias Separation — does the call predict the move?

> The accuracy score cannot answer this in a trending market: Neutral is
> hard-coded to 0.5 and Bullish scores 1.0 whenever the market rises, so a
> permanently-bullish model looks skilled while saying nothing. This section
> asks the regime-robust question instead — **conditional on what the model
> said, what did the market actually do?**
>
> Returns are standardized within (window, asset), so **z** is in standard
> deviations of that asset's own move over that horizon. Positive z is always
> the direction a Bullish call claims.
>
> p-values come from a **block permutation test** (21-day blocks,
> 2000 draws) because daily reports with a T+20 horizon overlap almost
> completely. Blocks are few, so treat p as indicative — the signal to trust is
> whether the effect holds its sign across assets and horizons.
>
> Each gap also carries a **95% block-bootstrap interval** (2000
> draws). Read it before the p-value: on a short sample a high p means the
> interval is too wide to see an effect, not that there is none [KB-023].

**Arm:** `market` (114 of 139 score files).

> Arms are scored separately — they are different systems, and the score
> files share a `report_date`, so pooling them (or joining on the date)
> silently mixes them [KB-023].

| Arm | reports | resolved calls | span |
|-----|--------:|---------------:|------|
| `exogenous` | 5 | 33 | 2026-07-27 → 2026-08-24 |
| `kimi` | 20 | 240 | 2026-08-03 → 2026-08-28 |
| `market` **(this section)** | 114 | 1927 | 2026-03-13 → 2026-08-28 |

**All windows pooled (n=1927):** **inverted separation** — the label orders returns backwards (Bearish > Neutral > Bullish); it is informative, but read forward it is worse than useless

| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | 95% CI | p | Bear−Bull | p |
|--------|--:|----------:|----------:|----------:|----------:|:------:|--:|----------:|--:|
| **all** | 1927 | -0.209 (n=495) | +0.031 (n=1091) | +0.204 (n=341) | -0.239 | [-0.53, +0.08] | 0.001 | +0.413 | 0.001 |
| T+5 (1 week) | 682 | -0.145 (n=172) | +0.054 (n=395) | +0.033 (n=115) | -0.199 | [-0.43, +0.04] | 0.049 | +0.178 | 0.171 |
| T+10 (2 weeks) | 652 | -0.195 (n=168) | +0.024 (n=370) | +0.208 (n=114) | -0.219 | [-0.57, +0.14] | 0.043 | +0.403 | 0.005 |
| T+20 (1 month) | 593 | -0.294 (n=155) | +0.010 (n=326) | +0.377 (n=112) | -0.305 | [-0.60, +0.04] | 0.009 | +0.671 | 0.001 |

### By run profile *(WP-16.B conviction-floor A/B)*

> `baseline` is the untagged pre-WP-16.B population — the control the
> loosened arm is measured against.

| Profile | n | dates | Bullish z | Neutral z | Bull−Neut | 95% CI | p |
|---------|--:|------:|----------:|----------:|----------:|:------:|--:|
| `baseline` | 1239 | 69 | -0.360 (n=360) | -0.142 (n=549) | -0.218 | [-0.56, +0.08] | 0.013 |
| `loosened` | 688 | 45 | +0.195 (n=135) | +0.206 (n=542) | -0.011 | [-0.26, +0.26] | 0.929 |

> ⛔ **`baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-08-28). The profile was switched in one block, so *profile* and *market period* are the same partition of the data — no test above can tell them apart, and the rows should not be read as an A/B. Assign the profile per report-date (alternating) to make this comparison mean anything [KB-023, WP-21.B].

### Mean realized move by call, per asset *(raw %, all windows)*

| Asset | Bullish | Neutral | Bearish |
|-------|--------:|--------:|--------:|
| S&P 500 | +0.51% (n=81) | +1.25% (n=182) | +4.24% (n=57) |
| Gold | -0.07% (n=202) | -0.29% (n=111) | -4.03% (n=9) |
| WTI Oil | -6.02% (n=54) | +0.11% (n=250) | +4.14% (n=18) |
| 10Y Treasury Yield | +0.38% (n=63) | +1.11% (n=208) | +0.52% (n=51) |
| DXY | -0.03% (n=11) | -0.22% (n=168) | +0.15% (n=143) |
| Bitcoin | -4.36% (n=84) | +3.50% (n=172) | +2.58% (n=63) |

> ⚠️ **The ordering is inverted.** Realized returns run Bearish > Neutral > Bullish — the model's calls are informative but point the wrong way. This is invisible to the accuracy score, which rewards a Bullish call for any rise. Before reading it as a contrarian signal, check the per-asset table above: an inversion carried by one or two high-volatility assets, or by one stretch of the sample, is a small-sample artefact rather than a tradable edge.

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).