# TODO — open decisions & carried-forward findings

Working memory across sessions. Anything here is **known and deliberately not
done yet** — either because it needs a design call rather than a bug fix, or
because it was out of scope for the change that found it.

Conventions:
- **Open decision** = needs a human call; do not "fix" it silently.
- **Carried finding** = agreed problem, just not scheduled yet.
- Cite the file/line and the source (design doc, run, KB entry) so the next
  context can pick it up without re-deriving the analysis.

Last reviewed: 2026-08-24 (first live portfolio rebalance).

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

### Open decision #1 — read the conditional table instead of note prose
**Where:** `.macro-assist/portfolio/rebalance.py` — `conditional_sigma_annual`.
**Problem:** the book's risk input is regex-scraped from LLM prose. DESIGN §3
step 3 actually specifies `conditional.lookup_distribution(bucket, a, 5, table)`,
and `.macro-assist/data/conditional_distributions.json` is built and fresh. Prose
scraping is why the market book flatlined on its first live run: a wording change
silently zeroes the book. The parser is now tolerant, but the dependency remains.
**Why not just done:** reading the table needs a *point-in-time bucket* at
rebalance date `t` (`conditional.assign_bucket` on an ALFRED-vintage snapshot →
network + FRED key), which is the same class of dependency as `live_regime`, and
DESIGN §7 forbids look-ahead. Choosing table-vs-prose is a point-in-time fidelity
decision, not a bug fix.
**Options:** (a) table lookup with a PIT snapshot, prose as fallback;
(b) have the pipeline emit a structured band field in the note frontmatter, so
the book reads data rather than prose; (c) keep prose, accept the coupling.
*Lean: (b) — cheapest, keeps point-in-time fidelity by construction.*

### Open decision #2 — the three arms do not run the same sizing rule
**Where:** `.macro-assist/portfolio/rebalance.py:64` `sizing_config_for`.
**Problem:** `kimi` gets `require_distribution=False`; market and exogenous keep
`True`. The exogenous notes carry no conditional band at all (their drivers are
monetary-stance prose), so **the exogenous book is structurally guaranteed to
stay flat forever** under the current gate — confirmed again on 2026-08-24.
This voids DESIGN §6: "whose predictions make money" cannot be measured when
only one arm is permitted to hold anything.
**Options:** (a) a σ source that exists for all three arms (HAR-only, i.e.
`require_distribution=False` everywhere) — uniform rule, weaker abstention;
(b) make the exogenous emitter carry a band; (c) accept it and drop exogenous
from the P&L comparison, documenting why.
*Lean: (a) for rule uniformity, since HAR σ is available for every instrument
and the abstention was meant to catch missing risk data, not missing prose.*

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

### Carried finding #4 — kimi confidence is effectively binary
**Where:** kimi ensemble agreement → `AssetSignal.confidence`.
**Problem:** 12-sample agreement lands on 100% / 92% / 50%; the 50s are Neutral
and abstain, so everything that actually trades carries c ≈ 1.0. DESIGN §3.2
says sizing is where "confidence is made consequential" and where KB-007's
clamped-confidence problem gets attacked — with c pinned at 1.0 that channel
contributes nothing, and (combined with the cap) sizing degenerates to
"max weight or nothing".
**Needs:** either a finer agreement statistic (vote margin, per-sample
probability rather than modal agreement), or accepting that the kimi arm is a
direction-only signal and saying so in DESIGN.
**Watch:** `vol_shortfall` in the weekly reports — if the cap binds every week,
this is confirmed.

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

### Carried finding #6 — day-1 NAV comparisons read as alpha
**Where:** `format_report`, the `Book NAV vs Benchmark NAV` line.
**Problem:** on 2026-08-24 the flat market book showed 100,000.00 vs a benchmark
at 99,877.96 — a +12bp "outperformance" that is entirely the benchmark paying
its entry costs against a book holding nothing. Harmless now, misleading in a
quarterly read.
**Fix when convenient:** suppress or label the comparison until the book has
held a position for a full period, and report excess return only from first
exposure. DESIGN §5 wants information ratio vs buy-and-hold — that series should
start when the book actually takes risk.

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
  cannot be recovered — open decisions #1 and #2 are on that clock.
- Test-fixture discipline: `test_rebalance.py`'s band fixture asserted a note
  layout the pipeline has never emitted, so the suite stayed green while
  production parsed nothing. When a fixture stands in for pipeline output,
  copy a real line out of `results/` rather than composing a plausible one.
