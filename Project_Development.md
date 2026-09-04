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
| v1.4 | 2026-05-29 – 2026-06-26 | + Phase 12: quantitative context block (HAR-RV vol + HMM regime + conditional dist); Phase 14: weekly refit + monitoring |
| v1.5 | 2026-06-27 – present | + WP-16: run profiles (control/loosened arms), conviction-floor flag, Brier/reliability calibration, base-rate-first |

### Output Schema

Every `*-macro.md` file carries `agent_version` in its YAML frontmatter, inserted after `type: macro-intelligence`:

```yaml
---
date: YYYY-MM-DD
day: Monday
type: macro-intelligence
agent_version: v1.5
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

1. **WP-16.A.1 — Prototype. ✅ Done** (branch `feature/emergence`). Pure functions in `.macro-assist/fragility.py` (`realized_variance_trend`, `correlation_tightening`, `vix_term_backwardation`, `level_acceleration`, `lag1_autocorrelation`) → `fragility_index()` = 0–100 composite + per-component breakdown + Resilient/Normal/Elevated label + Rising/Stable/Falling trend. Standalone CLI; 17 pure tests (`test_fragility.py`). Function/method detail in the code + git.

2. **WP-16.A.2 — Backtest validation (the decision gate). ✅ Done — verdict GO** (→ KB-001). Pure-numerical, zero-API harness `fragility_backtest.py` (pull-once/slice, look-ahead-safe 180d window, Mann-Whitney AUC + precision/lift + lead-time vs forward SP500 drawdowns; 11 tests). **Composite AUC 0.71/0.66 (5/10d); Elevated flag ~34% precision / 8× lift; median 4–6 trading-day lead** — genuinely leading, not coincident. Component reality: `vix_term` strongest but semi-circular, `correlation` barely above chance, `autocorr` no-skill (as the literature predicts). Caveats carried to A.3 (de-overlap the daily windows; down-weight `correlation`/drop `autocorr`; cap `vix_term`).

3. **WP-16.A.3 — Recalibrate weights + calibrate thresholds (de-overlapped). ✅ Done** (→ KB-002). Added episode-level scoring + non-overlapping AUC + a 6-scheme ablation to `fragility_backtest.py` (18 tests). **Chosen `DEFAULT_WEIGHTS` = `var_led_vix35`:** variance_trend 0.45 / vix_term 0.35 / acceleration 0.15 / correlation 0.05 (token) / autocorr 0.0 (dropped). **Thresholds** percentile-anchored: **Elevated ≈ 56.5 (90th pct)**, **Resilient ≈ 24.0 (40th pct)**. De-overlapped honest-n: AUC 0.72/0.69, episode recall ~0.30, alarm precision 0.53/0.73, 4–8d lead — a precise-but-incomplete tail-risk early-warning (KB-001's 8× lift was overlap-inflated).

4. **WP-16.A.4 — Wire into quant context (shadow first). *(Shadow-wired — branch `feature/emergence`; observation pending)*.** Added a `**Fragility Monitor**` subsection to `quant_context.py` (4th quant subsection, after Conditional) and `raw["fragility"]` to the Phase-14.3 JSONL log via `collect_quant_raw`. Because the live `histories` is only ~90 calendar days (< the validated 180-day window), the block fetches its own ~1y window (yfinance, free; graceful degradation to no-block on failure; **no fetch when histories is absent**, preserving the no-network test contract). **Shadow mechanism — a 3-level `FRAGILITY_MODE` env ladder, default `log`:** `log` = computed + written to the JSONL only, **not shown in the note, zero output impact** (the safe default for running on `main`); `show` = reading rendered into the prompt, no directive; `active` = + the behavioural directive (Elevated → widen Target Ranges + tail-risk bullet, **never** change Bias). The raw reading is logged in **every** mode, so the shadow record accumulates even at `log`. This is designed so the experimental code can live on `main` under a single workflow with no consequence until escalated. Tests: `test_quant_context.py` +10 (mode ladder, no-network guards); all pass. **Next (A.5):** merge to `main` at default `log`, observe the JSONL ≥20 trading days, then escalate `log → show → active` and record findings as a KB entry.

5. **WP-16.A.5 — Monitoring.** Append fragility raw outputs to `results/quant_context_log/` (Phase 14.3 mechanism). After 30+ live days, check whether fragility spikes actually preceded realized vol / drawdowns. **Visibility (done):** at `log` mode the reading rendered nowhere, so a run gave no sign of it and the record was only readable by opening the JSONL. `quant_context.py` now exposes two pure formatters over the same `collect_quant_raw()` dict — `fragility_log_lines()` (→ `[FRAGILITY]` / `[FRAG-OR]` one-liners in the daily run's stdout, `WARN` when Elevated or the OR flag fires) and `build_fragility_snapshot()` (→ a `### Fragility Monitor` table in the note's **Data Snapshot**, appended by `build_note()` *after* the LLM call, so the shadow discipline holds: still zero influence on the analysis). No extra compute and no way for the three surfaces to disagree. Tests: `test_quant_context.py` +10.

6. **Future extensions.** Feed the fragility index as a 5th HMM regime feature (Phase 10), or add a dedicated "transition-risk" regime state; apply the cross-asset correlation component to the backlog "Correlation Regime" item (Phase 15).

---

### WP-16.B — Loosen Control on the Model *(design-by-emergence)*

**Goal.** Stop manufacturing conviction; let behaviour and signal weights emerge from the scoring loop. The honest critique: the **minimum-conviction rule fights the data** — if the genuine edge is near zero, the system should be allowed to say so, and forcing a directional call to avoid "analysis paralysis" manufactures conviction the evidence doesn't support.

1. **WP-16.B.1 — Conviction floor → config flag. *(Built — branch `feature/loosen-control`; awaiting floor-off data)*.** **Trace finding:** the conviction floor is **100% prompt-instruction** — nothing in the schema or post-processing rejects/rewrites an all-Neutral table (schema allows `Neutral`; `_apply_accuracy_override` only warns on Neutral high-signal calls; the adversarial clamp only bounds already-directional calls). So the flag is a prompt toggle. **Implementation:** `CONVICTION_FLOOR` env var (default `on` = current behaviour). The four forcing pressures (min-conviction, high-signal MUST-call, contrarian-instead-of-Neutral, and the dynamic accuracy-context language) are wrapped in `<!-- CF:ON/OFF -->` sentinels in both prompt files; `_render_conviction` strips the inactive arm at load (clean A/B), and `load_accuracy_context(floor_on)` softens its language. The note frontmatter records `conviction_floor: on|off`; `score_predictions.py` carries it into the score files; `summarize_accuracy.calibration_by_floor` reports the Brier/BSS A/B once both arms have data. Tests: `tests/test_conviction_floor.py` (16) + 3 in `test_summarize_accuracy.py`. **To run the off arm:** `CONVICTION_FLOOR=off python .macro-assist/collect_and_analyze.py`. **Decision (per KB-007):** does calibration of the calls it *does* make improve when calls aren't forced? Bar: BSS(off) > BSS(on) with ECE↓ at n≥30 floor-off decisive calls. *(Selection effect: fewer, more honest calls should calibrate better.)*

2. **WP-16.B.2 — Calibration measurement (Brier / reliability). ✅ Done** (→ KB-007). Added `calibration()` to `summarize_accuracy.py` (Brier + Brier Skill Score + ECE + confidence-binned reliability diagram, decisive calls only; surfaced in `accuracy_report.md` + `accuracy_summary.json`). 12 tests. **Baseline KB-007: confidence is anti-informative — BSS −0.195 overall (−0.344 feedback-era), decisive calls right only ~36%, below chance and worsening with horizon.** Brier/BSS is now the **north-star eval metric** for B.1/B.3/B.4 + Phase 18 + 16.C (must move Brier, not just accuracy); **elevates B.1** — forcing directional calls likely manufactures the below-chance decisive calls.

   **Commitment metric added 2026-07-14 (→ KB-011):** the decisive-only Brier A/B needs n≥30 decisive calls, which floor-off makes rare (loosened had only 2 after 12 notes), so `commitment_by_arm` in `summarize_accuracy.py` scores the **commitment decision over all resolved calls** — commit-rate, wrong/right-decisive rate, net decisive edge — using the model's `bias` to separate "declined to commit" from "market was flat". Gives a directional read at low n (`accuracy_report.md` → Commitment section; JSON `commitment_by_arm`; 9 tests). **Early read KB-011: loosened commits 20% vs baseline 56% and bleeds less (net edge −0.067 vs −0.125) — thesis holds directionally, but decisive n=2 so "commits better" is not yet shown; verdict still gated on the decisive-only Brier at n≥30.**

3. **WP-16.B.3 — Emergent signal weights.** Log, per prediction, which primitive signals were "active" (from the dashboard + quant context). Offline, regress realized outcomes on the active-signal vector to derive a **data-driven signal-weight table** that is injected into the prompt — progressively replacing hand-tuned thresholds. This is "invent the rules, discover the consequences," done with the backtest rather than by intuition. **Shares its per-prediction logging substrate with Phase 18 and consumes Phase 18's input-value ranking as a prior** (whole-section value from 18.4 → signal weights here); build the logging once for both.

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

> **Execution philosophy (revised 2026-06-27 — loosen prompt testing, keep numeric rigor).** Two classes of change, deliberately treated differently:
> - **Prompt / model-behavior levers** — conviction floor (B.1), prune hard rules (B.4), ensembling (C.1), analog retrieval (C.2), base-rate-first (C.3). These are model-entangled with slow, noisy 5–20-day feedback, so per-lever Brier A/B gating is low-ROI and risks overfitting the prompt to one model. **Apply research-grounded reasonable defaults, bundle them behind one "loosened" config, ship, and monitor the bundle in aggregate** against the KB-007 baseline (is *loosened* better than *current*?). Do **not** gate each lever on n≥30. Keep it one-line reversible.
> - **Calculated / numerical inputs** — input information-value (Phase 18), emergent signal weights (B.3), and the quant layers (17.5). Deterministic and model-independent, so backtests transfer. **Keep the look-ahead-safe numeric testing.**
> - **B.2 (Brier) stays the aggregate north-star** — it now judges the *bundle* (and, via the run matrix, the *model choice*), not each individual lever.
> - **Accepted trade-off:** bundling forfeits per-lever attribution. The run matrix still cleanly separates **model** and **bundle on/off**; it just can't separate the levers *inside* the bundle. That's the deliberate cost of moving fast on the prompt side.
>
> Net effect on the table below: B.1 / B.4 / C.1 / C.2 / C.3 are executed as one **loosened-config bundle on reasonable assumptions** (not sequential gated experiments); B.3, Phase 18, and 17.5 retain numeric rigor; B.2 monitors the aggregate.

| Priority | Work Package | Effort | Prerequisite | Status |
|----------|-------------|--------|--------------|--------|
| 1 | **WP-16.B.2 — Brier / reliability scoring** (north-star metric) | Low | Phase 8 + scoring loop | ✅ Done (baseline KB-007: BSS −0.20 overall, confidence anti-informative) |
| 2 | **WP-16.A.1 — `fragility.py` prototype** (starting point) | Medium | Phase 8 | ✅ Done |
| 3 | **WP-16.A.2 — Fragility backtest gate** | Medium | A.1 | ✅ Done (GO — composite AUC 0.66–0.71, 4–6d lead) |
| 4 | WP-16.C.1 — Ensemble the analysis agent | Low | B.2 | 🔲 (v2 of loosened bundle — deferred; N× cost) |
| 5 | WP-16.A.3 — Recalibrate weights + thresholds (de-overlapped) | Medium | A.2 | ✅ Done (`var_led_vix35`; AUC 0.69–0.72 honest-n, precision 0.53–0.73, 4–8d lead) |
| 5b | WP-16.A.4 — Shadow-wire fragility into quant context | Medium | A.3 | 🟡 Shadow-wired (FRAGILITY_MODE ladder, default `log` = logged-only, zero note impact; safe to merge to `main`) |
| 5c | WP-16.A.5 — Observe JSONL ≥20 days, escalate log→show→active | Medium | A.4 | 🔲 |
| 6 | WP-16.B.1 — Conviction floor → flag | Low | B.2 | ✅ In loosened bundle (floor OFF when `MACRO_PROFILE=loosened`) |
| 7 | WP-16.C.2 — Analog-episode retrieval | Medium | Phase 11 | 🔲 (v2 of loosened bundle — deferred) |
| 8 | WP-16.C.3 — Base-rate-first prompting | Low | B.2 | ✅ In loosened bundle (BR:ON sentinel) |
| 9 | WP-16.B.3 — Emergent signal weights | High | B.2 + signal-active logging | 🔲 (numeric track — keep rigor) |
| 10 | WP-16.B.4 — Prune prompt rules | Medium | B.3 | ✅ In loosened bundle (hard directional overrides pruned via PR:OFF) |

**Order rationale (superseded by the 2026-06-27 execution philosophy above):** the prompt levers B.1/B.4/C.3 now ship together as the **loosened bundle** (run via `MACRO_PROFILE=loosened`, Opus 4.8 main), monitored in aggregate by B.2's Brier A/B-by-profile — not as sequential gated experiments. C.1 (ensembling, N× cost) and C.2 (analog retrieval) are deferred to a v2 bundle. B.3 (emergent weights) and Phase 18 stay on the numeric-rigor track. **Run-config mechanism:** `run_config()` resolves profile + per-lever env overrides; the prompt files carry CF/BR/PR sentinels stripped at load by `_render_prompt`; the note frontmatter records the resolved config; `summarize_accuracy.calibration_by_profile` does the headline A/B.

---

### Active Development Plan *(set 2026-06-16, after WP-16.A.4 shadow-wiring)*

Fragility (16.A) is shadow-wired and merge-safe at `FRAGILITY_MODE=log`. The plan: **merge `feature/emergence` → `main` to start the 20-trading-day shadow clock, then develop the three goals below on parallel branches off `main`.** The shadow observation is passive (zero output impact at `log`), so there is no reason to wait it out — the calendar runs in the background while real work continues.

| Goal | Scope | Branch (off `main`) | Depends on | Cost |
|------|-------|---------------------|------------|------|
| **Goal 1** | **Loosen model control + improve the feedback loop** = execute **WP-16.B** (conviction-floor flag B.1, **Brier/reliability B.2**, emergent signal weights B.3, prune rules B.4). "Improve the feedback loop" *is* B.2 + B.3: add calibration to `score_predictions.py`/`summarize_accuracy.py` and let weights emerge from it. | `feature/loosen-control` | B.2 is the foundation (everything is judged by it) | LLM re-scoring for B.1/B.3 |
| **Goal 2** | **Numerical-layer validation & rigor — start with the HMM regime** (see **Phase 17** below). The fragility index earned trust via a look-ahead-safe backtest; the regime layer never got one. | `feature/regime-validation` | none — independent | **zero LLM/API cost** (yfinance + existing models only) |
| **Goal 3** | **Research-grounded LLM levers** = execute **WP-16.C** (ensembling C.1, analog retrieval C.2, base-rate-first C.3). Sequenced **afterwards**. | `feature/llm-levers` | **B.2** (Brier is the eval metric for the whole track) | LLM calls (ensembling is N× per run) |

**Recommended parallelization while the shadow clock runs:**
- **Start Goal 2 now** — it is fully independent, zero-cost, and mirrors the fragility work that just went well; it is the ideal "keep working during the 20 days" task. *(Update 2026-06-23: Goal 2 regime arc complete — HMM retired, KB-006; remaining is WP-17.5.)*
- In parallel, land **WP-16.B.2 (Brier/reliability)** early on `feature/loosen-control`, since *both* Goal 1 and Goal 3 are judged by it. The rest of Goal 1 (B.1/B.3) follows.
- **Goal 3 (16.C) last**, gated on B.2 existing.
- **Input-value track (Phase 18) is the input-side of Goal 1** — its cheap proxies (18.2/18.3) are zero-cost and can run alongside B.2; its ablation (18.4) and the weighting payoff (18.5 → B.3) gate on B.2. Foundation WP-18.1 (payload preview) is already done on `main`.

Cut each branch from `main` *after* the Phase-16 merge so they don't entangle with the shadow wiring (Goal 2 is independent enough to branch immediately if preferred).

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
open half is the run itself: `Numeric Directional Baseline` on the Actions tab
(`exogenous: true`, the default), then read the two rows against the comparators
and write the result up as a KB entry. Nothing blocks on it.

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
> WP-21.G ✅ scoring loop wound down. Read WP-21.D below for what replaced the
> two columns.

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

### WP-21.A — Numeric directional baseline *(the learnability test — do this first)*

The single highest-value experiment, and mostly wiring: `backtest.py` already
defines the `strategy(snapshot) -> predictions` interface, ships
`strategy_neutral` / `strategy_random_walk` comparators, and leaves
`strategy_existing_pipeline` as an unimplemented stub; `point_in_time.py`
supplies ALFRED-vintage snapshots back to 1997.

- **Build:** `strategy_ridge` and `strategy_gbm` against that interface —
  walk-forward refit, trained only on data knowable at `t`, no peeking.
- **Score:** the same directional metrics the LLM is judged on (hit-rate, Brier,
  BSS, and the KB-022 bias/return separation), over 5–10 years, against
  `strategy_neutral`, `strategy_random_walk`, and always-Bullish.
- **Emit:** per-input coefficients / permutation importances — the detailed
  input-value measurement, grounded in outcomes rather than in the redundancy
  [KB-009] and citation [KB-010] *screens*.
- **Fold in:** the 20-day reversion effect as one candidate feature, validated
  here rather than as a standalone errand.
- **Cost/risk:** zero LLM spend, no new output lever, confounds no running A/B.
- **Decision value — symmetric:** if ridge/GBM cannot beat neutral over 10 years,
  the directional product is dead for every model class and WP-21.C and any
  future network are dead with it. If it can, the result is simultaneously the
  upper bound on achievable skill, the base-rate feed for WP-21.C, and the
  benchmark the LLM arm has never had.

**WP-21.A.1 — The harness. ✅ Done** (2026-09-03 →
`.macro-assist/numeric_baseline.py`, `tests/test_numeric_baseline.py`; +33 tests,
615 green). Everything above is built and tested; what is **not** done is the
run — see "Status" below.

- **Both models, both small.** `fit_ridge` is a standardised L2 logistic
  (scaler inside the pipeline, so it is fitted on the training fold only —
  scaling on the full sample would leak the future's variance into the past);
  `fit_gbm` is a depth-2, 150-tree, lr-0.03 gradient booster. Depth 2 allows
  pairwise interactions and nothing deeper, which is as much as ~150 independent
  windows over ~3 factors [KB-009] can support. `scikit-learn` is now named in
  `requirements.txt` (hmmlearn already pulled it in transitively).
- **Both leaks are closed, and tested as such.**
  1. *Panel leak.* `point_in_time.historical_snapshot()` costs one HTTP call per
     series per date — ~40k calls for a decade of daily walk-forward, which is
     why `strategy_existing_pipeline` was never run. The baseline takes the other
     route to the same guarantee: **only never-revised inputs are eligible**
     (yfinance prices; FRED's market-observed daily series — DGS10, DGS2, BAA10Y,
     T10YIE, DFII10, VIXCLS), so today's vintage *is* the historical vintage and
     no ALFRED call is needed. CPI / payrolls / M2 / WALCL / NFCI / claims are
     excluded **by construction**, and `test_fred_inputs_contain_only_unrevised_series`
     encodes that rule as an assertion rather than a comment. Every FRED series is
     additionally shifted one business day, so a print is only readable the day
     after it lands.
  2. *Label leak.* `walk_forward` embargoes `horizon + 1` trading days: predicting
     on `t` may train only on rows whose forward window closed **strictly** before
     `t`. `test_walk_forward_embargo_excludes_unresolved_labels` spies on every
     training matrix the harness hands the model and asserts it at all three
     horizons.
- **Scored by the production readers, not by a re-implementation.** Calls are
  emitted as score-file-shaped JSON and fed through `score_predictions.score_call`,
  `summarize_accuracy._brier_and_reliability` and `bias_separation.bias_separation`
  — the identical yardstick the LLM arm is held to, so the two can never diverge
  on what counts as a hit. Each model and comparator is a separate `arm`
  (`ridge`, `gbm`, `neutral`, `random_walk`, `always_bullish`), which makes the
  whole comparison a `calibration_by_arm` table for free. Comparators are scored
  on **exactly the model dates** — scoring them on a different sample would repeat
  the [KB-023] error inside the experiment meant to correct for it.
- **Output isolation.** Everything lands in `results/numeric_baseline/`, never in
  `results/scores/`. Dropping simulated arms where `summarize_accuracy.py` looks
  would contaminate the live A/B the moment the weekly job ran; there is a test
  for that too. The raw calls (~30k reports, ~100MB indented) are opt-in behind
  `--emit-scores` and written gzipped — the report and the diagnostics JSON are
  the deliverable.
- **The bar is written down before the numbers.** `verdict()` reports `edge` only
  at n ≥ 30 decisive calls, decisive hit-rate > 0.52, and either BSS > 0 or an
  `aligned` ordering — the same standard as [KB-007] / [KB-022] — and
  `underpowered` rather than `no edge` below n.
- **Two controls, because "no edge" is the result we half expect.** A harness that
  can only ever say "no edge" is indistinguishable from the truth we suspect, so
  the suite plants a learnable signal and requires it to be *found*
  (`test_walk_forward_finds_planted_signal`, >75% hit-rate, informative input
  outweighing the noise input) as well as requiring pure random walks to be
  reported as no edge.
- **20-day reversion is folded in, not chased separately.** `ret_20` is one of the
  own-price features; the report's per-input table carries its mean weight, its
  **sign stability** across refits (a big coefficient that flips sign every quarter
  is a refit artefact, not a finding) and its out-of-sample permutation drop. If
  the effect is real it shows up as a reliably negative, stable weight; if not,
  that is measured in the same pass as everything else.
- **One upstream change:** `bias_separation._compare` / `_section` /
  `bias_separation()` now take `n_perm` / `n_boot` (defaults unchanged, and the
  values actually used are echoed in `params`). Cost is draws × observations, and
  a decade of daily simulated calls is ~20× the daily report's ~2k — the defaults
  turned a research sweep into a coffee break.

**Status: run, read, and written up → [KB-024]. ✅ WP-21.A is closed.**

*The harness outlived the work package.* It is now the repo's general answer to
"is there directional signal in these inputs?", and WP-19.E added the Phase-19
exogenous anchor to it as two more arms (2026-09-04). WP-21.E's indicator search
is meant to run through the same door. What must not drift: the pre-committed
bar, the shared call set, and the rule that a new input has to be unrevised or it
does not enter the panel.

Two runs exist and only the second counts. The 2026-09-03 first read scored the
comparators on 78,656 calls against the models' 75,414 — the [KB-023] error one
level down, and it flattered `always_bullish`, the benchmark the verdict turns
on. **WP-21.A.2 ✅** fixed it (`shared_call_keys` intersects the
(window, date, asset) triples across arms, `restrict_calls` clamps every arm to
them, the report prints the shared n and a ⛔ if arms ever diverge again), and
the **2026-09-04 aligned re-run** on `origin/output` (`b3e4255`) is the
reportable one: all five arms on the same **75,432 calls**, 4,636 dates.

**The answer is no, for every model class tested.**

| Arm | n decisive | hit-rate | Brier | BSS | ECE | separation |
|---|---|---|---|---|---|---|
| `ridge` | 42,043 | 0.530 | 0.271 | −0.087 | 0.119 | inverted |
| `gbm` | 40,173 | 0.526 | 0.264 | −0.059 | 0.103 | inverted |
| `always_bullish` | 61,073 | **0.557** | **0.247** | **−0.000** | **0.007** | n/a |

`always_bullish` — a constant carrying no information — beats both fitted models
on hit-rate, Brier, BSS *and* calibration simultaneously. Both models fail the
pre-committed bar on every clause. `ridge`'s 90–100% confidence bin resolves at
**0.404**; `bear−bull` separation is inverted at **+0.093 (p=0.002, CI [+0.021,
+0.165])** and roughly sextuples from t5 to t20. Mechanism: `drawdown` is the
only input both classes find load-bearing, it is signed *stress → bearish*, and
stress mean-reverts at 10–20 days — so the one stable relationship in the panel
is contrarian and calling it directionally is systematically backwards.
`ret_20` closes the 20-day reversion errand negatively (sign stability 0.778,
the lowest of 20; permutation −0.001).

The alignment fix moved the benchmark, not the conclusion: `always_bullish`
0.560 → 0.557, both models unchanged to three decimals.

Full numbers, caveats and the reproduce recipe: **[KB-024]**.

```bash
python .macro-assist/numeric_baseline.py --start 2005-01-01 --save-panel panel.csv
python .macro-assist/numeric_baseline.py --panel panel.csv --windows t5   # offline re-runs
```

`--no-importance`, `--no-separation`, `--separation-draws` and `--windows` trade
completeness for speed while iterating — a **reported** result uses none of them.

### WP-21.B — Clean arm A/B *(day-alternating assignment)* — ❌ CLOSED, superseded by WP-21.A

[KB-023] made this a prerequisite rather than a refinement: with ~5 independent
21-day blocks in the entire scored history, switching `MACRO_PROFILE` in blocks
spends the whole sample and still confounds arm with market period.

**WP-21.B.1 — Arm-filter the readers. ✅ Done and kept** (2026-09-03 →
`.macro-assist/bias_separation.py`, `.macro-assist/summarize_accuracy.py`;
+19 tests). This work survives the closure: the readers are the historical
record's readers, and they stay correct. Both default to the production `market`
arm (`--arm all` pools deliberately) and emit an `arm_composition` table naming
what was excluded; `calibration_by_profile`, `calibration_by_floor` and
`commitment_by_arm` are scoped the same way, while `calibration_by_arm` keeps
seeing every arm because it *is* the cross-arm comparison. Four defects fixed
beyond the one that prompted the work:

  1. **The date collision.** `observations()` now reads `arm`/`profile` off each
     report as it flattens it; nothing keys on `report_date`. A regression test
     builds the exact two-arms-one-date case.
  2. **A silently empty A/B.** `calibration_by()` dropped the untagged bucket and
     the entire pre-WP-16.B control population is untagged — so the profile A/B
     had been rendering as a single row with nothing to compare. `profile_of()`
     resolves untagged to `baseline`.
  3. **A confound guardrail.** `date_overlap()` / `profile_confound()` report
     shared report-dates between profiles; the accuracy report and the
     separation section print a ⛔ block when a pair shares none, and the
     commitment verdict will not say "the thesis holds" while that flag is set.
  4. **Intervals, not just p-values.** Every gap carries a 95% block-bootstrap
     interval, and the verdict says **"inconclusive — underpowered"** instead of
     "no separation" when a high p comes with an interval wide enough to contain
     the effects already measured — the exact misread [KB-023] corrected.

  De-pooling moved the headline: decisive n 731 → 666, BSS −0.112 → **−0.123**,
  and the commitment baseline's net edge −0.109 → **−0.128**.

**WP-21.B.2 — Day-alternating assignment. ❌ NOT STARTED, and now closed.**
This is the deliberate call, recorded so it does not look like drift.

A clean A/B could only ever have answered *"which of two prompt configurations
produces less-bad directional calls."* It could never have answered *"is there a
directional signal to produce."* [KB-024] answers the second question, and the
answer removes the target: ranking two ways of writing a call is not worth
months of accumulation when no model class can beat a constant at making one.

The ordering argument matters as much as the evidence. WP-21.B.2 had not begun,
so n≥30 per arm was months away — months in which the note would have kept
publishing calls that resolve at ~36% while carrying ~63% confidence. Waiting
for a strictly less informative answer while the anti-informative product stays
live is the wrong order of operations. **WP-21.A was built precisely to answer
the bigger question without waiting, and it did.**

- **Also closed with it:** promoting `loosened` to default. There is no longer a
  directional product for the profile lever to improve. `MACRO_PROFILE` stays
  wired (it still switches model and prompt-rule blocks) but its A/B is over.

### WP-21.C — Conditional base rates into the prompt — ❌ CLOSED, inverted into the product

Gated on WP-21.A finding an edge. It did not, so the prompt-side version of this
work does not happen: feeding the model a base rate so it can overwrite it with a
worse guess is exactly the trade [KB-024] says not to make.

**What survives is the better half of the idea.** The conditional distribution is
already computed (`conditional.py`, Phase 11) and already appears in the note —
buried inside `primary_driver` as prose, because the prompt asks the model to
state it before departing from it. WP-21.D promotes it: the base rate becomes
**the published product**, rendered by Python from
`data/conditional_distributions.json`, and nothing overwrites it.

### WP-21.D — The kill criterion, read → **CUT** ✅ *(v1.6)*

The criterion as pre-committed read "cut if, after the WP-21.B clean A/B reaches
n≥30 per arm, separation is still not `aligned` and BSS is still < 0." That
condition is now unreachable by design — B is closed — so the criterion is read
against what actually exists, which is strictly more evidence than it asked for:

| | what it measured | result |
|---|---|---|
| [KB-007] | the LLM's own calls, 441 decisive | 36% hit-rate, BSS −0.195, confidence anti-informative |
| [KB-022] | the LLM's bias label vs forward returns | separation inverted |
| [KB-024] | whether *any* small model can learn the task | no — beaten by a constant, inverts the same way |

Three independent measurements, none `aligned`, every BSS < 0. **Cut.**

**The cut is surgical — the claim goes, the base rate stays.** Today's S&P row
already carries *"5d conditional median +0.4% (P25 −0.6%, P75 +1.2%) in the
current NFCI-low/YC-positive/HY-tight bucket, n=331"* — computed from data,
honest, and not what failed. The model then puts "Bullish, 63%" on top of it, and
that is the part three measurements call anti-informative. So the table is not
deleted; its columns change:

| before | after |
|---|---|
| `Bias` | `5d conditional distribution` (median, P25/P75, n — Python-rendered) |
| `Confidence` | *(gone; the note's risk read is the fragility flag, promoted to a headline block)* |
| `Primary Driver` | kept — narrative and cross-asset reasoning is not what failed |
| `Target Range` | kept — a plausible-move band, never scored as a directional call |

Shipped as **v1.6** (`versions.py`). The version gate is what keeps the
historical record intact: `score_predictions.py` scores v1.5-and-earlier reports
exactly as before and records v1.6+ as carrying no directional call, so
[KB-007]/[KB-011]/[KB-022] stay reproducible and the accuracy readers keep
working on the history they were written for.

**On a cut the report does not end** — the fragility / risk-flag products become
the headline. They are the ones with validated out-of-sample skill
([KB-017] leave-one-crisis-out CV, [KB-021] live parity), and the honest limit is
stated with them: precision ≈0.32, so roughly two of three flags are false
alarms. It is a high-recall "this is not a normal tape" warning, not a forecast.
The Fragility Monitor block moves from the tail of the Data Snapshot to a
headline section, and `FRAGILITY_OR_MODE` steps `log → show`.

**The promotion was blocked by the A/B, and the cut is what unblocks it.**
`Active_Experiments.md` held the ladder at "escalate only after the loosened A/B
resolves (a new output lever would confound it)." Closing WP-21.B removes that
confound. The two decisions were never independent.

It stays at `show`, not `active`: `show` surfaces the flag and lets the model see
it; `active` would let it widen Target Ranges. There is no live forward record
yet, so the flag gets one before it moves anything.

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

### Phase 21 — execution order *(complete)*

1. **WP-21.A** — numeric baseline. ✅ Harness, ✅ sample-alignment fix, ✅ run,
   ✅ **[KB-024]**.
2. **WP-21.B** — arm-filtered readers ✅ done and kept; day-alternating
   assignment ❌ closed, superseded by A.
3. **WP-21.C** — ❌ closed; the base rate is promoted to the product instead of
   fed to the prompt.
4. **WP-21.D** — criterion read → **cut**, shipped as v1.6, fragility promoted.
5. **WP-21.E** — capped indicator search, queued, blocking nothing.
6. **WP-21.F** — Kimi + exogenous arms stood down ✅ (soft-kill, nothing deleted).
7. **WP-21.G** — scoring loop wound down ✅; the record closes ~2026-10-02 and the
   run announces it.

### WP-21.F — Stand down the two remaining directional arms ✅ *(2026-09-04)*

`kimi_arm.py` and `exogenous/synth.py` were the last two things in the repo still
emitting a Bias/Confidence table. Both are now **deactivated**: their stages were
removed from `pipeline.yml` (stage 4 and stage 3 respectively), so neither runs on
its own any more.

**Soft-kill, not deletion.** Both workflows keep their `workflow_dispatch` trigger,
and nothing else was removed — the modules, their tests, every emitted note and
every scored file stay exactly where they are, and `calibration_by_arm` still reads
them. Restoring either arm is putting its job back in `pipeline.yml`. This is the
kill path both files' own comments describe (`kimi_arm_daily.yml` header,
`exogenous/DESIGN.md` §9).

Note what did *not* stop them: the version gate. Neither arm stamps an
`agent_version`, so `has_directional_calls()` reads them as scoreable and they
would have kept scoring indefinitely. That is the correct behaviour — silently
defunding a running experiment through a version constant it never opted into
would be the wrong mechanism — which is why standing them down is an explicit act
here rather than a side effect of the cut.

**Kimi — closed, and the reason is not "it failed".** The arm asked whether
ensemble self-consistency could calibrate `confidence_pct`, which [KB-007] found
anti-informative. v1.6 cut `confidence_pct`. Calibrating a signal that does not
exist is not a smaller task than calibrating a bad one; it is an empty one. The
mechanism was proven (it converges with the other arms on rates); the *target* is
what disappeared.

**Exogenous (Phase 19) — the scoring contract is paused, the thesis is untested.**
Worth being precise, because these are different claims. Its pre-committed gate
(DESIGN §4/§5) is a scored directional lean A/B'd head-to-head against the
market-only arm on `10Y` / `DXY` / `gold`. v1.6 cut market-only's calls, so the
comparator stopped accumulating and the gate became unreadable — the arm would be
measured against a frozen record it can neither beat nor lose to.

The *mechanism* never got its test. It is worth restating because it is easy to
misremember as "market vs institutions", which inverts the key design decision:
**market data was deliberately barred as a core input.** The natural rates
consensus is the market-implied path (fed-funds / SOFR futures), and DESIGN §6.1
excludes it precisely so the arm could not secretly re-derive from prices and
contaminate the A/B. The anchor is instead two free, official, **non-market**,
point-in-time consensus sources — the **Philly Fed SPF** (economist consensus) and
the Fed's own **SEP dot plot** (policymaker consensus) — and the bet has two
layers: the *gap between them* is itself a tension signal (economists disagreeing
with the Fed's dots), and because both update only quarterly, the branch tracks
**new FOMC communication** drifting away from a fixed anchor between updates.
Economists vs policymakers vs what the Fed is now saying, with the market excluded
on purpose.

Two live ways back, neither taken here:
- **(a) Re-point the gate at the WP-21.A benchmark** — score its leans against
  `always_bullish` / `neutral` on the same dates. Cheap, and [KB-024] shows that
  is a genuinely hard bar rather than a formality.
- **(b) Re-cut its output the way the main note was re-cut.** DESIGN §1 says the
  branch is about expectations-gaps and regime, **not** direction; the directional
  lean was adopted as a scoring convenience ("judged by the same Brier metric"),
  and it is exactly the part that just became unscoreable. Publishing the
  expectations gap itself would be the coherent product.

**(a) is the cheaper read; (b) is the better product.** Deferred to Phase 19.

**Update 2026-09-04 — (a) is taken.** The SPF anchor now runs as two arms inside
the WP-21.A harness (`exogenous_spf`, `market_plus_exo`), scored on the same
sample against the same pre-committed bar. See **WP-19.E**. (b) is still open and
is still the better product.

### WP-21.G — Wind down the scoring loop ✅ *(2026-09-04)*

With the main note cut and both arms stood down, **no new directional call is
produced anywhere in the repo.** The scored record is now finite, and the cleanup
follows from that:

- **The feedback loop is deleted, not disabled.** `load_accuracy_context()` (~120
  lines) built the prompt's "Your Historical Prediction Accuracy" block —
  best-window-per-asset, "anchor YOUR confidence to…", and a set of bias rules. Its
  last caller went with the columns. `accuracy_summary.json` is still *written*;
  nothing reads it back into a prompt.
- **The scorer still has work to do, and says how much.** The last directional note
  is 2026-09-04 (v1.5) and its T+20 window resolves ~2026-10-02, so the weekly
  stage must keep running until then. `record_closure()` / `print_closure()` report
  the outstanding count each run and print a **DIRECTIONAL RECORD CLOSED** banner
  once every window has resolved — naming the retirement. Without it the cron would
  print "0 score file(s) written" forever, which reads exactly like a silent
  breakage.
- **The scoring stage was re-parented.** It was gated on the kimi stage succeeding;
  removing kimi would have silently stopped the scorer. It now hangs off `daily`.
- **The readers stay.** `summarize_accuracy.py` and `bias_separation.py` read the
  history and keep working; that history is the evidence base for
  [KB-007]/[KB-011]/[KB-022] and must stay reproducible.

**Still running, deliberately:** the Phase-20 paper portfolio stage. It sizes from
bias + confidence, detects a post-cut note, and declines to advance the book with
a message saying why. Leaving it in place makes the withdrawn input visible every
week rather than quietly dropping a track record; retiring it is a Phase 20 call.
