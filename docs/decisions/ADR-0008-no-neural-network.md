# ADR-0008 — No neural network

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-03, recorded explicitly so it is not re-litigated |
| **Evidence** | [KB-009] (~3 orthogonal factors), sample-size arithmetic |
| **Related** | [ADR-0007](ADR-0007-measure-the-task-not-the-model.md) |

## Context

The natural objection to any negative result from a ridge and a shallow GBM is
"you did not try a big enough model". It gets raised every time, so the reasoning
was written down once.

## Decision

The numeric baseline uses exactly two model classes, both small and both
regularised:

- **`ridge`** — standardised L2 logistic regression, with the scaler inside the
  pipeline so it is fitted on the training fold only.
- **`gbm`** — depth-2, 150 trees. Depth 2 allows pairwise interactions and
  nothing deeper.

No neural network, at any point.

## Consequences

The justification is sample arithmetic, not taste. There are roughly **150
independent 20-day windows** across roughly **three orthogonal factors**
([KB-009]). That does not support a model with more capacity; it supports a model
with less. A network on this panel would fit noise and the result would be
uninterpretable either way.

The negative result is therefore correctly scoped, and the scoping is stated
every time it is cited: **direction is not learnable from this payload by any
model class tested**, on these assets, at these horizons. It is not a claim about
what a larger model on a larger panel could do.

The corroboration is that the LLM — an enormous model — fails the same way, with
the same inversion, on the same data ([KB-024]). Two very different capacity
regimes producing the same contrarian pathology is evidence about the panel, not
about model size.

## Would we revisit it?

Only alongside a materially larger and genuinely independent sample. Adding
capacity to this panel is not a experiment, it is a way of getting a different
random number.
