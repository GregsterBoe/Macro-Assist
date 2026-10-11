# ADR-0025 — A rule for new money is a target class, read on wealth at an equal budget against a drawdown rival

| | |
|---|---|
| **Status** | **Accepted** — drafted 2026-10-11 by the assistant at the owner's request, and accepted by the owner the same day as written ([`resolved.md`](../record/resolved.md) #37). Built the same day — `class_bars.FLOW_RULE` and `explore_rules.py --member h010` ([Scoring](../reference/scoring.md#the-contribution-rule-class-flow_rule-adr-0025)) — and no member has been read |
| **Decided** | 2026-10-11 |
| **Related** | [What is worth doing §2](../concepts/what-is-worth-doing.md#2-the-standing-goals) (goal 3) · [How we explore §5, §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast) · [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0022](ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md) · [ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md) · the first member, [H-010](../record/hypotheses.md#h-010) |

## Context

**The goal.** Goal 3 asks for one rule for each decision the owner actually
faces, and names three: new money, rebalancing and reducing risk. Reducing
risk was taken first ([ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md)),
and its first member, H-009, closed on the explore record. On 2026-10-11 the
owner chose the second decision, **new money**: a standing plan invests a base
amount (500 € a month) into the equity holding, and a rule decides when to
invest more or less of it. **Selling is ruled out.** The account is taxable,
and every sale brings tax forward (ADR-0023's Consequences, `resolved.md` #34).
A rule that only changes the pace of buying realizes nothing.

**ADR-0023's bar cannot read this rule.** It reads how much of each drop a
portfolio takes, with an exposure between 0 and 1. A contribution rule never
reduces exposure: every euro paid in stays in the account, as stock or as a
cash reserve, and the stock holding only grows. Its effect on a drop is small
and mostly mechanical: it holds a little more cash. Its whole claim is about
**what the same money is worth at the end**. ADR-0023's revisit section
assumed a money-flow member could sit under its bar. It cannot, because a
saving on drawdown is not what such a rule would buy.

**What the record already says.**

- **Stress tends to be followed by recovery.** The stress-reversion mechanism
  was found in three runs ([KB-022], [KB-024]). On the explore slice the OR
  flag's Elevated state is where forward returns sit right of unconditional
  ([H-004](../record/hypotheses.md#h-004)).
- **H-009's false alarms paid for the rebound.** Its 111 flag windows not
  followed by a 5% drop cost the halving rule 1.77 pp a year on 1932–2017
  ([H-009 ledger](../record/hypotheses.md#h-009)). A rule that buys *more*
  in those windows bets on the same rebound from the other side. **That
  number was seen on the explore slice before this ADR was written**, and the
  member it suggests is not blind there (Consequences).
- **The outside prior is against it.** Markets rise on average, so money held
  back costs return. That is why investing a lump sum at once usually beats
  spreading it, and why most "buy the dip" schemes trail plain monthly buying:
  the reserve sits in cash waiting for a dip that comes late or not deep
  enough.

**The trap.** A rule allowed to invest more money in total wins in any rising
market, and the comparison shows nothing. A rule judged only against plain
monthly buying may just be "buy after the market has fallen", which needs no
fragility flag. That is the rival lesson again ([KB-024], [KB-026], [KB-027]),
and H-009's.

## Decision (proposed)

**1. A fifth target type: a contribution rule.** Time runs in months. At each
month-end *t* a fixed contribution of 1 (the base amount, 500 € in the
owner's plan; the bar is scale-free) is paid into a cash **reserve**. The
member then names a multiple *m<sub>t</sub>* ≥ 0 from information available
at the close of *t*. The amount invested at the close of the next trading day
is *a<sub>t</sub>* = min(*m<sub>t</sub>*, reserve). What is not invested stays
in the reserve and earns the T-bill rate. **Nothing is ever sold**, and the
reserve can never go below zero, so no leg borrows. The rule is never
published as a call.

**2. Relation to ADR-0009. This is the decision the owner has to make
consciously.** ADR-0023 kept return as a cost limit and said a member whose
claim is "it earns more" is closed before it opens. A contribution rule's
claim *is* about return: it bets that money invested during stress earns
more than money invested at other times. That is a location bet. This ADR
proposes a second, narrow door through ADR-0009, for these reasons:

- **What ADR-0009 cut was a published signed forecast**, from a model, whose
  labels carried no information ([KB-022], [KB-024]). Nothing here is
  published, and no model writes anything. The rule is mechanical, fixed
  before any look, and read once on the sealed side against a bar written
  first.
- **The bet is bounded by construction.** Exposure only grows, the budget is
  fixed, and the worst a wrong rule can do is hold a capped reserve in cash
  for too long. That cost is what the bar reads.
- **The location effect it bets on is a measured property of the record**
  (the reversion), not a model's call. Whether a mechanical rule can harvest
  it at an equal budget has not been measured anywhere.
- **The door stays narrow.** It admits rules that change only *when*
  budgeted new money is invested. A rule that sells or cuts exposure stays
  under ADR-0023, where return is a cost limit only. One that borrows, or
  publishes a direction, stays ADR-0009 territory. ADR-0009's own revisit
  section ("only through WP-21.E") is amended by this clause and nothing
  else.

**3. The class bar, `flow_rule`.** It is written before any member is
promoted, and it names no member's parameters.

*Legs.* Every leg starts the slice with an empty reserve and receives the
same contribution of 1 at every month-end. Equity is the market's total
return; the reserve earns the risk-free rate. Each purchase pays a cost of
10 bps, then 30 bps (ADR-0023's two levels; both legs buy roughly the same
total, so cost moves little).

- **`plain`** invests the whole contribution every month (*a* = 1). It is the
  owner's "doing nothing", and the first rival.
- **`dip_matched`** names the member's own two multiples (its low and high
  *m*) but switches on the market's drawdown from its running peak at
  month-end instead of the member's signal: high when the drawdown is at
  least *D*, low otherwise. *D* is set so that `dip_matched` names the high
  multiple in the same share of months as the member. It is the answer to
  "just buy after a fall". Setting *D* from the whole slice uses information
  the member does not have, which strengthens the rival and makes the bar
  harder, never easier. A member with more than two multiples is matched
  through the drawdown's quantiles in the same way.

*The read.* Each leg's money-weighted annual return (its IRR over all
contributions, with the final reserve counted at its value) over the slice.
The member's **advantage** is its IRR minus the rival's, in percentage points
a year. Its interval is a 90% moving-block bootstrap of months (blocks of 24
months, so a drop and its recovery tend to stay in one block), with the
signal, the drawdown and both returns resampled together and every leg re-run
on each resample.

*Episodes.* A drop is ADR-0023's: at least 10% peak to trough in the
market's total return, a new episode only after a new high
(`class_bars.risk_episodes`). The rule's mechanism lives in drops, so the
floor counts them.

*Order.* Disqualifiers come first, and each will be driven alone by a test
when it is built.

| # | Verdict | Fires when |
|---|---|---|
| 1 | `exploratory` | The read is on dates before the seal |
| 2 | `underpowered` | The slice holds **fewer than 5 drops** of 10% or more (ADR-0023's floor, for its reason) |
| 3 | `inverted` | The advantage over `plain` is below zero at 10 bps |
| 4 | `no_edge` | The advantage over `plain` is **below 0.25 pp a year**, at 10 bps *or* at 30 bps, or its 90% interval includes zero |
| 5 | `explained_by_rival` | The advantage over `dip_matched` is not above zero |
| 6 | `unexplained` | The member's own mechanism clause fails |
| 7 | `edge` | None of the above |

*Why 0.25 pp a year.* On a plan of 500 € a month over twenty years it is
roughly 2.5% more money at the end. Less than that is not worth a rule
the owner has to follow every month. It was the proposer's default, and the owner
kept it (#37).

*Why the rival's clause is weaker than the plain one.* As in ADR-0023: with
five or six drops an interval clear of zero against a strong rival is out of
reach, so it asks only for a positive advantage. The read's report must say
so.

*Slice.* The sealed side runs from `SEAL_START` (2018-01-01) to the last
month-end with data at read time, read whole and once (the seal is reused,
as `resolved.md` #19 and #34 did). The explore side is everything before
2018-01-01 that the member's inputs reach.

*Reported, never read.* Each leg's final wealth per unit contributed; the
mean and largest reserve (in months of contributions); the share of months
the member wanted more than the reserve held (**starved** months); its
advantage over `plain` within each drop and outside drops; and the same
numbers on the first and second half of the slice.

**4. Taxes.** No leg sells, so no leg realizes a gain during the slice. The
German *Vorabpauschale* on accumulating funds depends on the holding's value
at each year start, which the legs share closely. Taxes are left out of the
bar and named in the report as left out.

**5. What changes on acceptance.**

- [How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
  gains a fifth row.
- `class_bars.py` gains `FLOW_RULE`, with its own reader (a money-weighted
  return, not a path drawdown).
- `explore_rules.py` gains a flow walk, reusing H-009's inputs and flag.
- [H-010](../record/hypotheses.md#h-010) can have its first explore look.

## Consequences

- Goal 3 gets its second decision covered by an instrument, and the one with
  no tax drag.
- **The explore side is not blind for the first member.** H-009's look
  measured what the panel flag's windows were followed by on 1932–2017, and
  this class was drafted after it. An explore look of H-010 there tests the
  arithmetic of the reserve, not whether the reversion exists. The sealed
  side is the only blind read, and the auditor should weigh that.
- **Power is the honest problem, as in ADR-0023.** 2018–2026 holds about five
  drops of 10% or more in the US market's total return. The sealed read may
  come back `underpowered`, and a forward record takes years.
- **The prior is low.** Cash drag is real, and the deepest drops (the 1930s,
  2008) last longer than any small reserve: the rule may run dry early and
  buy the bottom with nothing.
- **A second door through ADR-0009 is a precedent.** The next proposal will
  try to widen it. The door's boundary in §2 is the thing to hold.
- One more bar to maintain and one more multiplicity ledger.
- **The bar and its first member were drafted the same day,** which §5
  warns against. The defence is the same as ADR-0023's: no data has been
  read for either since H-009's look, and the bar names no parameter of the
  member. The auditor should check both.

## Would we revisit it?

- **If the first member reads `underpowered`,** revisit the drop floor and
  the 24-month block before a second member is chosen, never to rescue the
  first.
- **If a passing member is mostly starved** (it wanted more than its reserve
  in most flagged months), the reserve rule is the binding choice, and a
  second member should vary it rather than the signal.
- **If the owner's plan stops being monthly** (a lump sum arrives), the class
  needs a lump-sum leg; that is a change to this bar, not a new member.
- **If ADR-0009 is ever revisited,** §2 goes with it.
