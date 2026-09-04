# Macro-Assist — Empirical Knowledge Base

Standing record of **what we have actually measured**, so hard-won findings (and
their caveats) survive past the conversation that produced them. Each entry is a
falsifiable result, not a plan — plans live in `Project_Development.md`.

Format per entry: **what we tested → headline → the nuance that's easy to forget
→ what it changes.** Keep the caveats attached to the headline; the headline
alone is misleading.

---

## KB-001 — Fragility index leads SP500 drawdowns (WP-16.A.2)

**Date:** 2026-06-15 · **Branch:** `feature/emergence` · **Harness:**
`.macro-assist/fragility_backtest.py` (pure numerical, **zero LLM/API cost** —
yfinance only). Reproduce: `python .macro-assist/fragility_backtest.py`.

**What we tested.** Does the `fragility.py` composite, computed look-ahead-safe
on a trailing 180-day window, *rise ahead of* SP500 drawdowns? Walk-forward over
**4,513 daily readings, 2008-07 → 2026-06** (GFC, 2018-Q4, COVID, 2022 all in
sample). Scored with threshold-free Mann-Whitney AUC (0.50 = no skill), per-flag
precision/lift/recall, and lead time to the drawdown trough.

**Headline — GO.** The signal is real and it *leads*:

| Metric | 5-day horizon | 10-day horizon |
|---|---|---|
| Composite AUC | **0.711** | **0.664** |
| Elevated flag precision / lift | 34% / **8.05×** | 37% / 4.24× |
| Median lead (Elevated → trough) | **4 days** | **6 days** |
| % true positives with ≥3-day warning | 76% | 85% |

The Elevated flag (composite ≥ 65, provisional) is rare — ~3% of days
(146/4,513) — but when it fires it is genuinely *early*, not coincident. This is
the direct counter to the project's founding complaint ("the model only reacts
to events as they happened, not in advance").

**The nuance that's easy to forget.** The component AUCs only *partly* confirm
the Phase-16 thesis:

- `vix_term` is the **strongest** component (AUC 0.77 / 0.67) — but it is
  **semi-circular**: VIX backwardation is itself a stress reading, so part of its
  "lead" is really coincidence. Do not let it dominate the composite.
- `variance_trend` works as hypothesised (0.66 / 0.62).
- `correlation` is **barely above chance** (0.51 / 0.55) — it is *not* earning
  its 0.30 default weight. This was a surprise; the cross-asset
  correlation-tightening story did not show up in the data.
- `autocorr` (classic "critical slowing down") has **no skill** (0.44 / 0.50),
  **exactly as the literature predicted** for equities. Vindicates keeping it
  near-zero weight; a candidate to drop entirely.
- The `Rising` trend flag is **too trigger-happy**: fires ~40% of days, lift
  only ~1.4. The *level* (Elevated) carries the signal, not the trend flag.

**Methodological caveats (address before over-trusting the lift numbers).**
1. **Overlapping windows** — daily readings inside one drawdown episode are
   counted as many "events," inflating apparent n and significance. Re-score at
   the distinct-episode level.
2. yfinance-only run **excludes** the HY-spread / NFCI `acceleration` component
   (those get revised; left out to keep the result revision-clean). Its
   contribution is untested here.
3. Single market regime sample (one GFC, one COVID); 18 years is not many
   independent crises.

**What it changes.**
- Phase-16 / emergence direction is **worth continuing** — but the expensive
  LLM-pipeline backtest still should **not** run until thresholds and weights are
  fixed (A.3 / A.4).
- Next (WP-16.A.3): recalibrate weights — **drop or down-weight `correlation`,
  consider dropping `autocorr`**, cap `vix_term`'s influence — and re-score on
  de-overlapped episodes.

**Incidental bug found & fixed.** WTI front-month futures printed *negative* on
2020-04-20; `log()` of that is undefined and was silently producing NaNs in the
middle of the COVID stress window. Now masked in `fragility._to_log_returns`.

---

## KB-002 — Fragility weights recalibrated + de-overlapped (WP-16.A.3)

**Date:** 2026-06-15 · **Branch:** `feature/emergence` · **Harness:**
`.macro-assist/fragility_backtest.py` (`run_weight_ablation`, still **zero
LLM/API cost**). Reproduce: `python fragility_backtest.py` (default weights now
= the chosen scheme).

**What we tested.** Two things A.2 flagged as unfinished: (1) **de-overlap** the
scoring — 4,513 daily readings inside a handful of real crises are not
independent, which inflated A.2's day-level lift; (2) **recalibrate the
weights** (correlation looked dead, autocorr no-skill, vix_term semi-circular).
Added episode-level scoring (collapse both the drawdown label and the alarm flag
into distinct runs → count caught *crises* vs. true *alarms*) and a
non-overlapping AUC (subsample every horizon-th day). Ran a 6-scheme ablation on
the de-overlapped metrics, 2008-2026.

**Headline — the signal survives de-overlapping, but is smaller than it looked,
and the weights were wrong.** Chosen scheme **`var_led_vix35`** (variance 0.45 /
vix_term 0.35 / correlation 0.05 / acceleration 0.15* / autocorr 0.0):

| metric | 5-day | 10-day |
|---|---|---|
| Composite AUC (overlap) | 0.727 | 0.661 |
| Composite AUC (**non-overlap, honest n**) | **0.719** | **0.690** |
| Episode recall (distinct crises caught) | 14/46 = **0.30** | 17/58 = **0.29** |
| Alarm precision (distinct alarms that led a crisis) | **0.53** | **0.73** |
| Median lead (Elevated → trough) | 4 d | 8 d |
| % true positives ≥3-day warning | 80% | 91% |

\*`acceleration` (HY/NFCI) is never computed in the yfinance-only backtest, so
its weight renormalises away here; it is reserved for the A.4 wiring.

**Reframe the A.2 headline (important).** KB-001's "8.05× lift" was **inflated by
overlapping windows**. De-overlapped, this is a **precise-but-incomplete** flag:
it fires rarely (~10% of days at the 90th-pct Elevated cut), catches only ~30%
of distinct crises, but when it fires it is right **50–73%** of the time and a
genuine **4–8 trading days early**. It is a tail-risk *early-warning*, not a
comprehensive crash detector — size expectations accordingly.

**What the ablation settled.**
- **Dropping `autocorr` is free** — `baseline` and `drop_autocorr` were identical
  to 3 decimals. Its 0.05 weight contributed nothing. Dropped to 0.
- **Dropping `correlation` *helps*** — every scheme that zeroed it beat baseline
  on the honest AUC *and* episode precision/recall. The cross-asset
  correlation-tightening story is not in the data. Kept at a **token 0.05** only
  so the live composite degrades gracefully if VIX3M is unavailable.
- **`vix_term` is strongest but capped at 0.35** (below variance's 0.45): it is
  semi-circular (backwardation *is* a stress read), so it must not dominate.
- **`var_led_vix35` matched the max-skill 2-component `core_two` (var/vix 50/50)**
  on AUC (within 0.004–0.011, i.e. noise) while having the **highest alarm
  precision of any scheme** and degrading more gracefully — so it was preferred
  over both the aggressive (`core_two`) and the over-conservative
  (`var_led_capvix`) options.

**Threshold calibration (the other half of A.3).** Composite labels are now
**percentiles of this scheme's own 2008-2026 distribution**, replacing the
provisional absolute cuts: **Elevated = 90th pct ≈ 56.5**, **Resilient = 40th
pct ≈ 24.0**. The 90th-pct cut *is* the validated top-decile flag, so the live
`Elevated` label is exactly what the backtest scored.

**Caveats still open.**
1. Still a **single regime sample** (one GFC, one COVID) — 18 years, few
   independent crises. The ~0.01 AUC gaps between finalist schemes are within
   sampling noise; do not over-fit to them.
2. `acceleration` (HY-spread / NFCI) remains **untested** — it carries real
   weight (0.15) but only activates when A.4 wires in those feeds.
3. The `Rising` **trend flag is still trigger-happy** (fires ~40–50% of days,
   lift ~1.3); only the *level* flags (Elevated / top-decile) are validated.
   Trend momentum was retuned to lean on the variance slope (0.85) over the
   now-token correlation delta (0.15), but treat trend as informational.

**What it changes.**
- `fragility.py` `DEFAULT_WEIGHTS` and label cut-points are now the calibrated
  values above (was the A.2 provisional set). WP-16.A.3 is **Done**.
- Next is **WP-16.A.4** — wire the monitor into `quant_context.py` in **shadow
  mode** (widen ranges + tail-risk bullet when Elevated; never flip direction).
  The expensive LLM-pipeline backtest still should **not** run until after a
  shadow period confirms the wiring behaves.

---

## KB-003 — Regime layer: look-ahead-safe ≠ full-sample labels; single-point inference is startprob-dominated (WP-17.1)

**Date:** 2026-06-16 · **Branch:** `feature/regime-validation` · **Harness:**
`.macro-assist/regime_backtest.py` (pure-numerical; needs FRED for NFCI / yields
/ BAA10Y + yfinance for SP500). Reproduce: `FRED_API_KEY=… python
.macro-assist/regime_backtest.py`.

**What we tested.** Two WP-17.1 questions about the HMM regime layer (Phase 10),
which had never been backtested the way fragility was: (1) is the persisted /
full-sample model a valid basis for validating regime skill, and (2) how
look-ahead-safe is the live regime path? Walk-forward refit (weekly, trailing
~5y, single-point classify — mirrors production) vs. a full-sample fit, over
**2,357 daily readings (~2016→2026, COVID + 2022 in sample; no GFC at the 12y
fetch), 472 weekly refits, 8 needing a diag/carry fallback.**

**Headline — you cannot validate the regime layer on the persisted model.** The
look-ahead-safe (walk-forward) labels disagree with the full-sample labels on
**70.5%** of days. Any skill test (WP-17.2) **must** refit walk-forward; scoring
the persisted full-sample model would be measuring a different label series than
the live system produces.

**The nuance that's easy to forget (and the bigger finding).** The full-sample
model produced **only 1 distinct label across all 2,357 days** (vs. 4 for the
walk-forward path). This is not a harness bug — it traces to the **single-point
inference** the live pipeline uses: `regime_features` returns one (4,) vector and
`predict_regime` classifies it alone, so `predict_proba` = normalised
`startprob_ × emission`. A full-sample EM fit converges to a near one-hot
`startprob_`, so *every* single-day classification collapses to that one state.
The walk-forward path looks like it distinguishes regimes (4 labels) **only
because each weekly refit's favoured state differs** — within any one refit the
label is effectively pinned by `startprob_`. So the HMM's transition matrix does
no work at inference; the live "regime" is closer to a startprob-weighted
Gaussian-mixture pick than a sequential HMM state. **Flag for WP-17.3:** test
single-point vs. sequence (Viterbi) inference and GMM-vs-HMM directly — the HMM
may be earning none of its temporal machinery in the live path.

**Methodological caveats.**
1. 12y fetch ⇒ features span ~2016→2026 (COVID, 2022 — **no 2008 GFC**); re-run
   with `years≈18` for GFC coverage in the skill gate.
2. `label_states` maps state indices → economic labels *per fit* (median NFCI /
   vol split), so cross-refit label identity isn't guaranteed — compare by the
   economic label string, not the raw state index.
3. This is the look-ahead/divergence audit, **not** a skill measurement — it says
   nothing yet about whether the (walk-forward) labels predict forward returns.

**What it changes.**
- WP-17.1 **Done**. The skill gate (WP-17.2) scores the **walk-forward** label
  path, never the persisted model.
- WP-17.3 elevated in importance: single-point inference is `startprob_`-
  dominated, so "is the HMM better than a GMM / does sequence inference help?"
  is now a first-order question, not a refinement.
- Production context: the regime model was additionally **under-trained** (the
  HY-OAS feature only had ~3y on FRED — see WP-17.1), now fixed by switching the
  credit feature to **BAA10Y**; re-run `refit_models.py` after merge.

**Incidental.** The earlier 3.6% divergence figure is **void** — it was measured
on the ~2y truncated window where the full-sample model also collapsed to a
single label, so the comparison was meaningless.

---

## KB-004 — Regime layer has NO out-of-sample skill as wired (WP-17.2)

**Date:** 2026-06-16 · **Branch:** `feature/regime-validation` · **Harness:**
`.macro-assist/regime_backtest.py --skill` (18y fetch, BAA10Y credit feature).
Scored on the **walk-forward** label path only (KB-003).

**What we tested.** Do the regime labels separate the future? Over **3,922
walk-forward readings (~2010→2026), 785 weekly refits**: forward 5/10/20-day
SP500 return + realized vol per label, AUC of Risk-Off predicting a ≥5% forward
drawdown (least-circular test), AUC of High-Vol predicting top-tercile forward
vol (partly circular — vol-percentile is an input), and a high-posterior subset.

**Headline — NO SKILL. The regime layer is decorative as currently wired.**

| AUC (0.50 = none) | 5d | 10d | 20d |
|---|---|---|---|
| Risk-Off → drawdown | 0.482 | 0.465 | 0.485 |
| High-Vol → top-tercile fwd vol *(circular)* | 0.499 | 0.495 | 0.496 |

The Risk-Off→drawdown AUC is at/below chance at every horizon, and the
label→forward-return separation is perverse (e.g. 5d: "Risk-Off High-Vol" mean
fwd ret **+0.0033** vs "Risk-On Low-Vol" **+0.0017** — the wrong way round).

**The smoking gun (why it fails).** The **High-Vol→forward-vol AUC is ~0.50**.
Realized vol is highly persistent and the vol percentile is a *direct input
feature*, so a label that meant anything would predict forward vol with AUC well
above 0.5. It doesn't — **the labels don't even track their own inputs.** Cause
(per KB-003): single-point inference makes `predict_proba ≈ startprob_ ×
emission`, and the fitted `startprob_` is near one-hot, so the label is pinned by
`startprob_` regardless of the day's features. Confirmed by the confidence
column: **3,920 of 3,922 days read posterior ≥0.8** — near-universal false
confidence. The scorer itself is sound (the planted-signal unit test recovers a
real Risk-Off→drawdown signal), so this is a property of the labels, not a bug.

**What it changes.**
- The HMM regime block as it feeds the daily note carries **no predictive
  information**. It should not be trusted as-is.
- **Before dropping the regime *concept*, WP-17.3 must isolate cause from
  concept:** the failure is in the *inference path* (startprob-dominated single
  point), not necessarily the model. Test **sequence/Viterbi inference** (use the
  trailing window, let the transition matrix act) and a **GMM baseline**; also
  fix or bypass the degenerate `startprob_`. Only if proper inference still shows
  no skill is the regime concept itself dead.
- This is the mirror image of fragility (KB-001/002): same disciplined gate, but
  here the gate says **stop** — exactly its purpose. Do not spend LLM-pipeline
  budget on regime context until 17.3 resolves the inference path.

**Caveats.** 18y fetch ⇒ scored ~2010→2026 (2011, 2015-16, 2018Q4, 2020, 2022;
the 2008 GFC sits mostly in the 252-day warmup, so it is largely excluded).
n_states=4, default covariance — both revisited in WP-17.3.

---

## KB-005 — Regime: inference path was the bug, not the concept (WP-17.3)

**Date:** 2026-06-16 · **Branch:** `feature/regime-validation` · **Harness:**
`.macro-assist/regime_backtest.py --infer` (18y, 3,922 walk-forward readings
~2010→2026). Same look-ahead-safe fits, four inference methods compared.

**What we tested.** KB-004 showed the production label path (single-point
`predict_proba`) carries no skill and the labels don't track their own inputs —
traced to `startprob_` domination. Does a *different inference* recover skill on
the *same* walk-forward HMM/GMM fits?

**Headline — it was the inference, and the layer is salvageable (but modest).**

| inference @10d | Risk-Off → drawdown AUC | High-Vol → fwd-vol AUC |
|---|---|---|
| `point` (production) | 0.465 | 0.495 |
| `viterbi` (seq → last state) | **0.553** | **0.646** |
| `smoothed` (fwd-bwd last step) | 0.553 | 0.646 |
| `gmm` (no temporal structure) | 0.499 | 0.615 |

Feeding the **trailing sequence** (so the transition matrix + emissions act,
instead of `startprob_` alone) makes the High-Vol label track forward vol again
(0.495 → 0.646 — the floor test passes) and lifts Risk-Off→drawdown from
*below* chance to **0.553**.

**The nuance that matters.** The **HMM with sequence inference beats the GMM on
the drawdown axis** (0.553 vs 0.499) while matching it on the (partly circular)
vol axis. So the HMM's temporal structure earns its place — **but only if live
inference uses the sequence.** Risk-Off→drawdown 0.55 is in the **weak band**
(WP-17.2 scale: ≥0.58 separates / 0.53–0.58 weak / <0.53 decorative): real and
correctly-signed, not strong. `viterbi` and `smoothed` were identical on this
data.

**What it changes.**
- **Concrete production bug:** `predict_regime` / `quant_context` feed a single
  feature vector; they should feed a **trailing feature sequence** and take the
  Viterbi/smoothed last state. This moves the live regime block from *no-skill +
  false 0.9 confidence* (KB-004) to *modestly informative*. Until fixed, the
  regime block in the daily note is misleading and should not be trusted.
- The fix is non-trivial: the live path must reconstruct the recent (~120-day)
  4-feature matrix at inference, not just today's snapshot.
- The regime layer is **worth fixing, not dropping** — but given the modest 0.55,
  **WP-17.4 (does it beat the simpler Phase-11 conditional bucket?)** is the real
  keep/cut gate, and the **model-selection sweep** (n_states, covariance) should
  run to see if the weak signal strengthens.

**Caveats.** Scored ~2010→2026 (GFC mostly in the 252-day warmup). High-Vol→vol
is partly circular (vol percentile is an input); the load-bearing number is the
less-circular Risk-Off→drawdown (0.55). n_states=4, full covariance throughout.

---

## KB-006 — Regime HMM is redundant; a 4-feature rule beats it (WP-17.4)

**Date:** 2026-06-16 · **Branch:** `feature/regime-validation` · **Harness:**
`.macro-assist/regime_backtest.py --bucket` (18y, ~3,900 walk-forward readings).
The keep/cut gate.

**What we tested.** Does the HMM regime — even in its best Viterbi inference
(KB-005) — add drawdown-prediction skill beyond simply conditioning on the same
4 macro features? Compared Risk-Off→drawdown AUC for the HMM vs a transparent
equal-weight rule-based stress score (`+nfci_pct, −yc_slope, +credit_z,
+vol_pct`), their redundancy, and the regime AUC *within stress terciles*.

**Headline — DROP the HMM. It is redundant and worse than a trivial rule.**

| @10d, drawdown ≥5% | AUC |
|---|---|
| **rule-based stress score → drawdown** | **0.697** |
| HMM regime (Viterbi) → drawdown | 0.553 |
| regime AUC *within* stress terciles (mean) | **0.507** (≈ chance) |
| redundancy (Spearman, regime vs rule) | 0.336 |

The simple linear rule on the same inputs is **far** better (0.697 vs 0.553),
and once stress level is known the regime adds **nothing** (within-tercile mean
0.507). The low redundancy (0.336) means the HMM isn't even a noisy version of
the rule — it's worse *and* capturing something other than the stress that
actually predicts drawdowns.

**The nuance that's easy to forget.** The rule is **in-sample-standardised**
(full-sample mean/std), a mild look-ahead that flatters its 0.697; a fully-OOS
rule would score a little lower. But the decision does **not** rest on that
number — the **within-tercile 0.507** (standardisation-free) and the **0.336
redundancy** independently show the HMM has no incremental value. The rule's
score also leans partly on `vol_pct` (persistent/semi-circular for drawdowns),
the same caveat as fragility's vix_term — but it's still simpler and better.

**What it changes.**
- **WP-17.3b (fix the live inference path) is CANCELLED** — do not fix a layer
  we're dropping. The KB-005 "salvageable via sequence inference" path is moot
  because even salvaged it loses to a 4-line rule.
- **Recommendation: remove the HMM regime block from the daily note.** The
  macro-stress dimension it gestures at is already served better by (a) the
  Phase-16 **fragility monitor** (variance/credit/vix composite, AUC 0.69–0.72,
  KB-002) and (b) the trivial stress rule here — so dropping the HMM loses no
  information. Adding the stress rule as a *new* block would itself be redundant
  with fragility; prefer consolidation over another stress gauge.
- **Closes Goal-2's core question for the regime layer.** Full arc: under-trained
  (HY-OAS truncation, fixed → BAA10Y, KB/WP-17.1) → persisted model invalid for
  validation (70.5% divergence, KB-003) → startprob-dominated inference → no
  skill as wired (KB-004) → fixable via sequence inference but only to 0.55
  (KB-005) → **still redundant vs a 4-feature rule (KB-006) → drop.** A complex
  component validated as dead weight; the disciplined outcome is to simplify.

**Caveat.** Scored ~2010→2026 (GFC mostly in the warmup). The verdict is about
the HMM's *incremental* value for drawdown prediction; it does not test other
conceivable uses of regime state, but none are currently wired into the product.

## KB-007 — The model's directional confidence is anti-informative (WP-16.B.2 baseline)

**Date:** 2026-06-23 · **Branch:** `main` · **Harness:**
`.macro-assist/summarize_accuracy.py` (calibration block), over 59 scored
reports / 441 decisive directional calls. The first run of the new Brier /
reliability metric — establishes the calibration baseline the whole
loosening/weighting programme (Goal 1 + Phase 18) is judged against.

*Arm scope (added 2026-09-03): unaffected by the [KB-023] pooling defect. This
entry predates the `exogenous` (2026-07-27) and `kimi` (2026-08-03) arms, so its
441 calls are pure production-arm. Later re-runs of the same metric were pooled
until the arm filter shipped — at 128 files the pooled decisive n was 731 against
the market arm's 666 (BSS −0.112 pooled vs **−0.123** market-only).*

**What we measured.** Read each call's stated confidence (0–100) as P(call is
correct) and scored it against the binary outcome of *decisive* calls (Bullish/
Bearish on a non-flat move; Neutral/flat excluded). Brier (lower=better),
Brier Skill Score vs the constant base-rate forecast (BSS>0 ⇒ confidence beats
guessing the base rate), ECE, and a confidence-binned reliability diagram.

**Headline — confidence is not just overconfident, it is below chance and
anti-informative. BSS < 0 at every horizon, worsening with horizon and in the
recent (feedback-era) versions.**

| Set | n | base-rate (hit %) | Brier | BSS | ECE | read |
|---|---|---|---|---|---|---|
| Overall (all 59 reports) | 441 | **36%** | 0.276 | **−0.195** | 0.219 | overconfident |
| T+5 | 148 | 42% | 0.268 | −0.101 | 0.159 | overconfident |
| T+10 | 151 | 37% | 0.271 | −0.161 | 0.225 | overconfident |
| T+20 | 142 | **30%** | 0.291 | **−0.395** | 0.291 | overconfident |
| Feedback-era (≥v0.3) | 268 | **30%** | 0.279 | **−0.344** | 0.264 | overconfident |

Reliability bins are flat-to-inverted: the 60–70% confidence bin hits no better
(often worse) than the 50–60% bin (e.g. T+10: 50–60→30%, 60–70→42%, but T+20:
50–60→28%, 60–70→29%). Raising stated confidence does not earn a higher hit-rate.

**Two distinct problems (don't conflate them).**
1. **Skill:** decisive directional calls are right only ~36% of the time —
   *below* a coin flip. This is an accuracy problem, not just calibration.
2. **Calibration:** within that, confidence does not order outcomes (BSS<0,
   ECE 0.22). The confidence number currently carries negative information.

**Caveats / what this is NOT.** (a) "Decisive" excludes flat moves and Neutral
calls, so this measures skill *conditional on the model committing to a
direction on a move large enough to resolve* — the population most exposed to
being wrong. (b) Below-chance ≠ "just fade it": these are the hard-to-call
large moves, and per-asset varies wildly (10Y T+20 directional was 64% in the
accuracy table, Bitcoin/SP500 far below). (c) Pools all assets/versions; the
feedback-era subset being *worse* is the concerning part — recent structural
changes have not improved (and may have hurt) directional calibration.

**Why it matters / how to apply.** This is the **north-star baseline** for
Goal 1 and Phase 18: any loosening (B.1), reweighting (B.3), input pruning
(18.4), or LLM lever (16.C) must move **Brier/BSS**, not just accuracy. The
immediate implication for **WP-16.B.1 (conviction floor)**: forcing a directional
call when the honest read is "no edge" is plausibly *generating* these
below-chance decisive calls — allowing all-Neutral tables and re-scoring Brier
is now a high-priority test, not a nicety. Decision metric for everything
downstream: **BSS > 0 with ECE < 0.05 at n ≥ 30.**

## KB-009 — Input payload is redundancy-heavy in the market/sector block; the FRED macro series are the orthogonal core (WP-18.2)

**Date:** 2026-06-27 · **Branch:** `main` · **Harness:**
`.macro-assist/input_ledger.py` over **36 inputs × 1367 business days** (5y FRED +
market + sector panel). First run of the cheap input-quality screen — narrows the
WP-18.4 ablation candidate list. **A screen, not a verdict** (see caveats).

**What we measured (zero LLM cost).** Per input series: **staleness** (days past
the series' *true* last print — taken pre-ffill), normalised **entropy** of the
level distribution, MAD-scaled **robust σ**, and **redundancy** = max |corr| with
any other input, computed on **first differences** (levels are non-stationary and
correlate spuriously). Redundancy is assessed **only among daily-active series**
(non-zero change fraction ≥0.6); ffilled sub-daily FRED series produce mostly-zero
change vectors that manufacture artifacts, so they are flagged `redund-n/a` and
ranked by entropy alone. Ranking key `info_score = entropy·(1−max|corr|)`.

**Headline — the daily market/sector block is highly collinear (a handful of
factors), while the FRED macro series carry the orthogonal information.**

Redundancy clusters (the prune candidates, |corr| on changes):
- **Volatility:** `vix ≈ vix3m` (**0.978**) — near-duplicate; `vix3m` is *also*
  9d stale (a daily series) and used only for the term-structure ratio.
- **Equity beta:** `sp500 ≈ nasdaq` (0.957); `nasdaq ≈ xlk` (0.934); `sp500 ≈`
  xlk/xly/xli/xlc (0.81–0.88); `xli ≈ xlb` (0.804). The equity complex collapses
  onto ~one factor — most sector ETFs add little beyond SP500 directionally.
  Differentiated sectors: `xle` (tracks `wti_oil` 0.582, not SP500), `xlu↔xlre`
  (rate-sensitive pair 0.649), `xlv/xlp` (defensives ~0.6).
- **Rates:** `treasury_10y ≈ real_yield_10y` (0.856); `treasury_2y ≈ 10y` (0.788).
  `breakeven_10y` is the *independent* one (0.426) — it carries the inflation-
  expectations signal the nominal/real pair does not.

Orthogonal / high-info (NOT prune candidates): the FRED macro block — gdp, cpi,
m2, nfci, fed_total_assets, treasury_gen_acct, reverse_repo, philly_fed_mfg,
fed_funds_rate, unemployment, jobless_claims — plus gold (−0.286 vs dxy), bitcoin
(0.397), dxy (0.408), and the credit spreads (hy↔baa 0.619, independent of equity
and rates).

**Staleness.** Only one *real* abandonment signal: **`vix3m` 9d stale** for a
daily series — investigate the yfinance feed (and it's already a prune candidate:
redundant + single-use). The monthly-macro STALE flags (cpi/m2/unemployment/
fed_funds 57d, gdp 177d quarterly) are **cadence artifacts** — FRED dates these
month-/quarter-start and adds release lag, so they routinely exceed a 45d limit
without being abandoned. Implication: the `monthly` freshness limit (45d) is too
tight for FRED's dating convention; consider ~75d before treating monthly staleness
as a signal.

**Caveats / what this is NOT.** (a) **Screen, not verdict** — high |corr| ≠ no
marginal value; a redundant input may be the cleaner/faster member of a pair or
matter only at the tails. The keep/cut decision is the WP-18.4 outcome-grounded
ablation, against Brier (KB-007). (b) Entropy measures *distribution richness*, not
predictive value — an orthogonal series can be orthogonal *noise*; orthogonality
buys a 18.4 test, not a keep. (c) Redundancy is change-correlation among daily
series only; cross-frequency redundancy (e.g. a daily proxy for a monthly macro
read) is not captured here. (d) Pearson is linear — non-linear dependence is
invisible to this screen.

**Why it matters / how to apply.** This is the **candidate queue for WP-18.4**
(drop-one ablations, one lever at a time, n≥30 per arm, judged on Brier):
1. **Drop `vix3m`** — redundant (0.978) + stale + single-use (term-structure ratio
   can be derived without feeding it as a standalone input).
2. **Collapse the sector block** — test giving the model SP500 + the *differentiated*
   sectors (XLE, XLU/XLRE, XLV) only, dropping the SP500-clones (XLK/XLY/XLI/XLC/
   XLF/XLB); the prompt-economy payoff is large (sectors are ~1k chars).
3. **`nasdaq` vs `sp500`** — one of the two index series may suffice.
4. **`real_yield_10y` vs `treasury_10y`** — keep `breakeven_10y` (the independent one).
The FRED macro core is explicitly **not** a prune target — it is where the
non-redundant information lives. Next observability step: WP-18.3 citation screen
(does the model actually *reference* the redundant inputs?) before paying for 18.4.

## KB-010 — Redundancy and model-attention point at *different* prune candidates (WP-18.3)

**Date:** 2026-06-27 · **Branch:** `main` · **Harness:**
`.macro-assist/citation_screen.py` over **78 scored notes** (all versions), joined
to the KB-009 ledger. Measures how often the model **names** each input in its
free-prose rationale (Executive Summary, asset/theme sections, Key Risks, Primary
Driver cells); the templated Macro Dashboard table and the raw Data Snapshot are
excluded so the rate reflects chosen wording, not template.

**Headline — citation and redundancy are nearly anti-correlated, so the two
screens nominate different inputs.** The model heavily cites most of the
*redundant* market series (they are headline assets / forecast targets) while
ignoring several *orthogonal* macro-plumbing inputs. KB-009's redundancy alone
would prune inputs the model actively engages; KB-010's attention finds prunables
KB-009 rated high-info. **The WP-18.4 queue is the union of the two, not either
alone.** Result: zero inputs are *both* redundant (≥0.80) and rarely cited (≤10%),
so the composite "high" bucket is empty — the signal is in the two tails.

**Clear citation-side prune candidates (rarely named):**
- **`baa_spread` — 0/78, never cited.** Correlated with the cited `hy_spread`
  (0.62, below the 0.80 redundancy bar so the tool only marks it "watch"), and its
  one live consumer — the HMM regime credit feature — was **retired (KB-006)**.
  Strongest standalone prune: a human reads 0 citations + dead consumer as "drop."
- **Net-liquidity raw components** — `reverse_repo` 0/78, `fed_total_assets` 2/78
  (3%), `treasury_gen_acct` 7/78 (9%). Rarely cited *individually* because the
  model uses the synthesised **`net_liquidity`** (cited 42/78, 54%). These three
  are high-entropy/orthogonal so KB-009 would *never* flag them — a citation-only
  finding: drop the three raw lines, keep the synthesised aggregate.
- **Low-attention sectors** — `xlre` 13%, `xlp` 17%, `xlv` 23%, `xlu` 26%;
  combined with the redundant clones `xlb/xlc/xli/xly` (14–49%), this reinforces
  KB-009's "collapse the sector block." Exceptions that earn their place: `xle`
  (78%, tracks oil) and `xlk` (65%).

**Caveats / what this is NOT.** (a) **Template confound:** the six forecast assets
(`sp500`, `gold`, `wti_oil`, `treasury_10y`, `dxy`, `bitcoin`) are named *by
construction* in the 5-Day Predictions table → their ~100% rates are structural,
not free attention; they are forecast *targets* and not prunable regardless. (b)
**Screen, not verdict** — the model can use an input without naming it (it's in the
payload either way) or name one that didn't move the call; citation ≠ causal
weight. (c) The alias map is fallible and some aliases are broad ("claims",
"oil", "dollar"). (d) Pools all 78 notes across versions/regimes; a feedback-era
(`--min-version v0.3`) re-run could differ.

**Why it matters / how to apply.** Refined **WP-18.4 ablation queue** (union of
KB-009 redundancy + KB-010 attention, cheapest/clearest first; each judged on
Brier, n≥30 per arm):
1. **Drop `baa_spread`** — 0 citations + correlated with cited `hy_spread` + dead
   consumer (regime retired). The single clearest cut. **✅ Done 2026-06-27** —
   removed from `FRED_SERIES` + frequency map + the 5yr-mean branch in
   `collect_and_analyze.py` (no longer fetched or fed to the LLM). This was
   *cleanup*, not an 18.4 ablation: with no live consumer and 0 model attention
   there is nothing for an outcome A/B to measure, and it does not perturb the
   running loosened A/B. `refit_models.py`/`regime_features.py` keep their own
   BAA10Y references for a possible future regime revival.
2. **Drop the three raw net-liquidity components**, keep synthesised `net_liquidity`
   — prompt-economy win the redundancy screen could not see.
3. **Collapse the sector block** to SP500 + XLE (± XLK) — both screens agree.
4. **Lower priority:** `vix3m`, `nasdaq`, `real_yield_10y` — redundant (KB-009) but
   heavily cited (64–95%), so test only if 1–3 don't move Brier.

## KB-011 — Loosened arm commits far less and bleeds less (early read) (WP-16.B.1 reframe)

**Date:** 2026-07-14 · **Branch:** `main` · **Harness:**
`.macro-assist/summarize_accuracy.py` `commitment_by_arm` (new). This is the
loosened-vs-baseline A/B that KB-008 was reserved for. The decisive-only Brier
A/B needs n≥30 decisive calls, which floor-off makes rare (loosened has only **2**
decisive scored calls after 12 notes) — so instead this scores the **commitment
decision over all resolved calls**, giving a directional read now. Uses the
model's stated `bias` (Neutral vs directional) to separate "the model declined to
commit" from "the market was flat" (score 0.5 conflates them).

**Baseline (n=1179 resolved, pre-loosened / all non-loosened notes) corroborates
KB-007:** commit-rate **56%**, hit-rate-when-decisive **36%**, wrong-decisive 29%,
right-decisive 17%, **net decisive edge −0.125** (bleeds ~12.5 net wrong-decisive
per 100 calls — below chance, as KB-007 found).

**Loosened (n=30 resolved so far):** commit-rate **20%** (↓ from 56% — the floor-off
lever is large and working), neutral-rate 80%, wrong-decisive **7%** (↓ from 29%),
**net edge −0.067** (↑ from −0.125, i.e. *less* bleed). Read: **loosened commits
much less and bleeds less — the thesis holds directionally.**

**Caveats.** (a) Loosened decisive n=2 (both wrong, right-decisive 0%), so we can
say it commits *less* and cuts *wrong* commitments, **not** yet that its surviving
commitments are *better* — hit-rate-when-decisive is unmeasurable at n=2. (b) The
commit-rate and wrong-rate deltas rest on n=30 (more trustworthy than n=2 but
still small). (c) 'baseline' pools all non-loosened notes across versions (no
contemporaneous control — the daily var runs one profile at a time). (d) net-edge
improving partly reflects fewer decisive calls overall, not necessarily sharper
ones. **Decision still gated on the decisive-only Brier A/B at n≥30** (KB-007 bar:
BSS>0, ECE<0.05); this metric is the early tell, not the verdict. Rendered in
`accuracy_report.md` → "Commitment" section; JSON key `commitment_by_arm`.

---

**⚠️ SUPERSEDED 2026-09-03 — caveat (c) is far more serious than it reads.**
[KB-023] established that the two profiles share **zero** report-dates
(baseline 2026-03-13→06-26, loosened 06-29→08-21): `MACRO_PROFILE` was switched
in one block, so "baseline vs loosened" *is* "March–June vs July–August". The
assets that drove the result reversed sign across that boundary (T+20 WTI
−5.92% → +6.24%, Bitcoin −1.58% → +7.38%, Gold −3.32% → +6.72%). **"The thesis
holds directionally" is therefore not supported** — the comparison cannot
attribute anything to the conviction floor. Do not promote `loosened` to default
on this entry; wait for the day-alternating A/B (WP-21.B).

Two scoping notes, to be precise about what is and is not contaminated here:

* **This entry's own numbers are arm-clean.** It was written 2026-07-14, before
  the `exogenous` (from 07-27) and `kimi` (from 08-03) arms existed, so its
  baseline is pure market arm. The block confound is its only defect.
* **Later re-runs of the same metric were not.** Once the sibling arms began
  scoring, `commitment_by_arm` swept them into 'baseline' — by 2026-09-03 that
  was 1413 resolved calls instead of the market arm's 1239, and it *flattered*
  the baseline (wrong-decisive 0.276 vs the true 0.291; net edge −0.109 vs
  −0.128). `commitment_by_arm` is now scoped to the production arm, and the
  rendered verdict refuses to credit the loosened arm while the confound flag is
  set.

---

## KB-012 — Absorption ratio has no skill on the current asset set (needs a homogeneous cross-section) (WP-16.A.6)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/fragility_backtest.py` (walk-forward, de-overlapped; still **zero
LLM/API cost**, yfinance only). Reproduce: `python fragility_backtest.py` (prints
the `absorption` component AUC) and `run_weight_ablation(..., schemes=absorp_*)`.

**What we tested.** The first upgrade idea for the fragility monitor (KB-001/002):
replace the near-dead `correlation_tightening` component with the **Absorption
Ratio** (Kritzman, Li, Page & Rigobon 2011) — the fraction of cross-asset return
variation captured by the top eigenvectors of the return co-movement structure, a
peer-reviewed leading indicator of drawdowns. Implemented as `absorption_ratio()`
in `fragility.py`, scored on the paper's standardized shift `(AR_short − AR_long)/
σ(AR)`, using the **correlation** matrix (standardized returns) rather than raw
covariance so one high-vol asset (oil/BTC) can't dominate the heterogeneous set.
Wired in as a **shadow component (DEFAULT weight 0)** — computed + logged, zero
impact on the live composite until it earns weight.

**Headline — no skill on this data feed.** Standalone component AUC (2008–2026):

| scoring | 5-day AUC (ov / nov) | 10-day AUC (ov / nov) |
|---|---|---|
| ΔAR shift_z | 0.502 / 0.515 | 0.531 / 0.503 |
| raw AR level | 0.526 / 0.522 | 0.544 / 0.468 |
| AR_short level | 0.542 / 0.532 | 0.551 / 0.482 |

All three scorings land at 0.47–0.55 — indistinguishable from chance, and from the
dead `correlation` component (0.51–0.55) it was meant to replace. The composite
ablation agrees: giving absorption weight yields a noise-level +0.004 AUC bump but
makes the **honest episode metrics uniformly worse** (recall 0.293→0.276→0.224→
0.207 and alarm precision 0.688→0.611→0.444→0.350 as its weight rises). **Not
adopted.**

**The nuance that matters (why, not just that).** This is *not* a refutation of the
absorption ratio — it is untestable on the current inputs. AR needs a **broad,
homogeneous cross-section** (Kritzman used dozens of US industry/sector portfolios)
where the top eigenvector is a clean "market factor" whose rise signals systemic
coupling. Macro-Assist fetches only ~5 **heterogeneous** assets (equities, gold,
oil, DXY, BTC); a 5–6-asset heterogeneous correlation matrix has no stable factor
structure, so its eigen-fraction is noise. The proper AR test requires **adding a
sector-ETF / industry cross-section** to the data layer — a bigger change, deferred.

**Side confirmations (free).** (a) The KB-002 baseline reproduced **exactly**
(composite nov-AUC 0.720/0.691, episode recall 0.30/0.29), confirming the raised
`_LOOKBACK` (180→300, to give AR a baseline) does not disturb any pre-existing
component. (b) `vix_term` re-confirmed as the single strongest component (AUC 0.75
@5d) — still capped for being semi-circular.

**What it changes.**
- `fragility.py` gains `absorption_ratio()` + an `absorption` key in
  `DEFAULT_WEIGHTS` **at 0.0 (shadow)** — logged for the record, no composite
  impact. Backtest gains the `absorption` AUC column + `absorp_*` WEIGHT_SCHEMES.
- **Next fragility experiments** should target the *existing* heterogeneous data:
  **④ Turbulence / Mahalanobis** (built for a small heterogeneous set) and **②
  the credit/funding channel** (orthogonal; the reserved `acceleration` slot is
  still empty — the likeliest lever on the ~0.30 recall ceiling). Revisit AR only
  if/when a sector cross-section is added to the fetch. **→ Resolved by KB-013:
  the cross-section WAS added; AR does have skill on it.**

---

## KB-013 — Absorption ratio DOES have skill on a homogeneous cross-section (KB-012 reversed) (IMP-1.3)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_absorption_gate`; **zero LLM/API cost** —
free Fama-French data + the reused `fragility_backtest` scorers). Reproduce:
`python input_testing.py`. First result of the **Project Improvement** track (see
`Project_Improvement.md`, IMP-1).

**What we tested.** KB-012 found the absorption ratio (AR) had no skill (AUC ≈
0.50) and diagnosed the cause as the input, not the concept: AR needs a *broad,
homogeneous cross-section*, but the live monitor sees only ~5 heterogeneous assets.
IMP-1 added exactly that missing ingredient — **Fama-French 30-industry daily
portfolios** (1970-2026 here; the file runs to 1926), a dedicated fragility
data source decoupled from the traded assets — plus a generic **input-testing
gate** (walk any candidate signal forward look-ahead-safe → de-overlapped AUC +
episode recall/precision vs FF-market drawdowns). We re-ran AR on this panel over
a covariance-window grid.

**Headline — the reversal.** AR has genuine, if modest, skill on the homogeneous
cross-section (non-overlapping AUC, 48-81 independent crises):

| AR cov-window | 5d nov-AUC | 10d nov-AUC | episode recall | alarm precision |
|---|---|---|---|---|
| 60  | 0.644 | 0.641 | 0.21 / 0.22 | 0.29 / 0.54 |
| 120 | 0.633 | **0.675** | 0.21 / 0.19 | 0.28 / 0.48 |
| 252 | 0.619 | 0.567 | 0.19 / 0.16 | 0.32 / 0.41 |

vs **≈0.50** on the 5 heterogeneous assets (KB-012). **The diagnosis was right: the
cross-section was the problem.** Shorter covariance windows (60-120) beat 252 — the
transition is tracked better by a nearer-term co-movement estimate.

**The nuance that's easy to forget.** Skill ≠ adoption. AR-on-industries is **still
weaker than the current baseline**: `var_led_vix35` posts nov-AUC 0.72/0.69 and
episode recall ~0.30 (KB-002), while AR alone manages ~0.64-0.68 AUC and only
~0.20 recall. So AR does **not** replace the composite. The open question is
**orthogonality**: AR is computed on an entirely different data source (equity
industry panel) than the variance/vix components (index + VIX), so a weak-but-
uncorrelated signal could still lift the *ensemble*. That ensemble test is the next
gate, not settled here.

**Caveats.** (a) Run at `stride=5` (every 5th trading day) to keep the eigen-heavy
walk tractable — fine for an AUC estimate, but re-run dense before any adoption
decision. (b) FF-market drawdowns (not SP500) are the label here, for a common deep
history with the industries; slightly different target than KB-002's ^GSPC. (c) The
ov/nov AUC ordering flips in places (e.g. cov=120 10d: ov 0.562, nov 0.675) — small-
sample noise; treat the episode metrics as the sturdier read.

**What it changes.**
- Establishes `input_testing.py` as the reusable IMP-# gate (fetch FF cross-section
  → `walk_forward_signal` → `evaluate_signal`).
- AR stays at **shadow weight 0** in `fragility.py` pending the orthogonality/
  ensemble test on a common period. If it fails that, it stays shadow-logged as a
  diagnostic; if it passes, it graduates to a real weight.
- **Next (IMP-1.4/1.5):** run **turbulence / Mahalanobis** through the same gate on
  this panel, and test whether AR (and/or turbulence) is *additive* to the live
  composite over a common window.

---

## KB-014 — Financial turbulence is a recall instrument, complementary to absorption's precision (IMP-1.4)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_turbulence_gate`; **zero LLM/API cost** —
same free FF panel + reused scorers). Reproduce: `python input_testing.py
turbulence`. Second Project-Improvement result (`Project_Improvement.md`, IMP-1.4).

**What we tested.** Financial turbulence (Kritzman & Li 2010) — the Mahalanobis
distance of the latest industry-return vector from the trailing cross-sectional
mean, in the metric of the trailing (diagonal-shrunk, `shrink=0.2`) covariance,
smoothed over the last 5 days — run through the **same gate** as the absorption
ratio on the FF 30-industry panel (1970-2026), cov-windows 120/252. Where AR reads
the *eigenstructure* of co-movement, turbulence reads the *surprise* of the newest
observation against it — designed to be a different lens on the same panel.

**Headline — a different operating point, not a better one.** Turbulence's AUC is
comparable-to-slightly-weaker than AR's, but its precision/recall trade sits at the
**opposite end**:

| cov | horizon | nov-AUC | episode recall | alarm precision | n_alarms |
|---|---|---|---|---|---|
| 120 | 5d | 0.606 | **0.458** | 0.187 | 107 |
| 120 | 10d | 0.479 | 0.293 | 0.224 | 107 |
| 252 | 5d | 0.580 | **0.438** | 0.196 | 102 |
| 252 | 10d | 0.620 | 0.358 | 0.265 | 102 |

Contrast AR (KB-013): recall ~0.20, precision up to 0.54, ~25 alarms. **Turbulence
catches roughly twice as many crises (recall 0.44 vs 0.20) but fires ~4x as often
(≈105 vs ≈25 alarms), so its precision collapses to ~0.19.** Its 5d recall (0.44-0.46)
even beats the `var_led_vix35` baseline's ~0.30 — but only by trading away precision.

**The nuance that's easy to forget.** This is **not** a GO on its own. The nov-AUC
straddles the 0.60 gate line and is noisy (cov=120 10d dips to 0.479), and top-decile
precision under 0.20 is worse than baseline — as a standalone flag it would cry wolf.
The value is **behavioral complementarity**: AR = high-precision / low-recall (an eigen
read), turbulence = high-recall / low-precision (a surprise read), on the *same* panel.
That is precisely the shape that can help an **ensemble** — an any-channel-fires (OR)
or weighted blend could lift the composite's ~0.30 episode-recall ceiling without AR's
precision loss. That additivity test (IMP-1.5) is the actual decision gate.

**Caveats.** (a) One config only (`shrink=0.2`, `smooth=5`, `stride=5`, top-decile
flag); no sweep of shrink/smooth — precision especially may move with the flag
threshold, so read the *shape* (recall-heavy), not the exact numbers. (b) cov=60 was
not run — a 30×30 inverse from 60 obs is ill-conditioned even shrunk. (c) Same FF-market
(not ^GSPC) label and de-overlap caveats as KB-013.

**What it changes.**
- Adds `turbulence_signal` + `run_turbulence_gate` to the IMP harness.
- Sets up IMP-1.5 as a **two-candidate** ensemble test (AR *and* turbulence vs the live
  composite over a common window), with a clear prior: they occupy opposite precision/
  recall corners, so an OR-of-channels blend is the natural thing to try.
- Neither AR nor turbulence is wired live yet; both remain diagnostic until IMP-1.5.

---

## KB-015 — The cross-section is ORTHOGONAL: an OR-of-channels ensemble doubles crisis recall at equal precision (IMP-1.5)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_ensemble_gate`; **zero LLM/API cost**).
Reproduce: `python input_testing.py ensemble`. Third and decisive Project-Improvement
result (`Project_Improvement.md`, IMP-1.5) — the adoption gate for KB-013/KB-014.

**What we tested.** The open question from KB-013/KB-014 was **orthogonality**: AR and
turbulence each have skill on the industry panel, but do they add anything a
variance-led monitor doesn't already have? Test, all on ONE common window
(1971-2026, 2773 readings) and ONE label (FF-market ≥5% drawdowns):
- **B** = variance-trend on the FF market Close — a proxy for the live composite's
  *leading* (0.45) component, the honest non-circular baseline;
- **AR** (cov 120) and **TURB** (cov 252) on the industry panel;
- rank-blended ensembles (B+AR, B+TURB, B+AR+TURB) and an **OR-of-channels** flag
  (fire if ANY of B/AR/TURB is in its own top decile).

**Headline — orthogonality confirmed, and the recall ceiling breaks.** Episode recall
vs precision (the metric that actually matters for a risk gauge):

| signal | 5d recall | 5d prec | 10d recall | 10d prec | 5d/10d nov-AUC |
|---|---|---|---|---|---|
| B (variance-trend) baseline | 0.271 | 0.20 | 0.222 | 0.30 | 0.491 / 0.549 |
| B + AR + TURB (rank blend) | 0.271 | 0.26 | 0.259 | 0.38 | **0.586 / 0.610** |
| **OR-of-channels** | **0.646** | **0.219** | **0.494** | **0.324** | — (flag) |

Two distinct wins:
1. **The continuous blend adds AUC + precision.** B+AR+TURB lifts nov-AUC by +0.06-0.10
   over B and raises precision (0.20→0.26 at 5d, 0.30→0.38 at 10d) with recall held —
   AR and turbulence carry rank information the variance baseline does not.
2. **OR-of-channels breaks the recall ceiling at NO precision cost.** It catches
   **31/48** 5d crises (recall 0.65) vs the baseline's 13/48 (0.27) — *more than double* —
   while precision actually **rises** (0.20→0.219). Same at 10d (0.22→0.49 recall,
   0.30→0.324 prec). If the three channels were redundant, OR would just pile on alarms
   and crater precision; instead precision holds, which is the **signature of orthogonal
   channels catching DIFFERENT crises**. This is the ~0.30 episode-recall ceiling
   (KB-002) finally lifting — via cross-sectional breadth, not a better single signal.

**The nuance that's easy to forget.** The baseline B here is *deliberately conservative* —
variance-trend on the FF market ALONE, without the live composite's VIX-term arm (0.35,
no FF analogue). So part of OR's gain over B is B being weaker than the full
`var_led_vix35`. **This is strong evidence for the ensemble concept, not yet proof it beats
the full live composite.** But the orthogonality argument is structural and likely to
survive: the composite's variance and VIX arms are BOTH single-market stress reads (mutually
correlated), whereas AR/turbulence are cross-sectional — a different information source. The
required confirmation is re-running OR-of-channels against the REAL composite on the traded
assets, not against B.

**Caveats.** (a) Conservative baseline (above) — the headline is orthogonality/additivity,
not "beats production." (b) Full-sample `.rank(pct=True)` + full-sample top-decile cut, as in
KB-013/014 (consistent, fair comparison), but a live flag needs PIT-rolling thresholds — will
shift absolute numbers. (c) stride=5, single (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5)
config; FF-market (not ^GSPC) label. (d) n≈2 true macro crises dominate the episode counts;
regime-holdout CV (IMP-4) is still owed before any live weight.

**What it changes.**
- **GO on the ensemble hypothesis.** The industry cross-section adds orthogonal skill; an
  **any-channel-fires (OR) recall mode** is the mechanism that lifts recall without precision
  loss. This is direct empirical support for backlog **IMP-4** (OR-of-channels recall mode)
  and elevates it from "idea" to "validated direction."
- **Concrete next step (IMP-1.6 / promotion):** shadow-wire AR + turbulence computed on a
  homogeneous panel (FF for backtest; sector ETFs for a daily live feed) into the pipeline at
  weight 0, then validate OR-of-channels against the REAL `var_led_vix35` on the traded assets
  with PIT-rolling thresholds. Only then consider a live recall-mode flag.
- AR and turbulence remain **diagnostic (shadow)** in `fragility.py`; IMP-1 has established the
  cross-section is worth wiring, pending the real-composite confirmation. **→ Confirmed by KB-016.**

---

## KB-016 — Confirmed against the REAL composite: the cross-section doubles crisis recall, but it's a precision TRADE, not a free lunch (IMP-1.6)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_real_composite_gate`; traded assets via
yfinance + FF panel cached; **zero LLM/API cost**). Reproduce: `python
input_testing.py real`. The adoption gate for KB-015 — replaces the proxy baseline
with the real production signal.

**What we tested.** KB-015 showed the industry cross-section adds skill to a
*variance-trend-only proxy*, but flagged that the honest test is against the **full
live composite** (which also has the VIX-term arm the proxy lacked). So here the
baseline is the actual `var_led_vix35`, walked forward look-ahead-safe on the real
traded assets (SP500/VIX/VIX3M/gold/oil/DXY), scored against the real **^GSPC** ≥5%
drawdown label — the exact production setup (KB-002). Common window: 904 readings,
2008-07..2026-06 (composite ∩ industry channels, stride 5). Baseline reproduces
KB-002 (nov-AUC 0.744/0.664, recall ~0.33, precision 0.43-0.57).

**Headline — additivity CONFIRMED, but the shape changes vs KB-015.** OR-of-channels
(fire if composite OR AR OR turbulence hits its top decile) still roughly **doubles**
crisis recall against the full composite:

| horizon | composite recall / prec | OR-channels recall / prec | Δ |
|---|---|---|---|
| 5d  | 0.333 (6/18) / 0.429 | **0.722 (13/18)** / 0.323 | recall ×2.2, prec −0.11 |
| 10d | 0.321 (9/28) / 0.571 | **0.643 (18/28)** / 0.387 | recall ×2.0, prec −0.18 |

The cross-section catches crises the traded-asset composite misses — orthogonality
holds against the *real* signal, not just the proxy. **BUT** precision now **drops**
(unlike KB-015, where it held against the weak baseline): the real composite's VIX arm
already gives it strong top-decile precision, so OR-ing in the weaker-precision channels
trades ~0.11-0.18 precision for the doubled recall. Against the full composite it is a
**precision/recall trade, not a free lunch.**

**The nuance that's easy to forget.** (1) **The equal-weight continuous blend is the
WRONG adoption form.** Blending (composite+AR+TURB, rank-mean) *lifts* threshold-free
nov-AUC (0.744→0.787 at 5d, 0.664→0.689 at 10d) — the channels do carry orthogonal rank
info — but it *degrades* the validated top-decile flag (recall 0.333→0.278, precision
0.429→0.312), because averaging dilutes the composite's already-strong best alarms. So
the AUC gain and the flag-quality loss point in opposite directions; a naive blend
throws away the composite's edge. (2) **The trade is acceptable *for this product
specifically*:** fragility is a tail-risk / range-widening gauge that is NEVER a
directional call, so a false alarm is cheap (it over-widens a range) while a missed
crisis is expensive — an operating point of recall 0.72 / precision 0.32 (still ~8×
the 4% base rate) is a *good* trade here, though it would be a bad one for a directional
signal.

**Caveats.** (a) Small crisis count — 18 (5d) / 28 (10d) episodes over ~7 real macro
events (GFC, 2011, 2015-16, 2018, COVID, 2022, …); episode metrics are small integers,
indicative not precise. Regime-holdout CV (IMP-4) still owed. (b) Full-sample rank
thresholds (look-ahead in the *threshold*) — a live flag needs PIT-rolling cuts, which
will move absolute numbers. (c) Window capped at FF cache end (2026-06-30); stride 5;
single (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5) config. (d) Industry channels
run on FF (backtest only); a live feed needs a daily sector/industry panel (sector ETFs).

**What it changes.**
- **IMP-1 CLOSES positive.** The cross-section adds genuine orthogonal skill to the real
  composite; the ~0.30 recall ceiling is breakable. Concept proven end-to-end
  (KB-012 negative → KB-013/014 skill → KB-015 orthogonal → KB-016 confirmed live-baseline).
- **Adoption form is decided:** an explicit **OR-of-channels recall MODE** (a distinct
  high-recall flag), NOT a weight in the composite and NOT an equal blend. This is exactly
  backlog **IMP-4** — KB-016 hands it a validated mechanism and a live operating point.
- **Deliberately NOT auto-wired.** Because it's a precision trade (not a free lunch) and
  needs (i) a live daily industry panel and (ii) PIT-rolling thresholds and (iii) regime-
  holdout CV, promotion is IMP-4 work, not a silent live change. AR & turbulence stay
  shadow/diagnostic until then.
- A small *weighted* addition (composite-dominant + channels at low weight) is an open
  alternative to test in the WEIGHT_SCHEMES ablation — it might capture the blend's AUC
  gain without the top-decile dilution. Untested; noted for IMP-4.

→ **Both owed caveats [(a) regime-holdout CV, (b) PIT thresholds] resolved by KB-017.**

---

## KB-017 — The OR-of-channels recall doubling SURVIVES honest CV: leakage was negligible, live-safe thresholds hold it (IMP-4)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_holdout_cv`; same channels as
`run_real_composite_gate`, **zero LLM/API cost**). Reproduce: `python
input_testing.py holdout`. Closes the two caveats [KB-016] left open.

**What we tested.** KB-016 confirmed the OR-of-channels flag (fire if the real
`var_led_vix35` composite OR industry-panel absorption OR turbulence hits its top
decile) roughly *doubles* crisis recall — but with two honest-evaluation debts: the
decile cut was ranked over the **whole window** (the thresholds had already seen the
test crises), and it had never been checked out-of-sample across regimes. This
re-scores the identical channels under three protocols on the same 904-reading window
(2008-07..2026-06): **[1] in-sample** (KB-016 protocol, reference), **[2] in-sample
restricted to the post-warmup window** (isolates window-shrink from leakage), **[3]
PIT expanding-window thresholds** — each day's decile cut fit only on that channel's
own past, 252-day warm-up, 652 evaluable readings (the realistic LIVE protocol), and
**[4] leave-one-crisis-out** — each drawdown episode is a fold, thresholds fit on every
day *outside* it (the generalization headline).

**Headline — the doubling is REAL, not a thresholding artifact.**

| protocol | composite recall (5d/10d) | OR-channels recall (5d/10d) | OR precision (5d) |
|---|---|---|---|
| [1] in-sample (KB-016) | 0.333 / 0.321 | 0.722 / 0.643 | 0.323 |
| [3] PIT (live-safe) | 0.25 / 0.333 | **0.833 / 0.867** | 0.320 |
| [4] leave-one-crisis-out | 0.333 / 0.321 | **0.611 / 0.643** | (see nuance) |

[1] reproduces KB-016 to the digit (regression check on the refactor). The decisive
comparison is **[2] vs [3]: they are nearly identical** (OR 5d 0.75 vs 0.833; 10d 0.867
vs 0.867) — so replacing full-sample thresholds with strictly PIT-safe ones **barely
moves the result**. The look-ahead in the threshold that KB-016 flagged was **negligible**;
the doubling was never an artifact of it. Under the strictest test (LOCO, thresholds
that never saw the held-out crisis) OR recall still ~doubles composite-alone. Precision
holds at ~0.32 (5d) across protocols — the same operating point, not a new cost.

**The nuance that's easy to forget.** (1) **PIT recall > in-sample recall here**
(0.833 vs 0.722 at 5d) — not because live is magically better, but because the warm-up
drops the 2008 window down to 12/15 episodes and the survivors are the ones the
expanding cut calls easily; read PIT and in-sample as *the same story on a smaller,
cleaner denominator*, not as a live improvement. (2) **LOCO 5d (0.611) sits below PIT
(0.833)** because LOCO scores all 18 crises including the early GFC ones on a
leave-one-out cut; it is the *conservative floor*, and the floor is still ~2× composite.
(3) **LOCO precision is deliberately not computed** — leave-one-out test windows are too
short for an honest precision denominator; precision is read from PIT (~0.32), where the
non-crisis days exist to divide by. (4) The whole exercise **validated the yardstick, not
just the signal**: `run_holdout_cv` is now the honest gate, so a NEW channel's "recall
went up again" only counts if it survives PIT+LOCO — otherwise it is the mechanical
artifact of OR-ing another signal onto ~7 crises.

**Caveats.** (a) Small crisis count persists — 12–28 episodes; the point estimates are
indicative, but the *robustness across four protocols* is the real evidence, not any
single number. (b) FF industry channels are still the backtest feed; a live flag needs a
daily sector/industry panel (the ONE remaining plumbing item — thresholds are now shown
PIT-safe). (c) Single (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5, q=0.90, warmup=252)
config; window capped at FF cache end (2026-06). (d) LOCO fits on all *other* crises
(leave-one-out, not leave-one-regime-block-out); with n≈7 macro events that is the honest
maximum, but it is not a train-early/test-late split.

**What it changes.**
- **Resolves KB-016 caveats (a) and (b).** Regime-holdout CV done; PIT-safe thresholds
  done; the doubling survives both. The OR-of-channels recall mode is validated end-to-end
  on honest evaluation, not just the in-sample gate.
- **Operating point for the IMP-4 build is set:** OR recall MODE at the PIT point
  (recall ~0.83 / precision ~0.32 at 5d, ~0.87 / ~0.36 at 10d) — a distinct high-recall
  flag, NOT a composite weight (confirmed by KB-016's blend-degradation).
- **`run_holdout_cv` is now the adoption GATE for new channels.** Before IMP-2
  (credit/funding) or IMP-3 (downside semivariance) may enter the OR set, each must lift
  PIT/LOCO recall without collapsing precision through this harness — the guard against
  overfitting the OR knob on ~7 crises.
- **Remaining IMP-4 plumbing narrows to one item:** a live daily sector/industry ETF panel
  (thresholds are no longer a blocker). No live wiring yet — still IMP-4 work, not a silent
  change.

---

## KB-018 — Downside asymmetry does NOT sharpen the variance-trend channel (IMP-3, negative)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_semivariance_gate`; **zero LLM/API cost**).
Reproduce: `python input_testing.py semivariance`. A negative — logged so the next
session does not re-run it (KB-012 discipline).

**What we tested.** The live leading component `realized_variance_trend` (B, 0.45 of
the composite) trends **symmetric** realized vol, which also rises in melt-ups. IMP-3's
hypothesis: a **downside-only** estimator is a sharper stress lead. Two candidates,
each swapped into the *identical* slope/normalize/squash pipeline (the `sym` mode
reproduces the live channel to the digit — the regression check): **downside
semi-deviation** `sqrt(mean(min(r,0)²))`, and **signed asymmetry** `down_var − up_var`
normalised by total realized variance. Walked forward look-ahead-safe on the FF market
(deep history, 49/82 crises at 5d/10d) and confirmed on the production **^GSPC** (2008+,
22/30 crises), scored with the de-overlapped gate metrics.

**Headline — NO-GO. Neither variant beats symmetric.**

| series / metric | B symmetric | downside semidev | signed asymmetry |
|---|---|---|---|
| FF 5d nov-AUC | **0.753** | 0.725 | 0.615 |
| FF 5d recall / prec | 0.265 / 0.197 | 0.286 / 0.203 | 0.224 / 0.129 |
| ^GSPC 5d recall / prec | **0.318 / 0.35** | 0.227 / 0.208 | 0.136 / 0.10 |
| ^GSPC 10d recall / prec | **0.333 / 0.50** | 0.333 / 0.417 | 0.233 / 0.233 |

Downside semi-deviation's only gain is +1 FF crisis at 5d (0.265→0.286), paid for by a
lower AUC (0.753→0.725) and worse 10d precision — and on the **production ^GSPC it is
outright worse** (5d recall 0.318→0.227, precision 0.35→0.208). Signed asymmetry is
decisively worse on every metric on both series (more alarms, lower precision, lower AUC).

**The nuance that's easy to forget.** *Why* downside decomposition doesn't help: a
rising-variance regime is already downside-dominated, so symmetric std and downside
semi-deviation carry nearly the **same** trend information — but the symmetric estimator
uses **all** observations, making it a lower-variance estimator of that same trend, while
restricting to negative returns throws away half the sample for no signal gain. The signed
difference is a noisy-minus-noisy quantity dominated by estimation error. **The variance-
trend channel already captures the downside information**; there is no orthogonal downside
signal left to extract by decomposition.

**Caveats.** (a) Single default config (vol_window=20, trend_window=60, k=2.5); a
vol_window sweep was deliberately NOT run — the effect is *worse on the production asset*
and AUC-negative on FF, so a parameter search to rescue a marginal FF-only recall bump
would be fishing on ~7 macro events, exactly the overfitting trap [KB-017] guards against.
(b) Small crisis counts; episode metrics indicative. (c) This tested downside asymmetry as
a *variance estimator* swap; it does NOT rule out a genuinely orthogonal non-price downside
channel (that is IMP-2, credit/funding — untouched here).

**What it changes.**
- **IMP-3 CLOSES negative.** The variance-trend channel stays symmetric; no change to
  `fragility.py`. The candidate code stays in the harness, unwired.
- **Redirects the recall-ceiling effort to IMP-2** (credit/funding: HY OAS + NFCI) — a
  genuinely orthogonal, non-price channel — as the remaining live lever on the ~0.30
  episode-recall ceiling, to be run through the [KB-017] `run_holdout_cv` gate before it
  may enter the OR set.

---

## KB-019 — A credit channel has standalone skill but is REDUNDANT in the OR set: it adds no live recall at held precision (IMP-2, NO-GO — confirmed on canonical BAA10Y)

**Date:** 2026-08-26 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_credit_gate`; **zero LLM/API cost**).
Reproduce: `python input_testing.py credit fred` (canonical Moody's **BAA10Y**, needs
`FRED_API_KEY`) or `python input_testing.py credit proxy` (Yahoo HYG/IEF, no key).
**Confirmed:** the proxy and the canonical credit spread give the SAME verdict — the
same +0 PIT-recall, the same precision cost, and the same two marginal LOCO crises
(see the confirmation note). Not preliminary.

**What we tested.** IMP-2's premise: the live composite is entirely equity-market
(SP500 variance-trend + VIX term), so a **credit/funding** stress channel — spreads
leading equity stress through a *different* market — is the orthogonal, non-price
lever most likely to lift the ~0.30 recall ceiling, and the natural fill for the
reserved `acceleration` slot. Canonical inputs are FRED **HY OAS** (`BAMLH0A0HYM2`)
and **NFCI**; FRED's Akamai WAF silently drops requests from this network, so the
run used the Yahoo-reachable **HYG-vs-IEF** proxy: a synthetic HY spread
`−log(HYG/IEF)` (rises when HY underperforms duration-matched Treasuries), plus its
20-day widening **velocity** (the leading form). Two questions, both look-ahead-safe:
(1) **standalone** skill vs ^GSPC drawdowns; (2) **OR-set admission** — added as a
4th OR channel beside composite/AR/TURB, does it lift recall under the [KB-017]
holdout (in-sample → PIT → LOCO) WITHOUT collapsing precision?

**Headline — real standalone skill, but REDUNDANT as an OR channel.**

*Standalone (^GSPC 2008+, full daily):* credit **LEVEL** clears the AUC bar —
5d nov-AUC **0.676**, 10d **0.607** — at baseline-tier recall/precision (~0.28).
Velocity is noisier (5d nov-AUC 0.566, below bar). So credit stress genuinely leads
drawdowns; it is *not* a no-skill negative like [KB-012].

*OR-set admission (the decisive bar), CREDIT = velocity, on the shared composite grid:*

| protocol | OR 3-ch (comp/AR/TURB) | OR 4-ch (+CREDIT) |
|---|---|---|
| **PIT 5d** (live operating point) | recall **0.833** / prec **0.320** | recall **0.833** / prec 0.296 |
| **PIT 10d** | recall **0.867** / prec **0.360** | recall **0.867** / prec 0.333 |
| LOCO 5d (recall only) | 0.611 (11/18) | 0.667 (12/18) |
| LOCO 10d (recall only) | 0.643 (18/28) | 0.679 (19/28) |

At the **PIT live operating point credit adds ZERO recall and only costs precision**
(0.320→0.296 at 5d, 0.360→0.333 at 10d): its top-decile days coincide with crises the
trio already flags. Under LOCO it adds exactly **+1 crisis** at each horizon (2015-08
China-devaluation; 2010-05 flash-crash) — but LOCO is recall-only, and that +1 does not
survive the PIT precision cost. (Regression check: the 3-channel PIT reproduces [KB-017]'s
0.833/0.32 to the digit, confirming the window is aligned.)

**The nuance that's easy to forget.** *Why* an orthogonal-looking input adds nothing at
the margin: in a **5%+ equity drawdown, credit spreads and equity vol/absorption co-move
tightly** — deep spread widening *is* deep equity stress — so a credit OR channel mostly
**re-flags crises the trio already catches**. Standalone AUC (0.68) measures ranking skill
across *all* days; the OR flag only benefits from days in credit's **top decile that the
other channels miss**, and those are nearly empty. This is the OR-set version of the
[KB-018] lesson: a second estimator of the same latent stress adds no *new* recall, only
alarms. Orthogonality in normal times ≠ orthogonality in the tail.

**Confirmation on a canonical credit spread (the owed rerun, done).** The numbers above are
the initial **HYG/IEF proxy** run. The canonical rerun was blocked by a data-availability
surprise worth recording: **ICE license-truncated its BofA OAS series on free FRED to
~2023-08 onward** — `BAMLH0A0HYM2` (HY) and `BAMLC0A0CM` (IG) return only ~3yr now
(the FRED API's own `observation_start` reports 2023-08-28; `count`≈795), so the classic
1996+ HY OAS is **no longer freely available** and cannot back a 2008+ backtest. The
deep-history substitute is **`BAA10Y`** — Moody's Baa corporate yield minus 10Y Treasury,
daily, unrevised, 1986+ (Moody's series are not ICE-licensed). Re-running the gate on
BAA10Y (`source='fred'`) reproduces the proxy verdict essentially to the digit: standalone
5d nov-AUC 0.611 (velocity) / 0.674 (level) — real skill; OR-set **PIT 0.833→0.833 at 5d,
0.867→0.867 at 10d** (recall unchanged, precision 0.286→0.267 / 0.321→0.30); **LOCO +1
crisis each, the SAME two events** (2015-08, 2010-05). Two independent credit spreads (an
equity-correlated HY ETF and an unrevised IG bond spread) agreeing on the same marginal
crises confirms the redundancy is a **tail property, not a data-source artifact**.

**Caveats.** (a) **Confirmed across two sources** (HYG/IEF proxy + Moody's BAA10Y). BAA10Y
is investment-grade, so slightly *less* crisis-sensitive than true HY OAS — but the proxy is
HY-flavored and agrees, bracketing the answer. The ICE HY OAS deep history being paywalled
is the only reason it wasn't the primary; it would very likely land in the same place.
(b) **No parameter sweep** (vel_window=20, q=0.90 fixed) — deliberately,
per the [KB-017]/[KB-018] discipline: fishing vel_window on ~18 crises to manufacture a +2
would be the exact overfitting trap the CV gate exists to prevent. (c) Velocity was used as
the OR channel (the leading, less-collinear form); LEVEL is *more* collinear with the
composite in crises, so it would add even less orthogonal recall. (d) Small crisis counts;
episode metrics indicative.

**What it changes.**
- **IMP-2 CLOSES negative — confirmed on two sources.** Credit does NOT clear the OR-set
  admission bar: no live recall gain at held precision. No wiring into `fragility.py`;
  candidate code (`run_credit_gate`) stays in the harness.
- **The ~0.30 → ~0.83 recall ceiling stays where [KB-017] left it.** The OR set remains the
  IMP-1 trio (composite | AR | TURB); credit does not extend it. All three "add-a-channel"
  bids (IMP-2 credit, IMP-3 downside) are now exhausted.
- **The recall-ceiling search shifts from "add a channel" to "improve the operating point of
  the existing trio"** — IMP-4.2 (live daily sector/industry ETF panel) + IMP-4.3 (build the
  OR recall MODE flag at the validated PIT point).
- **Reusable data-acquisition note:** ICE BofA OAS on free FRED is truncated to ~2023+; use
  **BAA10Y** (deep, unrevised) for a credit spread. FRED's `fredgraph.csv` graph host is
  WAF-blocked to scripts AND clips browser CSVs to ~3yr; the **FRED JSON API**
  (`api.stlouisfed.org`, free key in `FRED_API_KEY`) is unblocked and honors full history —
  it is the reliable path (`fetch_fred_series`).

---

## KB-020 — The live daily sector-ETF panel reproduces the FF backtest feed: the OR channels survive the feed swap (IMP-4.2)

**Date:** 2026-08-27 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`fetch_sector_etfs` + `run_etf_panel_gate`;
**zero LLM/API cost**, yfinance-only, cached). Reproduce: `python input_testing.py etf`.
Clears [KB-017] caveat (b) — the "one remaining plumbing item".

**What we tested.** The OR-of-channels recall mode ([KB-016]/[KB-017]) was validated with
absorption (AR) and turbulence (TURB) computed on the **Fama-French 30-industry** panel.
That panel is Ken French library data — updated monthly with a multi-week lag, so it can
seed a backtest but **cannot drive a daily live flag**. The daily-fresh substitute is the
**SPDR Select-Sector ETF panel** (the original nine sectors XLB/XLE/XLF/XLI/XLK/XLP/XLU/
XLV/XLY, all trading from Dec-1998, fetched via the same yfinance path as the traded
assets). Before wiring a live flag on it (IMP-4.3), the one question that matters: does the
**coarser** live feed (9 sectors vs 30 industries) reproduce the FF-fed operating point?
Both feeds were scored **on one shared window and one shared anchor grid** (comp ∩ FF ∩ ETF
channels; 855 readings, 2009-07..2026-06), so the ONLY variable is the feed, not the dates.

**Headline — the feed swap is a wash-to-slight-improvement; parity holds.**

| protocol (5d) | composite | OR (FF feed) | OR (ETF feed) |
|---|---|---|---|
| PIT recall / precision | 0.176 / 0.214 | 0.647 / 0.241 | **0.647 / 0.318** |
| LOCO recall (18 folds) | 0.167 | 0.389 (7/18) | 0.333 (6/18) |

At the **live PIT operating point (5d)** the ETF feed gives **identical recall** (0.647,
11/17) at **higher precision** (0.318 vs 0.241) on **fewer alarms** (22 vs 29) — strictly
better. At 10d the ETF feed catches one fewer crisis (0.65 vs 0.70) but again at much higher
precision (0.455 vs 0.345). **Standalone**, both ETF channels match or beat their FF twin
(5d nov-AUC: ETF-AR 0.597 vs FF-AR 0.572; ETF-TURB 0.713 vs FF-TURB 0.715; ETF recall ≥ FF
on both). The recall doubling vs composite-alone survives the swap intact.

**The nuance that's easy to forget.** (1) **These absolute numbers are LOWER than [KB-017]'s
headline** (FF OR PIT 5d = 0.647 here, not 0.833) — *not* a regression: the ETF intersection
trims the shared window to 2009-07+, a different (smaller) crisis composition than KB-017's
comp∩FF window. The parity claim rests on FF-vs-ETF **on identical dates**, where the feed is
the only moving part; the cross-window number is not comparable and is not the point. (2)
**LOCO nets FF +1 crisis, but it's a wash, not a loss** — the feeds catch slightly *different*
marginal events: FF uniquely catches 2018-10 and 2020-06 (a minor post-COVID-rebound wobble);
ETF uniquely catches **2022** (the bear-market onset FF misses). Arguably complementary rather
than one dominating. (3) **Coarseness didn't hurt where it was feared.** 9 names give ~2
Kritzman eigenvectors vs ~6 on 30 industries, yet AR skill held — because the sector panel is
*cleaner* (exchange-traded, survivorship-free, no reconstruction lag) even if lower-dimensional.

**Caveats.** (a) Small crisis count (17-18 folds on the shared window); point estimates
indicative, the FF/ETF *parity* is the evidence, not any single number. (b) The 2008 GFC core
sits mostly before the shared warm-up window, as in [KB-017] — neither feed is credited/blamed
for it here. (c) Single config (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5, q=0.90,
warmup=252, stride=5); not swept (KB-017/018 discipline). (d) The nine-sector panel is fixed
membership by design; XLRE (2015) and XLC (2018) are later splits *of* these nine and were left
out of the validated core to keep membership stable across the backtest — they can be added to
the live feed without re-tiling the market.

**What it changes.**
- **[KB-017] caveat (b) is CLOSED.** A live, daily, free, homogeneous cross-section now exists
  and is validated to reproduce the FF-fed OR operating point (≥ its precision, = its 5d recall).
- **IMP-4.2 is a GO — the feed is unblocked.** `fetch_sector_etfs` is the live panel; IMP-4.3
  (build the OR recall MODE flag in `fragility.py` at the PIT operating point) can now proceed
  on real live inputs, not a backtest-only feed.
- **No `fragility.py` change yet.** This validates the feed and its parity; wiring the flag is
  IMP-4.3, a distinct step. `fetch_sector_etfs` / `run_etf_panel_gate` live in the harness.
- **Reusable note:** to compare two cross-section feeds honestly, compute both channels on ONE
  shared anchor grid (independently-strided grids off different trading calendars almost never
  coincide → an empty intersection) and hold the label window fixed.

---

## KB-021 — The OR recall mode is wired live as a shadow flag (IMP-4.3): the live code path reproduces the KB-020 operating point

**Date:** 2026-08-27 · **Branch:** `main` · **Code:** `.macro-assist/fragility_or.py`
(live OR-mode engine), `.macro-assist/quant_context.py` (`FRAGILITY_OR_MODE` ladder),
`.macro-assist/fragility.py` (`turbulence_signal` graduated in), `fragility_backtest.py`
(`fetch_sector_etfs` graduated in). **Zero LLM/API cost**, yfinance-only. Reproduce:
`python fragility_or.py` (today's reading + a live-path PIT self-check). Closes IMP-4.

**What we built.** The OR-of-channels recall flag ([KB-016]/[KB-017]) fed off the live
sector-ETF panel ([KB-020]) is now a **distinct, live-computable flag**, kept separate from
the composite Elevated label. It fires when ANY of {composite `var_led_vix35`, absorption
ratio, turbulence} is at/above **its own point-in-time top-decile** — each channel's
threshold is the 90th percentile of all of *its* readings strictly before today (expanding
window, min 252 prior readings), i.e. `input_testing._pit_decile_or_flags` evaluated at the
last day. This is adopted as an explicit **MODE, not a composite weight** — [KB-016] showed a
blended weight lifts AUC but *degrades* the validated top-decile flag, so the channels stay
separate and are OR-ed at the flag level.

**Headline — the live path reproduces the validated operating point.** `fragility_or`'s own
PIT self-check (composite ∩ ETF, the honest live window — no FF, since FF can't exist live;
914 readings 2008-07..2026-08-27, 662 evaluable after warm-up):

| protocol (5d) | composite | OR mode |
|---|---|---|
| PIT recall / precision | 0.118 (2/17) / 0.154 | **0.588 (10/17) / 0.273** |
| PIT recall / precision (10d) | 0.238 (5/21) / 0.385 | 0.524 (11/21) / 0.364 |

The **~5× recall over composite-alone at 5d** (and ~2× at 10d) at held precision is the
[KB-016]/[KB-017]/[KB-020] signature, reproduced end-to-end by the live engine. It reads a
touch below KB-020's 0.647 because this window is `comp ∩ ETF` only (KB-020's parity window
was the narrower `comp ∩ FF ∩ ETF`, 855 readings), so one marginal crisis lands differently
— within the ±1 KB-020 already documented, **not** a regression. The harness gate still
reproduces KB-020 **byte-for-byte** after the two graduations (OR-ETF PIT 5d 0.647/0.318,
LOCO same "differs" crises), confirming the moves are behaviour-preserving.

**Today's live reading (2026-08-27): quiet.** composite 44th pct, absorption 49th, turbulence
76th — no channel in its top decile. Sensible for the benign late-August tape; the flag has
not yet fired live (same posture as the composite monitor, which has never gone Elevated live).

**How it's wired — a shadow ladder, output-neutral by default.** `FRAGILITY_OR_MODE`
(default **`off`**) mirrors the existing `FRAGILITY_MODE` shadow pattern but adds an `off`
floor: `off` = not computed (zero extra compute/network); `log` = computed daily + written to
the JSONL log only, never shown (accumulates the live record); `show` = rendered into the
context; `active` = + a behavioural directive when the flag fires (widen Target Ranges, add a
tail-risk bullet — **never** a Bias flip). Separate ladder from the composite because the OR
flag is a **heavy** computation (it walks the composite + live ETF channels forward each run
to fit PIT thresholds), so it is opt-in per run, not always-on.

**Caveats.** (a) The live-path number (0.588) is on a slightly different window than the
KB-020 gate (0.647); the *reproduction* is the evidence, not the second-decimal match.
(b) Same fixed config as KB-020 (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5, q=0.90,
warmup=252, stride=5); **not swept** (KB-017/018 discipline — ~17 crises can't support tuning
the OR knob). (c) The composite walk (2008→today) is the run-cost driver; the default `off`
imposes none, and no incremental-cache optimisation was built yet (documented, not premature).
(d) The flag has never fired live — its live behaviour is forward-observation only, like the
composite monitor.

**What it changes.**
- **IMP-4.3 is DONE; IMP-4 is closed.** The OR recall mode exists as a live flag at the
  validated operating point, fed off the live panel, adopted as a mode (not a weight).
- **Escalation path (unchanged discipline):** flip `FRAGILITY_OR_MODE=off → log` (a repo var,
  like `MACRO_PROFILE` / `FRAGILITY_MODE`) to start the live shadow record; escalate
  `log → show → active` only after the log looks sane AND (per the fragility-monitor rule) the
  loosened-profile A/B has resolved, so a new output lever doesn't confound it.
- **Library graduations:** `turbulence_signal` now lives in `fragility.py` (peer of
  `absorption_ratio`), `fetch_sector_etfs` in `fragility_backtest.py` (peer of
  `fetch_histories`); the harness imports both from there. The stated design — validated
  inputs graduate out of the `input_testing` harness into the library — is now realised.

## KB-022 — The bias label separates forward returns, but orders them BACKWARDS (bull-market confound isolated)

**Date:** 2026-09-03 · **Branch:** `claude/llm-prediction-quality-eval-3dwzlt` ·
**Harness:** `.macro-assist/bias_separation.py` (new), rendered into
`results/accuracy_report.md`, over 128 scored reports / 2012 resolved calls
spanning 2026-03-13 → 2026-08-21.

**The problem this answers.** In a sustained bullish phase the accuracy score
cannot distinguish skill from drift: Neutral is hard-coded to 0.5 and a Bullish
call scores 1.0 whenever the market happens to rise. A permanently-bullish model
looks competent while carrying zero information. The regime-robust question is
**discrimination**, not accuracy: *conditional on what the model said, what did
the market actually do?* If Bullish and Neutral calls are followed by the same
return distribution, the label is noise regardless of what the scoreboard says.

**What we measured.** Every resolved call contributes its realized `pct_change`
at T+5/T+10/T+20 (sign convention is uniform — positive is always the direction
a Bullish call claims, 10Y yield included). Returns are standardized within
(window, asset) before pooling, because Bitcoin moves ~10% in a fortnight and
DXY ~0.5%; pooling raw percentages would just measure which assets got called
Bullish. Significance uses a **block permutation test** (21-day blocks, 2000
draws): daily reports with a T+20 horizon overlap almost completely, so
permuting individual labels would treat ~2000 dependent observations as
independent and manufacture absurd p-values.

**Headline — the buckets are NOT the same, and the ordering is inverted:
Bearish > Neutral > Bullish at every horizon, widening with horizon.**

| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | p | Bear−Bull | p |
|---|---|---|---|---|---|---|---|---|
| All pooled | 2012 | **−0.211** | +0.028 | **+0.236** | −0.239 | 0.001 | **+0.448** | 0.001 |
| T+5 | 754 | −0.169 | +0.063 | +0.072 | −0.232 | 0.013 | +0.240 | 0.048 |
| T+10 | 692 | −0.189 | +0.015 | +0.248 | −0.205 | 0.040 | +0.437 | 0.001 |
| T+20 | 566 | −0.298 | −0.005 | +0.411 | −0.293 | 0.009 | **+0.709** | 0.001 |

*z is in standard deviations of that asset's own move over that horizon.*

So the answer to "is T+5/10/20 different when it calls Bullish vs Neutral?" is
**yes, materially — and it gets worse with horizon.** Bullish out-returned
Neutral in only **4 of 18** asset×window cells. The monotone widening of
Bear−Bull (0.24 → 0.44 → 0.71 sd) is the most robust feature in the data.

**Why the scoreboard hides it.** Mean score by bias: Bullish **0.457**, Neutral
**0.500**, Bearish **0.386**. Neutral scores highest simply because it is pinned
to 0.5 — the metric is structurally incapable of showing that Neutral periods
were the ones with clean upside, or that Bearish calls preceded the *strongest*
rallies. The separation only becomes visible once you look at realized returns
conditional on the label.

**Premise correction.** The pipeline is not mostly-bullish in the aggregate:
across all resolved calls it is **Neutral 54.4% / Bullish 27.4% / Bearish 18.1%**.
The bullish tilt is real but lives *inside* the directional subset (60.2% of
committed calls are Bullish) and is heavily asset-specific (Gold 64% Bullish;
DXY only 5% Bullish vs 42% Bearish).

**Caveats — what is robust and what is not.** The Bear-vs-Bull ordering survives
every cut; the **Bull-vs-Neutral gap specifically does not**:

| Cut | Bull−Neut | p |
|---|---|---|
| All | −0.239 | 0.001 |
| Excl. Bitcoin & WTI | −0.086 | 0.19 |
| S&P + 10Y only | −0.308 | 0.006 |
| First half (Mar–Jun) | −0.325 | 0.000 |
| Second half (Jun–Aug) | −0.075 | 0.28 |

(a) Much of the pooled Bull−Neut gap is carried by **WTI and Bitcoin**, the two
highest-volatility assets, where Bullish calls were catastrophic (WTI Bullish
−6.02% mean vs Bearish +4.72%; Bitcoin Bullish −3.83% vs Neutral +3.72%).
(b) It is **concentrated in the first half of the sample** and largely absent
after June — consistent with a handful of bad commodity/crypto calls in one
stretch rather than a stable law. (c) With 109 report-dates and 21-day blocks
there are only ~5 independent blocks, so these p-values are indicative, not
confirmatory. (d) This is *not* a licence to fade the model: the inversion is
strongest exactly where the model commits on the most volatile assets, which is
also where a reversed strategy would carry the most risk.

**Relationship to KB-007.** KB-007 showed the *confidence number* is
anti-informative (BSS<0). This is the sibling result one level up: the *bias
label itself* is anti-informative in the same direction. Together they say the
problem is not miscalibrated sizing on top of a good signal — the directional
signal is itself pointing the wrong way, and confidence amplifies it. Notably
the low-confidence Bullish calls are the worst (T+20 Bullish z: conf<55 **−0.96**,
conf 55–65 −0.04, conf≥65 −0.01), i.e. the model's own hedging flag is where the
damage concentrates.

**Why it matters / how to apply.** Discrimination is now the regime-robust
companion metric to Brier: accuracy can drift with the market, but "do the
buckets separate, and in which order?" cannot. Decision metric: **Bull−Neut > 0
with the ordering `aligned`** is the target; the current `inverted` verdict means
no directional output should be sized up until it flips. Concretely this
strengthens the WP-16.B.1 case — the loosened (abstain-capable) arm should push
Bullish calls back toward the Neutral bucket, and this metric will show whether
the calls it *stops* making were the value-destroying ones. Re-check the
per-asset table before reading anything as a contrarian signal.

---

**⚠️ CORRECTED 2026-09-03 — the n=2012 pool mixed three prediction systems.**
[KB-023] found that the `market`, `kimi` and `exogenous` arms write score files
sharing a `report_date`, so the table above pools **market 1838 / kimi 150 /
exogenous 24** resolved calls. `bias_separation.py` now defaults to the `market`
arm. **The finding survives — every sign and the inverted ordering hold** — but
these are the figures to quote:

| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | 95% CI | p | Bear−Bull | p |
|---|---|---|---|---|---|---|---|---|---|
| All pooled | 1838 | **−0.207** | +0.025 | **+0.216** | −0.233 | [−0.53, +0.11] | 0.001 | **+0.424** | 0.001 |
| T+5 | 652 | −0.157 | +0.058 | +0.043 | −0.215 | [−0.46, +0.04] | 0.028 | +0.201 | **0.130** |
| T+10 | 623 | −0.191 | +0.018 | +0.219 | −0.209 | [−0.57, +0.17] | 0.057 | +0.410 | 0.003 |
| T+20 | 563 | −0.281 | −0.006 | +0.390 | −0.276 | [−0.60, +0.13] | 0.024 | **+0.671** | 0.001 |

Three things change in the reading, all in the direction of *less* certainty:

1. **"Bear−Bull is significant at every horizon" no longer holds at T+5** —
   p goes 0.048 → **0.130** once the other arms are removed. The monotone
   widening with horizon (0.20 → 0.41 → 0.67) is intact and remains the most
   robust feature in the data, but the short horizon is not carrying it.
2. **The bias shares shift slightly**: market-arm only is Neutral 55.6% /
   Bullish 26.0% / Bearish 18.4% (pooled: 54.4 / 27.4 / 18.1).
3. **Every gap now carries a bootstrap interval, and they are wide.** The pooled
   Bull−Neut interval [−0.53, +0.11] *includes zero*. The permutation p-value of
   0.001 and an interval spanning zero are not contradictory — they answer
   different questions (is the pairing non-random? vs how big is the effect?) —
   but the honest summary is: **the ordering is established, the magnitude is
   not.** Caveat (c) below already said the p-values are indicative; the interval
   is the quantitative version of that warning and should be quoted with the gap.

---

## KB-023 — The loosened arm's "repaired" separation is NOT established: arm and period are perfectly confounded (KB-022 follow-up)

**Date:** 2026-09-03 · **Branch:** `claude/directional-product-validation-0l70pa` ·
**Harness:** `bias_separation.py` primitives (`observations`, `_standardize`,
`_gap`, `block_permutation`) re-run over the same 128 score files as KB-022, but
with **per-file** `profile`/`arm` attribution and a block bootstrap added.

**The claim under test.** After KB-022 found the bias label inverted
(Bull−Neut = −0.239 pooled), the loosened arm (conviction floor OFF) looked like
the fix: bull-rate 19.7% vs 29.1%, **Bull−Neut = −0.008, p=0.93** — the inversion
apparently gone. Those numbers reproduce exactly. The question is whether they
are evidence about the *arm*.

**Headline — they are not. Three independent reasons, any one of which is
sufficient.**

**[1] There is no contemporaneous control at all — not a thin one.**

| Arm | dates | span |
|---|---|---|
| market / baseline (floor on) | 69 | 2026-03-13 → **2026-06-26** |
| market / loosened (floor off) | 40 | **2026-06-29** → 2026-08-21 |

The two arms share **zero** report-dates. `MACRO_PROFILE` was switched in one
block, so "loosened vs baseline" and "July–August vs March–June" are the *same
partition of the data*. No statistical treatment can separate them.
(An earlier read put the contemporaneous control at "16 dates, gap −0.216."
That was an artifact of the date-key collision in [3] — those 16 dates are
`kimi`/`exogenous` files, not baseline market-arm ones. The true overlap is 0.)

**[2] The assets that generated the inversion reversed sign between the two
periods.** Mean realized `pct_change`, model-independent:

| Asset | T+20 baseline | T+20 loosened | Δ |
|---|---|---|---|
| WTI Oil | −5.92% | **+6.24%** | +12.17 |
| Bitcoin | −1.58% | **+7.38%** | +8.97 |
| Gold | −3.32% | **+6.72%** | +10.04 |
| S&P 500 | +3.51% | +2.29% | −1.22 |
| DXY | +0.30% | −1.21% | −1.51 |

KB-022 named WTI and Bitcoin as the assets carrying the pooled Bull−Neut gap
(excluding them collapsed it to −0.086, p=0.19). Those are precisely the three
series that flipped from strongly negative to strongly positive across the arm
boundary. A permanently-bullish label looks *terrible* in the first period and
*fine* in the second for reasons that have nothing to do with the prompt.

**[3] The loosened gap is uninformative, not null.** Block bootstrap (21-day
blocks, 4000 draws) on the loosened arm:

| Arm | Bull−Neut | 95% CI |
|---|---|---|
| loosened | +0.014 | **[−0.250, +0.424]** |
| baseline | −0.220 | [−0.559, +0.068] |

The loosened interval **contains the baseline point estimate**. p=0.93 means the
40-date, 2-block, 118-Bullish-call sample cannot detect an effect the size of the
one KB-022 found — not that the effect is absent. And with the flipped assets
removed, the loosened arm is **still inverted**: Bull−Neut = **−0.184**
(nBull=54) vs baseline **−0.280** (nBull=90). Once the period effect is stripped
out, most of the apparent repair goes with it.

**Secondary finding (data hygiene, affects every future analysis).** The three
prediction arms write score files that **share a `report_date`**: `2026-08-03.json`,
`2026-08-03__kimi.json` and `2026-08-03__exogenous.json` all carry
`report_date: 2026-08-03`. Any join or dict keyed on `report_date` silently
overwrites one arm's metadata with another's — which is exactly how the phantom
"16-date contemporaneous control" above was produced. Attribution must key on
the **file**, not the date.

Consequence for KB-022: its n=2012 pool is **market 1838 / kimi 150 / exogenous
24** — three different systems in one bucket. The conclusion survives the split
(market-only: Bull−Neut = **−0.233**, p=0.001, Bear−Bull = **+0.424**, p=0.0005),
but the provenance has to be stated, and `bias_separation.py` needed an arm
filter before it was cited again — now shipped, see "What was fixed" below.

**The nuance that's easy to forget.** (a) This is **not** a finding that
loosening fails — it is a finding that the experiment as run cannot answer the
question either way. The commitment result [KB-011] rests on the same
block-switched data and inherits the same defect (its own caveat (c) already
said so). (b) The baseline arm's own halves are stable (Bull−Neut −0.291 then
−0.280), so there is no evidence of a pre-existing drift that the loosened
window merely continued — the discontinuity is at the period boundary, not
inside the baseline. (c) 21-day blocks over 40 dates give the loosened arm **2**
blocks; the permutation test is near-degenerate there and the p-value should not
be read as a measurement. (d) None of this touches KB-022's robust half
(Bear−Bull ordering), which was never claimed to be repaired.

**Why it matters / how to apply.**
1. **Do not promote `loosened` to default on current evidence.** Both metrics
   cited for it (KB-011 commitment, KB-022 separation) are confounded with the
   market period in the same way. This reverses the earlier "it's the one change
   with evidence behind it" read.
2. **Day-alternating arm assignment is now a prerequisite, not a refinement.**
   Any block-switched A/B on this pipeline is unreadable by construction; with
   ~5 independent 21-day blocks in the entire scored history, block switching
   spends the whole sample on one comparison and still confounds it.
3. **Arm-filter `bias_separation.py` and `summarize_accuracy.py`** before either
   is cited for an arm claim.
4. **Strategic:** three metrics still say the directional product does not work
   (accuracy <50%, BSS<0 [KB-007], inverted separation [KB-022]), and the one
   result that looked like a repair does not survive scrutiny. The open question
   is no longer "which prompt lever fixes it" but "**is this task learnable from
   this payload at all**" — which is a numeric question with a cheap answer
   (Phase 21), not another prompt A/B.

**What was fixed (2026-09-03, same branch).** The findings above are now
enforced by the tooling rather than left as a warning in a document:

* **Arm scoping.** `bias_separation.py` and `summarize_accuracy.py` default to
  the production `market` arm (`--arm all` pools deliberately). `arm_of()` is the
  single resolver, and it maps the scorer's literal `"unknown"` sentinel to the
  primary arm so the pre-arm-machinery history is not silently dropped. Every
  report and JSON now carries an `arm` field plus an `arm_composition` table
  naming what was scored and what was excluded.
* **The date collision cannot recur.** `observations()` reads `arm`/`profile` off
  each report as it flattens it; nothing keys on `report_date`. A regression test
  builds the exact collision (two arms, one date) and asserts they stay apart.
* **A confound guardrail.** `date_overlap()` / `profile_confound()` compute
  report-date overlap between profiles, and both the accuracy report and the
  separation section print a ⛔ block when a pair shares zero dates. The
  commitment verdict refuses to say "the thesis holds" while that flag is set.
* **Intervals, not just p-values.** Every gap now carries a 95% block-bootstrap
  interval, and `_verdict()` reports **"inconclusive — underpowered"** rather
  than "no separation" when a high p-value comes with an interval wide enough to
  contain the effects already measured. This was a live misread: the loosened
  arm's `gap −0.008, p=0.93` rendered as *"the label carries no information"*.
* **A silently empty A/B.** `calibration_by()` dropped the untagged bucket, and
  the entire pre-WP-16.B control population is untagged — so the profile A/B had
  been rendering with a single row and no comparison at all. `profile_of()`
  resolves untagged to `baseline`, and the A/B now actually appears.

Re-running the fixed tooling over the same 128 files moves the headline numbers,
because the pooled figures were flattered by the other arms:

| Metric | pooled (as published) | `market` arm (correct) |
|---|---|---|
| Calibration n (decisive) | 731 | **666** |
| BSS | −0.112 | **−0.123** |
| ECE | 0.176 | 0.172 |
| Commitment baseline n | 1413 | **1239** |
| Commitment baseline wrong-decisive | 0.276 | **0.291** |
| Commitment baseline net edge | −0.109 | **−0.128** |

Note the direction: de-pooling makes the *baseline* look worse, so the loosened
arm's apparent improvement gets **larger**, not smaller. That is the opposite of
a convenient correction, and it is why the confound guardrail matters more than
the arm filter — the number that grew is the one that is not attributable.

**Reproduce:** materialize `results/scores/` from the `output` branch
(`git archive origin/output scores | tar -x -C results`), then
`python .macro-assist/summarize_accuracy.py` (add `--arm all` to see the old
pooled view). Standardization is done within the scoped pool, so z is relative to
the arm under analysis; an earlier hand-run of this check standardized across all
arms first and reported Bull−Neut −0.266 / Bear−Bull +0.485. The shipped,
reproducible figures are **−0.233 / +0.424** — same sign, same conclusion, and
these are the ones to quote.

---

## KB-024 — Direction is not learnable from this payload by ANY model class: the numeric baseline loses to `always_bullish` and inverts the same way the LLM does (WP-21.A)

**Date:** 2026-09-04 · **Branch:** `claude/numerical-baseline-eval-4k1ouo` (harness),
run on `output` · **Harness:** `.macro-assist/numeric_baseline.py` · **Artifact:**
`numeric_baseline/numeric_baseline.{md,json}` on `origin/output`
(commit `b3e4255`, the sample-aligned re-run — supersedes the 2026-09-03 first read).

**The question under test.** Every prior measurement of the directional product
was a measurement of *the LLM* ([KB-007] 36% decisive accuracy, BSS −0.195;
[KB-011] commitment; [KB-022] inverted separation; [KB-023] the apparent repair
is confounded). None of them could distinguish "this model is bad at the task"
from "**this task is not doable from this payload**". WP-21.A asks the second
question directly, with the LLM removed: can a small, regularised numeric model
predict 5/10/20-day direction on these assets at all?

**Design.** 18-year panel (2005-01-03 → 2026-09-04, 5,655 business days), 20
features per asset (own-price + shared macro state), walk-forward expanding
window, `min_train` 756 days, refit every 21 steps, **embargo = horizon + 1**
trading days. Point-in-time discipline without ALFRED: **only never-revised
inputs are eligible** (prices + daily market-observed FRED), each shifted one
business day, enforced by a test. Two model classes — `strategy_ridge` and
`strategy_gbm` — scored by the **production** readers (`score_call`,
`_brier_and_reliability`, `bias_separation`), not bespoke ones, against
`neutral` / `random_walk` / `always_bullish`. A planted-signal positive control
proves the harness can detect an edge when one exists, so "no edge" cannot be a
dead pipeline. Pre-committed bar in `verdict()`: n ≥ 30 decisive, decisive
hit-rate > 0.52, **and** either BSS > 0 or an `aligned` separation ordering.

**Sample alignment (the WP-21.A.2 fix, and why this run supersedes the first).**
The 2026-09-03 read committed the [KB-023] error one level down: comparator
calls keyed off *price availability*, so the comparators were scored on 78,656
calls against the models' 75,414 — free extra sample for `always_bullish`, the
benchmark the entire verdict turns on. `shared_call_keys` now intersects the
(window, date, asset) triples across arms and `restrict_calls` clamps every arm
to them. **All five arms below are scored on the same 75,432 calls over the same
4,636 dates.** The fix moved the benchmark, not the conclusion:
`always_bullish` 0.560 → **0.557** (61,073 decisive, down from 64,167);
`random_walk` 0.500 → 0.498; both models unchanged to three decimals.

### Headline — no edge, on the wrong side of the trivial benchmark

| Arm | n decisive | decisive hit-rate | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|
| `ridge` | 42,043 | 0.530 | 0.271 | **−0.087** | 0.119 | inverted | **no edge** |
| `gbm` | 40,173 | 0.526 | 0.264 | **−0.059** | 0.103 | inverted | **no edge** |
| `neutral` | 0 | n/a | n/a | n/a | n/a | n/a | abstains |
| `random_walk` | 58,733 | 0.498 | 0.253 | −0.011 | 0.052 | inverted | no edge |
| `always_bullish` | 61,073 | **0.557** | **0.247** | −0.000 | **0.007** | n/a | no edge |

Both models fail the pre-committed bar on every clause, and they fail it in the
worst available way: **`always_bullish` beats them on all four metrics
simultaneously** — hit-rate (0.557 vs 0.530), Brier (0.247 vs 0.271), BSS
(−0.000 vs −0.087) and calibration error (0.007 vs 0.119). A constant that
carries no information outscores both fitted models. `ridge` does clear 0.52 on
raw hit-rate, which is exactly why the bar demands more than that: in a drifting
tape hit-rate is free, and the arm collecting it for free collects more.

### The confidence signal is anti-informative, and monotonically so

`ridge`, decisive calls binned by stated confidence:

| bin | n | mean confidence | realized hit-rate | gap |
|---|---|---|---|---|
| 50–60 | 13,825 | 0.571 | 0.519 | −0.053 |
| 60–70 | 18,242 | 0.638 | 0.536 | −0.102 |
| 70–80 | 7,146 | 0.737 | 0.554 | −0.182 |
| 80–90 | 2,009 | 0.835 | 0.509 | −0.326 |
| **90–100** | **821** | **0.943** | **0.404** | **−0.538** |

The most confident bin is the *only* one that resolves below a coin flip.
`gbm` reproduces the shape on its own scale (80–90: 0.416; 90–100: 0.200,
n=35). This is [KB-007]'s finding — confidence anti-informative — recovered
from a model that has no narrative, no prose, and no incentive to sound
decisive. **It is a property of the task, not of the writer.**

### The inversion is the same inversion, and it strengthens with horizon

`bearish_vs_bullish` — the gap the [KB-021]/[KB-022] convention says to quote,
because its interval excludes zero (block bootstrap, 221 blocks):

| Arm | window | bear−bull gap | p | 95% CI |
|---|---|---|---|---|
| `ridge` | overall | **+0.093** | 0.002 | **[+0.021, +0.165]** |
| `ridge` | t5 | +0.027 | 0.214 | [−0.045, +0.102] |
| `ridge` | t10 | +0.077 | 0.002 | [−0.008, +0.171] |
| `ridge` | t20 | **+0.158** | 0.002 | **[+0.063, +0.259]** |
| `gbm` | overall | **+0.080** | 0.002 | **[+0.012, +0.146]** |
| `gbm` | t20 | +0.098 | 0.002 | [+0.010, +0.198] |

Ordering is `inverted` for both model classes: what the model calls Bearish
subsequently outperforms what it calls Bullish, and the effect roughly
**sextuples from t5 to t20** in `ridge`. Do **not** quote
`bullish_vs_neutral` (ridge −0.040, p=0.002) as the headline — its CI
[−0.094, +0.015] spans zero, and `bias_separation`'s own docstring is explicit
that the interval, not the p-value, is what separates a real effect from an
underpowered one.

### Why it inverts — the mechanism is legible and shared by both model classes

Out-of-sample permutation drop (positive = the input was load-bearing) leaves
almost nothing standing. In `ridge` exactly one input clears zero materially:
`drawdown` (+0.003). In `gbm`: `drawdown` (+0.004), `vol_ratio` (+0.003),
`curve_chg_20` / `ma_gap_50` / `sp_ret_20` (+0.002). The one input both models
agree on is `drawdown`, and in `ridge` it carries a large negative coefficient
(−0.121, sign stability 0.806) — i.e. **stress → bearish**. Stress mean-reverts
at 10–20 days. So the models learn the only stable relationship in the panel,
that relationship is a *contrarian* one, and calling it directionally at
5–20 days is systematically backwards. That is the 90–100% bin at 0.404, and it
is why the inversion grows with horizon.

Note the honest reading of the permutation column: in `ridge` even `rv_20`
(−0.009) and `vol_ratio` (−0.005) come back **negative** — shuffling them
*helped*. Only `drawdown` survives. The 2026-09-03 first read described three
load-bearing inputs; on the aligned sample the ridge arm has one.

### The 20-day reversion errand closes negative

`ret_20` was carried specifically to test it. `ridge`: coefficient −0.014 with
**sign stability 0.778 — the lowest of all 20 inputs** — and permutation drop
−0.001. `gbm`: split importance 0.020 (bottom quartile), permutation +0.000.
The sign is nominally right and the effect is indistinguishable from noise.
20-day reversion is not a usable standalone feature in this panel.

### What this establishes, and what it does not

**Establishes.** Three independent measurements now point the same way:

| | what it measured | result |
|---|---|---|
| [KB-007] | the LLM's own calls, 441 decisive | 36% hit-rate, BSS −0.195, confidence anti-informative |
| [KB-022] | the LLM's bias label vs forward returns | separation inverted |
| **KB-024** | whether *any* small model can learn it | no — and it inverts the same way |

Two excuses are now closed. "The task was hard, so of course the model
struggled" is closed: the task was measured directly and no model class reaches
a trivial constant. "A better model would fix it" is closed: two model classes,
one linear and one non-linear, fail identically and for the same reason.

**Does not establish.** WP-21.A tested *numeric* models on the numeric panel.
An LLM can read news, narrative and positioning that a ridge regression cannot
see, so this result alone does not prove direction is unlearnable from *all*
information. What makes that objection non-load-bearing is that the LLM has
already been measured directly on exactly this task with the full payload
([KB-007], 441 decisive calls, 36%) and failed on its own terms. KB-024 does not
replace that measurement — it removes the last excuse for it.

This result also **does not** speak to the fragility / risk-flag products.
Those were scored under a different protocol and passed it ([KB-017] leave-one-
crisis-out CV, [KB-021] live parity); their honest limit is precision ≈0.32, not
absence of skill.

### Consequence

The directional product (`Bias` + `Confidence`) is cut from the daily note as of
**v1.6** — see WP-21.D in `Project_Development.md`. The conditional return
distribution that already sits underneath each call is kept and published as the
product; it is computed from data, carries its own n, and is not what failed.
**WP-21.B (day-alternating prompt A/B) is closed as superseded**: it could only
ever have ranked two prompt configurations against each other, and this result
says the target is not there to be hit.

**The way back in is left open and pre-registered.** If a bounded indicator
search (WP-21.E) finds a feature family that clears this same bar on sealed
holdout data, the column returns — with the base rate published underneath it.

**Reproduce:**

```bash
# fetch the artifact
git show origin/output:numeric_baseline/numeric_baseline.md
git show origin/output:numeric_baseline/numeric_baseline.json

# or re-run (manual Actions trigger; ~75k model calls, 3,601 refits)
gh workflow run numeric_baseline.yml     # or the Actions UI
python .macro-assist/numeric_baseline.py
```

Per-asset hit-rate/BSS lives in `scores.json.gz` on the 30-day CI artifact
(stripped before publish) — pull it before **2026-10-03** if that cut is wanted.
