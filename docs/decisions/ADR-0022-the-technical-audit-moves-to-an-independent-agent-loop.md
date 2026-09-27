# ADR-0022 — The technical audit moves to an independent agent loop; the owner keeps the goals, the seal key and the money gate

| | |
|---|---|
| **Status** | Accepted — drafted by the assistant at the owner's request, accepted by the owner the same day (`resolved.md` #32). Switched on only when the auditor has rejected every canary (Phase 25) |
| **Decided** | 2026-09-27 |
| **Related** | [How we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis) (the rule it changes) · [ADR-0020](ADR-0020-the-numeric-bar-has-a-skill-margin.md) (the bar precedes the candidate) · [ADR-0019](ADR-0019-paper-portfolio-mechanical-and-paper-only.md) (the money side) · [What is worth doing](../concepts/what-is-worth-doing.md) (the goals the owner keeps) |

## Context

[How we explore §6](../concepts/how-we-explore.md#6-the-owner-writes-the-hypothesis)
makes the owner the only party who may write a promoted hypothesis, and puts a
six-item competence gate in front of every promotion: trace a number in the note
to its line of code, reproduce a KB table, explain `verdict(sealed=False)` from
the code, and three more like them. Its reason is on the page and is still
right: *"the hypothesis, the bar, the run, the read and the KB entry are all
produced in one session, the record looks rigorous, and the owner could not
reproduce any of it alone."*

Two weeks under it measured the cost:

- **Nothing has been promoted.** §6 was written 2026-09-13. On 2026-09-27 the
  register holds eight entries: six wait on the owner's rewrite (H-003 to
  H-008), one was closed by the owner (H-002, 2026-09-24), none has reached
  `promoted`. `/orient` has printed the gate at the start of every session since
  WP-24.G shipped on 2026-09-21.
- **One worksheet item took a whole session.** Walking the owner through the
  first of H-002's ten worksheet items — *which "Elevated" instrument* — needed
  five modules read and three scratch scripts before there was anything to
  decide.
- **The owner's situation.** The owner works full-time elsewhere and does not
  read the code in this repository. Most of the gate's items are about the code.
  Held to them, the queue does not move. Routed around them quietly, the gate
  becomes a formality — the failure §6 exists to prevent.

The owner's own read, 2026-09-27: they trust an AI loop more than themselves on
the technical checks, and they want to keep understanding what the project
believes.

Taken apart, §6 was doing three jobs:

1. **Technical correctness.** Is every look counted, the seal untouched, the bar
   older than the data, the code doing what the entry says? Most of this is
   already code here (`SEAL_START`, `verdict(sealed=False)`, the
   disqualifier-first tests, `record_audit.py`). Where it is not, a model reading
   the code does it more consistently than a part-time owner.
2. **Independence.** Whoever proposes a hypothesis must not be the one who
   judges it. This is §6's real point; the owner was simply the only independent
   party available.
3. **Values.** Which decisions matter, how much risk to accept, when a track has
   lost its goal. Only the owner can do this, and none of it needs the code.

**A conflict of interest, stated.** This page was drafted by the assistant — the
proposer whose reach it widens. The owner's acceptance is the check on that, and
it is why the page is Open until then.

## Decision

The technical audit — jobs 1 and 2 — moves from the owner to an **auditor that
is independent of the proposer by construction**. The owner keeps job 3 and the
two irreversible actions.

### Four parties

| Party | Does | Never |
|---|---|---|
| **Proposer** — the assistant in a working session | Drafts register entries, runs explore looks, builds decision packets, writes the KB entry after a read | Judges its own entry; runs a promotion-tier audit and reports the result itself |
| **Auditor** — a separate agent | Answers [§9](../concepts/how-we-explore.md#9-the-checklist-an-entry-passes-before-it-is-promoted) against the entry; hunts the confound, the goalpost move, the uncounted look; writes the owner's brief | Sees the proposer's conversation or its argument; approves by default |
| **Code checks** | The seal, `verdict()`, `record_audit.py`, the look count | Give way to a model's opinion — when a check and a model disagree, the check wins |
| **Owner** | The goals page; the seal key; the money gate; a veto on any promotion | Has to read code to do any of it |

### What makes the auditor independent

The design is aimed at **slips and motivated reasoning, not fraud.** The
proposer is not trying to deceive. It talks itself into tidy stories and makes
accidental mistakes. Each mechanism below names what enforces it.

**The auditor cannot be steered by the proposer:**

- **Fresh context, fixed inputs.** The auditor starts with no conversation. It
  reads a bundle that code assembles — the pre-registration, the raw report, the
  diff, the look ledger — and never the proposer's summary of its own case.
- **Adversarial instructions, default reject.** It is asked what is wrong, never
  whether the entry is good. Approval means it found nothing blocking.
- **Its instructions are frozen against the change it judges.** One change may
  not both edit the auditor's instructions and promote an entry. A CI check
  enforces this, the way `test_product_boundary.py` enforces the import rule.
- **It writes the owner's brief,** with the strongest case against first. A
  brief written by the proposer would be persuasive by construction.

**The proposer cannot shape the verdict:**

- **Promotion-tier audits run in CI, and CI records the result.** The proposer
  does not run them and pass the answer on.
- **An approval is stamped to the exact text it approved.** Any later edit voids
  it, and a code check blocks the promotion.
- **No grinding.** Each resubmission after a rejection counts as a look in the
  ledger. After two rejections the entry closes or goes to the owner. Without
  this limit the auditor becomes a target to optimise against, and something
  eventually passes by attrition.
- **The bar must be older than the result,** by git history. `record_audit.py`
  checks it.
- **No number without a receipt.** The explore harness logs every run itself,
  and every number in a register entry must match a logged run. The ledger stops
  being self-reported.

**The auditor is itself tested:**

- **Canaries.** A small set of deliberately defective entries — a bar written
  after the data, a claim that is secretly a signed forecast, a read of the
  sealed slice, a cell resting on two episodes — which the auditor must reject,
  re-run on a schedule. This is convention #7's *disqualifiers fire first, with a
  test* applied to the judge: an auditor that has never rejected anything has not
  been tested.
- **A second model family at the high-stakes tiers.** Agents on one model share
  blind spots. For promotions and sealed reads, a second auditor from another
  provider reads the same bundle, and a disagreement goes to the owner. The
  dormant `kimi_arm` is existing plumbing for a second provider.

### Scaled to what is at stake

| Event | Reversible? | Audit | Owner |
|---|---|---|---|
| Explore look | yes | local, fresh-context auditor | nothing — it appears in the digest |
| Promotion (writes the member's bar) | partly | CI auditor, stamped, counted; second provider | reads the brief; may veto |
| Sealed read | **no** | as above, re-checked against the stamped text | **turns the key** |
| A rule acting on real money | **no** | as above | **turns the key**, and can state the rule, what it costs when wrong and when to stop using it, in their own words |

**The seal key** is an action only the owner's account can take: a GitHub
Actions environment with the owner as required reviewer, so the sealed-read job
waits until they approve it in GitHub. The assistant's credentials must not be
able to take that action. The split is verified when the key is built, or the
key is decorative.

**The owner's interface** is the brief (one per promotion and per key) and a
short periodic digest of what changed in
[What we believe](../concepts/what-we-believe.md). Not the code.

### The register

`draft` keeps its place and changes its meaning: *written by the proposer and
not yet through an audit — not a hypothesis.* An entry leaves `draft` by passing
an audit, not by the owner rewriting it.

### What this does not do

- **It is not retroactive.** H-003 to H-008 go through the audit from scratch.
  Nothing inherits a pass, and nothing already seen is relabelled as
  pre-registered.
- **It does not switch on when accepted.** Until the auditor exists and has
  rejected every canary, nothing is promoted by audit, and the rule §6 replaced
  still governs a promotion. §6 carries this as its *Until the auditor is
  switched on* subsection; deleting that subsection is the switch, and `orient.py`
  follows the page. Accepting this page schedules the change; passing the
  canaries switches it on. There is never a window with neither rule in place.
- **It does not relax any bar.** The class bar, the mechanism clause, the
  `underpowered` floor, one sealed read per class, negatives to the Knowledge
  Base — all unchanged. What changes is who checks them.

### On acceptance, these change

- [How we explore](../concepts/how-we-explore.md) §6 (rewritten to the four
  parties above), §9 question 12, and item 6 of *The short version*.
- `CLAUDE.md` — convention #7's last sentence, and the Current-state
  *Exploring* row.
- [The hypothesis register](../record/hypotheses.md) — the header's definition
  of `draft`.
- `orient.py` — the gate's heading. Its bullets are read from §6, so they follow
  the page on their own.
- `decision_packet.py` — question 12 stops being "no field owns it" and becomes
  "does a stamped audit record exist".
- [Operations](../reference/operations.md)' `COMPETENCE GATE` row,
  [Foundations](../foundations/index.md)' competence-gate item, and the §6
  prompt in [What is worth doing](../concepts/what-is-worth-doing.md).
- The roadmap gains a phase for the build, in this order: auditor instructions,
  input bundle and canaries; the four `record_audit.py` checks (bar before
  result, approval stamp, instruction freeze, receipts); the CI audit job; the
  seal key with the credential split verified; the second provider last.

## Consequences

- **The queue can move without the owner reading code,** and the owner's time
  goes where only they can spend it: the goals, the key, the money.
- **Everything here is cheap to run except the second provider,** and that runs
  only at promotions — a handful a quarter, against the 20 €/month ceiling in
  [What is worth doing §1](../concepts/what-is-worth-doing.md#1-what-this-project-is-for).
  The loop is triggered by events, never continuous.
- **Cost: nobody outside the AI can reproduce a finding by understanding it** —
  only by re-running it. §6's standard was that the owner could reproduce a
  result *alone*. The replacement — anyone can re-run it — is weaker. That is
  the price of the owner's time, paid knowingly.
- **Cost: correlated error.** Proposer and auditor on the same model share blind
  spots. The second provider covers only the high-stakes tiers, and only partly.
- **Cost: shared infrastructure fools both.** A defect in a data feed or in
  `assets.forward_change()` is inherited by proposer and auditor alike. Tests and
  canaries reduce this; nothing here removes it.
- **Cost: canaries only test the failures someone thought to plant.**
- **Cost: accidental sealed reads can be blocked, deliberate ones cannot.** The
  data is public. The receipt rule keeps an unlogged number out of the record; it
  does not stop the look. The session that drafted this page made that slip with
  a scratch script and caught it — the case the receipt rule is for.
- **Cost: the owner learns less.** The competence gate was also how the owner
  learned the system. The digest is a thinner channel.
- **Cost: more machinery** — a CI job, four checks, a canary set and a
  credential split, each of which can drift like anything else, and each of
  which `record_audit.py` should be able to see.
- **This changes a rule after running under it** — the pattern convention #7
  exists to catch. The defence, which can be checked: no entry has been
  promoted, so no result benefits, and nothing already seen is relabelled.

## Would we revisit it?

Yes, on any of the conditions below. Reversing it is cheap: §6's current text
stays in history, and the owner taking a gate back needs no new ADR.

- **Phase 25 stalls short of the switch.** If the canaries never all pass, the
  old rule governs by default — the outcome this page was written to end. Reopen
  the design rather than let §6's transition subsection become permanent.
- **A canary passes the auditor.** Promotions stop until it is fixed. If it
  recurs, the auditor is the wrong shape.
- **The auditor does not discriminate** — it approves everything, or rejects
  everything, across its first five real submissions.
- **The two providers disagree on most promotions.** Then one of them is noise,
  and the owner is deciding by coin toss.
- **A KB entry from an audited promotion is later shown wrong** in a way the
  audit should have caught.
- **The audit's running cost passes a quarter of the 20 €/month ceiling.**
- **The owner's time changes.** Any gate can be taken back.
