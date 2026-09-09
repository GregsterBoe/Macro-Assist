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

</div>

---

## The four layers

This documentation is deliberately layered, because the project has four
different kinds of reader and they want incompatible things.

| Layer | Answers | Where |
|---|---|---|
| **Orientation** | What is this, and what state is it in? | [README](https://github.com/GregsterBoe/Macro-Assist#readme) · this page |
| **Concepts** | What do I need to know to follow the current work? | [Concepts](concepts/index.md) |
| **Reference** | How exactly does X work? | [Reference](reference/index.md) |
| **Record** | What was tried, what was measured, what was decided? | [Knowledge Base](record/knowledge-base.md) · [Decisions](decisions/index.md) · [Roadmap](record/roadmap.md) |

The rule that keeps them from drifting: **a fact lives in exactly one layer.**
Concepts explain and link; they do not restate reference detail. Reference
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
| **Pipeline version** | v1.6 (2026-09-05 →) |
| **Published product** | Empirical conditional return distribution (median, P25/P75, n) across 6 assets, plus the Fragility Monitor as the headline risk read |
| **Not published** | Any directional call. Removed in v1.6 — [KB-024](record/knowledge-base.md) |
| **Live experiment** | Phase 22 — the distribution scorer. Bar sealed 2026-09-08, first honest read ~2027-05 |
| **Winding down** | The directional scorer, once the last open T+20 window resolves ~2026-10-02 |
| **Blocked on a decision** | WP-21.E families 2–3, pending a written BSS floor — [KB-027](record/knowledge-base.md) |

The authoritative version of this table is the board in
[Active experiments](record/active-experiments.md). If the two disagree, the
board wins.
