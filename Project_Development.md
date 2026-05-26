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
| v1.1 | 2026-05-26 – present | + MA-3b: synthesis agent |

### Output Schema

Every `*-macro.md` file carries `agent_version` in its YAML frontmatter, inserted after `type: macro-intelligence`:

```yaml
---
date: YYYY-MM-DD
day: Monday
type: macro-intelligence
agent_version: v1.1
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

**Goal:** Bring in high-frequency economic and liquidity data.

**New FRED series to add in `collect_and_analyze.py`:**

| Series | Description | Frequency |
|--------|-------------|-----------|
| `WALCL` | Fed Total Assets | Weekly |
| `WTREGEN` | Treasury General Account | Weekly |
| `RRPONTSYD` | Reverse Repo | Daily |
| `ICSA` | Initial Jobless Claims | Weekly |
| `NFCI` | Chicago Fed National Financial Conditions Index | Weekly |

**Fed Net Liquidity calculation (Python, before Claude call):**
```
Net Liquidity = WALCL - WTREGEN - RRPONTSYD
```
Compute WoW and MoM % change. Pass only the derived signal to Claude — e.g. `"Net Liquidity: Expanding, +1.2% WoW"`.

---

### Phase 2 — Shift the "Quant" Burden to Python *(Completed 2026-04-28)*

**Goal:** Stop asking Claude to infer trends from raw prices. Feed it pre-calculated technical states.

1. **Expand yfinance history window** from 10 days → **90 days** in `collect_and_analyze.py`. No cost difference.

2. **Add technical indicators** (via `pandas` or `pandas_ta`) for S&P 500, Gold, Oil, DXY, Bitcoin:
   - **14-day RSI** — flag as `Overbought` (>70), `Oversold` (<30), or `Neutral`
   - **Distance from 50-day MA** — e.g. `"+3.2% above 50d MA"`
   - **60-day Z-Score** — replace the simple notable-move detector

3. **New prompt block:** Structure output as `## Technical & Positioning State` table injected before Claude's analysis sections.

---

### Phase 3 — Add Free Positioning Data (COT) *(Completed 2026-04-28)*

**Goal:** Get institutional positioning data for Commodities and Currencies.

**Requires:** Free [Nasdaq Data Link](https://data.nasdaq.com/) API key → add as `NASDAQ_DATA_LINK_KEY` secret in GitHub Actions. Pipeline skips this block gracefully if the key is absent.

- `nasdaq-data-link>=1.0.0` added to `requirements.txt`
- `fetch_cot_data()` fetches CFTC net non-commercial positioning for WTI Crude (`CFTC/067651_FUT_ALL_CR`) and Gold (`CFTC/088691_FUT_ALL_CR`) — ~52 weeks of weekly data
- Computes percentile of current net long vs 1-year min/max range
- Injected as `## COT Positioning` block: percentile ≥80 = "Crowded Long — contrarian bearish"; ≤20 = "Crowded Short — contrarian bullish"; else "Neutral"
- System prompt rule added: COT is a contrarian signal, not a standalone entry — must confirm with price trend or fundamental catalyst

---

### Phase 4 — Overhaul System Prompt & Guardrails *(Completed 2026-04-28)*

**Goal:** Force Claude to use the new data correctly and cure observed doom bias in equity predictions.

**System prompt rules added (`prompts/system_prompt.md`):**
- Equity/liquidity rule: Fed Net Liquidity Expanding + RSI <70 + price above 50dMA → do not call S&P 500 Bearish on lagging indicators alone
- COT weighting rule: percentile ≥80 = contrarian bearish; ≤20 = contrarian bullish; COT must confirm with a catalyst
- NFCI and ICSA reading guides with level thresholds (matching HY Spread / Philly Fed pattern)

**Quantitative accuracy override — `_apply_accuracy_override()` in `collect_and_analyze.py`:**
- Runs after adversarial review on every daily note
- Reads `accuracy_summary.json`; if T+5 directional accuracy for any asset is <40% at n≥8 and the current call is Bearish, floors confidence at 50% and appends a bias warning to the Primary Driver cell
- Direction is intentionally kept (not flipped to Neutral) so calls remain scoreable and accuracy stats can recover naturally — flipping to Neutral would freeze the sample and lock in the bad stats permanently
- Currently fires on: S&P 500 (35%, n=17) and WTI Oil (33%, n=15)

---

### Phase 5 — Window-Aware Prediction Calibration *(Planned)*

**Goal:** Stop wasting the DXY signal. After 30 scored reports, the accuracy data is clear:

| Asset | T+5 dir. | T+10 dir. | T+20 dir. | Verdict |
|-------|----------|-----------|-----------|---------|
| DXY | 50% (n=12) | **82% (n=11)** | **87% (n=15)** | Best signal — currently discarded |
| Bitcoin | 63% (n=19) | 68% (n=19) | 25% (n=12) | Solid short/mid; degrades at 1 month |
| S&P 500 | 35% (n=17) | 18% (n=17) | **0% (n=18)** | Systematic inverse signal |
| WTI Oil | 33% (n=15) | 31% (n=16) | 27% (n=11) | Wrong at all horizons |

The current accuracy override anchors every asset to its *T+5* directional accuracy. DXY is called "Neutral, no edge" at T+5 (50%) even though it has an 87% signal at T+20 — the model's strongest read by far.

**Changes:**

1. **System prompt — predictions section:** Inject the accuracy table broken out by window (T+5 / T+10 / T+20). Instruct Claude to anchor confidence to the *window where directional accuracy is highest at n≥8*, and to name that window explicitly in the Primary Driver cell.

2. **Accuracy override (`_apply_accuracy_override`):** Pass window-level stats, not just T+5. Add a DXY conviction rule: if T+10 or T+20 directional accuracy ≥70% at n≥10, permit a directional call at ≥55% confidence even if T+5 is weak.

3. **Predictions table footnote:** Add a `Best Window` implicit note — Claude should state the horizon it is most confident about for each asset, especially when T+5 and T+20 diverge significantly.

---

### Phase 6 — Break the Neutral Collapse *(Done)*

**Goal:** Prevent all-Neutral reports. The accuracy override system overcorrected — reports now frequently show 5 of 6 assets at Neutral/50%, which produces no actionable signal.

**Problem:** The current override floors bad calls (Bearish S&P 500) at 50% Neutral. This is correct, but with no corresponding floor on the upside, the model defaults to Neutral as the safe answer for every uncertain asset.

**Changes:**

1. **Require at least one conviction call per report.** System prompt rule: the predictions table must contain at least one Bullish or Bearish call with confidence ≥57%. If all assets are Neutral, the model must identify which single asset has the strongest macro case and make a directional call on it, explicitly naming the uncertainty.

2. **Signed contrarian override for systematic inverse assets.** For assets where T+5 directional accuracy is <40% at n≥12 (currently S&P 500 and WTI Oil), allow a *low-confidence contrarian* call (50-53% confidence, labelled `[Contrarian — bias correction]`) rather than forcing Neutral. An asset that's been wrong 80% of the time carries information — inverting it weakly is more honest than pretending there is no signal.

3. **Confidence differentiation rule:** Prohibit more than 3 assets sharing the same confidence figure in one table. Forces the model to differentiate real signals from noise.

---

### Phase 7 — Sector Opportunity Research *(Done — 7d scoring deferred)*

**Goal:** Replace the repetitive "buy short-duration Treasuries" Opportunity Gap with a dedicated, scored section identifying sector- and stock-level opportunities aligned with current macro signals.

**Why the current Opportunity Gap fails:** It is one bullet inside Portfolio Risk Assessment with no data forcing depth or variety. The model reliably defaults to the always-defensible macro-cash trade. Without valuation data in the prompt, any stock name would be hallucinated as "undervalued."

#### 7a. Data Infrastructure (prerequisite)

Add `fetch_sector_fundamentals()` to `collect_and_analyze.py`:

- **Expand sector ETF coverage** from 5 → 11 ETFs: add XLV (Health Care), XLU (Utilities), XLP (Consumer Staples), XLB (Materials), XLRE (Real Estate), XLC (Communication Services).
- **Per-ETF fundamentals via yfinance:** forward P/E, trailing P/E, 52-week return, 1-month return, % above/below 52-week high. yfinance `.info` dict provides these without additional API keys.
- **Relative valuation:** rank all 11 ETFs by forward P/E percentile vs. their own 5yr average (yfinance `.info["forwardPE"]` vs a computed trailing mean). Flag any ETF whose fwd P/E is >1 std below its 5yr mean as "potentially undervalued."
- **Stock-level candidates (top 3–5 per sector):** pull fwd P/E, market cap, and 1yr return for the top 5 holdings of each flagged ETF (hardcoded holding lists per ETF, updated quarterly). No LLM hallucination — every number comes from yfinance.

#### 7b. New Prompt Section

Add `### Sector Opportunity Research` to `system_prompt.md`, placed between Portfolio Risk Assessment and Key Risks & Themes.

**Instructions to Claude:**

```
### Sector Opportunity Research

Identify 2–3 sectors where current macro signals (from the Dashboard and FRED data)
create a structural tailwind. For each sector:
- Name the ETF, its 1-month return vs. S&P 500, and its forward P/E vs. its 5yr average.
- State the one macro signal that drives the tailwind (specific data point, not generality).
- If the sector's fwd P/E is flagged as below 5yr average: name 1–2 specific stock
  tickers from the injected holdings list, their fwd P/E, and why the macro tailwind
  applies to that name specifically. Label every name explicitly:
  "Research candidate — not a recommendation. Verify independently."

Hard rules:
- Do not name a sector that lacks a specific data-driven macro rationale.
- Do not repeat the same lead sector on consecutive days (checked via injected prior note).
- Do not use the word "undervalued" without citing the fwd P/E vs. 5yr average figure.
- Maximum 200 words for this section. It must fit within the token budget.
```

#### 7c. Token Budget

Raise `max_tokens` from 4000 → 5000. The truncation-detection warning added in the code review will catch any remaining overflow.

#### 7d. Scoring (Accountability)

Extend `score_predictions.py` to score the 2–3 sector ETFs named each day as implicit directional calls at T+10 and T+20. This gives the section the same accountability as the predictions table and will surface whether the macro → sector mapping is actually predictive.

**Key design principle:** every number cited in this section is fetched by Python and injected — Claude synthesises, it does not invent. This is the lesson from the SPX accuracy failure: macro narrative without grounded data produces confident noise.

---

## Multi-Agent Architecture — Phases MA-0 through MA-3

**Strategic rationale.** Phases 1–7 enriched the data pipeline and added prompt rules as reactive patches to observed failures. The result is a system where a single LLM call carries conflicting objectives: interpret raw data, generate directional calls, write narrative, apply self-calibration, and assess portfolio risk simultaneously. This structure produces a specific class of failures — bias/narrative contradictions (Bullish label paired with "fade" commentary), meta-prompt leakage (instruction text echoed into output), and a model that hedges before making a call because it sees its own failure statistics inside the analysis prompt.

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

Each agent has one objective and a minimal information diet. Numbers travel between agents as typed JSON — never embedded in prose where they can drift through paraphrase. The synthesis agent assembles; it never re-analyzes.

**Placement.** These phases must be completed before Phase 8 (Validation Infrastructure). The backtest harness in Phase 8 is designed to compare pipeline versions — it should test the clean architecture, not the patched one. Migrating after Phase 8 would invalidate that baseline comparison.

---

### Phase MA-0 — Immediate Bug Fixes *(Done — 2026-05-22)*

Three bugs are directly fixable in the current code. They are standalone patches with no dependency on the multi-agent migration and should be shipped immediately.

#### MA-0.1 — Time-Travel Date in Fed Net Liquidity

**Root cause.** `_compute_net_liquidity()` sets `"date": combined.index[-1].strftime("%Y-%m-%d")`. The `combined` DataFrame uses `resample("W").last()`, which in pandas defaults to week-ending Sunday. When the pipeline runs on a Friday, the last resample period end is the following Sunday — placing the "As Of" date 2 days in the future. Reproduced in the May 22, 2026 report which displayed `As Of: 2026-05-24`.

**Fix in `_compute_net_liquidity()`.** Cap the date at today:

```python
# replace:
"date": combined.index[-1].strftime("%Y-%m-%d"),

# with:
"date": min(combined.index[-1].date(), datetime.now(timezone.utc).date()).strftime("%Y-%m-%d"),
```

#### MA-0.2 — Meta-Prompt Leakage Stripper

**Root cause.** The system prompt contains explicit instruction text (`Maximum 200 words for this section`). When the model approaches its token budget in sections like Sector Opportunity Research, it echoes these constraint phrases verbatim into the final output (e.g., `*Maximum 200 words — section complete.*`).

**Fix.** Add `_scrub_prompt_artifacts(text: str) -> str` in `collect_and_analyze.py`, called inside `analyze_with_claude()` before returning the analysis string:

```python
_ARTIFACT_PATTERNS = [
    re.compile(r'\*?Maximum \d+ words[^\n]*\*?', re.IGNORECASE),
    re.compile(r'\*?[Ss]ection complete\.?\*?', re.IGNORECASE),
    re.compile(r'\*?Token budget[^\n]*\*?', re.IGNORECASE),
]

def _scrub_prompt_artifacts(text: str) -> str:
    for pattern in _ARTIFACT_PATTERNS:
        text = pattern.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', text)  # collapse excess blank lines from removals
```

#### MA-0.3 — Bias / Narrative Contradiction Detector

**Root cause.** Bias label and Primary Driver text are written in one generation pass with no structural constraint linking them. The model can write `Bullish` in the Bias column while writing "contrarian call: fade near-term spike..." in the same row's Primary Driver — as seen in the WTI Oil call in the May 22 report.

**Fix.** Add `_check_prediction_consistency(analysis: str)` called from `_apply_accuracy_override()`. Logs a WARN to CI for human review without blocking the pipeline (the structural fix comes in Phase MA-1):

```python
_BULLISH_CONTRADICTIONS = frozenset({"fade", "fade the", "short ", "expect decline"})
_BEARISH_CONTRADICTIONS = frozenset({"short squeeze", "relief rally", "buy the dip"})

def _check_prediction_consistency(analysis: str) -> None:
    match = re.search(
        r'\| Asset \| Bias \|.*?\n(?:\|[^\n]+\n)+', analysis, re.DOTALL
    )
    if not match:
        return
    for line in match.group(0).splitlines():
        if not line.startswith("|") or "---" in line or "Asset" in line:
            continue
        cells = line.split("|")
        if len(cells) < 5:
            continue
        asset = cells[1].strip()
        bias  = cells[2].strip().lower()
        driver = cells[3].strip().lower()
        if bias == "bullish" and any(w in driver for w in _BULLISH_CONTRADICTIONS):
            _log("VALIDATE", "WARN", f"{asset}: Bullish bias contradicted by driver text")
        elif bias == "bearish" and any(w in driver for w in _BEARISH_CONTRADICTIONS):
            _log("VALIDATE", "WARN", f"{asset}: Bearish bias contradicted by driver text")
```

---

### Phase MA-1 — Structured Output Contract *(Done — 2026-05-24)*

**Goal.** Replace the free-form main analysis output with a Pydantic-validated JSON schema. This is the single most important architectural change — without a typed output contract, agents cannot pass results to each other reliably, and the structural contradictions caught manually in MA-0.3 become validation errors caught automatically.

**New file: `.macro-assist/schemas.py`**

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal

class AssetPrediction(BaseModel):
    asset: str
    bias: Literal["Bullish", "Bearish", "Neutral"]
    primary_driver: str = Field(min_length=10, max_length=350)
    confidence_pct: int = Field(ge=50, le=80)
    target_range: str
    horizon_days: int = 5

    @model_validator(mode="after")
    def bias_narrative_consistent(self):
        fade_words = {"fade", "fade the", "expect decline", "downside risk if"}
        if self.bias == "Bullish":
            for w in fade_words:
                if w in self.primary_driver.lower():
                    raise ValueError(f"Primary driver contradicts Bullish bias: '{w}' found")
        return self

class AnalysisOutput(BaseModel):
    executive_summary: str = Field(max_length=600)
    macro_regime: Literal["Risk-On", "Risk-Off", "Stagflation", "Reflation", "Neutral/Mixed"]
    equities_note: str = Field(max_length=500)
    rates_note: str = Field(max_length=500)
    inflation_growth_note: str = Field(max_length=500)
    commodities_note: str = Field(max_length=500)
    key_risks: list[str] = Field(min_length=3, max_length=5)
    predictions: list[AssetPrediction] = Field(min_length=6, max_length=6)
    sector_opportunity: str | None = Field(default=None, max_length=1200)
    portfolio_risk: dict | None = None
```

**Implementation.** Use Anthropic tool_use to force structured output: define a tool `submit_analysis` whose `input_schema` is the `AnalysisOutput` JSON schema, then pass `tool_choice={"type": "tool", "name": "submit_analysis"}`. The model must populate the schema; the tool input is parsed and validated by Pydantic. On `ValidationError`, retry once with the error injected as a correction message. On second failure, fall back to the current free-text path and log `FAIL` to CI.

**System prompt changes.** Remove: all `## Output Format` section-ordering instructions, word-count limits, markdown heading directives. The system prompt shrinks from ~241 lines to the analytical rules only (staleness thresholds, data usage rules, prediction methodology). The model fills fields — Python assembles markdown.

**`build_note()` change.** Receives `AnalysisOutput` object rather than a raw string. Assembles markdown from the typed fields in guaranteed section order. Meta-prompt leakage is impossible by construction — the model never writes markdown.

**Zero-downtime deployment.** If structured output fails twice, `analyze_with_claude()` falls back to the string-based path. This makes the migration safe to deploy with no risk to daily report production.

---

### Phase MA-2 — Analysis / Calibration Split *(Done — 2026-05-25)*

**Goal.** Remove the accuracy history from the analysis agent's information diet. The analysis agent makes its authentic data-driven call. Calibration is applied to the structured output separately, in Python.

**Core insight.** Injecting `## Your Historical Prediction Accuracy` (which states "S&P 500 T+5 directional accuracy 14%, SYSTEMATIC BIAS") into the analysis prompt causes the model to hedge the call *before forming it*. A model aware it has been wrong 14 of 17 times on SPX defaults to Neutral regardless of what the data says. Separating analysis from calibration removes this pre-emptive hedging — the analysis agent makes its best call, and calibration adjusts confidence afterward on the structured output.

**Changes to `analyze_with_claude()`:**

1. **Strip `accuracy_context` from the analysis agent user message.** The analysis agent receives only: FRED data, market data, technicals, COT, events, sector fundamentals, YouTube summaries. The prompt shrinks by ~60 lines.

2. **Repurpose the adversarial pass as a structured calibration agent.** Instead of receiving the full prose report (and regex-extracting the predictions table), the calibration agent receives only:
   - The `predictions` list from `AnalysisOutput` (6 rows of structured data)
   - The `key_risks` list
   - No raw data, no accuracy history
   
   Output is a `CalibrationOutput` dict:
   ```python
   # {asset: {"confidence_delta": int, "risk_flag": str | None}}
   {"WTI Oil": {"confidence_delta": -5, "risk_flag": "Driver text indicates fade — contradicts Bullish"}}
   ```

3. **Python applies accuracy overrides to `AnalysisOutput` directly.** The existing `_apply_accuracy_override()` logic is refactored to operate on the Pydantic object, modifying `prediction.confidence_pct` in place. This eliminates the fragile regex table-parsing in `_apply_adversarial_revisions()`.

**Why the ordering matters.** The analysis agent forms a view from data alone. The calibration agent flags contradictions between that view and listed risks. Python applies the historical accuracy discount. Each step is auditable — a diff of the `AnalysisOutput` before and after calibration makes every change explicit, replacing the current `_log_adversarial_diff()` string comparison.

---

### Phase MA-3 — Risk Agent + Synthesis Agent *(Done — MA-3a: 2026-05-25; MA-3b: 2026-05-26)*

**Goal.** Add a dedicated portfolio risk agent and a synthesis agent that composes the final report from structured inputs alone, completing the 3-agent architecture.

#### MA-3a — Risk Agent (Haiku)

Currently the portfolio risk section is embedded in the main analysis prompt. The analysis agent sees FRED macro data and portfolio positions simultaneously, producing portfolio commentary that is generic because the two contexts distract from each other.

The risk agent is narrow: it receives `macro_regime` (one field from `AnalysisOutput`) and the portfolio positions block. It knows nothing about FRED series, COT data, or prediction methodology.

```python
class PortfolioRiskOutput(BaseModel):
    biggest_headwind: dict   # {position: str, reason: str, pnl_label: str}
    biggest_tailwind: dict   # {position: str, reason: str}
    actionable: str = Field(max_length=200)
    opportunity_gap: dict    # {asset: str, rationale: str, reduces_concentration: bool}
```

Uses `claude-haiku-4-5-20251001`. Portfolio risk assessment is a narrow, structured task — Sonnet is unnecessary and would cost 5× more per call.

#### MA-3b — Synthesis Agent (Sonnet)

The synthesis agent is a copyeditor, not an analyst. It receives:
- `AnalysisOutput` (post-calibration)
- `CalibrationOutput` (risk flags to surface in narrative)
- `PortfolioRiskOutput` (if portfolio data present)

It sees **no raw data**. Its system prompt is ~15 lines: *"Format the provided structured JSON into the Macro Intelligence Note markdown template. Do not add analysis or data points not present in the JSON. Enforce section length by cutting, not by re-summarising. Strip any text that reads as an instruction or constraint echoed verbatim."*

The small, clean context eliminates the prompt-injection artifacts by framing: the synthesis agent has no instructions to echo.

#### Token economics

| Metric | Current | MA-3 target |
|--------|---------|-------------|
| Analysis context in | ~3,500 tokens | ~2,200 (no accuracy history, no portfolio) |
| Analysis output | 5,000 tokens prose | 1,800 tokens JSON fields |
| Calibration output | 250 tokens | 150 tokens structured deltas |
| Risk agent output | — | 400 tokens (Haiku) |
| Synthesis output | — | 1,800 tokens markdown |
| **Estimated daily cost** | **~$0.09** | **~$0.10–0.11** |

The ~15% marginal cost increase purchases qualitatively different reliability: structural contradiction detection, no meta-prompt leakage, calibration that does not suppress primary analysis.

#### Deployment sequence

1. MA-0 bugs: one PR, ship immediately
2. MA-1 structured output: one PR, zero-downtime fallback, ship when schema is stable
3. MA-2 calibration split: one PR, depends on MA-1 Pydantic objects in scope
4. MA-3a risk agent: one PR, parallel to MA-2 (independent of calibration refactor)
5. MA-3b synthesis agent: final cutover — retire free-text `build_note()` path after 5 consecutive structured-output reports pass manual review

---

## Quantitative Statistical Layer — Roadmap Extension (Phases 8–15)

**Strategic context.** Phases 1–7 enriched the data Claude sees and disciplined how it interprets that data. The next stage adds a **structured statistical layer** that feeds Claude pre-computed probabilistic context: volatility forecasts, regime classifications, and historical conditional return distributions. The goal is **not** to replace Claude's narrative analysis — it's to anchor the model's predictions to calibrated statistical reality, in the same spirit as the Phase 2 technical indicators but at a higher abstraction level.

**Compute footprint:** All math in Phases 8–15 is lightweight (HAR-RV is pandas operations; HMM training ~30s; conditional distributions are groupby + percentiles). It runs comfortably in GitHub Actions — **no local GPU or compute required**. Trained models and lookup tables are committed to the repo as small pickle/JSON files.

**Validation philosophy:** at each phase, no module is considered working until it (a) passes synthetic-data round-trip tests, (b) beats a naive baseline in backtest, and (c) survives visual inspection against known historical periods.

---

### Phase 8 — Validation Infrastructure *(To Implement — prerequisite for all subsequent phases)*

**Goal:** Build the backtest framework that lets every later phase be objectively validated. Without this, no module can be proven to work — it MUST be implemented before Phases 9–13.

**New dependencies:** none (uses existing `fredapi`, `requests`, `pandas`, `pytest`).

#### Phase 8.1 — Point-in-Time Data Layer

**New file:** `.macro-assist/point_in_time.py`
**New file:** `.macro-assist/tests/test_point_in_time.py`

**Function to implement:**
```python
def historical_snapshot(snapshot_date: date) -> dict:
    """
    Returns same structure as fetch_fred_data() output, but using ALFRED vintage data.
    ALFRED endpoint: https://api.stlouisfed.org/fred/series/observations
        ?series_id=X&realtime_start=YYYY-MM-DD&realtime_end=YYYY-MM-DD&api_key=...
    
    For each FRED series in FRED_SERIES, query the vintage that was published as of snapshot_date.
    yfinance market data: reuse existing fetch_market_data() — close prices don't revise materially.
    
    Returns dict with same keys as current fetch_fred_data() + a 'snapshot_date' meta field.
    """
```

**Validation tests (in `test_point_in_time.py`):**
- `test_no_future_leakage`: for 10 randomly sampled historical dates between 2020-01 and today, no returned series has a release_date > snapshot_date
- `test_schema_matches_current`: returned dict has same keys and types as live `fetch_fred_data()`
- `test_pre_alfred_raises`: calling with date < 1997 raises `ValueError` (most series lack ALFRED coverage before then)
- `test_market_data_present`: market data is fetched for the snapshot date (use yfinance with end=snapshot_date+1)

**Claude Code prompt:**
> In `.macro-assist/`, add a new module `point_in_time.py`. Expose `historical_snapshot(snapshot_date: date) -> dict` that returns FRED data as it was knowable on `snapshot_date` using ALFRED (FRED's archival API at `https://api.stlouisfed.org/fred/series/observations`). For each series in the existing `FRED_SERIES` dict, set `realtime_start` and `realtime_end` to `snapshot_date.isoformat()` so the returned observations represent the data available on that date. Reuse the existing `fetch_market_data()` logic for yfinance market series, but constrain it to data ending at `snapshot_date`. Output shape must match the current `fetch_fred_data()` output plus a `snapshot_date` meta key. Add unit tests in `.macro-assist/tests/test_point_in_time.py` covering: (1) no future leakage on 10 random sampled dates, (2) schema parity with current `fetch_fred_data()`, (3) ValueError when called with a date before ALFRED coverage, (4) market data is correctly truncated to snapshot_date. Run tests with `pytest .macro-assist/tests/test_point_in_time.py -v`.

---

#### Phase 8.2 — Backtest Harness

**New file:** `.macro-assist/backtest.py`
**New file:** `.macro-assist/tests/test_backtest.py`

**Function to implement:**
```python
def run_backtest(
    start_date: date,
    end_date: date,
    strategy: Callable[[dict], dict],
    output_dir: Path,
    skip_weekends: bool = True,
) -> dict:
    """
    Walk-forward simulator.
    For each date d in [start_date, end_date]:
        - Calls historical_snapshot(d) to get the data knowable on d
        - Calls strategy(snapshot) which must return a predictions dict matching
          the format that score_predictions.py expects
        - Writes predictions to output_dir / f"{d.isoformat()}.json"
    
    Returns aggregate metadata: {dates_processed, errors, output_dir}.
    """

# Baseline strategies (also in backtest.py):
def strategy_neutral(snapshot: dict) -> dict: ...
def strategy_random_walk(snapshot: dict) -> dict: ...
def strategy_existing_pipeline(snapshot: dict) -> dict: ...
```

**Validation tests:**
- `test_neutral_strategy_scores_random`: running neutral strategy over 6 months and scoring with `score_predictions.py` should produce ~50% directional accuracy (within ±5pp)
- `test_existing_pipeline_reproduces_history`: running existing pipeline as strategy over the past 30 scored days should reproduce `accuracy_summary.json` within ±2pp per asset

**Claude Code prompt:**
> In `.macro-assist/backtest.py`, implement `run_backtest(start_date, end_date, strategy, output_dir)` that walks day-by-day through the range, calls `historical_snapshot(d)` from `point_in_time.py`, then calls `strategy(snapshot)` and writes the prediction JSON to `output_dir`. The prediction dict format must match what `score_predictions.py` consumes (Bias / Target Range / Confidence / Primary Driver per asset). Include three baseline strategies in the same module: `strategy_neutral` (returns Neutral 50% for all assets), `strategy_random_walk` (predicts continuation of last 5d direction), and `strategy_existing_pipeline` (wraps the current `collect_and_analyze.main()` logic). Add tests verifying that neutral scores ~50% directional accuracy and that the existing-pipeline strategy reproduces current `accuracy_summary.json` numbers within ±2pp.

---

#### Phase 8.3 — Synthetic Data Generators

**New file:** `.macro-assist/synthetic.py`
**New file:** `.macro-assist/tests/test_synthetic.py`

**Functions to implement:**
```python
def synthetic_garch(n: int, omega: float, alpha: float, beta: float, seed: int = 42) -> np.ndarray:
    """GARCH(1,1) return series with known parameters."""

def synthetic_regime_switching(
    n: int,
    transition_matrix: np.ndarray,  # shape (k, k), rows sum to 1
    state_means: np.ndarray,        # shape (k,)
    state_vols: np.ndarray,         # shape (k,)
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (series, true_state_labels)."""

def synthetic_conditional(
    n: int,
    state_fn: Callable[[int], int],     # maps t -> macro state
    forward_means: dict[int, float],    # state -> mean forward return
    forward_vols: dict[int, float],     # state -> vol of forward return
    seed: int = 42,
) -> pd.DataFrame:
    """Returns DataFrame with columns: date, macro_state, forward_5d_return."""
```

**Validation tests:** round-trip — fit a GARCH/HMM/empirical-bucketing recovery procedure on synthetic output, verify recovered parameters match true parameters within statistical tolerance.

**Claude Code prompt:**
> Add `.macro-assist/synthetic.py` with three generators: (1) `synthetic_garch(n, omega, alpha, beta, seed)` producing a GARCH(1,1) return series; (2) `synthetic_regime_switching(n, transition_matrix, state_means, state_vols, seed)` producing a return series and a true state label series; (3) `synthetic_conditional(n, state_fn, forward_means, forward_vols, seed)` producing a DataFrame mapping macro state to forward returns. All use numpy + a seeded RNG for reproducibility. Tests in `.macro-assist/tests/test_synthetic.py` should verify: (a) GARCH series exhibits volatility clustering (autocorrelation of squared returns > 0.1 at lag 1), (b) regime-switching output state proportions match stationary distribution of the transition matrix within 5%, (c) conditional output respects forward_means within sampling tolerance.

---

### Phase 9 — Volatility Forecasting Layer *(To Implement — depends on Phase 8)*

**Goal:** Predict 5/10/20-day realized volatility per asset and compute the Variance Risk Premium against VIX. Inject as one block of pre-computed quantitative context.

**New dependencies:** `arch>=6.3.0` (add to `requirements.txt`).

#### Phase 9.1 — HAR-RV Model

**New file:** `.macro-assist/vol_forecast.py`
**New file:** `.macro-assist/tests/test_vol_forecast.py`

**Algorithm:** HAR-RV (Heterogeneous Autoregressive Realized Variance, Corsi 2009) is chosen over GARCH for three reasons: (a) simpler and more interpretable, (b) often outperforms GARCH on financial data per the literature, (c) easy to fit with plain pandas — no `arch` dependency needed for the core model (we still add `arch` for VRP utilities).

The model: `RV_{t+1} = β₀ + β₁·RV_daily + β₂·RV_weekly + β₃·RV_monthly + ε`

Where:
- `RV_daily` = today's squared return
- `RV_weekly` = mean of last 5 days' squared returns
- `RV_monthly` = mean of last 22 days' squared returns

**Function to implement:**
```python
def har_rv_forecast(returns: pd.Series, horizon: int = 5) -> dict:
    """
    Fits HAR-RV on `returns` (daily log returns) and forecasts `horizon`-day-ahead RV.
    Returns:
    {
        'forecast_daily_vol': float,           # annualized %
        'forecast_horizon_vol': float,         # annualized %, scaled to horizon
        'percentile_60d': float,               # rank of forecast vs trailing 60d realized vol
        'r_squared': float,                    # in-sample R²
        'params': {'beta_0', 'beta_d', 'beta_w', 'beta_m'},
    }
    """
```

Apply to: sp500, nasdaq, gold, wti_oil, bitcoin (skip dxy and vix themselves).

**Validation tests:**
- `test_recover_garch_vol`: on synthetic_garch(2000, ...), out-of-sample RMSE on last 500 obs should beat naive ("yesterday's RV = today's RV") by ≥10%
- `test_real_sp500_outperforms_naive`: fit on 2022-2024 SP500 returns, evaluate on 2025, RMSE should beat naive by ≥10%
- `test_r_squared_in_range`: in-sample R² should be in [0.2, 0.7] for SP500 (RV is genuinely predictable in this range)

**Claude Code prompt:**
> Implement `.macro-assist/vol_forecast.py` with `har_rv_forecast(returns: pd.Series, horizon: int = 5)`. The model is HAR-RV: `RV_{t+1} = β₀ + β₁·RV_daily + β₂·RV_weekly + β₃·RV_monthly`. Compute RV components from squared daily returns (RV_daily = r²ₜ, RV_weekly = mean of last 5, RV_monthly = mean of last 22). Fit via OLS (statsmodels or sklearn). Return forecasted volatility annualized to %, the 60-day percentile of the forecast vs trailing realized vol, R², and fitted parameters. Add `.macro-assist/tests/test_vol_forecast.py` with three tests: (a) on synthetic GARCH(1,1) data with omega=0.00001, alpha=0.1, beta=0.85, HAR-RV out-of-sample RMSE on last 500 obs beats naive by ≥10%; (b) on real SP500 data 2022-2024 (fit) / 2025 (test), RMSE beats naive by ≥10%; (c) in-sample R² for SP500 falls in [0.2, 0.7]. Use the `synthetic_garch` generator from Phase 8.3.

---

#### Phase 9.2 — Variance Risk Premium

**Extend:** `.macro-assist/vol_forecast.py`

**Function to implement:**
```python
def variance_risk_premium(vix: float, harrv_forecast: dict, history: pd.DataFrame = None) -> dict:
    """
    Computes VRP = VIX - HAR-RV annualized forecast for SP500.
    Returns:
    {
        'vrp': float,
        'vrp_60d_percentile': float,
        'interpretation': str,  # 'Compressed' / 'Normal' / 'Elevated'
    }
    """
```

**Validation tests:**
- `test_vrp_positive_on_average`: on full historical sample, mean VRP > 0 (well-documented stylized fact)
- `test_vrp_compressed_in_crisis`: VRP percentile during March 2020 and October 2022 should be < 30 (crisis compression)

**Claude Code prompt:**
> Extend `.macro-assist/vol_forecast.py` with `variance_risk_premium(vix, harrv_forecast, history=None)`. VRP = VIX − annualized HAR-RV forecast. Compute the 60-day percentile of current VRP vs its trailing distribution (history dataframe must include columns 'date', 'vix', 'realized_vol'). Interpretation thresholds: percentile ≤25 = 'Compressed', ≥75 = 'Elevated', else 'Normal'. Tests: (a) mean VRP positive on full historical 2020-2025 sample; (b) VRP percentile in March 2020 and October 2022 < 30.

---

### Phase 10 — Regime Classification Layer *(To Implement — depends on Phase 8)*

**Goal:** Classify the current macro regime (4 states) using a Hidden Markov Model on normalized macro features. Persist the trained model in the repo, refit weekly.

**New dependencies:** `hmmlearn>=0.3.0` (add to `requirements.txt`).

#### Phase 10.1 — Feature Engineering

**New file:** `.macro-assist/regime_features.py`
**New file:** `.macro-assist/tests/test_regime_features.py`

**Function to implement:**
```python
def regime_features(snapshot: dict) -> np.ndarray:
    """
    Extracts a 4-feature vector from a FRED+market snapshot:
        [0] nfci_percentile      (normalized 0-1 over historical range)
        [1] yield_curve_slope    (10Y - 2Y, in bps, raw)
        [2] hy_spread_zscore     (vs 5yr mean from snapshot)
        [3] realized_vol_pct     (60d annualized realized SP500 vol percentile)
    Returns numpy array shape (4,).
    """
```

**Validation tests:**
- `test_no_nan_on_recent_snapshots`: for 5 historical snapshots across 2024-2025, returned vector has no NaN
- `test_feature_distributions`: across 1000 historical snapshots, each feature's mean ∈ [-1, 1] and std ∈ [0.5, 2.0] (sanity check for normalization)

**Claude Code prompt:**
> In `.macro-assist/regime_features.py`, implement `regime_features(snapshot: dict) -> np.ndarray` returning a 4-feature vector: NFCI percentile (0-1 vs historical range), yield curve slope in bps (10Y minus 2Y, raw), HY spread Z-score (current vs 5yr mean from snapshot), 60-day realized SP500 vol percentile. All features should be roughly normalized to support HMM fitting. Add tests verifying no NaN on 5 historical snapshots and reasonable distributions (means/stds) across 1000 historical days.

---

#### Phase 10.2 — HMM Fitting and Inference

**New file:** `.macro-assist/regime.py`
**New file:** `.macro-assist/tests/test_regime.py`
**New artifact:** `.macro-assist/data/regime_model.pkl` (committed; refit weekly)

**Functions to implement:**
```python
def fit_regime_model(
    historical_features: np.ndarray,    # shape (n_days, 4)
    n_states: int = 4,
    random_state: int = 42,
) -> GaussianHMM:
    """Fits hmmlearn.GaussianHMM with full covariance. Returns fitted model."""

def predict_regime(model: GaussianHMM, current_features: np.ndarray) -> dict:
    """
    Returns:
    {
        'state': int,
        'state_label': str,            # human-readable
        'posterior': list[float],      # length n_states
        'transition_probs_from_current': dict[int, float],
    }
    """

def label_states(model: GaussianHMM) -> dict[int, str]:
    """
    Assigns labels by inspecting state means:
    - Lowest realized_vol_pct + lowest NFCI percentile -> 'Risk-On Low-Vol'
    - Highest realized_vol_pct + highest NFCI percentile -> 'Risk-Off High-Vol'
    - etc. for the remaining 2 states.
    """
```

**Validation tests:**
- `test_recover_synthetic_regimes`: on `synthetic_regime_switching(2000, known_transition_matrix, ...)`, fitted HMM's transition matrix should match the true matrix within ±0.1 per cell
- `test_historical_alignment`: print regime labels by month for 2020-present; manually verify that March-May 2020 is labeled 'Risk-Off High-Vol' and most of 2021 is 'Risk-On Low-Vol' (visual / assert-list test)
- `test_regime_persistence`: median dwell time across historical data should be 10-60 trading days

**Claude Code prompt:**
> Implement `.macro-assist/regime.py` with three functions: (1) `fit_regime_model(historical_features, n_states=4)` using `hmmlearn.GaussianHMM` with full covariance — fit and pickle to `.macro-assist/data/regime_model.pkl`; (2) `predict_regime(model, current_features)` returning state, label, posterior probability vector, and transition probabilities from the current state; (3) `label_states(model)` assigning 'Risk-On Low-Vol', 'Risk-On High-Vol', 'Risk-Off Low-Vol', 'Risk-Off High-Vol' to the 4 states based on inspection of state means (lower realized_vol_pct/NFCI = Risk-On; higher = Risk-Off; the second axis is vol). Add tests: (a) on `synthetic_regime_switching` with a known 4-state transition matrix, recovered matrix should match within ±0.1 per cell; (b) historical regime labels should mark March-May 2020 as 'Risk-Off High-Vol'; (c) median regime dwell time on 2020-2025 historical data is 10-60 trading days.

---

#### Phase 10.3 — Anti-Flicker Layer

**Extend:** `.macro-assist/regime.py`

**Function to implement:**
```python
def stable_regime_label(
    posteriors_history: list[np.ndarray],
    min_posterior: float = 0.7,
    min_dwell: int = 3,
) -> int:
    """
    Returns the regime label only if:
    - the top-posterior state has posterior > min_posterior
    - that state has been the top-posterior state for >= min_dwell consecutive days
    Otherwise returns the last stable label.
    Used to prevent daily label flipping that would confuse the LLM.
    """
```

**Validation tests:**
- `test_switch_count_reasonable`: applied over 2020-2025, total regime switches should be 4-12 (not 50+)

**Claude Code prompt:**
> Extend `.macro-assist/regime.py` with `stable_regime_label(posteriors_history, min_posterior=0.7, min_dwell=3)` that smooths raw HMM posterior labels by requiring both a confidence threshold and a minimum dwell time before relabeling. Test: applied over 2020-01 to today, total number of regime switches should fall in [4, 12].

---

### Phase 11 — Conditional Distribution Layer *(To Implement — depends on Phase 8)*

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

### Phase 12 — Quantitative Context Integration *(To Implement — depends on 9, 10, 11)*

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

### Phase 13 — End-to-End Validation *(To Implement — depends on 12)*

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

### Phase 14 — Production Hardening *(To Implement — depends on 13 passing)*

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
| 13 | **Phase 8 (Validation Infrastructure)** | **Medium** | **MA-3b complete** | 🔲 **To Implement** |
| 14 | **Phase 9 (Volatility Forecasting)** | **Medium** | **Phase 8** | 🔲 **To Implement** |
| 15 | **Phase 10 (Regime Classification)** | **Medium** | **Phase 8** | 🔲 **To Implement** |
| 16 | **Phase 11 (Conditional Distributions)** | **Medium** | **Phase 8** | 🔲 **To Implement** |
| 17 | **Phase 12 (Quant Context Integration)** | **Low** | **Phases 9, 10, 11** | 🔲 **To Implement** |
| 18 | **Phase 13 (End-to-End Validation)** | **High** | **Phase 12** | 🔲 **To Implement** |
| 19 | **Phase 14 (Production Hardening)** | **Low** | **Phase 13 passing** | 🔲 **To Implement** |
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