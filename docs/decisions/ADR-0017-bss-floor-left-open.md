# ADR-0017 — `EDGE_MIN_BSS` stays at 0.0; the floor is an open decision, not a fix

| | |
|---|---|
| **Status** | **Open** — blocking WP-21.E families 2 and 3 |
| **Decided** | 2026-09-08 — decided *not* to decide it yet, deliberately |
| **Evidence** | **[KB-027]** |
| **Related** | [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md) · [The method](../concepts/the-method.md) |

## Context

WP-21.E family 1 (VIX term structure) produced the first arm in this project to
clear a BSS of zero: **+0.003**. That was enough to satisfy the pass clause's
disjunct and the pre-committed `verdict()` returned **`edge`** for an arm its own
pre-registration had disqualified as inverted.

Two things were wrong, and only one of them was fixable without cheating.

## Decision

**Fixed:** an `inverted` separation ordering now disqualifies outright, before the
pass clause, returning `inverted` as its own verdict. This is a correction, not a
goalpost move — the pre-registration, committed before the run, had already named
an inversion as outcome 3 and said explicitly that it "is **not** a pass and must
not be re-labelled a contrarian signal after the fact." The implemented function
and the registered read disagreed, and the function was the looser one.

**Deliberately not fixed:** `EDGE_MIN_BSS` stays at **0.0**.

A floor of literally zero is obviously not a skill threshold. +0.003 over the base
rate on 15,215 heavily overlapping calls (2,261 dates × 6 assets × 3 horizons) is
not distinguishable from zero, and the block-bootstrap CIs are wide enough to say
so. But raising it *after* seeing a result it would have changed is a real
goalpost move — the pre-registration says nothing about a margin — so it is
recorded as open rather than edited in quietly, and pinned by
`test_the_bss_margin_was_deliberately_left_alone`.

## Consequences

- **WP-21.E families 2 and 3 are blocked on this**, deliberately. Deciding it
  *now*, with no candidate family on the table, is the only moment it can be
  decided honestly. Deciding it after the next family runs reopens the same
  argument with a result already sitting on the table.
- The published report on `origin/output` still shows the pre-correction `edge`.
  [KB-027] carries both columns.
- Applying the correction relabels `ridge`/`gbm`/`market_plus_vixterm` from
  `no edge` to `inverted`, which is more informative and consistent with [KB-024]:
  across [KB-022], [KB-024] and [KB-027] a wrong-signed relationship is the single
  most repeated finding in this project, and "did nothing" and "did something
  backwards" should not print the same word.
- Phase 22 answered the equivalent question *in advance* for the distribution
  product — `MIN_SKILL = 0.02`, set before any data existed. That is the shape the
  answer here should take.

## What needs deciding

Either a **margin** on BSS, or a **comparator-relative clause** — "must beat the
best comparator on Brier", which is arguably the more principled bar given that
every negative so far has been a loss to a trivial rival.

It must be written down **before family 2 runs**.
