# Start here

Macro-Assist is a daily macro intelligence pipeline that is also, and more
importantly, **a record of what it has actually measured about itself**.

Every weekday it fetches economic and market data, runs a multi-agent Claude
pipeline, and delivers a formatted note to an Obsidian vault. Every week it
scores what it published. Roughly every other month, one of those scores kills a
feature.

The most recent one killed the main product. In September 2026 the pipeline
stopped making directional calls, because eighteen years of walk-forward
evidence said that on this payload, at these horizons, **nobody can** — see
[The cut](concepts/the-cut.md).

---

## Two tracks

| | What it is | Where |
|---|---|---|
| **Product** | What is ready to use, what it promises, what it does not — and the module boundary that keeps it stable | [Product](product/index.md) |
| **Research** | The ladder a question climbs: exploration → confirmation → accepted finding → product. Nothing crosses a rung without a bar | [Research](research/index.md) |

The two are separated by an import rule the test suite enforces: research
measures the product and may import it; the product never imports research
([ADR-0021](decisions/ADR-0021-product-and-research-are-separated-by-an-import-boundary.md)).

---

## Pick a path

<div class="grid cards" markdown>

- **:material-compass: I want to understand what this is**

    Start with [What this is](concepts/what-this-is.md), then
    [The signal stack](concepts/the-signal-stack.md). About 20 minutes.

- **:material-flask: I want to understand the current work**

    Read [The method](concepts/the-method.md) and
    [The cut](concepts/the-cut.md), then the live board in
    [Active experiments](record/active-experiments.md).

- **:material-book-open-variant: I want to know what has been established**

    [What we believe](concepts/what-we-believe.md) is the distilled version.
    The evidence behind every line of it is the
    [Knowledge Base](record/knowledge-base.md).

- **:material-help-circle: I want to know why something is the way it is**

    [Decisions](decisions/index.md) — one page per load-bearing choice, with
    the evidence that forced it and whether it still holds.

- **:material-wrench: I need to operate or fix it**

    [Operations](reference/operations.md) for the pipeline, cron and secrets;
    [Development](reference/development.md) to run it locally.

- **:material-file-find: I need to look something up**

    [Reference](reference/index.md) — data sources, agents, scoring, workflows.

- **:material-school: I met a term I don't know**

    [Foundations](foundations/index.md) — absorption ratio, Brier skill score,
    block bootstrap, seal: the background the other layers assume, in this
    project's terms, each entry pointing at the code that owns the number.

</div>

---

## The layers

This documentation is deliberately layered, because the project has several
different kinds of reader and they want incompatible things.

| Layer | Answers | Where |
|---|---|---|
| **Orientation** | What is this, and what state is it in? | [README](https://github.com/GregsterBoe/Macro-Assist#readme) · this page |
| **Concepts** | What do I need to know to follow the current work? | [Concepts](concepts/index.md) |
| **Foundations** | What does this term mean, and where is its number owned? | [Foundations](foundations/index.md) |
| **Reference** | How exactly does X work? | [Reference](reference/index.md) |
| **Record** | What was tried, what was measured, what was decided? | [Knowledge Base](record/knowledge-base.md) · [Decisions](decisions/index.md) · [Roadmap](record/roadmap.md) |

The rule that keeps them from drifting: **a fact lives in exactly one layer.**
Concepts explain and link; they do not restate reference detail. Foundations
define general concepts and point at the owner of every project-specific
number. Reference
describes the system as it is today; it does not narrate how it got there. The
record is append-mostly and is never rewritten to match a later opinion.

This is not a style preference. A second, drifting copy of the system
description living inside the roadmap is a defect this project has already
diagnosed, archived and written up — see the
[maintenance log](record/maintenance-log.md), 2026-09-04.

---

## Current state, in one table

| | |
|---|---|
| **Pipeline version** | v2.1 (2026-09-13 →; first note 2026-09-14) — [milestones](reference/versions.md) |
| **Published product** | Empirical conditional return distribution (median, P25/P75, n) across 6 assets, bucketed on NFCI × curve × BAA10Y over 26 years of history since v2.1, plus the Fragility Monitor as the headline risk read |
| **Not published** | Any directional call. Removed in v1.6 — [KB-024](record/knowledge-base.md) |
| **Live experiment** | Phase 22 — the distribution scorer. Bar sealed 2026-09-08, first honest read ~2027-05 |
| **Winding down** | The directional scorer, once the last open T+20 window resolves ~2026-10-02 |
| **Queued** | WP-21.E families 2–3 — unblocked by [ADR-0020](decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md); no family chosen, honest prior low |

The authoritative version of this table is the board in
[Active experiments](record/active-experiments.md). If the two disagree, the
board wins.
