# Operations

Running the thing: workflows, the external cron trigger, secrets, and annual
maintenance.

## GitHub Actions workflows

### pipeline.yml — the entry point (Mon–Fri 06:23 UTC, catch-up 10:47 UTC)

The single entry point, started by an
[external cron service](#external-cron-trigger). Its only `schedule:` is a late
backstop for the day the cron service itself fails. Every stage below is a **job** in this one run, ordered by `needs:` rather
than by cron offsets.

Stages 1–6 used to be six separate workflows fired by six separate crons spaced
15–30 min apart. GitHub's scheduler routinely fires 45–220 min late (measured
peak: 372 min on 2026-06-15) and drops runs entirely under load (2026-08-27:
nothing ran at all), so the gaps never reliably held the order. On 2026-08-03
scoring started 34 s after the kimi arm and both ran against the same commit —
that day's kimi note went unscored with every check green.

**Recovering a failed stage:** use *Re-run failed jobs* on the run. Only the
failed stage and the stages downstream of it re-run; completed stages are
skipped. You never need to re-run the whole pipeline to fix one stage.

**Catch-up run:** the 10:47 call re-enters the same pipeline. Stages no-op when
their output for the date already exists, so on a normal day it writes nothing
and costs about a minute per stage; on a day the morning call never landed — the
cron service was down, the token had expired, GitHub returned a 5xx — it fills
the gap unattended.

**The run's date** is resolved once by the `plan` job and passed to every stage
as `asof`; no stage derives its own. This matters because the delay above keeps
growing — on 2026-08-28 the two slots landed 12h25m and 10h28m late, both in the
evening. When a stage read the clock itself, a run that crossed UTC midnight
wrote the *next* day's note and left the intended day permanently empty, and the
Monday-only stages vanished, all with a green run. An external caller is prompt where GitHub's scheduler was not, but a retry after
an outage still lands late, so the guard stays: `plan` treats a start before
06:00 UTC as the previous day's slot (the earliest call is 06:23, so it cannot be
its own day's), and the `asof` input overrides the whole decision.

**Monday stages** (3, 5, 6) are selected by the `plan` job from the weekday of
that resolved `asof` — not from the wall clock — and are overridable via the
`weekly` dispatch input.

Each stage also keeps its own `workflow_dispatch` with its full input set, so any
one of them can still be run standalone from the Actions tab.

### macro_data_check.yml — stage 1

Runs before the daily note as an early warning. Calls `collect_and_analyze.py --fetch-only` — no LLM, no file writes. Checks all data sources and exits non-zero if any critical source fails.

Does not require `ANTHROPIC_API_KEY` or `VAULT_PAT`.

### macro_daily.yml — stage 2

1. Checkout Macro-Assist (write token) + External-Brain vault
2. Install Python dependencies
3. Run `collect_and_analyze.py` (fetch → analyze → write note to vault)
4. Copy note to `results/` in Macro-Assist and commit back

### macro_weekly_scoring.yml — stage 3 (Mondays)

Ordered after the daily note and both arm stages by `needs:`, so the week's
predictions are always committed before they are scored.

1. Checkout Macro-Assist + vault
2. Run `score_predictions.py` — **legacy**, winding down; deletable as a step once
   the last T+20 window resolves (~2026-10-02) and the run prints
   `DIRECTIONAL RECORD CLOSED`. Removing the *step* only — stage 3 itself is
   permanent, because `score_distributions.py` runs there.
3. Run `score_distributions.py` — the current scorer (Phase 22)
4. Run `summarize_accuracy.py`
5. Commit `accuracy_summary.json` to Macro-Assist
6. Copy `accuracy_report.md` to vault (`Economy/Analysis/prediction-accuracy.md`)

### macro_weekly_refit.yml — Sunday 22:00 UTC

Its own cron call rather than a pipeline stage: it has no upstream dependency and
runs the night before Monday's pipeline, which picks up the fresh models. A
missed refit is not silent-but-fatal the way a missed daily note is — the models
just stay a week old and the next Sunday call refreshes them — so it has no
catch-up call.

1. Checkout Macro-Assist
2. Run `refit_models.py` (5yr FRED + market data fetch, HMM refit, distribution rebuild)
3. Commit `data/regime_model.pkl` + `data/conditional_distributions.json`

All workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. Cron calls dispatch `ref: main`, and the backstop schedule (like every GitHub schedule) runs on the default branch, so everything executes against `main`.

Stages 1–6 are reusable workflows (`workflow_call`) and carry no trigger of their own — `pipeline.yml` is the only scheduled entry point in the chain, so there is exactly one thing to check when a morning looks quiet.

Almost every run now arrives as a `workflow_dispatch`, which would otherwise make the Actions list an undifferentiated column of identical names. Each entry point sets a `run-name` from its `source` input, so the list reads `Macro Pipeline · cron-primary`, `· cron-catchup`, `· manual`, or `· schedule-backstop` at a glance.

---

## External cron trigger

GitHub's `schedule:` no longer starts the pipeline. An external cron service
does, by calling the workflow-dispatch API. `pipeline.yml` keeps one late
`schedule:` purely as a [backstop](#the-backstop); `macro_weekly_refit.yml` has
none.

**Why.** The scheduler was measured, not guessed: runs delivered 42–224 min late
through July/August 2026, peaking at 372 min on 2026-06-15; 12h25m and 10h28m
late on 2026-08-28; and on 2026-08-27 the day's schedules were dropped entirely
and nothing ran at all. Late delivery is what forced the `asof` plumbing (a run
crossing UTC midnight used to write the *next* day's note), and a dropped run is
worse than a failed one — there is no red check, just a silent gap in the series.
An external call is delivered when it is made, and when it fails it fails in the
caller's log where it can be alerted on.

### The schedule

All times UTC — set the cron service's timezone to UTC so the slots don't move
twice a year.

| Slot | Cron (UTC) | Call |
|---|---|---|
| Daily pipeline | `23 6 * * 1-5` | `pipeline.yml`, `source=cron-primary` |
| Catch-up | `47 10 * * 1-5` | `pipeline.yml`, `source=cron-catchup` |
| Weekly refit | `0 22 * * 0` | `macro_weekly_refit.yml`, `source=cron-refit` |

The catch-up is not a duplicate run: stages no-op when their output for the date
already exists, so it costs about a minute per stage and writes nothing unless
the morning call is missing. The odd minutes carry over from the old crons and no
longer matter — GitHub's contended `:00`/`:15`/`:30`/`:45` slots only affected its
own scheduler — but there is no reason to move them.

### The backstop

Moving off GitHub's scheduler moves the single point of failure rather than
removing it: if the cron service is down, its host is off, or the token has
expired, nothing calls the workflow at all. GitHub's scheduler is unreliable,
not dead — a late slot it *usually* delivers is worth having behind a caller
that might never fire.

So `pipeline.yml` keeps exactly one `schedule:`, at **14:37 UTC, Mon–Fri**. It is
not the trigger and is not meant to be on time: both external calls have long
since landed by then, so on a normal day it finds the date's output already
written and every stage no-ops — about a minute per stage, nothing committed. It
only does real work on a day nothing else called.

It sends no inputs (a schedule trigger can't), so `plan` labels it
`schedule-backstop` in the run name and the summary. If GitHub delivers *it* late
too, the date guard still holds: past midnight it resolves to the previous day —
correct, that is the day the run is for — and in the morning it resolves to the
new day, which the primary call has usually already written, so it no-ops. Either
way it cannot write the wrong day's note.

`macro_weekly_refit.yml` gets no backstop: a missed refit leaves the models a
week old and the next Sunday call refreshes them.

### The token

A **fine-grained PAT**, scoped to this repository only, with **Actions: read and
write** (plus the automatic Metadata: read). Nothing else — the token itself
cannot read the repo's secrets or push commits.

This token lives in the cron service, not in GitHub secrets: it is the credential
for getting *into* GitHub, so it cannot be stored behind the thing it opens.
Fine-grained PATs expire — note the expiry date somewhere you will see it, since
the symptom of an expired token is a `401` in the cron service's log and an
otherwise silent morning here.

### Setting it up

**On a host with a shell** (a VPS, a NAS, a Raspberry Pi) — `trigger_pipeline.sh`
in the repo root is the caller; it retries transport failures, GitHub 5xx and
rate limits with backoff, and explains the auth errors it will not retry:

```cron
# crontab -e, with MACRO_ASSIST_TOKEN exported for cron (e.g. in the crontab itself)
23 6  * * 1-5  /path/to/Macro-Assist/trigger_pipeline.sh --source cron-primary
47 10 * * 1-5  /path/to/Macro-Assist/trigger_pipeline.sh --source cron-catchup
0  22 * * 0    /path/to/Macro-Assist/trigger_pipeline.sh --workflow macro_weekly_refit.yml --source cron-refit
```

**On an HTTP-only service** (cron-job.org, EasyCron, Zapier, a Cloudflare Worker)
— configure one job per row of the table above:

```
POST https://api.github.com/repos/GregsterBoe/Macro-Assist/actions/workflows/pipeline.yml/dispatches

Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{"ref": "main", "inputs": {"source": "cron-primary"}}
```

Swap `pipeline.yml` for `macro_weekly_refit.yml` in the URL for the refit slot.
Send input values as **strings** (`"force": "true"`, not `true`) — GitHub coerces
them to the type the workflow declares. Any input the workflow exposes can be
passed the same way: `asof`, `force`, `pf_reset`, `weekly`. (`kimi_n` was removed
with the kimi stage in WP-21.F.)

### Checking it works

```bash
./trigger_pipeline.sh --dry-run --source cron-primary   # prints the request, sends nothing
MACRO_ASSIST_TOKEN=github_pat_... ./trigger_pipeline.sh --source manual-test
```

A `204 No Content` means GitHub accepted the request — not that the run
succeeded. The run then appears in the Actions tab named for its `source`, and
the `plan` job's summary repeats the source and the resolved `asof`.

| Symptom | Cause |
|---|---|
| `401` | Token invalid or expired — issue a new fine-grained PAT. |
| `403` | Token lacks *Actions: read and write* on this repo. |
| `404` | No such workflow with a `workflow_dispatch` trigger on `ref`, or the token cannot see the repo. The trigger must exist on the **default branch** — a workflow that only has it on a feature branch is not dispatchable. |
| `422` | Unknown input name or bad value. |
| No run at all, no error | The call was never made. This is the cron service's log to check, not GitHub's — turn on its failure notifications. The 14:37 backstop should have covered the day; if it didn't, GitHub dropped that slot too. |

---

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `FRED_API_KEY` | [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `VAULT_PAT` | GitHub Personal Access Token with `repo` scope (for pushing to External-Brain) |
| `VAULT_REPO` | External-Brain repo name, e.g. `GregsterBoe/External-Brain` |
| `SUPADATA_API_KEY` | [Supadata API key](https://supadata.ai) for YouTube transcripts (optional) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions. The workflows require `permissions: contents: write`, enabled in the workflow files and under repo Settings → Actions → General → Workflow permissions → Read and write.

COT positioning data is fetched directly from `cftc.gov` — no API key required.

The external cron token is deliberately **not** in this table: it lives in the cron service, not in GitHub secrets (see [External cron trigger](#external-cron-trigger)).

---


## Annual Maintenance

| Task | When | Where |
|------|------|-------|
| Update FOMC meeting dates | Every January | `FOMC_DATES` list in `collect_and_analyze.py` |
| Review sector ETF top holdings | Every quarter | `SECTOR_HOLDINGS` dict in `collect_and_analyze.py` |
| Renew the external cron PAT | Before it expires | GitHub → Settings → Developer settings → Fine-grained tokens, then update the cron service |

FOMC dates source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

---

