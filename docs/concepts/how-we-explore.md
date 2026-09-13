# How we explore

> **Status: draft, 2026-09-13.** Written before any exploration has run under it,
> which is the only honest time to write it. Nothing here is a source of truth
> for a number. The companion page, [The method](the-method.md), is the
> *refutation* side of the project; this is the *generation* side, and it exists
> because the refutation engine has run out of its kind of question.

---

## Why this page exists

The method is very good at one thing: taking a candidate and killing it
honestly. It deleted the project's headline feature ([the cut](the-cut.md)),
caught its own bar being wrong ([KB-027]), and caught a green CI run that had
tested nothing ([KB-025]). Of 33 Knowledge Base entries, most are negatives, and
that is the design working.

But it is a filter, not a generator, and the board on 2026-09-13 shows what
happens when the generator runs dry:

- *"The IMP-1 candidate list is exhausted; nothing is queued on the fragility
  track."*
- *"WP-21.E families 2 and 3 — unblocked, not chosen, honest prior low."*
- WP-18.4 gated on a metric that no longer exists.

Every remaining queued idea is **another input to a question that has already
been closed three times** ([KB-024], [KB-026], [KB-027]). A fourth indicator
family for direction is not a hypothesis; it is a re-run.

Meanwhile the one thing the project actually *discovered* — not a product, a
mechanism — is filed under "why the models fail" and has never been walked
toward:

!!! quote "[KB-024], and again in [KB-022] and [KB-027]"
    Stress → bearish signal → stress mean-reverts at 10–20 days → rally.
    `drawdown` is the only input both model classes find load-bearing, and it is
    signed this way. Bearish calls precede the *highest* forward returns.

Three independent runs found the same relationship. It is the most robust
empirical statement in the repository, and it is currently used only as an
explanation of a negative.

## Where the framing comes from

Terence Tao's description of research as a hike: you set out for a waterfall you
have heard about, you get lost, and the notes you make while lost — the other
phenomena, the more spectacular waterfall glimpsed in the distance that you
cannot reach yet — are often worth more than the destination. The tools we now
have are helicopters: they fly straight to the named goal and back, and you
learn nothing about the terrain.

Three of his points bear directly on this repository.

**A bar that scores the answer would have discarded Copernicus.** The
heliocentric model initially fit the data *worse* than the tuned geocentric one.
Our confirm bar — beat `always_bullish` on a sealed slice, BSS > 0.02, interval
clear of zero ([ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md))
— is the correct filter for a *product decision*. It is the wrong filter for
*exploration*, because it cannot tell a wrong idea from a right idea that is not
yet well-fitted. What made [KB-024] conclusive rather than merely discouraging
was not a number, it was that the mechanism was legible.

**These tools are strong at breadth, weak at depth.** Pointed at a thousand
problems they solve a random five percent; pointed at the one hard problem they
guess. The project has, correctly, capped breadth on the *confirm* side (a hard
cap of three families, one sealed slice). It has never given breadth a place to
happen on the *explore* side where it is actually useful.

**The helicopter risk is the assistant.** The failure mode is concrete: the
hypothesis, the bar, the run, the read and the KB entry are all produced in one
session, the record looks rigorous, and the owner could not reproduce any of it
alone. The skill accrues to the tool. Everything below is arranged so that the
one artefact that must be the owner's — the hypothesis and its pre-registration —
cannot be delegated.

---

## 1. Two tiers, separated by code

Exploration and confirmation are different activities with different rules, and
they must not share a surface.

| | **Explore tier** | **Confirm tier** |
|---|---|---|
| Data | The explore slice only — never the sealed slice | The sealed slice, once |
| Breadth | Unbounded, but **counted** (§4) | One promoted hypothesis at a time |
| Bar | None. There is nothing to pass | Pre-registered, written *before* the candidate is chosen (§5) |
| Output | An entry in the [hypothesis register](../record/hypotheses.md) | A Knowledge Base entry, either way |
| What the code returns | `exploratory`, and structurally nothing stronger | A verdict |
| Who decides what runs | Either | The owner, in writing, dated |

The separation already exists in the codebase and only needs to be respected:
`numeric_baseline.SEAL_START` (2018-01-01) splits the historical panel into an
explore surface (~2009–2017) and a sealed holdout; `verdict(sealed=False)` can
only return `exploratory`; Phase 22's seal is dated 2026-09-07 on the live
record. **Which seal governs a promoted hypothesis is itself a decision to
write down before the first promotion** — the 2018+ slice was sealed for
*directional* families, and reusing it for a different question is defensible
only if the multiplicity ledger records it.

The explore tier does not touch the published note, the sealed table, or
`pipeline.yml`. A shadow computation that runs alongside the product and is
scored by the same scorer is the pattern ([ADR-0005](../decisions/ADR-0005-fragility-mode-ladder.md)'s
`log` rung, generalised).

## 2. The hypothesis register

Tao's note of the waterfall in the distance. A record of things *seen* and
things *proposed*, held to a fixed format so that an interesting pattern cannot
quietly become a claim.

The prototype already exists in the repo, and it is worth reading as the model:
[KB-026]'s "one unpre-registered observation, flagged as a hypothesis and not a
result" — a monotonically ordered confidence signal, the first ever measured
here, with its confound named, the artifact that would test the confound
located, and a deadline attached. That is exactly what an entry looks like.

The format, fixed like the KB's:

**What was seen → where (run, table, line) → the mechanism it would imply →
the confound that would explain it away → what would test it → the target
space check (§7) → what to read first.**

An entry has a status: `seen` (observed in data, unplanned), `proposed` (a
question, not yet looked at), `promoted` (a bar has been written and the
confirm run is scheduled), or `closed` (→ KB pointer). A `draft` entry is one
that has not yet been rewritten by the owner in their own words, and a draft is
not a hypothesis (§6).

The register lives in `docs/record/`, next to `todo.md`, and is different from
it: `todo.md` holds decisions and carried findings; the register holds
*conjectures*. When a conjecture becomes a decision ("promote H-002"), the
decision goes to `todo.md` / `resolved.md` as usual.

## 3. Mechanism first

Every entry states the mechanism it is probing, and the mechanism must make at
least one prediction that is **not the skill number**. [KB-024]'s mechanism
predicts a sign structure — the bearish-minus-bullish forward-return gap is
positive and grows with horizon — and that structure was checked, independently
of the Brier score, in three runs.

The confirm-tier bar for a promoted hypothesis therefore carries a **mechanism
check** next to the skill clause. An arm that clears the number but whose
predicted structure fails is `unexplained`, not `edge`. This is the Kepler
clause: a fit without a mechanism is the tuned geocentric model, and this
project already knows what a product looks like when it scores well against
nothing ([the method §4](the-method.md#4-always-put-a-trivial-rival-next-to-the-product)).

## 4. Breadth is allowed, and counted

The explore tier may look at many things. The condition is that every look is
**written down before promotion**, in a multiplicity ledger: what was tried, on
which slice, how many variants, what was seen. When a hypothesis is promoted the
ledger travels with it, and the confirm bar is written knowing the family size.

This is the honest form of breadth. The alternative — a hard cap — is a confirm
tier concept and it is right there. On the explore side a cap only pushes the
looking somewhere unrecorded.

The ledger is the register itself: an entry's "where" field and its variant
count. There is no second document.

## 5. The bar precedes the candidate

[ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md) was
decided "with no candidate family on the table, which is the whole defence".
That trick becomes the rule: **a confirm bar is written for a *class* of
hypothesis before any member of the class is promoted.** A bar for "a shadow
conditioner against `unconditional`" exists before anyone proposes which
conditioner. A bar for "a quarterly gap against realized width" exists before
anyone proposes which gap.

When the bar exists first, the assistant's enthusiasm about a specific candidate
is never load-bearing, because nothing about the candidate can move the number.

## 6. The owner writes the hypothesis

This is the anti-helicopter rule and it is the one that costs the most.

The assistant may run the breadth, build the plumbing, pull the artifacts,
draft the entry, and write the KB entry after the run. The assistant does **not**
author the pre-registration text of a promoted hypothesis. That text — the
mechanism, the prediction, the confound, the bar — is written by the owner, in
the owner's words, and a draft written by anyone else is marked `draft` until
that has happened.

The check that this is real rather than a formality is a competence gate. Before
promoting a hypothesis, the owner should be able to do the following **without
the assistant**, and the register entry lists which of them it depends on:

- Trace one number in today's note back to the line of code that rendered it,
  and say which stage of `pipeline.yml` produced its input.
- Reproduce one KB table from its reproduce block, and check the metadata line
  [KB-025] says to check before reading a number.
- Explain why `verdict(sealed=False)` can only return `exploratory`, from the
  code, not from this page.
- Say what `SEAL_START` is, why it is a calendar date and not a fraction, and
  what would be lost by moving it.
- State the [KB-024] mechanism and the sign structure it predicts, and find the
  table in [KB-027] where it was checked.
- Say what `assets.forward_change()` returns for the 10Y, and why
  ([ADR-0011](../decisions/ADR-0011-canonical-asset-registry.md)).

None of these is hard. All of them are the difference between owning the
finding and being flown to it.

## 7. The target space: never a signed forecast

The strongest gravitational pull in this repository is back toward the
directional call. Any exploration whose output is *a sign with a confidence
attached* is [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md)
territory in a new coat, regardless of how the question is phrased.

The safe target space, each with a scorer that exists or could:

| Target | What "better" means | Scorer |
|---|---|---|
| A **distribution** — location, width, tails, quantiles | Lower pinball loss than `unconditional` on the same sample | `score_distributions.py`, as is |
| A **state** — fragile / not, regime | Recall and precision on labelled episodes, PIT thresholds | `fragility_backtest.py`, `input_testing.py` |
| A **gap** — between two consensus sources, or between a source and its later realization | Predicts a realized *width* or *surprise magnitude* | Does not exist; would need writing |

Every register entry carries a one-line check against this table. If the
honest answer is "the output is a sign", the entry is closed before it opens.

## 8. Digestion has a cadence

Tao's *proof indigestion*: generation outpacing understanding. The Knowledge
Base is ~190 KB and [What we believe](what-we-believe.md) is its textbook. The
2026-09 documentation passes were digestion; they should not be one-offs.

Rule: **every five KB entries, or any time an entry changes a standing belief,
[What we believe](what-we-believe.md) is rewritten, not appended.** The check
is that the page stays readable in one sitting. The maintenance log records the
pass.

---

## The short version

1. Two tiers, separated by code. Explore never touches the sealed slice.
2. Things seen while lost go in the register, in the fixed format, with the
   confound named.
3. State the mechanism, and make it predict something that is not the score.
4. Look at as much as you like — and count every look.
5. Write the bar for the class before choosing the member.
6. The owner writes the hypothesis. A draft is not a hypothesis.
7. The output is a distribution, a state or a gap. Never a sign.
8. Rewrite the textbook every five entries.

---

**Next:** the [hypothesis register](../record/hypotheses.md) — what has been
seen, and what is proposed.
