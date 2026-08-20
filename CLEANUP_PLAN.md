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

### Task 5a — Prune the WP-19.B build-log (self-flagged)
Line ~670 is a single ~600-word build-log paragraph the doc **itself** marks:
*"Original build-log retained below for now; git + DESIGN.md are the source of truth. Safe to prune to this summary."*
**Action:** collapse it to the 3–4-line summary already sitting above it (status, what it built, KB-012-pending, kill-procedure pointer). Keep the KB refs and the "Phase-19 integration status" block.

### Task 5b — Trim completed Phase-16.A WPs
WP-16.A.1 / A.2 / A.3 / A.4 are all **Done** with results in `Knowledge_Base.md` (KB-001/002 etc.). Their multi-paragraph method/result detail (lines ~479–495) duplicates the KB.
**Action:** trim each Done WP to `status + one-line verdict + KB pointer`. Keep A.5 (open — monitoring) intact.

### Task 5c — Trim Phase-17 completed WPs
17.1–17.4 all **Done**, 17.3b **CANCELLED**, verdicts in KB-003…006 (lines ~595–603). Same treatment. Keep WP-17.5 (still "later"/open).
**Action:** trim to status + verdict + KB pointer.

### Task 5d — Archive closed phases → `Project_Development_Archive.md`
Per the convention's "when an entire phase closes, move its detail to the archive + add a table row."
- **Phase 16.A** is effectively closed bar A.5 monitoring — consider moving the design detail once A.5 resolves (judgment call; may defer).
- **Phase 19** is INTEGRATED + forward-only (only KB-012 verdict pending) — a candidate to move the design/build detail to the archive, leaving the "integration status + kill procedure" summary inline.
**Action:** for each genuinely-closed phase, cut detail to the archive and add a row to the completed-phases table (line ~411). **Do NOT archive** phases with open sibling WPs a reader still needs (Phase 20 → 20.E open; Phase 18 → 18.4/18.5 open; Phase 16.B/C open). Leave those.
**Note:** obey the convention's guardrail — *never trim before the result is in the KB, and don't remove context an open WP depends on.*

---

## Tier 4 — Test-suite health

### Task 6 — Quarantine live-data-dependent tests
4 tests fail on a clean run — **none are pure**, so they break the "no-network unit
suite" contract and produce false reds as market data / yfinance auto-adjust drift:
- `test_vol_forecast.py::test_r_squared_in_range` — downloads live `^GSPC`, asserts R²∈[0.2,0.7]; currently 0.094.
- `test_regime.py::test_historical_alignment` — downloads `^GSPC`, asserts ≥50% Risk-Off in Mar–May 2020; currently 49%.
- `test_regime.py::test_switch_count_reasonable` — downloads `^GSPC`, asserts 4–12 regime switches; currently 28.
- `test_quant_context.py::TestBuildQuantContext::test_empty_on_no_data` — **isolation leak**: expects empty output with no histories, but reads the ambient `.macro-assist/data/conditional_distributions.json` and renders a Conditional block. Not network — a fixture-isolation bug.

**Action:** (a) mark the three yfinance tests `@pytest.mark.network` (or `integration`) and register the marker in `pytest.ini` so the default run skips them / they run explicitly; (b) fix `test_empty_on_no_data` to monkeypatch `DEFAULT_TABLE_PATH` / point the data dir at a tmp path so it no longer reads real on-disk distributions.
**Done when:** default `pytest .macro-assist/tests` is fully green with no network dependence.
**Context:** the regime tests exercise the HMM layer that was **retired from the note** (KB-006) but is still used by the portfolio gate (`rebalance.live_regime`) — so keep the tests, just quarantine the live ones.

---

## Tier 5 — Judgment calls (discuss before doing)

### Task 7 — Decide the fate of the retired HMM regime code
KB-006 dropped the regime block from the daily note, but `regime.py`, `regime_features.py`, `conditional.py`, `regime_backtest.py` and `_build_regime_block` (in `quant_context.py`) all remain. `_build_regime_block` is now reachable **only** via `build_nonlive_signals_block` (the WP-18.1 payload-preview "withheld signals" view); `regime.py`/`predict_regime` is still a live dependency of the **portfolio gate** (`portfolio/rebalance.live_regime`).
**Not dead — do not auto-delete.** Decision needed: keep the preview-only `_build_regime_block` for inspection, or remove it and simplify `build_nonlive_signals_block` to fragility-only. Recommend **keep** (cheap, documents a withheld signal) unless you want the surface gone.

### Task 8 — (Optional) Split `collect_and_analyze.py` (2867 lines, 52 top-level defs)
Not urgent — no duplicate defs, minimal dead code inside. But it's ~5× the next-largest module and mixes fetching, prompt-building, LLM orchestration, and rendering. If it keeps growing, consider extracting the FRED/market/COT **data-fetch** layer and the **payload/prompt-build** layer into their own modules. Flagged for awareness only; leave unless you want to invest.

---

## Suggested execution order
1 → 2 (git hygiene) · 3 → 4 (unused code, one commit) · 6 (test health) · 5a → 5b → 5c → 5d (doc archiving) · 7 (decide) · 8 (optional, later).

Verify after each code task: `source venv/bin/activate && python -m pyflakes .macro-assist/*.py .macro-assist/{portfolio,exogenous}/*.py` and `python -m pytest .macro-assist/tests -q`.
