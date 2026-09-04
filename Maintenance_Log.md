# Maintenance Log

Running record of housekeeping / cleanup passes (code hygiene, refactors, doc
pruning) — kept separate from `Project_Development_Archive.md` (closed roadmap
phases) and `Knowledge_Base.md` (measured findings). Newest entry first. Append a
new dated section per pass; carry any unfinished items into **Open follow-ups**.

---

## Open follow-ups

- **`point_in_time.py` runs network by default.** Its tests make real ALFRED/FRED calls (~113s of the default suite) but are *not* marked `integration`, so they run on every `pytest`. They're an important look-ahead-leakage guard — left in the default run deliberately. Decide whether to mark them `integration` (faster default; guard then only runs on explicit `-m integration`).
- **Optional further split of `llm_analysis.py`** (1331 lines). One cohesive concern (the multi-agent LLM pipeline) but the largest remaining module and the least test-covered. Could later split into agents / synthesis / note-markdown if it keeps growing; kept as one module for now to minimise churn in untested code.
- **Archive Phase 19 build detail** (`Project_Development.md`) once the exogenous arm resolves to keep-or-kill. Still open, and the trigger changed: KB-012 will never be written as specified — the arm's live gate became unreadable when v1.6 cut its comparator (WP-21.F). The resolution now comes from **WP-19.E** (the SPF anchor scored in the numeric harness) plus a decision on option (b) (re-cut the branch's output to the expectations gap). Archive the L0–L4 build detail then, keeping the integration-status + kill block inline.

---

## 2026-09-04 — Post-cut doc pass: archive what v1.6 made stale

`Project_Development.md` **1,252 → 460 lines**; `Project_Development_Archive.md`
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
Phase-15 backlog table, and every cross-reference — `Active_Experiments.md`
pointers were re-aimed at the summary or the archive rather than left dangling.

**Title changed:** "Project State" → "Project Development (the roadmap)". The old
title was the reason the system-state block grew there in the first place.

---

## 2026-08-20 – 08-21 — General cleanup & reorganize pass

Suite baseline before: 435 passed / 4 failed / 1 xfailed → after: **442 passed / 8 deselected / 1 xfailed** (default run is now pure/no-network). All source pyflakes-clean.

**Git hygiene** — untracked 2 committed `.pyc` files (already gitignored); removed the orphan `.macro-assistdata.gitkeep` typo.

**Dead code** — removed 12 unused imports + a redundant `json` re-import + a dead `model =` assignment; stripped 20 placeholder-less `f"…"` prefixes.

**Test-suite health** — the 3 drifting yfinance asserts (`test_r_squared_in_range`, regime `historical_alignment` / `switch_count_reasonable`) were already `@pytest.mark.integration`; added `addopts = -m "not integration"` to `pytest.ini` so the default run excludes them (run with `pytest -m integration`). Fixed an isolation leak in `test_empty_on_no_data` (monkeypatch `DEFAULT_TABLE_PATH`).

**Doc pruning** (`Project_Development.md` 96.7 KB → 85.3 KB) — pruned the self-flagged WP-19.B build-log to a pointer; trimmed completed WP-16.A.1/2/3 to status+verdict+KB-pointer (kept A.4's `FRAGILITY_MODE` ladder — open A.5 depends on it). Phase-17 WPs already at target granularity (no-op). Phase archiving (5d) deferred — see Open follow-ups.

**HMM regime retired (kept for revival)** — single switch `regime_enabled()` in `regime.py` (grep `REGIME-RETIRED`), **default OFF**, `REGIME_ENABLED=1` revives. Gated all three execution sites: portfolio gate (`rebalance.live_regime` → gate 1.0), weekly refit (`refit_models` → skips HMM fit, keeps the feature matrix the non-retired conditional table needs), payload preview (`quant_context.build_nonlive_signals_block` → omits block). Code (`regime*.py`, `conditional.py`) untouched.

**Split `collect_and_analyze.py`** (2865 → 463 lines) — AST-based move into focused modules; public API preserved via re-exports + `__all__`, so external importers (`point_in_time`, `input_ledger`, `exogenous/sep`, tests) are unchanged:
`pipeline_common.py` (58, logger/paths/schemas flag/`next_review_date` — no pipeline imports so no cycles), `fred_data.py` (222), `market_data.py` (616), `calendar_events.py` (98), `pipeline_config.py` (216), `llm_analysis.py` (1331), and the slim `collect_and_analyze.py` orchestrator (463).
