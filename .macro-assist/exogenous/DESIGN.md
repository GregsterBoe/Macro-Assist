# Exogenous Information Engine — Design (WP-19.A, target-lock)

Design/target-lock for Phase 19 (see `Project_Development.md`). This is the
**locked contract** the WP-19.B vertical slice builds against. Code lives beside
this file in `.macro-assist/exogenous/`.

Decisions locked 2026-07-14:
- **First slice:** monetary / rates-expectations branch.
- **Primary success bar:** a scored **asset directional lean**, judged by the same
  Brier / commitment metric and A/B'd against the market-only arm.

---

## 1. Target (what this branch produces)

A daily-or-cadence **structured brief** whose *scored* payload is a **directional
lean on the assets monetary information most directly drives**:

- **Assets in scope for the slice:** `10Y Treasury yield`, `DXY`, `gold`
  (three of the six the market-only pipeline already forecasts — so the A/B is
  head-to-head on the *same* targets).

The brief also carries **non-scored context** — net policy stance, the
expectations-gap read, and an optional catalyst→exposure note — but the go/no-go
gate is measured **only** on the asset lean. Context that never earns a place on
the scoreboard is cut (Phase-16/18 discipline).

**Explicitly NOT the target:** an index-level (SPX) up/down call, or any lean that
re-derives from prices. Market data is a *flagged optional comparator*, never a
core input (see §6).

## 2. The three data contracts (L1 → L2 → L3)

Fixed schemas at every level; the per-branch token cap on the L2 brief is what
keeps the payload bounded as branches are added (total ≈ N × cap).

### L1 — Evidence item (cheap-model extraction, one per salient fact)
```
Evidence:
  claim:            str              # the factual/interpretive statement
  source_type:      enum             # fomc_statement | fomc_minutes | speech | calendar | consensus
  source_id:        str              # url / doc id (provenance)
  published:        date             # point-in-time gate key (§6)
  stance:           enum             # hawkish | dovish | neutral   (monetary domain)
  magnitude:        float 0..1       # salience / strength
  affected_assets:  list[str]        # subset of {10Y, DXY, gold}
  extractor_conf:   float 0..1
```

### L2 — Branch brief (bounded analyst output; HARD CAP ≈ 600 tokens)
```
BranchBrief:
  branch:            "monetary"
  as_of:             date
  net_stance:        {label: hawkish|dovish|neutral, score: -1..+1}
  what_changed:      str             # vs the previous brief (bounded)
  expectations_gap:  str             # our read vs consensus / survey path
  drivers:           list[str]       # top cited evidence, each -> source_id
  asset_implications:{ 10Y:{bias,confidence}, DXY:{...}, gold:{...} }
  brief_confidence:  float 0..1
```

### L3 — Exogenous output (scored artifact; for the single slice L3 ≈ lift L2's
`asset_implications` into the scored-lean shape; multi-branch L3 reconciles briefs)
```
ExoOutput:
  as_of:      date
  arm:        "exogenous"                       # A/B tag (§4)
  leans:      { asset: {bias: Bullish|Bearish|Neutral, confidence: 0-100,
                        rationale: str, citations: list[source_id]} }
  regime_note:  str                             # non-scored context
  scenario_map: list[{catalyst, exposure}]      # optional, non-scored
```

## 3. Pipeline (L0–L4) for the monetary slice

- **L0 adapters (deterministic):** FOMC statements + minutes + speeches (Fed site)
  for the *evolving* signal, anchored to two **free, non-market, point-in-time
  consensus benchmarks** (see §6.5). Normalise, timestamp, dedup. Point-in-time
  enforced here.
- **L1 extract (cheap model):** each document → `Evidence[]` with a
  hawkish/dovish stance + salience. Deterministic transforms for numeric calendar
  rows.
- **L2 analyst (bounded):** aggregate recent, non-stale evidence → the capped
  `BranchBrief` (net stance, what changed, expectations-gap, asset implications).
- **L3 synth:** lift `asset_implications` → `ExoOutput.leans` for {10Y, DXY, gold}.
- **L4 score:** reuse `score_predictions.py` (directional at t5/t10/t20) +
  `summarize_accuracy.py` (Brier/BSS/ECE + `commitment_by_arm`) on the arm-tagged
  leans.

## 4. Scoring & the A/B mechanism (L4)

Reuse the existing machinery unchanged:
- Tag each exogenous output with `arm: "exogenous"` (frontmatter / score-file
  field), exactly as `profile` tags the loosened arm today. **BUILT (WP-19.B):**
  `score_predictions.py` now stamps `arm = fm.get("arm", "market")` (every existing
  market-only note defaults to `"market"`, non-breaking); `synth.render_exo_note`
  emits the exogenous leans with `arm: exogenous` frontmatter + the same
  `### 5-Day Predictions` table the scorer already parses.
- `calibration_by` / `commitment_by_arm` already split by an arbitrary field →
  extend them to split on `arm` so the report shows **exogenous vs market-only**
  side by side on {10Y, DXY, gold}.
- **Baseline = the market-only pipeline's leans on the same three assets** over
  the same period (not the pooled all-asset baseline — the comparison must be
  asset-matched to be fair).

## 5. Go / no-go bar (KB-style, pre-committed)

On {10Y, DXY, gold}, the exogenous arm must reach **parity-or-better vs the
market-only arm**:
- **Primary (n≥30 decisive):** `BSS(exogenous) ≥ BSS(market-only)` with
  `ECE(exogenous) ≤ ECE(market-only)`.
- **Early read (low n, the KB-011 metric):** `net_decisive_edge(exogenous) ≥
  net_decisive_edge(market-only)` **and** `wrong_decisive_rate(exogenous) ≤`
  that of market-only — i.e. it commits at least as well while using *no* price
  information.
- **Kill:** if after the slice **plus 1–2 further branches** it cannot reach
  parity, cut the whole Phase-19 branch. Adding orthogonal-but-worthless
  information to a below-chance system (KB-007) is a net negative.

Record the result as **KB-012** when the slice has data.

## 6. Two honest constraints that shape everything

1. **Market-light tension.** The cleanest "consensus" for rates is the
   market-implied path (fed-funds / SOFR futures) — but that is market data, and
   using it would let the arm secretly re-derive from prices and contaminate the
   A/B. So the slice uses the two **non-market** consensus benchmarks in §6.5
   (economist survey + Fed projections) as the core anchor; the market-implied path
   may appear **only as an explicitly-flagged optional comparator**, never a core
   input. Honor this or the "no market data" claim (and the A/B) is a lie.
2. **LLMs cannot be cleanly backtested on dated public text.** The extraction/
   analyst models were trained on historical FOMC documents and *know what happened
   after* a given historical date — so a historical backtest of this branch is
   leakage-prone and cannot be trusted for the Brier gate. **Validation is
   forward/live** (accumulate arm-tagged leans going forward, like the loosened
   A/B); historical runs are for **pipeline shakedown only, clearly flagged**. This
   sets timeline expectations: the go/no-go read is weeks-to-months out, and the
   KB-011 commitment metric is the early tell.

## 6.5. Data sources — LOCKED (researched 2026-07-14, zero paid deps)

Two independent, **free, official, non-market, point-in-time** consensus
benchmarks — and the **gap between them is itself an expectations-tension signal**
(economists disagreeing with the Fed's dots):

| Role | Source | Access | Cadence | Point-in-time? |
|---|---|---|---|---|
| **Economist consensus** | Philadelphia Fed **Survey of Professional Forecasters (SPF)** — TBOND (10Y), TBILL (3M), UNEMP, CPI, RGDP | free Excel download (Philly Fed "real-time data research") | quarterly (since 1968) | **yes** — each row tagged by survey quarter |
| **Policymaker consensus** | FRED **Summary of Economic Projections (SEP / "dot plot")** — `FEDTARMD` (median fed funds) + release `rid=326` (63 series) | **existing `fredapi` adapter — no new dep** | quarterly (Mar/Jun/Sep/Dec) | yes |
| Evolving signal | FOMC statements / minutes / speeches | Fed website (free text) | ~monthly | yes (dated) |

- **New plumbing = one small SPF Excel adapter** (download + parse the relevant
  worksheet with pandas/openpyxl); the SEP side reuses the existing FRED adapter.
- Both consensus sources are **non-market**, so they satisfy §6.1 — futures are
  excluded (or flagged-optional only).
- **Cadence is a feature:** between quarterly consensus updates the benchmark is a
  fixed anchor and the branch tracks *new FOMC communication* against it — exactly
  the expectations-gap mechanism.

**Deferred (do NOT take now):** high-frequency, day-of *release* consensus (exact
CPI/NFP beat-miss) is the one thing not cleanly free — Trading Economics API
(true survey consensus, but free tier heavily sample-limited → paid), or
freemium/scraper feeds (FinanceFlowAPI, Pineify, Apify fed-watch, DataSetIQ) with
ToS/reliability risk. The monetary slice does **not** need it; take that paid
dependency only if a later high-frequency macro-nowcast branch is built.

## 7. Cost & cadence

Cheap-extract / expensive-synthesise (Haiku extract, Opus synth — the existing
split). FOMC docs move ~monthly (8 meetings/yr + speeches), so **refresh evidence
weekly, cache, and only re-synthesise the brief when new evidence arrives** — do
not re-run the full pipeline daily for a signal that changes monthly.

## 8. WP-19.B scope (what "the slice" delivers, next)

L0 monetary adapters (point-in-time): **SPF Excel adapter** (economist consensus)
+ **FRED SEP pull** via the existing adapter (policymaker dots) + FOMC
statement/minutes/speech fetch. → L1 extractor + `Evidence` schema + tests → L2
monetary analyst producing the capped `BranchBrief` (net stance, SPF-vs-SEP gap,
asset implications) + tests → L3 lift to `ExoOutput` → L4 arm-tagging so
`summarize_accuracy` shows the exogenous-vs-market A/B. First milestone: produce
**one** valid arm-tagged `ExoOutput` for today and have it appear as its own arm
in `accuracy_report.md` (unscored until outcomes resolve). Build order within B:
start with the two deterministic consensus adapters (SPF + SEP) — zero LLM, fully
testable — before the FOMC-text extraction/analyst LLM layers.
