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

Last reviewed: 2026-10-10 — **#26** closed at the owner's call → [`resolved.md`](resolved.md):
the vol term structure's feed stays as it is (retry + CBOE fallback + `feed_gate`), no
catch-up re-check, no second issuer. Before that, 2026-10-01 (later) — the note stops calling the model (v2.2,
[ADR-0024](../decisions/ADR-0024-the-note-makes-no-llm-call.md)), and three items it
made moot or finished closed → [`resolved.md`](resolved.md): **#7** (the Target Range
is no longer published), **#1b** (the note now carries the computed table itself) and
**#11** (`llm_analysis.py` is dormant). Earlier the same day, **#36** opened by IMP-9's step 1 (which outside
input is tried first as a filter on the OR flag) and closed the same day →
[`resolved.md`](resolved.md): CBOE SKEW first, then the commercial-paper
spread. Earlier the same day, **#35** opened by the risk-rule build (does H-009's clause
count a firing just before an episode's peak?) and closed the same day → [`resolved.md`](resolved.md):
yes, up to 19 trading days. Before that, 2026-09-29 — **#33** opened by WP-23.B: the gap → width class has
a bar and no seal. Before that, 2026-09-22 (second pass, same day) — all three items from the
06:00 pipeline failure worked. **#28 closed** → [`resolved.md`](resolved.md)
(monthly critical series carry forward seven days, marked; `treasury_10y` never
does; the abort survives for a series with nothing available), leaving its one
deferred question as the new **#29** — whether the sealed Phase 22 scorer may
read a carried day, which is answered at its first read, not now. **#27**'s fork
is decided (install) and the half that stops it recurring shipped: every run
leaves a heartbeat and `record_audit.py` is **red until the crontab line is
installed**. **#26** item 1 is done and its blocker is half-answered — the CBOE
probe is green off the runner and now runs in CI, so the next pipeline run
settles it; item 3 (move the run) is the remaining decision and shares a crontab
with #27.

Earlier the same day — #27 and #28 opened from the 06:00 pipeline failure
(Actions run 35692953937): the catch-up call that has never fired, and the
critical-series abort that cost a note over an unchanged monthly series. The
retry defect under that failure was fixed the same day, not carried here. #26
work item 2 corrected — it assumed the catch-up runs.

Before that: 2026-09-14 — #23 and #24 (the Phase 24 convention calls) opened
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

### Deferred #6b — an excess-return / IR series from first exposure
*From resolved #6.* The flat-book NAV label prevents the misread; a proper
information-ratio series that **starts at first exposure** is the real DESIGN §5
deliverable. Belongs with the §9 quarter read, not a mid-flight reporting tweak.

---

## Pipeline / accuracy

*#13 (the ≤3-year mean labelled five) landed 2026-09-14 and the below-chance
headline accuracy (#7, carried) was answered by the cut itself — both in
[`resolved.md`](resolved.md). #8 above is the Phase 22 item; #7 resolved moot 2026-10-01 (ADR-0024).*

### Carried finding #30 — ADR-0012's revisit section has not been re-read since the failure that tested it
**Where:** [ADR-0012](../decisions/ADR-0012-external-cron-with-backstop.md),
`## Would we revisit it?`.
**Source:** the carried obligation from #27, which closed 2026-09-23 →
[`resolved.md`](resolved.md).

ADR-0012 chose an external cron service over GitHub's scheduler, and the
catch-up call was part of what made that trade look safe. Its revisit section
hedges only the direction where **GitHub's scheduler becomes reliable**. It says
nothing about the direction that actually cost a note: **the external caller
being incompletely installed** — one of its two slots configured, for a month,
with nothing anywhere able to notice.

That direction is now instrumented (the heartbeat, WP-24.B entries for all three
slots), so the decision is better defended than it was. The section still does
not mention the failure mode, which means the next person to read the ADR gets
the pre-2026-09-22 picture of what could go wrong with it.

**Per convention #11 the person who re-reads it edits that section** — even to
say "and it did not fire", which is a legitimate answer and clears the line.
This item is not licence for the assistant to rewrite it. WP-24.F does not flag
it today, because no *cited* referent has moved; the gap is in what the section
chose to cite in the first place.

### Carried finding #29 — may the Phase 22 scorer read a day conditioned on a carried value?
**Where:** `fred_data.carry_forward` · `results/quant_context_log/*.jsonl`, key
`carried_forward` · `score_distributions.py`.
**Source:** the carried caveat from #28, which closed 2026-09-22 →
[`resolved.md`](resolved.md).

A critical monthly series that cannot be fetched is now carried forward and
marked, so a day's published distribution may have been conditioned on an input
that was up to seven days old. **Nothing in the scorer acts on that**, and that
was the deliberate call: Phase 22's bar is sealed with its first honest read
~2027-05, and changing what the scorer reads mid-flight is the convention #7
hazard — a threshold or a sample moved after the seal is a goalpost move, even a
well-meant one. Deciding it now would also be guessing, since no carried day has
occurred yet.

**What has to happen at the read**, not before: count the carried days in the
scored window, and decide then whether they are scored, excluded (the way the
2026-09-16 → 09-18 `Unavailable` composites are, #14b), or reported as a split.
The flag exists precisely so that question has an answer available. If the count
is zero the question is moot; if it is large enough to matter, the fact that it
was *recorded before anyone looked* is what makes any of the three honest.

**The one thing that would force it earlier:** a long FRED outage producing a
run of carried days inside the sealed window. That is a reason to read the count,
not a licence to change the bar.

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

*#15 (the turbulence-only hindsight read) and #16 (the CORR shadow flag) closed
2026-09-14 → [`resolved.md`](resolved.md); the track is forward observation only
and the next OR-admission bar carries the lead clause. #18 (WP-18.4's missing
metric) closed the same day: Phase 18 is closed at 18.3, negative-by-construction.*

---

## Phase 23 — exploration tier

### Open decision #33 — which seal governs the gap → width class (H-003)?

**Opened 2026-09-29, by WP-23.B.** The class bar is written
(`class_bars.GAP_WIDTH`: ≥ 40 quarters in ≥ 10 four-quarter blocks) and its
seal is left `None`, so `class_bars.read` and `seal_key.py` refuse a sealed
read under it. `resolved.md` #19 decided the seal for the *conditioner* class;
it did not decide this one, and the choice here is not the same choice.
Point-in-time SEP exists quarterly from 2012, so the whole record is ~55
quarters, and on the 2018-01-01 seal the sealed side is ~34 — under the floor
by construction.

1. **The whole SEP record is the sealed side.** Nothing has ever looked at the
   gap against realized width (H-003: *What was seen — nothing yet*), so no
   part of 2012 → now has been seen for this question. One read, ~55 quarters,
   clears the floor. Cost: no explore side at all. The data errand has to be
   built without ever scoring the gap against outcomes, and the first look
   *is* the read.
2. **2018-01-01, reused, as #19 did.** One seal in the repo; 2012 → 2017
   (~24 quarters) is the explore side. Cost: the sealed read is `underpowered`
   by construction until ~2028, so this is a decision to wait.
3. **No historical seal; read the live record forward.** Forty quarters is ten
   years. In practice, never.

*Lean, the proposer's:* (1), with the errand's output limited to the gap series
and a test that nothing in it reads a realized rate change. The floor was set
from a principle (ten years, more than one rate cycle) and not moved to fit
any option. Nothing depends on this before H-003's data exists.

*Earlier: #35 (H-009's clause counts a firing up to 19 trading days before an episode's peak) closed 2026-10-01. #34 (accept ADR-0023 — a fragility rule for a real decision, read on drawdown) closed 2026-10-01, accepted with a 0.5 pp return budget and the 2018-01-01 seal. #32 (accept ADR-0022 — the technical audit moves to an
independent agent loop) closed 2026-09-27, accepted. #19 (the seal — 2018-01-01
reused for the distribution class), #21 (H-005 changes nothing before Phase 22
reads) and #22 (the scorer does not gain `har_scaled` before its first read) all
closed 2026-09-14. All four → [`resolved.md`](resolved.md). H-001's artifact
errand is done (register). The independent audit was built as Phase 25 and
switched on 2026-09-29 — an entry is promoted only through `audit_entry.yml`
([how we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis))
— and WP-23.B, the class bars and the sealed runner, was built 2026-09-29.*

---

## Repo & tooling follow-ups

*Folded in from `maintenance-log.md` 2026-09-11 so there is one inbox rather
than three. The maintenance log now records passes; the open items live here.*

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
