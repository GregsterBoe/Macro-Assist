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

1. **WP-16.B.1 — Conviction floor → config flag. *(Built — branch `feature/loosen-control`; awaiting floor-off data)*.** **Trace finding:** the conviction floor is **100% prompt-instruction** — nothing in the schema or post-processing rejects/rewrites an all-Neutral table (schema allows `Neutral`; `_apply_accuracy_override` only warns on Neutral high-signal calls; the adversarial clamp only bounds already-directional calls). So the flag is a prompt toggle. **Implementation:** `CONVICTION_FLOOR` env var (default `on` = current behaviour). The four forcing pressures (min-conviction, high-signal MUST-call, contrarian-instead-of-Neutral, and the dynamic accuracy-context language) are wrapped in `<!-- CF:ON/OFF -->` sentinels in both prompt files; `_render_conviction` strips the inactive arm at load (clean A/B), and `load_accuracy_context(floor_on)` softens its language. The note frontmatter records `conviction_floor: on|off`; `score_predictions.py` carries it into the score files; `summarize_accuracy.calibration_by_floor` reports the Brier/BSS A/B once both arms have data. Tests: `tests/test_conviction_floor.py` (16) + 3 in `test_summarize_accuracy.py`. **To run the off arm:** `CONVICTION_FLOOR=off python .macro-assist/collect_and_analyze.py`. **Decision (per KB-007):** does calibration of the calls it *does* make improve when calls aren't forced? Bar: BSS(off) > BSS(on) with ECE↓ at n≥30 floor-off decisive calls. *(Selection effect: fewer, more honest calls should calibrate better.)*

2. **WP-16.B.2 — Calibration measurement (Brier / reliability). ✅ Done** (→ KB-007). Added `calibration()` to `summarize_accuracy.py` (Brier + Brier Skill Score + ECE + confidence-binned reliability diagram, decisive calls only; surfaced in `accuracy_report.md` + `accuracy_summary.json`). 12 tests. **Baseline KB-007: confidence is anti-informative — BSS −0.195 overall (−0.344 feedback-era), decisive calls right only ~36%, below chance and worsening with horizon.** Brier/BSS is now the **north-star eval metric** for B.1/B.3/B.4 + Phase 18 + 16.C (must move Brier, not just accuracy); **elevates B.1** — forcing directional calls likely manufactures the below-chance decisive calls.

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