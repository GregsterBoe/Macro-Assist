# Cleanup & Reorganize Plan

> **Temporary working tracker** (delete when finished). Compiled 2026-08-20.
> Tasks are ordered so they can be tackled one after another, cheapest/safest first.
> Baseline at compile time: `pytest` → **435 passed, 4 failed, 1 xfailed** (the 4
> failures are pre-existing live-data flakiness — see Task 6, they are *not* caused
> by anything here). Re-run the suite after each code task; nothing below should
> change the pass count except Task 6, which should turn 4 red → green/skipped.

---

## Tier 1 — Git hygiene (trivial, zero-risk, do first) — ✅ DONE 2026-08-20

### Task 1 — Untrack committed bytecode — ✅ DONE
Two `.pyc` files are tracked even though `.gitignore` already excludes `__pycache__/` and `*.pyc` (they were committed before the ignore rule).
- `.macro-assist/__pycache__/collect_and_analyze.cpython-313.pyc`
- `.macro-assist/__pycache__/youtube_data.cpython-313.pyc`

**Action:** `git rm --cached .macro-assist/__pycache__/*.pyc` (keep the ignore rule; files stay on disk).
**Done when:** `git ls-files | grep -c '\.pyc$'` → `0`.

### Task 2 — Delete the orphan gitkeep typo — ✅ DONE
`.macro-assistdata.gitkeep` (1 byte, project root) is a mis-typed duplicate of the real, correct `.macro-assist/data/.gitkeep`. It's tracked and serves no purpose.

**Action:** `git rm .macro-assistdata.gitkeep`.
**Done when:** file is gone; `.macro-assist/data/.gitkeep` remains.

---

## Tier 2 — Dead / unused code (mechanical, low-risk) — ✅ DONE 2026-08-20

### Task 3 — Remove unused imports (pyflakes-confirmed) — ✅ DONE
All verified by `python -m pyflakes`. Each is a plain unused import/name — deleting the line is safe.

| File | Line | Unused |
|------|------|--------|
| `collect_and_analyze.py` | 18 | `typing.Optional` |
| `collect_and_analyze.py` | 2016 | `pydantic.ValidationError as PydanticValidationError` |
| `conditional.py` | 46 | `sys` |
| `regime_backtest.py` | 48 | `typing.Optional` |
| `tag_versions.py` | 22 | `versions.VERSION_MILESTONES` |
| `portfolio/book.py` | 33 | `dataclasses.field` |
| `portfolio/sizing.py` | 53 | `dataclasses.field` |
| `portfolio/rebalance.py` | 49 | `portfolio.book.buy_and_hold` |
| `exogenous/run_slice.py` | 30 | `exogenous.analyst.ASSET_CANONICAL` |
| `exogenous/synth.py` | 22 | `typing.Optional` |

**Action:** delete each unused name; re-run `pyflakes` to confirm clean; run the suite.
**Note:** `parse_positions.py:546` re-imports `json` (already imported line 19) and `refit_models.py:320` assigns a local `model` that's never used — fold these two in here (remove the redundant re-import; drop or use the dead assignment — read the surrounding lines first).

### Task 4 — Fix f-strings with no placeholders — ✅ DONE (20 f-prefixes stripped; pyflakes fully clean)
Cosmetic but pyflakes-flagged (`f"..."` with no `{}`): `bump_version.py:121`, `collect_and_analyze.py:1156/1158/1160`, and a cluster in `summarize_accuracy.py` (629-640, 658-664, 711-712).
**Action:** drop the `f` prefix where there's genuinely no interpolation. Quick pass, do after Task 3 while in the same files.
**Done when:** `pyflakes` reports no "f-string is missing placeholders".

---

## Tier 3 — Documentation archiving (the biggest win; follows the repo's own convention)

`Project_Development.md` is **96 KB / ~740 lines** and violates its own stated
**"archive-on-completion"** rule (lines 402–409): completed WPs should be trimmed to
a one-line status + KB pointer, and closed phases moved to
`Project_Development_Archive.md`. Do these in order; each is self-contained.

> **Tier-3 progress (2026-08-20):** 5a + 5b done; 5c already-compliant (no-op); 5d deferred with rationale. `Project_Development.md` **96.7 KB → 85.3 KB (~12% smaller)**, markdown integrity verified.

### Task 5a — Prune the WP-19.B build-log (self-flagged) — ✅ DONE
Replaced the ~600-word build-log with a one-line pointer to `exogenous/` + `DESIGN.md` + git; kept the summary and the KB-013 early-read.
Line ~670 is a single ~600-word build-log paragraph the doc **itself** marks:
*"Original build-log retained below for now; git + DESIGN.md are the source of truth. Safe to prune to this summary."*
**Action:** collapse it to the 3–4-line summary already sitting above it (status, what it built, KB-012-pending, kill-procedure pointer). Keep the KB refs and the "Phase-19 integration status" block.

### Task 5b — Trim completed Phase-16.A WPs — ✅ DONE
Trimmed A.1/A.2/A.3 from multi-bullet method+result blocks to single status+verdict+key-numbers+KB-pointer lines (KB-001/002). **Kept A.4 fully intact** — its `FRAGILITY_MODE` log/show/active ladder is live operational context the still-open A.5 (and WP-18.1's non-live preview) depend on. A.5 untouched.

### Task 5c — Trim Phase-17 completed WPs — ✅ ALREADY COMPLIANT (no-op)
On inspection, 17.2/17.3/17.3b/17.4 are **already** single-line status+verdict+KB-pointer entries (KB-004…006). 17.1 carries extra detail (the `BAMLH0A0HYM2`→`BAA10Y` credit-feature bug fix) but that's context the **open WP-17.5** explicitly references ("truncated HY-OAS input"), so per the convention's guardrail it stays. No change needed.

### Task 5d — Archive closed phases → `Project_Development_Archive.md` — ⏸ DEFERRED (nothing cleanly closed)
Per the convention's "when an entire phase closes, move its detail to the archive + add a table row."
- **Phase 16.A** is effectively closed bar A.5 monitoring — consider moving the design detail once A.5 resolves (judgment call; may defer).
- **Phase 19** is INTEGRATED + forward-only (only KB-012 verdict pending) — a candidate to move the design/build detail to the archive, leaving the "integration status + kill procedure" summary inline.
**Assessment (2026-08-20):** none of Phases 16–20 are cleanly closed right now — each has a live/open sibling: 16.A→A.5 (monitoring), 17→17.5 (later), 18→18.4/18.5, 19→forward-validation live + KB-012 pending + 19.C/D/E future, 20→20.E, 16.B/C open. Phases 1–14 are already archived (table at line ~411). So there is nothing to archive without violating the "don't remove context an open decision depends on" guardrail. The 5a/5b prunes already reclaimed the bulk (~11 KB). **Revisit when a phase actually closes** — e.g. archive Phase 19's design/build detail (keep the integration-status + kill block inline) once KB-012 resolves to keep-or-kill.

---

## Tier 4 — Test-suite health

### Task 6 — Quarantine live-data-dependent tests — ✅ DONE 2026-08-20
**Resolution:** the 3 yfinance tests were *already* `@pytest.mark.integration`; the real gap was `pytest.ini` not excluding them. Added `addopts = -m "not integration"` so the default run is the pure suite (run integration explicitly with `pytest -m integration`). Fixed the isolation leak in `test_empty_on_no_data` by monkeypatching `quant_context.DEFAULT_TABLE_PATH` to a tmp path (mirrors the existing `DEFAULT_MODEL_PATH` pattern). **Default suite now: 431 passed, 8 deselected, 1 xfailed — green, no network asserts.**
**Follow-up spotted (not done):** `test_point_in_time.py` makes real ALFRED/FRED network calls (~113s of the run) but is **not** marked `integration`, so it still runs by default. It's an important look-ahead-leakage guard, so I left it in the default run rather than silently demoting a safety test — decide whether to mark it `integration` (faster default, but the leakage guard only runs on explicit `-m integration`) or leave it.

<details><summary>Original task note</summary>
4 tests fail on a clean run — **none are pure**, so they break the "no-network unit
suite" contract and produce false reds as market data / yfinance auto-adjust drift:
- `test_vol_forecast.py::test_r_squared_in_range` — downloads live `^GSPC`, asserts R²∈[0.2,0.7]; currently 0.094.
- `test_regime.py::test_historical_alignment` — downloads `^GSPC`, asserts ≥50% Risk-Off in Mar–May 2020; currently 49%.
- `test_regime.py::test_switch_count_reasonable` — downloads `^GSPC`, asserts 4–12 regime switches; currently 28.
- `test_quant_context.py::TestBuildQuantContext::test_empty_on_no_data` — **isolation leak**: expects empty output with no histories, but reads the ambient `.macro-assist/data/conditional_distributions.json` and renders a Conditional block. Not network — a fixture-isolation bug.

**Action:** (a) mark the three yfinance tests `@pytest.mark.network` (or `integration`) and register the marker in `pytest.ini` so the default run skips them / they run explicitly; (b) fix `test_empty_on_no_data` to monkeypatch `DEFAULT_TABLE_PATH` / point the data dir at a tmp path so it no longer reads real on-disk distributions.
**Done when:** default `pytest .macro-assist/tests` is fully green with no network dependence.
**Context:** the regime tests exercise the HMM layer that was **retired from the note** (KB-006) but is still used by the portfolio gate (`rebalance.live_regime`) — so keep the tests, just quarantine the live ones.
</details>

---

## Tier 5 — Judgment calls (discuss before doing)

### Task 7 — Retire the HMM regime cleanly (keep code, stop it running) — ✅ DONE 2026-08-20
Decision (user): keep the code for possible future use, but ensure it does **not run for now**. Implemented a single greppable switch `regime_enabled()` in `regime.py` (grep `REGIME-RETIRED`), **default OFF**, env-overridable with `REGIME_ENABLED=1` to revive every consumer at once. Gated all three execution sites so each degrades gracefully:
- **portfolio gate** (`rebalance.live_regime`) → returns None ⇒ book runs ungated (gate=1.0);
- **weekly refit** (`refit_models`) → skips the HMM fit (keeps the feature-matrix build the *non-retired* conditional table needs; stale `regime_model.pkl` left untouched);
- **payload preview** (`quant_context.build_nonlive_signals_block`) → omits the regime block.
Tests: added `regime_enabled` default/override tests + split the quant_context preview test into default-omitted / enabled-included. Suite green.

### Task 8 — Split `collect_and_analyze.py` — ✅ DONE 2026-08-20
Split the 2865-line monolith into focused modules (AST-based move; public API preserved via re-exports + `__all__`, so `point_in_time.py`, `input_ledger.py`, `exogenous/sep.py`, and the tests still `from collect_and_analyze import ...` unchanged):
- `pipeline_common.py` (58) — logger, paths, structured-output flag, `next_review_date` (shared foundation, no pipeline imports → no cycles)
- `fred_data.py` (222) — FRED fetch
- `market_data.py` (616) — market/sector/technicals/COT/notable-moves
- `calendar_events.py` (98) — FOMC/econ calendar
- `pipeline_config.py` (216) — run-config, prompt rendering, accuracy context
- `llm_analysis.py` (1331) — YouTube + all multi-agent LLM orchestration
- `collect_and_analyze.py` (**463**, was 2865) — slim orchestrator (`main`, `build_note`, `validate_data`, `get_output_path`, `_run_fetch_check`) + re-exports

All 7 pyflakes-clean; CLI entry (`collect_and_analyze.py --help`) loads all modules; full suite **442 passed / 8 deselected / 1 xfailed**.
**Optional follow-up:** `llm_analysis.py` (1331) is still the largest — it's one cohesive concern (the LLM pipeline) but could later split into agents / synthesis / note-markdown if it keeps growing. Left as one module for now (it's the least test-covered area, so lower-churn is safer).

---

## Suggested execution order
1 → 2 (git hygiene) · 3 → 4 (unused code, one commit) · 6 (test health) · 5a → 5b → 5c → 5d (doc archiving) · 7 (decide) · 8 (optional, later).

Verify after each code task: `source venv/bin/activate && python -m pyflakes .macro-assist/*.py .macro-assist/{portfolio,exogenous}/*.py` and `python -m pytest .macro-assist/tests -q`.
