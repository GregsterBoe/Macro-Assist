# Inference

The statistical discipline behind every number in the Knowledge Base. The
[method](../concepts/the-method.md) states the rules; this page explains the
mechanics they rest on — why overlapping days are not independent, what a
block bootstrap does, what makes data point-in-time, and what "sealed" means
in code. Read this before designing an experiment or trusting a p-value here.

The data has three properties that break textbook inference, and every
technique below is a response to one of them:

1. **Observations overlap** — daily forecasts of 5–20-day windows.
2. **Inputs get revised** — most macro series are restated after release.
3. **There is one history** — you cannot rerun 2008, and once you have
   looked at a sample it is no longer a holdout.

---

## 1. Overlap is not sample size

A forecast made on Monday for the next 20 trading days and one made on Tuesday
share 19 of their 20 days. Their outcomes are almost the same number. Ten
years of daily 20-day forecasts is ~2,500 rows and roughly **125** independent
windows. At a 5-day horizon, ~500.

Treating the rows as independent inflates every test statistic by about
$\sqrt{h}$ and makes p-values meaningless — a 0.001 on 2,500 overlapping
observations is a 0.1 on the honest count. The project's answers:

- **Report the block count** beside every interval and p-value. When it is a
  single digit, the write-up says the number is indicative and the signal to
  trust is consistency across assets and horizons.
- **Resample and permute in blocks** (§2).
- **Subsample for AUC** — every `h`-th day, so windows do not overlap
  (`fragility_backtest.subsample_auc`).
- **Count episodes, not days**, for alarms
  ([Scoring rules §4](scoring-rules.md#4-scoring-an-alarm-auc-recall-precision-lead)).

## 2. Block bootstrap and block permutation

**Bootstrap** — the general idea: to get a confidence interval for a statistic
without assuming a distribution, resample the data with replacement many
times, recompute the statistic each time, and read the interval off the spread
of results. With serially correlated data, resampling single rows destroys the
correlation and gives an interval that is too narrow.

**Block bootstrap** resamples contiguous runs of dates instead. Here the dates
are cut into 21-trading-day blocks (`BLOCK_DAYS`, one calendar month), blocks
are drawn with replacement until the original length is reached, the
statistic (BSS, or skill vs a rival) is recomputed, and the 2.5th and 97.5th
percentiles of 2,000 draws are the interval
(`score_distributions.block_bootstrap`, `numeric_baseline` for BSS).

The bar's second clause is that this interval **excludes zero**. That clause
is what stops a +0.003 on a few months of data being called an edge — the
point estimate can be positive while the interval comfortably straddles zero,
and KB-027's family 1 was exactly that.

**Block permutation** answers a different question: do two labels' forward
returns differ? Under the null they are exchangeable, so shuffle the labels
across 21-day blocks (keeping each block's labels together), recompute the gap,
repeat 2,000 times; the p-value is the fraction of shuffles whose gap is at
least the observed one (`bias_separation.block_permutation`). Shuffling
individual days would treat ~2,000 rows as ~2,000 draws and produce p-values
that are wrong by the same factor as above.

The two modules share the `BLOCK_DAYS` constant and a test asserts they do —
two analyses of the same overlap cannot disagree about what counts as
independent.

**How few blocks is too few:** `MIN_BLOCKS = 8` in the distribution scorer
returns `underpowered` before any skill number is read. Eight monthly blocks is
the floor at which an interval means anything; Phase 22 reaches it around
May 2027.

## 3. Walk-forward, and the embargo

A **walk-forward** fit refits the model at each date using only data before
it, predicts that date, and moves on. Every out-of-sample number in the KB is
walk-forward. The full-sample fit — one model, all history — is reported only
as the explicitly labelled in-sample counterpart, because it has seen the
answers. KB-003 is the lesson: HMM regime labels that looked clean full-sample
were startprob-dominated when inferred one point at a time.

The subtle part is **which rows count as "before"**. A training row dated
$d$ carries a label that only resolved at $d + h$. If the model predicting
date $t$ trains on rows up to $t - 1$, it trains on labels that reach into
$[t, t + h - 1]$ — it has partially seen the outcome it is predicting. The
**embargo** removes those rows: training stops at $t - (h + 1)$
(`numeric_baseline.walk_forward`; "the embargo is the whole point").

A related trap on the *feature* side is a **date proxy**: any feature that
increases monotonically with time (a raw date, an ever-growing count) lets a
model learn "later = bull market" without learning anything about markets.
The baseline's feature builder is checked for this.

## 4. Point-in-time data

A backtest is point-in-time (**PIT** — the data sense, not the probability
integral transform; see the [glossary](index.md#pit-two-meanings)) when every
input is the value that was *knowable on that date*. Two things break this:

**Revisions.** Most macro series are restated: CPI, payrolls, GDP, NFCI, M2,
the SEP median rate (`FEDTARMD`). FRED serves the *current* vintage — today's
best estimate of what 2015's value was — and a backtest reading it is reading
the future. ALFRED serves historical vintages, but a decade of daily
walk-forward is ~40,000 requests. The project's route (ADR-0014): **only
never-revised series are eligible** — prices and FRED's market-observed daily
series (yields, spreads, VIX). For those, the current vintage *is* the
historical vintage, by construction. The honest cost: the baseline excludes
CPI, payrolls, M2, WALCL, NFCI and claims, and a null is a null about the
eligible panel.

**Release lag.** A series dated Monday may not be published until Tuesday
afternoon. Every series is shifted one business day, so a print is readable
the day after it lands — and `test_point_in_time.py` makes real ALFRED calls
to check the shift holds, which is why it is not marked `integration` and runs
by default.

**PIT thresholds.** The same discipline applies to cut-points: the OR flag's
"top decile" for a channel on date $t$ is the 90th percentile of that
channel's readings *strictly before* $t$, expanding, with a 252-reading
warm-up (`fragility_or._pit_backtest`). A cut computed on full history would
know the future's distribution. KB-030 measured the cost of applying this to
the composite label and kept the static cut on purpose — the discipline is
the default, not a law.

## 5. Holdouts and seals

A **holdout** is data the fit never touched. A **sealed** holdout is stronger:
data that did not exist, or had never been *looked at* by anyone, when the bar
was written — and the writing is dated.

The distinction matters because looking is enough to leak. A researcher who
has seen the 2018–2026 results and then writes a threshold has tuned the
threshold to them, however honestly, and no later analysis can separate the
tuning from the finding. So:

- `numeric_baseline.SEAL_START = 2018-01-01`: the walk-forward's read is
  taken on 2018 onward; 2008–2017 is the explore slice.
- `score_distributions.SEAL_START = 2026-09-07`: the day P25/P75 first
  entered the quant log; the bar was written 2026-09-08, when the interval
  record had zero resolved observations.
- `verdict(sealed=False)` returns `exploratory` and nothing else. The
  explore slice's result **cannot** be called a finding, in code, regardless
  of how good it looks.

A seal is consumed on first read. Reading the sealed slice, adjusting, and
reading again is the same as never having sealed it; the only honest second
read is against a *new* bar on data that arrived after the first. Which seal
governs a new hypothesis is therefore a decision to record before the harness
is built (`resolved.md` #19: for the distribution class, the same 2018-01-01).

## 6. Pre-registration, and the line it draws

Pre-registration is the written, committed statement of the metric, the
threshold, the sample, and what each outcome would mean, made before the
numbers exist. Its purpose is not procedural; it is the only thing that lets
you tell two actions apart afterwards:

- **Fixing a defect the pre-registration already required** — KB-027's
  `verdict()` returned `edge` for an arm its own pre-registration disqualified,
  because a disjunct let a positive BSS skip the ordering check. Correcting it
  made the function do what the committed text said.
- **Moving a goalpost** — raising `EDGE_MIN_BSS` from 0.0 after seeing a
  +0.003, which the pre-registration had said nothing about. It was left at
  0.0 and recorded as an open decision (ADR-0017), then settled once no
  candidate existed for the number to favour (ADR-0020), with a test showing
  the new bar relabels nothing in the record.

Both look like "changing the bar after the result". The committed text is
what distinguishes them, and without it neither correction could be made
honestly.

**Disqualifiers first.** The structural lesson from KB-027: a gate is only
exercised by results that reach it, so a hole in the skill clause can sit
unreached for three runs. Phase 22's `verdict()` evaluates `underpowered` →
`miscalibrated` → `inverted` before any skill number, each returning its own
verdict, and each has a test that drives it independently with a strong skill
number behind it.

## 7. Controls

A harness that reports "no skill" has said nothing until it has shown it
*can* report skill. Every scorer here carries two controls, as tests:

- **Positive control** — a planted signal (a synthetic arm that knows the
  outcome with some noise) that the harness must flag. `synthetic.py` and the
  scorer tests do this.
- **Negative control** — a setting where the rival *is* the truth, in which
  the harness must report skill ≈ 0. If it reports skill here, it is scoring
  something other than what it claims.

Both are in the suite rather than in a memory of having run them once, because
KB-025 is what a degraded harness looks like: green, complete, well formatted,
and not measuring the thing it existed to measure.

## 8. Confounds, and reading a pattern after the fact

A **confound** is a third variable that produces the observed relationship
without the claimed mechanism. The project's two standing examples:

- **The bull-market confound** (KB-022). In a rising sample, any label that
  fires less often in the down months looks predictive of up-moves. The
  bearish label "separated" forward returns — backwards — because it fired
  during stress, and stress reverts. The fix was the block permutation test
  plus the base-rate rival.
- **Arm × period** (KB-023). Two arms run over different date ranges cannot be
  compared, because any difference is either the arm or the period, and
  nothing in the data can say which. "Perfectly confounded" means the
  design, not the analysis, has to change.

The related discipline is **multiplicity**: a pattern found by looking at many
things is expected to appear somewhere by chance. KB-026's ordered reliability
table was recorded as *seen*, not *found*, because it was not pre-registered;
the hypothesis register exists so that such observations are counted against
the number of places that were looked, rather than promoted on their own
strength ([How we explore §4](../concepts/how-we-explore.md)).

---

**Read next:** [Models](models.md) for what was fitted under these rules ·
[The method](../concepts/the-method.md) for the rules as rules.
