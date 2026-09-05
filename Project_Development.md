# Macro-Assist — Project Development (the roadmap)

## What this document is

The **roadmap**: phases, work packages, and the reasoning behind the decisions —
including the ones that closed something. It is deliberately *not* the system
reference.

- **How the system works today** — architecture, data sources, the analysis
  pipeline, scoring, workflows, secrets, versioning, maintenance — is
  [README.md](README.md), which is kept current with the code.
- **Measured findings** (KB-###, negatives included) are in `Knowledge_Base.md`.
- **What is running right now** is the board in `Active_Experiments.md`.
- **Closed phases and superseded detail** are in
  [Project_Development_Archive.md](Project_Development_Archive.md).

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
prompts now live in [Project_Development_Archive.md](Project_Development_Archive.md).
Measured results live in `Knowledge_Base.md`.

> **Archive-on-completion convention (default editing behaviour).** When a **WP**
> is marked Done *and* its result is recorded in `Knowledge_Base.md`, trim its
> entry here to a one-line status + verdict + KB pointer (kept inline under its
> phase — the method/harness/reproduce detail is redundant with the KB entry and
> the code). When an **entire phase** closes, move its remaining detail to
> `Project_Development_Archive.md` and add a row to the table below. **Never trim
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
| 9 | Volatility forecasting (HAR-RV + VRP) | ✅ 2026-05-26 |
| 10 | Regime classification (HMM) | ✅ 2026-05-26 · ⚠ retired from note — WP-17.4 / KB-006 |
| 11 | Conditional distribution layer | ✅ 2026-05-29 |
| 12 | Quant context integration | ✅ 2026-05-29 |
| 13 | End-to-end validation | ⏸ Backlog (optional) |
| 14 | Production hardening (weekly refit, monitoring) | ✅ 2026-05-29 |
| 16 | Fragility monitor + design-by-emergence prompt levers | ✅ Closed 2026-09-04 — 16.A shipped and alive (→ IMP-4), 16.B/C closed by Phase 21; detail archived |
| 21 | Directional product validation → **the cut (v1.6)** | ✅ Closed 2026-09-04 — [KB-024]; WP-level detail archived, WP-21.E queued |

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

> **Execution-order table + implementation notes for Phases 1–15** moved to [Project_Development_Archive.md](Project_Development_Archive.md).


## Experimental Track — Emergence & Fragility (Phase 16) ✅ CLOSED

*Detail archived 2026-09-04 → [Project_Development_Archive.md](Project_Development_Archive.md).*

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
board in `Active_Experiments.md`.

**Worth remembering the phase for the method, not the levers.** Fragility earned
its place through a look-ahead-safe backtest *before* anyone trusted it, and that
discipline — pre-commit the gate, de-overlap the sample, write the KB entry
whichever way it goes — is what Phases 17, 19 and 21 all ran on afterwards.


---

## Numerical-Layer Validation & Rigor (Phase 17) — *Goal 2*

**Why.** The fragility index earned its place via a rigorous, look-ahead-safe backtest before we trusted it (Phase 16.A). The **HMM regime layer (Phase 10) never got the same scrutiny**: it is fit and feeds the quant context, but we have not shown (a) that it is computed look-ahead-safe in the daily pipeline, (b) that its state labels actually separate forward returns / volatility out-of-sample, or (c) that 4 states is the right choice rather than an arbitrary one. This track applies the fragility discipline to the existing numerical layers, **starting with regime**. Pure-numerical, **zero LLM/API cost**, on its own branch in parallel with the fragility shadow.

**Branch.** `feature/regime-validation`. **Method.** Reuse the fragility harness patterns (`fragility_backtest.py`): pull-once-and-slice for prices, walk-forward look-ahead-safety, Mann-Whitney AUC, de-overlapped episode scoring, and record results in `Knowledge_Base.md` (KB-003+), kept separate from this plan.

1. **WP-17.1 — Look-ahead audit of the regime pipeline. ✅ Done** (→ KB-003). Built `regime_backtest.py` (walk-forward vs full-sample, look-ahead-safe). Findings: live labeling is safe; validation must use walk-forward, never the persisted full-sample model; inference is single-point so the HMM's transition matrix is unused live. Caught a **shipped bug** — the HY-OAS credit feature (`BAMLH0A0HYM2`, only ~3y of FRED history) truncated training to ~2y; fixed by switching the regime credit feature to **`BAA10Y`** in both training + live (`baa_spread`, model regenerated via `refit_models.py`). Walk-forward vs full-sample labels disagree 70.5%; the full-sample model collapses to one label (startprob-dominated). *(Conditional layer still on truncated HY-OAS → WP-17.5.)*

2. **WP-17.2 — Regime skill gate (the WP-16.A.2 analog). ✅ Done — verdict NO SKILL** (→ KB-004). Walk-forward (18y, 3,922 readings): Risk-Off→drawdown AUC ~0.47–0.49, High-Vol→fwd-vol ~0.50 despite vol-percentile being a direct input; ~all days falsely ≥0.8 posterior. No predictive information as wired; scorer sound (planted-signal test passes). Decision deferred to 17.3 (inference vs concept). Harness: `--skill`.

3. **WP-17.3 — Inference path vs. concept. ✅ Done — verdict INFERENCE was the bug** (→ KB-005). Switching single-point → **sequence (Viterbi/smoothed) inference** lifts High-Vol→fwd-vol AUC 0.495→0.646 and Risk-Off→drawdown 0.465→0.553; HMM-sequence beats GMM on drawdown (0.553 vs 0.499). The concept is salvageable but modest (0.55 = weak band). Harness: `--infer`.

4. **WP-17.3b — Fix the live inference path (sequence, not single point). *(CANCELLED — KB-006)*.** Was the payoff of KB-005 (sequence inference recovers the regime to AUC 0.55), but WP-17.4 then showed even the salvaged regime loses to a 4-feature rule and adds nothing within stress strata. No point fixing a layer we're dropping.

5. **WP-17.4 — Incremental value over the simpler bucket (keep/cut gate). ✅ Done — verdict REDUNDANT → drop the HMM** (→ KB-006). A 4-feature equal-weight rule-based stress score gets drawdown AUC 0.697 vs the HMM's 0.553, and within stress terciles the regime adds nothing (mean 0.507; redundancy Spearman 0.336). Regime block removed from the daily note (its macro-stress dimension is already covered by the Phase-16 fragility monitor). Harness: `--bucket`.

6. **WP-17.5 *(later)* — Extend to vol_forecast + conditional layers.** Same look-ahead-safe walk-forward + skill scoring for HAR-RV (Phase 9) and the conditional-distribution table (Phase 11). Also fix the conditional layer's truncated HY-OAS input (the `assign_bucket` series only has ~3y — same FRED limit found in WP-17.1).

---

## Input Information Value & Prompt Economy (Phase 18) — *input-side of Goal 1*

**Premise.** Phase 17 asked, layer by layer, whether each *numerical component* earns its place (and cut the HMM regime when it didn't). Phase 18 points the **same discipline at the LLM input payload**: the daily user message is now ~6.5k chars across 7 sections (FRED ~3.1k, Sector ~1k, Market ~0.9k, Quant ~0.65k, Technicals ~0.45k, COT ~0.37k) plus a ~13k-char system prompt — and **none of it has ever been tested for whether it actually improves the macro assessment.** Unhelpful inputs aren't free: they cost tokens and dilute attention. This is the **input-side complement to WP-16.B.3** (emergent signal weights): same substrate (per-prediction logging + Brier), one level up (whole input sections/series, not just dashboard signals). Point-1 ("is this quality information?") and point-2 ("weight the inputs") converge here.

**Hard gate — read before starting.** Every verdict in this phase is measured by **WP-16.B.2 (Brier / reliability)**, which **does not yet exist**. B.2 is therefore the prerequisite for the outcome-grounded parts of Phase 18 *and* for all of Goal 1's loosening/weighting — build it first, or these experiments are unfalsifiable (accuracy alone rewards overconfidence). Two standing rules, inherited from Phases 16–17: **(a) cheap proxies before expensive ablation** (zero-cost screens narrow what we pay the LLM to test); **(b) one lever at a time** against the B.2 baseline (don't loosen + reweight + prune in the same window, or the Brier delta is unattributable).

1. **WP-18.1 — Payload observability. *(Done — on `main`)*.** `MACRO_PREVIEW=1` writes `results/llm_payload_preview/<date>.md`: a section-size index + the verbatim user message the model receives + the **withheld** signals (shadow fragility forced to `show`, retired HMM regime). Built `build_payload_preview` (`collect_and_analyze.py`) + `build_nonlive_signals_block` (`quant_context.py`); the daily Action sets the flag and prints the file to its log; the old `MACRO_DEBUG` stdout dump was retired. This is the inspection substrate the rest of Phase 18 builds on — the section-size index is already the first crude "density" view (e.g. FRED is ~half the payload).

2. **WP-18.2 — Cheap input-quality proxies (zero-cost, no LLM). ✅ Built** (2026-06-27, on `main`; awaiting first real-data run for KB-009). `input_ledger.py` builds an aligned FRED+market+sector level panel and computes, per input series: **staleness** (days past a cadence-appropriate freshness limit → STALE flag), **entropy** (normalised Shannon entropy of the clipped level distribution, [0,1]; <0.15 → DEAD), **robust σ** (MAD-scaled, outlier-proof, human-readable units), and **cross-input redundancy** (max \|corr\| with any other input, computed on **first differences** — levels are non-stationary and correlate spuriously; ≥0.80 → REDUNDANT, e.g. the 10y/2y/real-yield/breakeven and SPY/sector-ETF clusters). Ranks by a transparent `info_score = entropy·(1−max\|corr\|)` (lowest = most prunable); optional payload-section token-cost table from a `--preview` file. Pure math is unit-tested (22 tests, synthetic series — constant→DEAD, collinear-changes→REDUNDANT, level-trend-but-independent-changes→not flagged); the IO shell needs FRED_API_KEY (`python .macro-assist/input_ledger.py`, user-run like `regime_backtest.py`), writes `results/input_ledger/<date>.{md,json}`. **A screen, not a verdict** — low-density/flagged inputs are *candidates* for the WP-18.4 ablation; a fully-redundant input scores 0 like a dead one (no marginal info), so 18.4 picks the cleaner of each redundant pair. **Two methodology fixes after the first real run (2026-06-27, 36 inputs × 1367 days):** (a) **staleness** must come from each series' *true* last-print date (`last_obs_map`), not the ffilled panel index — the ffill made every series read "1d stale" (gdp/cpi too); (b) **redundancy is only assessed among daily-active series** (non-zero change fraction ≥0.6) — a ffilled monthly/weekly FRED series has a mostly-zero change vector that manufactures artifact correlations, so sub-daily series are flagged `redund-n/a` and ranked by entropy alone. **Findings recorded → KB-009** (corrected re-run, 36 inputs × 1367 days): the daily market/sector block is highly collinear (VIX≈VIX3M 0.98, SP500≈Nasdaq≈XLK 0.93–0.96, most sector ETFs≈SP500, 10y≈real_yield 0.86) while the FRED macro series carry the orthogonal information. WP-18.4 ablation queue: (1) drop vix3m (redundant+stale+single-use), (2) collapse the sector block to SP500 + differentiated sectors (XLE/XLU/XLRE/XLV), (3) nasdaq-vs-sp500, (4) real_yield-vs-10y (keep breakeven). Also surfaced: the `monthly` freshness limit (45d) is too tight for FRED's month-start dating (cpi/m2 routinely 57d without being abandoned) — only vix3m's 9d is a real staleness signal. Next observability step before paying for 18.4 = **WP-18.3 citation screen**.

3. **WP-18.3 — Model-attention / citation screen (low-cost). ✅ Built + run** (2026-06-27, on `main`; → KB-010). `citation_screen.py` (+ `tests/test_citation_screen.py`, 13 tests) scans the **free-prose** rationale (Exec Summary, asset/theme sections, Key Risks, Primary Driver cells) of every scored note for per-input alias mentions, **excluding** the templated Macro Dashboard table + raw Data Snapshot, and reports each input's citation rate (fraction of notes naming it); joins the latest input-ledger so redundant-AND-rarely-cited inputs surface (`prune_priority` high/watch/keep). Pure (no network/LLM) — runs locally over `results/**/*-macro.md`, writes `results/citation_screen/<date>.{md,json}`. **KB-010 headline: citation and redundancy are nearly anti-correlated — the two screens nominate *different* prune candidates, so the 18.4 queue is their union.** Refined queue: (1) drop `baa_spread` (0/78 cited + correlated w/ cited `hy_spread` + its only consumer the retired HMM regime), (2) drop the 3 raw net-liquidity components (model uses synthesised `net_liquidity` 54%; orthogonal so 18.2 couldn't see this), (3) collapse the sector block to SP500+XLE(±XLK), (4) lower-priority vix3m/nasdaq/real_yield (redundant but heavily cited). **Caveat:** the 6 forecast assets are named by construction in the predictions table (~100% structural, not free attention) and are forecast targets anyway. **Screening proxy, not a verdict** — flags candidates for 18.4; does not decide.

4. **WP-18.4 — Outcome-grounded input ablation (the decision gate; gated on B.2 + sample).** Drop-one-section (and add-one) A/B over the live LLM, re-scoring **Brier**/accuracy on the resulting calls. Expensive (N× LLM cost; outcomes resolve in 5–20d), so run **only on the candidates flagged by 18.2/18.3, one lever at a time, n≥30 per arm.** Verdict: a section that doesn't move Brier past a threshold ⇒ **trim from the payload** (token + attention savings, the prompt-economy payoff); a section that helps ⇒ feed its weight into B.3.

5. **WP-18.5 — Feed results into weighting (closes the loop with WP-16.B.3).** The input-value ranking becomes a **prior for the emergent signal-weight table**: down-weight or drop low-value inputs, up-weight high-value ones, and eventually reorder/prune the prompt itself. This is the explicit join between point-1 (quality test) and point-2 (weighting) — Phase 18 produces the evidence, [WP-16.B.3](#) consumes it.

**Suggested order:** B.2 (build first, it gates everything) → 18.2 + 18.3 (cheap screens, in parallel, zero/low cost) → 18.4 (ablate only the flagged candidates) → 18.5 / B.3 (let weights emerge from the evidence). Branch off `main`; shares `feature/loosen-control`'s B.2 work, so sequence after B.2 lands there.

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

**Information-source taxonomy** (judged first on lead / expectations-gap, then on cost):

| Branch | Example sources | Signal type | Lead? | Access |
|---|---|---|---|---|
| Monetary / policy | Fed speeches, minutes, statements; econ calendar + **consensus** | expectations-gap, regime | medium | free text |
| Macro nowcast | official releases (FRED) + consensus; freight/shipping, EIA energy, claims trend | expectations-gap, fundamentals | some | free/cheap |
| Alt-data leading | Google Trends, job postings, electricity demand, retail/app proxies | fundamentals nowcast | **genuine** | mixed cost |
| Corporate / sector | earnings-call transcripts, guidance tone, estimate revisions | relative, sector | medium | semi-free |
| Positioning / sentiment | COT (have), fund flows, AAII / put-call, social | contrarian / regime | coincident | mixed |
| Policy / geopolitical events | fiscal, regulatory, geopolitics | catalyst→exposure map | event | free text |
| Expert synthesis | analyst notes, YouTube transcripts (have) | human reasoning | varies | free |

**Compaction architecture — a map-reduce evidence pipeline** with a fixed contract at every level and a **per-branch token budget**, so branches scale without blowing the payload (total ≈ N branches × cap):
- **L0 — Source adapters (deterministic):** pull each source on its own cadence, normalise, timestamp, dedup; enforce point-in-time. No LLM.
- **L1 — Extractors (cheap model, Haiku-class):** raw text/data → a structured evidence schema `{claim, direction, magnitude, affected_assets, confidence, source, date}`. This is where the "dump" is prevented — nothing passes downstream as free prose.
- **L2 — Branch analysts (the "narrowing"):** one bounded-budget agent per branch consumes its evidence and emits a **fixed-size structured brief** (~400–600 tokens): stance on the branch's domain, what *changed* vs last period, the expectations-gap read, confidence, citations. The hard cap is the scalability guarantee. Mirrors the existing MA-* / sector sub-agent pattern.
- **L3 — Synthesiser (expensive model, Opus-class):** consumes the N capped briefs (total bounded) → the reframed output (gaps, regime/tail, scenario→exposure, optional scored lean).
- **L4 — Scoring / feedback:** every brief and the synthesis carry falsifiable claims scored on **Brier / commitment**, reusing the Phase-18 input-value + `commitment_by_arm` machinery → measure *which branches earn their tokens*; prune the losers.

Design commitments: structured contracts not prose; provenance + staleness on every claim; cheap-extract / expensive-synthesise (the Haiku/Opus split already in use); and **deliberate market-data independence** so the A/B measures the *marginal* value of real-world reasoning, not a leak of price information.

**Work packages / roadmap (cheap-first; do NOT build the framework before proving one slice):**
1. **WP-19.A — Reframe & target lock (design only). ✅ Done** (2026-07-14 → `.macro-assist/exogenous/DESIGN.md`). Locked: **first slice = monetary / rates-expectations**; **primary success bar = a scored asset directional lean on {10Y, DXY, gold}** (three assets the market-only pipeline already forecasts), judged by Brier/commitment and A/B'd head-to-head against the market-only arm on the *same* assets. Defined the three data contracts (L1 `Evidence` → L2 bounded `BranchBrief` ≤~600 tok → L3 `ExoOutput`), the L4 arm-tag reuse of `calibration_by`/`commitment_by_arm`, and the go/no-go bar (BSS≥market-only at n≥30, or KB-011 net-edge≥ & wrong-rate≤ early; kill after slice + 1–2 branches if no parity → **KB-012** when scored). **Two honest constraints baked in:** (a) *market-light tension* — use survey/economist consensus, not fed-funds-futures (market-derived), as the core benchmark, or the A/B is contaminated; (b) *LLMs can't be cleanly backtested on dated public text* (trained on historical FOMC docs → leakage), so **validation is forward/live**, historical runs are pipeline-shakedown only. Cheap-extract/expensive-synthesise; refresh evidence weekly + cache (FOMC moves ~monthly). **Data sources LOCKED (researched 2026-07-14, zero paid deps):** Philly Fed **SPF** (economist consensus — TBOND/TBILL/UNEMP/CPI/RGDP, free Excel, point-in-time) + FRED **SEP dot-plot** (`FEDTARMD`, via the existing adapter) as two non-market consensus anchors whose *divergence* is itself a signal; FOMC statements/minutes/speeches as the evolving input. High-frequency day-of release consensus (Trading Economics/paid) deferred — the quarterly-cadence slice doesn't need it.
2. **WP-19.B — One vertical slice (L0→L4, monetary/rates). ✅ DONE + INTEGRATED (2026-07-24, on `main`; modular, kill-list = DESIGN §9).** Built the full slice — L0 SPF+SEP consensus adapters + SPF-vs-SEP gap (with structural-nuance interpretation) → L1 Haiku FOMC-text extractor (`Evidence`) → L2 Opus analyst (bounded `BranchBrief`, asset biases matched to the scorer) → L3 arm-tagged `ExoOutput` + a note the existing scorer parses → L4 arm-keyed scoring + `calibration_by_arm` → **live/forward emission** (auto-fetch latest FOMC statement, weekly `exo_weekly_emit.yml`). ~119 tests. **Both confirm-on-first-run calibration smokes PASSED** (synthetic + the real June-17-2026 FOMC statement): L1 reads tone without template-matching, L2 dials conviction proportionally, gap-hardening confirmed. First live exogenous note emitted (2026-07-27, net hawkish; 10Y/DXY Bullish, Gold Bearish; resolves ~08-01). Forward-only validation → **KB-012 pending** (weeks-to-months; early tell = commitment metric). Live-run wiring detail in the **Phase-19 integration status** block below; per-file detail in the code + `DESIGN.md` + git.
   - **Leakage-free early read (backtest, 2026-07-25 → record as KB-013):** `gap_backtest.py` tested the *deterministic* L0 signal historically (no LLM ⇒ no leakage). **Verdict: the SPF consensus rate-*level* forecast has NO positive directional skill on the 10Y** — 40% hit @ binom_p=0.028 at 1Q (mildly *contrarian*: SPF-implied-up precedes a ~7bp fall and vice-versa), washing to noise at 2Q; consistent with the literature that rate forecasts ≈ random walk. **The SPF-vs-SEP gap is NOT backtestable from FRED** — `FEDTARMD` exposes only the latest vintage (~3 pts), so the divergence would need ALFRED vintages (out of scope). Implication: the deterministic anchor is *not* an edge → **lowers the prior** the slice clears the bar; the engine's remaining hope is the (un-backtestable) LLM-tone read. Don't add branches; re-decide at the commitment read.
   - *Build-log pruned 2026-08-20 (per its own "safe to prune" note). The layer-by-layer detail — L0 SPF/SEP adapters, L1 Haiku extractor, L2 Opus analyst, L3 synth, L4 arm-tagging, the FOMC auto-fetcher + weekly emitter, and the two passed calibration smokes — lives in the code (`exogenous/`), `exogenous/DESIGN.md`, and git history. The summary above + the integration-status block below are the doc-level record.*
3. **WP-19.C — Generalise the branch contract.** Only after B works, extract the L0–L2 skeleton + brief schema so branch #2/#3 are cheap to add and the payload stays bounded.
4. **WP-19.D — Add branches by measured value.** One at a time, each gated on "does it improve the scored output vs without it" (Phase-18 ablation discipline). Prune losers immediately.
5. **WP-19.E — Integrate or kill. 🟡 RE-POINTED (2026-09-04) — the comparator was cut, so the gate moved.** As written, this A/B'd the exogenous arm against market-only on Brier/commitment. v1.6 cut market-only's directional calls [KB-024], so that comparator froze and the A/B became unreadable. Option (a) from WP-21.F is now taken: **the anchor is scored inside the WP-21.A numeric harness, against the same pre-committed bar.** Detail in the WP-19.E block at the end of this phase.

**Kill criteria (pre-committed).** Cut the whole branch if, after 2–3 branches, it does not beat market-only on Brier/commitment. Watch-items: cost blow-up (mitigate via cheap extraction, caching, cadence-appropriate refresh — policy monthly, news daily); alt-data access/reliability (start free/scrapeable, treat paid feeds as later bets gated on the free ones); look-ahead bias in text backtests (point-in-time from day one).

**Branch strategy.** Develop on `feature/exogenous-engine` off `main`. Independent of the market-only pipeline; integrates only at WP-19.E via the existing `profile` / run-config A/B. Start with WP-19.A (design) then the WP-19.B single vertical slice.

**Phase-19 integration status: INTEGRATED into `main` 2026-07-24 — modular / removable.**
The user opted to integrate now (autonomous weekly run) rather than manually dispatch during a test phase, on the condition it stays cleanly excisable if it proves unvaluable.
- **Runs autonomously:** `exo_weekly_emit.yml` cron (Mon 06:45 UTC) fetches the latest FOMC statement, runs L0→L3, commits `results/<month>/<date>-exogenous-macro.md`; the existing *Weekly Prediction Scoring* (07:15) scores it when the window closes; `summarize_accuracy` shows the exogenous-vs-market A/B once ≥2 arms have data. Cost ≈ 1 Haiku + 1 Opus call/week.
- **Isolation guarantees (why it's safe to leave running):** the engine is one directory (`exogenous/`); the emission is its own workflow (never touches the market pipeline); the two shared hooks (`score_predictions` arm-keying, `summarize_accuracy.calibration_by_arm`) are **inert without exogenous data** (all notes default to `arm:"market"`, which keeps the bare `{date}.json` score name). Exogenous scores live in separate `{date}__exogenous.json` files.
- **KILL PROCEDURE documented in `exogenous/DESIGN.md` §9.** Soft-kill = disable/delete `exo_weekly_emit.yml` (arm freezes, zero risk). Hard-kill = delete `exogenous/` + its 7 tests + both exo workflows + emitted `*-exogenous-macro.md` / `*__exogenous.json` + `grep -rn PHASE-19-EXO` the two inert hooks + drop `beautifulsoup4`. None of it alters the `market` arm.
- **Validation still forward-only** (DESIGN §6.2): the go/no-go read (KB-012, DESIGN §5 bar) is weeks-to-months out; the early tell is the KB-011 commitment metric. If it doesn't clear the bar → hard-kill.
- **SUPERSEDED 2026-09-04 — the arm is soft-killed and the weekly cron is gone.** `exo_weekly_emit.yml` is `workflow_dispatch`-only and the emission stage was removed from `pipeline.yml` (WP-21.F). Nothing above was deleted; what changed is that the branch no longer emits on a schedule, so "runs autonomously" and "weeks-to-months out" describe a clock that has stopped. The live scoring contract is paused; the branch's current test is WP-19.E below.

---

### WP-19.E — The anchor, scored in the numeric harness ✅ *(shipped 2026-09-04; the run is the open half)*

**Why the work package changed shape.** WP-19.E was "A/B the exogenous arm vs
market-only". v1.6 cut market-only's directional calls, so there is no live
comparator left to A/B against — the gate did not fail, it became **unreadable**.
WP-21.F named two ways back and this is **(a)**: re-point the gate at the WP-21.A
benchmark, which [KB-024] shows is a genuinely hard bar rather than a formality.

**What was built.** `numeric_baseline.py` now carries two more arms, and they ask
two different questions:

| arm | inputs | question |
|---|---|---|
| `exogenous_spf` | SPF consensus only — no price, no market input | does the non-market anchor carry direction on its own? |
| `market_plus_exo` | the WP-21.A market panel **plus** those columns | does the anchor add anything on top of it? (read against `ridge`) |

Seven features, all derived from the Philadelphia Fed SPF median-level workbooks
already committed as `exogenous/example/` fixtures: the consensus curve
(`spf_curve`), the consensus path at four quarters out (`spf_10y_path`,
`spf_policy_path`), the survey-to-survey revisions (10Y / 3M / unemployment), and
a staleness clock. Levels are deliberately excluded — over two decades a trending
level is a date proxy, the same reason `macro_features` omits the 10Y level.

**Why this is a real test and not a fifth arm for its own sake.** Everything the
harness already guarantees now covers the anchor too: the embargo, the shared
call set, the production readers, and the pre-committed `verdict()` bar. The
exogenous features carry fewer NaNs than the market panel's 252-day lookbacks, so
an exo-only arm can start predicting earlier — `shared_call_keys` intersects
across feature sets, so it earns no hit-rate for starting sooner and
`always_bullish` gets no free sample either. That is the [KB-023] error one level
down, and it is asserted by test.

**What is deliberately NOT in it — read this before reading a null.**
- **The SEP dot plot.** FRED serves the *current* vintage of a projection path
  that every SEP release rewrites, so a walk-forward reading it would see the
  Fed's later revisions. `sep.py` says so in its own point-in-time note, and
  WP-19.B's early read already found the SPF-vs-SEP gap un-backtestable for the
  same reason. **The SPF-vs-SEP gap therefore stays a live-only signal** — and it
  is half the two-layer bet. `EXCLUDED_EXOGENOUS_SERIES` holds the exclusion as a
  checked fact rather than a comment.
- **The LLM layers** (L1 extract / L2 analyst). DESIGN §6.2: those models were
  trained on the dated FOMC text they would be reading, so a historical backtest
  of them is leakage-prone by construction. Nothing in the harness reads a
  document.

**So what a null here would and would not close.** It would close *the SPF anchor
as a directional input*, generalising WP-19.B's leakage-free early read (which
found the SPF 10Y level forecast had no positive directional skill — 40% hit at
1Q, mildly contrarian) from one asset and one quarterly horizon to six assets at
t5/t10/t20, on the same sample and bar as every other arm. It would **not** close
the expectations-gap mechanism, which lives in the SPF-vs-SEP divergence and in
FOMC communication drifting from a fixed anchor — neither of which this can test.
Say that plainly when the result is written up; the honest scope of a negative is
the thing most easily lost between a report and a KB entry.

**Cost.** Zero LLM spend, no new secret, no new network dependency — the
workbooks are in the repo. Two ridge arms on the existing panel.

**Status.** Harness shipped and tested (16 new tests; the whole suite green). The
open half is the run itself:

```
Actions → Numeric Directional Baseline → Run workflow
  branch: the branch carrying this change   inputs: defaults (exogenous: true)
```

It needs `FRED_API_KEY` and reachable yfinance/FRED, which is why it lives in CI.
Expect ~90 minutes (the [KB-024] run took 87; two extra ridge arms are cheap next
to the GBM). The report prints to the job log and publishes to
`origin/output:numeric_baseline/`.

#### The read, pre-registered *(written 2026-09-04, before the run)*

Same discipline as WP-21.A: the bar goes down before the numbers, so a marginal
Δ cannot be talked into a finding afterwards.

**Primary — does the anchor carry direction on its own?** `exogenous_spf` must
clear the standing `verdict()` bar (n ≥ 30 decisive, decisive hit-rate > 0.52,
and BSS > 0 **or** an `aligned` separation ordering) **and** beat
`always_bullish` on the same sample. The second condition is not redundant:
[KB-024]'s whole point is that the constant is the real bar and the nominal one
is not.

**Secondary — does it add anything?** `market_plus_exo` vs `ridge`, same model,
same sample, seven extra columns. An increment counts only if `market_plus_exo`
clears the bar **in absolute terms** *and* improves BSS over `ridge`. A Δ that
leaves both arms below the constant is not a gain — it is two failures with a gap
between them, and the report's increment table is there to be read that way.

**Third outcome, and the one to watch for.** If `exogenous_spf` *inverts* on
separation (bear − bull positive) the way both market arms did, that is a third
independent replication of [KB-024]'s mechanism — stress reads bearish, stress
mean-reverts at 10–20d — and it would mean the SPF anchor is riding the same
contrarian relationship rather than carrying information of its own. Record it as
a replication, not as a new finding.

**Read regardless of the verdict** — the pooled per-input table, which is the
only place this harness can say anything about the branch's actual thesis:
`spf_policy_path` (does the consensus policy path pay at all?), `spf_staleness`
(does a stale anchor behave differently from a fresh one — the closest observable
proxy this harness has for the drift mechanism), and the sign stability of the
three revision columns.

**What the KB entry says either way.** It must carry the scope sentence: this
scored the branch's deterministic, point-in-time half; the SPF-vs-SEP gap and the
FOMC-drift layer were excluded as leakage, so a null closes *the SPF anchor as a
directional input* and leaves the expectations-gap mechanism untested. Without
that sentence the entry would read as a verdict on Phase 19, which it is not.

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

**Reuse the arm machinery — one book per prediction arm.** The pipeline already tags predictions `arm ∈ {market, exogenous, kimi}`. Give **each arm its own paper book** (plus the benchmarks) → P&L becomes a new axis of the existing A/B: *whose predictions actually make money*, not just who is best-calibrated. This is nearly free — it's the same `calibration_by_arm` pattern applied to a ledger.

**Architecture (mechanical v1 — deterministic, no new LLM calls).**
```
Existing dated predictions  (results/**/<date>-*-macro.md, per arm)
        + conditional.py     (per-asset p10/25/50/75/90 forward-return dist by macro bucket)
        + regime.py          (4-state HMM posterior → risk-on/off gate)
        + confidence         (Kimi ensemble-agreement → size scalar)
                │
        sizing.py  (FIXED rule):  expected return + dispersion per asset
                                  → vol-targeted / fractional-Kelly target weights
                                  → clamp to risk limits (max weight, gross cap, vol target)
                │
        book.py    (ledger):  positions, cash, NAV in EUR; yfinance close fills;
                              transaction-cost model (bps); decision log per rebalance
                │
        rebalance.py (weekly, matches note cadence):  targets → trades → new NAV
                              benchmark NAV (ACWI, 60/40) computed alongside
                │
        report:  NAV curve, CAGR, vol, Sharpe/Sortino, max DD, turnover, hit-rate,
                 excess-return + information ratio vs benchmark, per-arm comparison
```

**Universe (small + fixed) — the book trades what the pipeline *predicts*, not the TR sleeves.** Corrected in `portfolio/DESIGN.md` §2: the pipeline emits biases for {S&P 500, Gold, Bitcoin, 10Y yield, WTI, DXY}, so the book must trade *those* or the P&L isn't testing the signal. **v1 tradeable universe = {S&P 500, Gold, Bitcoin, 10Y-via-bond-proxy (IEF, sign-inverted)}**; WTI and DXY excluded from v1 (poor fits for a cash book — futures roll / FX). Base currency **USD** (removes FX noise from the edge measurement; EUR is a WP-20.E realism concern).

**Sizing input is already built.** `conditional.py` emits per-asset percentile forward-return distributions per macro bucket — i.e. **expected return *and* dispersion**, exactly a vol-target / fractional-Kelly input. The regime posterior gates gross exposure (risk-on/off); ensemble-agreement confidence scales size. v1 is mostly *wiring existing outputs into a sizing rule and a ledger* — estimated ~1 week, no new model calls.

**Work packages (cheap-first; prove the slice before generalising).**
1. **WP-20.A — Design & scope lock (design only). ✅ Done** (2026-08-19 → `.macro-assist/portfolio/DESIGN.md`). Locked: **vol-target inverse-vol sizing** (Kelly rejected — too sensitive to our weak point estimates, KB-007/013); **v1 universe = {S&P 500, Gold, Bitcoin, 10Y-via-IEF}** in **USD** (corrects the sketch's TR-sleeve universe — the book trades what the pipeline predicts); the seven-step deterministic sizing rule (§3), the ledger contract (§4), benchmarks = buy-and-hold equal-vol basket + 60/40 + ACWI with **information ratio** the headline metric (§5), per-arm books reusing the arm machinery (§6), forward-only + shakedown-backtest-only discipline (§7), weekly cadence (§8), and the pre-committed go/no-go bar + kill (§9). Four open constants deferred to WP-20.B/C (§10: vol estimator, bond proxy, cash rate, Neutral handling — leans stated).
2. **WP-20.B — The book (deterministic, no LLM). ✅ Done** (2026-08-19 → `.macro-assist/portfolio/book.py` + `__init__.py`, 13 tests in `test_book.py`, all green; 407 total collected). **Instrument-agnostic, sleeve-tagged ledger** (deliberate design choice — corrects nothing but *enables* the sector/materials-ETF option the user asked to keep open: any instrument registers with `{ticker, asset_class, currency, cost_bps}`, positions carry a `sleeve` tag, and `exposure_by_sleeve` attributes value per sleeve — so a future sector sleeve is additive and independently A/B'd, never contaminating the macro-signal measurement). The book **executes** target weights and enforces **no** risk limits (that is `sizing.py`'s job — clean separation). Covers valuation (NAV / gross / net / per-sleeve), long+short, close-out of omitted instruments, per-instrument bps costs, leverage-as-negative-cash, daily marking, JSON round-trip, and a `buy_and_hold` benchmark helper (a Book rebalanced once then marked forward). No network — prices are passed in `{name: price}`; yfinance fetching is deferred to WP-20.D. **Sector-ETF verdict (design note):** trading finer instruments off the *same* index read would conflate signal-edge with a hand-coded macro→sector heuristic (unattributable); the honest path is a separate, independently-scored sector *sleeve* added under WP-20.D, which the ledger now supports for free.
3. **WP-20.C — Sizing rule (deterministic, no LLM). ✅ Done** (2026-08-19 → `.macro-assist/portfolio/sizing.py`, 17 tests in `test_sizing.py`, all green; 424 total collected). Implements the DESIGN §3 seven-step vol-target rule as a **pure function of already-extracted pipeline numbers** (no model objects, no network — point-in-time by construction; `rebalance.py`/WP-20.D does the extraction). `AssetSignal` (bias, confidence, HAR-RV σ, conditional-dist σ, `invert_sign`) + `RegimeState` → `size_positions()` → `SizingResult` (weights that feed straight into `book.rebalance`, plus a per-asset `AssetTarget` audit trail for the decision log). Direction from bias with **10Y sign-inversion** (Bullish yield ⇒ short the bond proxy); confidence clamped to [0,1]; **risk σ = HAR-RV cross-checked against conditional-dist spread** (default `risk_blend="max"` — respect the larger dispersion); **missing distribution after fallback ⇒ abstain** (DESIGN §3 step 3); inverse-vol pre-weight `d·c/σ`; **regime gate** `g = 1 − P(High-Vol states)`; **exact ex-ante vol targeting** to `vol_target·g`; hard clamps (per-asset `MAX_WEIGHT=0.35`, `GROSS_CAP=1.5`). Every knob in one `SizingConfig`. **Locked §10 open decisions:** vol estimator = conservative `Σ|w|σ` (no diversification credit); Neutral = **flat** (honest abstention); bond-proxy/cash-rate are `rebalance.py` wiring choices (lean IEF / 0%), not sizing-internal. **One deliberate deviation from the DESIGN *numbering* (documented in the module):** the regime gate is folded into the vol-target rescale as an effective target `vol_target·g` rather than applied as a separate pre-rescale step — applying it before an exact rescale-to-target would mathematically cancel it (num + denom both scale with g). Same intent, correct behaviour. Per-arm book instantiation ({market, exogenous, kimi} + benchmarks) is deferred to WP-20.D wiring (it needs the note-extraction path, not sizing math).
4. **WP-20.D — Weekly driver (rebalance.py). ✅ Done** (2026-08-19 → `.macro-assist/portfolio/rebalance.py`, 10 tests in `test_rebalance.py`, all green; 434 total collected). The wiring layer: committed note → `AssetSignal`s → `size_positions` → `book.rebalance` + equal-vol buy-and-hold benchmark → persisted ledger + markdown report. Same testability split as book/sizing: the risky logic (note parsing, instrument mapping, signal assembly, benchmark weighting, `advance_books` orchestration) is **pure and injected with prices/regime** (fully offline-tested); the network/model bits (`fetch_prices_and_har`, `live_regime`, `run`) are **lazy-imported** and isolated. **Extraction (point-in-time):** bias/confidence from the predictions table; **conditional σ parsed from the driver prose's "P25–P75 x%/y%" band** (IQR→σ annualized — exactly the distribution the note author saw, no table reload; a band-less row ⇒ σ=None ⇒ honest abstention); **HAR-RV σ recomputed from yfinance history ≤ t** (loosened notes carry no structured vol block); **regime gate = full point-in-time** — `live_regime` reconstructs the regime the pipeline's way (ALFRED-vintage `historical_snapshot(t)` → `regime_features` → the fitted HMM `predict_regime`), builds a `RegimeState` from the posterior + `label_states`, and gates on High-Vol mass; guarded so a missing model artifact / `FRED_API_KEY` / network failure degrades to gate 1.0 (logged in the decision record), never crashes the run. Locally (no FRED key) it degrades as designed; in CI (key present, `data/regime_model.pkl` resolves) the full path engages. **v1 universe wired** = {S&P 500 `^GSPC`, Gold `GC=F`, Bitcoin `BTC-USD` (30 bps), 10Y→`IEF` sign-inverted}; WTI/DXY excluded. **Live smoke test on the 2026-08-19 note passed** end-to-end (real yfinance prices): Gold the sole actionable name (Bullish + band) → sized to the 0.35 clamp; S&P/BTC Neutral and 10Y band-less → abstain; benchmark = equal-vol basket of all four; report + ledger JSON emitted. **Workflow shipped:** `.github/workflows/portfolio_rebalance.yml` — weekly (Mon 07:45 UTC, after the daily note + scoring job), loops `python -m portfolio.rebalance --arm {market,exogenous,kimi}` (each skips gracefully with no note), passes `FRED_API_KEY` for the gate, commits `results/portfolio/*`; `workflow_dispatch` accepts a `date` input for manual/backfill runs. Entry point verified end-to-end (`python -m portfolio.rebalance` resolves all imports from `.macro-assist/` cwd; clean no-op + exit 0 on a dateless future run). **Go/no-go after ≈1 quarter:** does any arm's book beat the buy-and-hold basket on information ratio at acceptable drawdown? **Only WP-20.E (live broker) remains — deferred, gated on this forward run showing edge.**
5. **WP-20.E — Live broker integration (DEFERRED, gated on WP-20.D showing edge).** Only once a book demonstrably beats the benchmark: adapt `book.py`'s trade interface to a real API. **Broker research (2026-08-19):** paper-first on simulated fills; when live, **IBKR** (mature REST/Python API, widest asset universe, free paper account to build against; caveat — IBKR Ireland ⇒ manual `Anlage KAP`, no auto-Abgeltungsteuer) or **Smartbroker+** (German-domiciled/BaFin, auto-tax, REST API ~29.90 €/mo, younger). Keep **Trade Republic as the general deposit** (no official trading API); open the API-capable account separately. *This is the reason v1 is broker-agnostic paper — a real broker is a later bet, not a v1 dependency, so a v1→v2 sizing change is a code edit, never a broker migration.*

**Kill criteria (pre-committed).** v1 is measurement on a virtual book → near-zero risk; the failure mode is *building without a benchmark* or *tuning a backtest*, both explicitly out of scope. Cut the phase if, after ~1–2 quarters forward, **no arm's book beats buy-and-hold ACWI on risk-adjusted return.** A calibrated-but-unprofitable result is itself a valuable KB finding (it would confirm edge < costs). Modular/removable like Phase 19: one `portfolio/` directory + one workflow + a ledger file; the prediction pipeline is untouched.

**Branch strategy.** Develop on `feature/paper-portfolio` off `main`. Purely downstream of the prediction arms — it *reads* their notes and never alters them; integrates only at WP-20.D via its own workflow. Start with WP-20.A (design), then the WP-20.B accounting core in isolation before any sizing logic.

**Experimental model arm — Kimi K2.6 ensemble (INTEGRATED into `main`, modular).** A second use of the arm A/B machinery, aimed at the **confidence** problem (KB-007: the market arm's self-reported `confidence_pct` is clamped 50–80 and non-discriminative). `.macro-assist/kimi_arm.py` reads the *same* daily payload the market model sees (`results/llm_payload_preview/<date>.md`), runs **Kimi K2.6** (Moonshot Anthropic-compatible endpoint, thinking disabled — it defaults ON and both breaks forced tool_choice and eats the token budget) **N times**, and derives confidence from **agreement across samples** (self-consistency): unanimous → high & *un-clamped* (33–100%), split → **Neutral** (honest abstention). Emits an `arm: kimi` note that rides the generic arm hooks → `calibration_by_arm` shows **market vs exogenous vs kimi**. First manual run (2026-07-31, n=8): 4/6 Neutral, Gold Bull 62%, **10Y Bull 88%** (converges with the market + exogenous arms' best asset). Runs daily via `kimi_arm_daily.yml` (Mon–Fri 07:05 UTC, after the market run commits the preview); needs `MOONSHOT_API_KEY`. **Modular/removable (grep `KIMI-ARM`):** soft-kill = disable `kimi_arm_daily.yml`; hard-kill = delete `kimi_arm.py` + its test + both kimi workflows + `*-kimi-macro.md`/`*__kimi.json`. **What it proves vs not:** the mechanism (discriminative, grounded, abstaining confidence) is demonstrated; whether that confidence is *calibrated* (does 88%-agreement out-hit 62%?) is the forward question the daily accumulation + `calibration_by_arm` will answer.
---

## Directional Product Validation (Phase 21) — *is this task learnable at all?* ✅ COMPLETE

> **Resolved 2026-09-04 — the answer is no, and the directional product is cut.**
> [KB-024]: neither a ridge nor a GBM beats a constant `always_bullish` on this
> payload, and both invert exactly the way the LLM does. WP-21.A ✅ ·
> WP-21.B ❌ superseded · WP-21.C ❌ closed · **WP-21.D → cut, shipped as v1.6** ·
> WP-21.E queued · WP-21.F ✅ both remaining directional arms stood down ·
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

### Why not a neural network (decided 2026-09-03 — recorded so it is not re-litigated)

The instinct behind the proposal is right: this *is* a weighting and
data-quality problem, and an LLM is structurally a poor weigher — it has no
gradient, no memory of which input paid off, and its effective weights are
whatever the prompt emphasised plus its priors. `load_accuracy_context()` is a
very lossy substitute for an update step. The remedy, however, does not scale to
a learned per-input model, for three reasons this project has already measured:

1. **Effective sample size, not row count.** Full-panel coverage is bounded by
   the youngest inputs (reverse repo meaningful from ~2013, Bitcoin from 2014,
   TIPS/breakeven from 2003, free-FRED HY OAS truncated to ~2023 — see the note
   in `refit_models.py`). That is ~3,000 business days ⇒ **~150 non-overlapping
   20-day windows**, across 6 assets that collapse to roughly 3 independent
   factors [KB-009: the equity complex is ~one factor]. Low hundreds of
   effective examples against 36+ inputs is where a network learns the sample.
2. **The small version was already run, twice, and said "fewer weights."**
   [KB-002]: a 6-scheme weight ablation over 18 years found `autocorr`'s weight
   contributed nothing (identical to 3 d.p.), `correlation`'s weight was
   *actively harmful*, and the winner tied a 2-parameter 50/50 blend within
   noise — the data honestly supported about **two** weights. [KB-016]: the
   equal-weight continuous blend *degraded* the validated flag; the correct
   adoption form was a discrete **mode** (an OR), not a weight.
3. **"An update step each time" is the worst case here.** At a 20-day horizon
   each new day contributes ~1/20 of an independent observation, and macro is
   non-stationary — so an online learner tracks the most recent regime. That is
   precisely the mechanism [KB-023] just caught fooling a block-switched A/B.

**What survives the objection** is the cheap version: a *regularised* model
(ridge/logistic + a small GBM) fitted point-in-time in the harness that already
exists. It answers the same question — what is each input worth, measured
against outcomes — at a model complexity the sample can support, and it doubles
as the missing benchmark. That is WP-21.A. A more expressive model is
reconsidered **only if** WP-21.A shows an edge to be expressive about.

### WP-21.A–D — the learnability test, and the cut *(detail archived 2026-09-04)*

Method, full numbers and the kill-criterion reasoning →
[Project_Development_Archive.md](Project_Development_Archive.md). The measured
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
indicator search is meant to run through the same door. Three things must not
drift — the pre-committed bar, the shared call set, and the rule that an input
has to be unrevised to enter the panel at all.

### WP-21.E — Bounded, pre-registered indicator search *(queued, blocks nothing)*

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
3. **The bar is the one already written.** Same `verdict()` clause as WP-21.A
   (n ≥ 30 decisive, hit-rate > 0.52, and BSS > 0 or an `aligned` ordering), on
   **sealed holdout data** — a slice held out before the family is chosen, not
   after. Clearing it on the training panel is not a result.

If a family clears that bar, the column comes back — with the conditional
distribution published underneath it. If none does, WP-21.E is a KB negative and
the search closes for good.

### Phase 21 — execution order and wind-down *(complete; detail archived 2026-09-04)*

A → D ran in that order and closed the phase. Two follow-ons shipped with it:

- **WP-21.F ✅ — the two remaining directional arms stood down** (2026-09-04).
  The kimi and exogenous stages came out of `pipeline.yml`; both keep
  `workflow_dispatch` and **nothing was deleted**. The two closures are different
  claims and the distinction matters: kimi's *target* disappeared (it calibrated
  a `confidence_pct` that v1.6 cut), while the exogenous arm's *comparator*
  disappeared — its mechanism was never actually tested. The two ways back are
  recorded under Phase 19, and **(a) has since been taken → WP-19.E**.
- **WP-21.G ✅ — the scoring loop wound down** (2026-09-04). The feedback loop
  (`load_accuracy_context()`) is deleted, not disabled. The scorer keeps running
  until the last v1.5 note's T+20 window resolves ~2026-10-02, printing a
  `DIRECTIONAL RECORD CLOSED` banner when it does — then stage 3 comes out of
  `pipeline.yml`. The readers stay: they hold the evidence base for
  [KB-007]/[KB-011]/[KB-022], which has to stay reproducible.

The archive carries the rest — why the version gate did *not* stop the arms
(neither stamps an `agent_version`, and silently defunding a running experiment
through a constant it never opted into would be the wrong mechanism), and why the
Phase-20 stage is deliberately left running against a withdrawn input.
