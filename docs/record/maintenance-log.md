# Maintenance Log

Running record of housekeeping / cleanup passes (code hygiene, refactors, doc
pruning) — kept separate from `roadmap-archive.md` (closed roadmap
phases) and `knowledge-base.md` (measured findings). Newest entry first. Append a
new dated section per pass; carry any unfinished items into **Open follow-ups**.

---

## Open follow-ups

- **`point_in_time.py` runs network by default.** Its tests make real ALFRED/FRED calls (~113s of the default suite) but are *not* marked `integration`, so they run on every `pytest`. They're an important look-ahead-leakage guard — left in the default run deliberately. Decide whether to mark them `integration` (faster default; guard then only runs on explicit `-m integration`).
- **Optional further split of `llm_analysis.py`** (1331 lines). One cohesive concern (the multi-agent LLM pipeline) but the largest remaining module and the least test-covered. Could later split into agents / synthesis / note-markdown if it keeps growing; kept as one module for now to minimise churn in untested code.
- **GitHub Pages is still switched off.** The docs site cannot publish until a repo admin sets **Settings → Pages → Build and deployment → Source: "GitHub Actions"** once — or, when that settings page 404s, does the same with `POST /repos/GregsterBoe/Macro-Assist/pages -d '{"build_type":"workflow"}'` under a PAT that has admin on the repo. Storing that PAT as the `PAGES_ADMIN_TOKEN` secret lets the deploy preflight do it instead; the default Actions token still cannot (see 2026-09-10 below). Every push to `main` that touches `docs/` will keep failing at the deploy preflight until it is done.
- **Archive Phase 19 build detail** (`roadmap.md`) once the exogenous arm resolves to keep-or-kill. Still open, and the trigger changed: KB-012 will never be written as specified — the arm's live gate became unreadable when v1.6 cut its comparator (WP-21.F). The resolution now comes from **WP-19.E** (the SPF anchor scored in the numeric harness) plus a decision on option (b) (re-cut the branch's output to the expectations gap). Archive the L0–L4 build detail then, keeping the integration-status + kill block inline.

---

## 2026-09-10 — The docs site cannot switch itself on

Three consecutive `main` builds of `docs.yml` failed. The first two died at
`actions/deploy-pages` with a bare 404; the fix for that (PR #23) added
`actions/configure-pages` with `enablement: true`, and the third died one step
earlier and louder:

```
Get Pages site failed. Error: Not Found
Create Pages site failed. Error: Resource not accessible by integration
```

**The finding.** `enablement` cannot work here, and no `permissions:` block
changes that. `POST /repos/{owner}/{repo}/pages` requires repository *admin*
rights; the Actions `GITHUB_TOKEN` is an installation token that has `pages:
write` but is not an admin, so the create call is refused. The one-time setting
the 2026-09-08 entry recorded is not a convenience — it is the only way to turn
Pages on, and it has to be done in the browser.

**What changed.** `configure-pages` is gone from the build job: it was
attempting the impossible, and MkDocs does not use its `base_url` output (the
site URL is pinned in `mkdocs.yml`). The build job drops back to `contents:
read`, with the Pages scopes now only on the job that deploys. In their place
the deploy job runs a preflight that reads the Pages API and distinguishes the
two states `deploy-pages` reports identically as 404 — Pages off, and Pages on
but reading from a branch — naming the setting to change in each case.

This does not make `main` green. It makes the red legible: until an admin flips
the setting, the run fails at a step that says exactly what to do, instead of at
a 404 that says nothing. Carried in **Open follow-ups** above.

**Correction, same day: "in the browser" was too strong.** The admin-rights
finding holds; the conclusion drawn from it did not. What `POST /repos/.../pages`
requires is an *admin token*, not a human at a settings page — a PAT the repo
owner issues has admin, so the same call that `GITHUB_TOKEN` is refused succeeds
under one. This matters because the settings page itself can be the thing that
fails: a 404 on `/settings/pages`, or a Source dropdown that will not stick,
leaves the browser route with no fallback if the browser is believed to be the
only route.

So the preflight now takes an optional `PAGES_ADMIN_TOKEN` secret. With it set,
the step stops reporting the misconfiguration and fixes it — `POST` to create the
site when Pages is off, `PUT` to move it to `build_type: workflow` when it reads
from a branch — then carries on to deploy. Without it the behaviour is unchanged
except that the error now prints the `curl` as well as the settings path, so
whichever route is open to the reader is in front of them. The one-time setup is
still one-time and still needs admin; it no longer needs a working settings page.

---

## 2026-09-08 — Docs restructure: four layers, a decision record, and a site

The doc set was disciplined but flat: ~5,300 lines across eight top-level files,
no index, and a 849-line README serving four audiences at once. Three gaps, none
of which was "the files aren't listed":

1. **No conceptual layer.** Nothing explained what the project is *for* or told
   the story that shapes it — the directional product's measurement, falsification
   and deletion — which existed only as sediment across KB-007/022/023/024/026/027.
2. **No map.** Eight documents, no entry point.
3. **Decisions were not addressable.** "Why not a neural network" was prose in the
   roadmap; the Phase 19/20 scope-locks were `DESIGN.md` files beside code; the
   load-bearing calls (the cut, the frozen scorer, `EDGE_MIN_BSS` left at 0.0)
   were buried in KB consequence sections.

**What moved.** All seven long-lived docs into `docs/record/`, via `git mv` so
history follows. Nothing was rewritten and nothing was deleted; only cross-links
and filenames changed.

| Was | Now |
|---|---|
| `Knowledge_Base.md` | `docs/record/knowledge-base.md` |
| `Project_Development.md` | `docs/record/roadmap.md` |
| `Project_Development_Archive.md` | `docs/record/roadmap-archive.md` |
| `Active_Experiments.md` | `docs/record/active-experiments.md` |
| `Project_Improvement.md` | `docs/record/improvement-track.md` |
| `TODO.md` | `docs/record/todo.md` |
| `Maintenance_Log.md` | `docs/record/maintenance-log.md` |

**What was added.**
- `docs/concepts/` — five essays: what this is · the signal stack · **the
  method** · the cut (v1.6) · what we believe.
- `docs/reference/` — the old README body, split by audience across six pages,
  updated for v1.6 where it had drifted (the dataflow diagram still showed the
  retired accuracy override; Window-Aware Calibration was described as live; the
  `verdict()` bar predated the [KB-027] correction; `score_distributions.py` was
  undocumented).
- `docs/decisions/` — **19 ADRs** back-filled from the KB, roadmap, both
  `DESIGN.md` scope-locks and todo.md. One is `Open` (ADR-0017, the BSS floor)
  and is the one currently blocking work.
- `mkdocs.yml` + `.github/workflows/docs.yml` — MkDocs Material on GitHub Pages.
  The markdown stays the single source of truth and the site is generated from
  it; `mkdocs build --strict` fails on a broken internal link, so a future doc
  move cannot leave a dangling reference. **One-time setup still required:**
  Settings → Pages → Source: GitHub Actions.

**README** cut 849 → 190 lines: the arc, the current state, and the map.

**Code touched, minimally.** Doc-path references in nine modules updated;
`bump_version._PROJECT_DOC` re-pointed to `docs/record/roadmap.md`. No behaviour
changed.

**Found, not fixed:** `bump_version.py` has been broken since the 2026-09-04
archive pass — the anchors it edits moved into the archive with the v1.5
snapshot, so any bump raises. Recorded as **open decision #9** rather than
patched, because it asks where the milestones table belongs now.

---

## 2026-09-04 — Post-cut doc pass: archive what v1.6 made stale

`roadmap.md` **1,252 → 460 lines**; `roadmap-archive.md`
512 → 1,446. Nothing deleted — three blocks moved, each replaced inline by a
summary that keeps the verdict, the KB pointer and anything a still-open sibling
WP depends on (the archive-on-completion convention this file's roadmap declares).

**What moved, and why it was stale rather than merely old:**
- **The v1.5 system-state snapshot** (~390 lines: What It Does / Architecture /
  Data Sources / Analysis Model Logic / Output Format / Prediction Evaluation /
  CI / Portfolio module / Result Versioning / Annual Maintenance). It described
  the note's Bias/Confidence table (cut in v1.6, [KB-024]), a self-calibration
  feedback loop whose code WP-21.G **deleted**, and a workflow schedule that
  predates `pipeline.yml`. `README.md` describes the system that actually runs.
  The defect was structural: a second copy of the system description living in
  the roadmap, drifting against the maintained one.
- **Phase 16** (Emergence & Fragility) — closed. 16.A shipped and is alive as
  IMP-4's OR flag; 16.B/C were closed by Phase 21 ([KB-023] made the loosened A/B
  unreadable, [KB-024] made ranking prompt configs moot). B.3 and C.2 are marked
  **superseded**, not pending: both weighted or retrieved for a directional call
  that no longer exists. Live summary keeps the fragility shadow clock, which is
  the one remnant still waiting on data.
- **Phase 21's WP-level detail** (A–D, the execution order, F and G) — the
  measured result is [KB-024] and the code is live, so the method detail was
  redundant with both. WP-21.E stays inline (queued, blocks nothing), as does the
  "why not a neural network" decision — it exists to stop a re-litigation, which
  only works if it is where the next reader is.

**Kept deliberately:** Phases 17/18/19/20 (each has an open sibling WP), the
Phase-15 backlog table, and every cross-reference — `active-experiments.md`
pointers were re-aimed at the summary or the archive rather than left dangling.

**Title changed:** "Project State" → "Project Development (the roadmap)". The old
title was the reason the system-state block grew there in the first place.

---

## 2026-08-20 – 08-21 — General cleanup & reorganize pass

Suite baseline before: 435 passed / 4 failed / 1 xfailed → after: **442 passed / 8 deselected / 1 xfailed** (default run is now pure/no-network). All source pyflakes-clean.

**Git hygiene** — untracked 2 committed `.pyc` files (already gitignored); removed the orphan `.macro-assistdata.gitkeep` typo.

**Dead code** — removed 12 unused imports + a redundant `json` re-import + a dead `model =` assignment; stripped 20 placeholder-less `f"…"` prefixes.

**Test-suite health** — the 3 drifting yfinance asserts (`test_r_squared_in_range`, regime `historical_alignment` / `switch_count_reasonable`) were already `@pytest.mark.integration`; added `addopts = -m "not integration"` to `pytest.ini` so the default run excludes them (run with `pytest -m integration`). Fixed an isolation leak in `test_empty_on_no_data` (monkeypatch `DEFAULT_TABLE_PATH`).

**Doc pruning** (`roadmap.md` 96.7 KB → 85.3 KB) — pruned the self-flagged WP-19.B build-log to a pointer; trimmed completed WP-16.A.1/2/3 to status+verdict+KB-pointer (kept A.4's `FRAGILITY_MODE` ladder — open A.5 depends on it). Phase-17 WPs already at target granularity (no-op). Phase archiving (5d) deferred — see Open follow-ups.

**HMM regime retired (kept for revival)** — single switch `regime_enabled()` in `regime.py` (grep `REGIME-RETIRED`), **default OFF**, `REGIME_ENABLED=1` revives. Gated all three execution sites: portfolio gate (`rebalance.live_regime` → gate 1.0), weekly refit (`refit_models` → skips HMM fit, keeps the feature matrix the non-retired conditional table needs), payload preview (`quant_context.build_nonlive_signals_block` → omits block). Code (`regime*.py`, `conditional.py`) untouched.

**Split `collect_and_analyze.py`** (2865 → 463 lines) — AST-based move into focused modules; public API preserved via re-exports + `__all__`, so external importers (`point_in_time`, `input_ledger`, `exogenous/sep`, tests) are unchanged:
`pipeline_common.py` (58, logger/paths/schemas flag/`next_review_date` — no pipeline imports so no cycles), `fred_data.py` (222), `market_data.py` (616), `calendar_events.py` (98), `pipeline_config.py` (216), `llm_analysis.py` (1331), and the slim `collect_and_analyze.py` orchestrator (463).
