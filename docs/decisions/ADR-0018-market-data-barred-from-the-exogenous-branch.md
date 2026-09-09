# ADR-0018 — Market data is barred from the exogenous branch's core inputs

| | |
|---|---|
| **Status** | Accepted · branch soft-killed as a live arm |
| **Decided** | 2026-07-14 (Phase 19 target-lock, DESIGN §6.1) |
| **Evidence** | [KB-026] scores the deterministic half |
| **Related** | [ADR-0015](ADR-0015-soft-kill-convention.md) |

## Context

Phase 19's bet was a second prediction branch reasoning about **real-world
information** rather than prices, so that its output could be A/B'd against the
market-only pipeline as a genuinely independent arm.

The natural anchor for a rates-expectations branch is the market-implied path —
fed-funds and SOFR futures. Using it would have let the arm secretly re-derive
from prices and contaminate the very comparison it existed to make.

## Decision

**Bar market data as a core input.** It is a flagged optional comparator, never
part of the payload.

The anchor is instead two free, official, **non-market**, point-in-time consensus
sources:

- the **Philly Fed SPF** — economist consensus (TBOND, TBILL, UNEMP, CPI, RGDP);
- the Fed's own **SEP dot plot** — policymaker consensus (`FEDTARMD`).

The bet is two-layered: **(1)** the gap *between* them is itself a signal —
economists disagreeing with the Fed's own dots; and **(2)** both update only
quarterly, so between updates the anchor is fixed and the branch tracks **new FOMC
communication** drifting away from it. The drift is the tradeable gap.

So: *economists vs policymakers vs what the Fed is now saying* — institutions
against each other, with the market excluded on purpose.

## Consequences

- The A/B is uncontaminated, which is the whole reason the constraint exists.
- **The constraint is also what made the branch hard to score**, and the scoring
  is where it ran aground. Its gate was a head-to-head against the market-only
  LLM arm; v1.6 froze that comparator, so the gate became *unreadable* rather than
  failed. WP-19.E re-pointed it at the numeric benchmark instead, and the SPF
  anchor closed negative ([KB-026]).
- **[KB-026] does not close the thesis, and says so.** It scores the branch's
  deterministic, point-in-time half. The SPF-vs-SEP gap is excluded — FRED serves
  only the current vintage of the dots, so a walk-forward would read the Fed's
  later revisions — and so are the LLM extraction layers. **Both layers of the
  actual bet remain untested.**
- The branch is soft-killed as a live arm: stage removed from `pipeline.yml`,
  cron removed, code and `workflow_dispatch` intact.

## Would we revisit it?

The surviving route is **(b)**: publish the expectations gap itself rather than a
directional lean. DESIGN §1 always said the branch was about expectations-gaps and
regime, *not* direction — the directional lean was a scoring convenience, and
[KB-026] closed the convenience rather than the thesis.

That needs a scoring protocol which is not direction, and none exists. **Building
one is a decision, not a continuation**; the alternative is DESIGN §9's hard-kill,
which is fully documented and cheap.
