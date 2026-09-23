# What is worth doing

> **Status: empty, 2026-09-23.** A scaffold, not a page. Every section below is
> a blank for the owner to fill in their own words. Until it is filled this page
> is not a source of truth for anything and nothing should cite it. Delete this
> banner when it is written, and date it.

---

## Why this page exists

[How we explore §5](how-we-explore.md#5-the-bar-precedes-the-candidate) says a
confirm bar is written for a *class* before any member of the class is proposed
— [ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md) was
decided "with no candidate family on the table, which is the whole defence."
This page is the same move one level up: **the criteria for what makes a track
worth pursuing, written before the open tracks are ranked against them.**

Without it, any ranking of open work is a mirror. It returns whatever the last
document read sounded enthusiastic about — and that is as true of the owner on a
tired evening as it is of a model asked "what should we do next". The repo has a
board for *what is running*, a roadmap for *what is planned*, and 21 ADRs for
*why the system has the shape it has*. Nothing anywhere says what any of it is
**for**, or how to tell a track that has lost the goal from one that is merely
slow.

Two readers, and the page has to work for both:

- **The owner**, deciding whether to promote, continue, or kill.
- **A screen** that scores every open board row and inbox item against §4 and
  §5 below and prints the drift. A screen can only score against criteria that
  are written down.

**One rule while filling it in:** no section may name a track that is currently
open. If a goal can only be stated as "finish Phase 23", it is not a goal, it is
a plan, and it belongs in the roadmap.

---

## 1. What this project is for

> *One paragraph. If the whole repository were deleted, what would be lost —
> stated as a capability or a kind of knowledge, not as a list of features?*
>
> *[The cut](the-cut.md) is the precedent worth reading first: the headline
> feature was deleted and the project survived, so whatever survived it is
> pointing at the answer.*

_(unwritten)_

---

## 2. The standing goals

> *Two to five. More than five is not a goal set, it is a backlog.*
>
> *Each row needs all three columns. The second column is the one that does the
> work: a goal you cannot tell you have reached is a mood. The third is the
> near-miss the goal is most likely to be confused with.*

| Goal | What would count as having reached it | What it is **not** |
|---|---|---|
| _(unwritten)_ | | |
| _(unwritten)_ | | |
| _(unwritten)_ | | |

> *Then, in prose: which of these is first when two of them conflict, and why.
> They will conflict.*

_(unwritten)_

---

## 3. What this project is deliberately not doing

> *The exclusions, each with the reason and a pointer if one exists. One is
> already decided and belongs here:
> [ADR-0009](../decisions/ADR-0009-cut-the-directional-product.md) — no
> directional call, no signed forecast with a confidence attached
> ([how-we-explore §7](how-we-explore.md#7-the-target-space-never-a-signed-forecast)).*
>
> *What else? An exclusion written down here is worth more than an exclusion
> that has to be re-argued every time it comes up.*

_(unwritten)_

---

## 4. How two open tracks are ranked

> *An ordered list of criteria, most important first. This is the section a
> screen reads, so each criterion has to be answerable about a track from the
> record alone — not from remembering the conversation it came out of.*
>
> *Prompts, not answers:*
>
> - *Does it advance a goal in §2, and which one?*
> - *What does the project learn if it comes back negative? (Convention #2 says
>   a negative is logged; a track whose negative teaches nothing is a track
>   whose positive probably would not either.)*
> - *Is the question already closed? Three of this repo's KB entries closed the
>   same question. A fourth input to a closed question is a re-run, not a track.*
> - *What does it cost in owner attention, as distinct from compute or
>   assistant time — see §6.*
> - *Does it raise the price of other work? Every counted explore look enlarges
>   the multiplicity ledger that a later promotion's bar must be written
>   against ([§4](how-we-explore.md#4-breadth-is-allowed-and-counted)).*

_(unwritten)_

---

## 5. When a track stops

> *The kill criteria, written before the tracks they will be applied to.*
>
> *This section is the one the owner is best placed to write and the assistant
> is worst placed to: noticing that work has quietly lost its goal is a judgment
> the record cannot make for itself. Written down, it becomes a rule that fires
> on its own instead of a feeling that has to be re-derived each time.*
>
> - *What makes a track dormant rather than dead?
>   ([ADR-0015](../decisions/ADR-0015-soft-kill-convention.md) is the code
>   analogue — deactivate, never delete.)*
> - *How long may a board row sit with no edit before it must be defended or
>   closed? (`record_audit.py` 24.E already prints the ages; nothing reads
>   them against a threshold, because no threshold exists.)*
> - *What is the tell that a track has become its own justification?*
> - *Who closes it, and where does the reasoning go — `resolved.md`?*

_(unwritten)_

---

## 6. The scarce resource

> *Name what is actually in short supply and how much of it there is.*
>
> *The candidate answer is owner attention, and it matters which parts of it:
> [§6 of how-we-explore](how-we-explore.md#6-the-owner-writes-the-hypothesis)
> makes the owner the only one who may author a promoted hypothesis and pass
> the competence gate, so that attention is not substitutable by anything.
> Everything else in the project is.*
>
> - *Roughly how many hours a week, and in what size blocks?*
> - *Which activities may consume it, and which must not?*
> - *What is the throughput this implies — promotions per quarter, say — and is
>   the current queue consistent with that number?*

_(unwritten)_

---

## 7. When this page is rewritten

> *[§8 of how-we-explore](how-we-explore.md#8-digestion-has-a-cadence) puts
> [What we believe](what-we-believe.md) on a cadence: rewritten, not appended,
> every five KB entries. This page needs its own trigger.*
>
> *Candidates: on a closed phase, on a goal being reached, on a kill under §5,
> or on a fixed date. Pick one and say where the pass is recorded
> (`maintenance-log.md`?).*
>
> *Rewritten, not appended — the same rule. A goals page that only grows is a
> backlog with a different title.*

_(unwritten)_

---

**Next:** [How we explore](how-we-explore.md) — the rules a conjecture passes
before it becomes a hypothesis. This page is what decides whether it was worth
conjecturing about in the first place.
