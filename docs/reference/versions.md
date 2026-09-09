# Versioning

Every generated note and every score file carries an `agent_version` stamp naming
the pipeline version that produced it. This page is the live record of what those
stamps mean.

`.macro-assist/versions.py` is the **single source of truth**. The table below is
generated from `VERSION_MILESTONES` by
[`bump_version.py`](#bumping-the-version) and pinned to it by
`tests/test_versions.py` — if the two disagree, the test fails and the code wins.

<!-- BEGIN VERSION MILESTONES — generated from versions.py by bump_version.py; do not edit by hand -->

| Version | Date Range | Capability Added |
|---------|-----------|-----------------|
| v0.1 | 2026-03-12 – 2026-04-02 | Baseline: FRED + market data, signal matrix |
| v0.2 | 2026-04-03 – 2026-04-04 | + Accuracy scoring, feedback loop |
| v0.3 | 2026-04-05 – 2026-04-07 | + Opus, adversarial review, HY/ISM data |
| v0.4 | 2026-04-08 – 2026-04-27 | + YouTube transcript integration |
| v0.5 | 2026-04-28 – 2026-05-16 | + Portfolio positions (TR), Nasdaq data |
| v0.6 | 2026-05-17 – 2026-05-18 | + Sector research, COT positioning |
| v0.7 | 2026-05-19 – 2026-05-24 | + COT XLS fix, Pass 2 numerical anchoring |
| v1.0 | 2026-05-25 – 2026-05-25 | + Multi-agent: MA-1/MA-2/MA-3a |
| v1.1 | 2026-05-26 – *(superseded same day)* | + MA-3b: synthesis agent |
| v1.2 | 2026-05-26 – 2026-05-28 | + Phase 9/10: HAR-RV vol + HMM regime |
| v1.3 | 2026-05-29 – *(superseded same day)* | + Phase 11: conditional distributions |
| v1.4 | 2026-05-29 – 2026-06-26 | + Phase 12: quant context block; Phase 14: weekly refit + monitoring |
| v1.5 | 2026-06-27 – 2026-09-04 | + WP-16: run profiles (control/loosened), conviction-floor flag, Brier calibration |
| v1.6 | 2026-09-05 – 2026-09-08 | WP-21.D: directional product CUT — Bias/Confidence removed [KB-024]; conditional distribution published instead; fragility promoted to headline |
| **v2.0** | **2026-09-09 – present** | Phase 22 — the measured product is complete: canonical asset registry; conditional table 3 → 6 assets; distribution scorer live against a sealed pre-registered bar. Major: 1.x predicted direction, 2.x measures |

<!-- END VERSION MILESTONES -->

Two entries are marked *superseded same day*: v1.1 and v1.3 were deployed and
replaced within the same date, so they own no dates and `version_for_date()`
never returns them. They are kept because notes stamped with them at runtime
exist in the record.

## The 1.x and 2.x lines

The major digit marks a change in the **kind of claim the note makes**, not the
size of a release. There has been exactly one:

| Line | The note's claim | Scored by |
|---|---|---|
| **1.x** | A directional call — `Bias` and `Confidence %` per asset, per horizon | `score_predictions.py`, against the market |
| **2.x** | A measured conditional return distribution (median, P25/P75, `n`) and a tail-risk gauge. **No directional call anywhere** | `score_distributions.py`, against an unconditional benchmark |

So a 1.x note and a 2.x note are not two versions of one product; they are two
different products, and reading one as the other is a mistake the stamp exists to
prevent. Spend a major when a reader of an old note would misread a new one — not
on a large feature.

!!! note "Why the cut is v1.6 and not v2.0"
    The approach changed on **2026-09-05**, when [the cut](../concepts/the-cut.md)
    removed the directional call — arguably the major boundary. It is numbered
    v1.6 anyway, for one reason: notes on the `output` branch already carry
    `agent_version: v1.6`, and this project does not rewrite the record to match
    a later opinion. v1.6 is the demolition and reads as post-cut everywhere the
    scorers gate; **v2.0 is where the replacement product became complete and
    measurable** — a registry, six assets, and a scorer with a sealed bar. The
    boundary that actually gates behaviour is `LAST_DIRECTIONAL_VERSION` below,
    which is `v1.5`, and it is unaffected by either number.

## What each version boundary means for scoring

The stamp is not decoration — three readers branch on it.

| Reader | Uses the version to… |
|---|---|
| `score_predictions.py` | Skip post-cut notes. Gates on `has_directional_calls()`, **not** on table shape, so a stray legacy-shaped table cannot re-open the scorer — see [ADR-0010](../decisions/ADR-0010-freeze-the-directional-scorer.md) |
| `summarize_accuracy.py` | Exclude pre-`MIN_FEEDBACK_VERSION` reports from `feedback_windows`, and break out per-version stats for the 5 most recently deployed versions |
| `tag_versions.py` | Backfill `agent_version` onto older report and score files from `version_for_date()` |

Three constants carry that:

**`PIPELINE_VERSION`** — stamped into every new note. Always equals the open
milestone (the one ending `2099-12-31`).

**`MIN_FEEDBACK_VERSION`** (`v0.3`) — the earliest version whose predictions enter
the accuracy feedback loop. v0.3 introduced adversarial review, the first
structural quality gate on prediction output. Earlier reports are still scored
for historical completeness, but excluded from `feedback_windows`. Raise it when
a quality gate invalidates older predictions.

**`LAST_DIRECTIONAL_VERSION`** (`v1.5`) — the last version whose notes carry a
`Bias` / `Confidence %` table. v1.6 removed both from the schema, so a v1.6+ note
has nothing for the directional scorer to read. An absent or unparseable version
reads as *directional*: mis-skipping real history is the worse failure, so an
unknown version sorts first and stays scoreable.

!!! warning "Re-opening the directional gate is a decision, not an edit"
    If a bounded indicator search ever earns the column back, add the new version
    to `versions.py` as the last **directional** one and give the gate an
    explicit gap. Do not silently widen the range — the reproducibility of
    [KB-007] / [KB-011] / [KB-022] depends on v1.5-and-earlier scoring exactly as
    it always has.

## The output stamp

Every `*-macro.md` carries `agent_version` in its YAML frontmatter, inserted after
`type: macro-intelligence`:

```yaml
---
date: YYYY-MM-DD
day: Monday
type: macro-intelligence
agent_version: v2.0
tags: [macro, daily-note, economics]
---
```

Score files (`results/scores/YYYY-MM-DD.json`) carry the same field immediately
after `report_date`:

```json
{
  "report_date": "2026-09-09",
  "agent_version": "v2.0",
  "scored_at": "2026-09-15",
  "windows": { ... }
}
```

## Bumping the version

Bump the **minor** digit after a structural capability change — a new data source,
a new agent pass, a change to what the note publishes. Not for a bug fix, a doc
pass, or a refactor that leaves the output identical. Bump the **major** digit
only when the kind of claim changes, per [the 1.x and 2.x lines](#the-1x-and-2x-lines)
above.

```bash
python .macro-assist/bump_version.py v2.1 "+ what changed, one line"
```

That does all of it atomically: sets `PIPELINE_VERSION`, closes the open
milestone at yesterday, appends the new entry, and regenerates the table on this
page from `VERSION_MILESTONES`.

When the capability goes live on a date that is not today — a weekly refit lands
on Sunday, say — pass the real go-live date so the stamp does not claim a
capability the notes did not yet have:

```bash
python .macro-assist/bump_version.py v2.1 "+ ..." --start 2026-09-14
```

Then run the post-bump hooks and the guard:

```bash
python .macro-assist/tag_versions.py         # backfill the stamp onto existing files
python .macro-assist/summarize_accuracy.py   # rebuild per-version stats
pytest .macro-assist/tests/test_versions.py  # milestones + this page agree
```

`tag_versions.py` assigns by **date**, so it will re-stamp a note whose runtime
`PIPELINE_VERSION` was written before the bump landed. That is the intended
direction: the date range is the more accurate record of which code built the
note.

## Where the old table went

`roadmap-archive.md` contains a *frozen* milestones table inside the
"System-state snapshot (~v1.5)" block, ending at `v1.5 – present`. It is
preserved as it stood on 2026-09-04 and is **not** maintained — the archive is
append-mostly and is never rewritten to match a later opinion. This page is the
live one.
