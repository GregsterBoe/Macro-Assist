# ADR-0001 — Generated output lives on an orphan `output` branch

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | ~2026-08 |
| **Evidence** | Operational |
| **Related** | [Architecture](../reference/architecture.md#branch-layout-code-vs-generated-output) |

## Context

The pipeline writes a note every weekday, plus score files, quant-context logs
and harness artifacts. Committing all of that to `main` would bury the code
history under thousands of generated commits and make `git log` useless for the
thing it is actually for.

## Decision

Code lives on `main`. All generated output under `results/` lives on a separate
**orphan** branch, `output`, mounted at `results/` as a **git worktree**.

Scripts read and write `<repo>/results/` exactly as before and know nothing about
the split; `main` gitignores the directory. CI mounts it with
`ci_mount_output.sh` before a run and publishes with `ci_publish_results.sh`
after. Locally it is `./publish_output.sh "msg"`.

## Consequences

- `main`'s history is code-only and readable.
- The vault and any consumer can pull `output` independently of code changes.
- **A fresh clone has no `results/`** and must run
  `git fetch origin output && git worktree add results output`. This is the one
  real cost and it surprises everyone exactly once.
- Model artifacts (`.macro-assist/data/*.pkl`, `*.json`) deliberately stay on
  `main` — they are inputs, not output.

## Would we revisit it?

Only if the worktree step proved to be a recurring stumbling block for more than
one person. It has not.
