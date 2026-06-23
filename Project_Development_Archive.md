# Macro-Assist — Project Development Archive

Detailed design notes, Claude Code prompts, and the execution-order table for
**completed phases 1–14** (incl. Multi-Agent MA-0–MA-3 and the Quant Statistical
Layer 8–14). Moved out of `Project_Development.md` on 2026-06-16 to keep the live
plan lean — nothing is deleted; this is the historical implementation record.
Measured results live in `Knowledge_Base.md`; active plans in `Project_Development.md`.

---

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
