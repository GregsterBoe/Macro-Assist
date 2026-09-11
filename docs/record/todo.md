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

Last reviewed: 2026-09-11 (cleanup pass — resolved items split out to
`resolved.md`; the maintenance log's open follow-ups folded in below).

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
reader sees. The table already holds p10/p90. Publishing those instead (or as
well) would be a more useful risk read, but it changes the published product
mid-record and would restart the sealed interval clock that starts 2026-09-07.
**Not a fix — a product decision with a cost.** Revisit only if the note format
is being revised for another reason.
---

## Phase 20 — paper portfolio

## Phase 20 — paper portfolio

Context: the first live rebalance ran 2026-08-24 and produced two fully flat
books out of three. Root causes below. `.macro-assist/portfolio/DESIGN.md` is
the contract; §7 mandates a confirm-on-first-run eyeball, which is what surfaced
all of this.

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

## Pipeline / accuracy

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

### Open decision #12 — GitHub Pages is still switched off
The docs site cannot publish until a repo admin sets **Settings → Pages → Build
and deployment → Source: "GitHub Actions"** once — or, when that settings page
404s, does the same with
`POST /repos/GregsterBoe/Macro-Assist/pages -d '{"build_type":"workflow"}'` under a
PAT that has admin on the repo. Storing that PAT as the `PAGES_ADMIN_TOKEN` secret
lets the deploy preflight do it instead; the default Actions token cannot (see
`maintenance-log.md`, 2026-09-10). **Every push to `main` that touches `docs/` will
keep failing at the deploy preflight until this is done.** Not a code problem —
don't try to fix it in the workflow.

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
