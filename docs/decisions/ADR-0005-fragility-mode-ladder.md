# ADR-0005 — Fragility ships behind a mode ladder, never straight to live

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | Phase 16 (WP-16.A) |
| **Evidence** | [KB-001], [KB-002] |
| **Related** | [ADR-0006](ADR-0006-or-mode-not-weight.md) |

## Context

The fragility index was the first component built with a look-ahead-safe,
de-overlapped backtest *before* anyone trusted it. That earned it a place, but a
backtest is not a live record, and a tail-risk gauge that has never fired in
production has not been observed doing anything.

## Decision

Ship it behind an explicit escalation ladder rather than an on/off switch:

| Mode | Behaviour |
|---|---|
| `log` (default) | Computed and recorded; **never enters the prompt** |
| `show` | Rendered into the prompt and the note |
| `active` | Allowed to affect output — e.g. widen Target Ranges |

`FRAGILITY_MODE` governs the composite; `FRAGILITY_OR_MODE` governs the
OR-of-channels flag independently.

At `log`, the reading still surfaces three ways so a shadow run is not invisible:
the full raw reading in `results/quant_context_log/`, a `[FRAGILITY]` one-liner
in the run log with a `WARN` when Elevated, and a table appended to the note's
Data Snapshot *after* the LLM call — visible to the operator, not to the model.

## Consequences

- Escalation is a deliberate act with a stated gate, not a drift.
- Current state: the **OR flag is at `show`** (promoted 2026-09-04 with v1.6,
  once the loosened A/B that confounded it closed); the **composite clock is
  still at `log`**, waiting on exactly one thing — a live `Elevated` episode.
- Two ladders means two states to remember. The board tracks both separately.

## Would we revisit it?

The pattern generalises well enough that it is the default shape for any future
signal. The open question is what evidence justifies `active`, and it is
deliberately unanswered: `active` would let the flag widen published ranges, and
there is still no live forward record.
