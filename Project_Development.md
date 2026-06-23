# Macro-Assist — Project State

## What It Does

A fully automated daily macro intelligence pipeline. Every weekday it fetches economic and market data, passes it to Claude Sonnet for analysis, and writes a structured Markdown note into an Obsidian vault. A separate weekly job scores the directional accuracy of Claude's predictions and feeds those statistics back into the next day's prompt as a self-calibration loop.

---

## Architecture

```
GitHub Actions (daily, Mon-Fri 07:30 UTC)
    collect_and_analyze.py
        -> FRED API          (macro indicators)
        -> yfinance          (prices + sector ETFs)
        -> BLS JSON          (economic calendar)
        -> Supadata API      (YouTube transcripts)
        -> Claude Sonnet     (main analysis)
        -> Claude Sonnet     (adversarial review pass)
        -> Obsidian vault    (output note)
        -> Macro-Assist repo (copy of report for scorer)

GitHub Actions (weekly, Monday 07:15 UTC)
    score_predictions.py    (score past predictions via yfinance)
    summarize_accuracy.py   (aggregate scores -> accuracy_summary.json)
        -> Obsidian vault    (accuracy_report.md)
        -> Macro-Assist repo (.macro-assist/data/accuracy_summary.json)
```

Two repos are involved:
- **Macro-Assist** — code, workflow files, accuracy data, report copies (`results/`)
- **External-Brain** — Obsidian vault; receives the daily note and accuracy report

---

## Data Sources

### FRED (Federal Reserve Economic Data)
Fetched via `fredapi`. 5-year history is pulled for each series to enable historical context (5yr mean, vs-mean comparisons). Every series includes `days_stale` so Claude can apply tiered staleness rules.

| Key | FRED Series | Frequency | Notes |
|-----|------------|-----------|-------|
| `fed_funds_rate` | FEDFUNDS | Monthly | |
| `cpi` | CPIAUCSL | Monthly | YoY % and 5yr mean YoY computed |
| `gdp` | GDP | Quarterly | Often 60-90 days stale |
| `unemployment` | UNRATE | Monthly | |
| `m2` | M2SL | Monthly | YoY % and 5yr mean YoY computed |
| `treasury_10y` | DGS10 | Daily | |
| `treasury_2y` | DGS2 | Daily | |
| `hy_spread` | BAMLH0A0HYM2 | Daily | ICE BofA HY OAS; 5yr mean computed |
| `philly_fed_mfg` | GACDFSA066MSFRBPHI | Monthly | Philly Fed diffusion index; 5yr mean computed |
| `real_yield_10y` | DFII10 | Daily | 10Y TIPS real yield; 5yr mean computed |
| `breakeven_10y` | T10YIE | Daily | 10Y inflation breakeven; 5yr mean computed |

Derived: `yield_curve_spread` = 10Y minus 2Y (computed inline).

### Market Data (yfinance)
90-day history fetched to support technical indicators. A `vix_term_ratio` (VIX / VIX3M) is computed to distinguish acute stress (backwardation) from anticipated volatility (contango). SPX also fetches 1-year history separately for 200dMA calculation.

| Key | Ticker | Notes |
|-----|--------|-------|
| `sp500` | ^GSPC | |
| `nasdaq` | ^IXIC | |
| `gold` | GC=F | |
| `wti_oil` | CL=F | |
| `vix` | ^VIX | |
| `dxy` | DX-Y.NYB | |
| `bitcoin` | BTC-USD | |
| `vix3m` | ^VIX3M | Used only for term ratio; not in snapshot table |

**Sector ETFs** (5-day history): XLE, XLK, XLF, XLI, XLY. Injected as a separate block to enable sector-level divergence analysis in the Equities section.

**Technical indicators** (`## Technical & Positioning State` block): computed for S&P 500, Nasdaq, Gold, WTI Oil, DXY, Bitcoin.
- 14-day Wilder's RSI (Overbought >70 / Oversold <30 / Neutral)
- % distance from 50-day MA (SPX uses the 1y-history MA from `fetch_equity_momentum`)
- 60-day Z-score of today's daily return (|Z| ≥ 2.0 = statistically unusual)

**Notable Moves detector**: flags any asset where `|daily_change| >= 2 * 60d rolling std` AND exceeds a per-asset minimum absolute threshold (e.g. 1.5% for equities, 2.0% for oil). VIX and VIX3M excluded. Output is a `## Notable Moves` block prepended to the prompt.

### COT Positioning (Nasdaq Data Link / CFTC)
Weekly CFTC Commitments of Traders data for WTI Crude and Gold. Computes net non-commercial (speculative) positioning and its percentile vs 1-year range. Injected as `## COT Positioning` block. Pipeline skips gracefully if `NASDAQ_DATA_LINK_KEY` is absent.

### Economic Calendar
- **BLS releases**: fetched live from `https://www.bls.gov/schedule/news_release/schedule.json`. Filters for CPI, PPI, Employment Situation within the next 7 days.
- **FOMC dates**: hardcoded list in `collect_and_analyze.py`. **Must be updated every January.** Source: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`

### YouTube Transcripts (Supadata API)
- YouTube RSS feed (no auth) detects videos published in the last 36 hours per channel.
- Full transcript fetched via Supadata REST API (`x-api-key` header, `text=true`). Free tier: 100 req/month.
- Claude Haiku (`claude-haiku-4-5-20251001`) pre-summarises each transcript into 6-8 macro-relevant bullet points, stripping stock picks and promotions.
- Summaries injected as `## Analyst Video Insights` into the main prompt.

Configured channels (in `collect_and_analyze.py`):
| Channel | ID |
|---------|----|
| Bravos Research | UCOHxDwCcOzBaLkeTazanwcw |

---

## Analysis Model Logic

### Main Pass — Claude Sonnet (`claude-sonnet-4-6`, max 3000 tokens)

The system prompt (`prompts/system_prompt.md`) instructs Claude to produce exactly these sections in order:

1. **Executive Summary** — 2-4 sentences, single most important development
2. **Macro Dashboard** — signal matrix (9 indicators x 4 asset classes: Equities / Bonds / Commodities / Crypto)
3. **Equities** — index moves, risk character, sector divergence, VIX context
4. **Rates & Fed Policy** — Fed Funds trajectory, yield levels, curve shape, real yields vs. breakevens
5. **Inflation & Growth** — CPI trend, GDP + unemployment, M2, stagflation risk
6. **Commodities** — Gold (real yield cross-reference), WTI, DXY context
7. **Portfolio Risk Assessment** — (only when CSV present) position-level macro alignment, concentration, rate/FX sensitivity, one actionable observation
8. **Key Risks & Themes** — 3-5 actionable bullets for the next 1-4 weeks
9. **5-Day Predictions** — directional forecasts table (6 assets, Bias / Target Range / Confidence / Primary Driver)

Key rules baked into the system prompt:
- `days_stale` tiered treatment: ≤14 days = current signal; 15-30 = note date once; >30 = trend only, mark "(stale)" in Dashboard
- Confidence bounded 50%-80% (no false certainty)
- Historical context anchored to `five_yr_mean` when available
- VIX term structure ratio interpreted as acute vs. anticipated stress
- Notable moves opened first in their section
- Economic calendar events flagged in relevant section + Key Risks if within prediction window
- YouTube transcripts treated as secondary source (one citation per section max)

### Adversarial Review Pass — Claude Sonnet (max 600 tokens)

A second Claude call reviews the predictions table against the Key Risks section. Applies a high bar: only lowers confidence (by 5-10pp) and annotates Primary Driver with `[Risk: label]` if a listed Key Risk would make the directional call **outright wrong** if it materialised (not merely uncertain). Confidence is hard-floored at 50% in code regardless of model output. Changes are logged to stdout for inspection in CI.

### Self-Calibration Feedback Loop

`accuracy_summary.json` (tracked in `.macro-assist/data/`) is injected into each daily prompt as `## Your Historical Prediction Accuracy`. Claude is instructed to use directional accuracy stats (only when `n >= 8`) to calibrate confidence. Assets with directional accuracy below 40% are flagged as having systematic bias.

---

## Output Format

Notes are written as Markdown with YAML frontmatter:

```yaml
---
date: YYYY-MM-DD
day: Monday
type: macro-intelligence
tags: [macro, daily-note, economics]
---
```

Path: `Economy/YYYY/MM-Month/YYYY-MM-DD-Weekday-macro.md`

The note appends a **Data Snapshot** section with raw market and FRED tables — Claude never sees this; it is added by `build_note()` after analysis.

---

## Prediction Evaluation

### score_predictions.py

Runs weekly (Monday). Finds all `*-macro.md` reports, parses the 5-Day Predictions table, and scores each prediction at three horizons:

| Window | Trading Days |
|--------|-------------|
| T+5 | 5 (1 week) |
| T+10 | 10 (2 weeks) |
| T+20 | 20 (1 month) |

Only scores reports where the evaluation date has fully passed (plus 1-day buffer). All prices fetched from yfinance — never from the report's own data snapshot.

**Scoring logic:**

| Outcome | Score |
|---------|-------|
| Direction correct | 1.0 |
| Direction wrong | 0.0 |
| Move is flat (below threshold) OR call is Neutral | 0.5 |

Flat thresholds: 3 bps for 10Y Treasury Yield; 0.5% for all other assets.

Output: `results/scores/YYYY-MM-DD.json` per report.

### summarize_accuracy.py

Aggregates all score JSONs into two metrics per asset per window:

- **Overall accuracy** — all calls including Neutral/flat (0.5 = random baseline)
- **Directional accuracy** — only Bullish/Bearish calls with 0/1 outcomes; excludes flat moves and Neutral calls (signal quality metric)

Outputs:
- `.macro-assist/data/accuracy_summary.json` — tracked in git, read by daily pipeline
- `results/accuracy_report.md` — human-readable, copied to vault

---

## CI / GitHub Actions

### Daily (`macro_daily.yml`) — Mon-Fri 07:30 UTC
1. Checkout Macro-Assist (with write token)
2. Checkout External-Brain vault
3. Install Python deps
4. Run `collect_and_analyze.py` (writes note to vault)
5. Copy report to `results/` in Macro-Assist
6. `git pull --rebase --autostash` + commit + push to Macro-Assist

### Weekly (`macro_weekly_scoring.yml`) — Monday 07:15 UTC
1. Checkout Macro-Assist (with write token)
2. Checkout External-Brain vault (as `MACRO_REPORTS_DIR`)
3. Install Python deps
4. Run `score_predictions.py`
5. Run `summarize_accuracy.py`
6. `git pull --rebase --autostash` + commit `accuracy_summary.json` + push to Macro-Assist
7. Copy `accuracy_report.md` to vault

### Required Secrets
| Secret | Used by |
|--------|---------|
| `FRED_API_KEY` | Daily |
| `ANTHROPIC_API_KEY` | Daily |
| `SUPADATA_API_KEY` | Daily (YouTube transcripts) |
| `NASDAQ_DATA_LINK_KEY` | Daily (COT positioning — optional; pipeline skips gracefully if absent) |
| `VAULT_PAT` | Both (External-Brain checkout) |
| `GITHUB_TOKEN` | Both (Macro-Assist push, auto-provided) |

---

## Portfolio Intelligence Module (In Development)

A hands-on investment assistant layer built on top of the macro pipeline. Reads the user's Trade Republic transaction export to surface position-level risk and macro-aligned opportunities.

### Architecture

```
data/tr_positions.csv          (manual export from TR app)
    parse_positions.py
        -> aggregate net positions (BUY - SELL per ISIN)
        -> yfinance current prices (USD→EUR via EURUSD=X)
        -> portfolio summary dict

Daily pipeline (collect_and_analyze.py)
    -> [optional] inject ## Portfolio Positions block into prompt
    -> Claude Sonnet: position risk + macro alignment commentary

On-demand (planned)
    -> opportunity_scan.py      (macro-driven watchlist: 3-5 candidates)
    -> deep_dive.py             (single-stock deep analysis)
```

### parse_positions.py

Located at `.macro-assist/parse_positions.py`. Reads `data/tr_positions.csv` (path overridable via `POSITIONS_CSV` env var).

**What it computes:**
- Net shares per asset (cumulative BUY − SELL)
- Average cost basis in EUR (from transaction amounts)
- Current price in EUR (yfinance; USD assets converted via EURUSD=X)
- Unrealized P&L (EUR + %)
- Portfolio allocation %

**ISIN → ticker resolution (three-layer lookup):**

1. **Hardcoded `ISIN_TO_TICKER` dict** — crypto shortcodes (BTC/ETH/SOL), bonds, ETFs with known EUR tickers, and any manual overrides. Always wins.
2. **Local cache** (`data/ticker_cache.json`) — resolved mappings from previous OpenFIGI lookups. Committed alongside the CSV so CI doesn't re-query.
3. **OpenFIGI API** — free ISIN→ticker lookup (no API key required, 25 req/min). Called automatically for unknown ISINs on first run, then cached. Exchange is selected by ISIN country prefix (US ISINs → NASDAQ/NYSE; IE/FR/DE ISINs → Xetra/Euronext Paris).

**Result:** pushing an updated `tr_positions.csv` with a new position is sufficient — no code changes needed for standard equity ISINs. Bonds, crypto, and ETFs with ambiguous exchange listings remain in the hardcoded dict for precision.

**Hardcoded overrides** (kept in `ISIN_TO_TICKER`):

| Symbol | Asset | Ticker | Currency |
|--------|-------|--------|----------|
| BTC | Bitcoin | BTC-EUR | EUR |
| ETH | Ethereum | ETH-EUR | EUR |
| SOL | Solana | SOL-EUR | EUR |
| IE00B44Z5B48 | MSCI ACWI ETF | SPYY.DE | EUR |
| IE000KCS7J59 | MSCI EM ETF | — (no reliable feed) | EUR |
| FR0010790980 | Stoxx Europe 50 ETF | C50.PA | EUR |
| IE00BJ38QD84 | Russell 2000 ETF | ZPRR.DE | EUR |
| DE0001135226 | German Bund 2034 | — | EUR |
| JE00B588CD74 | WisdomTree Swiss Gold | — | EUR |

**Output:** `format_portfolio_for_prompt()` renders a Markdown table for Claude injection.

**CLI check:** `python .macro-assist/parse_positions.py data/tr_positions.csv`

### Planned Features

| Feature | Status | Notes |
|---------|--------|-------|
| TR CSV parsing + P&L table | Done | `parse_positions.py` |
| Auto ISIN→ticker via OpenFIGI + cache | Done | No code changes needed for new equity positions |
| Inject portfolio into daily macro prompt | Done | `collect_and_analyze.py` |
| Portfolio risk + macro alignment section in note | Done | Conditional section in `system_prompt.md` |
| Opportunity scanner (3-5 watchlist candidates) | Planned (P2) | `opportunity_scan.py` |
| Deep-dive single stock analysis | Planned (P3) | `deep_dive.py`, on-demand script |

### TR CSV Format

Export from Trade Republic app → History → Export CSV. Columns used:

| Column | Used for |
|--------|---------|
| `category` | Filter to `TRADING` rows only |
| `type` | `BUY` / `SELL` |
| `symbol` | ISIN (or `BTC` for crypto) |
| `name` | Display name |
| `shares` | Signed quantity (+buy, −sell) |
| `amount` | Signed EUR cash flow (−buy, +sell) |

Non-trading rows (dividends, interest, transfers, card transactions) are ignored.

---

## Result Versioning

Every generated note and score file carries an `agent_version` field that identifies which pipeline version produced it. This enables the accuracy feedback loop to filter out predictions from older, lower-quality pipeline versions.

### Version Milestones

| Version | Date Range | Capability Added |
|---------|-----------|-----------------|
| v0.1 | 2026-03-12 – 2026-04-02 | Baseline: FRED + market data, signal matrix |
| v0.2 | 2026-04-03 – 2026-04-04 | + Accuracy scoring, feedback loop |
| v0.3 | 2026-04-05 – 2026-04-07 | + Opus, adversarial review, HY/ISM data |
| v0.4 | 2026-04-08 – 2026-04-27 | + YouTube transcript integration |
| v0.5 | 2026-04-28 – 2026-05-16 | + Portfolio positions (TR), Nasdaq data |
| v0.6 | 2026-05-17 – 2026-05-18 | + Sector research, COT positioning |
| v0.7 | 2026-05-19 – 2026-05-24 | + COT XLS fix, Pass 2 numerical anchoring |
| v1.0 | 2026-05-25 – 2026-05-25 | + Multi-agent: MA-1 / MA-2 / MA-3a |
| v1.1 | 2026-05-26 – 2026-05-26 | + MA-3b: synthesis agent |
| v1.2 | 2026-05-26 – 2026-05-28 | + Phase 9/10: HAR-RV vol forecasting + HMM regime classification |
| v1.3 | 2026-05-29 – 2026-05-29 | + Phase 11: conditional return distribution lookup (18-bucket state model) |
| v1.4 | 2026-05-29 – present | + Phase 12: quantitative context block (HAR-RV vol + HMM regime + conditional dist) |

### Output Schema

Every `*-macro.md` file carries `agent_version` in its YAML frontmatter, inserted after `type: macro-intelligence`:

```yaml
---
date: YYYY-MM-DD
day: Monday
type: macro-intelligence
agent_version: v1.4
tags: [macro, daily-note, economics]
---
```

Score JSON files (`results/scores/YYYY-MM-DD.json`) carry the same field immediately after `report_date`:

```json
{
  "report_date": "2026-05-25",
  "agent_version": "v1.1",
  "scored_at": "2026-06-01",
  "windows": { ... }
}
```

`PIPELINE_VERSION` in `collect_and_analyze.py` is the single source of truth for new notes. Bump it when a structural capability change is deployed (new data source, new agent pass, new prompt architecture). Date range in `tag_versions.py` must also be extended for the retroactive tagger to work correctly on future reports.

### Feedback Loop Filter Policy

`MIN_FEEDBACK_VERSION = "v0.3"` in `summarize_accuracy.py`. v0.3 (2026-04-05) introduced adversarial review — the first structural quality gate on prediction output. Reports before v0.3 are scored for historical completeness but excluded from the `feedback_windows` block that drives the daily bias override in `_apply_accuracy_override_structured()`.

`accuracy_summary.json` carries two parallel stats blocks:

- **`windows`** — all scored reports (35 total as of v1.0 launch). Used for human review and historical trend analysis.
- **`feedback_windows`** — v0.3+ only (19 reports as of v1.0 launch). Used exclusively by the daily pipeline bias override. Preferred by `_apply_accuracy_override_structured()` via `acc_data.get("feedback_windows") or acc_data.get("windows", {})` — falls back to `windows` only if `feedback_windows` is absent (e.g. before the first `summarize_accuracy.py` re-run after adding this field).

### Retroactive Tagging

`.macro-assist/tag_versions.py` assigns versions to all existing files. Safe to re-run — skips files that already carry `agent_version`. Run after extending `VERSION_MILESTONES` for a new version boundary:

```
python .macro-assist/tag_versions.py
python .macro-assist/summarize_accuracy.py
```

The second command regenerates `accuracy_summary.json` with the updated `feedback_windows` block.

---

## Annual Maintenance

| Task | When | Location |
|------|------|----------|
| Update FOMC meeting dates | Every January | `FOMC_DATES` list in `collect_and_analyze.py` |

Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

---

## Improvement Roadmap

All phases are implementable at $0 cost using existing API keys (FRED, yfinance) plus one new free provider (Nasdaq Data Link for Phase 3).

### Completed Phases (detail archived)

Phases 1–14 are deployed and stable; their full design notes and Claude Code
prompts now live in [Project_Development_Archive.md](Project_Development_Archive.md).
Measured results live in `Knowledge_Base.md`.

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


## Experimental Track — Emergence & Fragility (Phase 16)

**Strategic context.** Phases 1–15 made the system describe the present accurately and extrapolate it (conditional distributions, regime persistence, momentum). The honest limitation: it *reacts* to the present rather than *anticipating* change, because its inputs are coincident/lagging and its forecasts project the current state forward. This is partly the efficient-market / computational-irreducibility wall — you cannot reliably point-predict an irreducible adaptive system. Two directions survive that critique honestly:

1. **Fragility / phase-transition monitoring** — you cannot predict the trigger, but you can measure the system *losing resilience* as it approaches a tipping point. The empirical evidence for markets is specific: classic *critical slowing down* (rising lag-1 autocorrelation) is **not** a reliable pre-crash signal in equities; **rising variance / variability is.** So this track weights variance- and correlation-based components and treats autocorrelation as secondary/experimental.
2. **Design-by-emergence applied to the pipeline itself** — stop legislating model behaviour with hand-coded prompt rules; define primitive signals as building blocks and let the scoring loop discover which combinations predict. The current 270-line prompt full of overrides is reactive patching ("nerf/buff after observing misbehaviour"); the emergent alternative is to let consequences emerge and prune rules the data no longer supports.

**Branch strategy.** A single long-lived feature branch `feature/emergence`. Everything here is experimental and runs in **shadow mode** (Phase 13.1 mechanism) — it must not alter the production daily note until validated against the Phase 8 backtest harness. Reuse the existing decision gate (≥3pp directional-accuracy improvement at n≥30) plus a new calibration metric (Brier score / reliability diagram) and, for fragility, a lead-time metric. Merge to `main` only per-work-package, only after its gate passes.

**Sources grounding this track:**
- Fragility / rising-variance evidence: [Lack of Critical Slowing Down… yet Rising Variability Could Signal Systemic Risk (PLOS One)](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0144198); [Are Critical Slowing Down Indicators Useful to Detect Financial Crises? (HAL-SHS)](https://shs.hal.science/halshs-01505202); [Critical slowing down… crypto-currency (Royal Society Open Science)](https://royalsocietypublishing.org/rsos/article/7/3/191450/95387/Critical-slowing-down-associated-with-critical).
- LLM prediction levers: [Wisdom of the silicon crowd — LLM ensembles rival human crowds (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11800985/); [ForecastBench (arXiv)](https://arxiv.org/pdf/2409.19839); [Training LLMs to Predict World Events — Mantic/Thinking Machines](https://thinkingmachines.ai/news/training-llms-to-predict-world-events/); [Retrieval-augmented LLMs for Financial Time Series Forecasting (arXiv 2502.05878)](https://arxiv.org/abs/2502.05878).

---

### WP-16.A — Fragility / Phase-Transition Monitor *(starting point)*

**Goal.** A new `.macro-assist/fragility.py` that produces a composite **Fragility Index (0–100)** from data the pipeline already fetches, reframing the product from "what is the price Friday" to "how close is the system to a transition." Injected as a `## Fragility Monitor` block. It is a **risk/resilience gauge, never a directional signal** — it widens ranges and flags tail risk, it does not flip a Bullish/Bearish call.

**Components** (all derivable from the existing `histories` dict in `collect_and_analyze.py`):
- Rolling realized-variance **trend** — slope of 20d realized vol over a 60d window, per asset and aggregate. *(primary — strongest empirical basis)*
- Cross-asset **correlation tightening** — mean pairwise |corr| across SP500/Gold/10Y/DXY/Bitcoin vs 60d baseline; rising = diversification breaking down = system stiffening. *(primary)*
- **VIX term-structure** dynamics — persistence of backwardation (reuse `vix_term_ratio`). *(primary)*
- **HY spread + NFCI acceleration** — 2nd difference (rate-of-change of rate-of-change), not level. *(secondary)*
- Lag-1 **autocorrelation** of returns. *(experimental — flagged; weak in equities per the research, kept for transparency/ablation)*

**Step-by-step from the prototype:**

1. **WP-16.A.1 — Prototype *(Done — branch `feature/emergence`)*.** Pure functions in `.macro-assist/fragility.py`: `realized_variance_trend`, `correlation_tightening`, `vix_term_backwardation` (primary); `level_acceleration` (secondary — HY/NFCI); `lag1_autocorrelation` (experimental, near-zero weight). `fragility_index(histories, hy_spread=, nfci=, weights=) -> dict` returns a 0–100 composite, per-component breakdown, renormalised weights, provisional label (Resilient/Normal/Elevated — calibrated in A.3), and a Rising/Stable/Falling trend (from variance-slope + correlation-delta). Standalone CLI (`python .macro-assist/fragility.py`); **not wired into the pipeline.** Tests: `.macro-assist/tests/test_fragility.py` — 17 pure unit tests via `synthetic.py` (GARCH vol-explosion → Rising; stationary → neutral); all pass.

2. **WP-16.A.2 — Backtest validation (the decision gate). *(Done — branch `feature/emergence`)*.** Implemented as a **pure-numerical, zero-API-cost** harness in `.macro-assist/fragility_backtest.py` (no LLM calls; yfinance only). It pulls full daily history once (2008→today, capped by VIX3M's start), walks the index forward look-ahead-safe (trailing 180-day slice per day, prices aren't revised), and scores it against forward SP500 drawdowns. Metrics: threshold-free Mann-Whitney **AUC** (composite + each component), per-flag **precision/lift/recall**, and **lead time to the drawdown trough**. Tests: `.macro-assist/tests/test_fragility_backtest.py` — 11 pure tests (incl. a planted-signal end-to-end). **Result on 2008-07→2026-06 (4,513 daily readings):**
   - Composite **AUC 0.711** (5-day horizon) / **0.664** (10-day) — real, well above the 0.50 no-skill line.
   - Component breakdown confirms the Phase-16 thesis *partially*: `variance_trend` AUC 0.66/0.62 (works), `vix_term` 0.77/0.67 (strongest, but semi-coincident — VIX backwardation is itself a stress read), `correlation` 0.51/0.55 (**barely above chance — not earning its 0.30 weight**), `autocorr` 0.44/0.50 (**no skill, exactly as the literature predicts** — keep near-zero or drop).
   - The provisional **Elevated** flag (composite ≥65): rare (146/4,513 days ≈ 3%) but high-precision — when it fires, **34% precision / 8.05× lift** for a 5% drawdown within a week.
   - **Lead time (the answer to "reacts vs. predicts"):** Elevated fires a **median 4–6 trading days before the trough**; 76–85% of true positives give ≥3 days of warning. This is genuinely leading, not coincident.
   - The `Rising` trend flag is too trigger-happy (fires ~40% of days, lift only ~1.4) — needs tightening.
   - **Verdict: GO.** The index earns its place; proceed to A.3. Caveats for A.3: (a) overlapping daily windows inflate apparent significance — re-score at the distinct-episode level; (b) reconsider weights — down-weight/replace `correlation`, possibly drop `autocorr`; (c) `vix_term` carries much of the load and is partly circular, so don't let it dominate the composite.

3. **WP-16.A.3 — Recalibrate weights + calibrate thresholds. *(Done — branch `feature/emergence`)*.** Two parts, both on **de-overlapped** metrics (the A.2 caveat: overlapping daily windows inflated the day-level lift). Added episode-level scoring (collapse drawdown labels and alarm flags into distinct runs → caught *crises* vs. true *alarms*) and a non-overlapping AUC (subsample every horizon-th day) to `fragility_backtest.py`, plus a 6-scheme `run_weight_ablation`. **Results (full detail in `Knowledge_Base.md` KB-002):**
   - **Chosen weights `var_led_vix35`:** variance_trend 0.45 / vix_term 0.35 / acceleration 0.15 (reserved for A.4) / correlation 0.05 (token, for graceful degradation) / autocorr 0.0 (dropped). Now `fragility.py`'s `DEFAULT_WEIGHTS`.
   - Ablation settled the A.2 open questions: dropping `autocorr` is **free** (zero effect — it earned nothing), dropping `correlation` **helps** (kept at a token weight only for degradation), `vix_term` is strongest but **capped below variance** (semi-circular). `var_led_vix35` matched the max-skill 2-component scheme on AUC (within noise) with the **best alarm precision** and graceful degradation.
   - **Thresholds** now percentile-anchored to this scheme's own 2008-2026 composite: **Elevated = 90th pct ≈ 56.5**, **Resilient = 40th pct ≈ 24.0** (the Elevated cut *is* the validated top-decile flag).
   - **De-overlapped reality check:** composite AUC 0.72/0.69 (honest n), episode recall ~0.30 (catches ~30% of distinct crises), alarm precision **0.53/0.73**, median lead **4–8 trading days**. A *precise-but-incomplete* tail-risk early-warning, not a comprehensive crash detector — KB-001's 8× lift was overlap-inflated. Tests: `test_fragility_backtest.py` now 18 (added 7 for de-overlap functions); all pass.

4. **WP-16.A.4 — Wire into quant context (shadow first). *(Shadow-wired — branch `feature/emergence`; observation pending)*.** Added a `**Fragility Monitor**` subsection to `quant_context.py` (4th quant subsection, after Conditional) and `raw["fragility"]` to the Phase-14.3 JSONL log via `collect_quant_raw`. Because the live `histories` is only ~90 calendar days (< the validated 180-day window), the block fetches its own ~1y window (yfinance, free; graceful degradation to no-block on failure; **no fetch when histories is absent**, preserving the no-network test contract). **Shadow mechanism — a 3-level `FRAGILITY_MODE` env ladder, default `log`:** `log` = computed + written to the JSONL only, **not shown in the note, zero output impact** (the safe default for running on `main`); `show` = reading rendered into the prompt, no directive; `active` = + the behavioural directive (Elevated → widen Target Ranges + tail-risk bullet, **never** change Bias). The raw reading is logged in **every** mode, so the shadow record accumulates even at `log`. This is designed so the experimental code can live on `main` under a single workflow with no consequence until escalated. Tests: `test_quant_context.py` +10 (mode ladder, no-network guards); all pass. **Next (A.5):** merge to `main` at default `log`, observe the JSONL ≥20 trading days, then escalate `log → show → active` and record findings as a KB entry.

5. **WP-16.A.5 — Monitoring.** Append fragility raw outputs to `results/quant_context_log/` (Phase 14.3 mechanism). After 30+ live days, check whether fragility spikes actually preceded realized vol / drawdowns.

6. **Future extensions.** Feed the fragility index as a 5th HMM regime feature (Phase 10), or add a dedicated "transition-risk" regime state; apply the cross-asset correlation component to the backlog "Correlation Regime" item (Phase 15).

---

### WP-16.B — Loosen Control on the Model *(design-by-emergence)*

**Goal.** Stop manufacturing conviction; let behaviour and signal weights emerge from the scoring loop. The honest critique: the **minimum-conviction rule fights the data** — if the genuine edge is near zero, the system should be allowed to say so, and forcing a directional call to avoid "analysis paralysis" manufactures conviction the evidence doesn't support.

1. **WP-16.B.1 — Conviction floor → config flag, default OFF on this branch.** Allow all-Neutral tables. Re-score and ask: does the calibration of the calls it *does* make improve when calls aren't forced? (Selection effect: fewer, more honest calls should be better calibrated.)

2. **WP-16.B.2 — Calibration measurement (prerequisite for everything in this track).** Add **Brier score** + a **reliability diagram** (predicted confidence vs realized hit-rate) to `summarize_accuracy.py`. Today the system tracks accuracy but not calibration — and accuracy alone rewards overconfidence. Brier becomes the north-star eval metric. (This is the precursor to the Phase 15 "Bayesian confidence calibration" backlog item.)

3. **WP-16.B.3 — Emergent signal weights.** Log, per prediction, which primitive signals were "active" (from the dashboard + quant context). Offline, regress realized outcomes on the active-signal vector to derive a **data-driven signal-weight table** that is injected into the prompt — progressively replacing hand-tuned thresholds. This is "invent the rules, discover the consequences," done with the backtest rather than by intuition.

4. **WP-16.B.4 — Prune prompt rules.** For each hand-coded override, log when it fires and whether firing correlates with better outcomes; retire rules the scoring data no longer supports. Treat the prompt as an emergent system to be tuned down, not a rulebook to grow.

---

### WP-16.C — Research-Grounded LLM Prediction Levers *(research + experiment)*

**Goal.** Answer directly: *what does the research show actually helps an LLM produce powerful predictions from data?* — and adopt the cheap, high-leverage levers. **The user's existing instinct is validated by the literature:** LLMs are weak at raw numerical extrapolation and strong at reasoning over *computed* features + text, so doing the math in Python and reserving the model for meaning-extraction and synthesis is the correct division of labour. The levers below build on that, they don't reverse it.

**What the research says works (strongest → weakest leverage):**
- **Ensembling / aggregation** is the single most reliable lever — LLM ensembles match human-crowd accuracy ("wisdom of the silicon crowd"); single calls are mediocre.
- **Agentic retrieval + supervisor reconciliation** — multiple agents retrieve, a supervisor reconciles disagreement (AIA Forecaster reaches the superforecaster *median*). You already have the multi-agent skeleton (MA-1/MA-3).
- **Analog retrieval (RAG of historical analog episodes)** improves financial forecasting — retrieve similar past macro states and their *narrative* outcomes, not just percentiles. Your conditional-distribution layer is a numeric proto-version of this.
- **Post-hoc statistical calibration** of model probabilities — exactly your accuracy feedback loop; strengthen it via WP-16.B.2.
- **Superforecaster-style prompting** — base-rate-first / reference-class reasoning, decompose into sub-questions, then argue for deviation.
- **Argumentative-coherence filters** — enforce that the stated probability matches the argument; your adversarial pass is a primitive version.

**Concrete experiments (mapped to existing architecture, all validated via the Phase 8 harness + WP-16.B.2 Brier metric):**

1. **WP-16.C.1 — Ensemble the analysis agent.** Run MA-1 N times at temperature (and/or across Opus/Sonnet/Haiku); aggregate predictions (median Bias, mean Confidence, union of Key Risks). Cheapest high-leverage change. Gate: ≥3pp directional **or** meaningful Brier improvement at n≥30.
2. **WP-16.C.2 — Analog-episode retrieval.** Given the current bucket/regime, retrieve the 2–3 most similar historical dates from `point_in_time` history and inject a short narrative of *what actually happened next*. Upgrades conditional distributions from percentiles to reference-class storytelling.
3. **WP-16.C.3 — Base-rate-first prompting.** Restructure so the model states the conditional-distribution base rate **first**, then must argue explicitly for any deviation (extends the existing "reasoning-before-confidence" discipline).
4. **WP-16.C.4 — Brier as the north-star metric.** Adopt WP-16.B.2's Brier/reliability scoring as the primary evaluation across this whole track, since directional accuracy alone rewards overconfidence.

---

### Phase 16 — Suggested Execution Order

| Priority | Work Package | Effort | Prerequisite | Status |
|----------|-------------|--------|--------------|--------|
| 1 | **WP-16.B.2 — Brier / reliability scoring** (north-star metric) | Low | Phase 8 + scoring loop | 🔲 |
| 2 | **WP-16.A.1 — `fragility.py` prototype** (starting point) | Medium | Phase 8 | ✅ Done |
| 3 | **WP-16.A.2 — Fragility backtest gate** | Medium | A.1 | ✅ Done (GO — composite AUC 0.66–0.71, 4–6d lead) |
| 4 | WP-16.C.1 — Ensemble the analysis agent | Low | B.2 | 🔲 |
| 5 | WP-16.A.3 — Recalibrate weights + thresholds (de-overlapped) | Medium | A.2 | ✅ Done (`var_led_vix35`; AUC 0.69–0.72 honest-n, precision 0.53–0.73, 4–8d lead) |
| 5b | WP-16.A.4 — Shadow-wire fragility into quant context | Medium | A.3 | 🟡 Shadow-wired (FRAGILITY_MODE ladder, default `log` = logged-only, zero note impact; safe to merge to `main`) |
| 5c | WP-16.A.5 — Observe JSONL ≥20 days, escalate log→show→active | Medium | A.4 | 🔲 |
| 6 | WP-16.B.1 — Conviction floor → flag, re-score | Low | B.2 | 🔲 |
| 7 | WP-16.C.2 — Analog-episode retrieval | Medium | Phase 11 | 🔲 |
| 8 | WP-16.C.3 — Base-rate-first prompting | Low | B.2 | 🔲 |
| 9 | WP-16.B.3 — Emergent signal weights | High | B.2 + signal-active logging | 🔲 |
| 10 | WP-16.B.4 — Prune prompt rules | Medium | B.3 | 🔲 |

**Order rationale:** the Brier metric (B.2) comes first because every other package is judged by it. The fragility prototype (A.1) is the next concrete build per the brief. Ensembling (C.1) is sequenced early because it's the cheapest, highest-leverage research lever. The heavy "let weights emerge" work (B.3/B.4) comes last — it needs the calibration metric and signal-active logs to exist first.

---

### Active Development Plan *(set 2026-06-16, after WP-16.A.4 shadow-wiring)*

Fragility (16.A) is shadow-wired and merge-safe at `FRAGILITY_MODE=log`. The plan: **merge `feature/emergence` → `main` to start the 20-trading-day shadow clock, then develop the three goals below on parallel branches off `main`.** The shadow observation is passive (zero output impact at `log`), so there is no reason to wait it out — the calendar runs in the background while real work continues.

| Goal | Scope | Branch (off `main`) | Depends on | Cost |
|------|-------|---------------------|------------|------|
| **Goal 1** | **Loosen model control + improve the feedback loop** = execute **WP-16.B** (conviction-floor flag B.1, **Brier/reliability B.2**, emergent signal weights B.3, prune rules B.4). "Improve the feedback loop" *is* B.2 + B.3: add calibration to `score_predictions.py`/`summarize_accuracy.py` and let weights emerge from it. | `feature/loosen-control` | B.2 is the foundation (everything is judged by it) | LLM re-scoring for B.1/B.3 |
| **Goal 2** | **Numerical-layer validation & rigor — start with the HMM regime** (see **Phase 17** below). The fragility index earned trust via a look-ahead-safe backtest; the regime layer never got one. | `feature/regime-validation` | none — independent | **zero LLM/API cost** (yfinance + existing models only) |
| **Goal 3** | **Research-grounded LLM levers** = execute **WP-16.C** (ensembling C.1, analog retrieval C.2, base-rate-first C.3). Sequenced **afterwards**. | `feature/llm-levers` | **B.2** (Brier is the eval metric for the whole track) | LLM calls (ensembling is N× per run) |

**Recommended parallelization while the shadow clock runs:**
- **Start Goal 2 now** — it is fully independent, zero-cost, and mirrors the fragility work that just went well; it is the ideal "keep working during the 20 days" task.
- In parallel, land **WP-16.B.2 (Brier/reliability)** early on `feature/loosen-control`, since *both* Goal 1 and Goal 3 are judged by it. The rest of Goal 1 (B.1/B.3) follows.
- **Goal 3 (16.C) last**, gated on B.2 existing.

Cut each branch from `main` *after* the Phase-16 merge so they don't entangle with the shadow wiring (Goal 2 is independent enough to branch immediately if preferred).

---

## Numerical-Layer Validation & Rigor (Phase 17) — *Goal 2*

**Why.** The fragility index earned its place via a rigorous, look-ahead-safe backtest before we trusted it (Phase 16.A). The **HMM regime layer (Phase 10) never got the same scrutiny**: it is fit and feeds the quant context, but we have not shown (a) that it is computed look-ahead-safe in the daily pipeline, (b) that its state labels actually separate forward returns / volatility out-of-sample, or (c) that 4 states is the right choice rather than an arbitrary one. This track applies the fragility discipline to the existing numerical layers, **starting with regime**. Pure-numerical, **zero LLM/API cost**, on its own branch in parallel with the fragility shadow.

**Branch.** `feature/regime-validation`. **Method.** Reuse the fragility harness patterns (`fragility_backtest.py`): pull-once-and-slice for prices, walk-forward look-ahead-safety, Mann-Whitney AUC, de-overlapped episode scoring, and record results in `Knowledge_Base.md` (KB-003+), kept separate from this plan.

1. **WP-17.1 — Look-ahead audit of the regime pipeline. *(Done — branch `feature/regime-validation`)*.** Built `.macro-assist/regime_backtest.py` (pure-numerical, no LLM): `walk_forward_regime` (refit weekly on the trailing ~5y *strictly before* each date, then single-point classify — mirrors production), `full_sample_regime` (the leaky baseline: one fit over all data, same single-point inference, so the only difference is training data → isolates Baum-Welch fit leakage), and `label_divergence`. Tests: `tests/test_regime_backtest.py` — 7 pure/synthetic tests; all pass. **Audit findings (from reading `regime.py` / `refit_models.py` / `regime_features.py`):**
   - **(a) Live labeling is look-ahead-safe.** The weekly `refit_models.py` fits on the trailing ~5y and labels *today* (the last point) — no future leaks into the live call.
   - **(b) Validation must NOT reuse the persisted model.** Baum-Welch fits forward-backward over the whole window, so a past date's in-sample state is informed by its future. Scoring skill on the persisted full-sample model is leaky → the skill gate (17.2) must use `walk_forward_regime`.
   - **(c) Inference is single-point → the transition matrix is unused live.** `regime_features` returns one (4,) vector and `predict_regime` classifies it alone, so live labeling is effectively a Gaussian-mixture point classification weighted by `startprob_`; the HMM's temporal structure only shapes the fitted emissions. (Worth a direct GMM-vs-HMM and sequence-vs-point comparison in 17.3 — the HMM may be doing no more than a mixture model here.)
   - **Hardening (after first real run):** the first FRED run surfaced two issues — (i) only **531 valid feature-days of 2920** (the 12y matrix truncated to ~2y, likely affecting the production refit too), and (ii) a `GaussianHMM` **singular-covariance crash** on short windows. Fixed the crash: `_fit_robust` adds covariance regularisation + a `full → diag → carry-forward` fallback ladder (with an inference probe, since a degenerate full-cov model can fit but fail in `predict_proba`); added `diagnose_features()` to pinpoint the truncation, tz-normalised the yfinance index, and surfaced valid-day/fallback counts. Tests: 9 (added 2 robustness). The **truncation root-cause still needs the FRED diagnostic** (no key in the agent env).
   - **Truncation root cause (found via `diagnose_features`):** FRED serves the ICE BofA **HY OAS (`BAMLH0A0HYM2`) with only ~3y of history** (785 rows from 2023-06, even with `observation_start=1997`) — a provider/licensing limit, not our code. The HY z-score feature's rolling-mean warmup then pushed the first valid feature day to 2024-06. This also **truncated production training** (`refit_models.py` uses the same series) — the live regime model was training on ~1.5–2y, not 5. *Real shipped bug caught by the validation track.*
   - **Fix (user-approved — switch the regime credit feature to a long-history source):** replaced the regime z-score's input with **`BAA10Y`** (Moody's Baa − 10Y, daily since 1986) in *both* training and live, via a new `baa_spread` series — `refit_models._FRED_SERIES` + `_build_feature_matrix` f2 (`_BAA_STD=0.5`), `regime_features.py` feature [2], and `collect_and_analyze.py`'s FRED fetch (+5yr-mean). **`hy_spread`/HY-OAS is intentionally left untouched** for the daily-note display and `conditional.assign_bucket` (whose tertile thresholds are HY-OAS-calibrated — swapping the series there would mis-bucket). Tests updated; full suite green apart from 3 pre-existing unrelated failures.
   - **⚠ Action after merge:** the persisted `data/regime_model.pkl` was trained on the old (truncated HY) feature, while the live `regime_features` now emits the BAA10Y feature — **re-run `refit_models.py` to regenerate the model** so live inference matches training. Until then the live regime block is inconsistent (this branch only).
   - **Related follow-up:** `conditional.assign_bucket` still keys off the truncated HY-OAS series, so the **conditional-distribution table is also built on ~3y** — fold into WP-17.5 (extend validation to the conditional layer).
   - **Result on full BAA10Y history (→ KB-003):** 2,357 PIT readings (~2016→2026), 472 weekly refits, 8 fallbacks. **Look-ahead-safe labels disagree with the full-sample labels on 70.5% of days**, and the full-sample model is **degenerate (1 distinct label across all days)** because single-point inference is dominated by `startprob_` (a full-sample fit → near one-hot `startprob_` → every day collapses to one state; the walk-forward path shows 4 labels only because each weekly refit's favoured state differs). Confirms (i) validation must be walk-forward, never the persisted model, and (ii) the HMM's transition matrix does no work at live inference — **elevates WP-17.3** (single-point vs. sequence inference, GMM-vs-HMM). The earlier 3.6% figure is void (measured on the ~2y truncated window). **WP-17.1 Done.**

2. **WP-17.2 — Regime skill gate (the WP-16.A.2 analog). *(Done — branch `feature/regime-validation`; verdict NO SKILL → KB-004)*.** Real-data run (18y, 3,922 walk-forward readings ~2010→2026): **Risk-Off→drawdown AUC 0.48/0.47/0.49** (at/below chance) and **High-Vol→forward-vol AUC ~0.50** even though vol-percentile is a *direct input* — the labels don't track their own features. `n_hiconf=3920/3922` (near-universal false confidence) confirms the KB-003 `startprob_`-domination. **The regime block carries no predictive information as wired.** The scorer is sound (planted-signal test passes), so this is real, not a bug. Decision deferred to 17.3: the failure is in the *inference path*, not proven to be the *concept*. Full detail in KB-004. Harness detail below: `regime_backtest.run_regime_skill` (CLI `--skill`, default **18y so the 2008 GFC is in sample**) scores the **walk-forward** label path only (KB-003: never the persisted/degenerate full-sample model): per 5/10/20-day horizon it builds a label→forward-outcome separation table (mean/median forward return + mean forward realized vol per regime), the **AUC of Risk-Off predicting a forward drawdown** (the least-circular test), the AUC of High-Vol predicting top-tercile forward vol (flagged *partly circular* — the vol-percentile feature is an input, like fragility's vix_term), and the Risk-Off→drawdown AUC on **high-posterior (≥0.8) days** as a confidence/calibration check. Verdict keys off the Risk-Off→drawdown AUC (≥0.58 separates / 0.53–0.58 weak → compare to the 17.4 bucket / <0.53 decorative). Tests: `tests/test_regime_backtest.py` +3 (forward metrics, planted-signal recovery, keys); 12 total, all pass. Reproduce: `FRED_API_KEY=… python .macro-assist/regime_backtest.py --skill`.

3. **WP-17.3 — Inference path vs. concept (now pivotal, per KB-004). *(Done — branch `feature/regime-validation`; verdict: INFERENCE was the bug → KB-005)*.** Real-data run (3,922 readings): switching from single-point to **sequence (Viterbi/smoothed) inference** lifts High-Vol→fwd-vol AUC 0.495→**0.646** (floor test passes — labels track inputs again) and Risk-Off→drawdown 0.465→**0.553** (below-chance → weak-but-real). The **HMM-sequence beats the GMM on the drawdown axis** (0.553 vs 0.499) while matching on the circular vol axis, so the temporal structure earns its place *if* inference uses the sequence. The regime layer is **salvageable, not dead** — but modest (0.55 = weak band). Harness detail below: KB-004 showed the labels carry no skill *and don't track their own input features*, traced to `startprob_`-dominated single-point inference. So 17.3 first answers **"is it the inference or the concept?"** `regime_backtest.walk_forward_inference_compare` (CLI `--infer`) does one look-ahead-safe walk-forward, refitting **HMM + GMM** weekly on the trailing window strictly before each date, and labels every day under four inference methods — **`point`** (production single-vector, `startprob_`-dominated), **`viterbi`** (Viterbi over the trailing window → last state, transition matrix acts), **`smoothed`** (forward-backward posterior at the last step), **`gmm`** (plain Gaussian mixture, no temporal structure). `compare_inference_skill` re-scores the 17.2 metric per method; the **floor test** is whether *any* non-point method makes High-Vol track forward vol (AUC ≥0.60 → inference was the problem and the layer is salvageable; else the concept is dead on these 4 features → simplify/drop). Tests: `tests/test_regime_backtest.py` +4 (all-methods, singular survival, skill keys, GMM label reuse); 16 total, all pass. Reproduce: `FRED_API_KEY=… python .macro-assist/regime_backtest.py --infer`.

4. **WP-17.3b — Fix the live inference path (sequence, not single point). *(CANCELLED — KB-006)*.** Was the payoff of KB-005 (sequence inference recovers the regime to AUC 0.55), but WP-17.4 then showed even the salvaged regime loses to a 4-feature rule and adds nothing within stress strata. No point fixing a layer we're dropping.

5. **WP-17.4 — Incremental value over the simpler bucket (keep/cut gate). *(Done — branch `feature/regime-validation`; verdict REDUNDANT → drop the HMM → KB-006)*.** Real-data run: a 4-feature equal-weight **rule-based stress score gets drawdown AUC 0.697 vs the HMM's 0.553**, and within stress terciles the regime adds nothing (mean 0.507; redundancy Spearman 0.336). The HMM regime layer is redundant dead weight — recommendation: **remove the regime block from the daily note** (the macro-stress dimension is already covered better by the Phase-16 fragility monitor). Caveat: the rule is in-sample-standardised (mild look-ahead), but the standardisation-free within-tercile 0.507 + low redundancy carry the decision. Harness detail below: Does the HMM regime (in its best Viterbi inference, KB-005) add drawdown skill beyond simply conditioning on the same macro inputs? The actual Phase-11 `assign_bucket` keys off the truncated HY-OAS series (WP-17.5), so it isn't computable over full history — `regime_vs_bucket` instead compares the HMM against a transparent **rule-based stress score on the same 4 features** (`feature_stress_score`: +nfci_pct, −yc_slope, +credit_z, +vol_pct), reporting Risk-Off→drawdown AUC for each, their Spearman redundancy, and the **regime AUC within stress terciles** (incremental value). Verdict: regime AUC > rule + 0.02 *and* within-stratum mean ≥0.52 → **adds value, fix live inference (17.3b) and keep**; regime ≤ rule and within-stratum ≤0.52 → **redundant, drop the HMM, keep the rule**; else marginal. CLI `--bucket`. Tests: `tests/test_regime_backtest.py` +2 (stress direction, planted keys); 18 total, all pass. Reproduce: `FRED_API_KEY=… python .macro-assist/regime_backtest.py --bucket`.

6. **WP-17.5 *(later)* — Extend to vol_forecast + conditional layers.** Same look-ahead-safe walk-forward + skill scoring for HAR-RV (Phase 9) and the conditional-distribution table (Phase 11). Also fix the conditional layer's truncated HY-OAS input (the `assign_bucket` series only has ~3y — same FRED limit found in WP-17.1).