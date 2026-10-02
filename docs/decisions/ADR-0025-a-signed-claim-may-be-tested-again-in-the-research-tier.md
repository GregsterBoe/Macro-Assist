# ADR-0025 — A signed claim may be tested again in the research tier; the note still publishes none

| | |
|---|---|
| **Status** | **Proposed** — the owner's call in principle on 2026-10-02 ("I want to loosen ADR-0009 … I don't think the numbers that went into it are adequate for the severity of the cut"). The terms below are the assistant's draft and wait on the owner ([`todo.md`](../record/todo.md) #37). Nothing changes until they are accepted |
| **Decided** | — |
| **Related** | [ADR-0009](ADR-0009-cut-the-directional-product.md) (narrowed, not superseded) · [ADR-0020](ADR-0020-the-numeric-bar-has-a-skill-margin.md) · [ADR-0021](ADR-0021-product-and-research-are-separated-by-an-import-boundary.md) · [ADR-0022](ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md) · [ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md) · [How we explore §5, §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast) · [KB-007], [KB-022], [KB-023], [KB-024], [KB-026], [KB-027] |

## Context

**What ADR-0009 decided.** It removed `Bias` and `Confidence %` from the note
and the schema. That decision was about the **product**: the note published
~36%-accurate calls at ~63% stated confidence ([KB-007]).

**What grew out of it.** The research tier later turned the product decision
into a rule about questions. [How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
says an entry whose output is a sign "is closed before it opens".
[ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md)
§2 says a member whose claim is "it earns more" is "closed before it opens".
The auditor rejects a `signed_forecast` whatever the wording
(`auditor/instructions.md`, §9 question 2).

**What the evidence measured, and what it did not.** The owner's challenge is
that the evidence does not carry that much weight. Read against what was
actually tested, the challenge is fair for the rule, not for the product cut:

| Measured ([KB-007], [KB-022]–[KB-024], [KB-026], [KB-027]) | Never measured |
|---|---|
| **Absolute** direction (up / down) of each of the note's assets | **Relative** return: one asset or sector against another, or against an index |
| Horizons of 5, 10 and 20 trading days | Horizons of 1–12 months, where the published trend and momentum results live |
| One payload: the note's prices and daily market FRED series (20 features), the VIX term structure, the SPF anchor | Long cross-sections: the Fama-French industries (about 90 years), already in the repo for the fragility work |
| Fitted models (an LLM, ridge, gradient boosting) learning a direction from that payload | A **published rule** fixed before any look (time-series momentum, industry momentum), read as one member |

[KB-024] is strong for what it tested: 4,636 dates, the same 75,432 calls for
every arm, a positive control, a bar written first. At 20 days that is still
only about 230 independent blocks, and it says nothing about the right-hand
column. Its one stable finding, stress → reversion, is itself a signed
relationship, found and confirmed.

**What the evidence does say about any signed claim**, and should be kept:

- **The trivial rival wins by default.** `always_bullish` beat every fitted
  arm on every metric ([KB-024]). Drift is free hit-rate.
- **Stress reverts at 10–20 days** ([KB-022], [KB-024], [KB-027]). A claim
  signed "stress → down" will be read against it.
- **Confidence was anti-informative** in both the LLM and the numeric models.
- **Power is short.** The sealed slice (2018-01-01 →) is about nine years. A
  realistic active strategy (an information ratio near 0.3) needs decades to
  be told from luck.

## Decision (proposed)

**1. ADR-0009 stands for the note.** No `Bias`, no `Confidence %`, nothing
signed is published. The import boundary
([ADR-0021](ADR-0021-product-and-research-are-separated-by-an-import-boundary.md))
keeps any signed research arm out of the live path. Publishing a signed claim
needs its own ADR that supersedes ADR-0009. This one does not.

**2. The research tier admits a fifth target type: a signed claim.** A claim
about the direction, or the return relative to a stated benchmark, of an asset
or a portfolio over a stated horizon. It is admissible on four conditions.

*(a) Its class bar comes first.* Each signed class gets its own bar, written in
its own ADR before any member is proposed
([§5](../concepts/how-we-explore.md#5-the-bar-precedes-the-candidate)).

*(b) The bar contains at least:*

- **Disqualifiers first,** each driven alone by a test, as in every class.
- **The trivial rival:** `always_bullish` for a direction, the cap-weighted
  benchmark (or buy-and-hold) for an allocation. [KB-024] is why.
- **The published rival:** the generic rule of the claim's family (for
  example 12-1 momentum for a trend claim, equal-weight for a sector
  allocation). A member has to beat what a textbook already gives away.
- **A skill margin** with an interval clear of zero: ADR-0020's 0.02 for a
  probability claim, a net-of-cost active return for an allocation claim.
- **`inverted`** as its own verdict, because [KB-024]'s models were.
- **Costs** at 10 and 30 bps, as ADR-0023 charges them, and the tax brought
  forward reported, because the owner's account is taxable.
- **A power floor written before any look:** the smallest effect the sealed
  slice can tell from zero. A member whose claimed effect is smaller reads
  `underpowered` and is not read.

*(c) It is counted.* At most **two** signed members are open in the register at
once, and every look is on the ledger. WP-21.E's three-family cap on the
numeric direction search is not reset by this: families 2–3 stay under it.

*(d) A pass leads to money, never to the note.* A sealed pass is followed by a
forward paper record and the owner's money key
([ADR-0022](ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)).

**3. ADR-0023's bar does not change.** Its revisit section says the
return-as-cost-limit clause goes if ADR-0009 is revisited. This ADR keeps it.
H-009 failed that bar on cost the day before this was drafted, so relaxing it
now would move a goalpost after the data. A rule whose claim is "it earns
more" goes to a signed class instead.

**4. What changes on acceptance.**

- [How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
  is retitled and gains a fifth row, "a signed claim, under its own class
  bar". §9 question 2 changes from "never a sign" to "a sign only under a
  signed class bar".
- `auditor/instructions.md`: `signed_forecast` narrows to a signed claim
  **without** a signed class bar, or one scored as a hit rate. The
  `signed_forecast` canary is rewritten to plant that. Editing the
  instructions voids the canary certification, so `auditor_canaries.yml`
  is re-run (about $2–3) before the next audit.
- ADR-0009's *Related* line and revisit section point here. ADR-0023 §2's
  closing sentence points here.
- The register's target-space check line reads against the new table.

## Consequences

- **The research tier can now ask the questions the owner cares about:** does
  a sector or a trend rule beat its benchmark? They still have to clear a bar
  written first, against the rivals that beat everything before.
- **The pull back to the directional call is the risk** that §7 was written
  against. The cap of two, the published rival and the auditor are what hold
  it. The owner should expect most signed members to read `no_edge`,
  `explained_by_rival` or `underpowered`.
- **Power is the likely verdict.** On a nine-year sealed slice, an honest
  power floor may refuse most allocation claims before any read. That is the
  bar working, not failing. A forward paper record may be the only real test.
- **The sealed slice is shared.** Each signed class gets its own claim on
  2018-01-01 →, but the slice's market history is the same one every class
  has seen in part.
- **One candidate was named before the bar.** Sector momentum was discussed
  with the owner on 2026-10-02, before any signed bar exists. Its bar's ADR
  should say so, and the auditor should check that no number in it was chosen
  with that candidate in mind.
- **Cost:** one ADR per signed class, a canary rerun now, and one more
  multiplicity ledger.

## Would we revisit it?

- **If the first two signed members both read `no_edge`, `inverted` or
  `explained_by_rival` on their explore looks,** close the fifth row again.
  That would be the right-hand column of the evidence table measured, and
  ADR-0009's rule would then rest on it.
- **If a signed member passes its sealed read and then its forward paper
  record over at least two years,** the question becomes whether the note
  should publish it. That is an ADR superseding ADR-0009, not an edit here.
- **If the power floor refuses every signed class before a read,** the tier is
  asking questions it cannot answer on a historical slice. Move signed claims
  to forward paper only.
