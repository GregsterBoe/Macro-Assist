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

### Phase 1 — Expand the Free Data Pipeline *(Completed 2026-04-28)*

Added 5 FRED series: WALCL, WTREGEN, RRPONTSYD, ICSA, NFCI. Fed Net Liquidity = WALCL − WTREGEN − RRPONTSYD computed in Python with WoW/MoM % change; derived signal passed to Claude.

---

### Phase 2 — Shift the "Quant" Burden to Python *(Completed 2026-04-28)*

Expanded yfinance history window from 10 → 90 days. Added 14-day RSI, 50dMA distance, 60-day Z-score for 5 assets. New `## Technical & Positioning State` block injected before analysis.

---

### Phase 3 — Add Free Positioning Data (COT) *(Completed 2026-04-28)*

CFTC COT via Nasdaq Data Link for WTI Crude and Gold. Speculative net-long percentile; `## COT Positioning` block; contrarian signal (≥80th pct = crowded long, ≤20th = crowded short). Pipeline skips gracefully if key absent.

---

### Phase 4 — Overhaul System Prompt & Guardrails *(Completed 2026-04-28)*

System prompt guardrails for equity/liquidity, COT weighting, and NFCI/ICSA thresholds. `_apply_accuracy_override()` floors <40% directional-accuracy assets at 50% confidence (direction kept scoreable, not flipped to Neutral).

---

### Phase 5 — Window-Aware Prediction Calibration *(Done)*

Per-window accuracy table (T+5/T+10/T+20) injected into system prompt. Best-window override: DXY conviction rule permits directional call if T+10/T+20 accuracy ≥70% at n≥10. Predictions table includes best-window horizon note per asset.

---

### Phase 6 — Break the Neutral Collapse *(Done)*

Requires ≥1 conviction call (≥57% confidence) per report. Signed contrarian override for systematic inverse assets (<40% accuracy at n≥12). Max 3 assets at same confidence figure per table.

---

### Phase 7 — Sector Opportunity Research *(Done — 7d scoring deferred)*

11 sector ETFs with forward P/E injected as fundamentals block. `### Sector Opportunity Research` section (≤200 words, 2-3 sectors with macro rationale); max_tokens 4000→5000. 7d ETF scoring deferred.

---

## Multi-Agent Architecture — Phases MA-0 through MA-3

**Strategic rationale.** Phases 1–7 enriched the data pipeline and added prompt rules as reactive patches to observed failures. The result is a system where a single LLM call carries conflicting objectives: interpret raw data, generate directional calls, write narrative, apply self-calibration, and assess portfolio risk simultaneously. This structure produces specific failures — bias/narrative contradictions, meta-prompt leakage, and a model that hedges before making a call because it sees its own failure statistics.

**Architecture target.**

```
Data Collection (Python — unchanged)
    ├── Analysis Agent  (Sonnet)  → AnalysisOutput JSON     [data-only; no accuracy history]
    │     ↓
    ├── Calibration     (Python + Sonnet)  → CalibrationOutput JSON
    │         [applies accuracy_summary.json deltas to structured predictions]
    ├── Risk Agent      (Haiku)   → PortfolioRiskOutput JSON [portfolio + macro_regime only]
    └── Synthesis Agent (Sonnet)  → Final Markdown           [no raw data; composes from JSON]
```

Each agent has one objective and a minimal information diet. Numbers travel between agents as typed JSON.

---

### Phase MA-0 — Immediate Bug Fixes *(Done — 2026-05-22)*

Three targeted patches:
- **MA-0.1 Time-travel date fix:** `_compute_net_liquidity()` date capped at today to prevent week-ending Sunday placing "As Of" 2 days ahead.
- **MA-0.2 Meta-prompt leakage scrubber:** `_scrub_prompt_artifacts()` strips instruction-text echoes ("Maximum 200 words", "Section complete") from model output.
- **MA-0.3 Bias/narrative contradiction detector:** `_check_prediction_consistency()` logs WARN when Bullish bias appears with fade/short language in Primary Driver.

---

### Phase MA-1 — Structured Output Contract *(Done — 2026-05-24)*

New file `.macro-assist/schemas.py`: `AssetPrediction` and `AnalysisOutput` Pydantic models. Anthropic tool_use (`submit_analysis`) forces structured output; retries once on `ValidationError`; falls back to free-text. System prompt shrunk to analytical rules only; `build_note()` assembles markdown from typed fields.

---

### Phase MA-2 — Analysis / Calibration Split *(Done — 2026-05-25)*

Removed accuracy history from analysis agent context (eliminated pre-emptive hedging). Adversarial pass repurposed as structured calibration agent on predictions list + key risks only (`CalibrationOutput` dict of confidence deltas). Accuracy overrides applied directly to `AnalysisOutput` Pydantic object.

---

### Phase MA-3 — Risk Agent + Synthesis Agent *(Done — MA-3a: 2026-05-25; MA-3b: 2026-05-26)*

**MA-3a:** Haiku risk agent receives only `macro_regime` + portfolio positions; outputs `PortfolioRiskOutput` (biggest headwind/tailwind, actionable, opportunity gap).

**MA-3b:** Sonnet synthesis agent composes final markdown from structured JSON inputs only — no raw data. Eliminates prompt-injection artifacts by construction. Free-text `build_note()` retired.

---

## Quantitative Statistical Layer — Roadmap Extension (Phases 8–15)

**Strategic context.** Phases 1–7 enriched the data Claude sees and disciplined how it interprets that data. The next stage adds a **structured statistical layer** that feeds Claude pre-computed probabilistic context: volatility forecasts, regime classifications, and historical conditional return distributions. The goal is **not** to replace Claude's narrative analysis — it's to anchor the model's predictions to calibrated statistical reality, in the same spirit as the Phase 2 technical indicators but at a higher abstraction level.

**Compute footprint:** All math in Phases 8–15 is lightweight (HAR-RV is pandas operations; HMM training ~30s; conditional distributions are groupby + percentiles). It runs comfortably in GitHub Actions — **no local GPU or compute required**. Trained models and lookup tables are committed to the repo as small pickle/JSON files.

**Validation philosophy:** at each phase, no module is considered working until it (a) passes synthetic-data round-trip tests, (b) beats a naive baseline in backtest, and (c) survives visual inspection against known historical periods.

---

### Phase 8 — Validation Infrastructure *(Done — 2026-05-26)*

**Goal:** Build the backtest framework that lets every later phase be objectively validated.

**Key files:** `.macro-assist/point_in_time.py`, `.macro-assist/backtest.py`, `.macro-assist/synthetic.py`

**Key functions:**
- `historical_snapshot(date)` — ALFRED vintage data (no look-ahead), same schema as `fetch_fred_data()`
- `run_backtest(start, end, strategy, output_dir)` — walk-forward simulator with JSON output per day
- `score_backtest(output_dir)` — scores prediction JSONs using `score_predictions.py` logic
- `strategy_neutral`, `strategy_random_walk`, `strategy_existing_pipeline` — three baseline strategies
- `synthetic_garch(n, omega, alpha, beta)`, `synthetic_regime_switching(n, matrix, means, vols)`, `synthetic_conditional(n, state_fn, forward_means, vols)` — three synthetic data generators

**Tests:** 18 pure unit tests across `test_point_in_time.py`, `test_backtest.py`, `test_synthetic.py`.

---

### Phase 9 — Volatility Forecasting Layer *(Done — 2026-05-26)*

**Goal:** Predict 5/10/20-day realized volatility per asset and compute the Variance Risk Premium against VIX.

**Key files:** `.macro-assist/vol_forecast.py`

**Key functions:**
- `har_rv_forecast(returns, horizon)` — HAR-RV model (numpy OLS): `RV_{t+1} = β₀ + β₁·RV_daily + β₂·RV_weekly + β₃·RV_monthly`. Returns annualized forecast %, 60d percentile, R², fitted parameters.
- `variance_risk_premium(vix, harrv_forecast, history)` — VRP = VIX − HAR-RV forecast. Thresholds: ≤25th pct = Compressed, ≥75th = Elevated, else Normal.

**New dependency:** `arch>=6.3.0`

**Tests:** 8 pure unit tests + 4 integration tests (`@pytest.mark.integration`).

---

### Phase 10 — Regime Classification Layer *(Done — 2026-05-26)*

**Goal:** Classify the current macro regime (4 states) using a Hidden Markov Model on normalized macro features.

**Key files:** `.macro-assist/regime_features.py`, `.macro-assist/regime.py`, `.macro-assist/data/regime_model.pkl`

**Key functions:**
- `regime_features(snapshot, sp500_returns)` — 4-feature vector: NFCI percentile [0,1], yield curve bps (raw), HY spread z-score (vs 5yr mean / 1.5), SP500 60d vol percentile.
- `fit_regime_model(historical_features, n_states=4)` — GaussianHMM full covariance; pickled to `data/regime_model.pkl`.
- `predict_regime(model, current_features)` — returns state, label, posterior vector, transition probs.
- `label_states(model)` — median split on NFCI (feature[0]) and vol (feature[3]): Risk-On/Off × Low/High-Vol.
- `stable_regime_label(posteriors_history, min_posterior=0.7, min_dwell=3)` — anti-flicker; returns -1 until first stable label.

**New dependency:** `hmmlearn>=0.3.0`

**Tests:** 30 pure unit tests + 3 integration tests.

---

### Phase 11 — Conditional Distribution Layer *(Done — 2026-05-29)*

**Goal:** Build empirical lookup tables of forward returns conditional on macro state. Given the current state, retrieve the historical distribution of 5/10/20-day returns per asset.

**New dependencies:** none.

#### Phase 11.1 — State Bucketing

**New file:** `.macro-assist/conditional.py`
**New file:** `.macro-assist/tests/test_conditional.py`

**Functions to implement:**
```python
def assign_bucket(snapshot: dict) -> str:
    """
    Returns a bucket label like 'NFCI:high|YC:inverted|HY:wide'.
    Uses:
    - NFCI percentile tertile (low / mid / high)
    - Yield curve sign (positive / inverted)
    - HY spread tertile (tight / mid / wide)
    Total possible buckets: 3 × 2 × 3 = 18.
    """

def build_bucket_index(historical_snapshots: list[tuple[date, dict]]) -> dict[str, list[date]]:
    """Labels every historical date with its bucket; returns inverted index."""
```

**Validation tests:**
- `test_bucket_occupancy`: on 5 years of historical data, most buckets should have n ≥ 20; sparse buckets should be flagged for collapse to parent (e.g. drop the HY tertile dimension)

**Claude Code prompt:**
> Implement `.macro-assist/conditional.py` with `assign_bucket(snapshot)` returning a string like `'NFCI:high|YC:inverted|HY:wide'` using NFCI percentile tertiles, yield curve sign, and HY spread tertiles. Tertile cuts computed from full historical 2010-present sample (commit the cut points as constants in the module). Also implement `build_bucket_index(historical_snapshots)` returning dict mapping bucket -> list of dates. Test that across 2020-2025 daily snapshots, every bucket has n ≥ 20 OR is flagged in a `SPARSE_BUCKETS` constant for parent-bucket collapse.

---

#### Phase 11.2 — Lookup Engine

**Extend:** `.macro-assist/conditional.py`
**New artifact:** `.macro-assist/data/conditional_distributions.json` (committed; refit weekly)

**Functions to implement:**
```python
def build_distribution_table(
    historical_snapshots: list[tuple[date, dict]],
    forward_returns: dict[str, dict[date, dict[int, float]]],
    min_n: int = 10,
) -> dict:
    """
    Schema:
    {
        bucket_label: {
            asset: {
                horizon_int: {
                    'p10': float, 'p25': float, 'p50': float,
                    'p75': float, 'p90': float, 'n': int
                }
            }
        }
    }
    Buckets with n < min_n collapse to parent (drop the most granular dimension).
    Persist as JSON.
    """

def lookup_distribution(
    current_bucket: str,
    asset: str,
    horizon: int,
    table: dict,
) -> dict | None:
    """Returns the distribution dict or None if no data even after parent fallback."""
```

**Validation tests:**
- `test_distinct_distributions`: median forward 5d SP500 return in `'NFCI:high|YC:inverted|HY:wide'` should differ from `'NFCI:low|YC:positive|HY:tight'` by ≥0.5pp
- `test_full_coverage`: every date in the last 12 months should map to a bucket with n ≥ 10

**Claude Code prompt:**
> Extend `.macro-assist/conditional.py` with `build_distribution_table(historical_snapshots, forward_returns, min_n=10)` producing a nested dict keyed by bucket → asset → horizon → percentile stats. Use pandas groupby on bucket labels and compute p10/p25/p50/p75/p90 + n. Buckets below `min_n` collapse to parent (drop HY tertile, then drop yield-curve sign, then drop NFCI tertile). Persist to `.macro-assist/data/conditional_distributions.json`. Implement `lookup_distribution(current_bucket, asset, horizon, table)` returning the distribution or None after parent fallback. Test: (a) `'NFCI:high|YC:inverted|HY:wide'` shows median forward 5d SP500 return ≥0.5pp lower than `'NFCI:low|YC:positive|HY:tight'`; (b) every date in the last 12 months maps to a bucket with n ≥ 10 after fallback.

---

#### Phase 11.3 — Lookahead-Safe Computation

**Extend:** `.macro-assist/conditional.py`

The critical invariant: when computing the distribution lookup for date D, the table can ONLY include rows where the forward-return observation date (the date at which the realized forward return is known) is ≤ D − max_horizon. Otherwise the backtest leaks future information.

**Function to implement:**
```python
def build_distribution_table_for_backtest(
    historical_snapshots: list[tuple[date, dict]],
    forward_returns: dict[str, dict[date, dict[int, float]]],
    as_of_date: date,
    max_horizon: int = 20,
    min_n: int = 10,
) -> dict:
    """
    Same as build_distribution_table but only uses observations where 
    snapshot_date + max_horizon <= as_of_date.
    Used inside the backtest harness.
    """
```

**Validation tests:**
- `test_subset_monotone`: for two backtest dates D1 < D2, the bucket sample size at D1 is ≤ at D2 (table grows monotonically)
- `test_no_future_leak`: for any backtest date D, no row used in the lookup has snapshot_date + 20 days > D

**Claude Code prompt:**
> Extend `.macro-assist/conditional.py` with `build_distribution_table_for_backtest(historical_snapshots, forward_returns, as_of_date, max_horizon=20, min_n=10)` that filters historical observations so only those where the forward return was known by `as_of_date` are included (snapshot_date + max_horizon ≤ as_of_date). Tests: (a) for D1 < D2, the n values per bucket at D1 ≤ those at D2; (b) no observation used at as_of_date D has snapshot_date + max_horizon > D.

---

### Phase 12 — Quantitative Context Integration *(Done — 2026-05-29)*

**Goal:** Combine vol forecasts, regime classifications, and conditional distributions into a single markdown block injected into the Claude prompt. Update the system prompt to instruct Claude on how to use this new context.

#### Phase 12.1 — Context Assembly

**New file:** `.macro-assist/quant_context.py`
**Modify:** `.macro-assist/collect_and_analyze.py`

**Function to implement:**
```python
def build_quant_context(snapshot: dict, snapshot_date: date) -> str:
    """
    Calls vol_forecast (Phase 9), regime (Phase 10), and conditional (Phase 11) modules.
    Returns a markdown block formatted like existing ## Sector Fundamentals.
    """
```

**Output format (target):**
```markdown
## Quantitative Context

**Volatility (HAR-RV, 5d ahead):**
- SP500: 0.78% daily (60d pct 35); VIX implies 0.88% → VRP 0.10 (60d pct 60, Normal)
- Gold: 0.55% daily (60d pct 50)
- WTI Oil: 1.42% daily (60d pct 78, Elevated)
- Bitcoin: 2.31% daily (60d pct 45)

**Regime (HMM, 4-state):**
Current: Risk-Off High-Vol (posterior 0.82, dwell 14 trading days)
Transition probabilities: stay 0.91 | Risk-On Low-Vol 0.04 | Risk-Off Low-Vol 0.05

**Conditional return distribution (bucket: NFCI:high|YC:inverted|HY:wide, n=47):**
| Asset | Horizon | P25 | Median | P75 |
|-------|---------|-----|--------|-----|
| SP500 | 5d | -1.2% | +0.1% | +1.4% |
| SP500 | 20d | -3.8% | -0.6% | +3.1% |
| Gold | 5d | -0.4% | +0.6% | +1.7% |
...
```

**Integration in `collect_and_analyze.py`:** add `quant_context = build_quant_context(snapshot, today)` after data fetch, before Claude call. Prepend to the user message just after the Notable Moves block.

**Validation:** add unit test that runs `build_quant_context` on a synthetic snapshot and asserts the output contains all three sub-sections (Volatility / Regime / Conditional).

**Claude Code prompt:**
> Implement `.macro-assist/quant_context.py` with `build_quant_context(snapshot, snapshot_date)` that calls `har_rv_forecast` + `variance_risk_premium` from `vol_forecast.py`, `predict_regime` + `stable_regime_label` from `regime.py`, and `assign_bucket` + `lookup_distribution` from `conditional.py`, then formats the combined output as a markdown block titled `## Quantitative Context` with three subsections (Volatility / Regime / Conditional return distribution). Match the formatting style of the existing `## Sector Fundamentals` block in the prompt. Modify `.macro-assist/collect_and_analyze.py` to call `build_quant_context` after data fetching and prepend its output to the user message right after the Notable Moves block. Add a unit test running `build_quant_context` on a synthetic snapshot and asserting all three subsections appear.

---

#### Phase 12.2 — System Prompt Updates

**Modify:** `.macro-assist/prompts/system_prompt.md`

**New rules to add (after existing rules, before predictions section):**

```
## Quantitative Context Block

A `## Quantitative Context` block is injected before your analysis sections. It contains:
- HAR-RV volatility forecasts per asset, with the Variance Risk Premium (VRP) for SP500
- Current HMM regime label, posterior probability, dwell time, and transition probabilities
- Historical forward return distribution conditional on the current macro state bucket

Rules for use:
1. Anchor confidence in the 5-Day Predictions table to the conditional distribution.
   Bullish/Bearish calls should sit within the 10-90 percentile range of the conditional
   distribution at the matching horizon. Calls outside this range MUST justify the
   deviation explicitly in the Primary Driver cell.

2. Regime persistence informs confidence: if the current regime has high posterior
   (>0.8) and long dwell (>10 trading days), regime-consistent calls warrant up to
   +5pp confidence vs the base accuracy-driven floor.

3. Variance Risk Premium informs equity risk character: VRP 'Compressed' means options
   markets are pricing less risk than the model expects — interpret as latent
   fragility in the Equities section. VRP 'Elevated' means options are richly priced
   relative to model expectations — interpret as fear that may unwind.

4. Conditional distribution sample size matters: if `n < 20` for the current bucket,
   note the small sample explicitly in any prediction that references it.
```

**Claude Code prompt:**
> In `.macro-assist/prompts/system_prompt.md`, add a new top-level section `## Quantitative Context Block` (place it after the existing Phase-4 rules block, before the predictions section). The section describes the new injected block from Phase 12.1 and gives four rules: (1) predictions should sit within the 10-90 percentile of the conditional distribution unless explicitly justified; (2) regime persistence informs confidence; (3) VRP informs equity risk character; (4) small-sample buckets (n<20) must be noted explicitly. Use the exact wording from Phase 12.2 of `Project_Development.md`.

---

### Phase 13 — End-to-End Validation *(Moved to Backlog — optional)*

**Rationale for deferral:** Running an LLM backtest ($20–40 API spend) and a shadow-mode A/B test (4-week window) adds cost and latency before any validated signal exists. The quantitative modules are unit-tested; production monitoring (Phase 14.3) will accumulate the evidence base for a future retrospective comparison. Re-evaluate after 30+ live days of quant context logs.

**Goal:** Validate that the new quant context actually improves prediction accuracy before deploying to production.

#### Phase 13.1 — Shadow Mode

**Modify:** `.macro-assist/collect_and_analyze.py`
**Modify:** `.github/workflows/macro_daily.yml`

Add environment flag `MACRO_SHADOW=1`. When set:
- Pipeline writes prediction JSON to `results/shadow/YYYY-MM-DD.json` instead of writing the markdown note to the vault
- Quant context IS included
- All other side effects (vault push, copy to results/) are suppressed

Workflow change: add a second job to `macro_daily.yml` that runs after the main job with `MACRO_SHADOW=1` set in env. The shadow job uses the SAME data fetch but the SHADOW pipeline.

**Validation:** after 4 weeks (≥20 trading days), score shadow vs production predictions side by side. Manually inspect 10 random divergence days; divergences should be explicable in terms of the quant context block.

**Claude Code prompt:**
> Modify `.macro-assist/collect_and_analyze.py` to support `MACRO_SHADOW=1`: when set, skip the vault push and `results/` copy, instead write the prediction JSON to `results/shadow/YYYY-MM-DD.json` (gitignore this directory). Modify `.github/workflows/macro_daily.yml` to add a second job `shadow-pipeline` that runs after the main job, depends on its outputs being already pushed (`needs: generate-note`), checks out the same repos, and runs the same script with `MACRO_SHADOW=1` in env. Both jobs use the same FRED + Anthropic + Vault secrets.

---

#### Phase 13.2 — Historical Backtest

**New file:** `.macro-assist/backtest_e2e.py`
**New output:** `results/backtest/`

End-to-end backtest script that:
1. Iterates 2024-01-01 to today using `historical_snapshot()` from Phase 8.1
2. For each date: builds quant context (new pipeline) AND skips quant context (old pipeline)
3. Calls Claude in both modes (this DOES burn API tokens — expect $20-40 for full backtest)
4. Saves both prediction JSONs to `results/backtest/{new,old}/YYYY-MM-DD.json`
5. Scores both using existing `score_predictions.py` machinery
6. Outputs comparison report to `results/backtest/comparison_report.md`

**Validation criterion to deploy:** integrated system shows ≥3pp improvement in directional accuracy at n ≥ 30 calls per asset across at least 4 of 6 assets. If <3pp or fails on majority of assets: do NOT deploy; iterate.

**Claude Code prompt:**
> Implement `.macro-assist/backtest_e2e.py` running both the new pipeline (with quant context) and the old pipeline (without) over 2024-01-01 to yesterday. Use `historical_snapshot()` for data. Save prediction JSONs to `results/backtest/new/` and `results/backtest/old/`. After all dates run, score both directories using the same logic as `score_predictions.py` and write a comparison report to `results/backtest/comparison_report.md` showing per-asset per-window directional accuracy delta. Add a CLI flag `--dry-run` that uses cached/stubbed Claude responses for testing the harness without API spend.

---

#### Phase 13.3 — Ablation Study

**Extend:** `.macro-assist/backtest_e2e.py`

Run the backtest 4 additional times with each individual quant context subsection disabled:
- Vol forecast only (regime + conditional disabled)
- Regime only (vol + conditional disabled)
- Conditional only (vol + regime disabled)
- None (baseline = old pipeline)

Produces per-module attribution: which subsection contributes how much to the total improvement?

**Claude Code prompt:**
> Extend `.macro-assist/backtest_e2e.py` with an ablation mode (`--ablate vol|regime|conditional|none`) that disables individual quant context subsections by passing flags through to `build_quant_context`. Run the four ablation backtests and write per-module attribution to `results/backtest/ablation_report.md`.

---

### Phase 14 — Production Hardening *(Done — 2026-05-29)*

**Goal:** Deploy the validated quant context to production, with weekly model refresh and graceful degradation.

#### Phase 14.1 — Weekly Refit Workflow

**New file:** `.github/workflows/macro_weekly_refit.yml`
**New file:** `.macro-assist/refit_models.py`

The refit script:
1. Pulls 5 years of historical FRED+market data
2. Refits HMM, saves new `data/regime_model.pkl`
3. Rebuilds `data/conditional_distributions.json` using all data through yesterday
4. Commits both back to the repo

Schedule: Sunday 22:00 UTC. Monday's daily run uses fresh models.

**Claude Code prompt:**
> Add `.github/workflows/macro_weekly_refit.yml` scheduled at Sunday 22:00 UTC. The workflow checks out Macro-Assist with write permissions, installs deps, runs `python .macro-assist/refit_models.py`, then commits any changes to `.macro-assist/data/regime_model.pkl` and `.macro-assist/data/conditional_distributions.json`. Implement `refit_models.py` that pulls 5 years of historical data via existing helpers, calls `fit_regime_model()` from Phase 10, calls `build_distribution_table()` from Phase 11, and saves both artifacts. The script must be idempotent (re-running same week produces identical output).

---

#### Phase 14.2 — Failure Modes

**Modify:** `.macro-assist/collect_and_analyze.py`

Wrap `build_quant_context()` in a try/except. If it fails (model file missing, distribution lookup empty, any exception): log a warning to stdout, skip the block, continue pipeline without it. The daily note must NEVER fail because of the quant layer.

**Claude Code prompt:**
> Wrap the `build_quant_context()` call in `collect_and_analyze.py` with try/except. On any exception, log a warning with the exception type and message, set `quant_context = ""`, and continue. Add a CI check that runs the pipeline with a deliberately corrupted `regime_model.pkl` and asserts the daily note is still produced (just without the Quantitative Context block).

---

#### Phase 14.3 — Monitoring

**New artifact:** `results/quant_context_log/YYYY-MM-DD.jsonl`

Each day, log the raw outputs of the three subsections (vol forecast, regime label + posterior, current bucket + distribution) to a JSONL file. Enables retrospective analysis: did vol forecast correlate with realized vol? Did regime change as predicted by transition probabilities? Were predictions consistent with conditional distribution?

**Claude Code prompt:**
> In `collect_and_analyze.py`, after `build_quant_context()` runs successfully, also append a JSONL row to `results/quant_context_log/YYYY-MM-DD.jsonl` with the raw outputs of each subsection (vol forecasts dict, regime state + posterior + dwell, current bucket + n + p50 returns). Track this in git. Add no analysis logic — just collection. Later phases will mine these logs.

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

## Updated Suggested Execution Order

| Priority | Phase | Effort | Prerequisite | Status |
|----------|-------|--------|--------------|--------|
| 1 | Phase 1 (FRED liquidity + jobless claims) | Low | None | ✅ Done |
| 2 | Phase 2 (90d history + RSI/MA/Z-score) | Medium | None | ✅ Done |
| 3 | Phase 4 (system prompt rules + accuracy override) | Low | Phases 1 & 2 deployed | ✅ Done |
| 4 | Phase 3 (COT via CFTC direct) | Medium | None | ✅ Done — no API key required |
| 5 | Phase 5 (DXY window-aware predictions) | Low | 30+ scored reports | ✅ Done |
| 6 | Phase 6 (break Neutral collapse) | Low | Phase 5 | ✅ Done |
| 7 | Phase 7 (Sector Opportunity Research) | High | Phase 6 + fundamentals data | ✅ Done (7d scoring deferred) |
| 8 | **Phase MA-0 (Bug fixes: time-travel, leakage, contradiction detector)** | **Low** | **None — ship immediately** | ✅ **Done** |
| 9 | **Phase MA-1 (Structured output contract + schemas.py)** | **Medium** | **MA-0** | ✅ **Done** |
| 10 | **Phase MA-2 (Analysis / calibration split)** | **Medium** | **MA-1** | ✅ **Done** |
| 11 | **Phase MA-3a (Risk agent — Haiku)** | **Low** | **MA-1** | ✅ **Done** |
| 12 | **Phase MA-3b (Synthesis agent — retire free-text build_note)** | **Medium** | **MA-2 + MA-3a stable** | ✅ **Done** |
| 13 | **Phase 8 (Validation Infrastructure)** | **Medium** | **MA-3b complete** | ✅ **Done** |
| 14 | **Phase 9 (Volatility Forecasting)** | **Medium** | **Phase 8** | ✅ **Done** |
| 15 | **Phase 10 (Regime Classification)** | **Medium** | **Phase 8** | ✅ **Done** |
| 16 | **Phase 11 (Conditional Distributions)** | **Medium** | **Phase 8** | ✅ **Done** |
| 17 | **Phase 12 (Quant Context Integration)** | **Low** | **Phases 9, 10, 11** | ✅ **Done** |
| 18 | **Phase 13 (End-to-End Validation)** | **High** | **Phase 12** | ⏸ **Backlog (optional)** |
| 19 | **Phase 14 (Production Hardening)** | **Low** | **Phase 12 + deployment** | ✅ **Done** |
| 20 | Phase 15 (Optional Extensions) | Varies | All above | 🔲 Backlog |

---

## Implementation Notes for Phases 8–15

**Working environment.** All compute fits comfortably in GitHub Actions (HMM training ~30s, HAR-RV ~ms, conditional distributions ~seconds). The full backtest in Phase 13.2 takes ~30 minutes and ~$20-40 in Claude API tokens; run it locally if preferred, but it works in CI too.

**Development order strictly enforced.** Phase 8 must be done first — without the point-in-time data layer and backtest harness, Phases 9-12 cannot be validated. Without Phase 13 passing, Phase 14 must not be deployed.

**Decision gates.** After Phase 13 (end-to-end validation), there are three possible outcomes:
- **≥3pp improvement on both shadow + backtest** → proceed to Phase 14 deployment
- **Improvement on backtest but not shadow** → suspect overfitting, iterate (likely culprit: regime labeler instability, bucket sparsity, or feature drift)
- **No improvement** → keep the layer as additional context in the prompt but lower priors; the value may emerge over months of more data, or the architecture may need revision

**Testing infrastructure.** Add `pytest` to `requirements.txt` if not already present. Create `.macro-assist/tests/` directory and `.macro-assist/tests/__init__.py`. Each phase's tests should run independently; CI test runner should be added to a new `.github/workflows/tests.yml` that runs on every push to a feature branch.

**Claude Code workflow recommendation.** Tackle one phase per Claude Code session, run its tests before moving to the next. Phases 9, 10, 11 can be parallelized in separate feature branches if desired (each only depends on Phase 8). Phase 12 integrates them — do it last in this group.

---

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

**Branch.** `feature/regime-validation`. **Method.** Reuse the fragility harness patterns (`fragility_backtest.py`): pull-once-and-slice for prices, walk-forward look-ahead-safety, Mann-Whitney AUC, de-overlapped episode scoring, and record results in `Knowledge_Base.md` (KB-004+), kept separate from this plan.

1. **WP-17.1 — Look-ahead audit of the regime pipeline. *(Harness built + audit done — branch `feature/regime-validation`; real-data divergence run pending FRED key)*.** Built `.macro-assist/regime_backtest.py` (pure-numerical, no LLM): `walk_forward_regime` (refit weekly on the trailing ~5y *strictly before* each date, then single-point classify — mirrors production), `full_sample_regime` (the leaky baseline: one fit over all data, same single-point inference, so the only difference is training data → isolates Baum-Welch fit leakage), and `label_divergence`. Tests: `tests/test_regime_backtest.py` — 7 pure/synthetic tests; all pass. **Audit findings (from reading `regime.py` / `refit_models.py` / `regime_features.py`):**
   - **(a) Live labeling is look-ahead-safe.** The weekly `refit_models.py` fits on the trailing ~5y and labels *today* (the last point) — no future leaks into the live call.
   - **(b) Validation must NOT reuse the persisted model.** Baum-Welch fits forward-backward over the whole window, so a past date's in-sample state is informed by its future. Scoring skill on the persisted full-sample model is leaky → the skill gate (17.2) must use `walk_forward_regime`.
   - **(c) Inference is single-point → the transition matrix is unused live.** `regime_features` returns one (4,) vector and `predict_regime` classifies it alone, so live labeling is effectively a Gaussian-mixture point classification weighted by `startprob_`; the HMM's temporal structure only shapes the fitted emissions. (Worth a direct GMM-vs-HMM and sequence-vs-point comparison in 17.3 — the HMM may be doing no more than a mixture model here.)
   - **Hardening (after first real run):** the first FRED run surfaced two issues — (i) only **531 valid feature-days of 2920** (the 12y matrix truncated to ~2y, likely affecting the production refit too), and (ii) a `GaussianHMM` **singular-covariance crash** on short windows. Fixed the crash: `_fit_robust` adds covariance regularisation + a `full → diag → carry-forward` fallback ladder (with an inference probe, since a degenerate full-cov model can fit but fail in `predict_proba`); added `diagnose_features()` to pinpoint the truncation, tz-normalised the yfinance index, and surfaced valid-day/fallback counts. Tests: 9 (added 2 robustness). The **truncation root-cause still needs the FRED diagnostic** (no key in the agent env).
   - **Next:** user runs `FRED_API_KEY=… python -c "from regime_backtest import diagnose_features; diagnose_features(12)"` to identify the truncating input, then `…python .macro-assist/regime_backtest.py` for the PIT-vs-full-sample label-divergence rate (→ KB-004). If `_build_feature_matrix` is the culprit, fix it there (corrects production too → re-run `refit_models.py`).

2. **WP-17.2 — Regime skill gate (the WP-16.A.2 analog).** Do the state labels separate the future? Score forward 5/10/20-day SP500 return and realized vol conditioned on regime label/posterior: mean/median separation, AUC of "Risk-Off"-type states predicting drawdowns, and **posterior calibration** (when it says 0.9, is it right ~90%?). Honest go/no-go: if regimes don't separate forward outcomes out-of-sample, the layer is decorative and should be simplified or dropped.

3. **WP-17.3 — Model selection.** Is 4 states justified? Compare `n_states ∈ {2..6}` and covariance types by out-of-sample log-likelihood + BIC/AIC and by the 17.2 skill metric; check label stability / switching across walk-forward refits.

4. **WP-17.4 — Incremental value over the simpler bucket.** Does the HMM regime add information beyond the Phase-11 conditional bucket (which already conditions on NFCI / curve / HY)? If conditioning forecasts on regime doesn't beat the bucket alone out-of-sample, simplify.

5. **WP-17.5 *(later)* — Extend to vol_forecast + conditional layers.** Same look-ahead-safe walk-forward + skill scoring for HAR-RV (Phase 9) and the conditional-distribution table (Phase 11).