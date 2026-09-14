# Product

**What is ready to be used, what it promises, and what it does not.** This
page is the contract. The description of the note is in
[What this is](../concepts/what-this-is.md) and the mechanics are in
[Reference](../reference/index.md); this page only states what a user may rely
on, and draws the line between the product and the research that measures it.

---

## What "ready" means here

The product is ready in the sense that matters for this project: **every claim
it publishes is scored against a trivial rival, and the ones that failed have
been removed.** It is not ready in the sense of "proven to have skill" — the
one live claim with a pre-registered bar (the conditional distribution) is
sealed until ~2027-05 and may fail. A user gets a product that says exactly
what it knows, which is less than most.

Concretely, as of **v2.1** (2026-09-13; first note 2026-09-14):

| Published | What it promises | What it does not promise | Held to |
|---|---|---|---|
| **Fragility Monitor** — composite 0–100 with a label, plus the OR flag | A high-recall "this is not a normal tape" warning. The OR roughly doubles crisis recall over the composite; the label is the top decile of the composite's own history | Direction. Precision ≈ 0.3, so most firings are false alarms, and the note says so inline | KB-016 → KB-017 → KB-020 → KB-021; aggregation and channel set closed by KB-031, KB-032 |
| **5-Day Outlook table** — per asset, the empirical conditional return distribution: median, P25/P75, `n` | The historical distribution of forward changes in the current macro bucket, rendered by Python from a fitted table | That conditioning beats not conditioning. That is the open question, and the scorer is measuring it | Phase 22, sealed bar — [ADR-0016](../decisions/ADR-0016-phase-22-scores-the-distribution-only.md), [ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md); first read ~2027-05 |
| **Narrative** — executive summary, dashboard, per-asset sections | A schema-constrained model reading of the day's data, with sources | A forecast of any kind. Nothing in the narrative is scored; nothing scorable is left in it | [ADR-0002](../decisions/ADR-0002-structured-output-contract.md), [ADR-0003](../decisions/ADR-0003-four-narrow-agents.md) |
| **Weekly scorecard and accuracy report** | Every published claim scored on the same sample as its rivals, with block-bootstrap intervals | A verdict before `MIN_BLOCKS` is reached — the scorer returns `underpowered` until then | [Scoring](../reference/scoring.md) |
| **Paper portfolio** | A mechanical, paper-only book driven by the published table | Any trading advice; it is an instrument for scoring the table's usefulness | [ADR-0019](../decisions/ADR-0019-paper-portfolio-mechanical-and-paper-only.md) |

**Removed, and why:** the directional call (`Bias` / `Confidence`), v1.6 —
[The cut](../concepts/the-cut.md). The HMM regime block — ADR-0004. Anything
proposing to put a signed forecast back is arguing against ADR-0009.

**Cadence and delivery:** one note per weekday, `asof` resolved once by the
pipeline's `plan` job; scoring and refit weekly. [Operations](../reference/operations.md).

## The product surface

The product is the set of modules that run in `pipeline.yml` or are imported
by one that does. The set is written down once, in
`.macro-assist/product_surface.py`, and the test suite enforces the one rule
that keeps it a product:

!!! note "The boundary rule (ADR-0021)"
    **Product code never imports research code.** Research may import product
    code freely — it measures it. `test_product_boundary.py` scans imports
    statically and fails on any new product → research edge, on any module
    left unclassified, and on any pinned leak that has been fixed without its
    pin being removed.

| Tier | Members | Rule |
|---|---|---|
| **Product** | `collect_and_analyze`, `llm_analysis`, `quant_context`, `conditional`, `fragility`, `fragility_or`, `fragility_panel`, `vol_forecast`, `market_data`, `fred_data`, `calendar_events`, `youtube_data`, `parse_positions`, `schemas`, `assets`, `versions`, `pipeline_common`, `pipeline_config`, `score_distributions`, `score_predictions`, `summarize_accuracy`, `bias_separation`, `portfolio/`, `refit_models`, `point_in_time` | Versioned; changed through the mode ladder and the version rule; never imports research |
| **Dormant** | `regime`, `regime_features`, `kimi_arm` | Soft-killed product ([ADR-0015](../decisions/ADR-0015-soft-kill-convention.md)); same rule |
| **Research** | `numeric_baseline`, `input_testing`, `aggregator_testing`, `companion_testing`, `fragility_backtest`, `regime_backtest`, `har_backtest`, `backtest`, `input_ledger`, `citation_screen`, `synthetic`, `exogenous/` | Free to change; never imported by product |
| **Tooling** | `bump_version`, `tag_versions` | Outside both rules |

No edge crosses the line. Two did on the day the rule was written — the live
OR flag took its data feeds from `fragility_backtest.py` — and draining them
produced `fragility_panel.py` ([resolved #20](../record/resolved.md)). The
manifest in code is authoritative if this table drifts.

A distinction worth holding: the **scorer** is product — it publishes what the
note is held to, every week, and a user can read it. The **read** of the
scorer's verdict against a bar is research. The same file serves both, and
the boundary is between the two acts, not the two tiers.

## How something enters the product

There is one door, and it has three steps. Nothing goes from an idea to the
note in fewer.

1. **An accepted finding.** A hypothesis was promoted, run once against a
   sealed slice, and its KB entry says it cleared the bar its class had
   written beforehand ([Research](../research/index.md)). Negative findings
   also change the product — by removing things — and that is the more common
   path so far.
2. **Shadow.** The component is computed and logged with zero effect on the
   note (the mode ladder, [ADR-0005](../decisions/ADR-0005-fragility-mode-ladder.md)).
   The live path is checked against the backtest numbers it was accepted on —
   KB-021 is the template.
3. **Live, with a version bump.** The stage enters `pipeline.yml`; the version
   bumps because what the note publishes changed
   ([Versioning](../reference/versions.md)); the scorer is extended if the
   new claim is scorable, and the claim is not published if it is not.

And one way out: [soft-kill](../decisions/ADR-0015-soft-kill-convention.md).
The stage leaves the pipeline; the code, tests, history and manual trigger stay.

## What is still open on the product

- The conditional table's bar is sealed, not passed. If it fails in 2027 the
  table is recorded as decoration and the product is the Fragility Monitor plus
  narrative, which is a smaller honest product rather than a larger dishonest one.
- The HAR-RV wiring publishes a variance risk premium off a fit KB-033 found
  degenerate at the live window; the fit floor is now `HAR_MIN_RETURNS = 1000`
  and the fetch periods are sized to deliver it.
- The directional scorer winds down when its last T+20 window resolves,
  ~2026-10-02. Until then the accuracy report carries both lines.

The [board](../record/active-experiments.md) is authoritative for all three.
