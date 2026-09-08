# ADR-0013 — One pipeline entry point, `needs:`-ordered, with one resolved `asof`

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | ~2026-08-28 |
| **Evidence** | The 2026-08-03 ordering failure; the UTC-midnight date bug |
| **Related** | [ADR-0012](ADR-0012-external-cron-with-backstop.md) |

## Context

Stages 1–6 used to be six separate workflows fired by six separate crons spaced
15–30 minutes apart, with the gaps holding the ordering.

The gaps did not hold it. On **2026-08-03** scoring started **34 seconds** after
the Kimi arm and both ran against the same commit — that day's Kimi note went
unscored, with every check green.

Separately, each stage derived its own run date from the wall clock. Once
scheduler delays grew past midnight UTC, a run would write the *next* day's note,
leave the intended day permanently empty, and silently skip the Monday-only
stages — all with a green run.

## Decision

**One workflow, `pipeline.yml`, is the only scheduled entry point.** Every stage
is a job in that run, ordered by `needs:` rather than by cron offsets. Stages 1–6
are reusable workflows (`workflow_call`) and carry no trigger of their own.

**The date is resolved once**, by the `plan` job, and passed to every stage as
`asof`. No stage derives its own. `plan` treats a start before 06:00 UTC as the
previous day's slot (the earliest call is 06:23, so it cannot be its own day's),
and an explicit `asof` input overrides the whole decision.

**Monday stages are selected from the weekday of the resolved `asof`**, not from
the wall clock, and are overridable via the `weekly` dispatch input.

## Consequences

- Ordering is a dependency graph, not a race.
- There is exactly one thing to check when a morning looks quiet.
- **Recovery is per-stage**: *Re-run failed jobs* re-runs only the failed stage
  and its dependents. The whole pipeline never needs re-running to fix one stage.
- Each stage keeps its own `workflow_dispatch` with its full input set, so any one
  can still be run standalone from the Actions tab.
- Almost every run now arrives as a `workflow_dispatch`, which would make the
  Actions list an undifferentiated column of identical names — so each entry point
  sets a `run-name` from its `source` input, and the list reads
  `Macro Pipeline · cron-primary`, `· cron-catchup`, `· manual` or
  `· schedule-backstop` at a glance.

## Would we revisit it?

No. The general lesson — **never let two jobs coordinate through a time gap, and
never let two jobs independently answer "what day is it"** — is broadly correct.
