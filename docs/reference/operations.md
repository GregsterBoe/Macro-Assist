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

### Re-running a day just to validate the data

`pipeline.yml` takes a `mode` input. `full` (the default, and what the cron
caller sends) is the whole pipeline. **`validate` runs `plan` and stage 1 only**
— every fetch, every source and the fragility vol legs — and writes nothing: no
LLM call, no note in the vault, no commit to `main` or `output`, not even a
quant-log line. It is how you ask *is the data good yet?* on a day whose note
has already been written.

Before it existed the only answer was `--force` on a full run, which costs an
LLM call and overwrites a published note to learn one fact.

| | `mode: full` | `mode: validate` |
|---|---|---|
| plan, stage 1 data check | runs | runs |
| stages 2–5 | run | **skipped** |
| a dead fragility vol leg | `WARN` — never blocks the note | **fails the run** |
| writes | note, vault, `output`, `main` | nothing |

Every stage that writes carries the `mode != 'validate'` guard **explicitly**,
and that is not belt-and-braces: `refit` is deliberately not gated on
`scoring.result` (a failed note must not stop the models being rebuilt) and
`!cancelled()` lets a job run after a *skipped* dependency, so skipping stage 2
alone would still let a Monday validate run commit a refit to `main`.
`test_pipeline_modes.py` asserts the guard on each of the four.

Dispatch it from the Actions tab on `Macro Pipeline` → Run workflow → mode
`validate`. The run is labelled `· VALIDATE (no note)` in the run list so it
cannot be mistaken for a real one. Stage 1 is also dispatchable on its own
(`Data Fetch Check`, with the same `strict_feeds` toggle), but prefer the
pipeline: one entry point (ADR-0013).

### macro_data_check.yml — stage 1

Runs before the daily note as an early warning. Calls `collect_and_analyze.py --fetch-only` — no LLM, no file writes. Checks all data sources and exits non-zero if any critical source fails.

Since IMP-5.4 it also checks the **fragility vol legs** — the one source it
could not see before. `vix_term` went missing on 2026-09-16 and this stage
stayed green for three days, because `build_quant_context()` succeeds perfectly
well with a degraded composite. It now runs the same probe as
`feed_audit.py --probe` (one implementation, not two) and reports each leg's
source, staleness and error. `--strict-feeds` promotes that from `WARN` to a
failure; `mode: validate` is what passes it.

Does not require `ANTHROPIC_API_KEY` or `VAULT_PAT`.

### macro_daily.yml — stage 2

1. Checkout Macro-Assist (write token) + External-Brain vault
2. Install Python dependencies
3. Run `collect_and_analyze.py` (fetch → analyze → write note to vault)
4. Copy note to `results/` in Macro-Assist and commit back

The fragility feed gate is **not** a step here — see `feed_gate` below.

### feed_gate — the fragility feed gate (IMP-5.4, [KB-034])

Its own job in `pipeline.yml`, `needs: [plan, daily]`. It exits non-zero when
the Fragility Monitor has been `Unavailable` for more than two consecutive
readings, turning the run red and sending the notification GitHub already sends
for a failed run. One degraded day stays a `WARN` — a vendor hiccup that
self-heals, and an alarm on day one would cry wolf. Two in a row is a feed that
is not coming back on its own, the shape both the 2026-07 and 2026-09 outages
had.

**Why a job and not a step of stage 2.** It shipped as the daily stage's last
step, reasoning that the note is already written and published by then, so a red
gate "costs nothing but a notification". That was wrong, and a Monday would have
proved it: a failing step fails the job, `scoring` requires
`needs.daily.result == 'success'`, and `rebalance` requires `scoring` — so a
dead vol feed would have skipped the week's scorecard and the paper-portfolio
rebalance, neither of which touches the vol legs. As a sibling job it still
reddens the run while `daily.result` stays `success` and every weekly stage
proceeds. `test_pipeline_modes.py` pins the shape.

It needs no `pip install`: `feed_audit.audit()` is stdlib plus
`pipeline_common`, and the probe imports (pandas, yfinance) are function-local.
It does mount `results/`, since the readings it audits live on the output branch.

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

### macro_weekly_refit.yml — stage 5 (Mondays)

A pipeline stage since 2026-09-11, ordered after `scoring` and [running last on
purpose](#everything-rides-one-call). Until then it had its own Sunday cron call
on the reasoning that it has no upstream dependency; that call was the one thing
the rebuilt cron never reached, and the table froze for eleven days. Still
dispatchable standalone, which is how a one-off refresh is done between Mondays.

1. Checkout Macro-Assist
2. Run `refit_models.py` (FRED + market data from 2000-08, distribution rebuild; HMM refit only if re-enabled)
3. Commit `data/regime_model.pkl` + `data/conditional_distributions.json`

### docs.yml — the documentation site

Independent of the pipeline. Renders `docs/` with MkDocs Material on any push to
`main` that touches `docs/`, `mkdocs.yml`, or the workflow itself, and publishes
the result to GitHub Pages. Pull requests build but do not deploy: `mkdocs build
--strict` fails on a broken internal link, so a doc move that leaves a dangling
reference is caught in review.

### record_audit.yml — the record audit

Independent of the pipeline. Runs `.macro-assist/record_audit.py` on every push
to `main` and every pull request, then its tests. The audit reads the workflows,
the docs and the git history and exits non-zero on a red finding; it writes
nothing. What it checks is listed in the script's header and grows with Phase
24; today it is the workflow-orphan rule [above](#everything-rides-one-call)
the [artifact-liveness rule](#a-reachable-stage-that-produces-nothing), the
[referential-integrity rule](#the-identifiers-that-are-not-links), the
[contradiction rule](#a-claim-the-repo-makes-twice-differently) and the
[ADR revisit rule](#a-decision-whose-condition-may-have-come-true) below,
plus the [ages table](#the-ages-computed), which is printed and never fails.
It is the only CI job that runs any of the test suite — the pipeline
stages do not, and `docs.yml` only renders. It checks out with
`fetch-depth: 0` because the liveness rule, the ages table and the revisit
rule read commit dates and the ADR numbering rule reads deletions; on a
shallow clone the audit refuses rather than passing vacuously.

**Publishing requires Pages to be switched on once**, by a repo admin, in one of
two ways. *Done on this repo 2026-09-12* — the recipes below are kept for a fresh
fork, and for the case where the setting is ever reverted.

*In the browser:* **Settings → Pages → Build and deployment → Source: "GitHub
Actions"**.

*Over the API*, which is the way out when that settings page 404s or the
dropdown will not stick. It needs a token with admin on the repo — a classic PAT
with `repo`, or a fine-grained one with *Pages: read and write*:

```bash
# create the Pages site with source "GitHub Actions" (201 = done)
curl -X POST -H "Authorization: Bearer $PAT" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/GregsterBoe/Macro-Assist/pages \
  -d '{"build_type":"workflow"}'

# if it answers 409 the site already exists on a branch source; switch it
curl -X PUT ...same headers... \
  https://api.github.com/repos/GregsterBoe/Macro-Assist/pages \
  -d '{"build_type":"workflow"}'      # 204 = done

# confirm
curl -H "Authorization: Bearer $PAT" \
  https://api.github.com/repos/GregsterBoe/Macro-Assist/pages | jq .build_type
```

Storing that same token as the repository secret `PAGES_ADMIN_TOKEN` hands the
job to the workflow: the deploy preflight creates the site, or switches it off a
branch source, on the next run. The default Actions token cannot do either —
creating a Pages site is an admin-level API call and `GITHUB_TOKEN` is not a repo
admin, so `actions/configure-pages` with `enablement` returns *Resource not
accessible by integration* whatever `permissions:` grants. Until Pages is on, the
preflight fails with these instructions rather than letting
`actions/deploy-pages` report a bare 404.

All workflows support `workflow_dispatch` for manual testing from the GitHub Actions UI. Cron calls dispatch `ref: main`, and the backstop schedule (like every GitHub schedule) runs on the default branch, so everything executes against `main`.

Stages 1–6 are reusable workflows (`workflow_call`) and carry no trigger of their own — `pipeline.yml` is the only scheduled entry point in the chain, so there is exactly one thing to check when a morning looks quiet.

Almost every run now arrives as a `workflow_dispatch`, which would otherwise make the Actions list an undifferentiated column of identical names. Each entry point sets a `run-name` from its `source` input, so the list reads `Macro Pipeline · cron-primary`, `· cron-catchup`, `· manual`, or `· schedule-backstop` at a glance.

---

## External cron trigger

GitHub's `schedule:` no longer starts the pipeline. An external cron service
does, by calling the workflow-dispatch API. `pipeline.yml` keeps one late
`schedule:` purely as a [backstop](#the-backstop).

**`pipeline.yml` is the only thing the cron calls.** That is the whole trigger
surface: anything not reachable from it does not run on a schedule at all. It was
not always true — the weekly refit had a Sunday call of its own until 2026-09-11,
and losing it is [why the refit is now a stage](#everything-rides-one-call).

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

Two calls, one workflow. There is **no separate weekly slot**: the Monday-only
stages — scoring, rebalance and the model refit — are jobs inside `pipeline.yml`,
gated on `plan.outputs.weekly`, which the `plan` job derives from the as-of date
(`date -u +%u = 1`). So the weekly work rides the same weekday call as the daily
note; there is nothing extra to schedule and nothing extra to forget.

The catch-up is not a duplicate run: stages no-op when their output for the date
already exists, so it costs about a minute per stage and writes nothing unless
the morning call is missing. The odd minutes carry over from the old crons and no
longer matter — GitHub's contended `:00`/`:15`/`:30`/`:45` slots only affected its
own scheduler — but there is no reason to move them.

### Everything rides one call

Because the cron calls only `pipeline.yml`, the `needs:` graph *is* the schedule.
What runs:

| | Runs | On |
|---|---|---|
| `plan` → `data_check` → `daily` | every weekday | the cron call |
| `scoring` (both scorers) · `rebalance` · `refit` | Mondays | `plan.outputs.weekly` |

And what does **not** run on any schedule — dispatch-only, by choice:
`numeric_baseline.yml` (WP-21's harness, run per experiment), `exo_slice_smoke.yml`
and `kimi_arm_smoke.yml` (both arms soft-killed, [ADR-0015](../decisions/ADR-0015-soft-kill-convention.md)),
and `macro_weekly_refit.yml` standalone, which is how a one-off refresh is done
between Mondays. `docs.yml` and `record_audit.yml` trigger on pushes and pull
requests, so they need no schedule.

**The rule this section exists to state: a new scheduled thing is a new stage,
not a new cron entry.** The weekly refit was the counter-example. It had its own
Sunday call at `0 22 * * 0`, deliberately *not* a pipeline stage, on the
reasoning that it has no upstream dependency. When the cron was rebuilt to call
only `pipeline.yml`, that made it the one scheduled thing nothing reached. The
conditional table froze at **2026-08-31**; no run failed, no check went red, and
the six-asset universe [WP-22.A](../record/roadmap.md) had already shipped simply
never landed — the table kept serving three assets and the note kept printing
"no conditional base rate" for the other three. It was found by reading commit
dates, not from an alert.

**The rule has a detector since 2026-09-14.** `record_audit.py` (WP-24.A) fails
CI on a workflow with its own `schedule:`, on a `workflow_call` workflow no
pipeline stage reaches unless it is pinned soft-killed
([ADR-0015](../decisions/ADR-0015-soft-kill-convention.md)), on a stage without
`needs:`, and on a row of the schedule table above that calls anything but
`pipeline.yml`. What it cannot see is the external service itself — a slot the
service has and the table does not, or the reverse, which is exactly how the
refit froze — so the table is the declaration the audit holds you to, and the
artifact's age in git ([below](#a-reachable-stage-that-produces-nothing)) is
the backstop for the gap it cannot close.

That is the same dropped-run failure that moved this project off GitHub's
scheduler in the first place, arriving through a different door: not a late run
or a red check, just a silent gap. "No upstream dependency" is an argument for
being independently *runnable*, not for being independently *triggered* —
[ADR-0013](../decisions/ADR-0013-one-pipeline-entry-point.md)'s point, which the
refit was the exception to until it broke.

The refit is stage 5 and **runs last on purpose.** It commits
`conditional_distributions.json` and `regime_model.pkl` to `main`, while every
stage's `actions/checkout` resolves to `github.sha` — the commit that triggered
the run. A stage ordered after it would still hold the pre-refit working tree, so
moving it first would look correct and change nothing. The fresh table therefore
takes effect on the *next* pipeline run, a one-business-day lag on a weekly refit
of slow macro series. That is point-in-time safe either way: a table fit at a
prior date is exactly what `score_distributions.py` assumes it is reading.

### A reachable stage that produces nothing

The other half of the detector (WP-24.B, same day). `record_audit.py` carries a
registry, `ARTIFACTS`, of every live track's output — the path, the branch the
stage pushes it to, and the cadence it is owed — and fails CI when the
artifact's **last-changed commit** is older than that cadence plus a day of
grace:

| Artifact | Branch | Written by | Red after |
|---|---|---|---|
| `.macro-assist/data/conditional_distributions.json` | `main` | stage 5 · weekly refit | 8 days |
| `.macro-assist/data/accuracy_summary.json` | `main` | stage 3 · weekly scoring | 8 days |
| `dist_scores_summary.json` | `output` | stage 3 · weekly scoring | 8 days |
| `*/*-macro.md` — the note, any month | `output` | stage 2 · daily note | 4 days |

Three things about how it reads are deliberate. The date is the **commit
date**, never the file's mtime — a fresh clone stamps every file with the
clone time and would pass for ever. It reads `origin/<branch>` when that ref is
fetched and the local branch otherwise, never `HEAD` — a pull request cut two
weeks ago does not carry the refits that landed since and must not fail for
them. And a **shallow clone is refused**: at depth 1 every path's last commit
is the clone boundary, which is the mtime problem in another coat.

The pairing with the workflow rule is the point. The workflow rule catches a
stage the repo cannot reach; this one catches a stage that is reachable and
yet produces nothing — including the case the workflow rule is blind to by
construction, a dispatch-only workflow whose external caller went away. The
frozen refit was that second kind. Replayed against the real history
(`--now 2026-09-08`), this rule goes red on day nine, three days before the
freeze was found by reading commit dates.

### An artifact that lands and is unusable

The shape neither rule above can see, and the one that cost three days in
September 2026 ([KB-034]). The Fragility Monitor's `vix_term` leg went missing
on 2026-09-16 and the composite published `Unavailable` — no calibrated label —
on the 16th, the 17th and the 18th. Nothing was late: the note was written each
day, the artifact landed on time, every workflow was reachable, and the liveness
rule above was satisfied by a file that exists. The only sign was a `WARN` line
in a passing Action, which is to say no sign at all.

So a dedicated pipeline job, `feed_gate`, reads the readings back out of
`results/quant_context_log/` and goes red on a *streak* of degraded ones
(`feed_audit.py`, above). It is deliberately not part of `record_audit.py`: that
script runs on push and pull request, and a feed that dies on a Wednesday with
no commits that week would wait for someone to push before anything noticed. A
daily failure needs a daily runner, and the pipeline is the only thing in this
repo that runs every day.

The gate reports the cause the failing run recorded, which is nothing for a
reading written before the instrumentation existed. To ask the feeds
themselves — why is `vix_term` missing *right now* — run
`python .macro-assist/feed_audit.py --probe`: it fetches the vol legs, prints
each leg's source, staleness and error, and names the reason the term structure
cannot be computed. It costs network, so it is opt-in and never part of the gate.

A track that stops is red here until its registry entry is removed — on
purpose, the same shape as a soft-kill pin. `accuracy_summary.json` is the
first one due: it keeps landing after the directional scorer's closure banner
(~2026-10-02) because `summarize_accuracy.py` rewrites it weekly; if that step
is ever retired, retire the entry with it.

`python .macro-assist/record_audit.py --now 2026-09-08` reads ages — the
artifacts' and the [record's](#the-ages-computed) — and the
[ADR revisit conditions](#a-decision-whose-condition-may-have-come-true) as
of a date, seeing only commits up to it, so a past week can be replayed
honestly.

### The identifiers that are not links

`mkdocs build --strict` fails on a broken *link*. The record also cites by
identifier — `[KB-024]`, `ADR-0013`, `WP-24.C`, `` `todo.md` #26 `` — and a
dangling one renders fine. `check_referential_integrity` (WP-24.C) reads every
page under `docs/` and `CLAUDE.md` and goes red on:

| Identifier | Must resolve to |
|---|---|
| `KB-###` | a `## KB-###` heading in `knowledge-base.md` |
| `ADR-####` | a file in `docs/decisions/`; the files are numbered contiguously from 0001, one per number, and none has been deleted in `HEAD`'s history (convention #11 — a slug rename keeps its number and is fine) |
| `WP-##.x` | any mention in `roadmap.md` or `roadmap-archive.md` — the two files that define work packages |
| `todo.md #N` | an item heading in `todo.md`; if it heads a `RESOLVED` entry in `resolved.md` instead the pointer still lands and the finding is **report-only**, one line per page, for the next housekeeping pass |
| `resolved.md #N` | a `RESOLVED` / `DONE` heading in `resolved.md` |

And on the inbox's own shape: one number, one open item; no number that heads
an open item *and* a resolved one. The inbox numbered per section until
2026-09-11 and carried two open `#7`s from 09-08 to 09-13 — replayed, the
check is red on every one of those trees.

Two pins, each held exactly (a pin whose condition has gone is itself red):
`RESERVED_KB_NUMBERS` for KB-008, reserved for an A/B the cut made moot and
named in the KB's prose without an entry; `KNOWN_ITEM_COLLISIONS` for `#7`,
the one number the inbox and `resolved.md` both hold — Phase 22's open
decision and the carried accuracy finding closed as "#7 (carried)".

### A claim the repo makes twice, differently

`CLAUDE.md` says who wins when two docs disagree about status — the board —
and until 2026-09-21 nothing checked whether they did. `check_contradictions`
(WP-24.D) reads every place the record states a **phase's** status and goes
red when they are not one class:

| Source | Where the status is read |
|---|---|
| `active-experiments.md` | every `### …` heading and every `- **…**` bullet whose bold span names `Phase N`; the first status marker after the name |
| `roadmap.md` | the `## … (Phase N) …` heading, and the phase's row in the phase table; the first marker in each |
| `CLAUDE.md` | every `Phase N` in the **Current state** table; the status *word* in the clause after the name (up to the next `;`, `.`, `\|` or `Phase N`, with parenthesised and backticked spans removed first). No word means the row calls the phase current |

The classes are the record's own markers: 🟢 🟡 🔍 are **open**, ⏸ is
**dormant**, ✅ ❌ are **closed**. `🟢 SHIPPED` beside `🟡 IN PROGRESS` is
one claim worded twice; `🟡 IN PROGRESS` beside `⏸ Draft` is two claims. A
heading with no marker claims nothing. The same rule holds the table's
**Version** row to `versions.py` — `bump_version.py` does not edit
`CLAUDE.md`. Work packages are out of scope on purpose: the board files
`WP-21.E` as ✅ for family 1 and ⏸ for families 2–3, which is right and would
read as a contradiction to a check that only sees the identifier.

The finding prints every claim with its `file:line` and **takes no side** —
red only insists that someone applies the precedence rule (`resolved.md`
#23). A disagreement kept on purpose is pinned in `KNOWN_CONTRADICTIONS`,
subject → the open `todo.md` item that carries it; the pair is still printed,
report-only, and the pin is held exactly: a pinned phase whose sources agree
again, or whose item is not open, is red.

**Found on the first run**, 2026-09-21: the roadmap's phase table still said
`⏸ Draft` for Phase 24 a week after the board, the roadmap's own heading and
`CLAUDE.md` said in progress — through the 24.A, 24.B and 24.C passes, each of
which edited the file. Replayed on every record commit since 2026-09-13 the
check is red from 2c47688 (24.B shipped, 09-14) to HEAD, and for two commits
on 09-14 (6bd8310, 7107428) on Phase 23, whose roadmap heading said `⏸ DRAFT`
after the board had it at 🔍 with the harness run. Both fixed by hand; the
pin table is empty.

### The ages, computed

`todo.md` carries a hand-written `Last reviewed:` line. On 2026-09-21 it said
2026-09-14; the file had been edited on 09-18. The audit prints, on every run,
what that line is trying to say — **the days since each open `todo.md` item
and each board row was last edited**, oldest first (WP-24.E):

```
ages — days since last edit, oldest first (WP-24.E; never red):
    17.1  board: IMP-4 — OR-of-channels fragility flag        2026-09-04  d80054b WP-21.F/G: stand down …
    12.9  todo.md #7 — Target Range: nominal coverage, and …  2026-09-08  890c248 WP-22.C: the pre-registered bar …
    10.2  todo.md #11 — optional further split of `llm_ana…   2026-09-11  05b432c Split todo.md, and make it the single inbox …
     3.1  todo.md #26 — the vol term structure's feed: ret…   2026-09-18  7cc1f78 Find the vix_term cause …
```

| Row | Its text |
|---|---|
| `todo.md #N` | every `### … #N` heading, through the line before the next numbered `###` or any `##` — an unnumbered sub-heading stays with its item |
| `board: …` | every `###` section under **Active** and every `- **…**` bullet under **Queued / dormant**, with its continuation lines; named by the heading up to its first status marker |

The date is per line from `git blame`, so a row's age is its **youngest
line's** — the commit named is the one that last touched any part of it.
Whitespace-only changes and blocks moved within the file are not edits
(`-w -M`); a line moved in from another file is one, which is why nothing in
the table predates the record's consolidation (`todo.md` was split out on
2026-09-11, the board restructured on 09-08). An uncommitted edit is zero days
old and says `uncommitted`. The changelog table and **Recently closed** are
not rows — a closed row is finished, not stale. `--now` blames the file as it
stood at that date, so the table replays like the artifact ages do; before
the file existed at its current path it is empty.

**Never red** — `resolved.md` #23 draws the line: an old item breaks no rule.
Replayed to 2026-09-13, the table led with the carried `#7`, `#4` and `#5` at
19 days, and the 2026-09-14 pass closed the first two by hand; they had led
it since the inbox was split out. `/orient` (WP-24.G) prints it at turn 1.

### A decision whose condition may have come true

Every ADR ends with **"Would we revisit it?"** — part 4 of the page shape in
[`decisions/index.md`](../decisions/index.md#adding-a-decision), a *condition*
rather than a date. `check_adr_revisit` (WP-24.F) enforces the section it
already had (`resolved.md` #24) and watches the part of it a machine can read:

| | What is read | Finding |
|---|---|---|
| **Presence** | every ADR whose **Status** row does not say *Superseded* has a `## Would we revisit it?` heading with text under it | **red** — the sibling of convention #11's *"a page with no costs listed has not been thought through"*. A reasoned **"No."** is an answer; an empty section is not. A superseded page is exempt: its replacement is its answer |
| **Cited condition** | every `[KB-###]`, `WP-##.x` and `Phase N` the section names, and every bare `#N` in a section that names `todo.md` | **report-only** — *"cited condition may have fired"* when the referent has closed or landed **after the section was last edited** |

A referent has closed when: the item heads a `RESOLVED` entry in
`resolved.md` and no open one in `todo.md`; every heading in the two roadmaps
that names the WP carries a closed-class marker (✅ ❌ — the classes are the
[contradiction rule's](#a-claim-the-repo-makes-twice-differently), and a
marker inside an italic `*( … )*` aside is about the aside, which is how
`WP-21.E`'s heading says ✅ for family 1 without closing the package); every
status claim for the phase on the board and in the roadmap is closed-class; or
the KB entry exists. The dates are per line from `git blame`, as in the
[ages table](#the-ages-computed): the referent's heading line against the
section's youngest line. **That comparison is what keeps the check quiet.**
[ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md) names
`[KB-027]` as the result it already absorbed, not a condition still pending —
its section is younger than the entry, and nothing prints. Editing the section
clears the line, even to say *"and it did not fire"*: the point is that the
page has been re-read since the thing it hangs on moved.

What is not read: prose. *"If GitHub's scheduler became reliable"*
([ADR-0012](../decisions/ADR-0012-external-cron-with-backstop.md)) is a
condition no machine evaluates, and the audit does not pretend to; a
structured condition field was rejected as narrower than the prose it would
replace (`resolved.md` #24). A cited id is also only a *proxy* for the
condition — ADR-0015 names Phase 19's design doc for its hard-kill procedure,
and Phase 19 closing would print a line the page then answers in a sentence.

**Found on the first run**, 2026-09-21: nothing — 20 pages carry the section,
ADR-0017 is superseded, and no cited referent has moved since its section was
last edited. Replayed to 2026-09-12 the check is red on exactly the two pages
`resolved.md` #24 dealt with, ADR-0015 (retrofitted 09-14) and ADR-0017
(superseded 09-13); the test suite asserts that replay. `--now` reads the
pages, the record and the blame at that date.

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

The weekly stages need no backstop of their own: they are jobs in this same
workflow, so whatever call arrives on a Monday brings them with it. A missed
Monday leaves the models a week old and the next Monday refreshes them.

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

Every slot calls `pipeline.yml`; there is no second URL to configure. Send input values as **strings** (`"force": "true"`, not `true`) — GitHub coerces
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

