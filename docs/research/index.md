# Research

Everything that is *not* the product: the harnesses that measure it, the
hypotheses about what it could become, and the findings that decide. This page
is the map. The rules are in [The method](../concepts/the-method.md) (how a
claim is refuted) and [How we explore](../concepts/how-we-explore.md) (how a
question is found); the results are in the [Knowledge Base](../record/knowledge-base.md).

Research and product are separated by an import boundary the test suite
enforces ([Product](../product/index.md), ADR-0021). Research imports product
code to measure it; product never imports research. That is what lets the
harnesses change freely and the note stay stable.

---

## The ladder

A question moves through four states. Each has its own home, its own status
vocabulary, and a code-level guarantee about what it can and cannot claim.

| State | What it is | Lives in | What it may claim | Leaves when |
|---|---|---|---|---|
| **1. Exploration** | A conjecture — something seen while doing something else, or proposed and not yet looked at. Looked at only on the **explore slice**, where the code returns `exploratory` and nothing stronger | [Hypothesis register](../record/hypotheses.md) — `draft` / `seen` / `proposed` | Nothing. An entry here has never been read against a bar | The owner rewrites it in their own words, the class bar exists, and it is `promoted` |
| **2. Confirmation** | One read of the **sealed slice** against a bar written for the hypothesis *class* before this member was chosen. Disqualifiers first; skill clause with margin; mechanism clause | Roadmap work package; the bar in an ADR or the WP; the run in CI | Exactly one of the bar's named outcomes — today `edge` / `no_edge` / `underpowered` / `miscalibrated` / `inverted`; `unexplained` once the mechanism clause of [How we explore §3](../concepts/how-we-explore.md) is in a bar | The result is a KB entry. Always — negatives included |
| **3. Accepted** | A finding the project now acts on. Positive: eligible for the product's door. Negative: something is removed, or a class is closed | [Knowledge Base](../record/knowledge-base.md) (the evidence) · [What we believe](../concepts/what-we-believe.md) (the standing conclusions) · [Decisions](../decisions/index.md) (when it changes the shape) | What its "establishes / does not establish" section says, and no more | It is superseded by a later finding, with both linked |
| **4. Product** | A component that runs in the pipeline, behind the mode ladder | [Product](../product/index.md) | What the product page's contract says | Soft-kill |

Two things about the ladder are deliberate and easy to miss:

- **State 3 is mostly negatives.** Of 32 KB entries, most closed something.
  "Accepted" does not mean "accepted into the product"; it means the project
  has stopped arguing about it. The direction-is-not-learnable finding
  (KB-024) is the most consequential accepted finding in the record and it
  removed the main feature.
- **There is no state between 1 and 2.** An exploratory number that looks
  good is not "provisionally confirmed". It is a `seen` entry with a confound
  to name, and it waits for a class bar. `verdict(sealed=False)` makes this
  a property of the code, not of anyone's discipline.

## The instruments

The research tier is a set of harnesses, each an instrument for one kind of
question. None runs in the pipeline; each is run by hand or by its own
`workflow_dispatch`, and each writes to the KB.

| Question | Instrument | Scores against | Standing result |
|---|---|---|---|
| Is direction learnable from this payload, by any model class? | `numeric_baseline.py` — walk-forward ridge / GBM / comparators, 2008–2026, sealed from 2018 | `always_bullish`; BSS with block-bootstrap interval | No — KB-024, and the same inversion in every arm. Closed for the eligible panel |
| Does a candidate fragility input have skill before it touches the live path? | `input_testing.py` — the IMP-1 gate: PIT walk-forward on a homogeneous cross-section | Drawdown label; de-overlapped AUC, episode recall / precision, lead | Absorption and turbulence graduated (KB-013, KB-014); credit redundant (KB-019); companions redundant (KB-032) |
| Can the OR flag's aggregation be improved? | `aggregator_testing.py`, `companion_testing.py` — LOCO on the crisis episodes | The plain OR at held recall / precision | No — KB-031, KB-032. Channel set and aggregation closed |
| Are the composite's weights and cut-points right? | `fragility_backtest.py` — the de-overlapped ablation | Drawdown label | `var_led_vix35`, static cuts — KB-002, KB-030 |
| Does the regime layer carry out-of-sample information? | `regime_backtest.py` | A four-feature rule | No — KB-004 to KB-006; retired |
| Does the HAR-RV forecast beat trailing realized vol? | `har_backtest.py` | Trailing 22-day RV | Only at ≥ 1000 returns — KB-033 |
| Does a label separate forward returns? | `bias_separation.py` — block permutation | Shuffled labels | Yes, backwards — KB-022; the stress-reversion mechanism |
| Does the conditional table beat the unconditional one? | `score_distributions.py` *read against its bar* — the scorer itself is product | `unconditional`, `trailing_250` | Sealed. First honest read ~2027-05 |

Every instrument carries a positive and a negative control in the test suite
([Foundations › Inference §7](../foundations/inference.md#7-controls)).

## What is in each state now

- **Exploration:** four entries in the [register](../record/hypotheses.md) —
  one `seen` with a 2026-10-07 deadline, three `draft` awaiting the owner's
  rewrite. Phase 23 in the [roadmap](../record/roadmap.md) is the harness
  they would share; nothing runs.
- **Confirmation:** Phase 22 — one sealed read pending. WP-21.E families 2–3
  have a bar and no candidate.
- **Accepted:** [What we believe](../concepts/what-we-believe.md), rewritten
  every five KB entries.
- **Queued for the product door:** nothing. No positive finding is waiting to
  be shadowed.

The [board](../record/active-experiments.md) is authoritative for this list.

---

**Read next:** [How we explore](../concepts/how-we-explore.md) if you have a
question · [The method](../concepts/the-method.md) if you have a result ·
[Foundations](../foundations/index.md) if you have a term.
