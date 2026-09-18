# TODO — open decisions & carried-forward findings

**The single inbox.** Anything here is **known and deliberately not done yet** —
either because it needs a design call rather than a bug fix, or because it was
out of scope for the change that found it. If an open item exists anywhere in
this repo, it should be listed or linked here.

Conventions:
- **Open decision** = needs a human call; do not "fix" it silently.
- **Carried finding** = agreed problem, just not scheduled yet.
- Cite the file/line and the source (design doc, run, KB entry) so the next
  context can pick it up without re-deriving the analysis.
- **When an item resolves, move it to [`resolved.md`](resolved.md)** with its
  reasoning intact, and pull any "carry forward" caveat back up into this file
  as its own entry. A resolved item left here is noise; a lost caveat is worse.

Last reviewed: 2026-09-14 — #23 and #24 (the Phase 24 convention calls) opened
from the draft and closed the same day → `resolved.md` (#23 a contradiction is
red with a pin, ages report-only; #24 the revisit section is enforced, not
introduced — 18 of 21 ADRs already had it). Earlier the same day, the closing pass (nine items → `resolved.md`: #19 seal
reused, #21 nothing before Phase 22, #22 no scorer change, #18 Phase 18 closed
at 18.3, #15 the OR stays as is, #16 already decided, #10 the PIT guard stays
in the default run, #13 the mean window is now labelled, #4 assessed and #7
superseded by the cut; the Phase 20 section re-framed as dormant, #5b folded
into #5). Before that: #22 opened from the second WP-23.C look
(H-007); #21 from the first; #20 drained → `resolved.md`. Prior: 2026-09-13
(#19, #17 → `resolved.md`, #18, #16, #15, #13, #14 → `resolved.md`);
2026-09-12 (#12 GitHub Pages closed → `resolved.md`);
2026-09-11: resolved items split out to `resolved.md`; the maintenance log's open
follow-ups folded in below.

---

## Phase 22 — distribution scoring

### Open decision #7 — Target Range: nominal coverage, and path vs endpoint
**Where:** `prompts/system_prompt.md:166` (the band's spec) · not scored anywhere.
The LLM's Target Range is the only remaining LLM-authored falsifiable claim in the
note, and it is unscored. Two things have to be decided before it can be, and
neither is a bug fix:
1. **No nominal coverage is stated anywhere.** The prompt calls it "a dispersion
   band for 5 business days", never "an 80% interval". Without a nominal, coverage
   is a measurement, not a test — so either pre-register a nominal (and the model
   should be told it), or accept that this can only ever be descriptive.
2. **It is a *path* band, not an endpoint band.** "Where the asset can reasonably
   trade" over 5 days is the intraday range, so containment must be scored against
   the high/low over the window, not the T+5 close. Scoring the close measures a
   different quantity and would report far higher coverage than the claim earns.
Deliberately deferred out of Phase 22 (scope was the conditional distribution).

### Open decision #8 — does the distribution deserve a wider published interval?
**Where:** `quant_context.conditional_cells` · `score_distributions.NOMINAL_COVERAGE`.
The note publishes P25/P75, so the interval it asks to be judged on contains 50%
of realizations by construction — half of all outcomes land outside the band the
reader sees. The table already holds p10/p90, and publishing those instead (or as
well) would be a more useful risk read.

**Narrowed 2026-09-11 — the expensive half is gone.** This was logged as costing a
restart of the sealed interval clock. It no longer does: `collect_quant_raw` now
writes **p10/p90 into the quant log** alongside the published triple. The log is
the scorer's point-in-time source, so the wider band is accumulating a record
from 2026-09-11 whether or not the note ever shows it — a later decision to
publish would inherit that record instead of starting at zero. Nothing about the
published product or the [WP-22.C](roadmap.md) seal changed, and
`score_distributions` ignores the extra keys because it scores the quantiles that
were *claimed*.

**What is still open is only the product call:** does the reader get a 50% band or
an 80% one? Publishing p10/p90 changes what the note asks to be judged on
mid-record, which still means the *published* band's sealed record restarts from
whenever it changes. That is a real cost, just a much smaller one than before.
Revisit when the note format is being revised for another reason — the record is
no longer the thing waiting.

---

## Phase 20 — paper portfolio *(dormant since v1.6 — everything here waits on a v2 sizer)*

Context: the first live rebalance ran 2026-08-24 and produced two fully flat
books out of three. `.macro-assist/portfolio/DESIGN.md` is the contract; §7
mandates a confirm-on-first-run eyeball, which is what surfaced all of this.
**Two rebalances ran in total (2026-08-24, 08-31).** v1.6 then withdrew the
sizer's input (bias + confidence), `rebalance.run()` declines to advance the
books, and the DESIGN §9 clock stopped with two weeks of sample — the board is
authoritative. Nothing below is a live fix; each is a constraint on the v2
sizer (off the conditional distribution) if one is ever pre-registered.

Seven items (#1, #2, #3, #4, #6 and the two 2026-08-24 fixes) are closed — see
[`resolved.md`](resolved.md). The caveats they carried forward are entries in
their own right below.

### Carried finding #5 — MAX_WEIGHT binds structurally on a low-vol universe *(carries #5b)*
**Where:** `SizingConfig.max_weight = 0.35`, `vol_target_annual = 0.10`.
**Problem:** with |w| ≤ 0.35 the max reachable book vol on the S&P/IEF pair is
`0.35·0.122 + 0.35·0.055 ≈ 6.2%` — the 10% target is unreachable by
construction whenever the book is concentrated in low-vol names. The capped
allocation reallocates freed budget and reports the shortfall, but it cannot
manufacture risk the cap forbids.
**The evidence is in, and it is all there will be (2026-09-14).** The item asked
for a few rebalances' worth of `vol_shortfall`; the track produced two before
its input was withdrawn, and the cap bound on both — 2026-08-31 kimi: ex-ante
book vol **1.5%** against a 10% target, "8.5pp under target — MAX_WEIGHT binds
on 10Y (IEF)", the one non-neutral position sized at the cap. Confirmed as a
structural property of the rule, not a tape.
**What it decides:** is 10%/0.35 the right pair? Options: raise `max_weight`,
lower `vol_target_annual`, or cap **risk contribution** (`|w|·σ`) instead of raw
weight — the last preserves the inverse-vol ratios the cap currently overrides.
*Lean: cap risk contribution; it is the version of the constraint that matches
what the rule is trying to express.* Needs a DESIGN §3 step 7 amendment, and it
belongs in the v2 sizer's pre-registration, not as a patch to a dormant v1.
**#5b, folded in:** the risk-contribution cap changes the **measured quantity**
(ex-ante book vol), so it must ship as a *single* isolated sizing change with
the before/after noted in the ledger — never alongside another sizing change,
or the forward-test P&L is unattributable. **One deliberate sizing change at a
time.**

### Carried caveat #2b — abstention is now weaker, deliberately
*From resolved #2.* A band-less directional call now always takes HAR-sized risk.
The guard it replaced was meant to catch missing *risk data*, and HAR σ **is** that
data, so this is the intended loosening — but it is a loosening. The
`require_distribution` knob survives for a deliberate per-arm revival.

### Carried caveat #3b — the fragility gate makes attribution impure
*From resolved #3.* Because fragility can cut gross before drawdowns, a future
"book beat benchmark" is partly the gate's **beta-timing**, not pure signal alpha.
Keep that distinction when reading the DESIGN §9 quarter result.

### Deferred #1b — emit a machine-readable band into the note
*From resolved #1.* Reading the code-computed table instead of LLM prose (option b)
is the correct eventual decoupling, but the committed note carries only the LLM's
prose reproduction, so it means re-plumbing note generation
(`llm_analysis._build_analysis_markdown` + threading the computed bands through).
Deferred: a large, reactive change mid-forward-test for a now-cosmetic gain.
**Revisit only if a note-format revision is already on the table** — the same
condition as open decision #8.

### Deferred #6b — an excess-return / IR series from first exposure
*From resolved #6.* The flat-book NAV label prevents the misread; a proper
information-ratio series that **starts at first exposure** is the real DESIGN §5
deliverable. Belongs with the §9 quarter read, not a mid-flight reporting tweak.

---

## Pipeline / accuracy

*Nothing open. #13 (the ≤3-year mean labelled five) landed 2026-09-14 and the
below-chance headline accuracy (#7, carried) was answered by the cut itself —
both in [`resolved.md`](resolved.md). #7 and #8 above are the Phase 22 items.*

---

## Fragility monitor

### Carried finding #14b — the live fragility record 2026-07-18 → 09-11 carries a frozen `vix_term`
**Source:** [KB-029]. The readings are correct by coincidence (contango throughout,
CBOE-confirmed) and are kept; the five `Elevated` rows 2026-08-13 → 08-19 are
artifacts and stay in the log as written, superseded by the KB entry. Anyone
reading the composite's live record across that window must know this. (#14
itself — the label cut's method — closed negative → `resolved.md`, [KB-030].)

**Extended 2026-09-18 → [KB-034]:** 2026-09-16, 09-17 and 09-18 carry **no
calibrated composite at all** — `vix_term` missing, label `Unavailable`, the OR
`comp` channel masked. Unlike the July–September window these are not "correct
by coincidence"; they are absent readings, and the cause was not recorded by
those runs. They are kept as written and are not part of any live Elevated
record.

### Open decision #26 — does the vol term structure need a second issuer feed?
**Source:** [KB-034]. The fallback chain is one deep: yfinance's `^VIX3M`, then
CBOE's own `VIX3M_History.csv`. It has now failed twice in two months
(2026-07-17, yfinance; 2026-09-16, both — cause unrecorded, see below), each
time costing the composite its calibrated label for days at a stretch. A third
tier would remove the single point of failure; it also adds a feed to keep
honest, and a source whose vendor convention differs from CBOE's would put a
subtly different series under the same component name — the [KB-029] failure
in a new costume.

**What is decided before anything is built:** whether a candidate feed is
admitted is a *parity* question, not an availability one — its VIX3M must
reproduce CBOE's own file on the overlap to the published precision, on a
window that includes a backwardation episode, before it may ever serve the
live component. No parity, no admission, however fresh it is.

**What to wait for first:** the instrumentation shipped with [KB-034] means the
next failure names itself. One recorded cause is worth more than a guess at
which tier to add — a 403 from a CDN, a renamed column and a parked file each
argue for a different remedy, and two of the three are fixed in the existing
client. Do not add a feed before the next occurrence is attributed.

*#15 (the turbulence-only hindsight read) and #16 (the CORR shadow flag) closed
2026-09-14 → [`resolved.md`](resolved.md); the track is forward observation only
and the next OR-admission bar carries the lead clause. #18 (WP-18.4's missing
metric) closed the same day: Phase 18 is closed at 18.3, negative-by-construction.*

---

## Phase 23 — exploration tier

*Nothing open. #19 (the seal — 2018-01-01 reused for the distribution class),
#21 (H-005 changes nothing before Phase 22 reads) and #22 (the scorer does not
gain `har_scaled` before its first read) all closed 2026-09-14 →
[`resolved.md`](resolved.md). H-001's artifact errand is done (register). What
remains on this phase is not inbox work: the owner's rewrites of H-002–H-007
(the competence gate, [how we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis))
and WP-23.B's class bar, written before any member is promoted.*

---

## Repo & tooling follow-ups

*Folded in from `maintenance-log.md` 2026-09-11 so there is one inbox rather
than three. The maintenance log now records passes; the open items live here.*

### Carried finding #11 — optional further split of `llm_analysis.py`
~1,200 lines. One cohesive concern (the multi-agent LLM pipeline) but the largest
remaining module and the least test-covered. Could split into agents / synthesis /
note-markdown if it keeps growing; kept as one module for now to minimise churn in
untested code.

---

## Housekeeping

- The DESIGN §9 go/no-go clock is **forward-only** and it **stopped** on
  2026-09-04 with two rebalances of sample (v1.6 withdrew the sizer's input).
  It does not restart until a v2 sizer is pre-registered; when it does, #5's
  lesson applies from day one — a structurally cap-throttled book must not
  masquerade as a low-conviction one, so `vol_shortfall` is read each week.
- Test-fixture discipline: `test_rebalance.py`'s band fixture asserted a note
  layout the pipeline has never emitted, so the suite stayed green while
  production parsed nothing. When a fixture stands in for pipeline output,
  copy a real line out of `results/` rather than composing a plausible one.
  *(Also recorded in `CLAUDE.md`.)*
