# Macro-Assist — Project Development (the roadmap)

## What this document is

The **roadmap**: phases, work packages, and the reasoning behind the decisions —
including the ones that closed something. It is deliberately *not* the system
reference.

- **How the system works today** — architecture, data sources, the analysis
  pipeline, scoring, workflows, secrets, versioning, maintenance — is
  the [Reference](../reference/index.md) layer, which is kept current with the code.
- **Measured findings** (KB-###, negatives included) are in `knowledge-base.md`.
- **What is running right now** is the board in `active-experiments.md`.
- **Every open decision and carried finding** is in `todo.md`, the single
  inbox; closed ones keep their reasoning in `resolved.md`.
- **Closed phases and superseded detail** are in
  [roadmap-archive.md](roadmap-archive.md).

> **Archived 2026-09-04 — the system-state snapshot that used to open this file.**
> ~390 lines describing the pipeline as it stood around v1.5: the note's
> Bias/Confidence predictions table, the self-calibration feedback loop, the
> pre-`pipeline.yml` workflow schedule, and the portfolio module's build status.
> v1.6 cut the first of those [KB-024] and WP-21.G deleted the second's code, so
> the block described a system that no longer exists — while README.md described
> the one that does. A second, drifting copy of the system description living
> inside the roadmap was the actual defect; it is preserved in the archive as a
> dated snapshot rather than deleted.

## Improvement Roadmap

All phases are implementable at $0 cost using existing API keys (FRED, yfinance) plus one new free provider (Nasdaq Data Link for Phase 3).

### Completed Phases (detail archived)

Phases 1–14 are deployed and stable; their full design notes and Claude Code
prompts now live in [roadmap-archive.md](roadmap-archive.md).
Measured results live in `knowledge-base.md`.

> **Archive-on-completion convention (default editing behaviour).** When a **WP**
> is marked Done *and* its result is recorded in `knowledge-base.md`, trim its
> entry here to a one-line status + verdict + KB pointer (kept inline under its
> phase — the method/harness/reproduce detail is redundant with the KB entry and
> the code). When an **entire phase** closes, move its remaining detail to
> `roadmap-archive.md` and add a row to the table below. **Never trim
> before the result is in the KB** (no information loss), and don't archive
> context a still-open sibling WP depends on.

| Phase | What it added | Status |
|-------|---------------|--------|
| 1 | FRED liquidity series + Net Liquidity | ✅ 2026-04-28 |
| 2 | 90d history + RSI/MA/Z-score technicals | ✅ 2026-04-28 |
| 3 | COT positioning (CFTC) | ✅ 2026-04-28 |
| 4 | System-prompt guardrails + accuracy override | ✅ 2026-04-28 |
| 5 | Window-aware prediction calibration | ✅ Done |
| 6 | Break the Neutral collapse | ✅ Done |
| 7 | Sector Opportunity Research | ✅ Done (7d scoring deferred) |
| MA-0 | Bug fixes (time-travel, leakage, contradiction) | ✅ 2026-05-22 |
| MA-1 | Structured output contract (`schemas.py`) | ✅ 2026-05-24 |
| MA-2 | Analysis / calibration split | ✅ 2026-05-25 |
| MA-3 | Risk agent (Haiku) + Synthesis agent | ✅ 2026-05-26 |
| 8 | Validation infrastructure (backtest harness) | ✅ 2026-05-26 |
| 9 | Volatility forecasting (HAR-RV + VRP) | ✅ 2026-05-26 · ⚠ degenerate as wired — WP-17.5 / KB-033, `todo.md` #17 |
| 10 | Regime classification (HMM) | ✅ 2026-05-26 · ⚠ retired from note — WP-17.4 / KB-006 |
| 11 | Conditional distribution layer | ✅ 2026-05-29 |
| 12 | Quant context integration | ✅ 2026-05-29 |
| 13 | End-to-end validation | ⏸ Backlog (optional) |
| 14 | Production hardening (weekly refit, monitoring) | ✅ 2026-05-29 |
| 17 | Numerical-layer validation — regime cut, conditional input rebuilt, HAR-RV read | ✅ Closed 2026-09-13 — [KB-003]–[KB-006], [KB-028], [KB-033]; detail archived |
| 18 | Input information value — payload screens; the ablation gate closed unrun | ✅ Closed 2026-09-14 at 18.3, negative-by-construction — [KB-009], [KB-010]; `resolved.md` #18; detail archived |
| 16 | Fragility monitor + design-by-emergence prompt levers | ✅ Closed 2026-09-04 — 16.A shipped and alive (→ IMP-4), 16.B/C closed by Phase 21; detail archived |
| 21 | Directional product validation → **the cut (v1.6)** | ✅ Closed 2026-09-04 — [KB-024]. WP-21.E bounded search: family 1 (VIX term structure) resolved **negative** 2026-09-08 → [KB-027]; 2 of 3 families remain, bar for them written 2026-09-13 ([ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)) |
| 22 | Scoring the distribution product | 🟢 Open 2026-09-08 — the scorer follows the v1.6 cut. A/B shipped; the bar is sealed, first read ~2027-05 |
| 23 | Exploration tier — the generation side of the method | 🔍 Open 2026-09-13 — harness built, two explore looks run 2026-09-14; seal decided (`SEAL_START` reused); next is the owner's rewrites, then the WP-23.B class bar |
| 24 | Record integrity & session continuity | 🟡 In progress 2026-09-14 — `record_audit.py` in CI: 24.A/B (workflow orphans, artifact liveness) since 2026-09-14, 24.C/D/E (referential integrity, contradictions, ages) since 2026-09-21; next 24.F revisit conditions. This row said ⏸ Draft for a week after the board went Active — 24.D's first red |

The v1.5 **system-state snapshot** that used to open this file was archived on the
same pass; `README.md` is the maintained system reference.

---

### Phase 15 — Optional Extensions *(Backlog — only after 8-14 are deployed and validated)*

Not on critical path. Listed for future planning.

| Extension | Description | Trigger |
|-----------|-------------|---------|
| Cross-asset correlation regime | Detect when SP500-gold, SP500-10Y, or SP500-DXY correlations break vs 60d baseline. Inject as `## Correlation Regime` block. | After 8-14 deployed; useful when conditional distributions show low n |
| Event-window prediction | Restrict prediction to FOMC/CPI/NFP windows; use higher-confidence framework only on event days. | Requires Phase 5 (window-aware calibration) first |
| Sentence-transformer embeddings on news | Use FinBERT or sentence-transformers to extract daily news sentiment vector from GDELT / Reddit. Inject as additional regime feature. | After regime classifier is validated |
| Sector rotation conditional probs | Conditional distribution layer applied to sector ETF relative performance, not absolute returns. | After 7d sector ETF scoring is implemented |
| Bayesian confidence calibration | Replace point-confidence with Beta-distributed posterior; track calibration via reliability diagrams. | After 12 months of scored predictions |

---

> **Execution-order table + implementation notes for Phases 1–15** moved to [roadmap-archive.md](roadmap-archive.md).


## Experimental Track — Emergence & Fragility (Phase 16) ✅ CLOSED

*Detail archived 2026-09-04 → [roadmap-archive.md](roadmap-archive.md).*

Two bets: measure the system **losing resilience** instead of predicting the
trigger (WP-16.A), and stop legislating model behaviour with hand-coded prompt
rules (WP-16.B/C). They ended in opposite places, and that contrast is the
phase's real result.

| WP | Verdict |
|---|---|
| **16.A — Fragility monitor** | ✅ **Shipped, and the only part still alive.** `fragility.py` → a composite index whose weights and thresholds were calibrated on a de-overlapped backtest [KB-001]/[KB-002], shadow-wired behind `FRAGILITY_MODE`. Its descendant is IMP-4's OR-of-channels flag [KB-016/017/020/021], now at `show` and the note's headline risk block. |
| **16.B — Loosen control** | ❌ **Closed by Phase 21.** B.2 built the Brier/BSS/ECE metric [KB-007] — the north star everything since is judged on, and the phase's most durable output. B.1 and B.4 shipped inside the loosened bundle, whose A/B turned out unreadable [KB-023] and is moot after [KB-024]. B.3 (emergent signal weights) is **superseded**: it would weight signals for a directional call that no longer exists. |
| **16.C — Research-grounded levers** | C.3 (base-rate-first) and C.4 (Brier as north star) ✅ shipped. C.1 (ensembling) ran as the Kimi arm and was stood down in WP-21.F. C.2 (analog retrieval) **superseded** — same reason as B.3. |

**The live remnant is the fragility shadow clock** (`FRAGILITY_MODE=log`), which
waits on exactly one thing: a live `Elevated` episode. Current status is on the
board in `active-experiments.md`.

**Worth remembering the phase for the method, not the levers.** Fragility earned
its place through a look-ahead-safe backtest *before* anyone trusted it, and that
discipline — pre-commit the gate, de-overlap the sample, write the KB entry
whichever way it goes — is what Phases 17, 19 and 21 all ran on afterwards.


---

## Numerical-Layer Validation & Rigor (Phase 17) ✅ CLOSED 2026-09-13

*Detail archived 2026-09-13 → [roadmap-archive.md](roadmap-archive.md).*

The fragility index had earned its place through a look-ahead-safe backtest
(Phase 16.A); nothing else in the numerical layer had. Phase 17 applied the same
discipline to each layer in turn — pure-numerical, zero LLM cost — and every one
of the three came back with a finding that changed the product.

| WP | Verdict |
|---|---|
| **17.1 — Regime look-ahead audit** | ✅ → [KB-003]. Live labelling safe; validation must be walk-forward. Caught a shipped bug: the credit feature was a 3-year FRED series, training truncated to 2y → switched to `BAA10Y`. |
| **17.2 — Regime skill gate** | ✅ NO SKILL → [KB-004]. Risk-Off→drawdown AUC ~0.47–0.49 as wired. |
| **17.3 — Inference vs concept** | ✅ INFERENCE was the bug → [KB-005]. Sequence inference lifts AUC to 0.55–0.65; concept salvageable but modest. |
| **17.3b — Fix live inference** | ❌ cancelled → [KB-006]; no point fixing a layer 17.4 then dropped. |
| **17.4 — Incremental value over a simple bucket** | ✅ REDUNDANT → [KB-006]. A 4-feature rule beats the HMM (0.697 vs 0.553); regime removed from the note ([ADR-0004](../decisions/ADR-0004-retire-hmm-from-the-note.md)). |
| **17.5a — Conditional table's input** | ✅ → [KB-028], shipped v2.1. The table was ~3 years of one regime and two of three dimensions contributed nothing; rebuilt from 2000-08 on BAA10Y. |
| **17.5b — HAR-RV walk-forward read** | ✅ DEGENERATE as wired → [KB-033]. A 4-parameter OLS on ~50–70 rows; zero forecasts published on 9 % / 13 % of S&P / Bitcoin dates; `skill` at 1000 days → the fetch is the defect → fixed 2026-09-13, `resolved.md` #17 (5y fetch, 1000-return floor, zero = no forecast). |

**The phase's recurring finding is the same one three times** ([KB-033] nuance
(c)): the history a component was fit on was whatever the fetch returned, never a
number the method asked for. What is still live from the phase: `BAA10Y` as the
credit input everywhere, the v2.1 conditional table, `regime_backtest.py` /
`har_backtest.py` as the harnesses, and the HAR fit window the phase's last
finding corrected (`resolved.md` #17; `vol_forecast.HAR_MIN_RETURNS`).

---

## Input Information Value & Prompt Economy (Phase 18) ✅ CLOSED 2026-09-14 — at 18.3, negative-by-construction

*Detail archived 2026-09-14 → [roadmap-archive.md](roadmap-archive.md);
decision in [`resolved.md`](resolved.md) #18.*

Phase 17's discipline pointed at the LLM input payload: does each section earn
its place? The cheap screens ran; the paid decision gate never could.

| WP | Verdict |
|---|---|
| **18.1 — Payload observability** | ✅ `MACRO_PREVIEW=1` → `results/llm_payload_preview/<date>.md`. |
| **18.2 — Cheap input-quality proxies** | ✅ → [KB-009]. The daily market/sector block is highly collinear; the FRED series carry the orthogonal information. A screen, not a verdict. |
| **18.3 — Citation screen** | ✅ → [KB-010]. Citation and redundancy nearly anti-correlated; the ablation queue was the union of the two screens. |
| **18.4 — Outcome-grounded ablation** | ❌ closed unrun. Its metric was Brier on the LLM's directional calls ([KB-007]); v1.6 cut those calls ([KB-024], [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md)) and the payload cannot move the Python-rendered distribution that replaced them. An ablation with no scored output is the unfalsifiable experiment the phase's own hard gate forbade. |
| **18.5 — Feed results into weighting** | ❌ closed with 18.4; WP-16.B.3, its consumer, closed with Phase 21. |

**What survives:** the two screens as the payload's documented redundancy, and
`input_ledger.py` / `citation_screen.py` as instruments. Nothing was pruned on
cost alone. Re-opens only through `todo.md` #7 — a scored Target Range would be
an outcome metric for the model's prose, and 18.4 could be re-pointed at it.

---

## Exogenous Information Engine (Phase 19) — *second prediction branch: real-world information, market-data-light*

**Premise.** Phases 1–18 predict the market by analysing *market* data (prices, vol, positioning) plus some real-world economic data (FRED). This phase opens a **parallel second branch**: predict/condition the market from **independent real-world information with minimal or no market data**, via a scalable, structured framework that compacts many information streams into a bounded payload — *not* a context dump into an LLM. Branch topology is deliberate: it is developed and judged independently and only ever *competes with* the market-only pipeline on the shared scoreboard.

**Honest framing — read before building (the reframe that makes this not-stupid).** The literal goal "reason over public information to call market direction" is a losing game: public information is already priced, we have no latency or proprietary-data edge, and KB-007 shows the existing system's decisive directional calls are already *below chance* — bolting a noisier, harder-to-calibrate input stream onto a system that cannot calibrate its current inputs adds variance, not signal. The naive "dump lots of context and hope" version is the stupid version and is explicitly out of scope. **The target is therefore reframed** from directional prediction to the places where structured real-world reasoning genuinely has edge *and* where being wrong is cheap:
- **Expectations gaps** — markets move on *surprise* (reality vs consensus), not on facts. Real-world info measures the "reality" side; the gap vs consensus is the tradeable part.
- **Regime & tail-risk conditioning** — what world are we in, the outcome distribution, what is building in the tails. Feeds the *risk* layer, not a directional call.
- **Causal transmission / scenario mapping** — "if X happens, here is the mechanism and the exposed assets." Decision-support, which LLMs are genuinely strong at.
- **Slow-fundamental nowcasting & cross-sectional / relative reads** — aggregate many weak leading signals to slightly lead official data, or rank sectors, where mispricings persist longer than at the index level.

The output of this branch is therefore **context — expectations-gaps, regime/tail reads, scenario→exposure maps — plus at most an optional *scored lean*; never a levered index-level directional bet.** If the target ever drifts back to "call SPX direction from the news," stop.

**The one source-selection principle.** The existing system's honest limitation (see the Phase-16 strategic-context note) is that it *reacts* because its inputs are coincident/lagging. **A real-world source earns a place only if it is *leading* or carries *expectations-divergence*.** "More context" is never a reason to add a source; "this leads price, or measures a consensus gap" is. Note the system already ingests non-market information (FRED = real-world economics, COT positioning, YouTube analyst transcripts), so this phase *systematises and expands the non-market side with a real framework* — it is not from scratch.

**Hard gate (inherited from Phases 16–18).** Every branch is judged by the **same Brier / commitment discipline** (WP-16.B.2 + the KB-011 commitment metric) and **A/B'd against the market-only arm** via the existing `profile` / run-config machinery. A branch that does not beat market-only on the scoreboard is unfalsifiable complexity and is cut. Standing rules carry over: **cheap screens before expensive LLM calls; one branch at a time; point-in-time discipline on every backtest** (no look-ahead — the Phase-17 rigor applies double to real-world *text*, which is easy to leak future knowledge into).

**The source taxonomy and the L0–L4 compaction architecture** — the map-reduce
evidence pipeline with a fixed contract at every level and a per-branch token
budget, so branches scale without blowing the payload — are archived in
[roadmap-archive.md](roadmap-archive.md). The built slice follows them;
`exogenous/DESIGN.md` is the live contract.

**Work packages / roadmap (cheap-first; do NOT build the framework before proving one slice):**
1. **WP-19.A — Reframe & target lock (design only) ✅** *(2026-07-14 → `exogenous/DESIGN.md`)*. Locked the first slice (monetary / rates-expectations), the three data contracts (L1 `Evidence` → L2 bounded `BranchBrief` → L3 `ExoOutput`), and the go/no-go bar. Two honest constraints are baked in: consensus must be **survey**-derived, not fed-funds-futures (market-derived), or the A/B is contaminated; and LLMs cannot be cleanly backtested on dated public text they were trained on, so **validation is forward-only**. Detail → [roadmap-archive.md](roadmap-archive.md).
2. **WP-19.B — One vertical slice (L0→L4, monetary/rates) ✅ DONE + INTEGRATED** *(2026-07-24, on `main`)*. SPF+SEP consensus → Haiku FOMC extractor → Opus bounded brief → arm-tagged `ExoOutput` → arm-keyed scoring, ~119 tests, leakage-free early tell. Build detail → [roadmap-archive.md](roadmap-archive.md); `exogenous/DESIGN.md` is the contract.
3. **WP-19.C — Generalise the branch contract.** Only after B works, extract the L0–L2 skeleton + brief schema so branch #2/#3 are cheap to add and the payload stays bounded.
4. **WP-19.D — Add branches by measured value.** One at a time, each gated on "does it improve the scored output vs without it" (Phase-18 ablation discipline). Prune losers immediately.
5. **WP-19.E — Integrate or kill. ✅ RESOLVED (2026-09-07) — the anchor does not carry direction [KB-026].** This closes Phase 19's **directional** route. Route (b) — re-cutting the branch's output to the expectations gap — is untested and unaffected; the scope of the null matters more than the verdict, and it is set out in the WP-19.E section below.

**Kill criteria (pre-committed).** Cut the whole branch if, after 2–3 branches, it does not beat market-only on Brier/commitment. Watch-items: cost blow-up (mitigate via cheap extraction, caching, cadence-appropriate refresh — policy monthly, news daily); alt-data access/reliability (start free/scrapeable, treat paid feeds as later bets gated on the free ones); look-ahead bias in text backtests (point-in-time from day one).

**Integration status.** Integrated on `main` 2026-07-24 as a modular, removable
directory (`exogenous/`) with its own workflow and two inert hooks; **soft-killed
2026-09-04** (WP-21.F): `exo_weekly_emit.yml` is `workflow_dispatch`-only and the
emission stage is out of `pipeline.yml`, nothing deleted. Kill procedure is
DESIGN §9. The isolation guarantees and the original "runs autonomously" block
→ [roadmap-archive.md](roadmap-archive.md).

---

### WP-19.E — The anchor, scored in the numeric harness ✅ RESOLVED negative *(2026-09-07)*

**Why the work package changed shape.** As written, WP-19.E A/B'd the exogenous
arm against market-only on Brier/commitment. v1.6 cut market-only's directional
calls [KB-024], so the comparator froze and the gate became **unreadable** rather
than failed. WP-21.F named two ways back; this is **(a)** — re-point the gate at
the WP-21.A benchmark, which [KB-024] shows is a genuinely hard bar.

**Both pre-registered questions close negative → [KB-026].** On the same 75,450
calls: `exogenous_spf` (SPF consensus only) scores 0.561 / BSS −0.030 / ECE 0.078
and loses to the constant `always_bullish` on Brier, BSS and ECE. `market_plus_exo`
is *worse than the panel it was added to* — BSS −0.087 → −0.124, ECE 0.118 → 0.141
— while getting a third more decisive. The anchor is **not** inverted (bear−bull
−0.038, CI [−0.135, +0.056]), so it does not replicate [KB-024]'s mechanism; it
dissolves it. On the per-input read: `spf_policy_path`, the branch's actual thesis
column, carries the highest sign stability of the seven (0.952) and a permutation
drop of −0.001.

**The scope of that null — route (b) still depends on this.** It scored the
branch's **deterministic, point-in-time half only**. The SEP dot plot was excluded
(FRED serves only the *current* vintage of a path every SEP release rewrites) and
the L1/L2 LLM layers were excluded (trained on the dated FOMC text they would
read). So the null closes **the SPF anchor as a directional input** and leaves the
**expectations-gap mechanism untested** — the SPF-vs-SEP divergence and FOMC
communication drifting from a fixed anchor are both live-only signals this harness
cannot reach.

**One void run, worth remembering.** The 2026-09-05 attempt was void [KB-025]: the
workflow built its CLI flag with `${{ inputs.exogenous && '' || '--no-exogenous' }}`,
which returns the fallback whenever the truthy branch is an empty string, so every
dispatch passed `--no-exogenous` and a valid **market-only** report went out under
a WP-19.E heading. A market-only table is a valid report, which is why it went
unnoticed for two days. `--require-exogenous` now turns that into a failed run.

Harness design, the seven features, the pre-registered read and reproduce
instructions → [roadmap-archive.md](roadmap-archive.md).

---

## Self-Managed Paper Portfolio (Phase 20) — *the integrated, unfakeable scoreboard*

**Premise.** Every phase to date scores the system on **Brier / commitment** at T+5/10/20. That is a calibration metric, and calibration is not money: a system can be beautifully calibrated and still unprofitable (good calibration + poor *discrimination*, or real edge smaller than costs, both score fine on Brier and lose money live). This phase adds the one metric that cannot be faked — **risk-adjusted P&L of an autonomous virtual book, forward-tested against a benchmark.** The book *consumes the dated predictions the pipeline already emits* and converts them into sized positions; whether NAV beats the benchmark is the honest answer to "does the accumulated data have edge in real time?"

**Honest framing — read before building (the reframe that keeps this rigorous).**
- **A portfolio does not escape the prediction problem — it *contains* it.** A portfolio is a function from beliefs to positions; it adds sizing, cost, and risk *on top of* the signal. If the signal has no edge, no construction rescues it. The value here is not an "easier" problem, it is a **strictly more honest measurement** that surfaces edge-vs-cost, which Brier structurally cannot.
- **Two separable experiments live inside "let the model manage a portfolio," and conflating them poisons attribution:**
  1. **Does the signal have edge?** → test with a **fixed, mechanical belief→weight rule.** Clean: a bad month is a bad signal, not a bad judgment call.
  2. **Can the LLM make good discretionary allocation calls?** → adds a second layer of LLM noise on top of the signal.
  **v1 is experiment #1 ONLY** — mechanical sizing, zero discretionary LLM trading. We are testing the *signal*, not a new agent. Loosening toward #2 is deferred and belongs to the Phase-16 "loosen control" track, not here.
- **Forward paper-trade; do NOT build a backtest optimizer.** The system's own honest limitation (it *reacts* — coincident/lagging inputs) is exactly what a tuned backtest hides and a live forward-test exposes. A backtest is permitted only as **pipeline shakedown** (à la Phase 19), never as a scored result. Point-in-time discipline (Phase 17) applies.
- **No benchmark ⇒ the number is vanity.** P&L is meaningless without a comparator. Benchmarks: **buy-and-hold ACWI** (which is literally the user's real-world TR core — apples-to-apples) and **60/40**. Report *excess* return and information ratio, not raw NAV.
- **"Some risk to it" = an explicit risk budget, not vibes.** A **volatility target** sets the risk level deliberately; position sizing expresses confidence honestly (size *is* confidence made consequential — directly attacks the clamped-confidence problem, KB-007).

**Design detail** — the one-book-per-arm reuse of the arm machinery, the
mechanical v1 architecture sketch, the universe correction (the book trades what
the pipeline *predicts*, not the TR sleeves) and the sizing-input argument — is
in `portfolio/DESIGN.md` (the live contract) and, as first written,
[roadmap-archive.md](roadmap-archive.md).

**Work packages (cheap-first; prove the slice before generalising).**
1. **WP-20.A — Design & scope lock ✅** (2026-08-19 → `portfolio/DESIGN.md`): vol-target inverse-vol sizing (Kelly rejected), v1 universe {S&P 500, Gold, Bitcoin, 10Y-via-IEF} in USD, seven-step rule, benchmarks.
2. **WP-20.B — The book ✅** (2026-08-19 → `portfolio/book.py`, 13 tests): instrument-agnostic sleeve-tagged ledger, bps cost model, decision log.
3. **WP-20.C — Sizing rule ✅** (2026-08-19 → `portfolio/sizing.py`, 17 tests): the DESIGN §3 rule as a pure function of extracted numbers; regime gate folded into the vol target; `MAX_WEIGHT` 0.35 / `GROSS_CAP` 1.5.
4. **WP-20.D — Weekly driver ✅** (2026-08-19 → `portfolio/rebalance.py`, 10 tests; `portfolio_rebalance.yml` Mon 07:45 UTC): note → signals → sizing → ledger + equal-vol benchmark; HAR-RV σ recomputed point-in-time. Go/no-go after ≈ 1 quarter: any arm's book beats the buy-and-hold basket on information ratio?
5. **WP-20.E — Live broker integration ⏸ DEFERRED**, gated on 20.D showing edge (IBKR, paper-first; research in the archive).

**Kill criteria (pre-committed).** v1 is measurement on a virtual book → near-zero risk; the failure mode is *building without a benchmark* or *tuning a backtest*, both explicitly out of scope. Cut the phase if, after ~1–2 quarters forward, **no arm's book beats buy-and-hold ACWI on risk-adjusted return.** A calibrated-but-unprofitable result is itself a valuable KB finding (it would confirm edge < costs). Modular/removable like Phase 19: one `portfolio/` directory + one workflow + a ledger file; the prediction pipeline is untouched.


**Status (board wins):** dormant since v1.6 — the sizer's input (bias +
confidence) was withdrawn with the cut, so `rebalance.run()` declines to advance
the books and says why; left scheduled so the stopped input stays visible. A v2
that sizes off the conditional distribution needs its own pre-registered test.
The Kimi ensemble arm that fed the `confidence` scalar was deactivated 2026-09-04
(`kimi_arm.py` stays, stage removed). The HAR-RV σ every position is sized off
was measured degenerate at the 130-day window → [KB-033]; `fetch_prices_and_har`
now fits on 1600 calendar days and a gated forecast falls back to the
conditional σ (`resolved.md` #17, 2026-09-13; inert while the sizer is dormant,
so no ledger before/after to record). Kimi-arm write-up,
broker research and the branch strategy → [roadmap-archive.md](roadmap-archive.md).
---

## Directional Product Validation (Phase 21) — *is this task learnable at all?* ✅ COMPLETE

> **Resolved 2026-09-04 — the answer is no, and the directional product is cut.**
> [KB-024]: neither a ridge nor a GBM beats a constant `always_bullish` on this
> payload, and both invert exactly the way the LLM does. WP-21.A ✅ ·
> WP-21.B ❌ superseded · WP-21.C ❌ closed · **WP-21.D → cut, shipped as v1.6** ·
> **WP-21.E family 1 ❌ negative** (VIX term structure, 2026-09-08 → [KB-027]:
> the arm is the drift benchmark, adding it to the panel makes the panel worse,
> and the mechanism is [KB-024]'s inversion through a new instrument. It also
> exposed a defect in the pre-committed bar — see the WP below. 2 of 3 families
> remain, against the bar in [ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)) · WP-21.F ✅ both remaining directional arms stood down ·
> WP-21.G ✅ scoring loop wound down. The WP-21.A–D table below carries the
> verdicts, including what replaced the two cut columns.

**Why this phase exists.** After 128 scored reports, three independent metrics
say the directional product does not work: decisive accuracy ~36% [KB-007],
BSS < 0 at every horizon [KB-007], and an *inverted* bias/return separation
[KB-022]. The one result that looked like a repair — the loosened arm's
apparently-fixed separation — turned out to be perfectly confounded with the
market period [KB-023]. Meanwhile the numeric track *does* work: the OR-of-
channels flag roughly doubles crisis recall and survived leave-one-crisis-out CV
[KB-015/016/017], reproduced on the live feed [KB-020/021].

That asymmetry has been read so far as "the prompt needs another lever." Phase 21
tests the rival hypothesis that has never been tested: **that 5/10/20-day
direction on liquid macro assets is close to unlearnable from this payload by
*any* model**, and that the LLM is being blamed for the task's difficulty. Every
work package below is chosen so that a negative result is as informative as a
positive one.

### Why not a neural network

Decided 2026-09-03 and written up once so it is not re-litigated →
**[ADR-0008 — No neural network](../decisions/ADR-0008-no-neural-network.md)**.

The instinct behind the proposal is right — this *is* a weighting problem and an
LLM is structurally a poor weigher. The remedy does not scale, for reasons the
ADR sets out: effective sample size is ~150 non-overlapping 20-day windows across
roughly 3 independent assets, and [KB-009] found only ~3 orthogonal factors in the
payload. A more expressive model is reconsidered **only if** WP-21.A shows an edge
to be expressive about. It did not — [KB-024].

### WP-21.A–D — the learnability test, and the cut *(detail archived 2026-09-04)*

Method, full numbers and the kill-criterion reasoning →
[roadmap-archive.md](roadmap-archive.md). The measured
result is **[KB-024]**.

| WP | What it did | Verdict |
|---|---|---|
| **21.A** | Ridge + a shallow GBM, walk-forward on unrevised inputs, `horizon+1` embargo, planted-signal positive control, scored by the production readers against a bar committed in advance | ✅ run → **[KB-024]**: both lose to a constant `always_bullish` on hit-rate, Brier, BSS *and* calibration at once, and invert on separation the same way the LLM does |
| **21.A.2** | Sample alignment — the comparators had been scored on 78,656 calls to the models' 75,414 | ✅ fixed; `always_bullish` moved 0.560 → 0.557 and neither model moved to three decimals — **the direction of the result never depended on it** |
| **21.B** | Day-alternating arm A/B | ❌ closed, superseded by A. B.1's arm-scoped reader fixes ✅ kept — they read the history |
| **21.C** | Conditional base rates *into* the prompt | ❌ closed, and **inverted**: the base rate became the published product rather than an input the model overwrites |
| **21.D** | The kill criterion, read | ✅ **CUT, shipped as v1.6.** `Bias` and `Confidence` are gone from the note; the conditional distribution already sitting underneath each call (median, P25/P75, n) is published in their place, rendered by Python. `Primary Driver` and `Target Range` stay. `score_predictions.py` gates on version, so v1.5-and-earlier history stays scoreable and [KB-007]/[KB-011]/[KB-022] stay reproducible |

**The harness outlived the phase.** `numeric_baseline.py` is now the repo's
general answer to "is there directional signal in these inputs?": WP-19.E added
the Phase-19 exogenous anchor to it as two more arms (2026-09-04), and WP-21.E's
indicator search now runs through the same door (2026-09-07, two more arms and a
sealed-holdout scope). Four things must not drift — the pre-committed bar, the
shared call set, the rule that an input has to be unrevised to enter the panel at
all, and now the seal date. Every optional family also arrives with its own
`--require-<family>` flag, because a run that quietly drops the thing it was
dispatched to test publishes a valid report answering a different question
[KB-025].

### WP-21.E — Bounded, pre-registered indicator search *(family 1 ✅ RESOLVED 2026-09-08 — negative, and it found a defect in the bar → [KB-027]. Two families remain; their bar is [ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md), written 2026-09-13.)*

The honest way back in. [KB-024] closes "this payload, these model classes" — it
does not close "no feature family predicts direction." So the search is allowed,
but on three conditions, written down before it starts:

1. **It does not gate the cut.** The cut is justified by evidence in hand; a
   search can only ever *add* something back later. Running them in the other
   order means publishing anti-informative calls for however many months the
   search takes, in exchange for a result the honest prior says comes back
   negative.
2. **It is capped.** Three feature families, maximum. **VIX term structure
   first** — it is nearly free given the panel `numeric_baseline.py` already
   builds, and `vix_term` is the strongest single fragility component
   ([KB-001], AUC 0.77/0.67) that has never been tested for *direction*.
3. **The bar is the one already written.** For family 1 that was WP-21.A's
   `verdict()` clause (n ≥ 30 decisive, hit-rate > 0.52, and BSS > 0 or an
   `aligned` ordering). **For families 2 and 3 it is
   [ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)**,
   written 2026-09-13 with no candidate chosen: n ≥ 30, hit-rate > 0.52, no
   `inverted` ordering, **BSS > 0.02 and the BSS block-bootstrap interval clear
   of zero**; `aligned` no longer substitutes for calibration. Either way, on
   **sealed holdout data** — a slice held out before the family is chosen, not
   after. Clearing it on the training panel is not a result.

If a family clears that bar, the column comes back — with the conditional
distribution published underneath it. If none does, WP-21.E is a KB negative and
the search closes for good.

#### Family 1 — result: negative, twice over → [KB-027]

Run 2026-09-08 on the sealed slice: `vix_term`'s whole margin over
`always_bullish` is +0.006 on hit-rate and it is 0.009 *behind* the constant on
the explore slice; `market_plus_vixterm` is worse than `ridge` on every metric
while being more decisive. The mechanism is [KB-024]'s inversion through a new
instrument. **And the bar was wrong:** `verdict()` returned `edge` because its
`BSS > 0 OR aligned` disjunct never consulted the `inverted` ordering; the
pre-registration had said an inversion is not a pass, so the function was
corrected to disqualify first — a defect fix, not a goalpost move. The floor
itself was settled afterwards, with no candidate in view →
[ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)
(`EDGE_MIN_BSS = 0.02` and the interval must clear zero). Scope: closes the
term structure as a *directional* input only; [KB-001]'s stress read stands.
Full result text → [roadmap-archive.md](roadmap-archive.md).

#### The seal — how condition 3 is actually enforced

`SEAL_START = 2018-01-01`, a constant in `numeric_baseline.py`, committed before
the family was fitted. Calls dated on or after it are the **sealed holdout**;
earlier calls are the **explore** slice.

- **`verdict()` is read on the sealed slice only.** The report renders it as the
  leading table, labelled as the bar; the explore table renders `_not the bar_`
  in place of every verdict, because that slice is the surface a family is
  allowed to be shaped against and a verdict there is circular by construction.
- **Why 2018.** A term-structure family is a stress instrument, so a holdout
  containing no stress episode could not falsify it in either direction. From
  2018 the sealed slice spans February 2018, Q4 2018, the 2020 crash, the 2022
  bear market and the recovery — five regimes, not one long tape. Calls begin
  ~2009 once the lookbacks and `min_train` are paid, so the split is roughly even
  and the explore surface stays usable.
- **A calendar date, not a fraction of the panel**, so it does not move when the
  panel is rebuilt a day later. Families 2 and 3 face the same holdout family 1
  faced, which is the only way three families are comparable to each other.
- The workflow pins `--seal-start` explicitly, so the boundary a verdict was read
  on is in the run's own log and not only in whichever revision of the source
  happened to be checked out.
- **Multiplicity is a stated cost, not a solved problem.** Three families share
  one sealed slice, so a single family clearing 0.52 once is worth roughly a
  third of what it looks like. The cap of three is what bounds it. This is on the
  report, not just here.

**Where:** `.macro-assist/numeric_baseline.py` (`vix_term_features`, `SEAL_START`,
`split_reports_by_seal`) · `.github/workflows/numeric_baseline.yml` · tests
section 9. Family 1's build detail and its pre-registered read →
[roadmap-archive.md](roadmap-archive.md).

### Phase 21 — execution order and wind-down ✅ *(complete; detail archived)*

A → D ran in that order and closed the phase. Two follow-ons shipped with it:
**WP-21.F** (re-pointing the exogenous gate, → WP-19.E above) and **WP-21.G**
(deleting the self-calibration loop the cut had orphaned). Execution order, the
`LAST_DIRECTIONAL_VERSION` reasoning, and why the Phase-20 stage is deliberately
left running against a withdrawn input → [roadmap-archive.md](roadmap-archive.md).

---

## Scoring the Distribution Product (Phase 22) — *the scorer follows the product*

**Why it exists.** v1.6 cut the directional call and published the empirical
conditional distribution in its place (WP-21.D, [KB-024]). `score_predictions.py`
scored the thing that was cut: it gates on `has_directional_calls()` and returns
`None` for every v1.6+ note, so from 2026-09-05 the pipeline has been publishing a
product **no scorer measures**. That is the gap this phase closes. It is not a new
experiment — it is the feedback loop catching up with the note.

**What is in scope, and what deliberately is not.** The note now carries four
falsifiable things: the conditional distribution, the LLM's Target Range, the
Fragility Monitor, and (logged, unpublished) the HAR-RV vol forecast. This phase
scores **the conditional distribution only**. The other three are named here so
the omission is a decision rather than an oversight: Target Range needs a
pre-registered nominal coverage and a path-vs-endpoint call it does not have yet
(the prompt says "where the asset can reasonably trade", which is the path, not
the T+5 close); the fragility forward record is IMP-4's clock, not this one; the
vol forecast is WP-17.5.

### WP-22.A — Six assets in the table ✅ *(2026-09-08)*

The universe went **3 → 6**. The note had been publishing `— no conditional base
rate` for the 10Y, DXY and Bitcoin, with prose calling it "thin-data terrain" —
which was not true: `refit_models._ASSETS` simply had three tickers in it. The gap
was build-side. Shipped with `assets.py`, the canonical registry that made the
same mistake impossible to repeat →
[ADR-0011](../decisions/ADR-0011-canonical-asset-registry.md).

*Reading the first months:* the three new assets carry no forward record until a
weekly refit rebuilds the table, so their record starts ~5 months after the
original three. `dist_scores_summary.json` reports `record_start_by_asset` rather
than pooling the two.

### WP-22.B — The distribution scorer ✅ *(2026-09-08)*

`.macro-assist/score_distributions.py`, the successor to `score_predictions.py`:
pinball loss at q25/50/75, IQR coverage, a 4-bin PIT, above-median sign, and
block-bootstrap CIs on 21-date blocks, wired as its own step in
`macro_weekly_scoring.yml`. **The benchmark is the test** — `unconditional`, the
same asset's full-history quantiles with no macro bucket. [KB-024]/[KB-026]/[KB-027]
each found a product scoring as skilled until a trivial rival was put next to it;
if conditioning cannot beat this, the bucket layer is decoration. Also
`trailing_250` and `har_gaussian`.

How the scorer behaves today, including the controls and the units-do-not-pool
rule → [Scoring](../reference/scoring.md). Build detail →
[roadmap-archive.md](roadmap-archive.md).

### WP-22.C — The pre-registered bar *(written 2026-09-08, sealed; first read ~2027-05)*

**The record splits in two, and the split is not a choice.** p25/p75 only entered
the quant log on **2026-09-07** — before that only `p50` was written, because
before v1.6 the distribution was a log record rather than the published product.
So:

- **the median-only backfill** (2026-05-29 → 2026-08-28, 210 obs at t5 across 4
  blocks) was computed *before* this bar was written. It is **exploratory** and
  can never return a `pass` verdict — `verdict(sealed=False)` returns
  `exploratory` and nothing else.
- **the interval record** — the actual published claim — had **zero resolved
  observations** when the bar was written. `SEAL_START = 2026-09-07`. That is the
  only window in which this could honestly be pre-registered, and it is why the
  bar exists now rather than after the first read.

**Pre-registered questions.** (1) Is the published P25–P75 interval calibrated —
does the coverage CI contain 0.50? (2) Does conditioning beat not conditioning on
pinball loss?

**Disqualifiers, evaluated FIRST and each returning its own verdict.** This
structure is [KB-027] applied literally. That finding was that a pre-committed
`verdict()` printed `edge` for an arm its own pre-registration had disqualified,
because the pass clause was reachable without the disqualifier ever being
consulted. So: `underpowered` (< 8 independent blocks, or no resolved interval
claims) → `miscalibrated` (coverage CI excludes 0.50 — a miscalibrated interval is
not an edge whatever its pinball loss says) → `inverted` (skill CI entirely below
zero: conditioning is reliably *worse* than not conditioning, which is a finding,
not merely an absent edge). Only then is the pass clause reachable. A test asserts
each disqualifier fires ahead of a strong skill number.

**`MIN_SKILL = 0.02`, not zero — and this settles in advance the decision WP-21.E
left open.** [KB-027] recorded that a floor of literally zero is not a skill
threshold, and that raising `EDGE_MIN_BSS` *after* seeing +0.003 would be a
goalpost move. The same question arises here, and the difference is timing: this
margin is set before any interval observation exists. A test pins that a skill of
+0.003 with a zero-excluding CI reads `no_edge`.

**`MIN_BLOCKS = 8`** ≈ 168 report dates ≈ 8 months of daily notes, putting the
earliest possible sealed read around **2027-05**. This is a slow instrument by
construction and should not be read early; [KB-023] is the standing reminder that
a wide interval means "cannot see", not "nothing there".

**What the skill number *is* — amended 2026-09-08, same day, sealed record still
empty.** As first written the bar read `skill_vs_unconditional["published"]` on
the multi-asset slice: a ratio of mean pinball losses **pooled across assets**.
That was safe only while every asset was percent-scale. WP-22.A takes the
universe to six on the 2026-09-13 refit, and the 10Y is scored in **basis
points**, where a typical loss is ~50x an equity's — so the pooled ratio would
have been carried almost entirely by the 10Y in both numerator and denominator,
and the product's headline skill would in fact have been a 10Y skill score. A
test states that failure directly: on a synthetic universe where three percent
assets each beat the benchmark by +0.10 and the 10Y loses by −0.10, the naive
pooled ratio reads **−0.089**.

The bar now reads `pooled_skill`: skill computed *within* each asset, where it is
unit-free, then averaged **equally across assets**. Equal weighting is what stops
the longest record speaking for the product — but on its own it creates the
mirror failure, an asset five report dates old voting as loudly as one with a
year. Hence **`MIN_POOL_BLOCKS = 2`**: below two blocks an asset has no bootstrap
CI at all, so it is held out of the pool and *named* in the report's `excluded`
map rather than silently dropped. The qualifying set is fixed once on the real
sample; the bootstrap re-pools exactly those assets, because a resample's own
block structure is degenerate and must not re-decide who is in the pool.

The headline the verdict is applied to is pooled over the **stable universe**
(`assets.ORIGINAL_KEYS` — SP500, Gold, WTI Oil): the three assets this seal was
written over, before the 10Y/DXY/Bitcoin rows existed. The six-asset pool is
reported alongside as `pooled_skill_all_assets` and judged separately once it has
a record of its own. Growing the universe mid-stream must not quietly change what
the sealed question was asking.

**Thresholds are unchanged; only the statistic they read is.** This is a
pre-data amendment, which is the only honest kind — p25/p75 entered the log
2026-09-07, the first 5d interval window resolves ~2026-09-14, and the sealed
record held **zero** resolved observations when this was written. After that date
the bar is frozen. On the exploratory backfill the pooled number reproduces the
figures already recorded below (t5 −0.009, CI [−0.055, +0.019] on 4 blocks; t20
−0.065, CI [−0.149, +0.054] on 3), now with a block-bootstrap interval the
previous equal-weight field did not carry.

**The conditioner changed once, on 2026-09-14 — amended 2026-09-13, zero
interval observations resolved.** WP-17.5 found the table the seal was written
over was built on ~780 dates of one regime with its credit dimension on a
3-year rolling FRED window, and that the live bucket had the same n as its
grandparent — the note's "conditional" numbers were conditional on NFCI alone
([KB-028]). The table is rebuilt from 2000-08 with the credit tertile on BAA10Y
(v2.1). What that does to this record, stated so it cannot be re-argued later:

- **The sealed question is unchanged** — does *this* conditioning beat not
  conditioning — and so are `SEAL_START`, `MIN_SKILL`, `MIN_BLOCKS` and the
  disqualifier order. A change to what "conditioning" *is* is not a change to
  the bar; it is a change to the thing the bar measures, and it is the same
  kind of change the weekly refit makes every Sunday, only larger and once.
- **The five report dates 2026-09-07 → 2026-09-11 were published from the old
  table.** They stay in the sealed record: nothing was resolved when the
  switch landed, the quant log dates it by itself (`HY:` → `CREDIT:` in the
  bucket label; `n` roughly triples), and dropping them would be a second
  post-hoc edit to defend the first. Five dates of one 21-day block cannot move
  an 8-block read; if the first sealed read is within a hair of a threshold,
  say so and read it both ways.
- **The exploratory backfill above was scored against the old table** and is
  not re-run. It was already exploratory.
- **Why now and not at the read:** because the alternative was letting the
  first sealed read judge a table whose YC and credit dimensions were inert,
  and then arguing about whether the null was about conditioning or about the
  data window. Fixing that after the read would be the goalpost move; fixing
  it at zero observations is the last honest moment, the same one WP-22.C's
  own amendment used.

**The `har_gaussian` comparator's σ changed once, from the 2026-09-14 note —
amended 2026-09-13, zero interval observations resolved** (`todo.md` #17 →
`resolved.md`, [KB-033]). The comparator reads the logged `forecast_daily_vol`,
and WP-17.5 measured that number as a four-parameter OLS on the ~50–70 rows a
`period="90d"` fetch leaves: `degenerate` on every asset, a printed
`0.0% ann-vol` on 7 / 76 S&P and 10 / 76 Bitcoin dates. From 2026-09-14 the
note fits on a separate 5y fetch (`market_data.fetch_vol_histories`), refuses
fewer than `HAR_MIN_RETURNS = 1000` returns, and drops a non-positive forecast
instead of logging it. Stated against the seal so it cannot be re-argued:

- **This is a comparator's input, not the bar and not the published arm.**
  `SEAL_START`, `MIN_SKILL`, `MIN_BLOCKS`, the disqualifier order and the
  `unconditional` benchmark — the test — are untouched. `har_gaussian` is an
  optional rival; a better rival makes the published table's job harder, not
  easier, so this cannot be read as a move in the product's favour.
- **The five report dates 2026-09-07 → 09-11 were logged from the 90d fit and
  stay in the sealed record.** Nothing was resolved when the switch landed;
  the quant log dates it by itself (the zeros stop, and the number moves —
  on 2026-09-13's tape the 90d fit said 12.3 / 27.0 / 62.0 / 26.8 % for
  SP500 / Gold / WTI / Bitcoin and the 5y fit says 13.0 / 19.8 / 45.1 / 35.3 %,
  against a trailing month of 8.8 / 22.7 / 39.3 / 25.8 %). A date the gate
  drops has no `har_gaussian` arm, exactly as a logged zero had none before.
- **The exploratory "a constant beat the model" observation above was scored
  against the old σ** and stands as written: `har_gaussian`'s median is zero by
  construction and that read was about drift, not σ. It is not re-run.
- **Why now:** the same reason as the conditioner — zero observations is the
  last honest moment, and landing it before the 2026-10-02 wind-down touches
  `pipeline.yml` keeps the two changes apart in the log. No version bump: a
  fit-window correction, not a capability change.

**The honest prior.** Low, and it should be said out loud before the data arrives.
[KB-024]'s mechanism — stress → bearish → mean-reversion — was about direction,
and a distribution is a weaker claim that does not need direction to be right. But
the bucket conditioning is coarse (18 cells on three slow macro series) and the
first read of the seen median backfill is a skill of **−0.009 at t5 and −0.065 at
t20** against the unconditional benchmark on 4 and 3 blocks respectively: no
detectable edge, and nowhere near the power to claim one either way. That number
is exploratory and is recorded here so it cannot later be presented as a sealed
result.

**One exploratory observation, flagged as a hypothesis with its confound named.**
On the same seen backfill, `har_gaussian` posts the *lowest* mean pinball of all
four arms on all three assets (SP500 0.729 vs published 0.758; Gold 1.622 vs
1.679; WTI 3.354 vs 3.367). Do not read that as "the vol model is the better
distribution" yet, because on a **median-only** claim the pinball at q=0.50 is
just half the absolute error, and `har_gaussian`'s median is **identically zero**
while the two empirical arms quote the historical drift median. So what this
measures is narrow and specific: *predicting no move beat predicting the
historical drift*, on 4 blocks of a bull tape. It is [KB-024]'s "a constant beat
the model" shape pointing at a different constant, and it is exactly the kind of
result that would be over-read. The informative version of this comparison —
all three quantiles, where `har_gaussian` actually has to get the interval width
right and the drift question falls away — cannot run until the sealed interval
record accumulates.

### WP-22.D — Wind-down of the directional scorer *(pending ~2026-10-02)*

Unchanged from WP-21.G: `score_predictions.py` keeps running until the last v1.5
note's T+20 window resolves, prints `DIRECTIONAL RECORD CLOSED`, and then stage 3
comes out of `pipeline.yml`. What changes is that stage 3 is no longer left empty
— `score_distributions.py` takes its place, so the pipeline never has a published
product with no scorer again.


## Exploration Tier (Phase 23) — *the generation side of the method* 🔍 OPEN — drafted 2026-09-13, harness run 2026-09-14, seal decided 2026-09-14

**Why it exists.** The method ([the method](../concepts/the-method.md)) is a
refutation engine, and on 2026-09-13 it ran out of its kind of question: the
IMP-1 candidate list is exhausted ([KB-032]), WP-21.E families 2–3 are unblocked
but unchosen with an honestly low prior, and WP-18.4 was gated on a metric that no
longer existed (Phase 18 closed 2026-09-14). Every queued item is another input to a question closed three
times ([KB-024], [KB-026], [KB-027]). Meanwhile the most robust empirical
statement in the repo — the stress-reversion mechanism, found independently in
three runs — is filed as an explanation of a negative and has never been asked
as a question. The reasoning, and the rules, are in
[How we explore](../concepts/how-we-explore.md); the candidates are in the
[hypothesis register](hypotheses.md). This phase builds the harness they need.

**What it is not.** Not a route back to a directional call
([ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md)); the target
space is distributions, states and gaps, and each register entry carries the
check. Not a change to the published note, the sealed table or `pipeline.yml`
— every explore-tier computation is a shadow. Not a replacement for the two
clocks (Phase 22 ~2027-05; a live fragility episode), which gate product changes
and are untouched.

### WP-23.A — Which seal governs ✅ decided 2026-09-14 → `SEAL_START` reused

`numeric_baseline.SEAL_START` (2018-01-01) was sealed for *directional* families.
A promoted distribution or state hypothesis reads a different question on the
same dates. **Decided ([`resolved.md`](resolved.md) #19): the slice is reused.**
It has never been read for a distribution question; one seal stays in the repo;
the multiplicity ledger of the two WP-23.C looks (nine arms, two runs, all
reported, all on explore surface) travels with whichever class is promoted
first. A promoted hypothesis reads 2018-01-01 → the day before Phase 22's live
record, once, and that read burns the slice for its whole class. The harness
keeps stopping at the seal.

### WP-23.B — The class bars *(written before any candidate is promoted)*

One pre-registered bar per hypothesis *class*, not per hypothesis — the
[ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md) move
made a rule. Two classes are visible in the register today:

- **Shadow conditioner vs `unconditional`** (H-002, H-004): Phase 22's bar as
  is — `MIN_SKILL = 0.02`, block-bootstrap interval clear of zero,
  `underpowered → miscalibrated → inverted` first — **plus a mechanism clause**
  named by the entry (for H-002: Elevated width > Normal width *and* medians on
  opposite sides of unconditional; either failing → `unexplained`, not `edge`),
  **plus `har_scaled` as a second comparator** (`resolved.md` #22): a promoted
  conditioner must beat not only `unconditional` but the vol forecast the
  product already has, applied to the empirical shape — on the explore slice
  that rival matched the best arm at every horizon, so a conditioner that
  clears `unconditional` and not `har_scaled` has found width, not a state.
- **Gap → width** (H-003): no scorer exists. Pinball loss on a quantile pair of
  the next-quarter rate change against `trailing_250` and `unconditional`,
  quarterly blocks, an explicit `underpowered` floor given ~55 observations.

Each bar ships with the tests [the method §10](../concepts/the-method.md#10-a-bar-is-not-tested-by-the-results-that-fail-it)
requires: every disqualifier driven independently, and a planted-signal
positive control.

### WP-23.C — The shadow-conditioner harness ✅ built 2026-09-14, first looks run

`.macro-assist/explore_conditioner.py` (research tier). Walks every arm
forward on the explore slice — report dates strictly before
`numeric_baseline.SEAL_START`, known-by-*t* quantiles, `MIN_N = 10` with the
product's collapse ladder — and scores each the Phase 22 way (`skill_vs`
against `unconditional`, 21-report-date block bootstrap, coverage, PIT), with
`verdict(sealed=False)` on every arm so the code, not the reader, returns
`exploratory`. Eight arms: the published macro bucket, `trailing_250`, the OR
flag's state, the composite's state, OR × NFCI, the S&P drawdown bin, and
drawdown × OR — plus the H-002 / H-004 structure checks. Two optional arms
since the second look: `har_gaussian` (the scorer's comparator, walked forward
with the product's fit) and `har_scaled` (the same σ on the empirical shape),
quoted where the product would quote a forecast and scored on their own
subsample, with the H-006 rival check beside them. Report in the
`numeric_baseline` shape at `results/explore_conditioner/report.md`; inputs
cached beside it so `--cached` reproduces the run.

It ran before WP-23.A was decided, deliberately: the 2010-06 → 2017-12 dates it
read are explore surface under every option #19 had, so nothing was burnt —
and the seal was then decided as 2018-01-01 (`resolved.md` #19). What it saw is on
the register: H-002 and H-004 each carry a ledger block (both structure checks
failed as written), H-005 and H-006 are new `seen` entries. Owner's competence
gate ([how we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis))
still applies before the first promotion. **The second counted look ran the
same evening — H-006's rival.** `har_gaussian` does not carry the drawdown
bin's gain; `har_scaled` does, and H-006 closes toward [KB-033] as a width
claim a vol forecast delivers. What the look also showed — the scorer's own
comparator over-covers and loses to `unconditional` at 20d because of its
Gaussian wrapper — is H-007 (`seen`); the scorer keeps its sealed comparator
and `har_scaled` is in WP-23.B's bar instead (`resolved.md` #22). Next counted look, if
any: the H-005 occupancy cut (deficit by bucket, single-episode cells), or the
price-only arms pushed back to 2001 to test H-006's calm-tape confound.

### WP-23.D — First promotion

Not chosen. H-004 is the cheapest (a sub-table of H-002). H-001's confound was
resolved 2026-09-14 from the pulled artifact (the ordering is a crisis-rebound
period effect and inverts within three of six assets) and the entry is
`closed` on its own target-space rule — an errand, not a promotion, and no KB
entry. The owner rewrites the chosen entry, its status moves `draft →
promoted`, the ledger is attached, and the run reads the sealed slice once.
Result → KB, either way.

---

## Record Integrity & Session Continuity (Phase 24) — *make the record layer executable* 🟡 IN PROGRESS — WP-24.A–E running in CI (24.A/B since 2026-09-14, 24.C/D/E since 2026-09-21)

**Why it exists.** Everywhere a claim could be inflated, this project built a
mechanism rather than a request: `verdict(sealed=False)` *cannot* return a pass,
`--require-<family>` fails a run that silently dropped its arm, the workflow
**pins** `--seal-start` so the boundary lands in the run log and not only in
whichever revision was checked out. The **record layer** — the four docs that
carry meaning across sessions — is the one place that still runs on good
intentions. `CLAUDE.md` states a precedence rule ("when two docs disagree about
status, `active-experiments.md` wins") with **no detector**; `todo.md` carries a
hand-written `Last reviewed:` line; convention #11's "never renumber, never
delete" is a sentence.

The cost is already measured. The 2026-09-11 maintenance pass found the weekly
refit unreachable: the conditional table had frozen at **2026-08-31**, *"no run
failed, no check went red"*, WP-22.A's six-asset universe never landed, and the
note kept printing "no conditional base rate" for three assets. It was **found by
reading commit dates**. That is the same failure as the exogenous gate going
*"unreadable rather than failed"* and as the three days when the pipeline
published a product no scorer measured — a track that can no longer answer its
question, with nothing watching.

So the axis is not progress, and not correctness. A wrong result is productive
here: it gets a KB entry and closes a question. The axis is **readability** — for
each open track, can it still answer its question, and when?

**What it is not.** Not a research track: no seal, no pre-registered bar, no KB
entry expected — nothing here measures the world, so [the method](../concepts/the-method.md)'s
machinery does not apply and invoking it would be cargo cult. Not a change to the
published note, the sealed table or `pipeline.yml`, so **no version bump**
(convention #9 — not a capability change). Not a new source of truth: the docs own
the facts and the audit only reads them. Not an auto-fixer — see WP-24.D.

**Drafted by the assistant, 2026-09-14, from a session walkthrough.** The
work packages are engineering; the two that change a *convention* (24.D's
precedence handling, 24.F's ADR page shape) were owner decisions, logged as
`todo.md` #23 and #24 and **decided the same day** →
[`resolved.md`](resolved.md): a contradiction is red with a pin; the revisit
section is enforced, not introduced. 24.D and 24.E shipped as decided; 24.F is specified and shippable.

**Order.** 24.A is the first step and stands alone; 24.B shipped the same day, 24.C–E a week later. The draft claimed it was
the check that would have caught the frozen refit on day one; building it showed
that is false, and the correction is recorded under 24.A — the refit's in-repo
declaration was fine, the *external service* was rebuilt without its call, and
nothing inside the repo can see that. **24.B is the check that would have caught
the refit**, around day nine. Everything after 24.A is additive and
independently shippable.

### WP-24.A — `record_audit.py` skeleton + the workflow-orphan check ✅ SHIPPED 2026-09-14

`.macro-assist/record_audit.py` · `tests/test_record_audit.py` (16 tests, each
finding driven on its own, plus the real checkout asserted clean) · its own
workflow `record_audit.yml` on every push and PR — it has its own job because
nothing else in CI runs pytest, and `docs.yml`'s path filter would not fire on a
workflow change. [ADR-0013](../decisions/ADR-0013-one-pipeline-entry-point.md)
made enforceable: every workflow is the entry point, a `needs:`-ordered stage of
it, dispatch-only, CI (push / pull_request — a fourth class the draft missed;
`docs.yml` and the audit's own workflow are it), or pinned in
`SOFT_KILLED_WORKFLOWS` on the `KNOWN_LEAKS` pattern — held exactly, so a pin
whose arm is restored, dropped its `workflow_call`, or has no file is itself
red. A second check reads the schedule table in `operations.md` and fails on a
slot that calls anything but `pipeline.yml`. Module classified `TOOLING`.

**The premise was wrong, and the code showed it.** Run against the tree from
just before the 2026-09-11 fix, the workflow check passes: the refit had no
`schedule:` of its own — it was `workflow_dispatch`-only, with its Sunday call
in the external service, and the repo's schedule table still listed that slot
after the service had been rebuilt without it. A repo-vs-world gap; no in-repo
audit sees it. The schedule-table check goes red on that tree, but only because
the rule now forbids the slot, not because it can tell whether the service
honours the table. The header of `record_audit.py` states the limit so nobody
relies on it. Found and fixed on the way: `operations.md` still described the
refit as "its own cron call" in three places and `trigger_pipeline.sh`'s usage
example still showed `cron-refit`.

### WP-24.B — Artifact liveness ✅ SHIPPED 2026-09-14

`check_artifact_liveness` in `record_audit.py`, driven by an `ARTIFACTS`
registry — path, the branch the stage pushes to, the cadence owed, the stage
that owes it. Red when the artifact's last-changed **commit** is older than
cadence + 1 day. Four entries, one per live track: the conditional table and
`accuracy_summary.json` on `main` (weekly, 8 days), `dist_scores_summary.json`
and the daily note (`*/*-macro.md`) on `output` (8 days / 4 days). Eleven
tests on synthetic git repositories, each finding driven on its own; the real
checkout is asserted for *shape* only (every entry resolves to something
written on its branch), so a bad pipeline week turns the CI audit red and not
the unit suite.

Three reading rules, each with a test that would fail without it: the date is
the **commit** date, never mtime (a fresh clone rewrites mtimes); the ref is
`origin/<branch>`, never `HEAD` (a PR branch cut two weeks ago must not fail
for refits it does not carry); a **shallow clone is refused** rather than
passing vacuously (`record_audit.yml` checks out with `fetch-depth: 0`).
`--now DATE` limits the git walk with `--until`, so a replay is honest.

**The claim above, checked.** Replayed against the real history: quiet on
2026-09-07; **red on 2026-09-08** — `conditional_distributions.json` last
changed 8.5 days ago on `main` (0d12737, the 2026-08-31 refit); still red
2026-09-11; clear 2026-09-12. Day nine, three days before the freeze was found
by hand. The same replay is `test_the_frozen_refit_replayed`.

A stopped track stays red until its registry line is removed — the pin shape
again, deliberately. `accuracy_summary.json` keeps landing past the directional
scorer's ~2026-10-02 banner because `summarize_accuracy.py` rewrites
`generated_at` weekly, so no entry is due to retire yet. Documented in
[Operations › A reachable stage that produces nothing](../reference/operations.md#a-reachable-stage-that-produces-nothing).

### WP-24.C — Referential integrity ✅ SHIPPED 2026-09-21

`check_referential_integrity` in `record_audit.py`. Every `KB-###`, `ADR-####`
and `WP-##.x` cited under `docs/` and in `CLAUDE.md` resolves — to a KB heading,
a file in `docs/decisions/`, a mention in `roadmap.md` or `roadmap-archive.md`.
ADR numbering is contiguous from 0001, one file per number, and no number has
been deleted from `HEAD`'s history (`git log --diff-filter=D --no-renames`, so
a renumbering shows as a deletion and a slug rename does not) — convention #11
enforced. The inbox holds one open item per number and none that `resolved.md`
also holds; every `` `todo.md` #N `` and `` `resolved.md` #N `` pointer lands.
One report-only shape: a `todo.md #N` whose item has since resolved — the
pointer still lands, in the other file, so it is printed per page for the next
housekeeping pass (eight pages today) and never fails. Twelve tests on a
synthetic docs tree, one defect at a time; the real checkout is asserted clean
(this check does not depend on the date, so it joins the 24.A checks there).

**What it found.** No dangling KB, ADR or WP identifier anywhere in the record.
Two things it could not pass without naming: **KB-008** is mentioned in the
KB's prose as a reserved number and was never written (pinned,
`RESERVED_KB_NUMBERS`), and **#7** heads both Phase 22's open Target Range
decision and the carried accuracy finding closed 2026-09-14 as "#7 (carried)"
(pinned, `KNOWN_ITEM_COLLISIONS`). Both pins are held exactly — a pin whose
condition has gone is itself red. Replayed against the trees from 2026-09-08
to 09-13, the check is red on each: the inbox carried **two open `#7`s** for
those six days, the duplicate the 09-14 maintenance pass closed by hand.
Documented in [Operations › The identifiers that are not links](../reference/operations.md#the-identifiers-that-are-not-links).

### WP-24.D — Contradiction surfacing ✅ SHIPPED 2026-09-21 *(report, never repair)*

`check_contradictions` in `record_audit.py`. Every place the record states a
phase's status is read — the board's headings and bullets, the roadmap's
`## … (Phase N)` heading and its phase-table row, every `Phase N` in
`CLAUDE.md`'s Current-state table — and classed by the record's own markers
(🟢 🟡 🔍 open, ⏸ dormant, ✅ ❌ closed; in `CLAUDE.md`, the status word in
the clause after the name). Two classes for one phase is red; wording within
a class is not. The finding prints every claim with its `file:line` and
**takes no side** — `CLAUDE.md` says who wins, red only insists that someone
applies it. `CLAUDE.md`'s Version row is held to `versions.py` the same way
(`bump_version.py` does not edit it). Work packages are out of scope, on
purpose: the board files WP-21.E as ✅ for family 1 and ⏸ for families 2–3.

**Decided 2026-09-14 (`resolved.md` #23): red, with a pin.** Built as decided:
`KNOWN_CONTRADICTIONS` maps the subject to the open `todo.md` item that
carries the disagreement; the pair is still printed, report-only; a pin whose
sources agree again, or whose item is not open, is itself red. Eight tests on
a synthetic board + roadmap + `CLAUDE.md`; the real checkout is asserted
clean, and a test asserts every pin names an open item.

**What it found — on the first run.** The roadmap's phase table still said
**`⏸ Draft`** for Phase 24 a week after the board went Active on 24.A, while
the roadmap's own heading and `CLAUDE.md` said in progress. The 24.A, 24.B and
24.C passes each edited this file and none saw it. Replayed on every record
commit since 2026-09-13: red from 2c47688 (24.B shipped, 09-14) to HEAD; and
red for two commits on 09-14 on **Phase 23**, whose roadmap heading said
`⏸ DRAFT` after the board had it at 🔍 with the harness run — the closing
pass fixed that one by hand the same day without a detector. Both rows fixed;
the pin table is empty. Documented in
[Operations › A claim the repo makes twice, differently](../reference/operations.md#a-claim-the-repo-makes-twice-differently).

### WP-24.E — Ages, from git ✅ SHIPPED 2026-09-21 *(a table, never a finding)*

`ages()` in `record_audit.py`, printed by the runner before the findings.
Days since each open `todo.md` item (every `### … #N` heading through the
next numbered one) and each board row (the **Active** sections, the
**Queued / dormant** bullets) was last edited, oldest first, with the commit
that did it. The date is per line from `git blame`, so a row's age is its
youngest line's; whitespace and moves within the file are not edits (`-w
-M`), a line moved in from another file is, an uncommitted line is zero days
old. `--now` blames the file as it stood then, so it replays. Not a check: it
returns no `Finding`, and **never red** as decided (`resolved.md` #23) — an
old item breaks no rule. Eight tests on a synthetic repo with pinned dates;
the real checkout is asserted for shape (every open item has a row).

**What the first run showed.** `todo.md`'s hand-written `Last reviewed:` line
said 2026-09-14 while the file's last edit was 09-18 — the line the table
replaces, failing on the day the table shipped. Oldest on 2026-09-21: the
IMP-4 and Phase 20 board rows, untouched since the 09-04 stand-down (17
days); then `#7` Target Range coverage (13 days); five items (`#1b`, `#2b`,
`#3b`, `#6b`, `#11`) unedited since the inbox was split out on 09-11. Replayed to 09-13,
the table led with the carried `#7`, `#4` and `#5` at 19 days, and the 09-14
pass closed the first two by hand. Nothing predates the consolidation, by
construction. Documented in
[Operations › The ages, computed](../reference/operations.md#the-ages-computed).

### WP-24.F — ADR revisit conditions *(enforce the existing page shape)*

Every ADR answers **"Would we revisit it?"** with a *condition* rather than a
date — [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md) names
WP-21.E's capped search; [ADR-0017](../decisions/ADR-0017-bss-floor-left-open.md)
is the worked example of a condition coming true and being acted on, a decision
parked with a test pinning it and closed five days later. The draft proposed
making the section mandatory; on inspection (2026-09-14) it already was —
[`decisions/index.md`](../decisions/index.md) lists it as part 4 of the page
shape and **18 of 21 ADRs carry it**. The retrofit was two pages (ADR-0015,
ADR-0021), done the same day and marked as written after the fact; ADR-0017 is
superseded and exempt. A reasoned **"No."** is a valid answer — four pages give
one. Decided as `resolved.md` #24.

What the audit does, in two halves: **(a)** every non-superseded ADR has the
section, non-empty — presence, the sibling of `CLAUDE.md` #11's *"a page with
no costs listed has not been thought through"*; **(b)** a revisit section that
cites a `todo.md` item, WP or KB id whose referent has since closed or landed
(ADR-0016 → #7/#8, ADR-0009 → WP-21.E, ADR-0020 → Phase 22's sealed read) is
printed as *"cited condition may have fired"* — report-only, and the answer to
a rule written in good faith that later holds progress back. Prose conditions
("if GitHub's scheduler became reliable") are not read by a machine and the
audit does not pretend to; a structured condition field was rejected as
narrower than the prose it would replace.

### WP-24.G — `/orient`, the session-start ritual

`.claude/` currently holds two settings files and nothing else: **no skills, no
commands.** A skill is the one artifact guaranteed to be in context when it is
relevant, rather than depending on a session happening to read the right file —
which makes this the cheapest continuity win available.

`/orient` prints, at turn 1 of any session: the board; the audit output including
24.D's contradictions and 24.E's ages; open `todo.md` items oldest first; any ADR
revisit condition now true; and, when a promotion is pending, the four
competence-gate questions from
[how we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis).

That last line is the point of the phase in miniature. §6 — the anti-helicopter
rule, the one that makes the owner rather than the assistant author a
pre-registration — was written 2026-09-13 and has **no trigger**. A rule nobody
is prompted to apply is in the same category as a precedence rule with no
detector.

**Where:** `.macro-assist/record_audit.py` · `.macro-assist/tests/test_record_audit.py` ·
`.github/workflows/record_audit.yml` (its own job — decided by 24.A) · planned:
`.claude/skills/orient/`.
