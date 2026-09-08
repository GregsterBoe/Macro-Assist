# ADR-0019 — The paper portfolio is mechanical and paper-only in v1

| | |
|---|---|
| **Status** | Accepted · stalled, input withdrawn |
| **Decided** | 2026-08-19 (Phase 20 scope-lock) |
| **Related** | [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0015](ADR-0015-soft-kill-convention.md) |

## Context

Phase 20 exists to answer one question — *does the signal have edge?* — with an
**unfakeable** scoreboard. Accuracy metrics can be argued with; a NAV curve
against a benchmark cannot.

The temptation with an LLM in the loop is to let it allocate.

## Decision

Three constraints, locked before any code:

1. **Mechanical sizing only.** Zero discretionary LLM trading. Loosening belongs
   to the Phase 16 track, not here.
2. **Paper / forward-test only.** No broker. Simulated fills on yfinance closes.
   Real-broker integration is WP-20.E and is gated on v1 showing edge.
3. **One primary success bar:** information ratio of excess return vs a
   buy-and-hold benchmark of the same universe, measured **forward**, with max
   drawdown as a risk guard. Everything else — per-arm comparison, turnover,
   hit-rate, the decision log — is diagnostic context.

Explicitly **not** the target for v1: a leveraged directional index bet, a tuned
backtest equity curve, discretionary allocation, or real-money execution.

Modular and removable — the prediction pipeline is never touched.

## Consequences

- The scoreboard cannot be gamed by narrative, which was the point.
- Testability was designed in: the risky logic (note parsing, instrument mapping,
  signal assembly, benchmark weighting) is pure and injected with prices, fully
  offline-tested; the network and model bits are lazy-imported and isolated.
- **It stalled, and not for its own reasons.** The sizer's input was `bias` and
  `confidence_pct`, which v1.6 removed. `rebalance.run()` now detects a post-cut
  note and **declines to advance the book with a message saying why** — rather
  than silently stopping, which would look identical to a broken cron.
- It is left running deliberately, so the withdrawn input stays visible weekly.

## Would we revisit it?

Re-pointing the sizer at the conditional distribution is a plausible v2 and would
need its own pre-registered test. It is not a port — sizing from a distribution is
a different rule than sizing from a label and a confidence number.
