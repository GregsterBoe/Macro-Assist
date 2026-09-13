# ADR-0020 — The numeric bar has a skill margin: `EDGE_MIN_BSS = 0.02` and the BSS interval must exclude zero

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-13 — with **no candidate family on the table**, which is the whole defence |
| **Evidence** | **[KB-027]** (the +0.003 that read as `edge`) · [KB-024], [KB-026] (every prior arm's numbers, re-read under the new bar below) |
| **Related** | Closes [ADR-0017](ADR-0017-bss-floor-left-open.md) · same shape as [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md)'s `MIN_SKILL` · [The method](../concepts/the-method.md) |

## Context

[ADR-0017](ADR-0017-bss-floor-left-open.md) recorded, deliberately, that
`EDGE_MIN_BSS` stayed at **0.0** after [KB-027]: `vix_term` posted a BSS of
**+0.003** on 15,215 heavily overlapping calls and the pre-committed `verdict()`
called it an edge. The inversion defect was fixed because the pre-registration
already required it; the floor was *not* raised because the pre-registration said
nothing about a margin, and raising it with the +0.003 sitting on the table would
have been a goalpost move.

ADR-0017 named two candidate shapes for the fix — a **margin** on BSS, or a
**comparator-relative** clause ("must beat the best comparator on Brier") — and
said the choice had to be written down before family 2 runs. Family 2 has not
been chosen. That is the condition under which this can be decided honestly, and
it does not last: the moment a family is proposed, whoever proposes it has an
interest in where the bar sits.

Three facts about the harness decide which shape is right. None of them are new
measurements; they are all readable off [KB-027]'s table and the code.

1. **BSS in this project is already comparator-relative — to the arm's own base
   rate.** `_brier_and_reliability` scores against `p·(1−p)` where `p` is the hit
   frequency of the arm's *own* decisive calls. So `BSS > 0` already means "beats
   confessing your own hit-rate", and `always_bullish` sits at −0.001 by
   construction. A clause "BSS must beat the best comparator's BSS" would be the
   floor of zero under a new name.
2. **The comparator-relative *Brier* clause, as the table computes it, is
   weaker than the bar it was meant to tighten.** On [KB-027]'s sealed table
   `vix_term`'s Brier is **0.244 against `always_bullish`'s 0.246** — it *beats*
   the best comparator on Brier, by 0.002. Had the ordering been clean, that
   clause would have passed the very arm the question was raised about. The
   reason is that the two Briers are on different decisive subsets (15,215 calls
   for an arm that abstains 56% of the time, 32,525 for a constant that never
   does); a like-for-like version would have to be *paired* on the arm's own
   decisive calls, and would still need a margin or an interval to say whether
   0.002 means anything.
3. **Phase 22 already made this decision for the distribution product, before
   any data existed.** [ADR-0016](ADR-0016-phase-22-scores-the-distribution-only.md)'s
   bar is `skill > MIN_SKILL (0.02)` **and** `skill_ci.lo > 0` on 21-date
   block-bootstrap blocks, with the disqualifiers evaluated first. Two scorers in
   one repo holding "skill" to two different standards would be a defect of the
   kind this project keeps finding in itself.

## Decision

The pass clause of `numeric_baseline.verdict()` becomes:

```
n ≥ EDGE_MIN_N                                   (30, unchanged)
and ordering is not `inverted`                   (disqualifies first, unchanged — KB-027)
and decisive hit-rate > EDGE_MIN_HIT_RATE        (0.52, unchanged)
and BSS > EDGE_MIN_BSS                           (0.0 → 0.02)
and BSS block-bootstrap CI lower bound > 0       (new; 21-date blocks, BLOCK_DAYS)
```

Three changes, stated so a later reader can tell whether a proposal violates
them:

- **`EDGE_MIN_BSS = 0.02`.** The same number as Phase 22's `MIN_SKILL`, for the
  same reason: it is the smallest margin that is *not zero* and it was settled
  with no result to protect or to rescue. It is not derived from a power
  calculation. It is a written-down number, which is the property the floor of
  zero lacked.
- **The BSS carries a block-bootstrap interval, and the lower bound must clear
  zero.** The margin alone would have failed +0.003; it would not have failed
  +0.021 on the same 15,215 calls, and nothing about those calls is more
  independent at 0.021 than at 0.003. The interval is what says whether the
  number is distinguishable from zero; the margin is what says it is worth
  having. Both are required, as in [ADR-0016]. The blocks are `BLOCK_DAYS = 21`
  report-dates, the unit `bias_separation` and `score_distributions` already use,
  so all three readers agree on what "independent" means.
- **The `aligned` ordering no longer buys a pass on its own.** The old clause was
  `hit > 0.52 AND (BSS > 0 OR aligned)`: an arm with a wrong-signed calibration
  could pass on a hit-rate and an ordering label. [KB-027] showed the ordering
  label is weak on a near-zero effect in *both* directions — "`inverted` is a
  weak label on a near-zero effect, exactly as `edge` was" — and the report's
  own preamble says a model that edges past 0.52 while `always_bullish` sits
  there "has shown nothing". Calibration is now required in every case; the
  ordering remains a disqualifier and a reported diagnostic, not a pass route.

Applied to every arm this project has ever scored, **no label changes**:

| Run | Arm | BSS | Old verdict (corrected) | New verdict |
|---|---|---|---|---|
| [KB-024] | `ridge` / `gbm` | −0.087 / −0.059 | inverted | inverted |
| [KB-026] | `exogenous_spf` / `market_plus_exo` | −0.030 / −0.124 | no edge | no edge |
| [KB-027] | `vix_term` | +0.003 | inverted | inverted |
| [KB-027] | `market_plus_vixterm` | −0.083 | inverted | inverted |
| all | `always_bullish` / `random_walk` | −0.001 / −0.012 | no edge | no edge |

That is the test that this is not a goalpost move: a bar that relabels nothing
in the record was not chosen to relabel anything. The one hypothetical it
changes is the one [ADR-0017] left open — `(hit 0.573, BSS +0.003, aligned)`
was `edge` and is now `no edge` — and it is pinned by a test in place of
`test_the_bss_margin_was_deliberately_left_alone`, which asserted the opposite
and is retired with this decision.

## Consequences

- **[ADR-0017] closes; WP-21.E families 2 and 3 are unblocked.** The cap of
  three families stands. The honest prior on them is unchanged and low.
- **The pre-registration for families 2 and 3 is this bar, not WP-21.A's.**
  `roadmap.md` → WP-21.E condition 3 said "the bar is the one already written";
  from here it reads "the bar is [ADR-0020]". A family that clears the *old*
  clause and not this one is a null, and saying so afterwards is not a defence.
- **Cost: a bar this tight will not be cleared by a marginal input, and that is
  intended.** Something with BSS +0.02 and a CI clear of zero on the sealed
  slice is a real signal on this panel. The project has never seen one. If the
  search closes with three nulls, WP-21.E's own pre-registration says the search
  closes for good.
- **Cost: the harness grows a bootstrap it did not have.** `evaluate()` must
  carry the report-date of each decisive item into the calibration block so the
  BSS can be resampled by block; the machinery exists (`bias_separation._blocks`,
  `score_distributions.block_bootstrap`) and the draws are the existing
  `SEPARATION_DRAWS`. Runtime cost is small next to the separation section, which
  already dominates the 1h 52m.
- **Cost: the published [KB-027] report is now two edits behind the function.**
  It shows `edge` (pre-correction) where the function now says `inverted`, and
  its preamble states `BSS > 0`. [KB-027] carries both columns and this page
  carries the third; the report on `origin/output` is not rewritten (ADR-0001).
  The *next* run's report prints the new bar in its preamble.
- **Not changed:** `EDGE_MIN_N`, `EDGE_MIN_HIT_RATE`, the seal, the disqualifier
  order, the comparators, and `score_distributions` — which already implements
  this shape and is the reference for it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Margin only** (`EDGE_MIN_BSS = 0.02`, no interval) | Cheapest; fails +0.003. But it passes +0.021 on the same overlapping calls with no statement about whether 0.021 is noise. [ADR-0016] requires both for the same reason. |
| **Comparator-relative Brier, as the table computes it** | Would have *passed* `vix_term` (0.244 vs 0.246) — see fact 2. Unpaired, so not like-for-like, and still needs a margin. |
| **Paired comparator-relative Brier** (arm vs `always_bullish` on the arm's own decisive calls, block CI on the difference) | The most principled version of that idea and it is not wrong. Rejected for now because it is a second yardstick next to the BSS one every KB entry reports, and because it needs a per-call join across arms that `evaluate()` does not do. If a family ever clears this bar, run the paired test as the confirmation before the column comes back — a pass here plus a paired loss to the constant would be [KB-024]'s lesson again. |
| **A power-derived margin** | Would be more defensible than 0.02 in principle, but the honest power calculation on this panel — three overlapping horizons, six correlated assets, ~2,261 sealed dates — depends on choices (effective sample size, correlation structure) that are themselves contestable after the fact. A fixed number the record cannot argue with beats a derived number it can. |
| **Leave it at zero and rely on the inversion disqualifier** | The disqualifier is a *sign* check; it does nothing for an arm that is aligned by chance at +0.003. That is exactly the case [ADR-0017] said needed deciding. |

## Would we revisit it?

- If a family clears this bar, run the **paired** comparator test above before
  restoring the column; if it fails that, the bar was too loose and this page
  should say so.
- If Phase 22's sealed read (~2027-05) leads to a different `MIN_SKILL`, the two
  bars should move together — one standard for "skill" across the repo.
- Not because a family posts +0.015 with a clean interval. That is the case this
  margin exists for, and it was set with no such result in view.
