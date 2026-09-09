# The method

This is the most transferable thing in the repository. The pipeline is a few
thousand lines of ordinary Python; the discipline below is what let it discover
that its own headline feature was worthless, and say so in writing.

Read this before designing, running or interpreting any experiment here.

---

## 1. Findings are written down, and negatives count

Every measured result becomes a numbered entry in the
[Knowledge Base](../record/knowledge-base.md), whichever way it comes out. The
format is fixed: **what was tested → the headline → the nuance that is easy to
forget → what it changes.**

Of the 26 entries, most are negative. That is not pessimism, it is the design
working: an experiment that can only produce a positive result is not an
experiment. KB-018 (downside asymmetry adds nothing), KB-019 (credit is
redundant), KB-026 (the SPF anchor carries no direction) and KB-027 (neither
does the VIX term structure) each cost real work and each saved more.

The corollary is a rule about **when** you may compress a plan: never trim a work
package out of the roadmap before its result is in the Knowledge Base. Losing the
plan is fine once the finding is recorded; losing both is how a project forgets
what it already tried.

## 2. Pre-register the read before the run

Write down what would count as a pass — the metric, the threshold, the sample
size, and what each possible outcome would mean — **and commit it** before the
numbers exist.

This is not ceremony. It is the only thing that distinguishes a legitimate
correction from rescuing a result you dislike, and the project has now needed
that distinction twice:

!!! quote "KB-027, on correcting a bar after seeing a result"
    "The change makes the function do what the pre-registration already said.
    That distinction is the whole defence and it only holds because the
    pre-registration was committed before the run — had the read not been written
    down first, this correction would be indistinguishable from rescuing a
    disliked result, and there would have been no honest way to make it."

The matching discipline is knowing when you have crossed the line. In the same
episode, `EDGE_MIN_BSS` was left at 0.0 even though a floor of literally zero is
obviously too loose — because raising it *after* seeing a result it would have
changed is a goalpost move, and the pre-registration said nothing about a margin.
It was recorded as an open decision instead, with a test pinning it
([ADR-0017](../decisions/ADR-0017-bss-floor-left-open.md)).

## 3. Seal the holdout, and time the sealing honestly

A pre-registered bar is only worth something if the data it will be read against
does not exist yet, or has never been looked at.

Phase 22 is the clean example. P25/P75 quantiles first entered the quant log on
2026-09-07. The bar was written on 2026-09-08 — the one window in which the
interval record had **zero** resolved observations, so the threshold could not
have been tuned to it even accidentally. `MIN_BLOCKS = 8` puts the earliest
honest read around May 2027, and the project is content to wait.

The same run produced the counter-example, labelled as such: a median-only
backfill running back to 2026-05-29 that had already been seen. It is recorded
as **exploratory** and the code physically cannot return anything else for it —
`verdict(sealed=False)` returns `exploratory` and nothing stronger, so an
exploratory number can never be dressed up as a result later.

## 4. Always put a trivial rival next to the product

Three separate findings in this repo say the same thing: **a product with no
trivial comparator will score as skilled.**

| Finding | The product | The trivial rival | Result |
|---|---|---|---|
| KB-024 | ridge / GBM directional models | `always_bullish` | The constant beat both on hit-rate, Brier, BSS *and* calibration simultaneously |
| KB-026 | the SPF exogenous anchor | `always_bullish` | Lost on Brier, BSS and ECE |
| KB-027 | the VIX term structure | `always_bullish` | +0.006 margin, negative at t20 |

So Phase 22 was built with `unconditional` — the same asset's full-history
quantiles, **no macro bucket at all** — as its primary benchmark. The entire
claim of the conditional layer is that conditioning beats not conditioning. If
it does not beat that, the bucket machinery is decoration, and the plan is
explicitly to record it as decoration.

## 5. Score every arm on the same sample

WP-21.A.2 is the cautionary tale, and it is subtle enough to be worth internalising.

The first numeric baseline run keyed comparator calls off *price availability*,
so the comparators were scored on 78,656 calls while the models got 75,414. The
extra sample went to `always_bullish` — the benchmark the entire verdict turned
on. Nothing was obviously wrong; every number looked plausible.

The fix intersects the `(window, date, asset)` triples across arms and clamps
every arm to the shared set. It moved the benchmark by 0.003 and left both models
unchanged to three decimals — **the conclusion never depended on it** — which is
precisely why it had to be fixed rather than waved off. A comparison that is
accidentally right is not a comparison.

## 6. Overlap is not sample size

Daily notes at a 5-day horizon overlap ~80%; at 20 days, ~95%. Raw `n` in the
tens of thousands is not tens of thousands of independent observations.

Every significance statement here therefore comes from a **block bootstrap or
block permutation test over 21-day blocks**, and the block count is reported next
to every p-value. With a few months of data there are only a handful of
independent blocks, so `p` is indicative and the signal to trust is consistency
across assets and horizons.

`score_distributions.py` and `bias_separation.py` share the same `BLOCK_DAYS`
constant, asserted by a test, so two analyses of the same overlap cannot disagree
about what counts as independent.

## 7. Controls are tests, not one-off checks

Every harness carries two controls, and both live in the test suite rather than
in someone's memory of having run them once:

- A **positive control** — a planted signal the harness must detect. Without it,
  "no edge found" is indistinguishable from a dead pipeline.
- A **negative control** — a setting where the benchmark *is* the truth, in which
  the harness must report approximately zero skill.

A null from a harness that has never demonstrated it can find a planted signal
means nothing at all.

## 8. Point-in-time discipline, and the cheap route to it

The gold standard for backtesting revised macro data is ALFRED vintages. For a
decade of daily walk-forward that is roughly 40,000 HTTP calls, which is not
happening.

So the project takes the other road: **only never-revised inputs are eligible.**
Prices, and FRED's market-observed daily series. Today's vintage is therefore the
historical vintage by construction. Every series is shifted one business day so a
print is only readable the day after it lands, and both properties are enforced
by tests rather than by convention
([ADR-0014](../decisions/ADR-0014-point-in-time-without-alfred.md)).

Walk-forward fits embargo `horizon + 1` trading days: a prediction on `t` may
train only on rows whose forward window closed strictly before `t`.

The honest cost is stated rather than hidden — this excludes CPI, payrolls, M2,
WALCL, NFCI and claims from the baseline entirely. A null established this way is
a null about *the eligible panel*, and the write-ups say so.

## 9. A degraded run is a valid run — guard against it

The nastiest failure this project has recorded is [KB-025], and nothing crashed.

A CI expression silently dropped the exogenous arms from a pre-registered
measurement. The workflow was green. The run took 2h50m. It produced a complete,
well-formatted report. It simply did not test the thing it existed to test, and
the only tell was one line of metadata.

The lesson generalises past CI: **a pipeline that degrades gracefully will
degrade silently.** The fix was a `--require-exogenous` flag that exits non-zero
when the arms are missing, plus a documented pre-flight check printed in every
subsequent reproduce block:

```bash
# must print: 7 {}  — anything else and the run is a KB-025 repeat, not a result
```

Every reproduce recipe in the Knowledge Base since then names the metadata line
to check *before* reading a number.

## 10. A bar is not tested by the results that fail it

[KB-027] again, because it is the sharpest lesson here.

The pre-committed `verdict()` had a hole: `hit > 0.52 AND (BSS > 0 OR aligned)`.
An `inverted` ordering could only ever be consulted through the `aligned`
disjunct, so a positive BSS satisfied the clause and the ordering check was
skipped **in exactly the case it was written for**.

It survived three prior runs undetected because the hole was unreachable unless
an arm posted BSS > 0, and no arm ever had. The first arm to clear zero was the
first to expose it.

Which means: your gate is only exercised by results that reach it. Write tests
that drive each disqualifier independently. Phase 22's bar was built this way —
`underpowered` → `miscalibrated` → `inverted` are evaluated first, each returns
its own verdict, and a test asserts each fires ahead of a strong skill number.

## 11. Say what a result does *not* establish

Every Knowledge Base entry has a "what this establishes, and what it does not"
section, and it is not boilerplate.

[KB-027] closed the VIX term structure as a *directional* input. [KB-001] had
scored the same curve as a *stress* instrument at AUC 0.77/0.67, and that result
is untouched — the two live fragility flags depend on it and nothing in
`fragility.py` changed. Without the scope line, a reader six months later
reasonably concludes the curve was discredited and rips out a working component.

Similarly [KB-026] closed the SPF anchor as a directional input while explicitly
leaving the expectations-gap mechanism untested, because the SPF-vs-SEP gap was
excluded from the run as leakage. A null on the deterministic half is not a null
on the thesis.

## 12. Soft-kill: deactivate, never delete

When an arm stops earning its keep, the stage comes out of the pipeline and the
cron call is removed. The code, its tests, its emitted history and its
`workflow_dispatch` trigger all stay
([ADR-0015](../decisions/ADR-0015-soft-kill-convention.md)).

The Kimi ensemble arm and the exogenous weekly emitter are both in this state.
Restoring either is a one-line change to `pipeline.yml`. Deleting them would have
made the historical scores unreadable and the decision irreversible, for the sake
of tidiness.

Documentation follows the same rule. The 2026-09-04 pass moved 792 lines out of
the roadmap and deleted none of them — every block was replaced inline by a
summary keeping the verdict, the KB pointer, and anything a still-open sibling
work package depended on.

---

## The short version

1. Write the finding down, especially when it is negative.
2. Write the bar down before the run.
3. Seal the holdout, and be honest about when you sealed it.
4. Put a trivial rival next to the product.
5. Score every arm on the same sample.
6. Overlapping observations are not independent ones.
7. Controls are tests, not memories.
8. Only never-revised inputs, shifted a day, enforced by tests.
9. A green run is not a valid run — check the metadata line.
10. Your gate is untested until a result reaches it.
11. State what the result does not establish.
12. Deactivate; do not delete.

---

**Next:** [The cut](the-cut.md) — the method's largest bill, paid in full.
