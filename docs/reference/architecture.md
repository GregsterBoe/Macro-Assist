# Architecture

How the pieces fit together, where the code lives, and why generated output sits
on its own branch.

For the conceptual version — what each layer is *for* — see
[The signal stack](../concepts/the-signal-stack.md).

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
  ├── Python → render measured blocks (fragility, conditional distribution)
  │
  ├── push note → External-Brain/Economy/YYYY/MM-Month/
  └── push note → Macro-Assist/results/MM-Month/

Macro Pipeline · stage 1 (Mon–Fri, before the daily note)
  └── data fetch check (--fetch-only, no LLM call)

Macro Pipeline · stage 3 (Mondays)
  │
  ├── score past predictions (T+5/T+10/T+20) — legacy, winding down ~2026-10-02
  ├── score published distributions (pinball, coverage, PIT)
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


## Repository structure

```
Macro-Assist/
├── .macro-assist/                   # all pipeline code (dot-prefixed: it is
│   │                                #   infrastructure, not vault content)
│   ├── collect_and_analyze.py       # the daily entry point (--fetch-only for data checks)
│   ├── llm_analysis.py              # the four-agent LLM pipeline + note assembly
│   ├── schemas.py                   # Pydantic models for MA-1's structured output
│   ├── pipeline_common.py           # shared CLI/run plumbing
│   ├── pipeline_config.py           # run profiles and lever resolution
│   ├── versions.py                  # single source of truth for version constants
│   ├── bump_version.py              # version bump helper
│   ├── tag_versions.py              # backfill agent_version onto older reports
│   │
│   ├── fred_data.py                 # FRED fetch + derived series
│   ├── market_data.py               # yfinance prices, technicals, sector ETFs
│   ├── parse_positions.py           # Trade Republic portfolio parser
│   ├── youtube_data.py              # YouTube transcript fetcher
│   ├── calendar_events.py           # BLS + FOMC calendar
│   ├── assets.py                    # canonical asset registry (key/ticker/name/unit)
│   │
│   ├── quant_context.py             # builds the Quantitative Context block
│   ├── vol_forecast.py              # HAR-RV volatility forecasting
│   ├── regime.py                    # GaussianHMM fit + inference (retired from note)
│   ├── regime_features.py           # NFCI / yield-curve / HY / vol features
│   ├── conditional.py               # macro-bucketed conditional return distributions
│   ├── fragility.py                 # composite tail-risk index
│   ├── fragility_or.py              # OR-of-channels flag (IMP-4)
│   ├── refit_models.py              # weekly refit (HMM + distributions)
│   │
│   ├── score_predictions.py         # directional scorer — FROZEN, winding down
│   ├── score_distributions.py       # distribution scorer — the current one
│   ├── summarize_accuracy.py        # accuracy aggregation + per-version tracking
│   ├── bias_separation.py           # discrimination test on the bias buckets
│   ├── numeric_baseline.py          # the learnability harness (measures the task)
│   ├── input_ledger.py              # input provenance ledger
│   ├── input_testing.py             # improvement-track harness (IMP-1/IMP-4)
│   ├── citation_screen.py           # which inputs the model actually cites
│   ├── backtest.py                  # point-in-time backtesting harness
│   ├── regime_backtest.py           # walk-forward regime validation
│   ├── fragility_backtest.py        # de-overlapped fragility backtest
│   ├── point_in_time.py             # ALFRED-vintage reconstruction
│   ├── synthetic.py                 # synthetic data generator for tests
│   ├── kimi_arm.py                  # ensemble confidence arm — DEACTIVATED
│   │
│   ├── exogenous/                   # Phase 19 branch — SOFT-KILLED as a live arm
│   │   ├── DESIGN.md                #   the locked contract
│   │   └── ...                      #   spf.py, sep.py, fed_docs.py, extract.py,
│   │                                #   analyst.py, emit.py, synth.py, run_slice.py
│   ├── portfolio/                   # Phase 20 paper portfolio
│   │   ├── DESIGN.md                #   the locked contract
│   │   └── ...                      #   book.py, sizing.py, rebalance.py
│   │
│   ├── data/                        # committed model artifacts + caches
│   │   ├── accuracy_summary.json    #   read by the daily pipeline
│   │   ├── regime_model.pkl         #   refit weekly
│   │   ├── conditional_distributions.json
│   │   └── cot_history.json         #   rolling 54-week COT cache
│   ├── prompts/                     # system_prompt.md, system_prompt_structured.md,
│   │                                #   synthesis_prompt.md
│   ├── tests/                       # 33 test modules
│   ├── ci_mount_output.sh           # mount the output branch in CI
│   ├── ci_publish_results.sh        # commit & push results/ in CI
│   └── requirements.txt
│
├── .github/workflows/               # see Operations
├── data/
│   ├── tr_positions.csv             # Trade Republic export (optional, gitignored)
│   └── ticker_cache.json            # ISIN→ticker cache (committed)
├── results/                         # generated output — a git worktree on the
│   │                                #   'output' branch (see below)
│   ├── MM-Month/                    #   archived note copies
│   ├── scores/                      #   raw directional score JSON
│   ├── dist_scores/                 #   distribution score JSON (Phase 22)
│   ├── numeric_baseline/            #   learnability harness output
│   ├── quant_context_log/           #   daily JSONL snapshots of quant outputs
│   └── accuracy_report.md
│
├── docs/                            # this documentation set
│   ├── index.md
│   ├── concepts/                    #   the background needed to follow the work
│   ├── reference/                   #   how the system works today
│   ├── decisions/                   #   ADRs — why it is the way it is
│   └── record/                      #   KB, roadmap, board, TODO, archive
├── README.md                        # orientation + the map
├── mkdocs.yml                       # the documentation site
├── trigger_pipeline.sh              # the external cron caller
├── publish_output.sh                # commit & push results/ locally
└── pytest.ini
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


## Where the documentation lives

Since the 2026-09-08 restructure, every long-lived document is under `docs/`.
The working-memory file is [`docs/record/todo.md`](../record/todo.md): open
design decisions, known-but-unscheduled findings, and the reasoning behind each,
cited to file and line. Read it before picking up a phase, and update it when a
run surfaces something that needs a human call rather than a fix.
