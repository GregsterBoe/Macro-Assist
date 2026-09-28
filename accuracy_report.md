# Prediction Accuracy Report

*Generated: 2026-09-28 | Arm: `market` | Reports scored: 119 | Feedback-loop reports (v0.3+): 103*

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
| `exogenous` | 6 | 51 | 2026-07-27 → 2026-08-31 | — |
| `kimi` | 25 | 420 | 2026-08-03 → 2026-09-04 | — |
| `market` | 119 | 2106 | 2026-03-13 → 2026-09-04 | ✅ |

## T+5 (1 week)

**Overall accuracy:** 49%  |  **Directional:** 46%  |  **Reports:** 119

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 49% | 48% (n=42) | 118 | 55% |
| Gold | 52% | 53% (n=68) | 119 | 57% |
| WTI Oil | 47% | 33% (n=24) | 119 | 55% |
| 10Y Treasury Yield | 49% | 42% (n=19) | 119 | 56% |
| DXY | 50% | 48% (n=23) | 119 | 55% |
| Bitcoin | 46% | 40% (n=47) | 118 | 54% |

## T+10 (2 weeks)

**Overall accuracy:** 46%  |  **Directional:** 39%  |  **Reports:** 119

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 42% | 31% (n=48) | 118 | 55% |
| Gold | 46% | 44% (n=71) | 119 | 57% |
| WTI Oil | 45% | 28% (n=25) | 119 | 55% |
| 10Y Treasury Yield | 50% | 47% (n=17) | 119 | 56% |
| DXY | 47% | 37% (n=30) | 119 | 55% |
| Bitcoin | 47% | 43% (n=49) | 118 | 54% |

## T+20 (1 month)

**Overall accuracy:** 44%  |  **Directional:** 34%  |  **Reports:** 114

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 43% | 32% (n=44) | 113 | 55% |
| Gold | 41% | 35% (n=69) | 114 | 57% |
| WTI Oil | 43% | 17% (n=23) | 114 | 55% |
| 10Y Treasury Yield | 54% | 67% (n=27) | 114 | 55% |
| DXY | 45% | 37% (n=41) | 114 | 55% |
| Bitcoin | 38% | 23% (n=48) | 113 | 54% |

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

**T+10 (2 weeks)** — overall: 44% | directional: 33% | reports: 20

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=2) | 20 | 51% |
| Gold | 25% | 19% (n=16) | 20 | 56% |
| WTI Oil | 45% | 0% (n=2) | 20 | 52% |
| 10Y Treasury Yield | 48% | 40% (n=5) | 20 | 55% |
| DXY | 38% | 22% (n=9) | 20 | 52% |
| Bitcoin | 57% | 64% (n=11) | 20 | 52% |

**T+20 (1 month)** — overall: 40% | directional: 24% | reports: 20

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 50% | 50% (n=2) | 20 | 51% |
| Gold | 22% | 18% (n=17) | 20 | 56% |
| WTI Oil | 45% | 0% (n=2) | 20 | 52% |
| 10Y Treasury Yield | 52% | 55% (n=11) | 20 | 55% |
| DXY | 32% | 0% (n=7) | 20 | 52% |
| Bitcoin | 35% | 20% (n=10) | 20 | 52% |

### v1.5  (50 scored / 50 total reports in this version)

**T+5 (1 week)** — overall: 51% | directional: 54% | reports: 50

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 46% | 38% (n=16) | 49 | 56% |
| Gold | 57% | 67% (n=21) | 50 | 56% |
| WTI Oil | 52% | 100% (n=2) | 50 | 57% |
| 10Y Treasury Yield | 52% | 100% (n=2) | 50 | 56% |
| DXY | 51% | 100% (n=1) | 50 | 55% |
| Bitcoin | 46% | 0% (n=4) | 50 | 55% |

**T+10 (2 weeks)** — overall: 49% | directional: 45% | reports: 50

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 42% | 32% (n=22) | 49 | 56% |
| Gold | 52% | 54% (n=24) | 50 | 56% |
| WTI Oil | 52% | 100% (n=2) | 50 | 57% |
| 10Y Treasury Yield | 53% | 100% (n=3) | 50 | 56% |
| DXY | 49% | 0% (n=1) | 50 | 55% |
| Bitcoin | 46% | 0% (n=4) | 50 | 55% |

**T+20 (1 month)** — overall: 52% | directional: 61% | reports: 45

| Asset | Accuracy | Directional | n | Avg Confidence |
|-------|----------|-------------|---|----------------|
| S&P 500 | 52% | 56% (n=18) | 44 | 56% |
| Gold | 58% | 68% (n=19) | 45 | 56% |
| WTI Oil | 51% | 100% (n=1) | 45 | 57% |
| 10Y Treasury Yield | 53% | 100% (n=3) | 45 | 56% |
| DXY | 50% | 50% (n=4) | 45 | 55% |
| Bitcoin | 48% | 25% (n=4) | 45 | 55% |

### v1.6  (0 scored / 3 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v1.6 reports.*

### v2.0  (0 scored / 2 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v2.0 reports.*

### v2.1  (0 scored / 11 total reports in this version)

*No scored predictions yet — T+5 window has not closed on any v2.1 reports.*

---

## Calibration — Brier / Reliability *(WP-16.B.2)*

> **Brier**: mean squared error of stated confidence vs outcome — lower is better (0 = perfect, 0.25 = always guessing 50/50).
> **BSS** (Brier Skill Score) > 0 ⇒ the confidence numbers beat simply predicting the base rate.
> **Gap** = actual hit-rate − predicted confidence: **+ underconfident**, **− overconfident**.
> Decisive directional calls only (Neutral / flat excluded — no binary outcome to calibrate).

**Overall (all windows):** Brier **0.269** | BSS -0.128 | ECE 0.177 | base-rate 39% | n=715 — *overconfident*

**Profile A/B (WP-16 — control vs loosened):**

- **baseline**: Brier 0.274 | BSS -0.196 | ECE 0.217 | base-rate 36% | n=564
- **loosened**: Brier 0.249 | BSS +0.000 | ECE 0.028 | base-rate 53% | n=151

> ⛔ **The profile A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

**Arm A/B (market vs exogenous vs kimi):**

- **exogenous**: Brier 0.204 | BSS -0.045 | ECE 0.175 | base-rate 27% | n=30
- **kimi**: Brier 0.336 | BSS -0.369 | ECE 0.303 | base-rate 57% | n=145
- **market**: Brier 0.269 | BSS -0.128 | ECE 0.177 | base-rate 39% | n=715

### T+5 (1 week) — Brier 0.263 | BSS -0.059 | ECE 0.114 | n=223 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 140 | 54% | 46% | -8% (over) |
| 60-70 | 78 | 62% | 44% | -18% (over) |
| 70-80 | 5 | 70% | 60% | -10% (over) |

### T+10 (2 weeks) — Brier 0.268 | BSS -0.130 | ECE 0.191 | n=240 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 155 | 54% | 36% | -18% (over) |
| 60-70 | 81 | 62% | 42% | -20% (over) |
| 70-80 | 4 | 70% | 100% | +30% (under) |

### T+20 (1 month) — Brier 0.275 | BSS -0.224 | ECE 0.228 | n=252 — *overconfident*

| Confidence bin | n | Predicted | Actual | Gap |
|----------------|---|-----------|--------|-----|
| 50-60 | 163 | 54% | 34% | -20% (over) |
| 60-70 | 84 | 62% | 32% | -30% (over) |
| 70-80 | 5 | 70% | 60% | -10% (over) |

---

## Commitment — does the loosened arm commit *less* and *better*? *(WP-16.B.1 reframe)*

> KB-007: decisive calls are below chance, so the loosened arm (floor off) aims to **commit less**. This scores the commitment decision over *all* resolved calls (usable at low n, unlike the decisive-only Brier).
> **commit-rate** = calls made directional (not Neutral). **bull / bear** = share of *all* resolved calls made Bullish / Bearish. **bear-share** = bearish ÷ directional (~50% = symmetric; near 0 = a one-sided 'long or abstain' book that cannot call a decline — looks calibrated only while markets rise). **wrong/right-decisive** = per resolved call, a commitment that resolved wrong/right. **net edge** = right − wrong per call (KB-007 baseline < 0; higher is better).

| Arm | n resolved | commit-rate | bull | bear | bear-share | wrong-dec | right-dec | net edge | hit-rate\|decisive |
|-----|-----------:|------------:|-----:|-----:|-----------:|----------:|----------:|---------:|-------------------:|
| baseline | 1239 | 56% | 29% | 27% | 48% | 29% | 16% | -0.131 | 36% (n=564) |
| loosened | 867 | 22% | 20% | 2% | 8% | 8% | 9% | +0.010 | 53% (n=151) |

Loosened vs baseline: commit-rate -34%, wrong-decisive -21%, net edge +0.141 — _**not attributable to the arm** — the profiles share no dates, so this is a before/after on the market as much as an A/B._

> ⛔ **The commitment A/B is confounded: `baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). `MACRO_PROFILE` was switched in one block, so the profile split *is* a time split — the rows differ by market period as much as by prompt. Assign the profile per report-date (alternating) before reading this as an A/B [KB-023, WP-21.B].

> ⚠️ **One-sided book**: only 8% of the loosened arm's 187 directional calls were Bearish (15 bear / 172 bull). It abstains from the downside rather than calling it, so any decisive hit-rate is inflated by a rising-market regime and untested against a drawdown. The target arm is abstain-capable **and** symmetric — watch bear-share into the next risk-off.

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
| `exogenous` | 6 | 51 | 2026-07-27 → 2026-08-31 |
| `kimi` | 25 | 420 | 2026-08-03 → 2026-09-04 |
| `market` **(this section)** | 119 | 2106 | 2026-03-13 → 2026-09-04 |

**All windows pooled (n=2106):** **inverted separation** — the label orders returns backwards (Bearish > Neutral > Bullish); it is informative, but read forward it is worse than useless

| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | 95% CI | p | Bear−Bull | p |
|--------|--:|----------:|----------:|----------:|----------:|:------:|--:|----------:|--:|
| **all** | 2106 | -0.216 (n=532) | +0.040 (n=1229) | +0.189 (n=345) | -0.256 | [-0.52, +0.02] | 0.001 | +0.405 | 0.001 |
| T+5 (1 week) | 712 | -0.153 (n=180) | +0.055 (n=417) | +0.042 (n=115) | -0.208 | [-0.44, +0.02] | 0.022 | +0.195 | 0.140 |
| T+10 (2 weeks) | 712 | -0.188 (n=180) | +0.028 (n=417) | +0.195 (n=115) | -0.216 | [-0.55, +0.15] | 0.029 | +0.383 | 0.002 |
| T+20 (1 month) | 682 | -0.310 (n=172) | +0.038 (n=395) | +0.331 (n=115) | -0.348 | [-0.61, -0.10] | 0.003 | +0.641 | 0.001 |

### By run profile *(WP-16.B conviction-floor A/B)*

> `baseline` is the untagged pre-WP-16.B population — the control the
> loosened arm is measured against.

| Profile | n | dates | Bullish z | Neutral z | Bull−Neut | 95% CI | p |
|---------|--:|------:|----------:|----------:|----------:|:------:|--:|
| `baseline` | 1239 | 69 | -0.384 (n=360) | -0.173 (n=549) | -0.211 | [-0.56, +0.08] | 0.014 |
| `loosened` | 867 | 50 | +0.137 (n=172) | +0.212 (n=680) | -0.075 | [-0.52, +0.11] | 0.347 |

> ⛔ **`baseline` and `loosened` share zero report-dates** (`baseline`: 2026-03-13 → 2026-06-26; `loosened`: 2026-06-29 → 2026-09-04). The profile was switched in one block, so *profile* and *market period* are the same partition of the data — no test above can tell them apart, and the rows should not be read as an A/B. Assign the profile per report-date (alternating) to make this comparison mean anything [KB-023, WP-21.B].

### Mean realized move by call, per asset *(raw %, all windows)*

| Asset | Bullish | Neutral | Bearish |
|-------|--------:|--------:|--------:|
| S&P 500 | +0.28% (n=99) | +1.15% (n=193) | +4.24% (n=57) |
| Gold | -0.04% (n=213) | -0.64% (n=130) | -4.15% (n=9) |
| WTI Oil | -5.44% (n=56) | +1.59% (n=278) | +4.14% (n=18) |
| 10Y Treasury Yield | +0.70% (n=66) | +1.50% (n=235) | +0.52% (n=51) |
| DXY | +0.08% (n=12) | -0.18% (n=193) | +0.17% (n=147) |
| Bitcoin | -4.40% (n=86) | +4.01% (n=200) | +2.58% (n=63) |

> ⚠️ **The ordering is inverted.** Realized returns run Bearish > Neutral > Bullish — the model's calls are informative but point the wrong way. This is invisible to the accuracy score, which rewards a Bullish call for any rise. Before reading it as a contrarian signal, check the per-asset table above: an inversion carried by one or two high-volatility assets, or by one stretch of the sample, is a small-sample artefact rather than a tradable edge.

---

## Calibration Notes

- **50%** = coin-flip — no signal value
- **55-60%** = weak signal, worth monitoring
- **>65%** with n>10 = genuine predictive value
- **<40%** = systematic bias; consider reversing the signal

Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.
Neutral calls always score 0.5 (excluded from directional accuracy).