# Prediction Accuracy Report

*Generated: 2026-09-14 | Arm: `market` | Reports scored: 119 | Feedback-loop reports (v0.3+): 103*

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
| `exogenous` | 6 | 42 | 2026-07-27 → 2026-08-31 | — |
| `kimi` | 25 | 330 | 2026-08-03 → 2026-09-04 | — |
| `market` | 119 | 2017 | 2026-03-13 → 2026-09-04 | ✅ |

## T+5 (1 week)

**Overall accuracy:** 49%  |  **Directional:** 46%  |  **Reports:** 119

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 49% | 48% (n=42) | 118 | 55% |
| Gold | 51% | 52% (n=65) | 119 | 57% |
| WTI Oil | 47% | 33% (n=24) | 119 | 55% |
| 10Y Treasury Yield | 49% | 42% (n=19) | 119 | 56% |
| DXY | 50% | 48% (n=23) | 119 | 55% |
| Bitcoin | 46% | 40% (n=47) | 118 | 54% |

## T+10 (2 weeks)

**Overall accuracy:** 47%  |  **Directional:** 40%  |  **Reports:** 114

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 43% | 33% (n=45) | 113 | 55% |
| Gold | 48% | 47% (n=68) | 114 | 57% |
| WTI Oil | 45% | 25% (n=24) | 114 | 55% |
| 10Y Treasury Yield | 50% | 47% (n=17) | 114 | 55% |
| DXY | 46% | 37% (n=30) | 114 | 55% |
| Bitcoin | 47% | 44% (n=48) | 113 | 54% |

## T+20 (1 month)

**Overall accuracy:** 44%  |  **Directional:** 35%  |  **Reports:** 104

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 42% | 31% (n=42) | 104 | 55% |
| Gold | 43% | 39% (n=64) | 104 | 58% |
| WTI Oil | 43% | 17% (n=23) | 104 | 55% |
| 10Y Treasury Yield | 53% | 64% (n=25) | 104 | 55% |
| DXY | 45% | 37% (n=38) | 104 | 55% |
| Bitcoin | 37% | 23% (n=48) | 103 | 54% |

---

## Per-Version Accuracy (latest 5 versions)

Accuracy broken out by the 5 most recently deployed pipeline versions.
Use this to confirm that structural improvements translate into better predictions.

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

### v1.5  (50 scored / 50 total reports in this version)

**T+5 (1 week)** — overall: 50% | directional: 53% | reports: 50

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 46% | 38% (n=16) | 49 | 56% |
| Gold | 56% | 65% (n=20) | 50 | 56% |
| WTI Oil | 52% | 100% (n=2) | 50 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=2) | 50 | 56% |
| DXY | 51% | 100% (n=1) | 50 | 55% |
| Bitcoin | 46% | 0% (n=4) | 50 | 55% |

**T+10 (2 weeks)** — overall: 50% | directional: 51% | reports: 45

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 44% | 37% (n=19) | 44 | 56% |
| Gold | 57% | 65% (n=20) | 45 | 56% |
| WTI Oil | 51% | 100% (n=1) | 45 | 57% |
| 10Y Treasury Yield | 53% | 100% (n=3) | 45 | 56% |
| DXY | 49% | 0% (n=1) | 45 | 55% |
| Bitcoin | 47% | 0% (n=3) | 45 | 55% |

**T+20 (1 month)** — overall: 54% | directional: 69% | reports: 35

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 53% | 56% (n=16) | 35 | 55% |
| Gold | 67% | 88% (n=16) | 35 | 56% |
| WTI Oil | 51% | 100% (n=1) | 35 | 57% |
| 10Y Treasury Yield | 51% | 100% (n=1) | 35 | 56% |
| DXY | 51% | 100% (n=1) | 35 | 55% |
| Bitcoin | 47% | 25% (n=4) | 35 | 54% |

### v1.6  (0 scored / 3 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.6 reports.*

### v2.0  (0 scored / 2 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v2.0 reports.*

### v2.1  (0 scored / 1 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v2.1 reports.*

---

## Calibration — Brier / Reliability *(WP-16.B.2)*

> **Brier**: mean squared error of stated confidence vs outcome — lower is better (0 = perfect, 0.25 = always guessing 50/50).
> **BSS** (Brier Skill Score) > 0 ⇒ the confidence numbers beat simply predicting the base rate.
> **Gap** = actual hit-rate − predicted confidence: **+ underconfident**, **− overconfident**.
> Decisive directional calls only (Neutral / flat excluded — no binary outcome to calibrate).

**Overall (all windows):** Brier **0.268** | BSS -0.120 | ECE 0.171 | base-rate 40% | n=692 — *overconfident*

**Profile A/B (WP-16 — control vs loosened):**

- **baseline**: Brier 0.274 | BSS -0.194 | ECE 0.214 | base-rate 36% | n=561
- **loosened**: Brier 0.243 | BSS +0.008 | ECE 0.036 | base-rate 57% | n=131

> ⛔ **The profile A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

**Arm A/B (market vs exogenous vs kimi):**

- **exogenous**: Brier 0.207 | BSS -0.296 | ECE 0.230 | base-rate 20% | n=25
- **kimi**: Brier 0.321 | BSS -0.336 | ECE 0.268 | base-rate 60% | n=115
- **market**: Brier 0.268 | BSS -0.120 | ECE 0.171 | base-rate 40% | n=692

### T+5 (1 week) — Brier 0.264 | BSS -0.065 | ECE 0.116 | n=220 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 137 | 54% | 47% | -7% (over) |
| 60-70 | 79 | 62% | 43% | -19% (over) |
| 70-80 | 4 | 70% | 50% | -20% (over) |

### T+10 (2 weeks) — Brier 0.266 | BSS -0.107 | ECE 0.177 | n=232 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 151 | 54% | 37% | -17% (over) |
| 60-70 | 77 | 62% | 43% | -19% (over) |
| 70-80 | 4 | 70% | 100% | +30% (under) |

### T+20 (1 month) — Brier 0.275 | BSS -0.216 | ECE 0.225 | n=240 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 152 | 54% | 36% | -18% (over) |
| 60-70 | 83 | 62% | 31% | -31% (over) |
| 70-80 | 5 | 70% | 60% | -10% (over) |

---

## Commitment — does the loosened arm commit *less* and *better*? *(WP-16.B.1 reframe)*

> KB-007: decisive calls are below chance, so the loosened arm (floor off) aims to **commit less**. This scores the commitment decision over *all* resolved calls (usable at low n, unlike the decisive-only Brier).
> **commit-rate** = calls made directional (not Neutral). **bull / bear** = share of *all* resolved calls made Bullish / Bearish. **bear-share** = bearish ÷ directional (~50% = symmetric; near 0 = a one-sided 'long or abstain' book that cannot call a decline — looks calibrated only while markets rise). **wrong/right-decisive** = per resolved call, a commitment that resolved wrong/right. **net edge** = right − wrong per call (KB-007 baseline < 0; higher is better).

| Arm | n resolved | commit-rate | bull | bear | bear-share | wrong-dec | right-dec | net edge | hit-rate\|decisive |
|-----|-----------:|------------:|-----:|-----:|-----------:|----------:|----------:|---------:|-------------------:|
| baseline | 1239 | 56% | 29% | 27% | 48% | 29% | 16% | -0.128 | 36% (n=561) |
| loosened | 778 | 21% | 20% | 2% | 7% | 7% | 10% | +0.024 | 57% (n=131) |

Loosened vs baseline: commit-rate -35%, wrong-decisive -22%, net edge +0.152 — _**not attributable to the arm** — the profiles share no dates, so this is a before/after on the market as much as an A/B._

> ⛔ **The commitment A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

> ⚠️ **One-sided book**: only 7% of the loosened arm's 165 directional calls were Bearish (12 bear / 153 bull). It abstains from the downside rather than calling it, so any decisive hit-rate is inflated by a rising-market regime and untested against a drawdown. The target arm is abstain-capable **and** symmetric — watch bear-share into the next risk-off.

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

**Arm:** `market` (119 of 150 score files).

> Arms are scored separately — they are different systems, and the score
> files share a `report_date`, so pooling them (or joining on the date)
> silently mixes them [KB-023].

| Arm | reports | resolved calls | span |
|-----|--------:|---------------:|------|
| `exogenous` | 6 | 42 | 2026-07-27 → 2026-08-31 |
| `kimi` | 25 | 330 | 2026-08-03 → 2026-09-04 |
| `market` **(this section)** | 119 | 2017 | 2026-03-13 → 2026-09-04 |

**All windows pooled (n=2017):** **inverted separation** — the label orders returns backwards (Bearish > Neutral > Bullish); it is informative, but read forward it is worse than useless

| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | 95% CI | p | Bear−Bull | p |
|--------|--:|----------:|----------:|----------:|----------:|:------:|--:|----------:|--:|
| **all** | 2017 | -0.217 (n=513) | +0.035 (n=1162) | +0.206 (n=342) | -0.253 | [-0.52, +0.03] | 0.001 | +0.423 | 0.001 |
| T+5 (1 week) | 712 | -0.157 (n=180) | +0.056 (n=417) | +0.042 (n=115) | -0.213 | [-0.43, +0.01] | 0.019 | +0.199 | 0.128 |
| T+10 (2 weeks) | 682 | -0.182 (n=172) | +0.018 (n=395) | +0.209 (n=115) | -0.200 | [-0.53, +0.14] | 0.068 | +0.391 | 0.004 |
| T+20 (1 month) | 623 | -0.323 (n=161) | +0.030 (n=350) | +0.370 (n=112) | -0.354 | [-0.61, -0.10] | 0.002 | +0.693 | 0.001 |

### By run profile *(WP-16.B conviction-floor A/B)*

> `baseline` is the untagged pre-WP-16.B population — the control the
> loosened arm is measured against.

| Profile | n | dates | Bullish z | Neutral z | Bull−Neut | 95% CI | p |
|---------|--:|------:|----------:|----------:|----------:|:------:|--:|
| `baseline` | 1239 | 69 | -0.369 (n=360) | -0.154 (n=549) | -0.215 | [-0.56, +0.08] | 0.013 |
| `loosened` | 778 | 50 | +0.139 (n=153) | +0.205 (n=613) | -0.066 | [-0.41, +0.15] | 0.453 |

> ⛔ **`baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). The profile was switched in one block, so *profile* and *market period* are the same partition of the data — no test above can tell them apart, and the rows should not be read as an A/B. Assign the profile per report-date (alternating) to make this comparison mean anything [KB-023, WP-21.B].

### Mean realized move by call, per asset *(raw %, all windows)*

| Asset | Bullish | Neutral | Bearish |
|-------|--------:|--------:|--------:|
| S&P 500 | +0.34% (n=91) | +1.21% (n=187) | +4.24% (n=57) |
| Gold | -0.07% (n=207) | -0.45% (n=121) | -4.03% (n=9) |
| WTI Oil | -5.85% (n=55) | +0.88% (n=264) | +4.14% (n=18) |
| 10Y Treasury Yield | +0.46% (n=64) | +1.25% (n=222) | +0.52% (n=51) |
| DXY | -0.03% (n=11) | -0.25% (n=182) | +0.15% (n=144) |
| Bitcoin | -4.38% (n=85) | +3.82% (n=186) | +2.58% (n=63) |

> ⚠️ **The ordering is inverted.** Realized returns run Bearish > Neutral > Bullish — the model's calls are informative but point the wrong way. This is invisible to the accuracy score, which rewards a Bullish call for any rise. Before reading it as a contrarian signal, check the per-asset table above: an inversion carried by one or two high-volatility assets, or by one stretch of the sample, is a small-sample artefact rather than a tradable edge.

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).