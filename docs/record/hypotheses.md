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
| [H-001](#h-001) | `closed` | The SPF anchor's confidence bins are the first correctly ordered ones ever measured here — *confound resolved 2026-09-14: the ordering is carried by two crisis-rebound periods and inverts within three of six assets; closed on its own target-space rule, no KB entry* |
| [H-002](#h-002) | `draft` | The stress-reversion mechanism is conditional on fragility state: stress continues in Elevated tapes, reverts in Normal ones — *explore look 2026-09-14: width half seen, location half not* |
| [H-003](#h-003) | `draft` | The SPF-vs-SEP gap predicts the *width* of the realized rate path, not its direction |
| [H-004](#h-004) | `draft` | The published conditioner's dimensions are not the ones that move the distribution; a fragility-state conditioner beats the macro bucket — *explore look 2026-09-14: structure check failed in direction* |
| [H-005](#h-005) | `seen` | On the explore slice the published macro bucket is reliably *worse* than not conditioning, and the deficit grows with horizon |
| [H-006](#h-006) | `seen` | The only conditioner that beats `unconditional` on the explore slice is the S&P's own drawdown bin — and its gain is a narrower interval in calm, not the reversion — *rival look 2026-09-14: the width claim holds; the product's `har_gaussian` does not carry it, the same σ on the empirical shape does* |
| [H-007](#h-007) | `seen` | The product's `har_gaussian` comparator is handicapped by its shape and its zero mean, not its σ: too wide in calm (coverage 0.57 at nominal 0.50), skewed PIT, −0.044 on the S&P at 20d, while the same forecast on the empirical shape is +0.016 … +0.026 |

---

## H-001 — The SPF anchor's confidence is ordered correctly, and nothing else's is {: #h-001 }

**Status:** `closed` · seen 2026-09-07 · confound resolved 2026-09-14 (the artifact was pulled to `results/numeric_baseline/runs/2026-09-07-wp19e-spf/scores.json.gz` on 2026-09-13, before its 2026-10-07 expiry). No KB entry — the entry's own rule below: the outcome is a note here, and the only thing the observation could become is a better-calibrated directional call, which [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md) closes. Pointer: [KB-026].

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

**Confound resolved (ledger).** *2026-09-14, draft by the assistant.* The
per-call record (`exogenous_spf`, 4,637 reports 2008-11-21 → 2026-08-31,
41,050 decisive calls) read with the production reader
(`summarize_accuracy._brier_and_reliability`), split the way the confound
asked for. **The ordering does not survive.**

- *Where the top bin lives.* Calls at 90–100 confidence occur only in
  2008–2011 and 2020; the arm's maximum confidence on 2012–2019 is 88 and on
  2021+ is 85. The 90–100 bin is 629 decisive calls, 270 of them 2020-05-18 →
  2020-08-14 — the post-crash rebound — and the rest the 2008–2011 recovery.
  Its composition is S&P Bullish (192), DXY Bearish (136), WTI Bullish (116),
  10Y Bullish (95), Bitcoin Bullish (84): directional calls on a tape that then
  went one way.
- *Within assets.* S&P 0.650 → 0.626 → 0.670 → 0.710 → **0.892** (n=186, 176
  of them Bullish, base rate 0.655); WTI 0.503 → … → 0.684; DXY … → 0.866
  (n=119, 113 Bearish, 2020). **Gold 0.741 → 0.167** (n=6), **10Y 0.444 →
  0.224** (n=67), **Bitcoin 0.649 → 0.442** (n=77). Three of six invert in the
  top bin; the three that hold are the post-crisis up-rate.
- *The calm middle.* On 2012–2019 every asset is flat-to-inverted:
  S&P 0.712 → 0.629, Gold 0.506 → 0.361, WTI 0.517 → 0.267, 10Y 0.525 → 0.000
  (n=7); DXY and Bitcoin never reach 80. Excluding 2020 alone leaves the
  pooled top bin at 0.749 — so it is not one episode but the class of episode:
  the anchor is far from consensus exactly when the tape has just crashed, and
  its high-confidence call is "back toward consensus", which is the reversion
  [KB-022] already measured.

So the mechanism the entry conjectured — confidence as distance-from-consensus,
a real quantity — reduces to *distance-from-consensus is large after a crash
and crashes revert*: a period-and-direction effect with zero discrimination
inside a regime, which is the confound as written. The gap/width lead
(→ H-003) is untouched by this; nothing here bears on whether the SPF–SEP gap
predicts width. **Closed, on the target-space check's own terms.** Reproduce:
`python -c` over `scores.json.gz` with `_brier_and_reliability` per asset, per
`report_date[:4]`; no harness change was needed.

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

**Explore-tier looks (ledger).** *2026-09-14* — `explore_conditioner.py`, one
run, one configuration fixed before looking (`DD_EDGES = (−5%, −10%)` from the
S&P's 252-day high, `MIN_N = 10`, `BURN_IN = 252`), report dates 2010-06-25 →
2017-12-29 (1,893, all < `SEAL_START`), realized S&P forward change by drawdown
bin × OR state, 6 cells × 3 horizons; the dose-response rival (drawdown bin
alone) beside it. Report: `results/explore_conditioner/report.md` (§ *H-002
structure check*).

- **The width half is seen.** Elevated is wider than Normal in 8 of 9
  bin × horizon cells; the exception is the calm bin at 5d (1.59 vs 1.61). In
  both stressed bins it holds at every horizon — 3.71 vs 2.91 and 5.31 vs 3.24
  at 5d; 8.41 vs 4.22 and 7.59 vs 4.21 at 20d.
- **The confound is not what explains it.** −5..−10% ∧ Elevated is wider than
  <−10% ∧ Normal at every horizon (3.71 vs 3.24 · 6.09 vs 3.96 · 8.41 vs 4.21):
  a deeper drawdown alone does not reproduce the split. On n = 70 and 96 days —
  two or three episodes each.
- **The location half is not seen.** Within each stressed bin the Elevated
  median sits *left* of the Normal one (6 of 6, one tie), but it is still
  *right* of the unconditional median in 5 of 6 cells (the exception, −5..−10% ∧
  Elevated at 5d, is +0.30 vs +0.37). Stress in an Elevated tape shows **less
  reversion and far more dispersion**, not continuation.
- **As a scored conditioner** (`dd_x_frag`) it does not beat the drawdown bin
  alone: +0.009 [−0.001, +0.020] on the original three at 5d, negative at 20d.
  The cells are too thin to pay for their own quantile noise.

What it changes for this entry: the prediction "medians on opposite sides"
is wrong as written. If the owner rewrites it, the width clause stands and
the location clause needs a different prediction, or none.

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

**Explore-tier looks (ledger).** *2026-09-14* — same run as H-002's. Arm
`frag_or`: the live OR flag's state (PIT top-decile per channel, 252-reading
warm-up, daily) as the only bucket dimension, per asset, collapse to
`unconditional` below `MIN_N`. Variants looked at and reported: `frag_comp` (the
composite channel alone) and `frag_or_x_nfci` (OR state × NFCI tertile).
Report: `results/explore_conditioner/report.md` (tables 1–2, § *H-004 structure
check*).

- **Skill vs `unconditional` is zero.** Pooled over SP500/Gold/WTI: +0.001 /
  −0.002 / −0.005 at 5 / 10 / 20d, every interval spanning zero. Over all six:
  −0.003 / −0.007 / −0.015.
- **The structure check failed in the predicted direction.** The gain was to
  sit in Elevated and be ~0 in Normal. Measured by the state the report date
  was in: **Elevated −0.027 [−0.046, −0.013] at 5d, −0.046 [−0.101, −0.008] at
  10d**; Normal +0.003 / +0.002. The arm loses exactly where the mechanism said
  it would win.
- **Why, legibly.** Elevated is 15% of report dates (287 of 1,893). Its quoted
  interval is wide (P25–P75 3.16 vs 1.79 at 5d) and its median is
  *right*-shifted (+0.71 vs +0.31): the flag fires mid-selloff and reversion
  follows. The pinball cost of the wide interval on the days that revert
  exceeds its gain on the days that continue — the distribution-side face of
  [KB-031]'s precision ≈ 0.33.
- `frag_comp` has the same shape, slightly less negative. `frag_or_x_nfci` is
  reliably worse than `unconditional` at every horizon (−0.013 → −0.070 over
  all six): the interaction thins the cells.

What it changes for this entry: as written (state × asset, no macro) the
mechanism does not show on the explore slice. Not closed — it has never been
read against a bar — but the honest prior dropped, and the reason is the same
one that makes the flag a good *state* detector and a poor *location* claim.

---

## H-005 — On the explore slice the published macro bucket is reliably worse than not conditioning, and the deficit grows with horizon {: #h-005 }

**Status:** `seen` · 2026-09-14 · draft text by the assistant — the owner's
rewrite is required before this can be promoted (§6)

**What was seen.** Walking the v2.1 conditioner forward on the explore slice —
the published bucket (NFCI tertile × curve sign × BAA10Y tertile), known-by-*t*
history from 2000-08, `MIN_N = 10` with the product's collapse ladder — and
scoring it exactly as Phase 22 scores, against `unconditional` on the same
observations:

| pooled skill vs `unconditional` | 5d | 10d | 20d |
|---|---|---|---|
| SP500 / Gold / WTI | −0.004 [−0.011, +0.003] | **−0.019 [−0.030, −0.008]** | **−0.029 [−0.051, −0.010]** |
| all six | **−0.009 [−0.017, −0.001]** | **−0.028 [−0.041, −0.015]** | **−0.053 [−0.081, −0.031]** |

At 20d every asset is negative; the 10Y −0.058 [−0.086, −0.032], DXY −0.076
[−0.118, −0.035], WTI −0.039 [−0.065, −0.014]. In the sealed vocabulary the
10d and 20d rows would read `inverted`; here `verdict(sealed=False)` returns
`exploratory`, which is what they are. Coverage of the quoted P25–P75 is 0.556
at 5d — wider than nominal on this tape. The deficit lives at the *full* 3D
level, which quoted on all 1,893 report dates; it is not collapse noise.
Per year on the S&P at 10d it is negative in five of eight years and positive
only in 2013, 2014 and 2017 — the three calmest years of the slice (0%, 4%
and 0% of days more than 5% off the high).

**Where.** `results/explore_conditioner/report.md`, tables 1–2 and § *Where
`macro`'s deficit lives* · reproduce with
`python explore_conditioner.py --cached` · inputs fetched 2026-09-14.
Multiplicity: this arm was one of seven in a single run, all reported.

**Mechanism it would imply.** The three dimensions are slow — they move over
quarters — and the history behind the table holds about three macro regimes.
A full bucket's known sample is dominated by the last episode that carried its
label (2001–02 or 2008–09 for the wide-credit and high-NFCI buckets), so the
table is a *regime-memory* conditioner with N ≈ 3, not N = 6,811, and a
distribution that remembers a crisis is penalised at every horizon on a tape
without one — most at 20 days, where the remembered dispersion is largest.

**The prediction that is not the score.** If this is regime memory, the
deficit is concentrated in buckets whose known history is dominated by one
episode and near zero in buckets populated across regimes
(`NFCI:mid|YC:positive|CREDIT:tight` and its neighbours). Not yet cut — one
more look, to be counted when taken.

**The confound.** The explore slice is *one* tape: 2010–2017, one bull market,
no crisis. A conditioner that remembers crises loses on it by construction and
may well win on 2018–2022, which holds five regimes — and which is the sealed
slice, the one thing not to look at. Also: this is the v2.1 table walked
forward, not the note's live record (the note used other tables until
2026-09-13, [KB-028]); it says nothing about what the note published.

**What would test it.** Nothing new — **Phase 22 is the test**, live and sealed
from 2026-09-07, first read ~2027-05. The only earlier read is the same
walk-forward on the 2018+ historical slice under the WP-23.B class bar, which
`resolved.md` #19 now permits (the seal is reused) and which burns that slice
for the conditioner class. Nothing changes before Phase 22 reads — decided,
`resolved.md` #21 (2026-09-14).

**Target-space check.** A conditional distribution against `unconditional`.
Passes.

**Read first.** [KB-028] (what the table is built on) ·
[ADR-0016](../decisions/ADR-0016-phase-22-scores-the-distribution-only.md) ·
`conditional.assign_bucket` and `lookup_distribution` · the report's metadata
line, before any number ([KB-025]).

---

## H-006 — The only conditioner that beats `unconditional` on the explore slice is the S&P's own drawdown bin, and its gain is a narrower interval in calm {: #h-006 }

**Status:** `seen` · 2026-09-14 · draft text by the assistant — the owner's
rewrite is required before this can be promoted (§6)

**What was seen.** Of seven arms, one has positive pooled skill with an
interval clear of zero: `dd_bin`, the S&P's drawdown from its 252-day high in
three bins (> −5% · −5..−10% · < −10%), applied to every asset. Pooled over
SP500/Gold/WTI **+0.009 [+0.003, +0.015]** at 5d and **+0.009 [+0.002,
+0.017]** at 10d; on the S&P itself **+0.023 [+0.011, +0.036]** at 5d and
**+0.027 [+0.009, +0.047]** at 10d — over `MIN_SKILL` with a zero-excluding
interval, *on the explore slice, which is not a pass*. It beats `trailing_250`
on the S&P (+0.011 [−0.004, +0.027] at 5d).

Where the gain lives, by the bin the report date was in: **the calm bin**
(> −5%, 1,536 of 1,893 dates) — pooled +0.007 [+0.004, +0.011] at 5d, S&P
+0.027. In the two stressed bins pooled skill is ~0 or negative with intervals
straddling zero. Per year the S&P skill is positive in seven of eight,
*including 2013 and 2017, which had no day more than 5% off the high, and
2014, which had ten* — years in which the arm all but only quoted its calm bin.

**Where.** `results/explore_conditioner/report.md`, tables 1–2, § *Where
`dd_bin`'s gain lives*, § *per year* · same run and multiplicity as H-005.

**Mechanism it would imply.** Own-price state is a vol-state proxy. The calm
bin's known sample (every day since 2000 with the S&P within 5% of its high)
has a P25–P75 width of ~1.75 at 5d (2000-08 → 2017); `unconditional` over
the same history carries 2001–02 and 2008 in its quantiles and is 2.34 wide.
Quoting the narrower interval when the tape is calm is what pays. The reversion median shift [KB-024] describes is *visible* in the
realized table (after a ≥10% drawdown the 5d median is +1.63% vs +0.29%
unconditional) but does **not** turn into pinball skill in the stressed bins
(130 dates ≈ three episodes).

**The prediction that is not the score.** If it is a width effect, a rival that
knows only realized vol should capture most of it: `har_gaussian` (the
product's HAR-RV arm, [KB-033]) walked forward on the same dates. If `dd_bin`
still clears HAR, the own-price state carries something vol does not; if not,
this entry is [KB-033] restated and closes.

**The confound.** Three. (a) 81% of the explore slice is the calm bin — a
calm-tape effect measured on a calm tape. (b) For the stressed half, [KB-022]'s
bull-market confound exactly: every 2010–2017 dip was bought; the sealed slice
holds 2022, where drawdowns continued. (c) The rival was `unconditional`, not
the product's vol-state arms — HAR was not in this run.

**What would test it.** Add a walk-forward `har_gaussian` arm to
`explore_conditioner.py` (from `har_backtest`) and re-read the explore slice
with HAR as the benchmark — still explore tier, one more counted look. A
confirm read waits on the WP-23.B class bar (the seal is decided,
`resolved.md` #19) with the benchmark set to the best existing vol-state arm
— which, after the rival look, is `har_scaled`.

**Target-space check.** A distribution, and the claim is its *width*. The
location half — a right-shifted median after a drawdown — is [KB-024]'s
mechanism wearing a distribution, and it is on the wrong side of
[ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md). Admissible
as a width claim only; a directional read is not taken even if it appears.

**Read first.** [KB-033] (HAR-RV, and why a gaussian from a vol forecast is the
width rival) · [KB-024] and [KB-022] · `numeric_baseline.asset_features`
(`drawdown`, `DRAWDOWN_WINDOW`) · the report.

**Explore-tier looks (ledger).** *2026-09-14, later the same day* — the rival
named above, run as the second look of `explore_conditioner.py`. Two arms
fixed before looking, both **optional** in the scorer's sense (quoted where the
product would quote a forecast, scored on their own subsample, never a reason
to drop an observation): `har_gaussian`, the product's comparator exactly —
zero-mean Normal on the HAR-RV σ fitted walk-forward on the last 1,250 closes
at or before the report date, `har_forecast_or_none`'s gates, for the four
assets the product logs (`_VOL_LOG_KEYS`) — and `har_scaled`, the same σ
applied to `unconditional`'s empirical quantiles as a width ratio about their
median (the width-vs-shape decomposition, so the prediction could fail for
the Gaussian's reasons and still be tested). Same 1,893 report dates; the
S&P, Gold and WTI carry a forecast on all of them, Bitcoin on the last ~130.
Report: § *H-006 rival check*, § *Mean quoted P25–P75 width by drawdown bin*.

- **The prediction as written fails.** `har_gaussian` does not capture the
  gain: `dd_bin` vs `har_gaussian` on the S&P is **+0.020 [+0.003, +0.038]** at
  5d, +0.041 [+0.011, +0.070] at 10d, +0.071 [+0.025, +0.116] at 20d.
  `har_gaussian` itself vs `unconditional` on the S&P is +0.003, −0.014,
  **−0.044 [−0.074, −0.015]** — it *loses* to no conditioning at 20d.
- **The width claim holds.** The same σ on the empirical shape matches the
  drawdown bin on the S&P at every horizon — `dd_bin` vs `har_scaled` −0.003
  [−0.014, +0.008] · +0.007 [−0.010, +0.024] · +0.015 [−0.013, +0.044] — and
  beats it pooled over the original three at 5d (−0.006 [−0.011, −0.001]).
  `har_scaled` vs `unconditional`: S&P +0.026 [+0.018, +0.036] · +0.020
  [+0.010, +0.032] · +0.016 [+0.002, +0.031]; pooled +0.015 [+0.011, +0.019] at
  5d, +0.010, +0.006. It also pays on WTI (+0.015 at 5d), where the S&P's
  drawdown bin cannot (+0.005).
- **Why the Gaussian fails is legible in the width table.** In the calm bin
  (1,536 dates) the realized 5d IQR is 1.57; `dd_bin` quotes 1.93,
  `har_scaled` 1.85, `har_gaussian` **2.44** — a Normal with the HAR variance
  is too wide for a fat-tailed return (its IQR/σ is 1.35; the S&P's is less),
  and it over-covers: 0.574 / 0.568 / 0.540 at nominal 0.50 across horizons,
  against `har_scaled`'s 0.500 / 0.512 / 0.487. In the deep-stress bin (130
  dates) the picture inverts — the Gaussian's 5.20 is the closest to the
  realized 5.03 — but 81% of the tape is the calm bin.
- **`trailing_250` is the worse "recent regime" rival**: vs `har_scaled`
  −0.016 [−0.029, −0.003] on the S&P at 5d.
- **What it means for this entry.** The width half is a vol-forecast effect
  and a vol forecast delivers it; the own-price state carries nothing the
  forecast does not, on this tape. That is the "closes as [KB-033] restated"
  branch, with one correction to how it was going to close: the rival that
  restates it is not the arm the product has. That is [H-007](#h-007).
  Confounds (a) and (b) stand unchanged; (c) is resolved. Two counted looks.

---

## H-007 — The product's `har_gaussian` comparator is handicapped by its shape and its zero mean, not its σ {: #h-007 }

**Status:** `seen` · 2026-09-14 · draft text by the assistant — the owner's
rewrite is required before this can be promoted (§6)

**What was seen.** Walked forward on the explore slice (1,893 report dates,
2010-06-25 → 2017-12-29) with the product's own fit — 1,250 closes, the
`HAR_MIN_RETURNS` gate, the four logged assets — the zero-mean Normal on the
HAR-RV σ scores **+0.003 / −0.014 / −0.044 [−0.074, −0.015]** against
`unconditional` on the S&P at 5 / 10 / 20d and over-covers its P25–P75 at
every horizon (0.574 / 0.568 / 0.540 against a nominal 0.50). The same σ
applied to the empirical unconditional quantiles as a width ratio about their
median (`har_scaled`) scores **+0.026 [+0.018, +0.036] / +0.020 / +0.016** with
coverage at nominal. Pooled over SP500/Gold/WTI: `har_gaussian` +0.009
[−0.000, +0.016] · +0.002 · −0.005; `har_scaled` +0.015 [+0.011, +0.019] ·
+0.010 [+0.004, +0.016] · +0.006 [−0.001, +0.013]. Gold is flat under both
(≤ ±0.004); WTI gains under both (+0.019 / +0.015 at 5d).

**Where.** `results/explore_conditioner/report.md`, tables 1–2 (the `har_*`
rows), § *H-006 rival check*, § *Mean quoted P25–P75 width by drawdown bin* ·
second look of 2026-09-14, ledgered under [H-006](#h-006).

**Mechanism it would imply.** The forecast is fine; the distribution wrapped
around it is not, in two ways. *Shape:* a Normal carries IQR = 1.35 σ; a
fat-tailed 5-day return with the same variance has a narrower IQR and heavier
tails, so the Gaussian quotes an interval that is too wide in calm (2.44
against a realized 1.57 at 5d) and pays pinball on it on the 81% of dates that
are calm. *Location:* its median is zero by construction while the S&P's
forward change has a positive drift median, so realizations land above its
P50 too often. In deep stress it is the closest arm to the realized width —
which is where a Normal's IQR/σ and the return's happen to agree — but that
is 130 dates. Scaling the *empirical* quantiles keeps the fat-tail shape and
the drift median and applies the σ only to the width, which is the one thing
the forecast knows.

**The prediction that is not the score.** Two cuts. (1) If it is shape and
location, `har_gaussian`'s 4-bin PIT is both hump-shaped and skewed, and
`har_scaled`'s is flat. *Cut, same run:* `har_gaussian` 0.19 / 0.26 / 0.32 /
0.23 at 5d (0.19 / 0.25 / 0.32 / 0.24 at 10d; 0.19 / 0.24 / 0.30 / 0.27 at
20d) — the two middle bins hold 0.57 / 0.57 / 0.54 against 0.50, and the
below-P25 bin is 0.19 at every horizon while the P50–P75 bin is 0.30–0.32:
the hump and the skew both. `har_scaled` is flat within ±0.017 at every
horizon. (2) The Gaussian's deficit vs `har_scaled` should be largest in the
calm bin and shrink toward zero in the deep-stress bin. *Not cut* — the
per-bin pairing is one `skill_by_state` call on the cached observations.

**The confound.** (a) One calm tape — the calm-bin share is 81%, and the
Gaussian's over-width is a calm-bin cost; a slice with more stress narrows
the gap. (b) `har_scaled` was designed in this session as the decomposition
arm, not pre-registered in an earlier entry — it is a second look, counted,
and its form (ratio about the median, σ over the full-history sd) is one of
several one could have chosen. (c) The sealed scorer's `har_gaussian` reads a
*logged* σ from the note's own fit (5y fetch since 2026-09-14); this walk
replicates that fit on yfinance history and is not the logged number.

**What would test it.** As a hypothesis about the comparator it needs no
sealed read of the product; it needs the two cuts above. The decision it
raised — whether the Phase 22 scorer gains `har_scaled` as a *further*
optional comparator before the first read — was taken 2026-09-14
(`resolved.md` #22): **no**. A better rival makes the published table's job
harder, not easier (the WP-22.C amendment's own words), so adding one was
admissible under the seal; it was declined because it would be a bar change
made after seeing the rival's number, and `har_scaled` goes into WP-23.B's
class bar instead. Replacing `har_gaussian` was never an option, because the
roadmap's exploratory observation was scored against it.

**Target-space check.** A distribution's width and shape; no location claim.
`har_scaled` inherits the empirical median rather than predicting one.
Admissible.

**Read first.** [KB-033] · the WP-22.C amendment in `roadmap.md` (*The
`har_gaussian` comparator's σ changed once*) and its "one exploratory
observation" paragraph, which this entry does not overturn (that was a
median-only read against the old σ; this is all three quantiles against the
new fit) · `score_distributions._gaussian_quantiles` · the report.

---

## Closed

*None yet.*
