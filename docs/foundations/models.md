# Models

The model families that appear in the record, each in a paragraph: what it
is, what it assumes, why it was chosen for the job it was given, and where the
result is. This project uses models as **instruments** — the question is
usually "can *anything* learn this?", and the family is chosen to make that
question hard to answer with "no" ([ADR-0007](../decisions/ADR-0007-measure-the-task-not-the-model.md)).

None of them is a neural network, by decision
([ADR-0008](../decisions/ADR-0008-no-neural-network.md)): on a few thousand
overlapping rows a model that can memorise will, and its null would prove
nothing.

---

## Ridge regression

Ordinary least squares with an $L_2$ penalty on the coefficients:

$$
\hat\beta = \arg\min_\beta \;\|y - X\beta\|^2 + \alpha\,\|\beta\|^2
$$

The penalty shrinks coefficients toward zero, which keeps the fit stable when
features are correlated (as macro features are) or when there are many
relative to the independent observations. It is the linear baseline: if a
signal is linear and present, ridge finds it, and its coefficients are
readable — which is how `drawdown` was identified as the one load-bearing
feature.

**Where:** `numeric_baseline.py` (`ridge` arm, walk-forward; KB-024);
`exogenous_spf` — ridge on the SPF features alone (KB-026).

## Gradient boosting (GBM)

An ensemble of shallow decision trees built sequentially, each tree fitted
to the errors the previous ones left. Depth-2 trees can express pairwise
interactions and thresholds ridge cannot; the small learning rate and tree
count keep it from memorising. It is the non-linear baseline: the family that
would find a signal if it were there but not linear.

**Where:** `numeric_baseline.py` (`gbm` arm — 150 trees, depth 2, learning
rate 0.03). KB-024: same verdict as ridge, same inversion. That two model
classes with different biases fail identically is the evidence that the
*payload* carries no direction, not that a model was mis-specified.

## Logistic regression

A linear model for a probability, $P(y=1 \mid x) = 1 / (1 + e^{-\beta^\top x})$.
Three parameters when fitted on three channels. Used once, as the most
principled aggregator one could try for the OR flag: let the data weight the
channels.

**Where:** `aggregator_testing.py` (IMP-6, KB-031). Under leave-one-crisis-out
it loses crises the plain OR catches, and does not raise precision. The OR
stays.

## Hidden Markov model (HMM)

Assumes an unobserved discrete state (a "regime") that switches over time with
fixed transition probabilities, and that the observed features are drawn from
a state-specific distribution. Fit by expectation-maximisation; the state at
each date is inferred from the whole sequence (smoothing) or from the past
only (filtering).

The seduction is that the smoothed labels look like an economist's regime
chart. The trap is that they use the future: filtered one point at a time,
the inferred state is dominated by the starting probabilities (KB-003), and
walk-forward the layer has no skill (KB-004). KB-005 found the inference path
was the bug; KB-006 found that even fixed, a four-feature rule on NFCI
percentile, curve slope, credit z-score and realized-vol percentile does the
same job. Retired from the note, code kept
([ADR-0004](../decisions/ADR-0004-retire-hmm-from-the-note.md)).

**Where:** `regime.py`, `regime_features.py`, `regime_backtest.py`.

## HAR-RV

Heterogeneous autoregressive realized variance (Corsi 2009). Tomorrow's
realized variance regressed on three backward averages of itself:

$$
RV_{t+1} = \beta_0 + \beta_1\,RV^{(d)}_t + \beta_2\,RV^{(w)}_t + \beta_3\,RV^{(m)}_t
$$

daily, weekly (5-day mean) and monthly (22-day mean). The "heterogeneous" is
the idea that traders at different horizons each contribute a component of
persistence. Four parameters by OLS — simple, and the standard benchmark for
realized-vol forecasting.

Four parameters still need rows. KB-033 read the live wiring walk-forward and
found it fitted on a few dozen returns: `degenerate` on every asset, zero
forecasts published on 9 % of S&P and 13 % of Bitcoin note dates, worse than
trailing 22-day realized vol at every horizon. `HAR_MIN_RETURNS = 1000` is
the floor the method asks for; at that length it has skill on S&P, gold and
Bitcoin.

**Where:** `vol_forecast.py`, `har_backtest.py`. Feeds the variance risk
premium and the `har_gaussian` rival.

## Empirical quantiles, and the Gaussian rival

The published distribution is not a model. It is the sorted historical
sample of forward changes in the bucket, read at the 25th, 50th and 75th
percentiles (`_empirical_quantiles`). No shape is assumed; fat tails and skew
come for free from the sample; the cost is that a thin bucket gives noisy
quantiles, hence `min_n` and the fallback to a coarser parent.

`har_gaussian` is the parametric rival: assume the forward change is normal
with mean zero and standard deviation from the HAR-RV forecast scaled to the
horizon, and read the quantiles at $z = \mp 0.674$ (`_gaussian_quantiles`).
It tests whether a *forecast width* with no bucket beats an *empirical shape*
with one.

## The comparators

Not models, but scored as arms and worth naming as a family: `always_bullish`
(the constant call), `unconditional` (full-history quantiles, no bucket),
`trailing_250` (last 250 days, no bucket). Each is the forecaster that knows
one obvious thing and nothing else. The method's rule that every product is
scored beside one of these is the single most consequential choice in the
record — it is what turned three "skilled" products into three nulls.

---

**Read next:** [KB-024](../record/knowledge-base.md) for the baseline in full ·
[Scoring rules](scoring-rules.md) for how each family's output was scored.
