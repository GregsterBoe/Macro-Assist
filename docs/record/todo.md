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

Last reviewed: 2026-09-22 (second pass, same day) — all three items from the
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

*#13 (the ≤3-year mean labelled five) landed 2026-09-14 and the below-chance
headline accuracy (#7, carried) was answered by the cut itself — both in
[`resolved.md`](resolved.md). #7 and #8 above are the Phase 22 items.*

### Open decision #27 — the catch-up call has never once fired
**Where:** `docs/reference/operations.md:257-258` (the schedule table) ·
`.github/workflows/pipeline.yml` header, *THE CATCH-UP CALL* ·
[ADR-0012](../decisions/ADR-0012-external-cron-with-backstop.md):50, which
rests on it · `todo.md` #26 work item 2, which is built on it.
**Source:** the 2026-09-22 06:00 UTC run (Actions run 35692953937) failed at
stage 1 and published no note; the day was recovered by a hand-dispatched run
at 12:48.

The record says the external service calls `pipeline.yml` twice each weekday —
`23 6` as `cron-primary` and `47 10` as `cron-catchup`. Across **all 39
pipeline runs since 2026-08-28 there is not one run with `source=cron-catchup`**:
every day carries exactly one `cron-primary` and one `schedule-backstop`. The
catch-up is documented, is the justification for several design choices, and
does not exist.

Two things follow, and neither is a bug fix:

1. **The recovery story is wrong wherever it is written.** The workflow header
   argues the catch-up "fills the gap unattended" on a day the primary never
   landed. On 2026-09-22 the primary landed and *failed*, and nothing filled
   the gap. The only surviving net is the `schedule:` backstop at 14:37 — which
   is GitHub's scheduler, the mechanism ADR-0013 moved off for being
   undeliverable, and which has in fact been delivered between 17:44 and 19:41
   on every observed day. Recovery was ~12 hours away, by a route the repo does
   not trust.
2. **#26 work item 2 rests on it.** "Let the 10:47 UTC catch-up call re-check
   the feeds" cannot be assessed until the call exists. Its stated limitation
   (it no-ops when the day's note is already written) is real but secondary to
   its not running at all.

**The decision — taken 2026-09-22: install it.** The `schedule:` backstop alone
is not a net anybody should rely on; it is the mechanism ADR-0013 moved off for
being undeliverable, and on 2026-09-22 it would have been ~12 hours away.

**Shipped the same day — the half that stops this recurring.** Installing a call
nobody watches is how this happened: a slot that never ran and a slot that ran
and no-op'd left **identical traces**, because a no-op writes nothing. So every
run now leaves one line on `output` naming who asked —
`schedule/last-<source>.txt`, written by `pipeline.yml`'s `heartbeat` job — and
`record_audit.py` carries all three slots in its `ARTIFACTS` registry at four
days (WP-24.B). A silent caller is now a red check rather than a month of nobody
looking. `operations.md` → *Is the schedule actually running?* has the by-hand
check; `pipeline.yml`'s THE CATCH-UP CALL header no longer states the catch-up
runs, because it does not.

`record_audit.py` is therefore **red on `schedule/last-cron-catchup.txt` until
the crontab line is installed**, and its message says exactly that. That red is
this item, held where it cannot be forgotten — it is not a stale registry entry
and must not be pinned away.

**Still owed by the owner, and neither is something the assistant can do:**
1. **The second call itself, on the caller.** *The caller is cron-job.org, not a
   shell host* (confirmed 2026-09-22) — so this is a second HTTP job, not a
   crontab line: same dispatch URL, body
   `{"ref": "main", "inputs": {"source": "cron-catchup"}}`, `47 10 * * 1-5`,
   timezone UTC (`operations.md` → *On an HTTP-only service*). The red clears on
   the first catch-up that lands. While in there, move the primary to `23 6` —
   see the adjacent item below, which is **load-bearing for this caller** in a
   way the note under it originally got wrong.
2. **Re-read [ADR-0012](../decisions/ADR-0012-external-cron-with-backstop.md)'s
   `## Would we revisit it?`** — see the paragraph below. Per convention #11 the
   person who re-reads it edits that section; this item is still not licence for
   the assistant to rewrite it.

Whichever way it goes, **ADR-0012's `## Would we revisit it?` should be read
again**: it hedges only the direction where GitHub's scheduler becomes
reliable, and says nothing about the external caller being incompletely
installed — which is the direction that actually cost a note. Per convention
#11 the person who re-reads it edits that section; this item is not licence to
rewrite it.

**Adjacent, same evidence, cheap to settle at the same time:** the primary is
documented at `23 6` and every observed dispatch has landed at 06:00:31-06:00:41
UTC. ~~so the crontab on the host is on `0 6`~~ — *corrected 2026-09-22: the
caller's job is `0 8 * * 1-5` on **Europe/Berlin**, and Berlin is UTC+2 right
now, so `0 8` local **is** 06:00 UTC. Nobody typed the wrong number; the slot is
being read in the wrong frame.* That is worse than a typo, because it moves:
**on 2026-10-25 Berlin falls back to UTC+1, so from Monday 2026-10-26 the same
line fires at 07:00 UTC**, and back to 06:00 UTC on 2027-03-28. `operations.md`
opens the schedule section with *"set the cron service's timezone to UTC so the
slots don't move twice a year"*; that instruction was not followed, and the
whole discrepancy is the consequence. **Fix: set the cron-job.org job's timezone
to UTC and use `23 6` / `47 10` literally** — a Berlin-local schedule that is
correct year-round cannot be written as one crontab line. The 31-second gap
against `plan`'s date cutoff is closed from the caller's side (`trigger_pipeline.sh`
now pins `asof`; `test_trigger_asof.py`), so this is no longer load-bearing —
but the table and the host still disagree, and whichever is wrong should move.
*2026-09-22, and the sentence above is wrong for the caller actually in use.*
`trigger_pipeline.sh` pins `asof` — but **the caller is cron-job.org**, which
sends a static JSON body and cannot compute a date, so it always falls through
to `plan`'s clock guess and its 06:00 cutoff. For this caller the 31-second
margin **is** load-bearing: a dispatch landing at 05:59 is read as yesterday's
slot, no-ops against yesterday's existing note, and leaves today with no note
and every check green. `23 6` buys 23 minutes instead of 31 seconds. The
`trigger_pipeline.sh` fix from the same morning protects a path nobody is
running. `operations.md` → *Is the schedule actually running?* now splits the
two callers instead of asserting the shell-host answer for both.

This also interacts with #26 item 3: if the run moves off the 06:00 hour to
dodge the empty `^VIX3M` window, both slots are being rewritten anyway and the
two should be decided together.

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

### Open decision #26 — the vol term structure's feed: retry, reschedule, or a second source?
**Reframed 2026-09-18** once the cause was found (→ [KB-034] addendum). The
original question below — "does it need a second issuer feed?" — is kept for its
parity rule, but it is probably the **wrong question**: `^VIX3M` returns nothing
from yfinance at ~06:04 UTC and current data at 16:24 UTC the same day, three
mornings running. A second issuer does not address a feed that works ten hours
later.

**What is actually open, cheapest first:**
1. ~~**Retry the yfinance leg.**~~ **Done 2026-09-22.** `pipeline_common.
   yf_history_with_retry` gives every yfinance path the CBOE client's budget —
   two attempts, one pause — and counts an **empty frame** as a failure rather
   than an answer, which was the actual defect. Wired into all three
   single-attempt loops: `quant_context._fetch_fragility_histories` (the live
   path that produced the three `Unavailable` readings), `market_data.
   _ticker_snapshot` (the payload's `vix_term_ratio`, which had no fallback of
   any kind) and `fragility_panel.fetch_histories` (the panel/backtest path,
   which the item had not named). `test_yfinance_retry.py`. Whether it is
   *enough* is a live question, not a settled one: the failure was time-of-day
   bound and lasted three consecutive mornings, so two attempts seconds apart
   may well draw the same empty frame twice. It removes the cheapest failure,
   it does not remove the cause — item 3 does.
2. **Let the 10:47 UTC catch-up call re-check the feeds.** ~~It runs today and
   no-ops~~ — *corrected 2026-09-22: it does not run at all. No pipeline run
   since 2026-08-28 carries `source=cron-catchup` (→ #27).* The limitation
   below still applies once it exists: stages skip when the day's note already
   exists, so the one mechanism built for "the early run failed" cannot help a
   run that *succeeded* with a hole in it.
3. **Move the run.** 06:04 UTC is 02:04 ET; nothing about the note needs that
   hour. **Still open, and now the only item that addresses the cause** — the
   feed is empty at 06:04 and current at 16:24, so a later slot is the one fix
   that does not depend on a retry winning a race or on a fallback nobody has
   yet seen work. It is a schedule decision, not a code change, and it touches
   the same crontab as #27.
4. A second issuer feed — only if 1–3 fail, and under the parity rule below.

**Blocking all four: does the fallback we already have work at all?**
**Half-answered 2026-09-22** (→ [KB-034] addendum). The probe is **green from a
developer machine** — both legs, current to 2026-09-21, exit 0 — so the code
path is sound and the failure is environmental. Every one of the three observed
failures was on an Actions runner; the probe was not. `fetch_cboe_index` fetches
`cdn.cboe.com` with bare `urllib` (`Python-urllib/3.x`, no other headers) from a
datacenter IP, which is the combination a CDN WAF rejects, and 403 is already
named in `fragility_panel.py`'s own comment — but the recorded reason from those
three runs was never captured, so that is a mechanism, not a finding.

`--probe-cboe` now runs in CI on every pipeline run (`pipeline.yml`, job
`feed_probe` — its own job, so it still runs on a day `daily` fails). **The next
pipeline run settles it**, with the runner's own reason attached: green closes
item 4, a 403 makes the fix a request header rather than a third feed. Until it
reports, the vol legs are still to be treated as having no fallback.

**Also carried:** `market_data`'s `vix3m` has no fallback on any path —
`vix_term_ratio` vanished from the LLM payload on all three days and no
mechanism covers it.

---

### The original question, kept for its admission rule — a second issuer feed
**Source:** [KB-034]. The fallback chain is one deep: yfinance's `^VIX3M`, then
CBOE's own `VIX3M_History.csv`. It has now failed twice in two months
(2026-07-17, a genuine two-month upstream stop; 2026-09-16, an intermittent
empty response at one hour of the day, with CBOE failing to cover it), each
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

**What to wait for first:** ~~the instrumentation shipped with [KB-034] means the
next failure names itself~~ — *superseded 2026-09-18: the cause was found from
the payload previews the same day, and it is not a case a new feed would fix.
Work items 1–4 above first.*

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
