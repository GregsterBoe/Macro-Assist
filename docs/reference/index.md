# Reference

How the system works **today**. Lookup material, organised by what you are trying
to do rather than by module.

This layer describes the current state and does not narrate how it got there —
that is [Concepts](../concepts/index.md) for the reasoning and
[Record](../record/knowledge-base.md) for the evidence.

| Page | Covers |
|---|---|
| [Architecture](architecture.md) | The two repositories, the daily/weekly/refit dataflow, the full repository tree, and the `main` / `output` branch split |
| [Data sources](data-sources.md) | FRED series, market data and technicals, the quantitative intelligence layer, sector ETFs, COT, calendar, transcripts |
| [Analysis pipeline](analysis-pipeline.md) | The four Claude agents, the structured output contract, the weekly model refit, the optional portfolio module |
| [Scoring](scoring.md) | The directional scorer (frozen), the distribution scorer (live), accuracy aggregation, bias separation, and the learnability harness |
| [Operations](operations.md) | GitHub Actions workflows, the external cron trigger and its backstop, required secrets, annual maintenance |
| [Development](development.md) | Local runs, environment variables, the test suite, version management |

## Things that trip people up

**Half of what is described here is retired but still present.** The HMM regime
layer is computed and not published; `MACRO_PROFILE` and its levers resolve but
gate nothing; `score_predictions.py` runs weekly and scores nothing new; the Kimi
and exogenous arms are deactivated but intact. Each is marked where it appears,
and each is deliberate — see
[ADR-0015](../decisions/ADR-0015-soft-kill-convention.md).

**Dates before 2026-09-05 describe a different product.** The pipeline made
directional calls until v1.6. [The cut](../concepts/the-cut.md) is the bridge.

**`results/` is a git worktree, not a directory.** It lives on the orphan
`output` branch. A fresh clone has to mount it — see
[Architecture](architecture.md#branch-layout-code-vs-generated-output).
