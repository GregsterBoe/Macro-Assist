# Scoring

How the system grades what it published.

There are two generations of scorer and one meta-instrument. The directional
scorer is frozen and winding down; the distribution scorer is the live one; and
`numeric_baseline.py` measures the *task* rather than the model. The reasoning
behind that split is [The cut](../concepts/the-cut.md).

## score_predictions.py

Runs weekly (Monday). Parses 5-Day Predictions tables from all `*-macro.md` reports and scores each at three horizons:

**As of v1.6 there are no new calls to score, anywhere in the repo.** The main note
stopped making them, and the two arms that still did — Kimi and exogenous — were stood
down on 2026-09-04 (WP-21.F). Post-cut notes are skipped by *version*
(`versions.has_directional_calls`), not by table shape, so a stray legacy-shaped table
cannot silently re-open the record.

The record is therefore **finite**. The last directional note is 2026-09-04 and its T+20
window resolves ~2026-10-02, so the weekly stage must keep running until then. Each run
reports how many reports still have an open window and prints a **DIRECTIONAL RECORD
CLOSED** banner once none do — that banner is the signal to retire the stage. Without it
the cron would print "0 score file(s) written" forever, which reads exactly like a silent
breakage.

`summarize_accuracy.py` and `bias_separation.py` keep working: they read the history, and
that history is the evidence base for KB-007 / KB-011 / KB-022.

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

## score_distributions.py

The successor to `score_predictions.py`, and the scorer for the product the note
actually publishes since v1.6. Shipped in Phase 22 (2026-09-08).

Reads `results/quant_context_log/*.jsonl`, writes `results/dist_scores/<date>.json`
plus `results/dist_scores_summary.json`, and runs as its own step in
`macro_weekly_scoring.yml`.

**Why the input needed no vintage reconstruction.** The quant log carries the
exact distribution the note published that day, drawn from a table fit at the
*prior* weekly refit. A logged quantile is knowable at `t` by construction — no
vintage to rebuild, no look-ahead to argue about.

**Metrics**

| Metric | What it is |
|---|---|
| Pinball loss at q=0.25/0.50/0.75 | The proper scoring rule for a quantile forecast — the distribution product's Brier. Minimised in expectation only at the true quantile, so it cannot be gamed by shading the interval |
| P25–P75 coverage | Against a nominal 0.50 |
| PIT histogram | Four bins — the whole PIT that three published quantiles can honestly support |
| Above-median sign balance | |

**Comparators, because three findings say a product without a rival scores as
skilled** ([KB-024], [KB-026], [KB-027]):

- `unconditional` — the same asset's full-history forward-return quantiles, **no
  macro bucket at all**. This is the test. The entire claim of the conditional
  layer is that conditioning beats not conditioning; if it does not beat this,
  the bucket machinery is decoration and gets recorded as decoration.
- `trailing_250` — a recent-regime rival with no macro state.
- `har_gaussian` — zero-mean Normal on the logged HAR σ, √h-scaled. Optional, and
  it **declines the 10Y outright**: converting a percent-return vol into a
  basis-point yield move needs the yield level and would make it a different
  model. Better no comparator than a wrong one.

**Sample alignment** ([The method](../concepts/the-method.md) §5). An observation
is emitted only when every required arm could quote a distribution for it, every
arm quotes *exactly the quantiles the note claimed that day*, and any head-to-head
skill score is computed on the shared subsample.

**Units do not pool.** Mean pinball loss is in the asset's own unit, so a
cross-asset mean would be adding basis points to percent. Per-asset is the primary
read; the only pooled figure is an equal-weighted mean of unit-free per-asset
*skill scores*, labelled as such. Coverage and PIT pool directly.

**Overlap.** Daily notes overlap 80% at 5d and 95% at 20d, so intervals come from
a block bootstrap over whole 21-report-date blocks — the same `BLOCK_DAYS` that
`bias_separation.py` uses, asserted by a test.

**Controls.** A negative control (stationary walk, where `unconditional` *is* the
truth) must report ~zero skill; a positive control (a planted regime the benchmark
cannot see) must be detected. Both are tests, not one-off checks.

**The bar is sealed.** `MIN_SKILL = 0.02` — deliberately not zero, settling in
advance the exact question [KB-027] left open for `EDGE_MIN_BSS`. `MIN_BLOCKS = 8`
≈ 8 months, so the earliest sealed read is **~2027-05**. Disqualifiers
(`underpowered` → `miscalibrated` → `inverted`) are evaluated first, each returning
its own verdict, with a test asserting each fires ahead of a strong skill number.
`verdict(sealed=False)` can only ever return `exploratory`.

```bash
python .macro-assist/score_distributions.py
```

## summarize_accuracy.py

Aggregates score files into two metrics per asset per window:

- **Overall accuracy** — mean score including Neutral/flat (0.5 = random baseline)
- **Directional accuracy** — mean score on Bullish/Bearish calls with 0/1 outcomes; excludes flat moves and Neutrals (signal quality metric)

Tracks the **5 most recently deployed pipeline versions** in `results/accuracy_report.md`. The current `PIPELINE_VERSION` (from `versions.py`) is always included, even before it has any scored reports.

Outputs:
- `.macro-assist/data/accuracy_summary.json` — tracked in git, read by daily pipeline
- `results/accuracy_report.md` — human-readable, copied to vault

## bias_separation.py

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

## numeric_baseline.py — the learnability test (WP-21.A)

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

`verdict()` applies a bar fixed before the numbers. `edge` requires n ≥ 30
decisive calls, decisive hit-rate > 0.52, and either BSS > 0 or an `aligned`
separation ordering — the same standard as [KB-007] / [KB-022]. Below n it
reports `underpowered`, not `no edge`.

!!! warning "Corrected after [KB-027]"
    As originally written, the pass clause was
    `hit > 0.52 AND (BSS > 0 OR aligned)`, so an `inverted` separation ordering
    was only ever consulted through the `aligned` disjunct — and a positive BSS
    satisfied the disjunct, skipping the ordering check in exactly the case it
    was written for. The hole was unreachable until an arm finally posted
    BSS > 0, which family 1 did, at +0.003.

    An `inverted` ordering now **disqualifies outright, before the pass clause**,
    and returns `inverted` as its own verdict rather than folding into `no edge`.
    A wrong-signed relationship is the single most repeated finding in this
    project; "did nothing" and "did something backwards" should not print the
    same word.

    `EDGE_MIN_BSS` was deliberately **left at 0.0**. Raising it after seeing a
    result it would have changed is a goalpost move and the pre-registration says
    nothing about a margin, so it is recorded as an open decision instead, pinned
    by `test_the_bss_margin_was_deliberately_left_alone`. See
    [ADR-0017](../decisions/ADR-0017-bss-floor-left-open.md).

## Window-Aware Calibration — retired in v1.6

`load_accuracy_context()` identified each asset's best-performing scoring window
(highest directional accuracy at n ≥ 8, preferring longer horizons on ties) and
injected a "Best Prediction Window" table into the Claude prompt, anchoring
confidence to that window and asking for a directional call on assets above 70%
best-window accuracy.

It was part of the self-calibration feedback loop, and it steered a directional
call that no longer exists. Retired with the rest of that machinery in v1.6 —
see [The cut](../concepts/the-cut.md) and
[ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md). Described here
because reports and findings from v1.5 and earlier were produced under it.

---

