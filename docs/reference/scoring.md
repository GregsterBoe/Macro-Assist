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
  Its σ is the logged `forecast_daily_vol`. **The fit window behind that number
  changed once, from the 2026-09-14 note** ([KB-033], `resolved.md` #17): the
  five sealed report dates 2026-09-07 → 09-11 were logged from a 90d fit
  measured as `degenerate`; from 09-14 the σ is a 5y fit. Both stay in the record — named against the seal in WP-22.C like
  [KB-028]'s conditioner change, not edited out. A date whose forecast the
  gate dropped has no `har_gaussian` arm, same as a logged zero before.

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

`verdict()` applies a bar fixed before the numbers
([ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)).
`edge` requires n ≥ 30 decisive calls, decisive hit-rate > 0.52, **BSS > 0.02**
*and* a BSS block-bootstrap 95% interval (21 report-date blocks, the unit
`bias_separation` and `score_distributions` share) whose lower bound is above
zero. The disqualifiers are read first, each with its own verdict: below n it
reports `underpowered`, an all-Neutral arm `abstains`, and an `inverted`
separation ordering returns `inverted` whatever the other numbers say. An
`aligned` ordering is a reported diagnostic, not a pass route. The headline table
prints the interval beside the BSS, and `meta.bar` in the JSON records the
constants a run was judged under. `0.02` is `score_distributions.MIN_SKILL`, and
a test keeps the two equal.

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

    `EDGE_MIN_BSS` was deliberately **left at 0.0** in that change. Raising it
    after seeing a result it would have changed is a goalpost move and the
    pre-registration said nothing about a margin, so it was recorded as an open
    decision ([ADR-0017](../decisions/ADR-0017-bss-floor-left-open.md)) and
    settled on 2026-09-13, with no candidate family on the table
    ([ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md)).
    The same change retired the `OR aligned` half of the old disjunct.
    `test_the_new_bar_relabels_nothing_in_the_record` is the check that the new
    bar changes no published verdict.

## class_bars.py — the class bars a promoted hypothesis is read against (WP-23.B)

A research-tier module holding one pre-registered bar per hypothesis *class*,
written before any member of the class is promoted
([how we explore §5](../concepts/how-we-explore.md#5-the-bar-precedes-the-candidate)).
The two quantile classes read observations in `explore_conditioner.py`'s
shape; the risk-rule class reads a daily path (below). It does not fetch
anything; [`sealed_runner.py`](#sealed_runnerpy-the-sealed-read-wp-23b) feeds it the sealed side.

| Class | Benchmark | Rival | Power | Clause cells | Seal |
|---|---|---|---|---|---|
| `conditioner` | `unconditional` | `har_scaled` | ≥ 8 blocks of 21 report dates, on the headline and on the rival's subsample | ≥ 63 report dates in ≥ 3 episodes | report dates 2018-01-01 → 2026-09-06 (`resolved.md` #19) |
| `gap_width` | `unconditional` | `trailing_250` | ≥ 10 four-quarter blocks, ≥ 40 quarters | ≥ 12 quarters in ≥ 3 episodes | **not decided** ([`todo.md`](../record/todo.md) #33) — a sealed read is refused |

Both classes use one pass clause for both comparators: pooled skill
> `MIN_SKILL` (0.02, Phase 22's) with a block-bootstrap interval clear of zero.
The headline is the equal-weight pooled skill over `ORIGINAL_KEYS` for the
conditioner and over the entry's series for the gap class. It is computed by
`pooled_skill`, which is the explore harness's statistic with the block as a
parameter; a test keeps the two identical at 21.

`verdict(bar, summary, clauses, sealed=…)` evaluates in this order and returns
at the first that fires: `exploratory` → `underpowered` → `miscalibrated`
(P25–P75 coverage interval excludes 0.50) → `inverted` → `no_edge` →
`explained_by_rival` → `unexplained` → `edge`. Every number is carried in the
result whichever verdict fires.

**A member's pre-registration** is a `Pre-registration` field in its register
entry: prose, then one fenced `json` block. `parse_preregistration` reads it,
and `validate` refuses unknown keys, a floor looser than the class's, an arm
that is the benchmark or the rival, and an empty clause list. An
illustration only — no entry has a pre-registration yet:

```json
{"class": "conditioner", "arm": "dd_x_frag", "horizon": 5,
 "floor": {"report_dates": 80, "episodes": 4},
 "clauses": [{"kind": "width_contrast", "series": "SP500",
              "a": {"dd_bin": ["dd-5..-10", "dd<-10"], "or_state": "Elevated"},
              "b": {"dd_bin": ["dd-5..-10", "dd<-10"], "or_state": "Normal"},
              "min_ratio": 1.0, "horizons": [5, 10, 20]}]}
```

The clause kinds:

- `width_contrast` needs the bootstrap interval of cell a's realized
  P75−P25 over cell b's to sit above `min_ratio`, which must be ≥ 1.
- `median_side` needs a cell's median minus the slice's to be clear of zero,
  on the named side.
- `skill_in_state` needs the arm's skill in a cell to be clear of zero, and
  optionally, with `null_in`, its skill in another cell to span zero.

A cell names labels the harness writes on each observation, and a list means
any of its values. A label the observations do not carry is refused, not
treated as empty. An episode is a run of a cell's report dates with no gap
longer than one block; a run longer than a year counts once per year.

`seal_key.py`'s preflight refuses the key for a promoted entry whose
pre-registration does not parse, or whose class has no decided seal.

### The risk-rule class (`RISK_RULE`, ADR-0023)

A member's output is an equity exposure *e<sub>t</sub>* in [0, 1], decided at
the close of *t* and traded at the close of *t* + 1, so it earns from day
*t* + 2. The rest sits in cash. `risk_read(path, spec, sealed=…)` takes a
daily path — `dates`, `equity` and `cash` daily returns, the member's
`exposure`, and the `signals` a clause may name — and builds every comparator
from it itself:

| Leg | Holds | Role |
|---|---|---|
| `member` | its own exposure | the candidate |
| `static_matched` | the member's mean exposure ē, every day | the pass clause's comparator: "just hold less stock" |
| `vol_matched` | min(1, *c* / σ̂<sub>t</sub>), σ̂ the sd of the trailing 21 daily returns, *c* set so the mean is ē | the rival: a volatility rule at the same average exposure |
| `buy_and_hold` | 1.0, no trades | reported only — "doing nothing" |

Every leg rebalances at each close and pays 10 bps (`DEFAULT_COST_BPS`) on
each unit traded; the whole read is repeated at 30 bps. An **episode** is a
stretch of buy-and-hold from one high to the next new high whose deepest point
is ≥ 10% below the high (`risk_episodes`; one still open at the end counts).
For each, *r* is a leg's deepest fall inside [peak, trough] over buy-and-hold's.

`risk_verdict` returns at the first that fires: `exploratory` → `underpowered`
(< 5 episodes, or the entry's stricter floor) → `inverted` (mean *r* > 1) →
`too_costly` (net annual return more than 0.5 pp behind `static_matched` at
10 *or* 30 bps) → `no_edge` (mean saving vs `static_matched` < 0.10, or its
90% episode-bootstrap interval touches zero) → `explained_by_rival` (mean
saving vs `vol_matched` not above zero, or better in fewer than two thirds of
episodes; a difference under 10⁻⁹ of a drop is a tie) → `unexplained` → `edge`.

Its one clause kind, `caught_split`, labels an episode *caught* when the named
signal fired between its peak and the day buy-and-hold first lost half the
episode's final depth — or up to `before_peak` trading days (0–63, default 0)
before the peak — and needs the mean saving in caught episodes to exceed the
mean in missed ones. With no caught or no missed episode it fails.

Reported for every leg at both costs and never read: worst drop, annual
return and volatility, time at reduced exposure, trades and turnover a year,
and the **tax brought forward** — the gain its sales realize a year on an
average cost basis, net of losses carried forward, × 18.46% (26.375% on the
taxable 70% of an equity fund's gain), as a share of the portfolio at the
year's start. An explore read refuses a path that reaches 2018-01-01; a sealed
read refuses one that starts before it. The sealed runner has no walk for this
class yet, so `--check` refuses it.

```json
{"class": "risk_rule", "arm": "h009_panel_or_half", "floor": {"episodes": 5},
 "clauses": [{"kind": "caught_split", "signal": "panel_or", "before_peak": 19}]}
```

```bash
python .macro-assist/class_bars.py          # print every bar
python .macro-assist/class_bars.py H-008    # parse this entry's pre-registration
```

## sealed_runner.py — the sealed read (WP-23.B)

The research-tier module that feeds a class bar the sealed side, once per
class. It walks the member's arm and the class's benchmark on the sealed report
dates, and the rival where it quotes, with the explore harness's own walk
(`explore_conditioner.observations_on`: known-by-*t* quantiles, `MIN_N = 10`,
the collapse ladder), carrying every label a cell may name. Quotes on the first
sealed date use everything known before it — the walk runs forward from 2010,
not fresh at the seal. `read_walked` then calls `class_bars.read(sealed=True)`,
which is honest because `walk` checks that no observation left the sealed side.

| Step | Where | Does |
|---|---|---|
| `--check` | anywhere, free | refuses a class with no walk (today: `gap_width`, `risk_rule`), an arm not in the harness's `ARMS`, a series that is not an asset, and a cell label or value the harness never writes (`LABELS`) — an empty cell would read `underpowered`. `seal_key.py`'s preflight runs it |
| `--fetch` | `sealed_read.yml` key job | the public inputs, to a file; nothing scored |
| `--claim` | key job | `sealed_reads/<hid>/<stamp>.claim.json`: the entry's stamped and bar text hashes, its pre-registration, the class bar's fingerprint, the run and the owner's approval. Pushed before the read |
| `--read` | key job | only once this run attempt's claim is on `output`: walk, read, write `<stamp>.json` (the verdict with every stage's number, the observations' sha256) and `<stamp>.md` (the report, verdict first) |
| `--sync-field` | anywhere, free | the entry's `Sealed read (ledger)` from CI's records |

Every data step refuses outside the key job of `sealed_read.yml` on `main`,
without the owner's approval on the run's record, or when `seal_key.py`'s
preflight refuses the entry — which includes a class whose slice already has a
claim. The guard stops an accident; the data is public, so it does not stop a
deliberate look (ADR-0022).

`record_audit.py` holds the records (on `output`, `sealed_reads/`):

- **`sealed-reads`** — one claim per class; every claim has a result, or it is
  a *lost read*; a result landed in a later commit than its claim; the class's
  bar fingerprint is what the claim recorded. Pins, each the owner's:
  `VOIDED_CLAIMS` (a claim whose run failed before any sealed number existed),
  `BAR_EDITS_AFTER_READ` (a defect fix the pre-registration already required).
- **`sealed-read-field`** — the entry's `Sealed read (ledger)` is exactly what
  those records render to, and an entry never read has none.

`bar_fingerprint(root, cls)` is sha256 over `class_bars.py` less its docstring,
its command line, `describe`, `BARS` and every other class's `ClassBar` or `RiskBar`, plus
the source of each name it imports from this repo. It is read as source text,
not imported and not `ast.dump`'d, so it is the same under the Python versions
CI runs and needs no numpy.

```bash
python .macro-assist/sealed_runner.py H-008 --check        # could it be walked?
python .macro-assist/sealed_runner.py H-008 --sync-field   # the ledger from CI's records
```

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

