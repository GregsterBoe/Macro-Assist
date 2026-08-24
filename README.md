# Macro-Assist

Automated daily macro intelligence pipeline. Every weekday morning a GitHub Actions workflow fetches live economic and market data, runs a multi-agent Claude pipeline for structured analysis, and delivers a formatted Markdown note to an Obsidian vault. A separate weekly workflow scores the accuracy of past predictions and feeds that track record back into future reports as a self-calibration loop. A second weekly workflow refits the quantitative models on fresh data.

---

## Architecture

The project spans two GitHub repositories:

- **Macro-Assist** (this repo) — all scripts, workflows, prompts, accuracy data, and archived reports
- **External-Brain** — personal Obsidian vault; receives the daily note and accuracy report via git push

```
GitHub Actions (06:30 UTC Mon–Fri)
  │
  ├── fetch FRED macro indicators (16 series, 5yr history each)
  ├── fetch market prices + technicals (yfinance, 90d history)
  ├── fetch sector ETF fundamentals (11 ETFs + holdings P/E)
  ├── fetch COT positioning (CFTC direct download, no API key)
  ├── fetch economic calendar (BLS + hardcoded FOMC dates)
  ├── fetch YouTube transcripts (Supadata API, if new video in 36h)
  ├── summarize transcripts (Claude Haiku)
  ├── inject historical prediction accuracy (accuracy_summary.json)
  ├── inject portfolio positions (tr_positions.csv, if present)
  ├── build quantitative context block:
  │     ├── HAR-RV volatility forecasts (SP500, Gold, WTI Oil, Bitcoin)
  │     ├── VIX variance risk premium (SP500)
  │     ├── HMM regime classification (4-state model)
  │     └── conditional return distributions (macro-regime bucketed)
  │
  ├── MA-1: Claude Sonnet → structured AnalysisOutput (tool_use, 5000 tokens)
  ├── MA-2: Claude Sonnet → adversarial review of predictions table
  ├── MA-3a: Claude Haiku → portfolio risk agent (structured, narrow context)
  ├── MA-3b: Claude Haiku → synthesis agent (formats JSON → markdown)
  ├── Python → accuracy override (bias floor, wasted-signal, clustering checks)
  │
  ├── push note → External-Brain/Economy/YYYY/MM-Month/
  └── push note → Macro-Assist/results/MM-Month/

GitHub Actions (06:00 UTC Mon–Fri)        ← runs 30 min before daily note
  └── data fetch check (--fetch-only, no LLM call)

GitHub Actions (07:15 UTC Mondays)
  │
  ├── score past predictions (T+5, T+10, T+20)
  ├── aggregate accuracy stats → accuracy_summary.json
  ├── push accuracy_summary.json → Macro-Assist/.macro-assist/data/
  └── push accuracy_report.md → External-Brain/Economy/Analysis/

GitHub Actions (22:00 UTC Sundays)
  │
  ├── fetch 5yr FRED + market data
  ├── refit GaussianHMM regime model
  ├── rebuild conditional return distributions
  └── commit regime_model.pkl + conditional_distributions.json
```

---

## Repository Structure

```
Macro-Assist/
├── .macro-assist/
│   ├── collect_and_analyze.py   # main pipeline script (--fetch-only for data checks)
│   ├── parse_positions.py       # Trade Republic portfolio parser
│   ├── score_predictions.py     # weekly prediction scorer
│   ├── summarize_accuracy.py    # accuracy aggregator + per-version tracking
│   ├── tag_versions.py          # retroactively backfill agent_version to older reports
│   ├── versions.py              # single source of truth for pipeline version constants
│   ├── youtube_data.py          # YouTube transcript fetcher
│   ├── schemas.py               # Pydantic models for structured Claude output (MA-1)
│   ├── quant_context.py         # builds quantitative context block for Claude prompt
│   ├── regime.py                # GaussianHMM regime model fit + inference
│   ├── regime_features.py       # NFCI/yield-curve/HY/vol feature extraction
│   ├── vol_forecast.py          # HAR-RV volatility forecasting
│   ├── conditional.py           # macro-regime conditional return distribution builder
│   ├── refit_models.py          # weekly refit script (run by macro_weekly_refit.yml)
│   ├── backtest.py              # point-in-time backtesting harness
│   ├── point_in_time.py         # point-in-time FRED data reconstruction
│   ├── synthetic.py             # synthetic data generator for tests
│   ├── requirements.txt
│   ├── data/
│   │   ├── accuracy_summary.json       # tracked in git; read by daily pipeline
│   │   ├── regime_model.pkl            # trained HMM; updated weekly by refit workflow
│   │   ├── conditional_distributions.json  # asset return distributions per regime bucket
│   │   └── cot_history.json            # rolling 54-week COT positioning cache
│   ├── prompts/
│   │   ├── system_prompt.md            # free-text Claude analyst instructions (fallback)
│   │   ├── system_prompt_structured.md # structured-output analyst instructions (MA-1)
│   │   └── synthesis_prompt.md         # synthesis agent instructions (MA-3b)
│   └── tests/
│       ├── conftest.py
│       ├── test_quant_context.py
│       ├── test_regime.py
│       ├── test_regime_features.py
│       ├── test_vol_forecast.py
│       ├── test_conditional.py
│       ├── test_backtest.py
│       ├── test_point_in_time.py
│       └── test_synthetic.py
├── .github/
│   └── workflows/
│       ├── macro_daily.yml           # Mon–Fri 06:30 UTC — main pipeline
│       ├── macro_data_check.yml      # Mon–Fri 06:00 UTC — data fetch pre-check
│       ├── macro_weekly_scoring.yml  # Monday 07:15 UTC — prediction scoring
│       └── macro_weekly_refit.yml    # Sunday 22:00 UTC — model refit
├── data/
│   ├── tr_positions.csv         # Trade Republic export (optional; gitignored)
│   └── ticker_cache.json        # ISIN→ticker cache (committed)
├── results/
│   ├── MM-Month/
│   │   └── YYYY-MM-DD-Weekday-macro.md  # archived report copies
│   ├── scores/                  # gitignored — raw JSON score files per report
│   ├── quant_context_log/       # gitignored — daily JSONL snapshots of quant outputs
│   └── accuracy_report.md       # human-readable accuracy summary
├── Project_Development.md       # phased implementation roadmap
├── TODO.md                      # open decisions + carried findings across sessions
└── .gitignore
```

**`TODO.md`** is the working-memory file: open design decisions, known-but-
unscheduled findings, and the reasoning behind each, cited to file/line. Read it
before picking up a phase and update it when a run surfaces something that needs
a human call rather than a fix.

---

## Data Sources

### FRED Macro Indicators

Fetched via `fredapi`. 5-year history pulled per series to enable historical context (5yr mean, vs-mean comparisons). Every series includes a `days_stale` field; Claude applies tiered staleness rules (current / note-once / trend-only).

| Key | FRED ID | Frequency | Notes |
|-----|---------|-----------|-------|
| `fed_funds_rate` | FEDFUNDS | Monthly | |
| `cpi` | CPIAUCSL | Monthly | YoY % and 5yr mean YoY computed |
| `gdp` | GDP | Quarterly | Often 60–90 days stale |
| `unemployment` | UNRATE | Monthly | |
| `m2` | M2SL | Monthly | YoY % and 5yr mean YoY computed |
| `treasury_10y` | DGS10 | Daily | |
| `treasury_2y` | DGS2 | Daily | |
| `hy_spread` | BAMLH0A0HYM2 | Daily | ICE BofA HY OAS; 5yr mean computed |
| `philly_fed_mfg` | GACDFSA066MSFRBPHI | Monthly | Philly Fed diffusion index; 5yr mean computed |
| `real_yield_10y` | DFII10 | Daily | 10Y TIPS real yield; 5yr mean computed |
| `breakeven_10y` | T10YIE | Daily | 10Y inflation breakeven; 5yr mean computed |
| `fed_total_assets` | WALCL | Weekly | Fed balance sheet (millions; scaled ÷1000) |
| `treasury_gen_acct` | WTREGEN | Weekly | Treasury General Account (billions) |
| `reverse_repo` | RRPONTSYD | Daily | Overnight reverse repo (billions) |
| `jobless_claims` | ICSA | Weekly | Initial claims; WoW % and 5yr mean computed |
| `nfci` | NFCI | Weekly | Chicago Fed Financial Conditions Index; 5yr mean computed |

**Derived:** `yield_curve_spread` = 10Y − 2Y (computed inline). `net_liquidity` = (WALCL/1000) − WTREGEN − RRPONTSYD; WoW/MoM % and 4-week rolling trend computed.

### Market Data

90-day history fetched via `yfinance` to support technical indicators. 1-year history fetched separately for S&P 500 (200dMA). A `vix_term_ratio` (VIX / VIX3M) is computed to distinguish acute stress (backwardation) from anticipated volatility (contango).

| Key | Ticker | Notes |
|-----|--------|-------|
| `sp500` | `^GSPC` | 1yr history for 200dMA; 90d for RSI/Z-score |
| `nasdaq` | `^IXIC` | |
| `gold` | `GC=F` | |
| `wti_oil` | `CL=F` | |
| `vix` | `^VIX` | |
| `dxy` | `DX-Y.NYB` | |
| `bitcoin` | `BTC-USD` | |
| `vix3m` | `^VIX3M` | Term ratio only; not in snapshot table |

**Technical indicators** (computed in Python, injected as `## Technical & Positioning State`):
- 14-day Wilder RSI — Overbought (>70) / Oversold (<30) / Neutral
- % distance from 50-day MA
- 60-day Z-score of today's daily return (|Z| ≥ 2.0 = statistically unusual)

**Notable Moves detector:** flags any asset where `|daily_change| ≥ 2 × 60d rolling std` and exceeds a per-asset minimum threshold (e.g. 1.5% for equities, 2.0% for oil). Output is a `## Notable Moves` block.

### Quantitative Intelligence Layer

Built by `quant_context.py` and injected as a `## Quantitative Context` block into the Claude prompt. Requires fitted model files (`regime_model.pkl`, `conditional_distributions.json`) — generated by the weekly refit workflow.

**HAR-RV Volatility Forecasts** — `vol_forecast.py`

Heterogeneous AutoRegressive model for Realized Volatility. Uses daily/weekly/monthly RV components from historical returns.

| Asset | Notes |
|-------|-------|
| S&P 500 | + VIX variance risk premium (VIX² − expected RV); Normal / Elevated / Compressed |
| Gold | |
| WTI Oil | |
| Bitcoin | |

Output per asset: annualized daily vol forecast + 60d percentile.

**HMM Regime Detection** — `regime.py`

4-state Gaussian HMM fitted on four macro features (weekly, 5yr history):

| Feature | Construction |
|---------|-------------|
| NFCI percentile | NFCI vs. 5yr range; forward-filled from weekly releases |
| Yield curve (bps) | DGS10 − DGS2 |
| HY z-score | (HY spread − 5yr mean) / 5yr σ |
| SP500 vol percentile | 60d realized vol vs. 252d rolling range |

States are labeled by their posterior probability. The state with the highest average NFCI percentile is treated as the stress state; the others are labeled Risk-On/Risk-Off by vol/yield-curve character. Output: state label, posterior probability vector, top-posterior confidence.

**Conditional Return Distributions** — `conditional.py`

Return distributions bucketed by a 3-dimension macro snapshot: NFCI tier × yield curve sign × HY spread tier. Each bucket shows the empirical P50 (median) forward return over T+5 and T+20 trading days, with sample count `n`.

| Asset | Windows |
|-------|---------|
| S&P 500 | T+5, T+20 |
| Gold | T+5, T+20 |
| WTI Oil | T+5, T+20 |

**Monitoring** — raw quant outputs (vol, regime, conditional) are logged to `results/quant_context_log/YYYY-MM-DD.jsonl` on each pipeline run for drift detection.

### Sector ETFs

Daily close and % change fetched for 11 sector ETFs (5-day history). Richer fundamentals — trailing P/E, 1M/1Y returns, distance from 52-week high — fetched separately for the `## Sector Fundamentals` prompt block.

| ETF | Sector |
|-----|--------|
| XLE | Energy |
| XLK | Technology |
| XLF | Financials |
| XLI | Industrials |
| XLY | Consumer Discretionary |
| XLV | Health Care |
| XLU | Utilities |
| XLP | Consumer Staples |
| XLB | Materials |
| XLRE | Real Estate |
| XLC | Communication Services |

For sectors where trailing P/E is >10% below the 5yr reference average, the top-3 holdings' forward P/E, market cap, and 1-year return are also fetched from yfinance and injected. No data is invented — every number comes from yfinance or is shown as N/A.

### COT Positioning

Weekly CFTC Commitments of Traders data fetched via direct public download from `cftc.gov` (no API key required). Current-year and prior-year ZIP files are parsed to compute net non-commercial (speculative) positioning and its percentile vs. 1-year range. Injected as `## COT Positioning` block. A rolling 54-week cache is maintained in `.macro-assist/data/cot_history.json`.

| Asset | CFTC Code |
|-------|-----------|
| WTI Crude Oil | 067651 |
| Gold | 088691 |

Percentile ≥ 80 = Crowded Long (contrarian bearish signal). Percentile ≤ 20 = Crowded Short (contrarian bullish signal). Claude is instructed to treat COT as positioning context only — a confirming catalyst is required before making a directional call.

### Economic Calendar

- **BLS releases:** fetched live from `https://www.bls.gov/schedule/news_release/schedule.json`. Filters for CPI, PPI, and Employment Situation within the next 7 days.
- **FOMC dates:** hardcoded list in `collect_and_analyze.py`. **Must be updated every January.** Source: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`

### YouTube Transcripts (optional)

YouTube RSS feed (no auth) is checked for videos published in the last 36 hours per configured channel. If a new video is found, the transcript is fetched via the [Supadata API](https://supadata.ai) and summarised to 6–8 macro-relevant bullet points by Claude Haiku before being passed to the main analysis call.

Currently configured: **Bravos Research** (`UCOHxDwCcOzBaLkeTazanwcw`)

To add channels, edit `YOUTUBE_CHANNELS` in `.macro-assist/collect_and_analyze.py`:
```python
YOUTUBE_CHANNELS = [
    ("UCOHxDwCcOzBaLkeTazanwcw", "Bravos Research"),
]
```

---

## Analysis Pipeline

### Multi-Agent Architecture

The pipeline runs four Claude calls per daily note:

| Agent | Model | Role |
|-------|-------|------|
| MA-1 | Sonnet (5000 tokens) | Structured macro analysis via `tool_use` → `AnalysisOutput` |
| MA-2 | Sonnet (250 tokens) | Adversarial review of predictions table only |
| MA-3a | Haiku (600 tokens) | Portfolio risk assessment (narrow context: regime + positions) |
| MA-3b | Haiku (3000 tokens) | Synthesis agent — formats structured JSON into final markdown |

If structured output fails after two attempts, the pipeline falls back to a single free-text Sonnet call (pre-v1.0 behaviour, unchanged).

### MA-1 — Structured Analysis (Claude Sonnet, max 5000 tokens)

Uses `system_prompt_structured.md` and Anthropic tool use (`submit_analysis`) to produce a validated `AnalysisOutput` Pydantic object. The schema enforces the section structure — section order and constraints are never in the model's output stream. Sections:

1. **Executive Summary** — 2–4 sentences on the dominant macro development
2. **Macro Dashboard** — signal matrix (9 indicators × 4 asset classes)
3. **Equities** — index moves, risk character, sector divergence, VIX term structure
4. **Rates & Fed Policy** — yield curve shape, real yield vs. breakeven decomposition, Fed trajectory
5. **Inflation & Growth** — CPI trend, GDP + unemployment regime read, M2, leading indicators
6. **Commodities** — Gold (real yield cross-reference), WTI (COT context), DXY
7. **Portfolio Risk Assessment** — position-level macro alignment (only when `tr_positions.csv` is present)
8. **Sector Opportunity Research** — 2–3 macro-driven sector tailwinds with P/E context
9. **Key Risks & Themes** — 3–5 actionable bullets for the next 1–4 weeks
10. **5-Day Predictions** — scoreable table per asset: Bias / Primary Driver / Confidence % / Target Range

Key prompt rules: confidence bounded 50%–70%; historical context anchored to `five_yr_mean`; VIX term structure used to distinguish acute from anticipated stress; minimum conviction requirement (at least one Bullish/Bearish call ≥57%).

### MA-2 — Adversarial Review (Claude Sonnet, max 250 tokens)

Receives only the predictions table + key risks (not the full analysis) to prevent rubber-stamping. Outputs a JSON delta `{asset: {append_risk, confidence_delta}}`. Python applies changes programmatically — numbers in Primary Driver are never touched by the model, eliminating autoregressive drift. Directional calls are clamped to ≥51% confidence.

### MA-3a — Portfolio Risk Agent (Claude Haiku, max 600 tokens)

Narrow context: only the current macro regime label + portfolio positions table. No FRED data, no accuracy history. Produces a structured `PortfolioRiskOutput` with: biggest headwind, biggest tailwind, one actionable observation, opportunity gap.

### MA-3b — Synthesis Agent (Claude Haiku, max 3000 tokens)

Receives the structured `AnalysisOutput` JSON and formats it into the final markdown note body. Python pre-formats the predictions table verbatim so the synthesis agent copies it without modification.

### Python Accuracy Override

`_apply_accuracy_override_structured()` runs post-review and applies four checks:

1. **Bias floor:** if any asset has directional accuracy <40% at n≥8 in any scoring window and the current call is Bearish, confidence is floored at 51% and a bias warning is appended to Primary Driver.
2. **Wasted signal warning:** if an asset has ≥70% directional accuracy at n≥10 in its best window but is called Neutral@50%, a `WARN` is emitted in CI output.
3. **Confidence clustering:** if 3+ directional calls share the same confidence figure, a `WARN` fires.
4. **All-Neutral collapse:** if every asset is called Neutral, a `FAIL` fires (minimum conviction rule violated).

The override uses `feedback_windows` (v0.3+ reports, adversarial review era) when available, falling back to `windows` (all reports).

---

## Prediction Scoring & Self-Calibration

### score_predictions.py

Runs weekly (Monday). Parses 5-Day Predictions tables from all `*-macro.md` reports and scores each at three horizons:

| Window | Trading Days | Calendar |
|--------|-------------|---------|
| T+5 | 5 | ~1 week |
| T+10 | 10 | ~2 weeks |
| T+20 | 20 | ~1 month |

Only scores once the evaluation date has fully passed (+ 1 day buffer). All prices fetched fresh from yfinance — never from the report's data snapshot.

**Scoring:** direction correct = 1.0 / wrong = 0.0 / flat move or Neutral = 0.5.

Flat threshold per asset:
- **10Y Treasury Yield:** 3 bps absolute change (`|eval_yield − entry_yield| < 0.03`). `^TNX` reports the yield as a level (e.g. `4.50`), so absolute difference is used — not a fractional return on the yield level.
- **All other assets:** 0.5% return (`|(eval − entry) / entry| < 0.005`).

Output: `results/scores/YYYY-MM-DD.json` per report (gitignored).

### summarize_accuracy.py

Aggregates score files into two metrics per asset per window:

- **Overall accuracy** — mean score including Neutral/flat (0.5 = random baseline)
- **Directional accuracy** — mean score on Bullish/Bearish calls with 0/1 outcomes; excludes flat moves and Neutrals (signal quality metric)

Tracks the **5 most recently deployed pipeline versions** in `results/accuracy_report.md`. The current `PIPELINE_VERSION` (from `versions.py`) is always included, even before it has any scored reports.

Outputs:
- `.macro-assist/data/accuracy_summary.json` — tracked in git, read by daily pipeline
- `results/accuracy_report.md` — human-readable, copied to vault

### Window-Aware Calibration

`load_accuracy_context()` dynamically identifies each asset's best-performing scoring window (highest directional accuracy at n≥8, preferring longer horizons on ties) and injects a "Best Prediction Window" table into the Claude prompt. Claude is instructed to anchor confidence to the best window and make a directional call for assets with ≥70% best-window directional accuracy.

---

## Quantitative Model Refit

`refit_models.py` + `macro_weekly_refit.yml` rebuild the HMM and conditional distributions every Sunday on fresh data, so the regime model doesn't drift as macro conditions evolve.

1. Fetch 5yr history: NFCI, DGS10, DGS2, BAMLH0A0HYM2 from FRED; SP500, Gold, WTI Oil prices from yfinance
2. Build (n\_days × 4) feature matrix aligned to business days; drop NaN rows
3. Refit `GaussianHMM(n_components=4)` via `regime.py`
4. Compute forward returns (T+5, T+10, T+20) per asset using integer-index offset over aligned prices
5. Classify each historical date into a macro bucket via `assign_bucket()` (NFCI × yield curve × HY spread)
6. Rebuild `conditional_distributions.json` via `conditional.py`
7. Commit `data/regime_model.pkl` + `data/conditional_distributions.json`

**First-time activation:** trigger `macro_weekly_refit` via `workflow_dispatch`, or run locally:
```bash
FRED_API_KEY=... python .macro-assist/refit_models.py
```

---

## Portfolio Intelligence (Optional)

When `data/tr_positions.csv` is present (Trade Republic transaction export), the daily pipeline injects a `## Portfolio Positions` block into the Claude prompt and the MA-3a portfolio risk agent produces a **Portfolio Risk Assessment** section.

`parse_positions.py` computes: net shares per position, average cost basis (EUR), current price (EUR, with USD→EUR conversion via `EURUSD=X`), unrealized P&L, and portfolio allocation %.

ISIN→ticker resolution uses a three-layer lookup: hardcoded overrides → local cache (`data/ticker_cache.json`) → OpenFIGI API (free, no key required). The cache is committed so CI never re-queries for known positions.

To check your positions locally:
```bash
python .macro-assist/parse_positions.py data/tr_positions.csv
```

---

## GitHub Actions Workflows

### macro_data_check.yml — Mon–Fri 06:00 UTC

Runs 30 minutes before the daily note as an early warning. Calls `collect_and_analyze.py --fetch-only` — no LLM, no file writes. Checks all data sources and exits non-zero if any critical source fails.

Does not require `ANTHROPIC_API_KEY` or `VAULT_PAT`.

### macro_daily.yml — Mon–Fri 06:30 UTC

1. Checkout Macro-Assist (write token) + External-Brain vault
2. Install Python dependencies
3. Run `collect_and_analyze.py` (fetch → analyze → write note to vault)
4. Copy note to `results/` in Macro-Assist and commit back

### macro_weekly_scoring.yml — Monday 07:15 UTC

Runs 45 minutes after the daily workflow to ensure Monday's note is written first.

1. Checkout Macro-Assist + vault
2. Run `score_predictions.py`
3. Run `summarize_accuracy.py`
4. Commit `accuracy_summary.json` to Macro-Assist
5. Copy `accuracy_report.md` to vault (`Economy/Analysis/prediction-accuracy.md`)

### macro_weekly_refit.yml — Sunday 22:00 UTC

1. Checkout Macro-Assist
2. Run `refit_models.py` (5yr FRED + market data fetch, HMM refit, distribution rebuild)
3. Commit `data/regime_model.pkl` + `data/conditional_distributions.json`

All workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. Scheduled runs always execute on the default branch (main).

---

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `FRED_API_KEY` | [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `VAULT_PAT` | GitHub Personal Access Token with `repo` scope (for pushing to External-Brain) |
| `VAULT_REPO` | External-Brain repo name, e.g. `GregsterBoe/External-Brain` |
| `SUPADATA_API_KEY` | [Supadata API key](https://supadata.ai) for YouTube transcripts (optional) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions. The workflows require `permissions: contents: write`, enabled in the workflow files and under repo Settings → Actions → General → Workflow permissions → Read and write.

COT positioning data is fetched directly from `cftc.gov` — no API key required.

---

## Version Management

Pipeline versions are centralized in `.macro-assist/versions.py`. To bump the version after a structural capability change:

1. Change `PIPELINE_VERSION` to the new `"vX.Y"` string
2. Close the last `VERSION_MILESTONES` entry (set end date to yesterday)
3. Append a new milestone entry with today as start and `date(2099, 12, 31)` as end
4. Run: `python .macro-assist/tag_versions.py && python .macro-assist/summarize_accuracy.py`

---

## Annual Maintenance

| Task | When | Where |
|------|------|-------|
| Update FOMC meeting dates | Every January | `FOMC_DATES` list in `collect_and_analyze.py` |
| Review sector ETF top holdings | Every quarter | `SECTOR_HOLDINGS` dict in `collect_and_analyze.py` |

FOMC dates source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

---

## Local Development

Install dependencies:
```bash
pip install -r .macro-assist/requirements.txt
```

Run the daily pipeline locally:
```bash
export FRED_API_KEY=...
export ANTHROPIC_API_KEY=...
export SUPADATA_API_KEY=...   # optional
python .macro-assist/collect_and_analyze.py
```

Run a data fetch check only (no LLM call, no file writes):
```bash
export FRED_API_KEY=...
python .macro-assist/collect_and_analyze.py --fetch-only
```

Output is written to `Economy/YYYY/MM-Month/` relative to the repo root by default. Override with:
```bash
export VAULT_ROOT=/path/to/your/vault
```

Set `MACRO_PREVIEW=1` to write a payload preview to `results/llm_payload_preview/<date>.md` — a section-size index plus the verbatim user message the model receives, and the signals computed but withheld from it (shadow fragility, retired HMM regime). Useful for inspecting what data is being injected. (The daily Action sets this automatically and prints the file to its log.)

Set `MACRO_PROFILE=loosened` to run the WP-16 loosened experiment arm — Opus 4.8 main model, conviction floor OFF (all-Neutral tables allowed), base-rate-first reasoning, and hard directional-override rules pruned, all bundled. `control` (default) preserves current production behaviour (Sonnet 4.6, floor on). Individual levers can be overridden independently of the profile: `MACRO_MODEL`, `CONVICTION_FLOOR`, `BASE_RATE_FIRST`, `PRUNE_RULES`. Each note records the resolved config in frontmatter (`config:` summary + `profile`/`model`/per-lever fields), and `summarize_accuracy.py` reports a Brier/BSS A/B by profile (and by floor) once ≥2 arms have scored data.

Run prediction scoring:
```bash
python .macro-assist/score_predictions.py
python .macro-assist/summarize_accuracy.py
```

To score against vault reports:
```bash
export MACRO_REPORTS_DIR=/path/to/External-Brain
python .macro-assist/score_predictions.py
```

Run the quant model refit locally:
```bash
export FRED_API_KEY=...
python .macro-assist/refit_models.py
```

Run the test suite:
```bash
pytest .macro-assist/tests/
```
