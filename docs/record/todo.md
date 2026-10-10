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

Last reviewed: 2026-10-10 — cleanup pass. Phase 20's four carried items (#5,
#2b, #3b, #6b) closed → [`resolved.md`](resolved.md): the book is dormant, they
constrain only a v2 sizer that has not been proposed, and #2b's object (a
directional call) no longer exists. **#26** closed the same day (the vol feed stays
as it is). Notes about items closed elsewhere, an empty section and two
housekeeping bullets that restated `CLAUDE.md` were removed. Earlier passes are
in git history and in `resolved.md`.

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

## Pipeline / accuracy

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

