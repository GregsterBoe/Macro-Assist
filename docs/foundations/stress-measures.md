# Stress measures

What the fragility instruments are actually computing, one at a time, with the
formula and the reason each one exists. This page explains; the constants are
owned by `fragility.py`, `fragility_or.py` and `fragility_backtest.py`, and the
results by the Knowledge Base entries named in each section.

The question all of them answer is the same: **how susceptible is the tape to a
shock right now?** Not "which way is it going" — that question was measured
separately and closed ([The cut](../concepts/the-cut.md)).

---

## 0. The target: a drawdown label

Every stress measure is scored against one thing — whether the S&P 500 falls
by at least a threshold within a forward window:

```
label_t = 1  if  min(close[t+1 .. t+h]) / close[t]  ≤  1 − threshold
```

with `threshold = 0.05` and `h ∈ {5, 10}` trading days
(`fragility_panel.drawdown_label`). It is a forward-looking boolean, one per
day, and because the window is 5–10 days wide, adjacent labels overlap almost
completely — see [Inference §1](inference.md#1-overlap-is-not-sample-size).

Before anything is counted, both the label and any alarm are **collapsed into
episodes**: a run of consecutive True days is one episode, and runs separated
by three or fewer False days are merged (`collapse_episodes`, `merge_gap=3`).
A crisis that dips below 5 % for two days mid-way is one crisis; an alarm that
flickers is one alarm. Recall and precision are then counted over these small
integers ([Scoring rules §4](scoring-rules.md#4-scoring-an-alarm-auc-recall-precision-lead)).

The label deliberately reads a *level* asset — the S&P — not a volatility
index, so that the stress inputs built from VIX are not scored against
themselves. That circularity is why the VIX term structure is capped
(§2) and why `vix` / `vix3m` are excluded from every cross-asset aggregate.

## 1. Realized variance trend

**Idea.** A system approaching a transition gets noisier before it moves.
Rising realized variance is the least circular way to see that: it uses only
the asset's own prices.

**Computation** (`fragility.realized_variance_trend`):

1. Log returns $r_t = \ln(P_t / P_{t-1})$.
2. Rolling 20-day standard deviation → a realized-vol series $\sigma_t$.
3. Least-squares slope of $\sigma_t$ over the trailing 60 days.
4. Divide by the mean of $\sigma_t$ over the same 60 days, so the slope is a
   *fractional change per day* — dimensionless, comparable across assets.
5. Average across the non-volatility assets, squash to 0–100.

**Weight in the composite:** 0.45 — the lead component. One of the two
components the calibrated label cut-points *require* (`_LABEL_REQUIRES`);
without it the composite is `degraded` and carries no label.

**What was tried and dropped:** adding downside asymmetry (only the variance of
negative returns) — KB-018, no sharpening.

## 2. VIX term structure

**Idea.** Implied volatility has a term structure like any curve. Normally
three-month protection costs more than one-month (contango: `VIX < VIX3M`).
Under acute stress the near month is bid above the far — **backwardation**,
`VIX / VIX3M > 1` — because the market wants protection *now*.

**Computation** (`fragility.vix_term_backwardation`): the ratio each day, then
the fraction of the trailing 20 days spent above 1.0, scaled to 0–100. A
single-day spike scores low; a week of backwardation scores high.

**Weight:** 0.35, capped on purpose. It is the strongest single component
(KB-001: AUC 0.77 at h=5, 0.67 at h=10 as a stress instrument) and also
semi-circular — VIX is itself the price of stress, so scoring it against a
drawdown is partly scoring fear against itself. The second required component.

**The feed matters.** yfinance's VIX3M stopped updating on 2026-07-17; the
component now fails closed when its leg is stale (`_VIX3M_MAX_STALE`) instead
of freezing the ratio. That is the KB-029 lesson: the composite's first live
`Elevated` was this leg dropping out and the remaining weights renormalising.

**Scope.** As a *directional* input the same curve carries nothing (KB-027).
Both results stand; they are about different questions.

## 3. Absorption ratio

**Idea** (Kritzman, Li, Page & Rigobon 2011, *Principal Components as a
Measure of Systemic Risk*). Take the returns of many assets. Do a principal
component analysis. The absorption ratio is the fraction of total variance
"absorbed" by the first few components:

$$
AR = \frac{\sum_{i=1}^{k} \lambda_i}{\sum_{i=1}^{N} \lambda_i}
$$

where $\lambda_i$ are the eigenvalues of the return covariance in descending
order and $k$ is a fifth of $N$. When AR is high, a few common factors drive
everything — the market is tightly coupled and a shock anywhere propagates.
The paper found most major US drawdowns were preceded by AR spikes.

**Two adaptations here** (`fragility.absorption_ratio`):

- **Correlation, not covariance.** Kritzman used a homogeneous equity
  universe. On a heterogeneous panel (equities, gold, oil, FX, crypto) the
  raw covariance's top eigenvector is just "whichever asset is most volatile",
  so returns are standardised first. On the homogeneous sector-ETF panel this
  matters less.
- **The shift, not the level.** AR stays high for months *after* a crash.
  The forward signal is the transition:
  $z = (AR_{15} - AR_{60}) / \text{std}(AR_{60})$, a short window against a
  long one, standardised. A rise of a sigma or more is the alarm.

**History.** KB-012: no skill on the five live assets — too few, too
different. KB-013: on the Fama–French industry cross-section, the same
function has skill; the input was fine, the panel was wrong. KB-020: the live
SPDR sector-ETF panel reproduces the backtest feed. It is a live OR channel
and a shadow composite component (weight 0.0).

## 4. Financial turbulence

**Idea** (Kritzman & Li 2010, *Skulls, Financial Turbulence, and Risk
Management*). Ask how *unusual* today's pattern of returns is, given the recent
volatilities and correlations. That is a Mahalanobis distance:

$$
d_t = (r_t - \mu)^\top \Sigma^{-1} (r_t - \mu)
$$

with $r_t$ the vector of today's returns across the panel, $\mu$ and $\Sigma$
the trailing mean and covariance. A large move in a direction the assets
usually move together is not turbulent; a modest move that breaks the usual
correlations is. Absorption reads the *structure*; turbulence reads the
*surprise* against it. KB-014 confirmed they are complementary — turbulence
catches more crises (recall), absorption raises fewer false alarms
(precision).

**Estimation** (`fragility.turbulence_signal`), because a 252-day covariance
of 9–30 names is nearly singular:

- Ledoit-style shrinkage of $\Sigma$ toward its diagonal, 20 %, so the
  inverse is stable.
- The score is the mean of the last 5 daily distances against the *same*
  $\mu, \Sigma$ — single-day turbulence is spiky.
- Everything uses observations up to the anchor date only.

It returns a raw distance, not a 0–100 score; the OR flag thresholds it on its
own history. It graduated from `input_testing` into `fragility.py` once KB-020
validated it live.

## 5. The composite and its labels

The composite (`fragility.fragility_index`) is a weighted mean of whichever
components could be computed, weights renormalised over those present:

| Component | Weight | Status |
|---|---|---|
| `variance_trend` | 0.45 | required for a label |
| `vix_term` | 0.35 | required for a label |
| `acceleration` (HY / NFCI) | 0.15 | reserved, never computable in the calibration backtest |
| `correlation` | 0.05 | token — near chance, kept for graceful degradation |
| `autocorr` | 0.0 | dropped — critical slowing down has no skill in equities |
| `absorption` | 0.0 | shadow — computed and logged, no effect |

Weights were set by de-overlapped ablation in WP-16.A.3 (KB-002, scheme
`var_led_vix35`).

**Labels** are percentile cut-points of that scheme's own 2008–2026
composite distribution: `Elevated` at the 90th percentile (56.5), `Resilient`
below the 40th (24.0). "Elevated" therefore means "top decile of its own
history", which is the operating point every backtest validated.

**Why the label is `degraded` when a required component is missing** (IMP-5,
KB-029): if `vix_term` drops out, the weights renormalise and the composite
becomes ~90 % variance trend — a different distribution, on which 56.5 no
longer means the 90th percentile. The cut-points are only meaningful on the
distribution they were fitted to.

**Why a degraded reading also says *which feed* died** (IMP-5.4, KB-034): the
first version of the rule above recorded only that a component was missing.
When `vix_term` dropped out again in September 2026 — with the issuer fallback
already in place — the record could not distinguish "the vendor returned
nothing" from "the leg is stale" from "the fallback itself failed", and the
monitor sat unlabelled for three days with every check green. A degradation
rule that cannot be diagnosed is half a rule; a fallback whose own failure is
invisible is not a fallback.

**Why the cuts are static** (KB-030): an expanding point-in-time cut sounds
more honest, but the composite's first year is 2008, so the early "90th
percentile" is a GFC percentile and two crises per horizon are lost. The
static cut was pre-registered against and kept.

## 6. The OR flag

The composite's `Elevated` label is a *precision* instrument. The project
also runs a *recall* instrument, kept separate (`fragility_or.py`):

```
OR = (composite ≥ its PIT p90)
   | (absorption ratio ≥ its PIT p90)     [sector-ETF panel]
   | (turbulence ≥ its PIT p90)           [sector-ETF panel]
```

Each channel is on its own scale, so each is thresholded against the 90th
percentile of its **own readings strictly before today** (an expanding window,
at least 252 prior readings — `_Q`, `_MIN_WARMUP`). Today fires if any channel
clears its own cut.

Why an OR and not a weight: KB-016 showed that blending the channels into the
composite *raises AUC* and *degrades the top-decile flag* — the two metrics
disagree, and the flag is what is operated. So the channels stay separate and
are OR-ed at the flag level (ADR-0006). The OR roughly doubles crisis recall
at a precision cost, which is a good trade for a tail-risk gauge and a bad one
for a directional call — and the project only needs the former.

Three attempts to buy precision back — persistence, severity tiers, a fitted
logistic — each lost crises out of sample (KB-031). Four companion measures
each had standalone skill and none added a crisis the trio catches with lead
(KB-032). The aggregation is a plain OR and the channel set is closed.

---

**Read next:** [Scoring rules §4](scoring-rules.md#4-scoring-an-alarm-auc-recall-precision-lead)
for how these are scored · [KB-001](../record/knowledge-base.md) → KB-002 →
KB-013 → KB-016 → KB-017 for the arc in evidence order.
