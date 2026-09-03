# Macro-Assist

Automated daily macro intelligence pipeline. Every weekday morning a GitHub Actions workflow — started by an external cron service calling the GitHub API, not by GitHub's own scheduler ([why](#external-cron-trigger)) — fetches live economic and market data, runs a multi-agent Claude pipeline for structured analysis, and delivers a formatted Markdown note to an Obsidian vault. A separate weekly workflow scores the accuracy of past predictions and feeds that track record back into future reports as a self-calibration loop. A second weekly workflow refits the quantitative models on fresh data.

---

## Architecture

The project spans two GitHub repositories:

- **Macro-Assist** (this repo) — all scripts, workflows, prompts, accuracy data, and archived reports
- **External-Brain** — personal Obsidian vault; receives the daily note and accuracy report via git push

```
Macro Pipeline · stage 2 (Mon–Fri, one run per external cron call)
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

Macro Pipeline · stage 1 (Mon–Fri, before the daily note)
  └── data fetch check (--fetch-only, no LLM call)

Macro Pipeline · stage 5 (Mondays)
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
│   ├── bias_separation.py       # discrimination test: do the bias buckets separate returns?
│   ├── numeric_baseline.py      # WP-21.A learnability test: ridge/GBM walk-forward vs the LLM's metrics
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
│       ├── test_numeric_baseline.py
│       ├── test_point_in_time.py
│       └── test_synthetic.py
├── .github/
│   └── workflows/
│       ├── pipeline.yml              # THE entry point — external cron Mon–Fri (+catch-up, +backstop)
│       ├── macro_data_check.yml      # stage 1 — data fetch pre-check
│       ├── macro_daily.yml           # stage 2 — main pipeline
│       ├── exo_weekly_emit.yml       # stage 3 — exogenous arm (Mondays)
│       ├── kimi_arm_daily.yml        # stage 4 — kimi ensemble arm
│       ├── macro_weekly_scoring.yml  # stage 5 — prediction scoring (Mondays)
│       ├── portfolio_rebalance.yml   # stage 6 — paper rebalance (Mondays)
│       ├── macro_weekly_refit.yml    # Sunday 22:00 UTC — model refit (independent call)
│       └── numeric_baseline.yml      # WP-21.A learnability test — manual only, zero LLM spend
├── data/
│   ├── tr_positions.csv         # Trade Republic export (optional; gitignored)
│   └── ticker_cache.json        # ISIN→ticker cache (committed)
├── results/                     # generated output — lives on the 'output' branch,
│   │                            #   mounted here as a git worktree (see below)
│   ├── MM-Month/
│   │   └── YYYY-MM-DD-Weekday-macro.md  # archived report copies
│   ├── scores/                  # raw JSON score files per report
│   ├── numeric_baseline/        # WP-21.A learnability test output (isolated from scores/)
│   ├── quant_context_log/       # daily JSONL snapshots of quant outputs
│   └── accuracy_report.md       # human-readable accuracy summary
├── trigger_pipeline.sh          # start a workflow from outside GitHub (the cron call)
├── publish_output.sh            # commit & push results/ to the 'output' branch
├── Project_Development.md       # phased implementation roadmap
├── TODO.md                      # open decisions + carried findings across sessions
└── .gitignore
```

### Branch layout — code vs generated output

Code lives on **`main`**; all generated output (`results/`) lives on a separate
orphan branch, **`output`**. This keeps `main`'s history code-only and lets notes
pull results independently.

`results/` is a **git worktree** pinned to `output`, so scripts still read and
write `<repo>/results/` exactly as before — `main` gitignores it. First-time
local setup (after a fresh clone):

```bash
git fetch origin output
git worktree add results output
```

After a local run, publish generated output with `./publish_output.sh "msg"`.
In CI, `.macro-assist/ci_mount_output.sh` mounts `output` at `results/` before the
pipeline and `.macro-assist/ci_publish_results.sh` commits & pushes it after —
code-tracked files (`data/`, `.macro-assist/data/` models) still commit to `main`.
Notes should pull the **`output`** branch.

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

**Fragility Monitor** — `fragility.py` (+ `fragility_or.py`)

A 0–100 composite tail-risk gauge (variance trend, VIX term structure, level acceleration, cross-asset correlation), labelled Resilient / Normal / Elevated with a Rising / Stable / Falling trend. A **risk gauge, never a directional signal**. It runs in shadow via the `FRAGILITY_MODE` ladder (`log` → `show` → `active`, default `log`); at `log` the reading never enters the prompt. The optional `FRAGILITY_OR_MODE` ladder (default `off`) adds the higher-recall OR-of-channels flag (composite | absorption | turbulence, each vs. its own point-in-time top decile).

Where the reading shows up at the default `log` mode — computed once, surfaced three ways, so a shadow run is no longer invisible:

| Surface | What appears |
|---------|--------------|
| `results/quant_context_log/YYYY-MM-DD.jsonl` | the full raw reading (the accumulating shadow record) |
| Daily run log (`macro_daily.yml`) | `[FRAGILITY]` / `[FRAG-OR]` one-liners — composite, label, trend, top drivers; `WARN` when Elevated or the OR flag fires |
| The note's **Data Snapshot** | a `### Fragility Monitor` table, appended by `build_note()` *after* the LLM call — visible to you, still not to the model |

**Monitoring** — raw quant outputs (vol, regime, conditional, fragility) are logged to `results/quant_context_log/YYYY-MM-DD.jsonl` on each pipeline run for drift detection.

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

### bias_separation.py

Answers the question the accuracy score structurally cannot in a trending market: **conditional on what the model said, what did the market actually do?**

Accuracy conflates skill with drift — Neutral is pinned to 0.5 and a Bullish call scores 1.0 whenever the market rises, so a permanently-bullish model looks skilled while carrying no information. This module tests **discrimination** instead: it compares the realized forward return distribution across the Bullish / Neutral / Bearish buckets at each of T+5 / T+10 / T+20. If the buckets don't separate, the label is noise; if they do, the *ordering* says whether to read the label forward or backward.

- Returns are standardized within (window, asset) before pooling, so the result isn't an artefact of which assets got called Bullish (Bitcoin moves ~10% a fortnight, DXY ~0.5%).
- Significance uses a **block permutation test** (21-day blocks). Daily reports with a T+20 horizon share almost their entire evaluation window, so permuting individual labels would treat thousands of dependent observations as independent. The block count is reported next to every p-value — with a few months of data there are only a handful of independent blocks, so p is indicative and the effect's consistency across assets and horizons is the signal to trust.
- The verdict is one of `aligned` (Bullish > Neutral > Bearish — the label reads forward), `inverted` (the reverse — informative but backwards), or `mixed` / no separation.

Renders as the **Bias Separation** section of `results/accuracy_report.md`, adds a `bias_separation` key to `accuracy_summary.json`, and runs standalone:

```bash
python .macro-assist/bias_separation.py
```

Current reading is documented in **KB-022** (ordering is `inverted`, widening with horizon).

### numeric_baseline.py — the learnability test (WP-21.A)

Every accuracy reading in this repo measures **the LLM**. This module measures **the task**: it fits two deliberately small, regularised numeric models walk-forward on the inputs the pipeline already collects, and asks whether *anything* can predict 5/10/20-day direction on these assets.

- **`ridge`** — standardised L2 logistic regression (the scaler lives inside the pipeline, so it is fitted on the training fold only).
- **`gbm`** — a depth-2, 150-tree gradient booster. Depth 2 allows pairwise interactions and nothing deeper; ~150 independent 20-day windows across ~3 factors ([KB-009]) will not support more.
- **Comparators** — `neutral`, `random_walk` (the `backtest.py` rule) and `always_bullish`, scored on **exactly the model dates**.

Two guarantees carry the whole result, and both are enforced by tests rather than by convention:

1. **The panel cannot see the future.** ALFRED vintages would cost ~40k HTTP calls for a decade of daily walk-forward, so the module takes the other route: only inputs that are *never revised* are eligible — yfinance prices, and FRED's market-observed daily series (`DGS10`, `DGS2`, `BAA10Y`, `T10YIE`, `DFII10`, `VIXCLS`). Today's vintage is therefore the historical vintage. Revised or lagged-release macro (CPI, payrolls, M2, WALCL, NFCI, claims) is excluded by construction, and every series is shifted one business day so a print is only readable the day after it lands.
2. **The fit cannot see the future.** Walk-forward embargoes `horizon + 1` trading days: a prediction on `t` may train only on rows whose forward window closed strictly before `t`.

Scoring goes through the **production readers** — `score_predictions.score_call`, `summarize_accuracy._brier_and_reliability`, `bias_separation.bias_separation` — so a numeric arm and the LLM arm are held to one yardstick. Each model and comparator is emitted as its own `arm`, which makes the comparison a `calibration_by_arm` table for free.

Output lands in `results/numeric_baseline/` — `numeric_baseline.md` (the report), `numeric_baseline.json` (every metric and diagnostic), and, behind `--emit-scores`, the raw simulated calls as `scores.json.gz`. Deliberately **not** `results/scores/`, which would contaminate the live accuracy corpus. The `numeric_baseline.yml` workflow runs it manually in CI, where `FRED_API_KEY` lives.

```bash
# full run — needs FRED_API_KEY + network; caches the panel for offline re-runs
python .macro-assist/numeric_baseline.py --start 2005-01-01 --save-panel panel.csv

# offline re-analysis; --windows / --no-importance / --no-separation trade
# completeness for speed while iterating (never for a reported result)
python .macro-assist/numeric_baseline.py --panel panel.csv --windows t5
```

`verdict()` applies a bar fixed before the numbers: `edge` requires n ≥ 30 decisive calls, decisive hit-rate > 0.52, and either BSS > 0 or an `aligned` separation ordering — the same standard as [KB-007] / [KB-022]. Below n it reports `underpowered`, not `no edge`.

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

### pipeline.yml — the entry point (Mon–Fri 06:23 UTC, catch-up 10:47 UTC)

The single entry point, started by an
[external cron service](#external-cron-trigger). Its only `schedule:` is a late
backstop for the day the cron service itself fails. Every stage below is a **job** in this one run, ordered by `needs:` rather
than by cron offsets.

Stages 1–6 used to be six separate workflows fired by six separate crons spaced
15–30 min apart. GitHub's scheduler routinely fires 45–220 min late (measured
peak: 372 min on 2026-06-15) and drops runs entirely under load (2026-08-27:
nothing ran at all), so the gaps never reliably held the order. On 2026-08-03
scoring started 34 s after the kimi arm and both ran against the same commit —
that day's kimi note went unscored with every check green.

**Recovering a failed stage:** use *Re-run failed jobs* on the run. Only the
failed stage and the stages downstream of it re-run; completed stages are
skipped. You never need to re-run the whole pipeline to fix one stage.

**Catch-up run:** the 10:47 call re-enters the same pipeline. Stages no-op when
their output for the date already exists, so on a normal day it writes nothing
and costs about a minute per stage; on a day the morning call never landed — the
cron service was down, the token had expired, GitHub returned a 5xx — it fills
the gap unattended.

**The run's date** is resolved once by the `plan` job and passed to every stage
as `asof`; no stage derives its own. This matters because the delay above keeps
growing — on 2026-08-28 the two slots landed 12h25m and 10h28m late, both in the
evening. When a stage read the clock itself, a run that crossed UTC midnight
wrote the *next* day's note and left the intended day permanently empty, and the
Monday-only stages vanished, all with a green run. An external caller is prompt where GitHub's scheduler was not, but a retry after
an outage still lands late, so the guard stays: `plan` treats a start before
06:00 UTC as the previous day's slot (the earliest call is 06:23, so it cannot be
its own day's), and the `asof` input overrides the whole decision.

**Monday stages** (3, 5, 6) are selected by the `plan` job from the weekday of
that resolved `asof` — not from the wall clock — and are overridable via the
`weekly` dispatch input.

Each stage also keeps its own `workflow_dispatch` with its full input set, so any
one of them can still be run standalone from the Actions tab.

### macro_data_check.yml — stage 1

Runs before the daily note as an early warning. Calls `collect_and_analyze.py --fetch-only` — no LLM, no file writes. Checks all data sources and exits non-zero if any critical source fails.

Does not require `ANTHROPIC_API_KEY` or `VAULT_PAT`.

### macro_daily.yml — stage 2

1. Checkout Macro-Assist (write token) + External-Brain vault
2. Install Python dependencies
3. Run `collect_and_analyze.py` (fetch → analyze → write note to vault)
4. Copy note to `results/` in Macro-Assist and commit back

### macro_weekly_scoring.yml — stage 5 (Mondays)

Ordered after the daily note and both arm stages by `needs:`, so the week's
predictions are always committed before they are scored.

1. Checkout Macro-Assist + vault
2. Run `score_predictions.py`
3. Run `summarize_accuracy.py`
4. Commit `accuracy_summary.json` to Macro-Assist
5. Copy `accuracy_report.md` to vault (`Economy/Analysis/prediction-accuracy.md`)

### macro_weekly_refit.yml — Sunday 22:00 UTC

Its own cron call rather than a pipeline stage: it has no upstream dependency and
runs the night before Monday's pipeline, which picks up the fresh models. A
missed refit is not silent-but-fatal the way a missed daily note is — the models
just stay a week old and the next Sunday call refreshes them — so it has no
catch-up call.

1. Checkout Macro-Assist
2. Run `refit_models.py` (5yr FRED + market data fetch, HMM refit, distribution rebuild)
3. Commit `data/regime_model.pkl` + `data/conditional_distributions.json`

All workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. Cron calls dispatch `ref: main`, and the backstop schedule (like every GitHub schedule) runs on the default branch, so everything executes against `main`.

Stages 1–6 are reusable workflows (`workflow_call`) and carry no trigger of their own — `pipeline.yml` is the only scheduled entry point in the chain, so there is exactly one thing to check when a morning looks quiet.

Almost every run now arrives as a `workflow_dispatch`, which would otherwise make the Actions list an undifferentiated column of identical names. Each entry point sets a `run-name` from its `source` input, so the list reads `Macro Pipeline · cron-primary`, `· cron-catchup`, `· manual`, or `· schedule-backstop` at a glance.

---

## External cron trigger

GitHub's `schedule:` no longer starts the pipeline. An external cron service
does, by calling the workflow-dispatch API. `pipeline.yml` keeps one late
`schedule:` purely as a [backstop](#the-backstop); `macro_weekly_refit.yml` has
none.

**Why.** The scheduler was measured, not guessed: runs delivered 42–224 min late
through July/August 2026, peaking at 372 min on 2026-06-15; 12h25m and 10h28m
late on 2026-08-28; and on 2026-08-27 the day's schedules were dropped entirely
and nothing ran at all. Late delivery is what forced the `asof` plumbing (a run
crossing UTC midnight used to write the *next* day's note), and a dropped run is
worse than a failed one — there is no red check, just a silent gap in the series.
An external call is delivered when it is made, and when it fails it fails in the
caller's log where it can be alerted on.

### The schedule

All times UTC — set the cron service's timezone to UTC so the slots don't move
twice a year.

| Slot | Cron (UTC) | Call |
|---|---|---|
| Daily pipeline | `23 6 * * 1-5` | `pipeline.yml`, `source=cron-primary` |
| Catch-up | `47 10 * * 1-5` | `pipeline.yml`, `source=cron-catchup` |
| Weekly refit | `0 22 * * 0` | `macro_weekly_refit.yml`, `source=cron-refit` |

The catch-up is not a duplicate run: stages no-op when their output for the date
already exists, so it costs about a minute per stage and writes nothing unless
the morning call is missing. The odd minutes carry over from the old crons and no
longer matter — GitHub's contended `:00`/`:15`/`:30`/`:45` slots only affected its
own scheduler — but there is no reason to move them.

### The backstop

Moving off GitHub's scheduler moves the single point of failure rather than
removing it: if the cron service is down, its host is off, or the token has
expired, nothing calls the workflow at all. GitHub's scheduler is unreliable,
not dead — a late slot it *usually* delivers is worth having behind a caller
that might never fire.

So `pipeline.yml` keeps exactly one `schedule:`, at **14:37 UTC, Mon–Fri**. It is
not the trigger and is not meant to be on time: both external calls have long
since landed by then, so on a normal day it finds the date's output already
written and every stage no-ops — about a minute per stage, nothing committed. It
only does real work on a day nothing else called.

It sends no inputs (a schedule trigger can't), so `plan` labels it
`schedule-backstop` in the run name and the summary. If GitHub delivers *it* late
too, the date guard still holds: past midnight it resolves to the previous day —
correct, that is the day the run is for — and in the morning it resolves to the
new day, which the primary call has usually already written, so it no-ops. Either
way it cannot write the wrong day's note.

`macro_weekly_refit.yml` gets no backstop: a missed refit leaves the models a
week old and the next Sunday call refreshes them.

### The token

A **fine-grained PAT**, scoped to this repository only, with **Actions: read and
write** (plus the automatic Metadata: read). Nothing else — the token itself
cannot read the repo's secrets or push commits.

This token lives in the cron service, not in GitHub secrets: it is the credential
for getting *into* GitHub, so it cannot be stored behind the thing it opens.
Fine-grained PATs expire — note the expiry date somewhere you will see it, since
the symptom of an expired token is a `401` in the cron service's log and an
otherwise silent morning here.

### Setting it up

**On a host with a shell** (a VPS, a NAS, a Raspberry Pi) — `trigger_pipeline.sh`
in the repo root is the caller; it retries transport failures, GitHub 5xx and
rate limits with backoff, and explains the auth errors it will not retry:

```cron
# crontab -e, with MACRO_ASSIST_TOKEN exported for cron (e.g. in the crontab itself)
23 6  * * 1-5  /path/to/Macro-Assist/trigger_pipeline.sh --source cron-primary
47 10 * * 1-5  /path/to/Macro-Assist/trigger_pipeline.sh --source cron-catchup
0  22 * * 0    /path/to/Macro-Assist/trigger_pipeline.sh --workflow macro_weekly_refit.yml --source cron-refit
```

**On an HTTP-only service** (cron-job.org, EasyCron, Zapier, a Cloudflare Worker)
— configure one job per row of the table above:

```
POST https://api.github.com/repos/GregsterBoe/Macro-Assist/actions/workflows/pipeline.yml/dispatches

Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{"ref": "main", "inputs": {"source": "cron-primary"}}
```

Swap `pipeline.yml` for `macro_weekly_refit.yml` in the URL for the refit slot.
Send input values as **strings** (`"force": "true"`, not `true`) — GitHub coerces
them to the type the workflow declares. Any input the workflow exposes can be
passed the same way: `asof`, `force`, `kimi_n`, `pf_reset`, `weekly`.

### Checking it works

```bash
./trigger_pipeline.sh --dry-run --source cron-primary   # prints the request, sends nothing
MACRO_ASSIST_TOKEN=github_pat_... ./trigger_pipeline.sh --source manual-test
```

A `204 No Content` means GitHub accepted the request — not that the run
succeeded. The run then appears in the Actions tab named for its `source`, and
the `plan` job's summary repeats the source and the resolved `asof`.

| Symptom | Cause |
|---|---|
| `401` | Token invalid or expired — issue a new fine-grained PAT. |
| `403` | Token lacks *Actions: read and write* on this repo. |
| `404` | No such workflow with a `workflow_dispatch` trigger on `ref`, or the token cannot see the repo. The trigger must exist on the **default branch** — a workflow that only has it on a feature branch is not dispatchable. |
| `422` | Unknown input name or bad value. |
| No run at all, no error | The call was never made. This is the cron service's log to check, not GitHub's — turn on its failure notifications. The 14:37 backstop should have covered the day; if it didn't, GitHub dropped that slot too. |

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

The external cron token is deliberately **not** in this table: it lives in the cron service, not in GitHub secrets (see [External cron trigger](#external-cron-trigger)).

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
| Renew the external cron PAT | Before it expires | GitHub → Settings → Developer settings → Fine-grained tokens, then update the cron service |

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
