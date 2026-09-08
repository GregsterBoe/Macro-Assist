# ADR-0010 — Freeze `score_predictions.py` rather than refactor or delete it

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-04 (WP-21.D), reaffirmed 2026-09-08 (WP-22.A) |
| **Evidence** | Reproducibility of [KB-007], [KB-011], [KB-022] |
| **Related** | [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0011](ADR-0011-canonical-asset-registry.md) · [ADR-0015](ADR-0015-soft-kill-convention.md) |

## Context

After the cut, `score_predictions.py` scores a product that no longer exists. Two
obvious moves — delete it, or refactor it onto the new asset registry — were both
rejected.

## Decision

**Freeze it.** It gates on pipeline version via `versions.has_directional_calls`
and returns `None` for every v1.6+ note. It is not refactored onto `assets.py`
(WP-22.A explicitly carves it out). It keeps running weekly until its last window
resolves.

## Consequences

- **The reason is reproducibility.** [KB-007], [KB-011] and [KB-022] are built on
  the corpus this module produced. A refactor that changed a flat threshold or a
  return convention would silently change three published findings.
- **The gate is by version, not by table shape**, so a stray legacy-shaped table
  cannot silently re-open the record.
- **The record is finite and dated.** The last directional note is 2026-09-04 and
  its T+20 window resolves ~2026-10-02.
- **Retirement is a defined event, not a judgement call.** Each run reports how
  many reports still have an open window and prints a `DIRECTIONAL RECORD CLOSED`
  banner once none do. That banner is the signal to delete the *step* — and only
  the step. Stage 3 of `pipeline.yml` is now permanent because
  `score_distributions.py` runs there.
- Without the banner the cron would print "0 score file(s) written" forever, which
  reads exactly like a silent breakage.
- The readers stay regardless: `summarize_accuracy.py` and `bias_separation.py`
  read the history, and that history is the evidence base.

## Would we revisit it?

No. This is the correct handling of an instrument whose output is cited.
