# ADR-0021 — Product and research are separated by an import boundary, enforced by test

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-14 |
| **Related** | [ADR-0005](ADR-0005-fragility-mode-ladder.md) (the door into the product) · [ADR-0015](ADR-0015-soft-kill-convention.md) (the door out) · [ADR-0007](ADR-0007-measure-the-task-not-the-model.md) |

## Context

By September 2026 `.macro-assist/` held ~20,000 lines in one flat directory,
of which roughly half runs in the daily pipeline and half is harnesses that
measure it. Nothing in the layout said which was which. Three consequences
had already been paid for:

- **A user could not be told what was "ready".** The note, the scorer, the
  paper portfolio and a dozen backtests shared one namespace, one test suite
  and one version number; "the product" was whatever `pipeline.yml` happened
  to call.
- **The live path depended on research code.** `fragility_or.py` — the
  component that puts the OR flag in every note — imports its data feeds and
  its history walk from `fragility_backtest.py`, the harness that first needed
  them. A refactor of the backtest could break the note, and nothing would say
  so until the next morning's run.
- **Research could not move freely.** The same coupling, from the other side:
  changing a harness meant re-verifying the live path.

The exploration tier drafted the day before (Phase 23, [How we explore](../concepts/how-we-explore.md))
made the third cost about to grow: it proposes a shadow-conditioner harness
that joins `conditional`, `fragility_or` and `score_distributions` — three
product modules — and without a boundary rule that harness would be the next
thing the product quietly imports.

## Decision

Every module under `.macro-assist/` belongs to exactly one of four tiers,
declared once in `product_surface.py`: **product** (runs in `pipeline.yml`,
or imported by something that does), **dormant** (soft-killed product),
**research** (harnesses and backtests), **tooling**.

**Product code never imports research code.** Research imports product
code freely — it measures it.

The rule is enforced by `tests/test_product_boundary.py`, a static import
scan (no module is imported, so no network). It fails on:

- any new product → research edge;
- any module not assigned to a tier;
- any pinned leak that has been fixed without its pin being removed.

A known violation goes in `KNOWN_LEAKS` with a todo number rather than being
tolerated in silence — the ADR-0017 pattern — and the test holds the set
exactly in *both* directions, so a pin cannot outlive its leak. On the day
the rule was written the set held two edges (`fragility_or` and
`quant_context`, both → `fragility_backtest`, both for data-feed functions);
they were drained the same day into `fragility_panel.py` and the set is empty
([resolved #20](../record/resolved.md)).

Two things this decision deliberately does **not** do:

- **It does not move files.** A `product/` vs `research/` directory split
  would touch every import, every workflow and every test for a benefit the
  boundary test already delivers. It can follow once the leaks are drained;
  the manifest makes the move mechanical when it comes.
- **It does not split the scorer.** `score_distributions.py` is product — it
  publishes the weekly scorecard a user reads. The *read* of its verdict
  against a bar is research. That boundary is between two acts on one file,
  and the [Research](../research/index.md) page states it rather than
  duplicating the module.

## Consequences

- There is a page that says what is ready — [Product](../product/index.md) —
  and its module table is checked against the manifest by the test's
  completeness assertion, so it cannot drift silently.
- The research tier has a stated ladder — exploration → confirmation →
  accepted → product — with the existing mechanisms (`verdict(sealed=False)`,
  the class bar, the KB, the mode ladder) as its rungs. Nothing new runs.
- Adding a module now requires classifying it. That is one line and it is
  the point.
- **Cost:** draining the two initial leaks touched the live fragility path.
  It was verified by running `fragility_or.py`'s self-check on the moved and
  the pre-move code on the same data — identical, and equal to the reference
  row [KB-031] recorded — not by the boundary test alone. Any future drain is
  held to the same standard.
- **Cost:** `fragility_backtest.py` now re-exports the moved names so research
  callers are unchanged. That is a convenience, not a second definition — a
  test asserts the re-exports are the same objects — but a reader will find
  `fetch_sector_etfs` importable from two places and must know which one owns it.
- **Cost:** "product" and "research" are not the same axis as the four doc
  layers (concepts / foundations / reference / decisions / record), which
  are organised by kind of reader. The two pages sit above the layers as
  tracks and point into them; they must not grow into a second copy of the
  reference — the same defect the maintenance log has diagnosed twice.
- **Cost:** `bias_separation` and `point_in_time` are classified product on
  the strength of who imports them (the accuracy report and the rebalance),
  although both read like research. The classification follows the import
  graph, not the prose; if either stops being imported by product it moves.
