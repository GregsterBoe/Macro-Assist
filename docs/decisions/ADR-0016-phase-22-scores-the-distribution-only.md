# ADR-0016 — Phase 22 scores the conditional distribution only

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-08 |
| **Evidence** | [KB-024], [KB-026], [KB-027] motivate the benchmark choice |
| **Related** | [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0017](ADR-0017-bss-floor-left-open.md) |

## Context

After the cut, the note carries **four** falsifiable things: the conditional
distribution, the LLM's Target Range, the Fragility Monitor, and (logged,
unpublished) the HAR-RV vol forecast. None of them had a scorer.

## Decision

Score **the conditional distribution only**. Name the other three explicitly as
out of scope, so the omission is a decision rather than an oversight.

| Excluded | Why |
|---|---|
| **Target Range** | Needs a pre-registered nominal coverage and a path-vs-endpoint call it does not have. The prompt says "where the asset can reasonably trade", which is the *path*, not the T+5 close — scoring the close would measure a different quantity and report far higher coverage than the claim earns. Tracked as open decision #7 |
| **Fragility forward record** | That is IMP-4's clock, not this one |
| **HAR-RV vol forecast** | That is WP-17.5 |

The benchmark is `unconditional` — the same asset's full-history quantiles, **no
macro bucket at all** — plus `trailing_250` and `har_gaussian`.

## Consequences

- **The benchmark is the test, not a formality.** [KB-024], [KB-026] and [KB-027]
  each found a product that scored as skilled until a trivial rival was put next
  to it. The entire claim of the conditional layer is that conditioning on
  `NFCI|YC|HY` beats not conditioning. If it does not beat this, the bucket
  machinery is decoration, and the plan is to record it as decoration.
- **The bar was sealed at the only honest moment.** P25/P75 entered the quant log
  on 2026-09-07; the bar was written 2026-09-08, when the interval record had
  **zero** resolved observations. `MIN_SKILL = 0.02` (deliberately not zero — this
  settles in advance the question [ADR-0017](ADR-0017-bss-floor-left-open.md)
  leaves open) and `MIN_BLOCKS = 8` put the earliest read at ~2027-05.
- **The exploratory half is fenced in code.** The median-only backfill
  (2026-05-29 → 2026-08-28) was seen before the bar was written, so
  `verdict(sealed=False)` can only ever return `exploratory`. It shows skill vs
  unconditional of −0.009 at t5 and −0.065 at t20 across 3–4 blocks — no edge, and
  nowhere near the power to claim one either way.
- **[KB-027]'s defect was designed out.** Disqualifiers (`underpowered` →
  `miscalibrated` → `inverted`) are evaluated first, each returning its own
  verdict, with a test asserting each fires ahead of a strong skill number.
- **This is not a new experiment.** It is the feedback loop catching up with the
  note — the gap [ADR-0009](ADR-0009-cut-the-directional-product.md) opened.

## Would we revisit it?

Target Range is the obvious next candidate, and it is blocked on a product
decision rather than on engineering. See open decisions #7 and #8 in
[todo.md](../record/todo.md).
