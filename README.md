# Macro-Assist

Automated daily macro intelligence pipeline. Every weekday morning a GitHub Actions workflow fetches live economic and market data, calls Claude Sonnet for structured analysis and a self-review pass, and delivers a formatted Markdown note to an Obsidian vault. A separate weekly workflow scores the accuracy of past predictions and feeds that track record back into future reports as a self-calibration loop.

---

## Architecture

The project spans two GitHub repositories:

- **Macro-Assist** (this repo) — all scripts, workflows, prompts, accuracy data, and archived reports
- **External-Brain** — personal Obsidian vault; receives the daily note and accuracy report via git push

```
GitHub Actions (06:30 UTC Mon–Fri)
  │
  ├── fetch FRED macro indicators (15 series, 5yr history each)
  ├── fetch market prices + technicals (yfinance, 90d history)
  ├── fetch sector ETF fundamentals (11 ETFs + holdings P/E)
  ├── fetch COT positioning (CFTC direct download, no API key)
  ├── fetch economic calendar (BLS + hardcoded FOMC dates)
  ├── fetch YouTube transcripts (Supadata API, if new video in 36h)
  ├── summarize transcripts (Claude Haiku)
  ├── inject historical prediction accuracy (accuracy_summary.json)
  ├── inject portfolio positions (tr_positions.csv, if present)
  │
  ├── Claude Sonnet → structured markdown note (main pass, 5000 tokens)
  ├── Claude Sonnet → adversarial review of predictions table
  ├── accuracy override → bias correction + clustering/collapse checks
  │
  ├── push note → External-Brain/Economy/YYYY/MM-Month/
  └── push note → Macro-Assist/results/MM-Month/

GitHub Actions (07:15 UTC Mondays)
  │
  ├── score past predictions (T+5, T+10, T+20)
  ├── aggregate accuracy stats → accuracy_summary.json
  ├── push accuracy_summary.json → Macro-Assist/.macro-assist/data/
  └── push accuracy_report.md → External-Brain/Economy/Analysis/
```

---

## Repository Structure

```
Macro-Assist/
├── .macro-assist/
│   ├── collect_and_analyze.py   # main pipeline script
│   ├── parse_positions.py       # Trade Republic portfolio parser
│   ├── score_predictions.py     # weekly prediction scorer
│   ├── summarize_accuracy.py    # accuracy aggregator
│   ├── youtube_data.py          # YouTube transcript fetcher
│   ├── requirements.txt
│   ├── data/
│   │   └── accuracy_summary.json  # tracked in git; read by daily pipeline
│   └── prompts/
│       └── system_prompt.md     # Claude analyst instructions
├── .github/
│   └── workflows/
│       ├── macro_daily.yml           # Mon–Fri 06:30 UTC
│       └── macro_weekly_scoring.yml  # Monday 07:15 UTC
├── data/
│   ├── tr_positions.csv         # Trade Republic export (optional; gitignored)
│   └── ticker_cache.json        # ISIN→ticker cache (committed)
├── results/
│   ├── MM-Month/
│   │   └── YYYY-MM-DD-Weekday-macro.md  # archived report copies
│   ├── scores/                  # gitignored — raw JSON score files
│   └── accuracy_report.md       # human-readable accuracy summary
└── .gitignore
```

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

Weekly CFTC Commitments of Traders data fetched via direct public download from `cftc.gov` (no API key required). Current-year and prior-year ZIP files are parsed to compute net non-commercial (speculative) positioning and its percentile vs. 1-year range. Injected as `## COT Positioning` block.

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

### Pass 1 — Main Analysis (Claude Sonnet, max 5000 tokens)

The system prompt (`prompts/system_prompt.md`) instructs Claude to produce exactly these sections in order:

1. **Executive Summary** — 2–4 sentences on the dominant macro development
2. **Macro Dashboard** — signal matrix (9 indicators × 4 asset classes: Equities / Bonds / Commodities / Crypto)
3. **Equities** — index moves, risk character, sector divergence, VIX term structure
4. **Rates & Fed Policy** — yield curve shape, real yield vs. breakeven decomposition, Fed trajectory
5. **Inflation & Growth** — CPI trend, GDP + unemployment regime read, M2, leading indicators
6. **Commodities** — Gold (real yield cross-reference), WTI (COT context), DXY
7. **Portfolio Risk Assessment** — position-level macro alignment (only when `tr_positions.csv` is present)
8. **Sector Opportunity Research** — 2–3 macro-driven sector tailwinds with P/E context and specific holdings (only when sector fundamentals data is present)
9. **Key Risks & Themes** — 3–5 actionable bullets for the next 1–4 weeks
10. **5-Day Predictions** — scoreable table per asset: Bias / Target Range / Confidence % / Primary Driver

Key system prompt rules:
- `days_stale` tiered treatment: ≤14 = current signal; 15–30 = note release date once; >30 = trend-only, mark "(stale)" in Dashboard
- Confidence bounded 50%–70% (no false certainty)
- Historical context anchored to `five_yr_mean` when available
- VIX term structure ratio used to distinguish acute from anticipated stress
- Notable moves opened first in their section
- Economic calendar events flagged in relevant section + Key Risks if within prediction window
- Minimum conviction requirement: predictions table must contain at least one Bullish/Bearish call ≥57% confidence

### Pass 2 — Adversarial Review (Claude Sonnet, max 600 tokens)

A second Claude call reviews the predictions table against the Key Risks section. It applies a high bar: only lowers confidence (by 5–10pp) and annotates the Primary Driver with `[Risk: label]` if a listed Key Risk would make the directional call **outright wrong** if it materialised. Confidence is floored at 50% in code regardless of model output.

### Pass 3 — Accuracy Override (Python)

`_apply_accuracy_override()` runs post-review and applies four checks:

1. **Bias floor:** if any asset has directional accuracy <40% at n≥8 in any scoring window and the current call is Bearish, confidence is floored at 50% and a bias warning is appended to Primary Driver.
2. **Wasted signal warning:** if an asset has ≥70% directional accuracy at n≥10 in its best window but is called Neutral@50%, a `WARN` is emitted in CI output.
3. **Confidence clustering:** if 3+ assets share the same confidence figure, a `WARN` fires (insufficient differentiation).
4. **All-Neutral collapse:** if every asset is called Neutral, a `FAIL` fires (minimum conviction rule violated).

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

Scoring: direction correct = 1.0 / wrong = 0.0 / flat move or Neutral = 0.5. Flat threshold: 3 bps for 10Y yield; 0.5% for all other assets.

Output: `results/scores/YYYY-MM-DD.json` per report (gitignored).

### summarize_accuracy.py

Aggregates score files into two metrics per asset per window:

- **Overall accuracy** — mean score including Neutral/flat (0.5 = random baseline)
- **Directional accuracy** — mean score on Bullish/Bearish calls with 0/1 outcomes; excludes flat moves and Neutrals (signal quality metric)

Outputs:
- `.macro-assist/data/accuracy_summary.json` — tracked in git, read by daily pipeline
- `results/accuracy_report.md` — human-readable, copied to vault

### Window-Aware Calibration

`load_accuracy_context()` dynamically identifies each asset's best-performing scoring window (highest directional accuracy at n≥8, preferring longer horizons on ties) and injects a "Best Prediction Window" table into the Claude prompt. Claude is instructed to anchor confidence to the best window and make a directional call for assets with ≥70% best-window directional accuracy.

---

## Portfolio Intelligence (Optional)

When `data/tr_positions.csv` is present (Trade Republic transaction export), the daily pipeline injects a `## Portfolio Positions` block into the Claude prompt and produces a **Portfolio Risk Assessment** section.

`parse_positions.py` computes: net shares per position, average cost basis (EUR), current price (EUR, with USD→EUR conversion via `EURUSD=X`), unrealized P&L, and portfolio allocation %.

ISIN→ticker resolution uses a three-layer lookup: hardcoded overrides → local cache (`data/ticker_cache.json`) → OpenFIGI API (free, no key required). The cache is committed so CI never re-queries for known positions.

To check your positions locally:
```bash
python .macro-assist/parse_positions.py data/tr_positions.csv
```

---

## GitHub Actions Workflows

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

Both workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. Scheduled runs always execute on the default branch (main).

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

Output is written to `Economy/YYYY/MM-Month/` relative to the repo root by default. Override with:
```bash
export VAULT_ROOT=/path/to/your/vault
```

Set `MACRO_DEBUG=1` to print the full assembled user message to stdout before the Claude call — useful for inspecting what data is being injected.

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
