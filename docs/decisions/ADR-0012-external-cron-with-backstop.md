# ADR-0012 — An external cron service triggers the pipeline; GitHub's scheduler is a backstop

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | ~2026-08-28 |
| **Evidence** | Measured scheduler latency and dropped runs, Jun–Aug 2026 |
| **Related** | [ADR-0013](ADR-0013-one-pipeline-entry-point.md) · [Operations](../reference/operations.md#external-cron-trigger) |

## Context

GitHub Actions' `schedule:` trigger was measured, not guessed:

- 42–224 minutes late through July and August 2026.
- **372 minutes late** on 2026-06-15.
- **12h25m and 10h28m late** on 2026-08-28, both landing in the evening.
- On **2026-08-27 the day's schedules were dropped entirely** and nothing ran.

Late delivery is what forced the `asof` plumbing — a run crossing UTC midnight
used to write the *next* day's note and leave the intended day permanently empty.
A dropped run is worse than a failed one: there is no red check, just a silent gap
in the series.

## Decision

An **external cron service** calls the workflow-dispatch API. `trigger_pipeline.sh`
is the caller, with backoff on transport failures, GitHub 5xx and rate limits.

`pipeline.yml` keeps **exactly one** `schedule:`, at 14:37 UTC Mon–Fri, purely as
a backstop. `macro_weekly_refit.yml` keeps none.

The credential is a fine-grained PAT scoped to this repository with **Actions:
read and write** and nothing else. It lives **in the cron service, not in GitHub
secrets** — it is the credential for getting *into* GitHub, so it cannot be stored
behind the thing it opens.

## Consequences

- An external call is delivered when it is made, and when it fails it fails in the
  caller's log, where it can be alerted on.
- **This moves the single point of failure rather than removing it.** If the cron
  host is off or the token expired, nothing calls the workflow at all — hence the
  backstop. GitHub's scheduler is unreliable, not dead, and a late slot it
  *usually* delivers is worth having behind a caller that might never fire.
- The backstop is not meant to be on time. On a normal day both external calls
  have long since landed, every stage no-ops, and it costs about a minute per
  stage.
- **Fine-grained PATs expire.** The symptom is a `401` in the cron service's log
  and an otherwise silent morning here. Renewal is on the annual maintenance list.
- The catch-up call at 10:47 is not a duplicate: stages no-op when their output
  for the date already exists, so it writes nothing unless the morning call is
  missing.

## Would we revisit it?

Only if GitHub's scheduler became reliable, which is not something to bet a daily
series on. The backstop already hedges the reverse direction.
