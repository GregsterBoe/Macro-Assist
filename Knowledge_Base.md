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
