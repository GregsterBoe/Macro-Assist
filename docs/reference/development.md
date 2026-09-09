# Development

Running the pipeline locally, the test suite, and version management.

Install dependencies:
```bash
pip install -r .macro-assist/requirements.txt
```

Run the daily pipeline locally:
```bash
export FRED_API_KEY=...
export ANTHROPIC_API_KEY=...
export SUPADATA_API_KEY=...   # optional
python .macro-assist/collect_and_analyze.py
```

Run a data fetch check only (no LLM call, no file writes):
```bash
export FRED_API_KEY=...
python .macro-assist/collect_and_analyze.py --fetch-only
```

Output is written to `Economy/YYYY/MM-Month/` relative to the repo root by default. Override with:
```bash
export VAULT_ROOT=/path/to/your/vault
```

Set `MACRO_PREVIEW=1` to write a payload preview to `results/llm_payload_preview/<date>.md` — a section-size index plus the verbatim user message the model receives, and the signals computed but withheld from it (shadow fragility, retired HMM regime). Useful for inspecting what data is being injected. (The daily Action sets this automatically and prints the file to its log.)

> **v1.6:** the prompt toggles below are **inert**. Every block they gated was a
> directional-call rule and those blocks are gone (WP-21.D). `run_config()` still
> resolves and records them so the frontmatter contract and the historical readers
> keep working, and `MACRO_PROFILE` still selects the model — but the A/B they
> existed for is closed (see [The cut](../concepts/the-cut.md)).

Set `MACRO_PROFILE=loosened` to run the WP-16 loosened experiment arm — Opus 4.8 main model, conviction floor OFF (all-Neutral tables allowed), base-rate-first reasoning, and hard directional-override rules pruned, all bundled. `control` (default) preserves current production behaviour (Sonnet 4.6, floor on). Individual levers can be overridden independently of the profile: `MACRO_MODEL`, `CONVICTION_FLOOR`, `BASE_RATE_FIRST`, `PRUNE_RULES`. Each note records the resolved config in frontmatter (`config:` summary + `profile`/`model`/per-lever fields), and `summarize_accuracy.py` reports a Brier/BSS A/B by profile (and by floor) once ≥2 arms have scored data.

Run scoring:

```bash
# the current scorer — the published conditional distribution (Phase 22)
python .macro-assist/score_distributions.py

# the legacy directional scorer — winding down; scores nothing on v1.6+ notes
python .macro-assist/score_predictions.py
python .macro-assist/summarize_accuracy.py
```

To score against vault reports:
```bash
export MACRO_REPORTS_DIR=/path/to/External-Brain
python .macro-assist/score_predictions.py
```

Run the quant model refit locally:
```bash
export FRED_API_KEY=...
python .macro-assist/refit_models.py
```

Run the test suite:

```bash
pytest .macro-assist/tests/
```

758 tests, ~3.5 minutes. `test_point_in_time.py` makes **real ALFRED/FRED network
calls** (~113 s) and is deliberately not marked `integration`, so it runs by
default — it is the look-ahead-leakage guard. To run offline, deselect it:

```bash
pytest .macro-assist/tests/ --deselect .macro-assist/tests/test_point_in_time.py
```

Whether to mark it `integration` is an open follow-up in the
[maintenance log](../record/maintenance-log.md).

## Version Management

Pipeline versions are centralized in `.macro-assist/versions.py`. Bump after a
**structural capability change** — a new data source, a new agent pass, a change
to what the note publishes — not for a bug fix or a refactor that leaves the
output identical:

```bash
python .macro-assist/bump_version.py v1.8 "+ what changed, one line"
python .macro-assist/tag_versions.py
python .macro-assist/summarize_accuracy.py
```

The bump script does the whole edit atomically — `PIPELINE_VERSION`, closing the
open milestone, the new entry, and the table on the
[Versioning](versions.md) page — so there is no hand-editing step to get
half-done. Pass `--start YYYY-MM-DD` when the capability goes live on a date
that is not today.

[Versioning](versions.md) is the full picture: what each stamp means, the
milestone table, and the three constants the scorers gate on.

---

