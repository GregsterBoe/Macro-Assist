# ADR-0014 — Point-in-time discipline without ALFRED: only never-revised inputs are eligible

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09 (WP-21.A) |
| **Evidence** | Enforced by tests; scoping stated in [KB-024], [KB-026], [KB-027] |
| **Related** | [ADR-0007](ADR-0007-measure-the-task-not-the-model.md) |

## Context

Backtesting on revised macro data with today's vintage manufactures skill out of
nothing: the model reads a number that was not knowable at the time. The correct
fix is ALFRED vintages — and for a decade of daily walk-forward that is roughly
**40,000 HTTP calls**, which is not happening for a free-tier research project.

## Decision

Take the other route: **restrict eligibility instead of reconstructing history.**

Only inputs that are *never revised* may enter the numeric harness:

- yfinance prices.
- FRED's market-observed daily series — `DGS10`, `DGS2`, `BAA10Y`, `T10YIE`,
  `DFII10`, `VIXCLS`.

Today's vintage is therefore the historical vintage, by construction. Every series
is shifted one business day so a print is only readable the day *after* it lands.
Revised or lagged-release macro — CPI, payrolls, M2, WALCL, NFCI, claims — is
excluded by construction.

Walk-forward fits embargo `horizon + 1` trading days: a prediction on `t` may
train only on rows whose forward window closed strictly before `t`.

**Both guarantees are enforced by tests, not by convention.**

## Consequences

- Look-ahead safety is a property of the input set rather than a per-run
  discipline that can be forgotten.
- **The cost is real and is stated every time a result is cited**: a null
  established this way is a null about *the eligible panel*. It does not
  establish anything about a panel containing revised macro series.
- The daily *note* is unaffected — it uses the full FRED set, because it is
  describing today rather than backtesting.
- `point_in_time.py` still does full ALFRED reconstruction where the call volume
  is bounded (the paper portfolio's regime gate). The two approaches coexist by
  call budget.

## Would we revisit it?

Only with a cached vintage store. Until then the restriction is the honest option,
and the honesty is in stating what it excludes.
