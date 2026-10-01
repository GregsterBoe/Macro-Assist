# ADR-0024 — The daily note makes no LLM call: the Fragility Monitor, a volatility-targeting dial and the conditional distributions

| | |
|---|---|
| **Status** | **Accepted** — decided by the owner 2026-10-01 ("remove the agent output from the daily note and reduce it to a volatility targeting and fragility monitor, since I don't think I need the cost"), drafted and built by the assistant the same day. Live from the first note after the push (v2.2, stamped from 2026-10-02) |
| **Decided** | 2026-10-01 |
| **Related** | [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0002](ADR-0002-structured-output-contract.md) and [ADR-0003](ADR-0003-four-narrow-agents.md) (dormant while this holds) · [ADR-0015](ADR-0015-soft-kill-convention.md) · [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md) · [ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md) · [KB-024], [KB-033] |

## Context

**What the model still wrote.** After [ADR-0009](ADR-0009-cut-the-directional-product.md)
cut Bias and Confidence (v1.6), the LLM pass wrote the note's prose: an
executive summary, the macro dashboard, four asset sections, a portfolio risk
read, sector research, key risks, and a *Primary Driver* and *Target Range*
for each asset. None of it was scored. The one LLM-authored falsifiable claim,
the Target Range, had no stated coverage and no scorer (`todo.md` #7).

**What the record says carries information.** Everything with a measured
result in the note is computed, not written: the Fragility Monitor ([KB-017],
[KB-021]), the HAR-RV volatility forecast ([KB-033]) and the conditional
distributions that Phase 22 scores ([ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md)).
Phase 22 reads `results/quant_context_log/`, which the quant layer writes
before the model is called, so the model never touched the scored record.

**What the research found about acting on stress.** Every attempt to beat
simple volatility in this repo failed. H-008 and H-004 could not improve on the
volatility forecast. H-009's fragility-timed rule lost to a volatility rule at
the same exposure. IMP-9's two filters ([KB-035], [KB-036]) did not make the OR
flag selective. The rule that kept winning is the textbook one: hold less when
volatility is high.

**The cost.** One `claude-opus-4-8` call per weekday, plus the Haiku sub-agents
and the YouTube transcript fetch, for prose the owner judged not worth it.

## Decision

1. **The note makes no LLM call.** `collect_and_analyze.py` builds the body
   from the logged quant reading. In order: the Fragility Monitor (unchanged), a
   new **Volatility Targeting** block, the **5-Day Outlook** as the conditional
   distribution alone, then the data snapshot (unchanged). The frontmatter keeps
   every key its readers parse, and records `model: none`, `profile: none`.
2. **The volatility-targeting dial.** For each asset with a HAR-RV forecast
   (S&P 500, Gold, WTI, Bitcoin), the dial is *hold = typical ÷ forecast*,
   capped at 100% and rounded to 5%. *Typical* is the asset's volatility over
   the fetched 5 years, on the forecast's own scale. The dial reads as a share
   of the owner's **normal** position, so the owner's allocation stays the
   owner's, and the dial never says hold more than normal (no leverage).
   `typical_vol` and `exposure` are logged with the forecast in
   `vol_forecasts`, so the note cannot publish a dial the record does not hold.
3. **It is labelled as the standard rule, not a finding.** The note says it
   is a risk dial, makes no directional claim, and has not been measured here
   as adding return.
4. **A soft-kill, not a deletion** ([ADR-0015](ADR-0015-soft-kill-convention.md)).
   `llm_analysis.py`, the prompts, the schemas, their tests and every saved
   note and payload stay. The repo variable `NOTE_ANALYSIS=llm` restores the old
   note with no code edit. The secrets stay wired and are unused while it is off.
5. **Minor version, v2.2.** It changes what the note publishes, but not the
   kind of claim: 2.x measures, and makes no directional call.

## Consequences

- **The daily run costs no API money.** What is left to pay for is
  owner-dispatched only: the auditor (`audit_entry.yml`, its canaries) and
  `model_compare.yml`.
- **Phase 22 is untouched.** Its input is the quant log, written exactly as
  before. The sealed clock and the ~2027-05 first read stand.
- **IMP-8 is moot.** It asked which model should write the note, and now none
  does. It closes unrun, with no measurement and so no KB entry.
- **`todo.md` #7 is moot.** The Target Range is no longer published. Deferred
  #1b is done: the note now carries the computed table itself, not the model's
  prose copy of it. Carried finding #11 (splitting `llm_analysis.py`) has no
  reason left while the module is dormant.
- **What is lost.** The prose summary, the portfolio risk read of the owner's
  positions, the sector research and the calendar of coming events. None of it
  was scored, so nothing measured is lost. But the owner may miss reading it.
  That is what decision 4 is for.
- **The dial is unvalidated here.** The literature on volatility management is
  mixed out of sample (Moreira & Muir 2017; Cederburg et al. 2020). This
  project measured it only as a rival, in H-009's look on the explore slice,
  where it took smaller drops than a fragility rule at the same exposure. It is
  published because it is the honest, simple default, not because it passed a
  bar. Whether it is worth following is the owner's call.
- **The typical level moves.** A 5-year window means a long calm stretch lowers
  *typical* and makes the dial cut sooner. A long rough stretch does the
  opposite. That is a property of the window, stated here so it is not read as
  a signal.
- **The Phase 20 paper book still has no input**, as since v1.6. The new note
  keeps the `### 5-Day Outlook` heading that `note_is_post_cut` reads, so the
  book declines to advance for the same reason it did before.

## Would we revisit it?

- **If the owner misses the prose,** set `NOTE_ANALYSIS=llm` for as long as
  wanted. It is a variable, not a decision to reverse. If it stays on for good,
  supersede this page.
- **If someone proposes acting on the dial with real money,** it goes through
  goal 3's risk-rule class ([ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md))
  as a member with its own entry, against the same rivals. The note's dial is a
  reading aid, and publishing it is not a pass.
- **If the Phase 22 read (~2027-05) finds the distributions carry no skill
  over an unconditioned one,** the 5-Day Outlook block is the next thing to
  question, under the same reasoning as this page.
