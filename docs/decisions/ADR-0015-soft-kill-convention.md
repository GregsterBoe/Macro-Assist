# ADR-0015 — Soft-kill: deactivate, never delete

| | |
|---|---|
| **Status** | Accepted · standing convention |
| **Decided** | Formalised in the Phase 19 and Phase 20 design docs; applied broadly 2026-09-04 (WP-21.F) |
| **Related** | [ADR-0004](ADR-0004-retire-hmm-from-the-note.md) · [ADR-0010](ADR-0010-freeze-the-directional-scorer.md) |

## Context

Several components have outlived their purpose: the HMM regime layer, the Kimi
ensemble arm, the exogenous weekly emitter, the run-profile A/B. The tidy instinct
is to delete them.

Deleting them makes their emitted history unreadable, destroys the ability to
reproduce the findings built on them, and makes the decision irreversible — for
the sake of a shorter file listing.

## Decision

When an arm stops earning its keep: **remove the stage from `pipeline.yml` and
remove its cron call. Keep everything else.** The module, its tests, its emitted
notes, its scored history and its `workflow_dispatch` trigger all stay.

Restoring an arm is a one-line change to `pipeline.yml`.

Currently soft-killed:

| Component | Deactivated | Why |
|---|---|---|
| Kimi ensemble arm | 2026-09-04 | It calibrated a `confidence_pct` that v1.6 removed |
| Exogenous weekly emit | 2026-09-04 | Its comparator was frozen by the cut; gate unreadable |
| HMM regime block | Phase 17 | Beaten by a four-feature rule ([KB-006]) |
| Run-profile levers | 2026-09-04 | Inert — every block they gated was a directional rule |

The Phase 19 and Phase 20 design docs each additionally document a **hard-kill
procedure**, so full removal remains available as a deliberate, specified act
rather than a cleanup impulse.

## Consequences

- `calibration_by_arm` still reads the Kimi history.
- Anyone reading the codebase will find substantial machinery that does not run.
  Every instance is marked where it appears, and
  [Reference](../reference/index.md) leads with the warning.
- The tradeoff is accepted deliberately: a slightly confusing repository is
  cheaper than an irreversible deletion.

## Documentation follows the same rule

The 2026-09-04 archive pass moved 792 lines out of the roadmap and **deleted
none of them**. Each block was replaced inline by a summary keeping the verdict,
the KB pointer, and anything a still-open sibling work package depended on.

The governing rule: **never trim a work package before its result is in the
Knowledge Base.** Losing the plan is fine once the finding is recorded; losing
both is how a project forgets what it already tried.
