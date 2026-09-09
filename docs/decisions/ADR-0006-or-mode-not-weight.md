# ADR-0006 — Adopt the cross-section as an OR *mode*, not a blended weight

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | IMP-1.6 → IMP-4 |
| **Evidence** | [KB-015], **[KB-016]**, [KB-017], [KB-020], [KB-021] |
| **Related** | [ADR-0005](ADR-0005-fragility-mode-ladder.md) |

## Context

The IMP-1 arc established that absorption and turbulence are **orthogonal** to
the fragility composite ([KB-015]) and that OR-ing the three channels roughly
doubles crisis recall — 0.33 → 0.72 at 5 days ([KB-016]).

The obvious way to adopt a second and third signal is to fold them into the
composite as additional weighted terms. That was tested.

## Decision

Adopt it as an **OR of independent channels**, each against its own point-in-time
top decile. Do **not** blend the channels into a weighted composite.

## Consequences

- The measured reason: an equal-weight blend **degrades** the validated flag
  ([KB-016]). Averaging orthogonal channels cancels exactly the independence that
  produced the recall gain.
- The trade is explicit and accepted: precision falls 0.43 → 0.32. For a
  tail-risk gauge that is a good trade, and the note carries the number inline so
  a reader knows most firings are false alarms.
- Validated end to end: honest cross-validation with negligible leakage
  ([KB-017]), reproduced on the live daily sector-ETF feed ([KB-020]), and
  reproduced by the live code path at the same operating point ([KB-021]).
- Two channels were subsequently tested for admission to the OR set and
  **rejected**: credit is redundant at the live operating point ([KB-019]) and
  downside asymmetry does not sharpen the variance-trend channel ([KB-018]).

## Would we revisit it?

Only for a channel that demonstrates orthogonality first. The precedent from
[KB-019] is that standalone skill is not sufficient — a channel must add *recall
at held precision* in the live PIT operating point, or it is decoration.
