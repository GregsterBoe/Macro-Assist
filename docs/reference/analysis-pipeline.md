# Analysis pipeline

The four Claude agents, what each one sees, and the model refit that feeds them.

For why it is split this way rather than one wide call, see
[The signal stack](../concepts/the-signal-stack.md#l2-the-llm-layer).

## The four agents

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

0. **Fragility Monitor** — the note's headline risk read, above everything else since
   v1.6. Computed in Python after the analysis (the model never writes it) from the
   composite plus the IMP-4 OR-of-channels flag. Carries its own honest limit inline:
   precision ≈0.32, so most firings are false alarms — high recall is the point.
1. **Executive Summary** — 2–4 sentences on the dominant macro development
2. **Macro Dashboard** — signal matrix (9 indicators × 4 asset classes). Note these
   cells are indicator *implications*, not per-asset scored calls; they are not what
   WP-21.D cut.

3. **Equities** — index moves, risk character, sector divergence, VIX term structure
4. **Rates & Fed Policy** — yield curve shape, real yield vs. breakeven decomposition, Fed trajectory
5. **Inflation & Growth** — CPI trend, GDP + unemployment regime read, M2, leading indicators
6. **Commodities** — Gold (real yield cross-reference), WTI (COT context), DXY
7. **Portfolio Risk Assessment** — position-level macro alignment (only when `tr_positions.csv` is present)
8. **Sector Opportunity Research** — 2–3 macro-driven sector tailwinds with P/E context
9. **Key Risks & Themes** — 3–5 actionable bullets for the next 1–4 weeks
10. **5-Day Outlook** — table per asset: 5d Conditional Distribution / Primary Driver / Target Range

> **v1.6 (WP-21.D): the directional product was cut.** Until v1.5 this table's first
> two columns were `Bias` (Bullish/Bearish/Neutral) and `Confidence %`. Three
> independent measurements said they were anti-informative — decisive calls resolved
> at ~36% with BSS −0.195 [KB-007], the bias label ordered forward returns *backwards*
> [KB-022], and an 18-year numeric baseline on the same panel lost to a constant
> `always_bullish` and inverted the same way [KB-024]. They were removed rather than
> hidden: the schema no longer has the fields, so the model is not asked for a call.
>
> What replaced them was already in the note, buried in the driver prose: the
> **empirical conditional return distribution** (median, P25/P75, n) for the current
> macro-state bucket. It is rendered by Python from `conditional_distributions.json`
> after the analysis, so the model cannot alter it. 10Y / DXY / Bitcoin have no
> conditional distribution and the column says so rather than improvising one.
>
> The note's risk read is now the **Fragility Monitor**, promoted to a headline block —
> it is the product with validated out-of-sample skill [KB-017/021], with its honest
> limit attached (precision ≈0.32: a high-recall warning, not a forecast).

Key prompt rules: describe forces, never predict an outcome; Target Range is a
dispersion band widened by uncertainty and never narrowed by confidence; historical
context anchored to `five_yr_mean`; VIX term structure used to distinguish acute from
anticipated stress; small-sample buckets (`n < 20`) disclosed explicitly.

### MA-2 — Adversarial Review (Claude Sonnet, max 250 tokens)

Receives only the outlook rows + key risks (not the full analysis) to prevent rubber-stamping. Outputs a JSON delta `{asset: {append_risk}}`. Python applies changes programmatically — numbers in Primary Driver are never touched by the model, eliminating autoregressive drift. The `confidence_delta` half of this pass was removed in v1.6 along with `confidence_pct`; the conditional distribution column is deliberately not shown to this agent, because measured data has nothing for an adversarial pass to revise.

### MA-3a — Portfolio Risk Agent (Claude Haiku, max 600 tokens)

Narrow context: only the current macro regime label + portfolio positions table. No FRED data, no accuracy history. Produces a structured `PortfolioRiskOutput` with: biggest headwind, biggest tailwind, one actionable observation, opportunity gap.

### MA-3b — Synthesis Agent (Claude Haiku, max 3000 tokens)

Receives the structured `AnalysisOutput` JSON and formats it into the final markdown note body. Python pre-formats the outlook table verbatim so the synthesis agent copies it without modification — since v1.6 that matters more than it did, because the distribution column is measured data and a formatter that "tidied" a percentile would be rewriting the product.

### Python Accuracy Override — RETIRED in v1.6

`_apply_accuracy_override_structured()` and its free-text twin used to apply four
checks after the adversarial pass: a bias floor on assets with <40% directional
accuracy, a wasted-signal warning at ≥70%, a confidence-clustering warning, and an
all-Neutral `FAIL`. Every one of them read or wrote `bias` / `confidence_pct`.

They were the feedback loop — score the calls, then steer next week's calls with the
result. [KB-024] closed the premise: correcting the direction of a call that carries
no information is not a smaller error, it is a more elaborate one. The calls are gone
and so is the machinery. The historical accuracy record is still produced (see below);
nothing reads it back into the prompt.

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

