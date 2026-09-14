# Resolved — decisions and findings that are closed

The other half of [`todo.md`](todo.md). Items move here **with their reasoning
intact** when they close, so `todo.md` stays a true inbox and the "why" behind a
closed call is not lost. Newest first.

This is not a changelog (that is `maintenance-log.md` for housekeeping passes and
`roadmap-archive.md` for closed phases) and not a results record (that is
`knowledge-base.md`). It is the disposition of items that were once open
questions.

> **Carried-forward caveats stay in `todo.md`.** Several items below closed *with*
> a trade-off attached. Those trade-offs are live entries in `todo.md` (#2b, #3b,
> #1b, #6b, #14b; #5b is folded into #5) — resolving an item never silently
> absorbs its cost.

---

## Phase 24 — record integrity

### RESOLVED 2026-09-14 — #23 a record contradiction is red in CI, with a pin; ages stay report-only
**Resolution: option (3) — red immediately, with an explicit pin.** WP-24.D's
contradiction check (board row vs `roadmap.md` entry, `CLAUDE.md` Current-state
table vs board) fails CI on an unpinned disagreement. A deliberate disagreement
is pinned in `record_audit.py` the way
[ADR-0021](../decisions/ADR-0021-product-and-research-are-separated-by-an-import-boundary.md)
pins an import leak: the pin names the pair, must appear in `todo.md`, and **a
pin whose contradiction no longer exists is itself red** — the escape hatch
cannot rot, because rot is what the test looks for. That precedent is one ADR
old and has already completed a full cycle (two leaks pinned, drained, unpinned —
#20), which is why the draft's objection to option (3) — "the escape hatch is
the thing that would rot" — does not hold here. Option (1) is the outcome the
draft itself names as the risk: a report nobody reads. Option (2)'s grace period
is a second clock with no owner, and a contradiction that is fine for N days is
a contradiction that is fine. The audit still **prints the pair and does not
pick a side** — `CLAUDE.md`'s precedence rule says who wins; the check only
insists that someone applies it. **Not red:** WP-24.E's ages. They break no rule
— an old item is information, not a defect — so they are printed by `/orient`
and never fail anything. The line between the two: red is for a *claim the repo
makes twice, differently*; report-only is for a number with no threshold.

### RESOLVED 2026-09-14 — #24 the revisit condition is enforced, not introduced; two ADRs retrofitted
**Resolution: enforce the page shape that already exists.** The draft's premise
was wrong on inspection: **18 of 21 ADRs already carry `## Would we revisit
it?`**, and [`decisions/index.md`](../decisions/index.md) has listed it as part
4 of the page shape all along. "20 existing ADRs would need one retrofitted" is
two — [ADR-0015](../decisions/ADR-0015-soft-kill-convention.md) and
[ADR-0021](../decisions/ADR-0021-product-and-research-are-separated-by-an-import-boundary.md),
both retrofitted the same day and marked as written after the fact.
[ADR-0017](../decisions/ADR-0017-bss-floor-left-open.md) is superseded; its
"What needs deciding" *was* the condition and it fired — superseded pages are
exempt. The "some decisions genuinely have none" worry is answered by the pages
themselves: ADR-0002, -0010, -0011, -0013 say **"No."** with a reason, and a
reasoned "No" is a valid value — the section asks for the conditions, and
"none, because …" is an answer. What the audit does: **(a)** every non-superseded
ADR has the section, non-empty — presence, like convention #11's costs;
**(b)** for the *became-true* half, only the machine-checkable subset: a revisit
section that cites a `todo.md` item, WP or KB id whose referent has since closed
or landed (ADR-0016 → #7/#8, ADR-0009 → WP-21.E / [KB-027], ADR-0020 → Phase
22's sealed read) is printed as *"cited condition may have fired"*, report-only.
Prose conditions ("if GitHub's scheduler became reliable", ADR-0012) are not
read by a machine and no pretence is made that they are. What this rejects: a
structured, machine-readable condition field — narrower than the prose, and the
prose is the point.

---

## Phase 23 — exploration tier

### RESOLVED 2026-09-14 — #19 the seal for a promoted distribution-class hypothesis is `SEAL_START` (2018-01-01), reused
**Resolution: option (1) — reuse.** One seal in the repo. The 2018+ slice has
never been read for a distribution question — every read of it so far was
directional ([KB-024], [KB-026], [KB-027]) — and the ledger records the reuse:
whichever class is promoted first carries the multiplicity of the two WP-23.C
looks (nine arms, two runs, all reported, 2010-06 → 2017-12, all explore
surface). The alternatives were a later seal for the class (gains 2018 and
2020 stress in the explore surface at the cost of holdout regimes and a second
seal to keep straight) and no historical seal at all (confirm only on Phase
22's live record, any read ≥ ~2027-05). Both were declined for the same reason:
the point of a seal is that it was fixed before the question, and 2018-01-01
was. **What it binds:** `explore_conditioner.py` keeps stopping at
`numeric_baseline.SEAL_START`; a promoted distribution hypothesis reads
2018-01-01 → the day before Phase 22's live record once, under WP-23.B's class
bar, and that read burns the slice for the whole conditioner class. The entry
that promotes names the class. **Carried:** nothing — the H-001 artifact errand
that was dated inside this item is done (register, 2026-09-14).

### RESOLVED 2026-09-14 — #21 the walked-forward macro bucket's explore-slice deficit changes nothing before Phase 22 reads
**Resolution: option (1) — nothing.** H-005 stands as the recorded prior (the
v2.1 conditioner walked forward on 2010-06 → 2017-12 scores −0.009 / −0.028 /
−0.053 against `unconditional` at 5 / 10 / 20d over six assets, intervals clear
of zero); the note keeps publishing the bucket; Phase 22's sealed read
(~2027-05) is the product decision and this look must not pre-empt it. Option
(2) — a pre-registered read on the 2018+ slice now that #19 makes it available
— was declined because it spends the class's one historical read on the arm
the explore slice already says is worst, and option (3) — rendering
`unconditional` beside the bucket in the note — was declined as a mid-record
presentation change with a versioning cost and no reader asking for it. The
look's mechanism (a regime-memory conditioner with about three regimes behind
it) and its confound (one calm tape here, five regimes there) are on the
register; if Phase 22 reads `no_edge`, H-005 is the explanation already written.
**Carried:** nothing.

### RESOLVED 2026-09-14 — #22 the Phase 22 scorer does not gain `har_scaled` before its first read
**Resolution: option (1) — no scorer change.** `har_gaussian` stays as the
optional comparator the bar was sealed with; H-007 (`seen`) is the recorded
prior that it is handicapped by its Gaussian wrapper, not its σ; `har_scaled`
enters the *next* bar — WP-23.B's, for any promoted distribution hypothesis —
where it was designed. Option (2), adding it to `score_distributions.ARMS` now,
was admissible under WP-22.C's own amendment principle (a better rival makes
the published table's job harder, not easier) and would have cost nothing on
the record (zero interval observations have resolved against any HAR arm), but
it is a scorer change against a sealed record chosen *after* an explore look at
the rival's number, and the discipline the whole record rests on is that the
bar does not move once the data is visible — either direction. Replacing
`har_gaussian` was never an option: the roadmap's "a constant beat the model"
observation was scored against it and stays comparable only if it stays.
**Carried:** `har_scaled` in WP-23.B's bar (roadmap).

---

## Phase 18 — input information value

### RESOLVED 2026-09-14 — #18 Phase 18 is closed at 18.3, negative-by-construction
**Resolution: option (1).** WP-18.4 (outcome-grounded payload ablation) and
18.5 (feed the ranking into signal weights) were to read Brier on the LLM's
directional calls ([KB-007]'s metric). v1.6 cut those calls ([KB-024],
[ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md)); the
distribution that replaced them is rendered by Python from
`conditional_distributions.json` and the LLM payload cannot move it; the only
LLM-authored falsifiable claim left is the Target Range, which is unscored
(`todo.md` #7). An ablation with no scored output is exactly the unfalsifiable
experiment the phase's own hard gate forbids, so 18.4 is closed unrun and 18.5
with it. The cheap screens stand as the payload's documented redundancy
([KB-009] collinearity, [KB-010] citation); nothing is pruned on cost alone
(option 3 declined — a prompt change mid-record for a token saving nobody
measured). Option (2), re-pointing 18.4 at Target Range coverage, is reachable
only through #7 and is re-opened by #7 if that is ever decided. Phase detail →
`roadmap-archive.md`; one line + verdict in the completed-phases table. No
KB entry: nothing was measured.

---

## Pipeline / accuracy

### RESOLVED 2026-09-14 — #13 `hy_spread.five_yr_mean` now carries the window it was computed over
**Resolution: option (1), landed.** `fred_data._mean_window(series)` returns
`mean_window_start` / `mean_window_years` from the series actually fetched, and
every site that computes a `five_yr_mean` emits them beside it — the
`fetch_fred_data` branch (`hy_spread`, `philly_fed_mfg`, `real_yield_10y`,
`breakeven_10y`, `nfci`, `jobless_claims`), the quant-only branch (BAA10Y and
company) and `point_in_time.historical_snapshot`, so the historical and live key
sets stay identical (`test_schema_matches_current`). Both system prompts gained
one clause at the anchoring rule: `mean_window_years` is the window the mean
covers; when it is under 5, name it, never "5yr". The label the model was
reading (`five_yr_mean`) is kept — historical readers and `regime_features`
parse it — the fix is that the truth now travels beside it. Bug fix, no version
bump; 4 tests (`test_fred_mean_window.py`). Options (2) — HY's mean on a
BAA10Y-scaled history — and (3) — fold into WP-18.4 — are moot: (2) compares a
level to a different series, (3)'s phase closed the same day (#18). The
`jobless_claims` comment that said its window "starts ~2021" was a dated remark
about a 5-year fetch, not a rolling-window problem; reworded so the two are not
conflated.

### RESOLVED 2026-09-14 — #7 (carried) headline accuracy below chance — superseded by the cut
**Resolution: answered, not fixed.** The 2026-08-24 accuracy report (T+5 46%,
T+10 42%, T+20 32%; overconfident at every horizon) was carried with "no code
change, watch bear-share into the first risk-off". The question it was
watching — is the directional call worth anything — was then asked properly
and answered: [KB-024] (not learnable by any model class on this payload),
[ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md) (the product
is cut, v1.6), and the kimi arm whose 100%-confident one-sidedness the item
worried about was deactivated 2026-09-04. The frozen scorer prints its last
window ~2026-10-02; the numbers stay in `accuracy_report.md` as the record of
why. Nothing to revisit at a "§9 quarter mark" that no longer arrives.

### RESOLVED 2026-09-13 — #17 the HAR-RV fit window is fixed, dated against the seal
**Resolution: landed, as recommended — the same day it was opened, with zero
Phase 22 interval observations resolved.** [KB-033] measured the note's vol
forecast walk-forward at the window the live callers handed it (`period="90d"`
→ 74–90 closes; the sizer 130 calendar days): a four-parameter OLS on ~50–70
rows, `degenerate` on every asset, coefficient signs random, and `0.0% ann-vol`
published on 7 of 76 S&P and 10 of 76 Bitcoin dates with `VRP = VIX − 0
(Normal)` attached. Fit on 1000 returns the same function is `skill` on SP500,
Gold and Bitcoin, so the pre-registered wiring rule fired: the fetch was the
defect, not the model.

**What landed** (`.macro-assist/`):
- `vol_forecast.HAR_MIN_RETURNS = 1000` and `har_forecast_or_none(returns)` —
  the one gate every live consumer goes through: fewer than 1000 returns, or a
  non-positive OLS forecast (the `max(0, ·)` clip fired), is *no forecast*.
  `har_rv_forecast` itself keeps its 30-return floor so `har_backtest.py`
  still reproduces the short windows.
- `market_data.fetch_vol_histories()` — a separate `period="5y"` fetch for the
  four published vol assets (≈ 1,255 closes on the equity-hours tickers,
  ≈ 1,830 on Bitcoin). The 90d `histories` the technicals, notable-moves and
  fragility consumers see is **unchanged**, so nothing else in the note moved.
- `quant_context.build_quant_context` / `collect_quant_raw` take
  `vol_histories`; `collect_and_analyze` passes it in both the check and the
  main path. A gated asset gets no note line (SP500: no VRP either) and no
  `vol_forecasts` entry in the quant log — which is what
  `score_distributions.logged_har_sigma` already read a zero as.
- `portfolio/rebalance.HAR_LOOKBACK_DAYS = 1600` (was 130) and
  `har_sigma_from_returns` returns `None` through the gate, so the sizer falls
  back to the conditional σ rather than flooring a zero to a 2 %-vol
  instrument. Inert while the sizer is dormant (v1.6 withdrew its input);
  correct when it is revived.
- 12 tests: the gate refuses 62/90/130/252/999 and passes 1000; a clipped zero
  drops the line, the VRP and the log entry; the 90d `histories` alone can
  never produce a vol block; the fetch list and `_VOL_ASSETS` cannot drift; the
  sizer's lookback clears 1000 closes with a holiday margin.

**Why it was a decision and how the cost was paid.** It changes the published
number from 2026-09-14, the σ every position would be sized off, and the Phase
22 `har_gaussian` comparator on the sealed record. That is the shape of
[KB-028]'s conditioner change and it was handled the same way: a dated
paragraph in WP-22.C, the board row, the five sealed dates 2026-09-07 → 09-11
kept with their old-window σ, and the quant log dating the switch by itself
(the zeros stop). It is a comparator's input, not the bar or the published arm
— a better rival makes the table's job harder, so it cannot be read as a move
in the product's favour. No version bump: a fit-window correction, not a
capability change. Landed before the 2026-10-02 wind-down touches
`pipeline.yml` so the two are not confounded in the log.

**What the number did on the day.** On 2026-09-13's tape the 90d fit said
12.3 / 27.0 / 62.0 / 26.8 % (SP500 / Gold / WTI / Bitcoin); the 5y fit says
13.0 / 19.8 / 45.1 / 35.3 %, against a trailing month of 8.8 / 22.7 / 39.3 /
25.8 %. That is one reading, not a result — the skill number is [KB-033]'s.

**Not done, deliberately.** `har_rv_forecast`'s clip and 30-return floor are
untouched (the harness depends on them); `ewma94`, the best trailing rival in
[KB-033] nuance (a), is not wired as a fallback — a gated asset publishes
nothing rather than a different model under the same label. The horizon read
(IID scaling right in variance, wrong in shape at 5d) is unchanged by the
window and is not acted on here.

## Fragility monitor

### RESOLVED 2026-09-14 — #15 "turbulence alone is not an alarm" stays a hindsight read; the OR is unchanged
**Resolution: leave it.** The observation ([KB-031] nuance (b): of the OR's 18
PIT alarms at 5d, all 6 true ones had a second channel firing and 10 of the 12
false ones were turbulence-only) was read off the IMP-6 window after the run;
any re-test on 2013–2026 is in-sample for it, and [KB-020] measured
ETF-turbulence as the best standalone channel by non-overlapping AUC (0.713) —
the flag's looseness and the channel's information are different things. The
OR is a recall mode by design with a stated precision ≈ 0.3, and nothing on the
backtest window can settle whether requiring a second channel is a rule or a
fit to twelve alarms. The alternative — a pre-registered forward shadow flag
`or_no_turb_alone`, judged only on live alarms after a stated date — was
declined as a new record to build and carry that becomes decidable only after
several live alarms, on a track that is forward observation only with nothing
queued. Recorded so it is a declined read and not a forgotten one; the next
OR-admission bar (with [KB-032]'s lead clause) is where a channel question is
asked, if one is.

### RESOLVED 2026-09-14 — #16 the CORR shadow flag IMP-7 admitted is not wired
**Resolution: not wired — the call was made 2026-09-13 and recorded in the
inbox; moved here on the closing pass.** Average pairwise correlation met the
IMP-7 admit clause by the letter (PIT recall +1 crisis at both horizons at the
trio's own 18 alarms, LOCO held); what met it was two trio-silent readings
(2020-06-01, 2020-06-08) extending the COVID alarm into its aftershock. An
`or_corr` shadow flag would agree with the live OR on 662 of 664 readings and
cannot produce a decidable live record. Not a re-reading of the bar — it was
met — but a judgement that the record it would build is worth nothing.
**Re-open only if** the next OR-admission bar, with the lead clause [KB-032]
names, is run on a shift-form correlation measure and admits on a crisis
*with lead*. Cost of wiring if ever wanted: a CORR channel in
`build_channels`, an `or_corr` boolean in the OR reading's JSONL log, tests;
no prompt exposure, no bump.

### RESOLVED 2026-09-13 — #14 the composite's label cut stays static (IMP-5.3, negative)
**Resolution: measured, and the answer is no → [KB-030].** The question was
whether the composite's `Elevated` cut (static 56.5, the full-sample 90th pct
from [KB-002]) should move to the expanding-PIT rule the OR flag applies to each
of its channels, so the note's two fragility flags share one method. The gate
was pre-registered: re-walk 2008–2026 with the PIT cut (warm-up 252) and
reproduce the static cut's episode recall within ±1 crisis per horizon on the
same window. It lost **2 crises at both horizons** and gained none. The reason is
structural, not noise: the composite's first 252 readings *are* the GFC, so the
expanding 90th percentile starts near 92 and takes until ~2017 to fall to 56.5 —
June 2010 sits at 64–74 against a cut near 80. Two threshold methods in one note
is now a documented asymmetry with a measured reason. The harness stays
(`python fragility_backtest.py pit-cut`); the live label does not consult it.
The frozen-`vix_term` caveat that rode along with #14 stays in `todo.md` as #14b.

## Tooling

### RESOLVED 2026-09-14 — #10 `test_point_in_time.py` stays in the default run
**Resolution: keep the trade.** Its tests make real ALFRED/FRED calls (~113 s
of the default suite) and are deliberately *not* marked `integration`, because
they are the look-ahead-leakage guard — the one test class whose silent
absence has already cost this project (the WP-17 input-window findings,
[KB-003] / [KB-028] / [KB-033], were all "the data was not what the code
assumed"). Marking them `integration` would buy two minutes per run and require
CI to be checked for still running them; the offline path is documented in
`CLAUDE.md` (`--deselect .macro-assist/tests/test_point_in_time.py`) for the
sessions that need it. A deliberate choice, now written down.

### RESOLVED 2026-09-14 — #20 the two product → research imports are drained

**Was:** `fragility_or` (the live OR flag) and `quant_context` (the note's vol
legs) imported their data feeds and history walk from `fragility_backtest.py`,
the research harness that first needed them. ADR-0021's boundary test pinned
both in `KNOWN_LEAKS` on 2026-09-14 rather than tolerate them silently.

**Done:** the feeds (`fetch_histories`, `fetch_cboe_index`, `freshen_vol_indices`,
`fetch_sector_etfs`, `_SECTOR_ETFS`, `_ETF_CACHE`), the walk
(`walk_forward_fragility`) and the target (`forward_worst_return`,
`drawdown_label`, `collapse_episodes`, `episode_scoring`) moved **unchanged**
into a new product module, `fragility_panel.py`. `fragility_backtest.py`
imports and re-exports every name, so `input_testing`, `aggregator_testing`,
`companion_testing`, `regime_backtest` and the tests that spell
`fragility_backtest.fetch_sector_etfs` are untouched; a test asserts the
re-exports are the same objects. `KNOWN_LEAKS` is empty and the test now fails
on any first edge.

**The target went with the feeds** deliberately: `drawdown_label` and
`episode_scoring` are what the live path checks *itself* against
(`python fragility_or.py`'s self-check), so they are on the product side of
the line. AUC, lead time, ablation and the pit-cut check stayed in the harness.

**Verified as todo #20 asked:** the self-check run on the moved code and on the
committed pre-move code, same day, same data, prints identical lines — OR
10/17 · 0.333 at 5d, 11/21 · 0.444 at 10d, 664 evaluable readings — which is
the reference row [KB-031] recorded when it noted the row had moved since
[KB-021]. The full offline suite passes. No behaviour changed; no version bump.

### RESOLVED 2026-09-12 — #12 GitHub Pages is switched on
**Resolution: the repo admin enabled it.** Settings → Pages → Build and
deployment → Source is now "GitHub Actions", so the deploy preflight passes and
the docs site publishes. Every push to `main` touching `docs/` had been failing
at that preflight since the site was stood up — a red check on green code, which
is the kind of noise that trains a reader to ignore checks.

Kept for the next time it matters: the preflight names the fix itself, and the
default Actions token **cannot** do it — a PAT with admin on the repo is
required, stored as `PAGES_ADMIN_TOKEN` if the preflight is ever to
self-heal. When the settings page 404s, the same change is
`POST /repos/GregsterBoe/Macro-Assist/pages -d '{"build_type":"workflow"}'`.
See `maintenance-log.md`, 2026-09-10, for how it was diagnosed.

### RESOLVED 2026-09-09 — #9 `bump_version.py` cannot find its anchors (pre-existing)
**Resolution: option 3 — generate the table.** The milestones table now lives at
[Reference → Versioning](../reference/versions.md), rewritten wholesale from
`VERSION_MILESTONES` between HTML markers on every bump, and
`tests/test_versions.py::test_docs_table_matches_milestones` fails if the page and
the code disagree. Option 2 (drop the doc half) was the earlier lean and was
rejected on one ground: the docs are a published site now, and it would leave a
reader with no way to learn what a `v1.6` stamp means without opening source. The
drift objection to option 1 does not apply to a generated view that a test pins.

Two things changed in `versions.py` to make the view derivable: the capability
text moved out of trailing comments into a `Milestone.capability` field (a
comment would have to be parsed back out), and `--start YYYY-MM-DD` was added for
a capability that goes live later than its merge — the Sunday refit case. First
use was the v2.0 bump, same day.

**Was:** `.macro-assist/bump_version.py:31` (`_PROJECT_DOC`) · `:86` (the
milestones regex) · `:97` (the `agent_version` regex).

`_update_project_doc()` edits two things in the roadmap: the `– present` row of
the milestones table, and the example `agent_version` YAML. **Neither is in the
roadmap any more.** The 2026-09-04 archive pass moved both into
`roadmap-archive.md` along with the v1.5 system-state snapshot, so
`_update_project_doc()` raises
`ValueError: Could not find a '– present' row ...` on any bump.

Confirmed against `git show HEAD:Project_Development.md` — **zero** matching
rows there, one in the archive. This predates the 2026-09-08 docs restructure;
that pass only updated the path constant, which now correctly resolves to
`docs/record/roadmap.md`.

It is an **open decision, not a bug fix**, because it asks where the milestones
table belongs now:
1. **Restore a live milestones table to the roadmap** and let the archive keep
   its dated snapshot copy — but the archive convention says archived blocks are
   not maintained, and a second live table is the exact drift defect the same
   pass was cleaning up.
2. **Point `bump_version.py` at `versions.py` only** and drop the doc-editing
   half. `VERSION_MILESTONES` is already the single source of truth and the
   README calls it that; the roadmap table is a derived view.
3. **Generate the table** from `versions.py` into a doc page at build time.

Option 2 looked right at the time — a bump helper that maintains a hand-written
duplicate of a constant it already owns is the drift problem in miniature — but
option 3 keeps the single source of truth *and* the published history, because
the duplicate is generated rather than hand-written. Bump with
[Development → Version Management](../reference/development.md#version-management).

---

## Phase 20 — paper portfolio

### RESOLVED 2026-09-14 — #4 kimi confidence clusters high — assessed, no change; the track is dormant
**Resolution: leave as-is, as assessed 2026-08-24; moved here on the closing
pass.** The confidence was already the continuous vote share (`aggregate`:
`conf = round(dir_share*100)`, un-clamped); it landed on 100/92 because the 12
samples genuinely agreed on a one-sided tape. A finer statistic would have been
a fit to that tape. The real lever was the cap (#5), where the "max weight or
nothing" degeneracy lives. The watch it carried — does the cap bind every
week — is answered inside #5 (it bound on both of the two rebalances the track
ever ran). Overtaken twice since: the kimi arm was deactivated 2026-09-04 and
v1.6 withdrew the sizer's input, so there is no confidence channel to tune.

Context: the first live rebalance ran 2026-08-24 and produced two fully flat books
out of three. `.macro-assist/portfolio/DESIGN.md` is the contract; §7 mandates a
confirm-on-first-run eyeball, which is what surfaced all of this.

### RESOLVED 2026-08-24 — #6 day-1 NAV comparison is now labelled
`format_report`'s NAV line now checks whether the book holds any risk this period
(`any(t["weight"] …)`); while it holds nothing it appends an explicit caveat —
_"book flat — the gap is the benchmark's entry cost, not alpha; excess return is
meaningful only from first exposure"_ — so a flat-week +Xbp can't be misread as
outperformance. A minimal, honest label rather than a new series.
*Deferred (still open, lower priority):* a proper excess-return / information-ratio
series that *starts* at first exposure (DESIGN §5). The label prevents the
misread; the clean IR-from-first-exposure series is the real §5 deliverable and
belongs with the §9 quarter read, not a mid-flight reporting tweak.

### RESOLVED 2026-08-24 — #2 all arms now run the same sizing rule
Chosen option (a): `sizing_config_for` returns `require_distribution=False` for
**every** arm, so all three size off direction + HAR-RV σ, with the conditional
band *enriching* σ (the `risk_blend="max"` cross-check) when present rather than
gating whether the book trades. HAR σ is a measured, PIT risk input available for
every instrument from prices alone; abstention is now reserved for **Neutral**
(no directional view). This unblocks the exogenous book (structurally flat before)
so DESIGN §6's cross-arm P&L read is finally like-for-like, and it removes the
market book's hostage-to-prose failure mode (see resolved #1).
`advance_books` default cfg now derives from `sizing_config_for(arm)` so the
library default matches the production rule. The `flat_book` flag was re-tuned:
a flat book now means an **all-Neutral** table (genuine no-view week), not a parse
failure, and the report warning says so. DESIGN §3 step 3 + §6 amended. Tests:
`test_market_arm_sizes_without_band_uniform_rule`, updated
`test_advance_books_sizes_only_actionable_names` (10Y sizes off HAR), all-Neutral
`_FLAT_NOTE`.
*Trade-off (carry forward):* weaker abstention — a band-less directional call now
always takes HAR-sized risk. The guard it replaced was meant to catch missing
*risk data*, and HAR σ is that data, so this is the intended loosening; the
`require_distribution` knob survives for a deliberate per-arm revival.

### RESOLVED 2026-08-24 — #1 the prose-band dependency is no longer load-bearing
**Subsumed by #2.** The acute failure #1 named was "a wording change silently
zeroes the book." Under the uniform HAR rule (#2, `require_distribution=False`)
that can no longer happen: HAR σ is the always-available risk input, so a
missing/mis-worded conditional band only forgoes the conditional *cross-check* —
it never flatlines the book. The prose parser stays (hardened for both layouts +
all dashes) as the σ-enrichment path.
**What's left is fidelity, not fragility.** Reading the code-computed table
instead of LLM prose (option b — emit a machine-readable per-asset 5d band into
the note at generation) is the correct eventual decoupling, but the committed
note does **not** carry the conditional distribution table (only the LLM's prose
reproduction), so option (b) means re-plumbing note generation
(`llm_analysis._build_analysis_markdown` + threading the computed bands through).
Deliberately **deferred**: re-plumbing note emission mid-forward-test is a large,
reactive change for a now-cosmetic gain. Revisit if/when a note-format revision is
already on the table.

### DONE 2026-08-24 — two fixes from the same eyeball
- ~~Conditional band parser never matched the live note layout~~ — fixed;
  `conditional_sigma_annual` now parses both the interleaved
  `(P25 -0.8%/P75 +1.2%)` layout the pipeline emits and the paired
  `P25–P75 x%/y%` layout, across any unicode dash. Regression tests use the real
  note prose.
- ~~MAX_WEIGHT truncation silently dropped risk budget~~ — fixed; `sizing.py`
  now solves DESIGN §3 steps 6–7 jointly via `_capped_vol_target`, and reports
  `vol_ex_ante` / `vol_shortfall` / `capped` so a binding cap is visible.

### RESOLVED 2026-08-21 — #3 the regime gate is dead → wired to fragility
Chosen option (a): the risk-off gate now reads the **fragility index**, not the
retired HMM. `rebalance.live_fragility_gate(asof)` fetches ~1y yfinance history
≤ t → `fragility.fragility_index` → a **threshold** gate on the validated
`Elevated` label (`GATE_ELEVATED=0.5`; Normal/Resilient → 1.0), degrading to 1.0
on any missing reading. Injected into `size_positions(..., gate=)` (explicit gate
wins over regime, which stays as the `REGIME_ENABLED=1` revival path). Point-in-
time-safe by construction (unrevised prices, no FRED/ALFRED dep) and directionally
neutral. Recorded in the decision log + report (`gate_info`). DESIGN §3 step 5
amended to name the real input. Live smoke 2026-08-24: composite 24.5 → Normal →
gate 1.0 (correctly ungated in a calm tape). Tests: `test_sizing` gate-override +
`test_rebalance` fragility_gate mapping/degradation/advance.
*Attribution caveat (carry forward):* because fragility can cut gross before
drawdowns, a future "book beat benchmark" is partly the gate's beta-timing, not
pure signal alpha — keep that distinction when reading the §9 quarter result.
