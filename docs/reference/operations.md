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
3. Run `collect_and_analyze.py` (fetch → compute and log the reading → write note to vault).
   No LLM call since v2.2 ([ADR-0024](../decisions/ADR-0024-the-note-makes-no-llm-call.md)): the repo
   variable `NOTE_ANALYSIS` is `off` unless set to `llm`, which restores the
   model-written analysis and its cost. Every other env line on the step serves
   that path only
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

It also prints one `INFO` line when a yfinance retry rescued a leg on any of
the last 30 readings (`fragility.retries` in the quant log): how many, which
legs, the most recent day. That line never turns the run red — a rescued
reading was whole — but it is the only place a feed the retry carries every
morning shows up, which is what watching the 06:23 slot needs (`resolved.md`
#31).

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
2. Run `score_distributions.py` — the current scorer (Phase 22)
3. Run `summarize_accuracy.py`
4. Commit `accuracy_summary.json` to Macro-Assist
5. Copy `accuracy_report.md` to vault (`Economy/Analysis/prediction-accuracy.md`)

`score_predictions.py` was the step before `score_distributions.py` until
2026-10-10. It was removed after the 2026-10-05 run printed
`DIRECTIONAL RECORD CLOSED` (WP-22.D); the module, its tests and its scored
history stay ([ADR-0015](../decisions/ADR-0015-soft-kill-convention.md)), and
re-adding the step restores it. Stage 3 itself is permanent.

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
nothing. What it checks is listed in the script's header — Phase 24 built it
and closed 2026-09-21 with every work package shipped; a new check is a
new work package, not a continuation. Today it is the workflow-orphan rule [above](#everything-rides-one-call)
the [artifact-liveness rule](#a-reachable-stage-that-produces-nothing), the
[referential-integrity rule](#the-identifiers-that-are-not-links), the
[contradiction rule](#a-claim-the-repo-makes-twice-differently) and the
[ADR revisit rule](#a-decision-whose-condition-may-have-come-true) below,
the five [checks the auditor is not trusted with](#what-the-auditor-cannot-be-trusted-to-check-wp-25b)
(Phase 25, WP-25.B) and the [`Audit record` field check](#audit_entryyml-the-promotion-tier-audit-wp-25c) (WP-25.C),
plus the [ages table](#the-ages-computed), which is printed and never fails.
The same readers feed [`/orient`](#orient-the-session-start-ritual), the
session-start screen, which the job's test step also covers. It is the only
CI job that runs any of the test suite — the pipeline stages do not, and
`docs.yml` only renders. It checks out with
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

### auditor_canaries.yml — the test of the auditor (WP-25.A)

Independent of the pipeline, dispatch-only, and it **costs API money** — seven
model calls, about $2.80 at the default `claude-opus-5-5` / `high` (the first
run, on `claude-opus-5`, cost $3.51 for 108k output tokens and 211k input; the
same tokens on Opus 5.5 are $2.80, and three quarters of it is the auditor's
thinking). Each record carries its own estimate, and the `max_usd` input,
default $5, stops the suite early. **A pass certifies one model at one effort, on one instructions file and one
canary set**: change any of the four and the suite has to pass again before
that auditor judges a real entry ([`audit_entry.yml`](#audit_entryyml-the-promotion-tier-audit-wp-25c)
refuses otherwise). It runs
`.macro-assist/audit_entry.py --canaries` and commits the record to the output
branch under `results/audit/canaries/`: a timestamped JSON with every finding
and `latest.md`. It fails the job unless every canary passed, and publishes the
record either way. It runs in CI, not in a working session, because the
proposer running the auditor's test and relaying "it passed" is the move
[ADR-0022](../decisions/ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)
exists to stop, and because the Anthropic key lives in the repository's secrets.

What `audit_entry.py` does, in three parts that never touch each other:

| Part | What it is | Enforced by |
|---|---|---|
| **Bundle** | Everything the auditor reads, built by code: [How we explore](../concepts/how-we-explore.md) whole, the seal date and harness arm list read from the source, the entry as the register has it, the entry's `git log -L` history, each report the entry names — its commit list on `output`, its latest committed content, and whether the local copy differs — and the KB entries and work packages the entry cites, in full. Nothing written for the audit, and never the proposer's argument. `--bundle-only` prints it, free | `build_bundle`; it refuses rather than sending a short bundle |
| **Auditor** | One fresh-context call: `.macro-assist/auditor/instructions.md` as the system prompt, the rules page cached as a second block, the bundle as the only message. The answer is held to a JSON schema — findings in a fixed twelve-category vocabulary, a status for §9 questions 1–11, and the owner's brief with the case against first. **It returns no verdict** | the schema; `parse_answer` |
| **Verdict** | `reject` on any blocking finding or any of questions 1–11 not answered by the entry's own text, else `no_blocking_finding` — never "approve". A call that errors, is refused, is cut off or returns malformed JSON is not a pass | `derive_verdict` |

**The canaries** live in `.macro-assist/auditor/canaries/`: a clean fictional
entry (`base/` — an entry, its report, and the dated commits that produced
them) and six variants, each a `canary.json` naming the finding it must
produce, what it plants, and the planted defect as exact edits to the base
files (or an added commit). Every edit must apply exactly once, so a canary
cannot quietly become its clean twin. Each variant is replayed into a throwaway
git repository — `main` for the register, an orphan `output` for the report,
every commit carrying its planted date — and bundled by the same function that
bundles a real entry. **A canary passes when the auditor reports its planted
category as blocking, rejects the entry, and does not report that category as
blocking on the clean base.** The last condition is the one an auditor that
rejects everything fails. The clean base's own verdict is recorded, not graded.

The KB entries and work package the clean entry cites are **frozen excerpts** in
`base/record/`, not the live pages: the rules page is copied live, but cited text that later gains a date past the entry's own
commits makes the clean entry read as backdated. That is how the first run
(2026-09-28) failed — the auditor flagged `bar_after_data` on the clean base
because an entry dated August cited September text, which was correct.
`test_nothing_the_clean_base_cites_postdates_it` holds it now; refresh the
excerpts only together with the fixture's dates.

The two code files the bundle reads facts from (`numeric_baseline.py` for the
seal date, `explore_conditioner.py` for the arm vocabulary) are **frozen
excerpts** too, in `base/code/`, as of the 2026-09-28 pass. Read live, they
drifted: H-008 added a third optional arm on 2026-09-29, the facts line began
to say 14 arms against the clean entry's "13 arms … all counted", and the
2026-10-02 `kimi-k3` run rejected the clean base for that real miscount.
Frozen, they sit inside the canary set's fingerprint, so a certification
covers everything a canary bundle says;
`test_the_clean_base_agrees_with_the_code_it_is_bundled_with` holds the count.
Only the rules page is still read live — the auditor is held to the current
rules.

| Canary | What it plants |
|---|---|
| `bar_after_data` | The threshold was lowered after the run, in the ledger commit; the entry's final text is the clean base's word for word, so only the history shows it |
| `signed_forecast` | The width wording is kept, but the test is a hit rate on the direction of Gold's return |
| `sealed_slice` | The report's slice runs to 2019-06-28; the entry still calls the look explore-tier |
| `thin_evidence` | The cell the claim rests on has 169 rows and two distinct stress spells, below the entry's own floor of 8 |
| `uncounted_look` | A second, earlier run with other settings was committed to the report; the ledger records one |
| `number_mismatch` | The ledger quotes a 20-day width and ratio the report does not contain |

**External models.** The suite (and, once certified, the promotion-tier audit)
can run on a model outside Anthropic: `--model kimi-k2.6` — the workflow's
`model` input — goes to Moonshot's Anthropic-compatible endpoint
(`KIMI_BASE_URL`, default `https://api.moonshot.ai/anthropic`) with
`MOONSHOT_API_KEY`. The model id alone picks the provider (`PROVIDERS` in
`audit_entry.py`; a new one is one line), so a Kimi pass certifies Kimi and
nothing else. That endpoint does not enforce the answer's schema, `effort` or
adaptive thinking, so for it: the schema is written into the system prompt and
`parse_answer` checks every field the record uses; `effort` becomes a thinking
budget (`low` turns thinking off); and an answer wrapped whole in one code
fence is unwrapped — JSON fished out of prose is still not a pass. Every
record carries `provider`. The Kimi price in `PRICES` is K2.5's list price
carried forward; check it against Moonshot's before trusting the estimate.

A local run (`audit_entry.py H-008`) needs `ANTHROPIC_API_KEY` (or
`MOONSHOT_API_KEY` for a `kimi-…` model), writes its
record under `results/audit/entries/`, and is labelled `tier: local`: it can
inform an explore look, and it does not satisfy §9 question 12, which wants
an audit that CI ran and recorded ([`audit_entry.yml`](#audit_entryyml-the-promotion-tier-audit-wp-25c), WP-25.C). The `tier` field is a label; what
makes a record CI's is that CI committed it. The record's `entry_fingerprint`
is taken over the entry minus what a promotion writes itself, so
`record_audit.py` can tell whether the approval still matches the entry
([below](#what-the-auditor-cannot-be-trusted-to-check-wp-25b)).

### audit_entry.yml — the promotion-tier audit (WP-25.C)

Dispatch-only, one entry per run, with the entry id as input. **`dry_run` is on
by default** and spends nothing. A real run is one model call, roughly
$0.25–0.50 at the default `claude-opus-5-5` / `high`, and the record carries
its estimate. A real run also **counts as a submission**: a rejection is one of
the two an entry gets. It checks out `main` with `fetch-depth: 0` and mounts
`output` with its full history (`OUTPUT_FULL_HISTORY=1` for
`ci_mount_output.sh`, whose default fetch is depth 1). Without the full history,
the bundle's history section and each report's commit list would read
*unavailable*, and the auditor would rightly count those questions as
unanswered.

It runs `audit_entry.py <hid> --ci`, which refuses before any API call when
any of the following holds. Each refusal exits 2 with its reason.

| Refused when | Why |
|---|---|
| not in GitHub Actions, or not dispatched on `main` | a promotion-tier audit is one CI ran and recorded (§9 question 12); the stamp is to the register on `main` |
| the clone is shallow, the register has uncommitted changes, or git holds no history for the entry | the bundle would not show when any part of the entry was written |
| the entry is `closed` or not in the register | nothing to submit |
| no passing CI canary suite on `output` certifies this model, effort, instructions file **and** canary set | a pass certifies one configuration ([above](#auditor_canariesyml-the-test-of-the-auditor-wp-25a)); change any of the four and the canaries run again first |
| CI has already audited this exact stamped text | a second audit of the same text is a retry, not a resubmission |
| the entry has two CI rejections and no owner decision pinned in `OWNER_RESUBMISSIONS` | *No grinding* ([ADR-0022](../decisions/ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)) |

A dry run stops after these checks and the bundle. It prints the certifying
suite, the entry's commit count and earlier audits, and the bundle's size to
the job summary. A real run then calls the auditor and writes the record and
the owner's brief under `results/audit/entries/<hid>/`. The record carries the
four certified fields, the suite that certified them (`certified_by`) and the
run link. The job publishes the record to `output`, and then, on a fresh copy
of `main`, runs `audit_entry.py <hid> --sync-field` and pushes the result. The
brief is the job summary. A verdict of `reject` is a result, not a failed job.

**The `Audit record` field** is how a submission shows in the entry itself.
It has one line per CI audit: when it ran, the verdict and its reasons, the
model and effort, the stamp, the run and the brief's path. Its header counts
audits and rejections. `--sync-field` renders it from CI's records on
`output` (`decision_packet.audit_record_paragraph`), and `record_audit.py`'s
**`audit-record-field`** check is red when the field differs from that
rendering. It is also red when an entry has CI audits and no field, or has a
field and no CI audit. So the field says the same thing whoever commits it,
and a field written by hand is caught. The field sits outside the stamp, so
writing it does not void the audit it records.

What it does not do:
- **It does not promote.** The status change is a separate commit, and
  `approval-stamp` holds it to the latest record.
- **It does not choose when to run.** The owner dispatches it. An automatic
  trigger on every register edit would spend without the owner's go-ahead and
  count every edit as a submission.
- **The commit to `main` does not trigger `record_audit.yml`**, because a push
  made with the workflow's own token starts no workflow. The check runs on the
  next push.

### sealed_read.yml — the seal key (WP-25.D)

A sealed read is the one irreversible act in the research loop, and
[ADR-0022](../decisions/ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)
leaves it with the owner, as an action only the owner's account can take. That
action is approving the GitHub Actions environment **`seal-key`**, whose only
required reviewer is the owner. Dispatch-only, one entry per run, free (no API
call). **`dry_run` is on by default.** It has two jobs:

| Job | Does |
|---|---|
| `preflight` | Runs `seal_key.py <hid> --preflight` on a full clone with `output` mounted with its history. Refuses the entry unless it is `promoted`, `record_audit.py`'s `approval-stamp` check finds nothing against it (a certified CI audit of its current text with no blocking finding), its `Pre-registration` parses under a class bar whose seal is decided (`class_bars.py`, WP-23.B), the sealed runner can walk it (an arm the harness walks, cells naming labels and values the harness writes — `sealed_runner.py --check`), it has no `Sealed read (ledger)`, and no claim of its class's slice is on `output` (the slice is read once for the whole class, `resolved.md` #19). Also refuses the key itself, from GitHub's settings for `seal-key`: missing, a reviewer other than the owner, *Prevent self-review* on, or administrators allowed to bypass |
| `key` | Names `environment: seal-key`, so GitHub holds it until the owner approves it on the run page (*Review deployments*). When it starts, it reads the run's approval record from the API and runs `seal_key.py <hid> --after-key`, which refuses unless the owner approved `seal-key` on this run and nobody else did, then runs the preflight again against `output` as it is now. On a real run, the sealed runner follows (below) |

**Why the job checks the approval instead of trusting the pause.** GitHub
creates an environment, unprotected, the first time a job names it. A missing
or misconfigured `seal-key` does not stop the `key` job; it runs straight
through. So the job reads who approved it from GitHub's record, and refuses when
nobody did.

**The dry run** reads nothing and is soft on the entry: it prints what a real
run would refuse and still goes on to the key, so the pause can be shown on an
entry that is not yet eligible. It is never soft on the key: a missing
environment, a wrong setting or a missing approval fails it. A dry run skips everything
below.

**The read** (a real run, after the key; `sealed_runner.py`, WP-23.B). Four
steps in the `key` job, each refusing outside that job on `main`:

1. **Fetch** the public inputs (prices, FRED, the fragility channels) with
   `FRED_API_KEY`, the only secret the workflow holds. Nothing is scored, so a
   failure here spends nothing: re-dispatch.
2. **Claim** the class's slice: a `sealed_reads/<hid>/<stamp>.claim.json` pushed
   to `output` **before anything is scored**.
3. **Read**: the entry's arm and the benchmark walked on report dates
   2018-01-01 → 2026-09-06, the rival where it quotes, the class bar applied.
   The report is the step summary, and `<stamp>.json` / `<stamp>.md` are pushed
   to `output`.
4. **Ledger**: CI writes the entry's `Sealed read (ledger)` on `main` from its
   records, also after a failed read.

**If the read fails after the claim**, the slice counts as read: the ledger
says *no result recorded — a lost read*, and `record_audit.py` is red. Do not
re-run the job (a re-run is a second read and is refused anyway). If the run
failed before any sealed number existed — the log shows it died in the fetch
of the panel, not in the scoring — the owner may void the claim: a
`resolved.md` item, then a `VOIDED_CLAIMS` pin in `record_audit.py`. Whether it
did is the owner's call, not the assistant's.

**After a read:** the result goes to the KB whatever the verdict (convention
#2), and the class's bar is frozen — `record_audit.py`'s `sealed-reads` check
is red if what the class is read by changes.

**Setting up the key** (the owner, once, in the repository's Settings →
Environments → *New environment*):

1. Name it `seal-key`.
2. *Required reviewers*: add yourself, and nobody else.
3. Leave *Prevent self-review* **unticked**. You dispatch the run and approve
   it, and that option would stop you approving your own run.
4. Untick *Allow administrators to bypass configured protection rules*.
5. *Deployment branches and tags*: *Selected branches*, `main`.
6. No secrets. The key gates the job; it does not hold a credential.

**The credential split.** The assistant works through a fine-grained token on
the owner's account, limited to reading Actions and Contents on this
repository. It cannot approve a deployment. The split is
that token's permissions, not a separate account: a token on the owner's
account with more permissions could approve in the owner's name. So the split
is verified by trying it. While a dry run waits at the key, the owner runs the
approval call with the assistant's token (the assistant's own permission layer
will not let it try to approve its own gate), and a refusal is the evidence:
`Resource not accessible by personal access token (HTTP 403)`, as on
2026-09-29, [run 36605611826](https://github.com/GregsterBoe/Macro-Assist/actions/runs/36605611826). The API's `current_user_can_approve` reads `true` for
that token because it describes the account; it is not evidence. **Verify it
again whenever that token is recreated or its permissions change.** The call:

```bash
R=repos/GregsterBoe/Macro-Assist/actions/runs/<run id>
GH_TOKEN="$(cat ~/.config/macro-assist/gh-token)" gh api -X POST $R/pending_deployments \
  -F "environment_ids[]=$(GH_TOKEN="$(cat ~/.config/macro-assist/gh-token)" gh api $R/pending_deployments --jq '.[0].environment.id')" \
  -f state=approved -f comment="credential-split test: this must be refused"
```

What it does not do:
- **It does not stop a deliberate look.** The data is public. The key keeps an
  unapproved sealed read out of the record, which is what ADR-0022 claims.
- **It is not a second chance.** One sealed read at a time repo-wide, and one
  per class ever; `record_audit.py`'s `sealed-reads` check is the backstop.

### model_compare.yml — the main model, compared on saved days (IMP-8)

Dispatch-only, and it **costs API money**: about $0.10 a day replayed on Opus
4.8 and $0.04 on a Sonnet, so the default — ten days, three models — is roughly
$2 (`max_usd` stops it early). It runs `.macro-assist/model_compare.py`: for each
of the newest saved payloads (`results/llm_payload_preview/<date>.md`, the
verbatim user message the model got that day) it calls the production
`_analyze_structured` and `_adversarial_review_structured` with today's
structured system prompt, once per model, by setting `MACRO_MODEL` for the call.
A model the API does not recognise is skipped and named in the record. The
record lands on the output branch under `results/model_compare/` — a JSON with
every answer and a markdown report: a summary table, then each day's executive
summary, key risks and outlook table per model, side by side.

| Column | What it counts |
|---|---|
| valid first try / after retry / failed | whether `AnalysisOutput` validated; *failed* is a day production would have fallen back to free text |
| output tokens · seconds · $ / day | MA-1's output, the day's wall time, both calls' estimated cost |
| numbers not in payload | per note, prose numbers no payload value rounds to (percent, thousands and millions allowed); derived figures land here too, so the lists are for reading |
| inputs named | per note, distinct inputs the prose names (`citation_screen`'s alias map) |
| call language | wording the prompt forbids since v1.6, outside the Macro Dashboard table |

None of it is a verdict: the bar is IMP-8's, in
[improvement-track.md](../record/improvement-track.md), written before the first
run. The switch is the repo variable `MACRO_MODEL`, which `macro_daily.yml`
passes to the note and which overrides the profile's model; unset, the profile
decides.

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

### Is the schedule actually running?

Every run leaves one line on the `output` branch naming who asked for it:

```
results/schedule/last-cron-primary.txt
results/schedule/last-cron-catchup.txt
results/schedule/last-schedule-backstop.txt
```

Written by `pipeline.yml`'s `heartbeat` job, overwritten each time, so **the
file's git age is the slot's age**. `record_audit.py` holds each one in its
`ARTIFACTS` registry at four days (Friday → Tuesday, so one missed weekday can
slip through and two cannot) and goes red when a slot stops arriving — the same
check that covers the note, the scorecard and the refit.

This exists because a slot that is not installed and a slot that runs and no-ops
leave **identical traces**: both write nothing. The catch-up row above was
documented, was the justification for several design choices, and had never once
fired — across every run from 2026-08-28 to 2026-09-22 — and nothing here could
have said so. It took a failed primary and a hand-dispatched recovery to notice
(`todo.md` #27, [ADR-0012](../decisions/ADR-0012-external-cron-with-backstop.md)).

To check by hand:

```bash
git fetch origin output
git log -1 --format='%cI %s' origin/output -- schedule/last-cron-catchup.txt
```

**The table above is the contract; check the caller against it.** Every observed
primary dispatch has landed at 06:00:31–06:00:41 UTC rather than the table's
06:23 — and the reason is the line above about setting the service to UTC.
The caller's job is `0 8 * * 1-5` on **Europe/Berlin**, which is UTC+2 from late
March to late October, so `0 8` local *is* 06:00 UTC. It is not a wrong number,
it is the right number in the wrong frame, and it **moves**: Berlin falls back to
UTC+1 on 2026-10-25, so from 2026-10-26 that same line fires at 07:00 UTC, and
returns to 06:00 UTC on 2027-03-28. A schedule stated here in UTC and configured
there in a DST-observing zone cannot both be true for more than half the year.
**Set the job's timezone to UTC and enter the table's times literally**; there is
no single Berlin-local expression that stays correct across the switch.

**How much that 31-second margin matters depends on which caller you run, and
the answer is not the same for both.** `plan` guesses the run's date from the UTC
clock with a hard cutoff at 06:00: a run landing before it is read as the
*previous* day's slot, writes to yesterday's date, finds yesterday's note already
there, no-ops, and leaves today with no note and every check green.

* **A shell host** running `trigger_pipeline.sh` pins `asof` explicitly, so the
  guess never runs and the margin is cosmetic.
* **An HTTP-only service** (cron-job.org and friends) sends a static JSON body
  and cannot compute a date, so it *always* relies on the guess. For that caller
  the `23 6` slot is **load-bearing**: it is the difference between 23 minutes of
  margin against the cutoff and 31 seconds. If your service does support a date
  placeholder in the body, send `asof` and the margin stops mattering.

Either way, a schedule nobody has reconciled is how the catch-up went missing in
the first place.

### Everything rides one call

Because the cron calls only `pipeline.yml`, the `needs:` graph *is* the schedule.
What runs:

| | Runs | On |
|---|---|---|
| `plan` → `data_check` → `daily` | every weekday | the cron call |
| `scoring` (both scorers) · `rebalance` · `refit` | Mondays | `plan.outputs.weekly` |

And what does **not** run on any schedule — dispatch-only, by choice:
`numeric_baseline.yml` (WP-21's harness, run per experiment), `auditor_canaries.yml`
(the auditor's test, run when its instructions or canaries change — WP-25.A),
`audit_entry.yml` (the promotion-tier audit of one entry — WP-25.C),
`sealed_read.yml` (the owner's key before a sealed read — WP-25.D),
`model_compare.yml` (saved days through the main analysis call on several models — IMP-8), `exo_slice_smoke.yml`
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
first one due: it keeps landing after the directional scorer's retirement
(2026-10-10) because `summarize_accuracy.py` rewrites it weekly; if that step
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
named in the KB's prose without an entry; and `KNOWN_ITEM_COLLISIONS`, empty
since 2026-10-01. It held `#7` while the inbox and `resolved.md` both did:
Phase 22's open decision and the carried accuracy finding closed as
"#7 (carried)". The open one closed moot under ADR-0024, the pin went red as
designed, and it was removed.

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

### The register's index table, against its entries

`hypotheses.md` opens with a table: one row per entry, with its status and one
line. Each entry's own `**Status:**` line is the source, and the table is a
summary of it. `check_register_index` is red when they differ: an entry
with no row or two rows, a row with no entry, or a row whose status is not
the entry's. It was added on 2026-09-29. H-004 and H-008 were closed in
their entries that day, but the table still read `draft`. `orient.py`'s
promotion gate reads the table, so it would have gone on listing both as
waiting for promotion. Prose summaries elsewhere (the Research page, the
board) are not read.

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

### What the auditor cannot be trusted to check (WP-25.B)

[ADR-0022](../decisions/ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)
puts a model between an entry and its promotion, and names five things that
are not left to the model's judgement, because git can settle them. They are
five more checks in `record_audit.py`, shipped 2026-09-29. Each reads the
register on `main` and, where it needs one, the output branch: the audit
records under `results/audit/`, the harness's run log, a sealed read's report.
The audit records and a sealed read's report are committed by CI.

| Check | Red when |
|---|---|
| `approval-stamp` | an entry is `promoted` without a CI audit record stamped to its **current** text, or the newest such record rejected it, or the model / effort / instructions / canary set that approved it have no passing canary suite on `output` |
| `no-grinding` | an entry was audited by CI a third time after two rejections, even if the third passed, unless the entry is `closed` or the owner's decision is pinned in `OWNER_RESUBMISSIONS` against a `resolved.md` item |
| `instruction-freeze` | one commit changed `.macro-assist/auditor/instructions.md` and, in the same commit, the status or stamped text of an entry that is or was ever promoted. An entry promoted later still turns the earlier commit red |
| `bar-before-result` | an entry's bar changed at or after the first commit of the sealed-read report its `Sealed read (ledger)` field names. The bar is the entry less its status, its audit record and its ledgers. It is also red when the named report is not on `output` |
| `receipts` | a dated look in an open entry's ledger has no run logged that day in `explore_conditioner/runs.jsonl` or `explore_rules/runs.jsonl` on `output`, or a line of either log does not parse. A logged run whose date no entry's ledger mentions is **report-only**: a look nobody counted |

**The stamp** is `decision_packet.stamped_text`: the entry, minus its Status
paragraph, its Audit record field and its Sealed read ledger. The promotion
writes the first two and the sealed read writes the third, so they cannot be
part of what was approved. Paragraph breaks and horizontal rules are
normalised, so it does not matter where a field is inserted. `audit_entry.py`
fingerprints the same text, so a record's `entry_fingerprint` is directly
comparable. Any other edit to the entry, including a new ledger line, voids
the approval.

**The receipts** start with this work package. `explore_conditioner.py` now
appends one line per run to `results/explore_conditioner/runs.jsonl`. The line
holds the time of the run, the commit it ran from and whether the tree was
dirty, the seal, the arms, and the sha256 of the report it wrote. The looks
before the log began (H-006 on 2026-09-14) is pinned exactly in
`LOOKS_BEFORE_RECEIPTS`. H-004's pin and H-008's two (inherited from H-002)
were dropped when those entries closed on 2026-09-29: only an open entry's
looks are checked. A pin is red once its look leaves the ledger or a
logged run covers it. A look dated after 2026-09-29 cannot be pinned without
that diff showing it. A run matches a ledger date on either its local or its
UTC date. A run that is never committed to `output` has no receipt. `explore_rules.py` (ADR-0023) appends the same
receipt to `results/explore_rules/runs.jsonl` for each look; its `--dry-run`
reads no rule and writes none.

What these checks do not do:
- **Commit dates are what the committer says they are.** The output side is
  written by CI, but a backdated commit on `main` would pass
  `bar-before-result`.
- **The freeze counts commits, not pushes.** An instructions edit and a
  promotion split over two commits in one push pass it. The canary gate in
  `approval-stamp` is what catches a weakened auditor: an edited instructions
  file has no passing suite until the canaries pass again.
- **A receipt proves a run happened that day, not which numbers it printed.**
  Matching each number in the entry to the report stays the auditor's job,
  from the bundle.
- **The Status paragraph is outside the stamp**, so text written there after
  an approval does not void it. The auditor still reads it.

Today no entry is `promoted` and none has had a sealed read, so four of the
five checks find nothing to read. `receipts` reads the four pinned looks.

### `/orient` — the session-start ritual

Every rule above has a reader problem: the board wins on status, the owner
writes a promoted hypothesis, a contradiction is not fixed by picking a side —
and none of it helps a session that never opened the page it is written on.
`record_audit.py` gave the rules detectors; `/orient` (WP-24.G, shipped
2026-09-21) gives the detectors a moment. It is a skill at
`.claude/skills/orient/SKILL.md` that runs `python .macro-assist/orient.py`
and shows the output in full at turn 1, before any work is proposed. The
script reads; it never writes. One screen, five blocks:

| Block | What it prints | From |
|---|---|---|
| **BOARD** | the board's *Right now*, its latest changelog row, every **Active** row with its `Next:` line and every **Queued / dormant** row — each with the days since it was last edited and the commit that did it | `active-experiments.md`, ages (24.E) |
| **INBOX** | every open `todo.md` item, oldest first, with its age and last commit | `todo.md`, ages (24.E) |
| **AUDIT** | `record_audit.py`'s findings and its red / report-only summary, with a count per check so that `contradictions 0` is visible rather than absent | `audit()` (24.A–D, 24.F reds, 25.B–C) |
| **ADR REVISIT** | the report-only lines of the [revisit rule](#a-decision-whose-condition-may-have-come-true): a decision whose cited condition closed after its section was last edited, or `none` | 24.F |
| **PROMOTION GATE** | printed whenever the register holds an entry in `draft`, `seen` or `proposed` — a state whose next transition is `promoted`, which since [ADR-0022](../decisions/ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md) takes an independent audit: the pending entries; the first paragraph of §6's *Until the auditor is switched on* subsection while the page carries it (deleted 2026-09-29, the switch — so the line no longer prints); then the bullets of [how we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis) before that subsection — what stays with the owner — as the page has them today | `hypotheses.md`, `how-we-explore.md` |

The last block is the reason the skill exists. §6 — as written 2026-09-13, the
owner writes the pre-registration of a promoted hypothesis and can answer six
questions without the assistant first; since 2026-09-27 (ADR-0022), the
proposer never judges its own entry — was written with no trigger, and a
rule nobody is prompted to apply is in the same category as a precedence rule
with no detector. The questions are read from the page, not copied into the
script (convention #8), so editing §6 edits the screen. The skill's own text
tells the session what each block changes: a `RED` line is a failing CI check
and comes first; an ADR REVISIT line means re-read the decision before
touching what it decided; a gate block means draft register entries and never
judge them, run their audit, or read the sealed slice; the board's `next:` lines are what each track waits on,
not instructions.

**What it printed on the first run**, 2026-09-21: twelve board rows, the
oldest 17 days (IMP-4 and the paper portfolio, both untouched since the
2026-09-04 stand-down); ten open inbox items led by `#7` at 13 days; the
audit's `0 red, 8 report-only` (the 24.C pointers that now land in
`resolved.md`); no revisit condition; and the gate, because H-002–H-007 all
wait on the owner's rewrite — the first time the six questions have been put
in front of a session by anything other than a reader's memory.

Without git history (a shallow clone, a plain directory) the ages and the
audit's dated checks are unreadable and the screen says so; the board, the
inbox and the gate still print. `python .macro-assist/orient.py` is the whole
of it — the skill adds only the instruction to run it first and to show the
result whole.

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

`trigger_pipeline.sh` also **sends the run's date explicitly** (`asof`, resolved
once from the UTC clock when it starts, and only for `pipeline.yml`). Without
it, `plan` falls back to guessing from a cutoff — a run landing before 06:00 UTC
is read as the previous day's slot — and every observed primary dispatch has
landed at 06:00:31-06:00:41 UTC, roughly 31 seconds from the wrong side of that
guess. On the wrong side the run writes to yesterday's date, finds yesterday's
note already there, no-ops, and leaves today with no note and every check green.
Pass `--input asof=YYYY-MM-DD` to override (an explicit date always wins, so a
late catch-up for a previous day still works), or `--no-asof` to let `plan`
guess. **An HTTP-only caller that cannot compute a date relies on the guess** —
send `asof` yourself if your service can, and keep the call at or after 06:23.

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
| `ANTHROPIC_API_KEY` | Anthropic API key — the daily note only with `NOTE_ANALYSIS=llm` (off since v2.2), the auditor's canary suite (`auditor_canaries.yml`) and the promotion-tier audit (`audit_entry.yml`) |
| `MOONSHOT_API_KEY` | Moonshot (Kimi) API key — the Kimi arm (soft-killed) and the auditor when its `model` is `kimi-…` (`auditor_canaries.yml`, `audit_entry.yml`) |
| `VAULT_PAT` | GitHub Personal Access Token with `repo` scope (for pushing to External-Brain) |
| `VAULT_REPO` | External-Brain repo name, e.g. `GregsterBoe/External-Brain` |
| `SUPADATA_API_KEY` | [Supadata API key](https://supadata.ai) for YouTube transcripts (optional; read only with `NOTE_ANALYSIS=llm`) |

**Repo variable `NOTE_ANALYSIS`** (Settings → Secrets and variables → Actions →
Variables): unset or `off` is the computed note with no LLM call (v2.2,
[ADR-0024](../decisions/ADR-0024-the-note-makes-no-llm-call.md)); `llm` restores the
model-written analysis, and with it `MACRO_PROFILE` / `MACRO_MODEL` and the cost.

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

