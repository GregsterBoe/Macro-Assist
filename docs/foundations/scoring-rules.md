# Scoring rules

How a forecast is turned into a number, for the three kinds of forecast this
project has made: a **probability** (the directional call, 1.x), a
**distribution** (the conditional quantiles, 2.x) and an **alarm** (the
fragility flag). The formulas are the general ones; the implementations named
are the only ones the project uses, so a numeric arm and an LLM arm are always
held to one yardstick.

The thread through all three: **a proper scoring rule is one a forecaster can
only minimise by reporting what they actually believe.** Hit-rate is not
proper — you improve it by rounding every call to the likelier side, which is
exactly what an overconfident model does. Brier and pinball are.

---

## 1. Scoring a probability: Brier, BSS, reliability

### Brier score

For a forecast probability $p_i$ and outcome $o_i \in \{0, 1\}$:

$$
\text{Brier} = \frac{1}{n} \sum_{i=1}^{n} (p_i - o_i)^2
$$

Lower is better. Saying 0.5 every time scores 0.25. Saying 1.0 and being
wrong costs 1.0 — the rule punishes confident errors quadratically, which is
the point.

Here the "probability" is the note's confidence (0–100) on a **decisive** call
— one that resolved to simply right or wrong — and $o_i$ is whether the call
was right (`summarize_accuracy._brier_and_reliability`).

### The reference, and BSS

A Brier score on its own is uninterpretable, because it depends on how
predictable the sample was. So it is compared with the Brier of a forecaster
who knows only the **base rate** $r$ — the fraction of outcomes that were 1 —
and says $r$ every time:

$$
\text{Brier}_{\text{ref}} = r(1 - r), \qquad
\text{BSS} = 1 - \frac{\text{Brier}}{\text{Brier}_{\text{ref}}}
$$

BSS = 0 means "no better than knowing the base rate"; 1 is perfect; negative
is worse than the constant. The reference is computed on the **same sample**
as the forecaster, which is why `always_bullish` is the honest rival for a
directional call rather than a straw man — it *is* the base-rate forecaster
whenever the base rate is above one half.

!!! example "Why overconfidence goes negative"
    Sample up-rate 60 %. A forecaster who says 0.6 every time: Brier = 0.24,
    which is the reference, so BSS = 0.

    A forecaster who is right 60 % of the time but says **0.9** every time:
    Brier = 0.6·(0.1)² + 0.4·(0.9)² = 0.006 + 0.324 = 0.330, and
    BSS = 1 − 0.330 / 0.240 = **−0.375**.

    Same hit-rate, badly negative skill. This is the shape of KB-007 and
    KB-024: the model arms were not wrong more often than the constant, they
    were *sure* more often, and the rule charges for that.

The bar for a directional arm (`numeric_baseline.verdict`, ADR-0020):
n ≥ 30 decisive calls, hit-rate > 0.52, **BSS > 0.02**, and a 21-day
block-bootstrap 95 % interval on BSS that excludes zero. No arm has ever
cleared it.

### Reliability, resolution, and the table

Murphy's decomposition splits the Brier score into three terms:

$$
\text{Brier} = \underbrace{\text{reliability}}_{\text{calibration gap, lower better}}
- \underbrace{\text{resolution}}_{\text{discrimination, higher better}}
+ \underbrace{r(1-r)}_{\text{uncertainty, fixed by the sample}}
$$

- **Reliability**: bin the forecasts by stated confidence; in each bin,
  compare the mean confidence with the realised hit-rate. The squared gaps,
  weighted by bin size, are the reliability term. Zero means perfectly
  calibrated.
- **Resolution**: how far each bin's hit-rate is from the overall base rate.
  Zero means the forecaster's confidence sorts nothing — every bin has the
  same outcome frequency.

The **reliability table** the KB prints is this, bin by bin: edges
`[0, 50, 60, 70, 80, 90, 100]`, each row `n`, mean confidence, hit-rate, gap
(+ underconfident, − overconfident). **ECE**, expected calibration error, is
the size-weighted mean absolute gap:

$$
\text{ECE} = \sum_b \frac{n_b}{n}\,\big|\,\text{hit}_b - \text{conf}_b\,\big|
$$

Reading a table: the *ordering* of the hit-rate column is resolution — does
it rise with confidence? — and the *gap* column is reliability. KB-024's ridge
had hit-rate falling to 0.404 in its top bin (inverted resolution — the LLM had already done the same, KB-007); KB-026's
SPF anchor was the first arm whose hit-rate rose monotonically (real
resolution), while its top bin claimed 0.947 against 0.696 realised (a
reliability penalty large enough to keep BSS negative). Those are different
failures and the decomposition is what lets a write-up say which.

## 2. Scoring a distribution: pinball, coverage, PIT

The product publishes three quantiles of the forward change — P25, P50, P75 —
and no direction. Scoring it means scoring quantiles.

### Pinball loss

For quantile level $q$, forecast $f$ and realisation $y$:

$$
L_q(y, f) =
\begin{cases}
q\,(y - f) & y \ge f \\
(1 - q)\,(f - y) & y < f
\end{cases}
$$

At $q = 0.5$ this is half the absolute error — the median is punished
symmetrically. At $q = 0.75$ a realisation *above* the forecast costs 0.75 per
unit and one *below* costs 0.25: the P75 is supposed to be exceeded a quarter
of the time, and the loss is tilted so that the forecast which minimises it in
expectation is exactly the true 75th percentile. That property — minimised
only by the true quantile — is what makes it proper: a forecaster cannot
improve it by shading the interval wider (safer coverage) or narrower
(looks sharper). It is the distribution product's Brier
(`score_distributions.pinball_loss`).

!!! example
    Forecast P75 = +2.0 %. Realised +3.0 %: loss = 0.75 × 1.0 = 0.75.
    Realised +1.0 %: loss = 0.25 × 1.0 = 0.25. Same miss, one-third the
    penalty — being under the P75 is the expected case three times in four.

The score of a forecast is the mean pinball over the three quantiles; an arm's
score is the mean over observations. **Units do not pool** — pinball is in the
asset's unit (percent for prices, basis points for the 10Y), so cross-asset
numbers are always the *skill* ratio below, never the raw loss.

### Skill against a rival

$$
\text{skill}(A \mid B) = 1 - \frac{\overline{L}_A}{\overline{L}_B}
$$

computed only on observations where both arms scored
(`score_distributions.skill_vs`). Positive means A beats B. The rivals are
`unconditional` (the asset's full-history quantiles, no bucket) and
`trailing_250` (the last 250 days, no bucket); the bar is skill vs
`unconditional` > 0.02 with a block-bootstrap interval clear of zero, after
the disqualifiers (`MIN_SKILL`, `MIN_BLOCKS = 8`; ADR-0016, ADR-0020).

### Coverage

The fraction of realisations that fell inside [P25, P75]. Nominal 0.50. It is
a check, not a score — a forecaster can hit 0.50 coverage with a badly placed
interval — and it pools across assets because it is unitless.

### The PIT histogram

*Probability integral transform*, not point-in-time — see the
[glossary](index.md#pit-two-meanings). For a calibrated forecast, the
quantile at which the realisation lands is uniform on [0, 1]. With three
published quantiles that uniform can only be checked in four bins — below P25,
P25–P50, P50–P75, above P75 — each of which should hold 25 %
(`score_distributions.pit_bin`). Too much mass in the outer bins means the
distribution is too narrow; in the inner bins, too wide; skewed to one side,
the median is biased. Four bins is not a coarse choice; it is all three
quantiles can honestly support.

## 3. Hit-rate, and why it is a gate rather than a target

Fraction of decisive calls that were right. It is reported everywhere, it is
what a reader reaches for first, and it is the least informative number on the
page: its floor is the base rate, so in a sample where the asset rose 60 % of
the time a hit-rate of 0.58 is *below* the constant. It appears in the bar
(> 0.52) only as a sanity condition beneath BSS, and it is never the clause a
verdict turns on.

## 4. Scoring an alarm: AUC, recall, precision, lead

An alarm is a boolean per day, scored against the drawdown label
([Stress measures §0](stress-measures.md#0-the-target-a-drawdown-label)).

### AUC

For a continuous score (the composite, the AR shift, turbulence) before any
threshold: the probability that a randomly chosen positive day scores higher
than a randomly chosen negative day — the Mann–Whitney statistic
(`fragility_backtest.auc`). 0.5 is chance; 1.0 perfect; below 0.5 the score
is inverted. Threshold-free, so it summarises the whole curve and says nothing
about any particular operating point. The **de-overlapped** form takes every
`h`-th observation so the point estimate rests on independent windows
(`subsample_auc`).

### Episode recall and precision

Once a threshold is chosen (top decile of the channel's own history), the flag
and the label are collapsed into episodes and:

- **Recall** = crisis episodes that an alarm episode overlapped ÷ all crisis
  episodes;
- **Precision** = alarm episodes that overlapped a crisis ÷ all alarm episodes;
- **Lead time** = days from the alarm's first day to the crisis's first day,
  for the crises it caught.

(`fragility_panel.episode_scoring`.) The denominators are ~a dozen crises
and a few dozen alarms — small integers that are honest about how much
evidence there is. Day-level counts would say "recall 0.94 on 4,000 days";
episode counts say "11 of 12 crises".

### Operating points, and "at held recall"

AUC and the flag can disagree: KB-016 found that blending the cross-section
channels into the composite raises AUC and *lowers* recall at the top decile.
The project operates a flag, not a curve, so candidates are compared **at a
held operating point**: fix recall and read precision (IMP-6, KB-031), or fix
precision and read recall (KB-019). Reporting a higher AUC for a candidate
that is worse where it would actually run is the mistake this guards against.

---

**Read next:** [Inference](inference.md) — every number on this page comes with
an interval, and the interval is where the honesty lives · the
[Scoring reference](../reference/scoring.md) for the current implementation's
switches and outputs.
