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
> #5b, #1b, #6b) — resolving an item never silently absorbs its cost.

---

## Tooling

### RESOLVED 2026-09-09 — #9 `bump_version.py` cannot find its anchors (pre-existing)
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

Context: the first live rebalance ran 2026-08-24 and produced two fully flat books
out of three. `.macro-assist/portfolio/DESIGN.md` is the contract; §7 mandates a
confirm-on-first-run eyeball, which is what surfaced all of this.

### RESOLVED 2026-08-24 — #6 day-1 NAV comparison is now labelled
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
### DONE 2026-08-24
- ~~Conditional band parser never matched the live note layout~~ — fixed;
  `conditional_sigma_annual` now parses both the interleaved
  `(P25 -0.8%/P75 +1.2%)` layout the pipeline emits and the paired
  `P25–P75 x%/y%` layout, across any unicode dash. Regression tests use the real
  note prose.
- ~~MAX_WEIGHT truncation silently dropped risk budget~~ — fixed; `sizing.py`
  now solves DESIGN §3 steps 6–7 jointly via `_capped_vol_target`, and reports
  `vol_ex_ante` / `vol_shortfall` / `capped` so a binding cap is visible.

### RESOLVED 2026-08-21 — #3 the regime gate is dead → wired to fragility
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
