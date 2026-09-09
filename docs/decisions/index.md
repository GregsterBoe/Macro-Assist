# Decisions

One page per load-bearing choice: what the situation was, what was decided, what
it cost, and whether it still holds.

This exists so a design choice can be **revisited without being re-derived**.
Before arguing for a change, read the relevant page — it will point you at the
two or three Knowledge Base entries that matter instead of all 26.

## How to read a decision page

| Status | Means |
|---|---|
| **Accepted** | In force. Change it deliberately, not incidentally |
| **Open** | Consciously undecided. The page says what needs deciding and by when |
| **Superseded** | Replaced. The page stays, and names its replacement |

A decision page is **not** a source of truth for how the code behaves today —
that is [Reference](../reference/index.md) — and not a source of truth for a
measurement — that is the [Knowledge Base](../record/knowledge-base.md). It is a
source of truth for *why*.

## The record

### Architecture and pipeline shape

| | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-output-on-an-orphan-branch.md) | Generated output lives on an orphan `output` branch | Accepted |
| [ADR-0002](ADR-0002-structured-output-contract.md) | MA-1 returns a validated object through `tool_use`, not prose | Accepted |
| [ADR-0003](ADR-0003-four-narrow-agents.md) | Four narrow agents rather than one wide call | Accepted |
| [ADR-0012](ADR-0012-external-cron-with-backstop.md) | External cron triggers the pipeline; GitHub's scheduler is a backstop | Accepted |
| [ADR-0013](ADR-0013-one-pipeline-entry-point.md) | One entry point, `needs:`-ordered, with one resolved `asof` | Accepted |

### What the system publishes

| | Decision | Status |
|---|---|---|
| [ADR-0009](ADR-0009-cut-the-directional-product.md) | **Cut the directional product (v1.6)** | Accepted |
| [ADR-0004](ADR-0004-retire-hmm-from-the-note.md) | Retire the HMM regime layer from the note, keep the code | Accepted |
| [ADR-0005](ADR-0005-fragility-mode-ladder.md) | Fragility ships behind a mode ladder, never straight to live | Accepted |
| [ADR-0006](ADR-0006-or-mode-not-weight.md) | Adopt the cross-section as an OR *mode*, not a blended weight | Accepted |
| [ADR-0011](ADR-0011-canonical-asset-registry.md) | One canonical asset registry; stored numbers are display units | Accepted |

### How things get measured

| | Decision | Status |
|---|---|---|
| [ADR-0007](ADR-0007-measure-the-task-not-the-model.md) | Build an instrument that measures the *task*, not the model | Accepted |
| [ADR-0008](ADR-0008-no-neural-network.md) | No neural network | Accepted |
| [ADR-0014](ADR-0014-point-in-time-without-alfred.md) | Point-in-time without ALFRED: only never-revised inputs are eligible | Accepted |
| [ADR-0010](ADR-0010-freeze-the-directional-scorer.md) | Freeze `score_predictions.py` rather than refactor or delete it | Accepted |
| [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md) | Phase 22 scores the conditional distribution only | Accepted |
| [ADR-0017](ADR-0017-bss-floor-left-open.md) | `EDGE_MIN_BSS` stays at 0.0 — the floor is an open decision | **Open** |

### Experiment tracks

| | Decision | Status |
|---|---|---|
| [ADR-0018](ADR-0018-market-data-barred-from-the-exogenous-branch.md) | Market data is barred from the exogenous branch's core inputs | Accepted |
| [ADR-0019](ADR-0019-paper-portfolio-mechanical-and-paper-only.md) | The paper portfolio is mechanical and paper-only in v1 | Accepted |
| [ADR-0015](ADR-0015-soft-kill-convention.md) | Soft-kill: deactivate, never delete | Accepted |

## Decisions that are still open

These are consciously undecided and are tracked in
[todo.md](../record/todo.md) rather than here, except where one blocks work:

- **[ADR-0017](ADR-0017-bss-floor-left-open.md) — the BSS floor.** Blocking
  WP-21.E families 2 and 3. Must be written down *before* family 2 runs.
- **Open decision #7 — Target Range coverage.** Needs a pre-registered nominal
  and a path-vs-endpoint call. It is the last LLM-authored falsifiable claim in
  the note and it is unscored.
- **Open decision #8 — should the note publish a wider interval?** P25/P75 means
  half of all outcomes land outside the band the reader sees. The table already
  holds p10/p90. A product decision with a cost: it would restart the sealed
  interval clock.

## Adding a decision

Copy the shape of any existing page. The parts that matter:

1. **Context** — the situation, with the measurements that created it. If there
   were none, say so.
2. **Decision** — what was chosen, stated so a reader can tell whether a proposed
   change violates it.
3. **Consequences** — including the costs. A page with no costs listed has not
   been thought through.
4. **Would we revisit it?** — the conditions under which this should be reopened.

Number sequentially. Never renumber. Never delete — supersede, and link both ways.
