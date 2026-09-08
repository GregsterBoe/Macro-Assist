# ADR-0009 — Cut the directional product (v1.6)

| | |
|---|---|
| **Status** | Accepted · shipped as v1.6, 2026-09-05 |
| **Decided** | 2026-09-04 (WP-21.D) |
| **Evidence** | [KB-007], [KB-022], [KB-023], **[KB-024]** |
| **Related** | [ADR-0010](ADR-0010-freeze-the-directional-scorer.md) · [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md) · [The cut](../concepts/the-cut.md) |

## Context

Three independent measurements said the directional call carried no information,
and [KB-024] said the task was not learnable from this payload by any model class
tested. A constant `always_bullish` beat both fitted models on hit-rate, Brier,
BSS and calibration error simultaneously.

The full narrative is [The cut](../concepts/the-cut.md).

## Decision

**Remove `Bias` and `Confidence %` from the note, and remove the fields from the
schema** so MA-1 is not asked for a directional call at all.

Remove with them:

- `_apply_accuracy_override_structured()` and its free-text twin — the four
  post-hoc checks that constituted the self-calibration feedback loop.
- The `confidence_delta` half of MA-2.
- Every prompt block gated by the run-profile levers.

Publish in their place what was already in the note, buried in the driver prose:
**the empirical conditional return distribution** (median, P25/P75, `n`) for the
current macro-state bucket, rendered by Python after the analysis. Promote the
**Fragility Monitor** to the headline risk read, with its precision ≈ 0.32 limit
attached inline.

## Consequences

The governing reasoning, quoted because it is the whole decision:

> Correcting the direction of a call that carries no information is not a smaller
> error, it is a more elaborate one.

That is why the feedback loop went too rather than being re-pointed.

- **Removed, not hidden.** Defaulting the fields or suppressing them in rendering
  would have left the model producing them and the corpus containing them.
- **WP-21.B.2 was cancelled** — a day-alternating A/B could only ever rank two
  prompt configs at a task with no learnable answer, and waiting for it meant
  months of publishing ~36%-accurate calls at ~63% stated confidence.
- **Downstream breakage was extensive and mostly foreseen**: the Kimi arm lost its
  purpose, the exogenous branch's gate became *unreadable* rather than failed, and
  the paper portfolio lost the input it sized from.
- **One consequence was not foreseen**, and it is the instructive one: the
  measurement apparatus stayed pointed at the deleted product, so for three days
  the pipeline published something no scorer measured. That gap is Phase 22.
- The run-profile levers still resolve and are still recorded in frontmatter, so
  the historical readers keep working — but they gate nothing.

## Would we revisit it?

Only through WP-21.E's capped, pre-registered search — three feature families, of
which family 1 has run and closed negative ([KB-027]). Families 2 and 3 are
deliberately blocked pending [ADR-0017](ADR-0017-bss-floor-left-open.md). The
honest prior is low and the roadmap says so.
