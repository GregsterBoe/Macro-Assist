# TODO — open decisions & carried-forward findings

Working memory across sessions. Anything here is **known and deliberately not
done yet** — either because it needs a design call rather than a bug fix, or
because it was out of scope for the change that found it.

Conventions:
- **Open decision** = needs a human call; do not "fix" it silently.
- **Carried finding** = agreed problem, just not scheduled yet.
- Cite the file/line and the source (design doc, run, KB entry) so the next
  context can pick it up without re-deriving the analysis.

Last reviewed: 2026-08-24 (TODO sweep — #1/#2/#6 resolved, #4 documented, #5 sharpened).

---

## Phase 20 — paper portfolio

Context: the first live rebalance ran 2026-08-24 and produced two fully flat
books out of three. Root causes below. `.macro-assist/portfolio/DESIGN.md` is
the contract; §7 mandates a confirm-on-first-run eyeball, which is what surfaced
all of this.

### DONE 2026-08-24
- ~~Conditional band parser never matched the live note layout~~ — fixed;
  `conditional_sigma_annual` now parses both the interleaved
  `(P25 -0.8%/P75 +1.2%)` layout the pipeline emits and the paired
  `P25–P75 x%/y%` layout, across any unicode dash. Regression tests use the real
  note prose.
- ~~MAX_WEIGHT truncation silently dropped risk budget~~ — fixed; `sizing.py`
  now solves DESIGN §3 steps 6–7 jointly via `_capped_vol_target`, and reports
  `vol_ex_ante` / `vol_shortfall` / `capped` so a binding cap is visible.

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

---

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
