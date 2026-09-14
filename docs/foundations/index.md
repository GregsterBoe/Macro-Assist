# Foundations

The background knowledge the rest of the documentation assumes. None of it is
specific to this project — absorption ratios, Brier scores and block bootstraps
exist without Macro-Assist — but every entry is written in *this project's*
terms and points at the code, reference page or Knowledge Base entry that owns
the actual number.

**What this layer is for.** A reader who meets "the OR flag's PIT top-decile
threshold" or "BSS against the base-rate reference" in a KB entry should be
able to look the phrase up here in under a minute, understand it well enough to
follow the argument, and find where to go for the full treatment.

**What it is not.** Not a source of truth for any constant, threshold or result.
Where a number appears below it is quoted to make the concept concrete, and the
owner is named beside it. If the number here and the owner disagree, the owner
is right — fix this page.

The four longer pages cover the clusters that need a formula or a worked
example; the glossary below covers everything in a paragraph.

| Page | Covers | Read it before |
|---|---|---|
| [Stress measures](stress-measures.md) | What "fragility" is measuring: variance trend, VIX term structure, absorption ratio, turbulence, drawdown labels, the composite, the OR flag | Any KB entry from KB-001 to KB-021, KB-029 to KB-032 |
| [Scoring rules](scoring-rules.md) | Brier / BSS / reliability / ECE for a probability; pinball loss, coverage and the PIT histogram for a distribution; AUC and episode recall/precision for an alarm | Any scorer, any bar, any `verdict()` |
| [Inference](inference.md) | Overlap, block bootstrap, walk-forward and embargo, point-in-time data, holdouts and seals, gates and disqualifiers, confounds, controls | Designing or reading any experiment |
| [Models](models.md) | Ridge, gradient boosting, logistic, HMM, HAR-RV, empirical and Gaussian quantiles — what each is and where it was tried | KB-004 to KB-006, KB-024, KB-033, ADR-0008 |

---

## A–Z

<div class="grid" markdown>

[Absorption ratio](#absorption-ratio) · [Alarm episode](#alarm-episode) · [Arm](#arm) · [AUC](#auc) · [Backwardation](#backwardation) · [Base rate](#base-rate) · [Block bootstrap](#block-bootstrap) · [Block permutation test](#block-permutation-test) · [Brier score](#brier-score) · [BSS](#bss) · [Bucket](#bucket) · [Calibration](#calibration) · [Composite](#composite) · [Conditional distribution](#conditional-distribution) · [Confound](#confound) · [Controls](#controls) · [Coverage](#coverage) · [Critical slowing down](#critical-slowing-down) · [Cross-section](#cross-section) · [Decisive call](#decisive-call) · [Disqualifier](#disqualifier) · [Drawdown](#drawdown) · [ECE](#ece) · [Embargo](#embargo) · [Empirical quantiles](#empirical-quantiles) · [Explore / sealed slice](#explore-sealed-slice) · [Fragility](#fragility) · [Gate](#gate) · [GBM](#gbm) · [HAR-RV](#har-rv) · [Hit-rate](#hit-rate) · [HMM](#hmm) · [Holdout](#holdout) · [Horizon](#horizon) · [Label cut-points](#label-cut-points) · [Lead time](#lead-time) · [LOCO](#loco) · [Logistic regression](#logistic-regression) · [Mahalanobis distance](#mahalanobis-distance) · [NFCI](#nfci) · [Operating point](#operating-point) · [OR mode](#or-mode) · [Overlap](#overlap) · [Pinball loss](#pinball-loss) · [PIT (two meanings)](#pit-two-meanings) · [Pre-registration](#pre-registration) · [Precision / recall](#precision-recall) · [Proper scoring rule](#proper-scoring-rule) · [Quantile](#quantile) · [Realized volatility](#realized-volatility) · [Reliability / resolution](#reliability-resolution) · [Ridge regression](#ridge-regression) · [Rival](#rival) · [Seal](#seal) · [SEP / SPF](#sep-spf) · [Shadow](#shadow) · [Skill](#skill) · [Soft-kill](#soft-kill) · [Spread (credit)](#spread-credit) · [Term structure](#term-structure) · [Turbulence](#turbulence) · [Variance trend](#variance-trend) · [Vintage](#vintage) · [VRP](#vrp) · [Walk-forward](#walk-forward) · [Yield curve](#yield-curve)

</div>

---

## Markets and stress

### Absorption ratio

The fraction of the variation in a set of asset returns that is explained by
the first few principal components — how much of the market is moving as one
thing. High or rising means diversification is breaking down and a shock
propagates. The signal used here is the *shift* (short-window AR minus
long-window AR, standardised), not the level, because AR stays high after a
crash. Kritzman, Li, Page & Rigobon (2011). Full treatment:
[Stress measures §3](stress-measures.md#3-absorption-ratio). Owner:
`fragility.absorption_ratio`; results KB-012 (no skill on five heterogeneous
assets), KB-013 (skill on a homogeneous cross-section).

### Alarm episode

A run of consecutive days on which a flag is True, with gaps of ≤ 3 days
merged into one run. Alarms and drawdown labels are both collapsed into
episodes before recall and precision are counted, so a flag that flickers for
a week is one alarm, not five.

### Backwardation

A futures or volatility curve in which the near term is priced *above* the
far term. For VIX: `VIX / VIX3M > 1` — the market is paying more for
protection this month than for the next three, which only happens under acute
stress. Normal is contango (ratio < 1). See [Term structure](#term-structure).

### Composite

The weighted mean of the available fragility components, on a 0–100 scale,
labelled *Resilient / Normal / Elevated* by fixed cut-points. Weights
renormalise over whichever components could be computed — which is the
mechanism behind the KB-029 false alarm. [Stress measures §5](stress-measures.md#5-the-composite-and-its-labels).
Owner: `fragility.fragility_index`, `DEFAULT_WEIGHTS`.

### Critical slowing down

The idea, from physics and ecology, that a system near a tipping point
recovers from perturbations more slowly, which shows up as rising lag-1
autocorrelation. The project's emergence-and-fragility track started here and
measured it: in equity returns it has no skill (WP-16.A.2/3), so the
composite is variance-led instead and `autocorr` carries weight 0.
Owner: `fragility.lag1_autocorrelation`, weight 0.0.

### Cross-section

Many assets observed on the same day, as opposed to one asset observed over
many days. Co-movement measures (absorption, turbulence) need a *homogeneous*
cross-section — many names of the same kind — to say anything; on five
assets with wildly different volatilities they measure the loudest asset
(KB-012). The project's cross-sections are the Fama–French daily industry
portfolios (backtest) and the SPDR sector ETFs (live), and KB-020 showed the
two agree at the operating point.

### Drawdown

Peak-to-trough decline. Two distinct uses here, and they must not be
confused:

- **The drawdown label** — the *target* the fragility instruments are scored
  against: does the S&P fall ≥ 5 % within the next 10 trading days?
  (`fragility_panel.drawdown_label`, defaults; horizons 5 and 10 are both
  reported). This is a forward-looking boolean.
- **The drawdown feature** — a *backward-looking input* in the numeric
  baseline: distance from the trailing 252-day high. It is the one input every
  model class finds load-bearing, signed stress → bearish, and it is why
  direction inverts (KB-024, KB-027; hypothesis H-002).

### Fragility

This project's word for *how much a shock would propagate right now* — the
susceptibility of the tape, not the direction of the next move. It is
measured by the composite and the OR flag, and validated against the
drawdown label. It deliberately does not mean "bearish": a fragile market can
rally, and the numeric baseline's inversion says it usually does.
Concept: [The signal stack](../concepts/the-signal-stack.md); measurement:
[Stress measures](stress-measures.md).

### Label cut-points

The composite values at which the label changes: Elevated ≥ 56.5 (the 90th
percentile of the composite's own 2008–2026 history), Resilient < 24.0 (40th).
Static by decision — KB-030 found the expanding point-in-time form loses two
crises because its warm-up year is 2008. Owner: `fragility._LABEL_ELEVATED`,
`_LABEL_RESILIENT`.

### Mahalanobis distance

The distance of a vector from a mean, measured in units of the covariance:
$d^2 = (r-\mu)^\top \Sigma^{-1} (r-\mu)$. A move that is large *given* recent
volatilities and correlations scores high; a large move in a direction the
assets usually move together scores low. It is the machinery inside
[Turbulence](#turbulence).

### NFCI

The Chicago Fed's National Financial Conditions Index, weekly; positive means
tighter than average. One of the three dimensions of the published bucket
(tertiles at −0.57 / −0.40, `conditional._NFCI_LOW_MID` / `_NFCI_MID_HIGH`),
and the dimension that KB-028 found was, until v2.1, effectively the only one
doing anything. It is a *revised* series, which is why it is barred from the
walk-forward baseline (ADR-0014).

### Realized volatility

The standard deviation of past returns over a window — what actually happened,
as opposed to the implied volatility a VIX-type index prices. Annualised as
$\sigma_{\text{ann}} = \sigma_{\text{daily}}\sqrt{252}$. The variance-trend
component is a slope fitted to a 20-day realized vol; `trailing_250` is a
rival built from nothing but it.

### Spread (credit)

The yield gap between risky and safe bonds of similar maturity, in percentage
points. Two series matter here: **BAA10Y** (Moody's Baa corporate yield minus
the 10-year Treasury — the canonical credit dimension of the bucket, because
FRED serves its full history) and the **HY OAS** (`BAMLH0A0HYM2`, high-yield
option-adjusted spread — richer, but the free feed serves only ~3 years, KB-021).
KB-019 found a credit channel has standalone drawdown skill and adds no recall
to the OR set.

### Term structure

The shape of a curve across maturities. For volatility, the VIX (30-day) against
the VIX3M (93-day); the component scores the fraction of the trailing 20 days
spent in backwardation. It is the strongest single fragility input and
"semi-circular" — VIX is itself a stress price — which is why its weight is
capped at 0.35. As a *stress* instrument it scored AUC 0.77 / 0.67 (KB-001); as
a *directional* input it carries nothing (KB-027). Both are true; see
[The method §11](../concepts/the-method.md#11-say-what-a-result-does-not-establish).

### Turbulence

Kritzman & Li (2010): the Mahalanobis distance of today's cross-sectional
return vector from its trailing mean, in the metric of the trailing covariance.
Reads the *surprise* of the latest observation; absorption reads the
*structure*. The two are complementary — turbulence is a recall instrument,
absorption a precision one (KB-014) — which is the reason the OR flag exists.
[Stress measures §4](stress-measures.md#4-financial-turbulence). Owner:
`fragility.turbulence_signal`.

### Variance trend

The lead component of the composite (weight 0.45): the least-squares slope of
a 20-day rolling realized vol over the trailing 60 days, divided by the mean
vol so it is a fractional change per day. Rising variance is the cleanest
non-circular fragility signal the project found. Owner:
`fragility.realized_variance_trend`.

### VRP

Variance risk premium: implied minus expected realized variance,
`VIX² − HAR-RV forecast`, annualised. Positive means the market is paying up
for protection relative to what realized vol suggests. Shown for the S&P in the
note; depends on the HAR-RV forecast, whose live wiring KB-033 found degenerate.
Owner: `vol_forecast.py`.

### Yield curve

The 10-year minus 2-year Treasury yield, in basis points. Its *sign* is one of
the three bucket dimensions (`YC:positive` / `YC:inverted`); an inverted curve
is the classic recession signal. In the regime features it enters as the raw
slope.

---

## Scoring

### Arm

One forecaster among several scored on the same observations. In
`score_distributions.py` the arms are `published`, `unconditional`,
`trailing_250`, `har_gaussian`; in `numeric_baseline.py` they are the model
classes and the comparators. An experiment's claim is always "arm A beats arm
B on the shared sample", never a lone number.

### AUC

Area under the ROC curve; equivalently, the probability that a randomly chosen
positive scores higher than a randomly chosen negative (Mann–Whitney). 0.5 is
no skill, 1.0 perfect, below 0.5 inverted. Threshold-free, so it says nothing
about *where* to set an alarm — which is why the fragility work reports episode
recall and precision beside it. [Scoring rules §4](scoring-rules.md#4-scoring-an-alarm-auc-recall-precision-lead).
Owner: `fragility_backtest.auc`, `subsample_auc` (the de-overlapped form).

### Base rate

The unconditional frequency of the outcome in the sample — the fraction of
windows in which the asset went up. The reference forecast for BSS is the
constant base rate of the *same* sample, so `always_bullish` is not an
arbitrary straw man; it is the forecaster that knows only this number. In a
bull-market sample the base rate alone produces a hit-rate above 0.5, which is
the confound KB-022 isolated.

### Brier score

Mean squared error of a probability forecast against a 0/1 outcome:
$\frac{1}{n}\sum (p_i - o_i)^2$. Lower is better; 0.25 is what "always 50 %"
scores. Proper, so honest probabilities minimise it. Decomposes into
reliability − resolution + uncertainty, which is the vocabulary KB-026 uses.
[Scoring rules §1](scoring-rules.md#1-scoring-a-probability-brier-bss-reliability).
Owner: `summarize_accuracy._brier_and_reliability`.

### BSS

Brier skill score: $1 - \text{Brier} / \text{Brier}_{\text{ref}}$ where the
reference is the constant base-rate forecast, $r(1-r)$. Zero means "no better
than knowing the base rate"; negative means worse. The numeric bar requires
BSS > 0.02 *and* a block-bootstrap interval that excludes zero
(`EDGE_MIN_BSS`, ADR-0020). Every model this project has scored is negative.

### Calibration

Whether stated confidence matches realised frequency: of the calls made at
"80 %", did 80 % come true? Shown as a reliability table (bins of confidence
vs hit-rate) and summarised by ECE. A forecaster can be well calibrated and
useless (always say the base rate) or discriminating and badly calibrated
(the SPF anchor, KB-026). [Scoring rules §1](scoring-rules.md#1-scoring-a-probability-brier-bss-reliability).

### Coverage

The fraction of realisations that landed inside the published P25–P75
interval. Nominal is 0.50; persistently above means the interval is too wide,
below too narrow. Pools across assets because it is unitless. Owner:
`score_distributions._coverage`.

### Decisive call

A directional call that was scored as simply right or wrong (`score ∈ {0, 1}`),
as opposed to a neutral or hedged one. Brier, BSS and reliability are computed
on decisive calls only; the bar requires n ≥ 30 of them. Historical — the
directional product is cut — but every KB entry before KB-028 is written in
these terms.

### ECE

Expected calibration error: the confidence-weighted mean absolute gap between
stated confidence and realised hit-rate across the reliability bins,
$\sum_b \frac{n_b}{n}\,|\text{hit}_b - \text{conf}_b|$. Bins here are
`[0,50,60,70,80,90,100]`. A gap sign convention: + underconfident,
− overconfident. Owner: `summarize_accuracy.CALIB_BIN_EDGES`.

### Empirical quantiles

Quantiles read directly off the sorted historical sample, no distributional
assumption. This is how the published P25 / P50 / P75 are built: sort every
historical forward change in the bucket, take the 25th / 50th / 75th
percentile. Contrast `har_gaussian`, which assumes a normal shape with a
forecast width. Owner: `score_distributions._empirical_quantiles`,
`conditional.py`.

### Hit-rate

Fraction of decisive calls that were right. The crudest metric and the most
misleading in a trending market, because the base rate sets its floor; the bar
requires > 0.52 only as a sanity gate beneath BSS. Also used per reliability
bin.

### Pinball loss

The proper scoring rule for a single quantile forecast. For quantile level $q$,
forecast $f$, realisation $y$:
$L_q = q\,(y-f)$ if $y \ge f$, else $(q-1)\,(y-f)$. Asymmetric on purpose —
the median is punished symmetrically, P75 is punished more for being *below*
the realisation than above. Minimised in expectation only by the true
quantile, so it cannot be gamed by shading the interval. It is "the
distribution product's Brier". [Scoring rules §2](scoring-rules.md#2-scoring-a-distribution-pinball-coverage-pit).
Owner: `score_distributions.pinball_loss`.

### PIT (two meanings)

The repository uses `PIT` for two unrelated things; the context always
disambiguates, but a new reader will be caught once.

- **Point-in-time** — data as it was knowable on the date, not as later
  revised. `_pit_backtest`, `pit_label_cuts`, `test_point_in_time.py`,
  ADR-0014. See [Inference §4](inference.md#4-point-in-time-data).
- **Probability integral transform** — where a realisation fell in the
  forecast distribution; a calibrated forecast makes it uniform. With three
  published quantiles this is a four-bin histogram, 25 % each if calibrated.
  `score_distributions.pit_bin`. See [Scoring rules §2](scoring-rules.md#2-scoring-a-distribution-pinball-coverage-pit).

### Precision / recall

For an alarm: **recall** = fraction of real drawdown episodes the alarm
overlapped; **precision** = fraction of alarm episodes that overlapped a real
drawdown. Counted at the *episode* level (runs of days collapsed, gaps ≤ 3
merged) so the denominators are small honest integers rather than inflated
day counts. The OR flag trades precision for recall by design: precision ≈ 0.3
"is the operating point of a recall mode, not a defect" (KB-031). Owner:
`fragility_panel.episode_scoring`.

### Proper scoring rule

A scoring rule that a forecaster minimises, in expectation, only by reporting
their true belief. Brier is proper for probabilities; pinball is proper for
quantiles; hit-rate is *not* proper (it rewards rounding every call to the
likelier side). The project scores only with proper rules and treats hit-rate
as a gate, not a target.

### Quantile

The value below which a given fraction of the distribution lies. P25, P50
(median) and P75 are the three the product publishes; their spread P75 − P25
is the interquartile *width*, which is the target space the hypothesis
register aims at.

### Reliability / resolution

The two informative terms of the Brier decomposition. **Reliability** (lower
is better) is the calibration gap — how far the stated probabilities are from
the observed frequencies in each bin. **Resolution** (higher is better) is how
much the observed frequencies differ *between* bins — whether the forecaster's
confidence sorts outcomes at all. KB-026's SPF anchor had real resolution and a
reliability penalty large enough to swamp it; the model arms had neither.

### Rival

The trivial comparator every product is scored next to: `always_bullish` for
a directional call, `unconditional` (the same asset's full-history quantiles,
no bucket) and `trailing_250` (the last 250 days, no bucket) for a
distribution. Method rule: "a product with no trivial comparator will score as
skilled" ([The method §4](../concepts/the-method.md#4-always-put-a-trivial-rival-next-to-the-product)).

### Skill

Improvement over a named rival on the shared sample, as a fraction: for
distributions `1 − pinball(arm) / pinball(rival)`, for probabilities the BSS.
Always a *relative* number; "skill" with no rival named is not a claim this
project makes. Owner: `score_distributions.skill_vs`.

---

## Inference

### Block bootstrap

Resampling for a confidence interval when observations are serially
correlated: resample contiguous *blocks* of dates (here 21 trading days,
`BLOCK_DAYS`) with replacement rather than single days, so each draw keeps the
within-block dependence. Used for the BSS and skill intervals; the block count
is reported next to every interval because with months of data it is single
digits. [Inference §2](inference.md#2-block-bootstrap-and-block-permutation).

### Block permutation test

The hypothesis-testing sibling: to test whether two labels' forward returns
differ, shuffle the labels across contiguous 21-day blocks (not across days)
and count how often the shuffled gap exceeds the observed one. That count is
the p-value. Owner: `bias_separation.block_permutation`; shares `BLOCK_DAYS`
with the scorer by test.

### Bucket

The conditioning cell the published distribution is drawn from — a label like
`NFCI:low|YC:positive|CREDIT:tight`, 3 × 2 × 3 = 18 cells over 26 years since
v2.1, falling back to a coarser parent when the cell is thin (`min_n`).
KB-028 is the cautionary tale of a bucket that was not what it said. Owner:
`conditional.assign_bucket`.

### Conditional distribution

The distribution of forward returns *given* today's bucket, as opposed to the
unconditional distribution over all history. The live product is exactly this,
and its entire claim is that conditioning on the bucket beats not conditioning
— which Phase 22 measures and has not yet read.

### Confound

A third variable that produces the observed relationship without the claimed
mechanism. The project's standing example: a bull-market sample makes any
label that fires less often in down-markets look predictive (KB-022); arm and
period were perfectly confounded in KB-023. Every hypothesis-register entry
must name its confound before it is finished.

### Controls

A **positive control** is a planted signal the harness must detect; a
**negative control** is a setting where the rival is the truth and the harness
must report ≈ 0 skill. Both live in the test suite. A null from a harness with
no positive control is uninterpretable. [Inference §7](inference.md#7-controls).

### Disqualifier

A condition evaluated *before* the skill number that returns its own verdict:
`underpowered` (too few blocks), `miscalibrated`, `inverted` (the ordering is
backwards). Disqualifiers first is the fix for the KB-027 hole, where a
positive BSS let an inverted arm reach `edge`. Each has a test asserting it
fires ahead of a strong skill number.

### Embargo

The gap between the last training row and the prediction date in a
walk-forward fit: `horizon + 1` trading days, so no training label's forward
window overlaps the date being predicted. Without it the fit sees the answer
through the overlapping window. Owner: `numeric_baseline.walk_forward`.

### Explore / sealed slice

The two halves of a sample separated by code: the explore slice may be looked
at freely and can only ever yield `exploratory`; the sealed slice is read once,
against a bar written before the read. `numeric_baseline.SEAL_START =
2018-01-01`; `score_distributions.SEAL_START = 2026-09-07`. The rule that
turns this into a research process is [How we explore](../concepts/how-we-explore.md).

### Gate

Overloaded in this repository; four senses, all "a check something must pass":

1. **The input-testing gate** — `input_testing.evaluate_signal`: a candidate
   fragility input must show de-overlapped AUC and episode recall/precision
   before it is wired even as a shadow (IMP-1).
2. **The verdict gate** — `verdict()` in a scorer: disqualifiers, then the
   skill clause with margin. This is the "bar".
3. **The version gate** — `score_predictions.py` refuses to score notes from
   v1.6+ (ADR-0010).
4. **The competence gate** — the six-item self-check in
   [How we explore §6](../concepts/how-we-explore.md), a reading gate for a
   person, not a number.

### Holdout

Data the fit never saw, kept for an honest read. A holdout that has been
*looked at* — even without fitting — is no longer one; that is the difference
between a holdout and a seal.

### Horizon

Trading days between the note and the outcome it is scored on. The product
publishes 5 (`PUBLISHED_HORIZON`); the scorers read 5, 10, 20 (`t5`, `t10`,
`t20`). Longer horizons overlap more and so have fewer independent blocks.

### Lead time

Days between an alarm's first firing and the start of the drawdown episode it
caught. Reported with recall and precision; an alarm with zero lead is a
coincident indicator, not a warning.

### LOCO

Leave-one-crisis-out cross-validation: the drawdown episodes are the folds.
Fit thresholds or aggregators on every episode but one, test on the held-out
one, rotate. The honest way to tune anything on a sample with ~a dozen crises.
KB-017 and KB-031 are LOCO results. Owner: `aggregator_testing.py`,
`input_testing._loco_recall`.

### Operating point

The specific threshold at which an alarm is run — here, "top decile of the
channel's own prior history" (`_Q = 0.90`, min 252 prior readings). Two
alarms are compared *at held recall* or *at held precision*: fix one axis, read
the other. Comparing AUCs alone can favour a curve that is worse at the point
you actually operate (KB-016).

### OR mode

The live high-recall fragility flag: fires if **any** of three channels
(composite, absorption ratio, turbulence) is at or above its own point-in-time
90th percentile. A *mode*, not a blended weight (ADR-0006), because blending
lifts AUC and degrades the top-decile flag. [Stress measures §6](stress-measures.md#6-the-or-flag).
Owner: `fragility_or.py`.

### Overlap

Two daily observations at a 20-day horizon share 19 of their 20 days, so they
are almost the same observation. Raw `n` overstates the evidence by roughly the
horizon. Every significance statement here uses blocks for this reason.
[Inference §1](inference.md#1-overlap-is-not-sample-size).

### Pre-registration

Writing the metric, threshold, sample and the meaning of each outcome, and
committing it, before the numbers exist. The only thing that distinguishes
fixing a bar from moving a goalpost. [The method §2](../concepts/the-method.md#2-pre-register-the-read-before-the-run).

### Seal

A pre-registration plus a holdout that did not exist, or had never been
looked at, when the bar was written — with the date recorded. Phase 22's bar
was written in the one window when the interval record had zero resolved
observations. [Inference §5](inference.md#5-holdouts-and-seals).

### Shadow

Computed and logged, zero effect on what is published. The mode-ladder rung
between "tested offline" and "live" (ADR-0005): absorption is a shadow
component (weight 0.0), the OR flag was a shadow flag before it went live, and
a *shadow conditioner* is the harness the hypothesis register proposes.

### Soft-kill

Deactivate, never delete (ADR-0015): the stage leaves `pipeline.yml`; the
module, tests, history and manual trigger stay.

### Vintage

The version of a revised data series as it stood on a given date. ALFRED
serves historical vintages of FRED series; FRED serves only the latest. A
backtest that reads today's vintage of a revised series (CPI, NFCI, the SEP
median) is reading the future. [Inference §4](inference.md#4-point-in-time-data).

### Walk-forward

Refit on data up to `t − embargo`, predict `t`, step forward, repeat.
Every out-of-sample number in the KB is walk-forward; a full-sample fit is
reported only as the labelled in-sample counterpart (KB-003 is the lesson).

---

## Models and data

### GBM

Gradient-boosted machine — an ensemble of shallow decision trees, each fitted
to the residual of the previous. Non-linear, interaction-aware, the standard
"if a signal exists, this will find it" baseline. Here: 150 trees, depth 2,
learning rate 0.03. KB-024: loses to `always_bullish` like everything else.
[Models](models.md).

### HAR-RV

Heterogeneous autoregressive realized variance (Corsi 2009):
$RV_{t+1} = \beta_0 + \beta_1 RV_{d} + \beta_2 RV_{w} + \beta_3 RV_{m}$ — tomorrow's
variance regressed on daily, weekly and monthly averages of past variance.
Four parameters; needs ~1000 returns to fit (`HAR_MIN_RETURNS`, after KB-033
found it degenerate on a few dozen). Feeds the VRP and the `har_gaussian`
rival.

### HMM

Hidden Markov model: assumes an unobserved regime that switches with fixed
transition probabilities and emits the observed features. Fitted on four macro
features to label regimes; retired from the note (ADR-0004) after KB-004 to
KB-006 found no out-of-sample skill and a four-feature rule beat it.

### Logistic regression

A linear model for a probability: $P(y=1) = \sigma(\beta^\top x)$. The
three-parameter aggregator KB-031 tried on the OR channels; lost crises under
LOCO.

### Ridge regression

Linear regression with an $L_2$ penalty on the coefficients, which keeps a fit
stable when features are correlated or many. The linear baseline in
`numeric_baseline.py`; also the model behind `exogenous_spf`.

### SEP / SPF

**SEP** — the FOMC's Summary of Economic Projections, quarterly since 2012,
the "dots"; FRED serves only the current vintage (`FEDTARMD`). **SPF** — the
Philadelphia Fed's Survey of Professional Forecasters, quarterly consensus of
private economists. Phase 19's thesis is the *gap* between them (hypothesis
H-003); KB-026 scored only the SPF half, for direction, and found none.
