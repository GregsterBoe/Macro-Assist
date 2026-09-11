# CLAUDE.md

Working notes for a coding session in this repo. This file is **pointers and
rules**, not documentation — it does not restate what the four doc layers
already say, and it must not become a second copy of them.

> **Read first if you have no context:** [The cut](docs/concepts/the-cut.md).
> In September 2026 this project deleted its main feature — the directional
> call — because three measurements said it carried no information. Most of the
> repo's shape follows from that. Proposing anything that reintroduces a
> Bias/Confidence prediction means arguing against [ADR-0009](docs/decisions/ADR-0009-cut-the-directional-product.md).

---

## Orientation

| Layer | Path | Is the source of truth for |
|---|---|---|
| **Concepts** | `docs/concepts/` | What the system is for, and why |
| **Reference** | `docs/reference/` | **How the code behaves today** — kept current with the code |
| **Decisions** | `docs/decisions/` | **Why** the system has its shape (19 ADRs) |
| **Record** | `docs/record/` | Plans, status, and **measured findings** |

Inside `docs/record/`:

| File | Holds | Don't put here |
|---|---|---|
| `knowledge-base.md` | **Measured results** (KB-###), negatives included | Plans |
| `roadmap.md` | Live plans — open phases and work packages | Shipped detail (→ archive) |
| `roadmap-archive.md` | Closed phases, historical implementation detail | — |
| `active-experiments.md` | **The status board** — one row per live track | Detail (link to it) |
| `improvement-track.md` | IMP-# experiments on components that exist | Results (→ KB) |
| `todo.md` | **The single inbox** for open decisions & carried findings | Anything resolved |
| `maintenance-log.md` | Dated housekeeping passes | Open items (→ `todo.md`) |

**When two docs disagree about status, `active-experiments.md` wins.** When a
board row and a detailed doc disagree about substance, the detailed doc wins —
fix the row.

---

## Commands

```bash
pip install -r .macro-assist/requirements.txt

# generated output is a separate orphan branch, mounted as a worktree (ADR-0001)
git fetch origin output && git worktree add results output

pytest .macro-assist/tests/                 # ~750 tests, ~3.5 min
python .macro-assist/collect_and_analyze.py --fetch-only   # no LLM call, no writes
python .macro-assist/collect_and_analyze.py  # full daily pipeline (costs API money)
python .macro-assist/score_distributions.py  # the current scorer
mkdocs build --strict                        # what CI runs; fails on a broken link
```

`pytest.ini` excludes `-m integration` by default. **`test_point_in_time.py` is
the exception** — it makes real ALFRED/FRED network calls (~113 s) and is
deliberately *not* marked `integration` because it is the look-ahead-leakage
guard. To work offline:

```bash
pytest .macro-assist/tests/ --deselect .macro-assist/tests/test_point_in_time.py
```

Full setup, env vars and CI: [Development](docs/reference/development.md) ·
[Operations](docs/reference/operations.md).

---

## Conventions that are binding

These are load-bearing and easy to violate by accident. Each links to the full
reasoning — read it before arguing for a change, don't re-derive it.

**1. Archive-on-completion.** When a **WP** is done *and* its result is in
`knowledge-base.md`, trim its roadmap entry to one line + verdict + KB pointer.
When a **phase** closes, move the remaining detail to `roadmap-archive.md` and
add a row to its table. **Never trim before the result is in the KB** — that
loses information. Don't archive context a still-open sibling WP depends on.

**2. Negatives MUST be logged.** Every improvement experiment that produces a
measured result gets a KB entry, including "this has no skill". A negative is as
valuable as a win — it stops the next session re-running a dead end. Format:
*what we tested → headline → the nuance that's easy to forget → what it changes*,
with the caveats attached to the headline.

**3. Soft-kill: deactivate, never delete** ([ADR-0015](docs/decisions/ADR-0015-soft-kill-convention.md)).
Remove the stage from `pipeline.yml` and its cron call. The module, its tests,
its emitted notes, its scored history and its `workflow_dispatch` trigger all
stay. Restoring is a one-line change.

**4. One canonical asset registry** ([ADR-0011](docs/decisions/ADR-0011-canonical-asset-registry.md)).
`assets.forward_change()` is defined once and imported by `refit_models` (build),
`quant_context` (render) and `score_distributions` (score). Stored numbers are in
**display units** named by `Asset.unit` — `pct` means percent, `level` means
**basis points**. Never redefine "forward change" locally.

**5. One pipeline entry point** ([ADR-0013](docs/decisions/ADR-0013-one-pipeline-entry-point.md)).
`pipeline.yml` is the only scheduled entry point; stages are `needs:`-ordered
jobs, not cron offsets. **The date is resolved once** by the `plan` job and
passed to every stage as `asof` — no stage derives its own.

**6. Output lives on the orphan branch** ([ADR-0001](docs/decisions/ADR-0001-output-on-an-orphan-branch.md)).
Code on `main`, everything generated under `results/` on `output`. Scripts read
and write `<repo>/results/` and know nothing about the split. Never rewrite
`output` history.

**7. Pre-register before you look.** A bar committed after seeing the data is not
a bar. [KB-027] caught exactly this — a `verdict()` that returned "edge" for an
arm its own pre-registration had disqualified. Disqualifiers are evaluated
*first*, each with a test asserting it fires ahead of a strong skill number.
Raising a threshold after seeing a result is a goalpost move; fixing a defect the
pre-registration already required is not.

**8. Docs are the single source.** The markdown under `docs/` generates the site;
never author the site separately. A second drifting copy of the system
description is a defect this project has already diagnosed twice
(`maintenance-log.md`, 2026-09-04 and 2026-09-08).

**9. Bump the version for capability changes only.** `.macro-assist/versions.py`
is central; use `bump_version.py`, which does the whole edit atomically. Bump for
a structural capability change — new data source, new agent pass, a change to
what the note publishes — **not** for a bug fix or an output-identical refactor.
See [Versioning](docs/reference/versions.md).

**10. ADRs: number sequentially, never renumber, never delete.** Supersede and
link both ways. See [the index](docs/decisions/index.md) for the page shape — a
page with no costs listed has not been thought through.

---

## Current state

| | |
|---|---|
| **Version** | **v2.0** — the measured line; 1.x predicted direction |
| **Live product** | Conditional return distribution across 6 assets + Fragility Monitor |
| **Live experiment** | Phase 22 distribution scorer — bar sealed, first honest read ~2027-05 |
| **Winding down** | The directional scorer, once the last T+20 window resolves ~2026-10-02 |
| **Blocked on a decision** | WP-21.E families 2–3, pending a written BSS floor ([ADR-0017](docs/decisions/ADR-0017-bss-floor-left-open.md)) |

The board in [active-experiments.md](docs/record/active-experiments.md) is
authoritative. If this table disagrees with it, the board wins — and fix this
table.

---

## Gotchas

- **`llm_analysis.py` is the largest and least-tested module** (~1,200 lines).
  Kept as one module to minimise churn in untested code; see `maintenance-log.md`
  open follow-ups before splitting it.
- **GitHub Pages is off** and every `main` push touching `docs/` fails at the
  deploy preflight until a repo admin turns it on once. The preflight names the
  fix. Not a code problem — don't try to fix it in the workflow.
- **`score_predictions.py` is frozen, not dead** ([ADR-0010](docs/decisions/ADR-0010-freeze-the-directional-scorer.md)).
  It gates on version so v1.5-and-earlier history stays scoreable. It scores
  nothing on v1.6+ notes. Its readers (`summarize_accuracy.py`,
  `bias_separation.py`) stay — they read the history.
- **Prompt profile toggles are inert** since v1.6. `run_config()` still resolves
  and records them so the frontmatter contract and historical readers keep
  working; `MACRO_PROFILE` still selects the model. The A/B they existed for is
  closed.
