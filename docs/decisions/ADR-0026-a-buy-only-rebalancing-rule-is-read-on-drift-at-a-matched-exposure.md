# ADR-0026 — A rule for where new money goes is a target class, read on drift from the target mix, with return as a cost limit against an exposure-matched rival

| | |
|---|---|
| **Status** | **Open** — drafted 2026-10-11 by the assistant at the owner's request ([`todo.md`](../record/todo.md) #38). Nothing is built and no data has been read for it |
| **Decided** | — |
| **Related** | [What is worth doing §2](../concepts/what-is-worth-doing.md#2-the-standing-goals) (goals 3 and 4) · [How we explore §5, §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast) · [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md) · [ADR-0025](ADR-0025-a-contribution-rule-is-read-on-wealth-at-an-equal-budget.md) · the first member, [H-011](../record/hypotheses.md#h-011) |

## Context

**The goal.** Goal 3 asks for one rule for each decision the owner actually
faces, and names three: new money, rebalancing and reducing risk. Reducing
risk ([ADR-0023](ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md),
H-009) and the pace of new money ([ADR-0025](ADR-0025-a-contribution-rule-is-read-on-wealth-at-an-equal-budget.md),
H-010) each have a class bar, and each first member closed on the explore
record. On 2026-10-11 the owner chose the third decision, **rebalancing**,
and left the portfolio open: the assistant may propose which holdings make
sense, bonds and commodities included.

**Selling is still ruled out.** The account is taxable, and every sale brings
tax forward (`resolved.md` #34, #37). The textbook rebalance sells what has
grown and buys what has shrunk. The tax-free version steers only new money:
each month's contribution goes to what is below its target share. That is the
decision this class reads.

**Neither existing bar can read it.**

- **ADR-0023** reads one equity exposure between 0 and 1 against drops. A
  rebalancing rule holds several assets and never reduces anything.
- **ADR-0025** reads *how much* of a contribution goes in, against a cash
  reserve. A rebalancing rule invests every euro every month; it only
  chooses *where*. Its §2 door admits rules that change *when* money is
  invested, and this rule is not one.

**What the record and the outside literature say.**

- **H-010 lost to cash drag** ([H-010 ledger](../record/hypotheses.md#h-010)):
  the reserve held money back through rising markets, and that cost more than
  the better timing gained. A rule that is always fully invested cannot lose
  that way.
- **The textbook claim for rebalancing is about risk, not return.** A mix
  that is never rebalanced drifts toward whatever has risen most, usually
  equities, so the portfolio carries more risk than the owner chose, often
  just before a fall. Whether rebalancing also earns a return bonus is
  disputed: it helps when assets revert relative to each other, and costs
  when one keeps trending.
- **Buy-only steering weakens as the account grows.** One month's
  contribution is a large share of a young account and a tiny share of an old
  one. After ten years of a plan, a 500 € contribution is well under 1% of
  the account, and a large drift takes many months to repair. How much
  control survives is the honest open question. It is a fact about the
  arithmetic *and* about how far and how long the assets drift apart, which
  only data can say.

**The trap.** A rule that keeps less in equities than plain buying does will
usually end with less money, and a rule that keeps more will usually end with
more. A comparison of wealth against plain buying therefore mostly measures
how much equity each held. The return comparison must be against a rival
holding the **same average equity share**, which is ADR-0023's lesson in a
new place.

## Decision (proposed)

**1. A sixth target type: an allocation rule for new money.** Time runs in
months. The owner chooses a **target mix** *w\** over a fixed set of assets
before any look. At each month-end *t* a contribution of 1 arrives. The
member names how to split it across the assets, from information available
at the close of *t*: weights, prices and any signal the member names. The
split is bought at the next trading day's close. **Nothing is ever sold,
nothing is held back, nothing is borrowed.** The rule is never published as a
call.

**2. Relation to ADR-0009: no door is needed.** The class's claim is about
**risk**: keeping the portfolio near the mix the owner chose, without sales.
Return enters only as a cost limit, exactly as in ADR-0023 §2. Nothing here
bets that one asset will beat another.

- **A member that steers by a signal** (for example, all new money into
  equities while the fragility flag fires) makes a location bet. Its claim to
  *extra return* is not admitted by this ADR. It may sit under this bar only
  on control and cost, read against the first member's rule as a further
  rival (§3), and any claim beyond that needs ADR-0025 §2's door widened
  from *when* to *where*. That is not proposed here.
- **The target mix is the owner's risk preference, not a parameter.** It is
  fixed before the look and never tuned on data. A different mix is a
  different member and a counted look.

**3. The class bar, `mix_rule`.** It is written before any member is
promoted, and it names no member's parameters beyond taking *w\** as given.

*Plans.* The owner's plan has no end date, so the bar reads the rule over
**plans of 120 months** (ten years), each starting with an empty account. On
the explore side a plan starts every January from the slice's start until the
last start whose 120 months fit before the seal, and every statistic is the
mean over plans. The sealed side holds one plan from `SEAL_START` to the last
complete month at read time; if that is shorter than 96 months, the read is
`underpowered`.

*Legs.* Every leg receives 1 at every month-end and invests all of it at the
next close, paying 10 bps, then 30 bps, on every purchase (ADR-0023's two
levels).

- **`plain`** splits every contribution at *w\** and never rebalances. It is
  the owner's "doing nothing", and the first rival.
- **`exposure_matched`** splits every contribution at a fixed mix with a
  different equity share *e*, the non-equity assets keeping their ratio from
  *w\**. *e* is chosen so that its mean equity weight over the plans equals
  the member's. It answers "you just held a different amount of stock". As in
  ADR-0025, setting *e* from the slice uses information the member does not
  have, which strengthens the rival and makes the bar harder.
- **`sell_rebalanced`**, reported and never read. It splits contributions at
  *w\** and sells back to *w\** at every December close. It is the control a
  taxable account cannot have for free, and the report gives the gains it
  would realize per plan, so the owner can see the tax the member avoids.
- **A later signal member** is also read against the first member's rule
  (§2) under the same clauses as `exposure_matched`.

*The reads.*

- **Drift.** At each month-end, before the contribution, *d<sub>t</sub>* =
  ½ Σ<sub>i</sub> |*w<sub>i,t</sub>* − *w\*<sub>i</sub>*|: the share of the
  account that would have to move to be back on target. The **control
  ratio** *R* is the member's mean drift divided by `plain`'s.
- **Cost.** Each leg's money-weighted annual return over a plan (its IRR over
  all contributions, the final holding at its value). The member's
  **shortfall** is `exposure_matched`'s IRR minus the member's, in
  percentage points a year.
- **Intervals.** A 90% moving-block bootstrap of months (blocks of 24 months),
  all assets' returns resampled together and every leg and plan re-run on each
  resample, as in ADR-0025.

*Episodes.* A drop is ADR-0023's: at least 10% peak to trough in the equity
asset's total return in the owner's currency (`class_bars.risk_episodes`).
Drift matters most when a drop arrives, so the floor counts them.

*Order.* Disqualifiers come first, and each will be driven alone by a test
when it is built.

| # | Verdict | Fires when |
|---|---|---|
| 1 | `exploratory` | The read is on dates before the seal |
| 2 | `underpowered` | The slice holds **fewer than 5 drops** of 10% or more, or the sealed plan is shorter than 96 months |
| 3 | `inverted` | *R* ≥ 1: the member drifts at least as far as `plain` |
| 4 | `costly` | The shortfall against `exposure_matched` (or a later member's rule rival) is **more than 0.25 pp a year**, at 10 bps *or* at 30 bps |
| 5 | `no_control` | *R* is **above 0.5**, or its 90% interval reaches 1 |
| 6 | `unexplained` | The member's own mechanism clause fails |
| 7 | `edge` | None of the above: the rule keeps the mix at least twice as close to target as doing nothing, at a cost no worse than 0.25 pp a year |

*Why 0.5.* Halving the drift is the least that changes what the owner holds
when a drop arrives. A rule that removes a quarter of the drift is not worth
a monthly decision.

*Why 0.25 pp a year as the cost limit.* ADR-0025's margin, used the other way
round: what would have counted as worth a rule's effort as a gain is the most
it may cost.

*Why the cost clause has no interval.* With five or six drops on the sealed
side, an interval clear of zero is out of reach in either direction. The read
asks only that the point estimate stays inside the limit, and the report
gives the interval.

*Slice.* The sealed side runs from `SEAL_START` (2018-01-01) to the last
month-end with data at read time, read once (the seal is reused, as
`resolved.md` #19, #34 and #37 did). The explore side is everything before
2018-01-01 that every asset's data reaches.

*Currency.* The owner saves in euros, so every leg is valued in euros. A
foreign asset's return includes its currency's move.

*Reported, never read.* Each leg's final wealth per unit contributed; each
leg's IRR, including the member against `plain`; *R* within each plan's first
and second half; the equity weight of each leg at the peak before each drop;
the share of months each asset received the money; `sell_rebalanced`'s drift
and realized gains; and the same numbers on the first and second half of the
plan starts.

**4. Taxes.** No leg except `sell_rebalanced` sells, so no other leg realizes
a gain. The German *Vorabpauschale* on accumulating funds and the partial
exemption for equity funds depend on each fund's value, which the legs share
roughly. They are left out of the bar and named in the report as left out.

**5. What changes on acceptance.**

- [How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
  gains a sixth row.
- `class_bars.py` gains `MIX_RULE`, with its own reader (drift and a
  money-weighted return over plans).
- A multi-asset monthly input set in the owner's currency (see H-011): a data
  errand, built and checked before any leg is walked.
- [H-011](../record/hypotheses.md#h-011) can have its first explore look.

## Consequences

- Goal 3 gets its third decision covered by an instrument, and the one whose
  claim does not rest on the fragility flag at all.
- **The first member is not fragility-based.** Goal 3 asks for
  *fragility-based* rules. A signal-free rebalancing rule is the baseline any
  fragility-steered allocation must beat, and the owner's practical answer
  for the decision either way. Whether a signal-free rule counts toward goal 3
  is the owner's call (`todo.md` #38).
- **Goal 4 is in tension with any diversified mix.** Goal 4 asks to beat the
  S&P 500 over two years. A mix with bonds and gold will usually trail it in
  a year that equities rise strongly. This class reads control and cost, not
  that race. The owner should choose the mix knowing this.
- **The explore side is not blind in the usual sense.** Nobody has looked at
  these assets in this repo, but the broad history of stocks, bonds and gold
  since the 1970s is common knowledge, the proposer's included. The sealed
  side is the only blind read, and the auditor should weigh that.
- **Power is the honest problem again.** 2018–2026 holds about five equity
  drops of 10% or more and one plan of about 105 months. The sealed read may
  come back `underpowered`.
- **The data errand is real.** No long euro-based multi-asset series exist in
  the repo, and the proxies (H-011) are not the owner's funds.
- One more bar to maintain and one more multiplicity ledger.
- **The bar and its first member were drafted the same day,** which §5 warns
  against. The defence is ADR-0023's and ADR-0025's: no data has been read for
  either, and the bar names no parameter of the member.

## Would we revisit it?

- **If the first member reads `underpowered`,** revisit the drop floor and the
  96-month sealed plan before a second member is chosen, never to rescue the
  first.
- **If the first member reads `no_control` only through its second half**
  (control fades as the account grows), the plan length is the binding choice,
  and a second member should vary how it steers (for example a threshold
  before it acts), not the mix.
- **If the owner allows sales** (a tax-free wrapper, or gains under the
  allowance), `sell_rebalanced` becomes a rival rather than a report, and this
  bar changes.
- **If a lump sum arrives,** the class needs a lump-sum leg; that is a change
  to this bar, not a new member.
- **If ADR-0009 is ever revisited,** §2 goes with it.
