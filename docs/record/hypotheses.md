# Hypothesis register

**Conjectures, not findings.** The place for things *seen* while doing something
else and things *proposed* but not yet looked at. The rules for what goes here
and how it leaves are in [How we explore](../concepts/how-we-explore.md); read
that first.

This is not `todo.md` (decisions and carried findings) and not the Knowledge Base
(measured results). An entry here has never been read against a bar. When it
is, it leaves: `closed → KB-###`.

**Status:** `draft` — written but not yet in the owner's own words; **not a
hypothesis** · `seen` — observed in data, unplanned · `proposed` — a question,
not yet looked at · `promoted` — bar written, confirm run scheduled ·
`closed` — result in the KB, pointer kept here.

**The format is fixed.** What was seen → where → the mechanism it would imply →
the confound → what would test it → target-space check → read first. An entry
missing a confound is not finished.

| # | Status | One line |
|---|---|---|
| [H-001](#h-001) | `seen` | The SPF anchor's confidence bins are the first correctly ordered ones ever measured here — artifact expires 2026-10-07 |
| [H-002](#h-002) | `draft` | The stress-reversion mechanism is conditional on fragility state: stress continues in Elevated tapes, reverts in Normal ones |
| [H-003](#h-003) | `draft` | The SPF-vs-SEP gap predicts the *width* of the realized rate path, not its direction |
| [H-004](#h-004) | `draft` | The published conditioner's dimensions are not the ones that move the distribution; a fragility-state conditioner beats the macro bucket |

---

## H-001 — The SPF anchor's confidence is ordered correctly, and nothing else's is {: #h-001 }

**Status:** `seen` · 2026-09-07 · **deadline 2026-10-07** (artifact expiry)

**What was seen.** In the WP-19.E run, `exogenous_spf` is the first arm measured
in this project whose reliability bins increase monotonically — 0.544 → 0.549 →
0.591 → 0.675 → **0.696** in the 90–100 bin, against `ridge`'s collapse to 0.404
in the same bin ([KB-007], [KB-024]). The arm still fails its bar: it is badly
overconfident (top bin says 0.947) and BSS stays negative because the
reliability penalty exceeds the resolution gain.

**Where.** [KB-026], section *"One unpre-registered observation"*. Run
`origin/output` `2780cb4`, Actions `34104184917`. Per-asset breakdown in
`scores.json.gz` on CI artifact `10013945071`.

**Mechanism it would imply.** A quarterly, slow-moving consensus anchor produces
*fewer* decisive calls, and the ones it does make are on the subset of dates
where its inputs are far from their base rate — i.e. its confidence is a
distance-from-consensus measure, which is a real quantity, unlike the model
arms' confidence, which is a fit artefact.

**The confound.** High-confidence calls may concentrate on assets or periods with
a higher up-rate. That alone produces an ordered reliability table with zero
discrimination. [KB-023] is the standing lesson about reading a pattern found
after the fact.

**What would test it.** Pull the artifact before it expires; the per-asset
breakdown either shows the ordering *within* each asset (survives the confound)
or shows it is carried by one asset's bull run (does not). This is a
**resolution of the confound, not a confirm run** — it does not need a sealed
slice, and its outcome is a note on this entry, not a KB entry, unless the
ordering survives, in which case the question becomes H-00x: *is
distance-from-consensus a width predictor* (→ H-003's territory).

**Target-space check.** The observation is about a directional arm's
*calibration*, which is on the wrong side of [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md). It is admissible here
only as a lead toward a gap/width question. If the only thing it can become is
"a better-calibrated directional call", close it.

**Read first.** [KB-026] in full · [KB-007] for what a mis-ordered table looks
like · `numeric_baseline._brier_and_reliability` for how bins are built.

---

## H-002 — The stress-reversion mechanism is conditional on fragility state {: #h-002 }

**Status:** `draft` — needs the owner's rewrite before it is a hypothesis

**What was seen.** The one stable relationship in the 18-year panel is
contrarian: `drawdown` is the only input both model classes find load-bearing,
signed *stress → bearish*, and stress mean-reverts at 10–20 days, so bearish
calls precede the *highest* forward returns — +1.685% vs +0.951% in [KB-027]; at
t5 the bear−bull gap is +0.294, p = 0.002, CI [+0.060, +0.629]. Found
independently in [KB-022], [KB-024], [KB-027]. It is filed as *why direction
inverts*. It has never been asked as a question about markets.

**Where.** [KB-024] *"Why it inverts"* · [KB-027] *"The mechanism, and it is
KB-024's"* · [KB-022] the original bull-market confound.

**Mechanism it would imply.** Stress reverts *on average* because most stress
episodes are not crises. The ones that are not reverting are the ones the
fragility monitor exists to catch. So the conditional forward distribution
after a stress reading should be **bimodal across fragility state**: in a
Normal tape, stress → reversion (right-shifted median, ordinary width); in an
Elevated tape, stress → continuation (left-shifted median, much wider). If
true, the two halves of the repository — the mechanism that killed the
directional product and the flag that survived — are the same phenomenon seen
from two sides.

**The prediction that is not the score.** The width (P75−P25) of the forward
distribution conditional on `stress ∧ Elevated` exceeds that of
`stress ∧ Normal` at every horizon, *and* the medians are on opposite sides of
the unconditional median. Both must hold; a width difference alone is
[KB-016]'s precision trade restated.

**The confound.** The fragility flag and `drawdown` are computed from
overlapping inputs (the composite's variance-trend and term-structure legs are
stress measures). "Elevated" may simply be "more stressed", in which case this
is a monotone dose-response of the same variable, not a state switch. The test
must show the split is not reproduced by a deeper drawdown bin alone.

**What would test it.** A **shadow conditioner** — never touching the published
table — built with `conditional.build_distribution_table_for_backtest` on the
explore slice, with fragility state as a bucket dimension (the PIT flag from
`fragility_or._pit_backtest`, ETF panel from 2007, so the explore surface is
~2009–2017). Scored the way Phase 22 scores: pinball loss vs `unconditional`,
block-bootstrap on 21-day blocks, disqualifiers first. The confirm bar for this
class (a shadow conditioner vs `unconditional`) is to be written **before** this
entry is promoted — see [How we explore §5](../concepts/how-we-explore.md#5-the-bar-precedes-the-candidate).
Which seal governs — `SEAL_START` 2018-01-01, or a new one — is a decision to
record in `todo.md` first.

**Target-space check.** Output is a conditional *distribution*, scored by the
existing distribution scorer. Not a sign. Passes.

**Read first.** [KB-024] end to end · [KB-016]/[KB-017] for what the flag's
operating point means · `conditional.py` (`assign_bucket`,
`build_distribution_table_for_backtest`) · `fragility_or.py` (`_pit_backtest`,
`_MIN_WARMUP`) · `score_distributions.py` (`skill_vs`, `block_bootstrap`,
`verdict`).

---

## H-003 — The SPF-vs-SEP gap predicts the width of the realized rate path {: #h-003 }

**Status:** `draft` — needs the owner's rewrite before it is a hypothesis

**What was seen.** Nothing yet. This is Phase 19's actual thesis, which
[KB-026] did *not* test: the SPF-vs-SEP gap and the FOMC-drift layer were
excluded from the run as leakage, and the deterministic SPF anchor alone was
scored — for direction, which was a convenience, not the thesis (DESIGN §1).
The board's own words: *"both layers of the actual bet remain untested"*, and
*"it needs a scoring protocol that is not direction, and none exists yet"*.

**Where.** [KB-026] *"Honest scope of a null"* · `roadmap.md` Phase 19 ·
`.macro-assist/exogenous/DESIGN.md` §1, §6.1 ·
[ADR-0018](../decisions/ADR-0018-market-data-barred-from-the-exogenous-branch.md).

**Mechanism it would imply.** When economists (SPF) and policymakers (SEP dots)
disagree about the policy path, the realized path over the following quarters
is *more dispersed* — not because either side is right, but because
disagreement between the two best-informed non-market forecasters is itself a
measure of how underdetermined the path is. The gap predicts **width**, and
width is a distribution property with a scorer.

**The prediction that is not the score.** The gap should be *uninformative
about direction* — the [KB-026] result, which already holds for the SPF half —
while being informative about the absolute size of the subsequent 2Y / 10Y
change. A gap that predicts sign is a different (and closed) claim.

**The confound.** Both forecasts, and the realized dispersion, respond to the
same visible regime (a hiking cycle is both high-disagreement and high-vol). The
test must beat a trivial rival that knows only trailing realized vol —
`trailing_250` is already an arm in `score_distributions.py`.

**What would test it.** The data problem first: FRED serves only the *current*
vintage of `FEDTARMD`, so a walk-forward off FRED reads the Fed's later
revisions ([KB-026]). Point-in-time SEP requires the dated projection materials
themselves (quarterly since 2012; each release is its own vintage). That is a
data-collection errand with a known shape, and its output is small — ~55
quarterly observations — so power is low and the honest read may be "cannot
tell". Then: a width forecast (e.g. a quantile pair on the next-quarter 2Y
change) as a function of the gap, scored by pinball loss against
`trailing_250` and `unconditional`, quarterly blocks.

**Target-space check.** Output is a *gap → width* mapping, scored as a
distribution. Not a sign. Passes — with the explicit rule that a directional
read of the gap is not taken even if it appears.

**Read first.** `exogenous/DESIGN.md` §1 and §6 · `exogenous/sep.py`
(`consensus_gap`, `SEP_SERIES`) · `exogenous/spf.py` (`load_spf_snapshot`) ·
[KB-026] *"What each SPF input was worth"* for `spf_curve`'s instability.

---

## H-004 — A fragility-state conditioner beats the macro bucket {: #h-004 }

**Status:** `draft` — needs the owner's rewrite before it is a hypothesis.
Related to H-002 but a narrower and cheaper question; either can be run first.

**What was seen.** [KB-028]: the published conditional table was, until
2026-09-14, effectively conditional on NFCI alone — the live bucket had the same
`n` as its grandparent, and two of the three dimensions (curve sign, HY tertile)
contributed nothing to the published numbers. The rebuild (24 buckets on
BAA10Y from 2000-08) fixed the *data*, but nobody has asked whether the three
dimensions are the *right* ones. The exploratory median-only backfill shows
skill vs `unconditional` of −0.009 at t5 and −0.065 at t20 — not a result, but
not encouraging.

**Where.** [KB-028] · WP-22.C exploratory block · `conditional.assign_bucket`.

**Mechanism it would imply.** The macro bucket conditions on *slow* variables
(financial conditions, curve, credit) that change over quarters. Forward
5–20-day return distributions are shaped by *fast* state — whether the tape is
fragile now — and the project's one validated out-of-sample instrument measures
exactly that ([KB-017], [KB-021]). A conditioner built from the thing with
skill should beat one built from things that were chosen because they were
available.

**The prediction that is not the score.** The fragility-state conditioner's
gain over `unconditional` should come from its **Elevated** bucket (wider, left
shifted) and be ~zero in Normal. If the gain is spread evenly across states it
is not this mechanism.

**The confound.** Sample. Elevated is by construction the top decile, so the
Elevated bucket has a tenth of the observations and its quantiles are noisy.
`MIN_POOL_BLOCKS` and the underpowered disqualifier must be evaluated first, as
Phase 22 does.

**What would test it.** Same shadow-conditioner harness as H-002, simpler
bucket (fragility state × asset, no macro dimensions), same scorer, same class
bar. If H-002 is run, this is a sub-table of it.

**Target-space check.** A conditional distribution. Passes.

**Read first.** [KB-028] · [ADR-0016](../decisions/ADR-0016-phase-22-scores-the-distribution-only.md) ·
`score_distributions.verdict` and the tests that drive each disqualifier.

---

## Closed

*None yet.*
