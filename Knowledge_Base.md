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
