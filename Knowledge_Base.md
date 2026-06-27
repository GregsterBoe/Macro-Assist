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
