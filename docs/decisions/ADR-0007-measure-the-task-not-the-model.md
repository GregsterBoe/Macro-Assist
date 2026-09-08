# ADR-0007 — Build an instrument that measures the *task*, not the model

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09 (WP-21.A) |
| **Evidence** | [KB-007], [KB-011], [KB-022], [KB-023] motivated it; **[KB-024]** is its first output |
| **Related** | [ADR-0008](ADR-0008-no-neural-network.md) · [ADR-0014](ADR-0014-point-in-time-without-alfred.md) · [ADR-0009](ADR-0009-cut-the-directional-product.md) |

## Context

By August 2026 the project had four independent measurements of the directional
product, and they all had the same blind spot: **they measured the LLM.**

- [KB-007] — decisive calls resolve at ~36%, BSS −0.195.
- [KB-011] — the loosened arm commits less and bleeds less.
- [KB-022] — the bias label separates forward returns, ordered backwards.
- [KB-023] — the apparent repair is confounded; arm and period are the same
  partition of the data.

None could distinguish *this model is bad at the task* from *this task is not
doable from this payload*. Every proposed next step — a better prompt, a
different model, an ensemble, calibrated confidence — implicitly assumed the
first, and each would have cost months.

## Decision

Build `numeric_baseline.py`: fit deliberately small, regularised numeric models
walk-forward on the inputs the pipeline already collects, and ask whether
*anything* can predict 5/10/20-day direction on these assets.

Design constraints, all of them non-negotiable and all enforced by tests:

- **Only never-revised inputs** ([ADR-0014](ADR-0014-point-in-time-without-alfred.md)),
  each shifted one business day.
- **Walk-forward with a `horizon + 1` embargo.**
- **Scored by the production readers** — `score_predictions.score_call`,
  `summarize_accuracy._brier_and_reliability`, `bias_separation.bias_separation` —
  so a numeric arm and the LLM arm face one yardstick.
- **A planted-signal positive control**, so "no edge" cannot be a dead pipeline.
- **A bar committed before the run.**
- Output to `results/numeric_baseline/`, deliberately **not** `results/scores/`,
  which would contaminate the live accuracy corpus.

## Consequences

- It answered the question in one run, negatively and decisively, and the product
  was cut three days later.
- Each model and comparator is emitted as its own `arm`, which makes the
  comparison a `calibration_by_arm` table for free — and made the harness
  immediately reusable for [KB-026] and [KB-027] without modification.
- It is the most expensive thing in the repo to run (~2–3 hours in CI, ~75k model
  fits), so it is manual-dispatch only and costs zero LLM spend.

## Would we revisit it?

This is arguably the best decision in the project. The generalisation — *before
improving a model at a task, establish the task is learnable* — is now standing
method.
