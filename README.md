# Macro-Assist

Automated daily macro intelligence pipeline. Every weekday morning, a GitHub Actions workflow fetches live market and economic data, calls Claude for structured analysis, and delivers a formatted note to an Obsidian vault. A separate weekly workflow scores the accuracy of previous predictions and feeds that track record back into future reports.

---

## Architecture

The project spans two GitHub repositories:

- **Macro-Assist** (this repo) — all scripts, workflows, prompts, and archived reports
- **External-Brain** — personal Obsidian vault; receives the daily note and accuracy report via git push

```
GitHub Actions (06:30 UTC Mon–Fri)
  │
  ├── fetch FRED macro indicators
  ├── fetch market prices (yfinance)
  ├── fetch YouTube transcripts (Supadata API)  ← if new video in last 36h
  ├── summarize transcripts (Claude Haiku)
  ├── inject historical prediction accuracy
  │
  ├── Claude Opus → structured markdown note
  │
  ├── push note → External-Brain/Economy/YYYY/MM-Month/
  └── push note → Macro-Assist/results/MM-Month/

GitHub Actions (07:15 UTC Mondays)
  │
  ├── score past predictions (T+5, T+10, T+20)
  ├── aggregate accuracy stats
  ├── push accuracy_summary.json → Macro-Assist/.macro-assist/data/
  └── push accuracy_report.md → External-Brain/Economy/Analysis/
```

---

## Repository Structure

```
Macro-Assist/
├── .macro-assist/
│   ├── collect_and_analyze.py   # main pipeline script
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
│       ├── macro_daily.yml      # Mon–Fri 06:30 UTC
│       └── macro_weekly_scoring.yml  # Monday 07:15 UTC
├── results/
│   ├── MM-Month/
│   │   └── YYYY-MM-DD-Weekday-macro.md  # archived report copies
│   ├── scores/                  # gitignored — raw JSON score files
│   ├── accuracy_report.md       # human-readable accuracy summary
│   └── accuracy_summary.json    # (also at .macro-assist/data/)
└── .gitignore                   # excludes results/scores/ only
```

---

## Data Sources

### FRED Macro Indicators
Fetched via `fredapi`. All series pulled from 2024-01-01 onward; latest and prior values captured.

| Series | FRED ID |
|--------|---------|
| Fed Funds Rate | `FEDFUNDS` |
| CPI | `CPIAUCSL` (YoY % computed) |
| GDP | `GDP` |
| Unemployment | `UNRATE` |
| M2 Money Supply | `M2SL` (YoY % computed) |
| 10Y Treasury Yield | `DGS10` |
| 2Y Treasury Yield | `DGS2` |

Yield curve spread (10Y − 2Y) is computed at runtime.

### Market Prices
Fetched via `yfinance` using the last 10 days of daily history. Latest close and 1-day % change captured.

| Asset | Ticker |
|-------|--------|
| S&P 500 | `^GSPC` |
| Nasdaq | `^IXIC` |
| Gold | `GC=F` |
| WTI Oil | `CL=F` |
| VIX | `^VIX` |
| DXY | `DX-Y.NYB` |

### YouTube Transcripts (optional)
Configured channels are checked for videos published in the last 36 hours via the YouTube public RSS feed (no API key required). If a new video is found, the full transcript is fetched via the [Supadata API](https://supadata.ai) and summarized to 6–8 macro-relevant bullet points using Claude Haiku before being passed to the main report call.

Currently configured channel: **Bravos Research** (`UCOHxDwCcOzBaLkeTazanwcw`)

To add channels, edit `YOUTUBE_CHANNELS` in `.macro-assist/collect_and_analyze.py`:
```python
YOUTUBE_CHANNELS = [
    ("UCOHxDwCcOzBaLkeTazanwcw", "Bravos Research"),
]
```

---

## Report Format

Each report is a Markdown file with YAML frontmatter. Sections are produced by Claude in a fixed order enforced by the system prompt:

1. **Executive Summary** — 2–4 sentences on the dominant macro development
2. **Macro Dashboard** — signal matrix table mapping 7 indicators × 4 asset classes (Bullish / Bearish / Neutral / Caution)
3. **Equities** — S&P 500, Nasdaq, VIX analysis
4. **Rates & Fed Policy** — yield curve, Fed trajectory
5. **Inflation & Growth** — CPI, GDP, unemployment, M2
6. **Commodities** — Gold, WTI Oil, DXY
7. **Key Risks & Themes** — 3–5 actionable bullet points
8. **5-Day Predictions** — scoreable table with Bias, Target Range, Confidence %, Primary Driver per asset
9. **Data Snapshot** — raw market and FRED tables appended by the script

Reports are saved to:
- Vault: `Economy/YYYY/MM-Month/YYYY-MM-DD-Weekday-macro.md`
- This repo: `results/MM-Month/YYYY-MM-DD-Weekday-macro.md`

Idempotency: if today's note already exists at the output path, the script exits early.

---

## Prediction Scoring

### score_predictions.py
Scores directional accuracy of the 5-Day Predictions table at three horizons.

**Scoring windows:**
| Label | Horizon | Description |
|-------|---------|-------------|
| `t5` | 5 trading days | ~1 calendar week |
| `t10` | 10 trading days | ~2 calendar weeks |
| `t20` | 20 trading days | ~1 calendar month |

A window is only scored once its evaluation date has fully passed (+ 1 day buffer). Reports without a predictions table (pre-March 13) are skipped.

**Scoring logic:**
- Entry price: closing price on the report date
- Evaluation price: closing price on the evaluation date (or next trading day)
- Flat threshold: moves < 0.5% (or < 3 bps for yields) score 0.5 regardless of direction
- `Bullish` correct = 1.0, wrong = 0.0, flat move = 0.5
- `Bearish` correct = 1.0, wrong = 0.0, flat move = 0.5
- `Neutral` always scores 0.5 (excluded from directional accuracy)

Prices for scoring are fetched fresh from yfinance — not taken from the report itself — to avoid the data entry errors present in early reports.

Output: `results/scores/YYYY-MM-DD.json` per report (gitignored).

### summarize_accuracy.py
Reads all score files and computes two metrics per asset per window:

- **Accuracy** — mean score across all calls (0.5 = random baseline)
- **Directional accuracy** — mean score on calls that resolved as 0 or 1 (excludes flat moves and Neutral calls; measures signal quality)

Outputs:
- `.macro-assist/data/accuracy_summary.json` — machine-readable, tracked in git
- `results/accuracy_report.md` — human-readable markdown table

### Feedback loop
`collect_and_analyze.py` reads `accuracy_summary.json` at runtime and injects a compact accuracy table into the Claude prompt. Claude sees its own historical track record per asset per horizon before writing new predictions, allowing it to self-calibrate confidence levels.

---

## GitHub Actions Workflows

### macro_daily.yml — Mon–Fri 06:30 UTC
1. Checkout Macro-Assist + External-Brain vault
2. Install Python dependencies
3. Run `collect_and_analyze.py` (FRED + market fetch → optional YouTube → Claude analysis → write note)
4. Commit and push note to vault (`Economy/`)
5. Copy note to `results/` and commit back to Macro-Assist

### macro_weekly_scoring.yml — Monday 07:15 UTC
Runs 45 minutes after the daily workflow to ensure Monday's note is written first.

1. Checkout Macro-Assist + vault
2. Run `score_predictions.py` with `MACRO_REPORTS_DIR` pointing at the vault
3. Run `summarize_accuracy.py`
4. Commit `accuracy_summary.json` to Macro-Assist
5. Copy `accuracy_report.md` to vault (`Economy/Analysis/prediction-accuracy.md`)

Both workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. When triggered manually, use the branch dropdown to test feature branches before merging to main. Note: scheduled runs always execute on the default branch (main).

---

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `FRED_API_KEY` | [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `VAULT_PAT` | GitHub Personal Access Token with `repo` scope (for pushing to External-Brain) |
| `VAULT_REPO` | External-Brain repo name, e.g. `GregsterBoe/External-Brain` |
| `SUPADATA_API_KEY` | [Supadata API key](https://supadata.ai) for YouTube transcripts (optional) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions — do not create it manually. The workflows require `permissions: contents: write` to push back to Macro-Assist, enabled both in the workflow files and under repo Settings → Actions → General → Workflow permissions → Read and write.

---

## Annual Maintenance

| Task | When | Where |
|------|------|-------|
| Update FOMC meeting dates | Every January | `FOMC_DATES` list in `.macro-assist/collect_and_analyze.py` |

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

By default, output is written to `results/` relative to the repo root. Override with:
```bash
export VAULT_ROOT=/path/to/your/vault
```

Run prediction scoring:
```bash
python .macro-assist/score_predictions.py
python .macro-assist/summarize_accuracy.py
```

To score against vault reports locally:
```bash
export MACRO_REPORTS_DIR=/path/to/External-Brain
python .macro-assist/score_predictions.py
```
