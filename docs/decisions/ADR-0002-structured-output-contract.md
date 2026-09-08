# ADR-0002 — MA-1 returns a validated object through `tool_use`, not prose

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-05-24 (Phase MA-1) |
| **Evidence** | Phase MA-0 bug fixes — time-travel, leakage, self-contradiction |
| **Related** | [ADR-0003](ADR-0003-four-narrow-agents.md) · [Analysis pipeline](../reference/analysis-pipeline.md) |

## Context

The pre-v1.0 pipeline made a single free-text call and asked the model to produce
a correctly structured note. It produced section drift, contradictions between
sections, and occasional invented numbers. Phase MA-0 fixed three such bugs
individually before it became clear the shape of the call was the problem.

## Decision

MA-1 uses Anthropic tool use (`submit_analysis`) to return a validated Pydantic
`AnalysisOutput` (`schemas.py`). **Section structure lives in the schema, not in
the model's output stream.**

A free-text Sonnet call remains as a fallback after two failed structured
attempts, preserving pre-v1.0 behaviour rather than failing the day's note.

## Consequences

- Section order and constraints cannot be silently violated, because they are
  never something the model has to remember.
- Downstream code consumes typed fields instead of parsing markdown, which is
  what later made it possible to *remove* fields (`bias`, `confidence_pct`) as a
  schema change rather than a prompt negotiation — see
  [ADR-0009](ADR-0009-cut-the-directional-product.md).
- The schema is now a load-bearing interface. Changing it changes what is
  scoreable, so schema edits are version bumps.

## Would we revisit it?

No. This decision is what made the v1.6 cut a clean deletion rather than an
argument with a prompt.
