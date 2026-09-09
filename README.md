# Macro-Assist

**An automated daily macro intelligence pipeline — and the record of what it has
actually measured about itself.**

Every weekday morning a GitHub Actions workflow fetches live economic and market
data from free sources, computes a layer of quantitative context in Python, runs
a four-agent Claude pipeline over it, and delivers a formatted Markdown note to a
personal Obsidian vault. Every Monday it grades what it published. Every Sunday
it refits its statistical models.

It costs a few dollars a month in API calls and runs on no servers.

📖 **[Browse the full documentation →](https://gregsterboe.github.io/Macro-Assist/)**

---

## The thing worth knowing first

In September 2026 this project deleted its main feature.

Until v1.5 the daily note led with a directional call — `Bias`
(Bullish/Bearish/Neutral) and a `Confidence %` — per asset, per horizon, scored
weekly against the market. Three independent measurements said that call carried
no information:

- decisive calls resolved at **~36%** with a Brier skill score of **−0.195**
  ([KB-007]);
- the bias label *did* separate forward returns, but ordered them **backwards**
  ([KB-022]);
- and the A/B that looked like it had fixed the problem turned out to be
  confounded — arm and market period were the same partition of the data
  ([KB-023]).

Every one of those measured **the model**. None could distinguish *our analyst is
bad at this* from *this task is not doable from this payload*. So a harness was
built to ask the second question with the LLM removed: an 18-year walk-forward
panel, two small regularised numeric models, a planted-signal positive control,
and a bar committed before the run.

A constant `always_bullish` beat both fitted models on hit-rate, Brier, skill
score **and** calibration error simultaneously ([KB-024]).

So the product was cut rather than defended, along with the entire
self-calibration loop that had been steering it. What the note publishes now is
**measured rather than predicted**: the empirical distribution of forward returns
in macro conditions like today's, and a tail-risk gauge with validated
out-of-sample skill and its precision limit printed next to it.

If you read one page in this repository, read
**[The cut](docs/concepts/the-cut.md)**.

---

## What it produces today

One note per weekday, containing:

| Block | Authored by | What it is |
|---|---|---|
| **Fragility Monitor** | Python, after the LLM call | 0–100 composite tail-risk gauge + a higher-recall OR-of-channels flag. Precision ≈ 0.32 stated inline — a high-recall warning, never a forecast |
| Executive summary, macro dashboard, per-asset sections | Claude (schema-constrained) | Equities, rates, inflation/growth, commodities, sector research, key risks |
| **5-Day Outlook** | Python renders the distribution; Claude writes the driver | Per asset: empirical conditional return distribution (median, P25/P75, `n`) for the current macro-state bucket, primary driver, target range |

And **no directional call**, anywhere.

---

## Documentation

The docs are layered, because the project has four kinds of reader and they want
incompatible things. Everything lives under [`docs/`](docs/) and is published as a
searchable site.

### Start here

| If you want to… | Read |
|---|---|
| Understand what this is | [What this is](docs/concepts/what-this-is.md) → [The signal stack](docs/concepts/the-signal-stack.md) |
| Follow the current work | [The method](docs/concepts/the-method.md) → [The cut](docs/concepts/the-cut.md) → [the board](docs/record/active-experiments.md) |
| Know what has been established | [What we believe](docs/concepts/what-we-believe.md) |
| Know why something is the way it is | [Decisions](docs/decisions/index.md) |
| Operate or fix it | [Operations](docs/reference/operations.md) · [Development](docs/reference/development.md) |
| Look something up | [Reference](docs/reference/index.md) |

### The four layers

**[Concepts](docs/concepts/index.md)** — five essays: what the system is, how a
data point becomes a published claim, the epistemic rules the project runs on,
the story of the v1.6 cut, and the standing conclusions.

**[Reference](docs/reference/index.md)** — how it works today.
[Architecture](docs/reference/architecture.md) ·
[Data sources](docs/reference/data-sources.md) ·
[Analysis pipeline](docs/reference/analysis-pipeline.md) ·
[Scoring](docs/reference/scoring.md) ·
[Operations](docs/reference/operations.md) ·
[Development](docs/reference/development.md)

**[Decisions](docs/decisions/index.md)** — 19 ADRs. One page per load-bearing
choice, with the evidence that forced it and whether it still holds. This is the
layer for revisiting a design choice without re-deriving it.

**[Record](docs/record/knowledge-base.md)** — the durable evidence.

| Document | Role |
|---|---|
| [Knowledge Base](docs/record/knowledge-base.md) | **Measured findings** (KB-###), negatives included. The durable record |
| [Active experiments](docs/record/active-experiments.md) | Live status board — what is running, right now |
| [Roadmap](docs/record/roadmap.md) | Phases and work packages (plans) |
| [Improvement track](docs/record/improvement-track.md) | Improvement experiments on existing components |
| [Open decisions](docs/record/todo.md) | Working memory: known, deliberately not done, and why |
| [Maintenance log](docs/record/maintenance-log.md) | Housekeeping and doc-hygiene passes |
| [Roadmap archive](docs/record/roadmap-archive.md) | Closed phases and superseded detail |

The rule that keeps these from drifting: **a fact lives in exactly one layer.**
Concepts explain and link. Reference describes today. The record is append-mostly
and is never rewritten to match a later opinion.

---

## Current state

| | |
|---|---|
| **Pipeline version** | v1.6 (2026-09-05 →) |
| **Live product** | Conditional return distribution across 6 assets + the Fragility Monitor headline |
| **Live experiment** | Phase 22 — the distribution scorer. Bar sealed 2026-09-08, first honest read ~2027-05 |
| **Winding down** | The directional scorer, once the last T+20 window resolves ~2026-10-02 |
| **Blocked on a decision** | WP-21.E families 2–3, pending a written BSS floor ([ADR-0017](docs/decisions/ADR-0017-bss-floor-left-open.md)) |
| **Soft-killed** | Kimi ensemble arm · exogenous weekly emit · HMM regime block · run-profile levers |

The authoritative version is the board in
[Active experiments](docs/record/active-experiments.md). If this table and the
board disagree, the board wins.

---

## Quick start

```bash
pip install -r .macro-assist/requirements.txt

# generated output lives on an orphan branch, mounted as a worktree
git fetch origin output
git worktree add results output

# data fetch check — no LLM call, no file writes
export FRED_API_KEY=...
python .macro-assist/collect_and_analyze.py --fetch-only

# the full daily pipeline
export ANTHROPIC_API_KEY=...
python .macro-assist/collect_and_analyze.py

# the test suite
pytest .macro-assist/tests/
```

Full setup, environment variables and CI details are in
[Development](docs/reference/development.md) and
[Operations](docs/reference/operations.md).

---

## Building the docs site

```bash
pip install -r docs/requirements.txt
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict # what CI runs; fails on a broken internal link
```

The markdown under `docs/` is the single source of truth. The site is generated
from it and never authored separately — a second, drifting copy of the system
description is a defect this project has already diagnosed once and written up
(see the [maintenance log](docs/record/maintenance-log.md), 2026-09-04).

Publishing is handled by `.github/workflows/docs.yml` on pushes to `main`.
One-time setup: repo **Settings → Pages → Source: GitHub Actions**.

---

## A note on scope

This is a personal research system. It is not investment advice, its outputs are
not signals, and its most reliable finding to date is that it could not predict
direction. What it does well — measuring whether a claim is worth publishing, and
deleting the claim when it is not — is the part worth borrowing. That method is
written up in [The method](docs/concepts/the-method.md).
