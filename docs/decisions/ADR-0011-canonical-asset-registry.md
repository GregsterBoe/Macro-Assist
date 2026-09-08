# ADR-0011 — One canonical asset registry; stored numbers are display units

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-08 (WP-22.A) |
| **Evidence** | The `^TNX` percent-of-a-percent bug, ~13× threshold inflation |
| **Related** | [ADR-0010](ADR-0010-freeze-the-directional-scorer.md) · [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md) |

## Context

The note published "— no conditional base rate" for the 10Y, DXY and Bitcoin, and
the prose called it "thin-data terrain". **That was not true.** `refit_models._ASSETS`
simply had three tickers in it. The gap was build-side, and the note was
explaining a limitation that did not exist.

Fixing it meant adding the 10Y, which surfaced the real problem. `^TNX` quotes the
10Y as a **yield level** in percent — 4.77 means 4.77%. A percent return over a
level like that is a percent-of-a-percent: it inflates the denominator and makes
any threshold roughly **13× too large**. That bug already had a home-grown fix in
`score_predictions.ABSOLUTE_DIFF_ASSETS`, written for the directional scorer only.

Adding the 10Y to the distribution product meant the build side, the render side
and the new scorer would each need the same correction, computed the same way.
Three hand-maintained asset lists were about to become three places to get a unit
conversion wrong.

## Decision

Create `.macro-assist/assets.py` as the single source of truth for four things:
the **key** used in the distribution table and quant log, the **ticker**, the
**note name**, and the **return convention**.

`assets.forward_change()` is defined once and imported by `refit_models` (build),
`quant_context` (render) and `score_distributions` (score).

**Stored numbers are in display units**, named by `Asset.unit`:

| Convention | Meaning |
|---|---|
| `pct` | percent return — `1.21` is +1.21% |
| `level` | **basis points** of level change — `6.0` is +6bp |

`format_change()` is the matching renderer, so a 6bp yield move can no longer
print as "+6.0%".

## Consequences

- The asset universe went **3 → 6**.
- "What does this stored number mean" is answered by the registry, never by the
  call site.
- The three original keys (`SP500`, `Gold`, `WTI Oil`) are **unchanged and must
  not be renamed** — the persisted table, every `quant_context_log` JSONL written
  since 2026-05-29, and the entire forward record key off those strings.
- The three new assets carry no forward record until a weekly refit rebuilds the
  table with them, so their record starts ~5 months after the original three.
  `dist_scores_summary.json` reports `record_start_by_asset` rather than pooling.
- `score_predictions.py` is deliberately **not** migrated onto the registry —
  see [ADR-0010](ADR-0010-freeze-the-directional-scorer.md).

## Would we revisit it?

No. The general lesson is worth keeping: **a unit convention that appears in more
than one module is a defect waiting for its third call site.**
