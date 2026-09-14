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

Last reviewed: 2026-09-14 (#22 whether the Phase 22 scorer gains a `har_scaled` comparator, from the second WP-23.C look (H-007); #21 does the explore-tier H-005 look change anything before Phase 22, from the first WP-23.C run; #19 updated — nothing burnt, no seal earlier than 2018; #20 the two product → research imports drained → `resolved.md`; #19 which seal governs a Phase 23 promotion, from the exploration-tier draft; #17 the HAR-RV fit window landed → `resolved.md`; #18 WP-18.4's missing metric, from the archive pass; #16 the CORR shadow flag IMP-7 admitted and did not wire, [KB-032]; #15 the turbulence-only hindsight read from [KB-031],
open decision; #13 `hy_spread` mean-window caveat from [KB-028]; #14
IMP-5.3 added from [KB-029] and closed the same day → `resolved.md`, [KB-030]).
Prior: 2026-09-12 (#12 GitHub Pages closed → `resolved.md`);
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

## Phase 20 — paper portfolio

Context: the first live rebalance ran 2026-08-24 and produced two fully flat
books out of three. `.macro-assist/portfolio/DESIGN.md` is the contract; §7
mandates a confirm-on-first-run eyeball, which is what surfaced all of this.

Six items (#1, #2, #3, #6 and the two 2026-08-24 fixes) are closed — see
[`resolved.md`](resolved.md). The caveats they carried forward are entries in
their own right below.

### Carried finding #4 — kimi confidence clusters high (no code change — deliberate)
**Where:** kimi ensemble agreement → `AssetSignal.confidence`.
**Assessed 2026-08-24 — leave as-is, document.** The confidence is **already the
continuous vote share** (`aggregate`: `conf = round(dir_share*100)`, un-clamped),
not a binary or bucketed statistic. It lands on 100/92 today because the 12
samples *genuinely agree* — a property of a one-sided tape, not a degenerate
estimator. A "finer statistic" (vote margin, per-sample probability) would not
change that near-unanimous agreement should read as high confidence; building one
now would be fitting to the current tape (exactly the "too reactive" move to
avoid). When the tape contests, agreement — and therefore confidence — will spread
on its own.
**The real lever is the cap, not the confidence.** The "max weight or nothing"
degeneracy the finding describes is #5 (the raw-weight cap binding), not the
confidence channel. Fix it there.
**Watch:** `vol_shortfall` in the weekly reports — if the cap binds every week,
#5 is confirmed and the confidence channel is moot until it's addressed.

### Carried finding #5 — MAX_WEIGHT binds structurally on a low-vol universe
**Where:** `SizingConfig.max_weight = 0.35`, `vol_target_annual = 0.10`.
**Problem:** with |w| ≤ 0.35 the max reachable book vol on the S&P/IEF pair is
`0.35·0.122 + 0.35·0.055 ≈ 6.2%` — the 10% target is unreachable by
construction whenever the book is concentrated in low-vol names. The capped
allocation now reallocates freed budget and reports the shortfall, but it cannot
manufacture risk the cap forbids.
**Open question:** is 10%/0.35 the right pair? Options: raise `max_weight`,
lower `vol_target_annual`, or cap **risk contribution** (`|w|·σ`) instead of raw
weight — the last preserves the inverse-vol ratios the cap currently overrides.
*Lean: cap risk contribution; it is the version of the constraint that matches
what the rule is trying to express.* Needs a DESIGN §3 step 7 amendment.
**Now the live question (2026-08-24).** #2 made all arms hold risk, so the cap
now binds in practice, not just in theory — and it is the mechanism behind #4's
"max weight or nothing". **Deliberately not changed in this batch:** the
risk-contribution cap changes the *measured quantity* (ex-ante book vol), so
doing it at the same time as #2 would make the forward-test P&L unattributable.
Discipline is one deliberate sizing change at a time. **Next step:** watch
`vol_shortfall` / `capped` in the weekly reports for a few rebalances; if the cap
binds every week (expected on the low-vol S&P/IEF pair), implement the
risk-contribution cap as a single, isolated §3-step-7 change and note the
before/after in the ledger.

### Carried caveat #5b — the risk-contribution cap is a *single* isolated change
*From resolved #2.* #2 made all arms hold risk, so the cap now binds in practice.
The risk-contribution cap changes the **measured quantity** (ex-ante book vol), so
shipping it alongside another sizing change would make the forward-test P&L
unattributable. **One deliberate sizing change at a time**; note the before/after
in the ledger when it lands.

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

### Carried finding #13 — `hy_spread.five_yr_mean` is a ≤3-year rolling mean wearing a 5-year label
**Where:** `fred_data.py:236-238` (the field is computed over whatever the fetch
returned) · `llm_analysis.py:1093` (the FRED dict is dumped as raw JSON into the
user message, so the model reads the key name `five_yr_mean` verbatim).
**Source:** [KB-028] nuance (d), carried out of WP-17.5 deliberately unfixed.
**Problem:** `fetch_fred_data` asks for 5 years, but free FRED serves
`BAMLH0A0HYM2` on a *rolling* ~3-year window (2023-09-12 → today on
2026-09-13, and the start date moves forward daily). `five_yr_mean` and
`vs_mean` for `hy_spread` are therefore means of ≤3 years of one credit regime,
labelled as five — the model is told "vs 5-yr mean" for a number that is not
that, and the baseline it compares against drifts as the window rolls. Every
other series in that branch (`philly_fed_mfg`, `real_yield_10y`,
`breakeven_10y`, `nfci`, `jobless_claims`) gets the full window; the mislabel is
specific to HY.
**Why not fixed with KB-028:** the conditional table is the note's published
product and got the BAA10Y fix; `hy_spread` is a prompt input the model cites
([KB-010]: kept for citations, `baa_spread` was the one dropped at 0/78), and
changing the payload mid-record is a separate lever from the quant-layer rebuild.
**Options, cheapest first:**
1. **Label honestly** — emit the window actually used (e.g. `mean_window_start`
   / `mean_window_years`) alongside or instead of `five_yr_mean`. Bug fix, no
   version bump; the model stops being told something false.
2. **Compute HY's mean on BAA10Y-scaled history** — a longer baseline, but then
   the level and the mean are different series, which is worse than the label.
3. **Fold into WP-18.4** as `drop-hy_spread`, next to `drop-baa_spread` — the
   ablation gate decides whether the field earns its place at all. If it goes,
   the mislabel goes with it.
*Lean: option 1 now, independent of 3 — a wrong label is a defect regardless
of whether the field survives ablation.* One caveat to carry: `jobless_claims`'
comment says its window "starts ~2021", which is a dated remark about a 5-year
fetch, not a rolling-window problem; don't conflate the two.


### Carried finding #7 — headline accuracy is below chance and horizon-decaying
**Where:** `results/accuracy_report.md` (2026-08-24 run).
**Numbers:** T+5 directional 46%, T+10 42%, T+20 32%; all three horizons flagged
overconfident (ECE 0.130 / 0.172 / 0.254, BSS negative throughout).
**Context:** the loosened arm's commitment table is the one positive — net edge
+0.031 vs baseline −0.113, commit-rate 20% vs 56%. But its own caveat is the
load-bearing one: **6% bear-share over 104 directional calls, entirely in a
rising tape**. The portfolio book is the forward test of exactly this, and the
arm it currently trades (kimi) went 100%-confident long S&P / short bonds on
2026-08-24 — the same one-sidedness, now at 70% gross.
**Action:** no code change. Do not read an early green NAV print as edge; watch
bear-share into the first risk-off. Revisit at the DESIGN §9 quarter mark.
---

## Fragility monitor

### Carried finding #14b — the live fragility record 2026-07-18 → 09-11 carries a frozen `vix_term`
**Source:** [KB-029]. The readings are correct by coincidence (contango throughout,
CBOE-confirmed) and are kept; the five `Elevated` rows 2026-08-13 → 08-19 are
artifacts and stay in the log as written, superseded by the KB entry. Anyone
reading the composite's live record across that window must know this. (#14
itself — the label cut's method — closed negative → `resolved.md`, [KB-030].)

### Open decision #15 — "turbulence alone is not an alarm": a hindsight read, not a result
**Where:** `.macro-assist/fragility_or.py` (the OR over `_CH_KEYS`) ·
**Source:** [KB-031] nuance (b), seen *after* the IMP-6 run on the window it was
read off. Of the OR flag's 18 PIT alarms at 5d, all 6 true ones have a second
channel firing in the run and 10 of the 12 false ones are turbulence-only; the
PIT-p90 turbulence flag fires on 13.6% of readings and discriminates label days
only 1.4× at 5d (composite 3.3×, absorption 2.8×). Requiring a non-turbulence
channel would have lifted 5d precision on *this* window — and that is exactly
the observation CLAUDE.md #7 says not to act on: it was not pre-registered, any
re-test on 2013–2026 is in-sample for it, and [KB-020] measured ETF-turbulence
as the best standalone channel by non-overlapping AUC (0.713), so the flag's
looseness and the channel's information are different things. **The call:**
either leave it (the OR's stated limit is precision ≈0.3, and it is a recall
mode by design), or pre-register it as a *forward* test — a second shadow flag
`or_no_turb_alone` logged beside the OR from a stated date, judged only on live
alarms after that date, with the bar written first. Nothing on the backtest
window can settle it. Not scheduled; IMP-7 ran next and is closed ([KB-032]).

### Open decision #16 — CORR was admitted by the letter of the IMP-7 bar; the shadow flag it earned is not wired
**Where:** `.macro-assist/fragility_or.py` (`build_channels`, `_CH_KEYS`) ·
`companion_testing.py` · **Source:** [KB-032] mechanism and nuance (c). The IMP-7
pre-registration committed an admitted companion to the shadow ladder as a
separate flag. Average pairwise correlation (CORR, 60-day, sector panel) met the
admit clause — PIT recall +1 crisis at both horizons at the trio's own 18 alarms
and precision, LOCO recall held. The diagnostic shows what met it: under its
expanding PIT p90 CORR fires on 14 of 664 readings and on **two** where the trio
is silent (2020-06-01, 2020-06-08), which extend the COVID alarm into the
2020-06-08 aftershock episode. An `or_corr` shadow flag would agree with the
live OR on 662 of 664 readings; it cannot produce a decidable live record.
**The call (made 2026-09-13, recorded here so it is a choice and not a quiet
drop):** not wired. Not a re-reading of the bar — the bar was met — but a
judgement that the record it would build is worth nothing. Re-open only if the
next OR-admission bar (with its lead clause, [KB-032] "what it changes") is run
on a shift-form correlation measure and that admits on a crisis with lead. Cost
of wiring if ever wanted: a CORR channel in `build_channels`, an `or_corr`
boolean in the OR reading's JSONL log, tests; no prompt exposure, no bump.

### Open decision #18 — WP-18.4 (input ablation) has had no outcome metric since v1.6
**Where:** `roadmap.md` Phase 18 (hard-gate paragraph, rewritten on the
2026-09-13 archive pass) · board "Queued / dormant". **Source:** the archive
pass itself, not a measurement. WP-18.4 was to ablate payload sections and read
the Brier of the LLM's directional calls ([KB-007]'s metric). v1.6 cut those
calls ([KB-024], [ADR-0009]), and the distribution that replaced them is
rendered by Python from `conditional_distributions.json` — the LLM payload
cannot move it. The only LLM-authored falsifiable claim left in the note is the
Target Range, which is unscored (#7). So 18.4 and 18.5 are not "gated on
sample"; they are gated on a scoring protocol for the model's prose that does
not exist. **Options:** (1) close Phase 18 at 18.3 as a negative-by-construction
— the screens ([KB-009]/[KB-010]) stand as the payload's documented redundancy,
and the token cost of a redundant section is the only remaining reason to prune,
which needs no A/B; (2) make #7 first and run 18.4 against Target Range
coverage; (3) prune the [KB-009]/[KB-010] union on cost alone, no outcome read,
and say so. *Lean: (1) or (3) — an ablation with no scored output is exactly the
unfalsifiable experiment the phase's own hard gate forbids.*

---

## Phase 23 — exploration tier

### Open decision #19 — which seal governs a promoted non-directional hypothesis (WP-23.A)
**Where:** `roadmap.md` Phase 23 (WP-23.A) · [`hypotheses.md`](hypotheses.md)
H-002/H-004 · `numeric_baseline.SEAL_START`. **Source:** the Phase 23 draft
(2026-09-13), not a measurement. `SEAL_START = 2018-01-01` was chosen for
*directional* families (five stress regimes in the holdout, ~9 years of explore
surface) and every WP-21.E family is comparable because they share it. A
promoted shadow-conditioner hypothesis reads a *different question* — a
conditional distribution against `unconditional`, Phase 22's bar — on the same
dates. **Options:** (1) reuse 2018-01-01: the slice has never been read for a
distribution question, and the ledger records the reuse; keeps one seal in the
repo; (2) a new seal for the distribution class, later than 2018 so the explore
surface includes 2018 and 2020 stress — costs holdout regimes; (3) no
historical seal at all — explore on all history, confirm only on Phase 22's
live record from 2026-09-07, which pushes any read to ~2027-05 or later.
*Must be decided before anything is promoted; the entry that decides it names
the hypothesis class, not a hypothesis.* **Update 2026-09-14:** WP-23.C ran its
first looks on report dates 2010-06-25 → 2017-12-29 — explore surface under all
three options, so nothing was burnt; but a seal *earlier* than 2018 is now off
the table, and the multiplicity ledger those looks left (seven arms, one run,
all reported) travels with whichever class is promoted first. Also inside this
phase, dated: H-001's confound is resolvable from CI artifact `10013945071`,
**expires 2026-10-07**.

### Open decision #21 — the macro bucket walked forward is reliably worse than `unconditional` on the explore slice: does anything change before Phase 22 reads?
**Where:** [`hypotheses.md`](hypotheses.md) H-005 · `results/explore_conditioner/report.md` ·
`conditional.assign_bucket` · **Source:** the first WP-23.C run, 2026-09-14 —
**explore tier, `exploratory` by construction, not a result.** The v2.1
conditioner (NFCI × curve × BAA10Y, `MIN_N = 10`, collapse as the product)
walked forward with known-by-*t* history on 2010-06 → 2017-12 scores −0.009 /
−0.028 / −0.053 against `unconditional` at 5 / 10 / 20d over all six assets,
intervals clear of zero at every horizon; on the original three, −0.004 /
−0.019 / −0.029. The mechanism H-005 names is legible (a regime-memory
conditioner with about three regimes behind it) and the confound is exactly the
sealed slice (one calm tape here; five regimes there). **The product decision
is Phase 22's** — sealed from 2026-09-07, first read ~2027-05 — and this look
must not pre-empt it. What needs a call is whether to wait: **Options:** (1)
nothing changes; the note keeps publishing the bucket, H-005 stands as the
recorded prior, Phase 22 answers it — the default, and the only option that
costs nothing; (2) decide #19 as option (1) and pre-register *one* read of this
walk-forward on the 2018+ historical slice under the WP-23.B class bar,
disqualifiers first — an answer years earlier, at the price of burning that
slice for the whole conditioner class; (3) the same as (1) but the note's
rendered comparison line names `unconditional` beside the bucket so a reader
can see both — a presentation change, needs the version discipline in
`versions.md`. *Not an option:* changing the bucket's dimensions now — that is
H-004's territory and it failed its own structure check in the same run.

### Open decision #22 — does the Phase 22 scorer gain a `har_scaled` comparator before its first read?
**Where:** [`hypotheses.md`](hypotheses.md) H-007 (and H-006's ledger) ·
`score_distributions._gaussian_quantiles` · `explore_conditioner.har_scaled_quantiles` ·
**Source:** the second WP-23.C look, 2026-09-14 — **explore tier, not a
result.** The scorer's optional `har_gaussian` comparator, walked forward on
2010-06 → 2017-12 with the product's own fit, scores +0.003 / −0.014 / −0.044
against `unconditional` on the S&P at 5 / 10 / 20d and over-covers its
P25–P75 (0.57 at nominal 0.50): a zero-mean Normal is the wrong wrapper for the
σ, on that tape. The same σ applied to `unconditional`'s empirical quantiles as
a width ratio about their median scores +0.026 / +0.020 / +0.016 with coverage
at nominal, and matches the best explore-slice conditioner (`dd_bin`) at every
horizon. So the strongest rival the published table could face is not in the
scorer. **Options:** (1) nothing — `har_gaussian` stays as the optional
comparator it was sealed with, H-007 is the recorded prior, and `har_scaled`
enters the *next* bar (WP-23.B's, for any promoted distribution hypothesis) —
the default; (2) add `har_scaled` to `score_distributions.ARMS` as a second
optional comparator now, before any interval observation resolves against it —
the WP-22.C amendment already states the principle that a better rival makes
the published table's job harder, not easier, so this is admissible under the
seal, but it is a scorer change against a sealed record and needs its own
amendment paragraph in `roadmap.md`, tests, and a note that the comparator was
chosen after an explore look at it. *Not an option:* replacing `har_gaussian`
— the roadmap's exploratory "a constant beat the model" observation was scored
against it and stays comparable only if it stays.

---

## Repo & tooling follow-ups

*Folded in from `maintenance-log.md` 2026-09-11 so there is one inbox rather
than three. The maintenance log now records passes; the open items live here.*

### Carried finding #10 — `point_in_time.py` runs network by default
Its tests make real ALFRED/FRED calls (~113 s of the default suite) but are *not*
marked `integration`, so they run on every `pytest`. They are an important
look-ahead-leakage guard, which is why they were left in the default run. **Open
decision:** mark them `integration` (faster default; the guard then only runs on
explicit `-m integration`) or keep the current trade.

### Carried finding #11 — optional further split of `llm_analysis.py`
~1,200 lines. One cohesive concern (the multi-agent LLM pipeline) but the largest
remaining module and the least test-covered. Could split into agents / synthesis /
note-markdown if it keeps growing; kept as one module for now to minimise churn in
untested code.

---

## Housekeeping

- The DESIGN §9 go/no-go clock is **forward-only** and already running. Every
  week a book sits flat for a wiring reason is a burned week of sample that
  cannot be recovered — the flat-book wiring causes (#1, #2) are now closed, so
  from here a flat book is a real all-Neutral week, not a burned one. The live
  clock item is now #5 (the cap): don't let a structurally cap-throttled book
  masquerade as a low-conviction one — read `vol_shortfall` each week.
- Test-fixture discipline: `test_rebalance.py`'s band fixture asserted a note
  layout the pipeline has never emitted, so the suite stayed green while
  production parsed nothing. When a fixture stands in for pipeline output,
  copy a real line out of `results/` rather than composing a plausible one.
  *(Also recorded in `CLAUDE.md`.)*
