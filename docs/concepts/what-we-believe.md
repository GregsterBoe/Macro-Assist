# What we believe

The standing conclusions, distilled from 26 Knowledge Base entries. Each line is
a claim the project would defend, with the evidence behind it and — where it
matters — the limit on how far it generalises.

This page is a **summary, not a source**. Where it and the
[Knowledge Base](../record/knowledge-base.md) disagree, the KB wins and this page
is the thing to fix.

---

## Established — direction

!!! danger "Direction at 5–20 days is not learnable from this payload, by any model class tested"
    **[KB-024]** · 18-year walk-forward panel, 5,655 business days, 75,432 shared
    calls. Ridge and GBM both lose to a constant `always_bullish` on hit-rate,
    Brier, BSS and calibration error simultaneously.

    **Limit:** *this payload, these six assets, these horizons.* It is not a
    claim about markets in general, and the eligible panel deliberately excludes
    all revised macro series.

**The one stable relationship in the panel is contrarian, and it is why
everything inverts.** Stress → bearish signal → stress mean-reverts at 10–20 days
→ rally. `drawdown` is the only input both model classes find load-bearing, and
it is signed this way. Bearish calls precede the *highest* forward returns
(+1.685% vs +0.951% in [KB-027]). The effect strengthens from t5 to t20. Found
independently in [KB-022], [KB-024] and [KB-027].

**Stated model confidence is anti-informative, monotonically.** Decisive calls
resolved at ~36% with BSS −0.195 in the LLM arm ([KB-007]); `ridge`'s 90–100%
confidence bin resolved at 0.404 in the numeric arm ([KB-024]). Two different
model classes, the same pathology.

**Adding a non-market consensus anchor does not help — it hurts.** The Philly Fed
SPF anchor scored worse than `always_bullish` on Brier, BSS and ECE alone; added
to the market panel it made the panel *worse* (BSS −0.087 → −0.124) while making
a third more decisive calls ([KB-026]). **Limit:** this closes the SPF anchor as
a directional input. The SPF-vs-SEP gap and the FOMC-drift layer — the actual
two-layer thesis — were excluded from the run as leakage and remain untested.

**The VIX term structure does not carry direction either.** Alone or added to the
panel, on a sealed holdout ([KB-027]). **Limit, and it matters:** [KB-001] scored
the same curve as a *stress* instrument at AUC 0.77/0.67 and that stands. The
two live fragility flags do not depend on this outcome.

## Established — fragility and tail risk

!!! success "Tail risk, unlike direction, is measurable out of sample"
    This is the project's positive result, and essentially all of its remaining
    live product.

**The fragility index leads S&P drawdowns.** Weights and thresholds calibrated on
a de-overlapped, look-ahead-safe backtest before anything trusted it
([KB-001], [KB-002]).

**The cross-section is orthogonal to the composite, and OR-ing the channels
roughly doubles crisis recall.** Composite | absorption | turbulence, each
against its own point-in-time top decile: 5-day recall 0.33 → 0.72
([KB-015], [KB-016]).

**It is a trade, not a free lunch, and the trade is worth it for a risk gauge.**
Precision falls 0.43 → 0.32. Confirmed against the real composite target
([KB-016]), survives honest cross-validation with negligible leakage
([KB-017]), and reproduces on the live daily sector-ETF feed ([KB-020]) and in
the live code path ([KB-021]).

**Adoption must be an OR mode, not a blended weight.** An equal-weight blend
degrades the validated flag ([KB-016],
[ADR-0006](../decisions/ADR-0006-or-mode-not-weight.md)).

**Absorption needs a homogeneous cross-section.** It had no skill on the ~5
heterogeneous live assets ([KB-012]) and real skill on Fama-French industries
([KB-013]) — a reversal caused entirely by the cross-section, not the measure.

**Two candidate channels were tested and rejected.** A credit/funding channel has
genuine standalone skill but is **redundant** in the OR set — zero added recall
at the live operating point, confirmed on two independent sources ([KB-019]).
Downside asymmetry does **not** sharpen the variance-trend channel ([KB-018]).

## Established — the inputs and the model layer

**The HMM regime layer has no out-of-sample skill as wired, and a four-feature
rule beats it.** Drawdown alone reaches AUC 0.697 against the HMM's 0.553, and it
was redundant with fragility ([KB-004], [KB-006]). It was retired from the note
and kept in the codebase ([ADR-0004](../decisions/ADR-0004-retire-hmm-from-the-note.md)).

**The regime bug was the inference path, not the concept.** Live labelling is
safe; validation must use walk-forward, never the persisted full-sample model,
which collapses to one label because it is startprob-dominated ([KB-003],
[KB-005]). Walk-forward and full-sample labels disagree 70.5% of the time.

**The input payload is redundancy-heavy in the market/sector block; the FRED
macro series are the orthogonal core** ([KB-009]). And **redundancy analysis and
model-attention point at different prune candidates** ([KB-010]) — so an ablation
has to be run, not inferred.

## Open — being measured now

| Question | Instrument | Earliest honest read |
|---|---|---|
| Does the conditional distribution beat not conditioning at all? | `score_distributions.py`, sealed bar, `MIN_SKILL = 0.02`, `MIN_BLOCKS = 8` | ~2027-05 |
| Does the fragility flag fire correctly on a live episode? | The shadow clock at `FRAGILITY_MODE=log` | Whenever the tape provides one |
| Is the HAR-RV vol forecast any good? | Logged daily, unpublished, unscored | WP-17.5 — not started |
| Is the LLM's Target Range calibrated? | Nothing. It is the last LLM-authored falsifiable claim in the note and it is **unscored** | Blocked on two decisions — open decision #7 |

The exploratory median-only backfill shows skill vs unconditional of −0.009 at t5
and −0.065 at t20. That is **not** a result — it was seen before the bar was
written, it is 3–4 blocks, and the code will only ever label it `exploratory`.
Nowhere near the power to claim an edge either way.

## Open — untested, and honestly so

- **The expectations-gap mechanism.** Phase 19's actual bet — economists (SPF) vs
  policymakers (SEP dots) vs what the Fed is currently saying — has never been
  tested. [KB-026] closed a *scoring convenience*, not the thesis. Testing it
  needs a scoring protocol that is not direction, and none exists.
- **Whether the paper portfolio's sizing rule has edge.** Its input was withdrawn
  by the cut before it accumulated a track record.
- **Everything downstream of an input ablation** (WP-18.4). The prune queue exists
  and is prioritised; it is gated on sample.

## Beliefs about the project itself

These are not measured, but they have been paid for.

- **A product without a trivial rival next to it will score as skilled.** Three
  independent confirmations ([KB-024], [KB-026], [KB-027]).
- **A green CI run is not a valid run.** [KB-025] — a degraded run is a valid run
  as far as the runner is concerned, and it will be silent.
- **A bar is not tested by the results that fail it.** [KB-027] — the hole in
  `verdict()` was unreachable until an arm finally cleared BSS 0.
- **The measurement apparatus must be re-pointed when the product changes.**
  Phase 22 exists because it was not, for three days.

---

**Where to go next:** the live board is
[Active experiments](../record/active-experiments.md); the reasoning behind the
current shape of the system is [Decisions](../decisions/index.md).
