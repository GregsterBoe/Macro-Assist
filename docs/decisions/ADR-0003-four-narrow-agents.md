# ADR-0003 — Four narrow agents rather than one wide call

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-05-25 / 2026-05-26 (Phases MA-2, MA-3) |
| **Evidence** | Observed rubber-stamping in the single-call design |
| **Related** | [ADR-0002](ADR-0002-structured-output-contract.md) |

## Context

One agent asked to analyse, self-critique, assess a portfolio and format markdown
does all four badly. The self-critique failure is the specific one: an agent shown
the reasoning that produced a claim will endorse the claim.

## Decision

Split into four calls with deliberately asymmetric context:

| Agent | Model | Sees | Produces |
|---|---|---|---|
| MA-1 | Sonnet | the full payload | structured `AnalysisOutput` |
| MA-2 | Sonnet | **only** outlook rows + key risks | a JSON delta of added risks |
| MA-3a | Haiku | **only** regime label + positions | structured portfolio risk read |
| MA-3b | Haiku | the structured JSON | the final markdown body |

Python applies MA-2's delta programmatically. Numbers in Primary Driver are never
touched by a model, which eliminates autoregressive drift.

## Consequences

- The adversarial pass is starved of context on purpose, and that is the point.
- Cost is controlled by routing the two mechanical jobs to Haiku.
- Four calls is four failure modes; each has its own retry and fallback.
- MA-3b's "copy the pre-formatted table verbatim" instruction became far more
  load-bearing after v1.6, because the table now contains measured data rather
  than opinions.

## Would we revisit it?

The MA-2 `confidence_delta` half was removed with the cut. The remaining split is
sound.
