# ADR-0023 — A fragility rule for a real decision is a target class, read on drawdown against an exposure-matched rival

| | |
|---|---|
| **Status** | **Accepted** — drafted 2026-10-01 by the assistant at the owner's request, and accepted by the owner the same day with the proposed return budget and seal ([`resolved.md`](../record/resolved.md) #34). Built the same day — `class_bars.RISK_RULE` and `explore_rules.py` ([Scoring](../reference/scoring.md#the-risk-rule-class-risk_rule-adr-0023)) — and no member has been read |
| **Decided** | 2026-10-01 |
| **Related** | [What is worth doing §2](../concepts/what-is-worth-doing.md#2-the-standing-goals) (goal 3) · [How we explore §5, §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast) · [ADR-0009](ADR-0009-cut-the-directional-product.md) · [ADR-0019](ADR-0019-paper-portfolio-mechanical-and-paper-only.md) · [ADR-0020](ADR-0020-the-numeric-bar-has-a-skill-margin.md) · [ADR-0022](ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md) · the first member, [H-009](../record/hypotheses.md#h-009) |

## Context

**The goal.** The owner's goal 3, written 2026-09-24, asks for one rule for
each decision the owner actually faces: new money, rebalancing and reducing
risk. Each rule is written before it is tested and has to beat doing nothing
net of costs. It is tested on the explore data first, then on held-out data
or paper. On 2026-10-01 the owner chose the first decision, **reducing risk**,
and what "beats doing nothing" means for it: **a smaller worst drop.**

**Nothing in the research tier can read such a rule.**
[How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
admits three target types: a distribution, a state and a gap. `class_bars.py`
holds two classes, conditioner and gap → width, and both read pinball loss on
quoted quantiles. A rule's output is an exposure path, and its result is a
portfolio path. Neither scorer reads either.

**What the record already says about such a rule.**

- **The flag detects stress, with a little lead.** The OR flag has 5-day crisis
  recall of about 0.7 at precision of about 0.3 ([KB-016], [KB-017], [KB-020]).
  The composite leads a trough by a median 4–8 trading days ([KB-002]).
- **Stress tends to revert.** The stress-reversion mechanism was found in three
  runs ([KB-022], [KB-024]). On the explore slice the OR flag's Elevated state is
  where forward returns sit *right* of unconditional
  ([H-004](../record/hypotheses.md#h-004)). So cutting risk on the flag is
  expected to **cost return**. Whether it buys a smaller drop has not been
  measured anywhere.
- **A volatility rule is the known way to cut drops.** Scaling exposure
  inversely to recent realized volatility is the published result
  (Moreira & Muir, *Volatility-Managed Portfolios*, 2017). Its out-of-sample
  strength is contested (Cederburg et al., 2020). If the flag is volatility
  restated, a volatility rule does the flag's job. That is the pattern
  H-006 → [KB-033] and H-008 already showed on the distribution side.
- **[ADR-0019](ADR-0019-paper-portfolio-mechanical-and-paper-only.md) bars a
  tuned backtest as a scored result** for the Phase 20 paper book.

**The trap.** Any rule that holds less stock on average has smaller drops.
"Hold half in cash, always" halves every drop and needs no flag. A rule
compared only with buy-and-hold will look skilful. That is the rival lesson
the record has paid for three times ([KB-024], [KB-026], [KB-027]).

## Decision (proposed)

**1. A fourth target type: a mechanical risk rule.** A member's output is an
equity exposure *e<sub>t</sub>* between 0 and 1. It is decided from
information available at the close of day *t* and applied from the close of
*t* + 1. The rest of the money sits in cash at the T-bill rate. The rule is
read on **path risk**: how much of each market drop its portfolio takes. It is
never published as a call, and it carries no sign and no confidence.

**2. Relation to ADR-0009.** ADR-0009 removed a published signed forecast
because it carried no information. A risk rule publishes nothing, and it is
read on drawdown. Drawdown is a property of the spread of the path, not of its
direction. Its *return*, though, does depend on direction: being half out
during a rebound is a location bet, and the record says that bet loses
([KB-022]). That is why return enters the bar only as a **cost limit**, never
as the headline. A member whose claim is "it earns more" is ADR-0009
territory, and it is closed before it opens.

**3. Relation to ADR-0019.** ADR-0019 governs the Phase 20 paper book and
stays as it is. A risk rule is not a tuned backtest. It has one member, whose
parameters are fixed before any look, an explore slice to look at, and one
sealed read against a bar written first. A sealed pass is not a licence to
trade. The path to money runs through a forward paper record and the owner's
money key ([ADR-0022](ADR-0022-the-technical-audit-moves-to-an-independent-agent-loop.md)).

**4. The class bar, `risk_rule`.** It is written before any member is
promoted, and it names no member's parameters.

*Episodes.* An episode is a distinct drop of at least **10%**, peak to trough,
in the buy-and-hold total return of the equity leg. A new episode begins only
after a new high. For episode *k*:

- *d<sub>k</sub>* is the deepest drop of a portfolio's value inside
  [peak<sub>k</sub>, trough<sub>k</sub>].
- *r<sub>k</sub>* = *d<sub>k</sub>* / buy-and-hold's drop. Buy-and-hold has
  *r* = 1. A portfolio that takes half the drop has *r* = 0.5.

*Rivals.* Both rivals hold the member's own **average exposure ē** on the
same slice. ē is computed from the member's exposure path, which depends on
the flag and never on returns.

- **`static_matched`** holds the constant ē, rebalanced daily, and pays the
  same costs. It is the answer to "just hold less stock".
- **`vol_matched`** holds *e<sub>t</sub>* = min(1, *c* / σ̂<sub>t</sub>).
  σ̂<sub>t</sub> is the trailing 21-day realized volatility to close *t*, and
  *c* is set so that the mean exposure is ē. Setting *c* from the slice's
  whole volatility path uses information the member does not have. That only
  strengthens the rival, so it makes the bar harder and never easier.
- **`buy_and_hold`** is reported and is not a rival. It is the owner's
  "doing nothing".

*Costs.* Every leg pays 10 bps on each unit of exposure traded, which is
`portfolio/book.py`'s `DEFAULT_COST_BPS`. Taxes are outside the bar (see
Consequences).

*Order.* Disqualifiers come first, and each will be driven alone by a test
when it is built.

| # | Verdict | Fires when |
|---|---|---|
| 1 | `exploratory` | The read is on dates before the seal |
| 2 | `underpowered` | The sealed side holds **fewer than 5 episodes**. Five is the smallest count at which a rule that wins every episode reaches one-sided p < 0.05 on a sign test (1/32). A drop claim on fewer cannot be told from luck |
| 3 | `inverted` | The member's mean *r* exceeds 1: it deepens drops |
| 4 | `too_costly` | Its net annualized return trails `static_matched` by more than **0.5 percentage points a year**, at 10 bps *or* at 30 bps (three times the cost, because retail spreads and fees are uncertain). The 0.5 was the proposer's default, and the owner kept it (#34) |
| 5 | `no_edge` | Its mean saving against `static_matched`, *s* = mean over *k* of (*r*<sub>static,k</sub> − *r*<sub>rule,k</sub>), is **below 0.10**, or the 90% episode-bootstrap interval of *s* includes zero |
| 6 | `explained_by_rival` | Its mean saving against `vol_matched` is not above zero, or it beats `vol_matched` in fewer than **two thirds** of episodes |
| 7 | `unexplained` | The member's own mechanism clause fails |
| 8 | `edge` | None of the above |

*Why 0.10.* The rule has to take at least ten points less of each drop than
simply holding the same average amount of stock. On a 30% fall that is three
percentage points. Less than that is not a difference an investor would act
on.

*Why the vol rival's clause is weaker than the static one.* With five or six
episodes, an interval clear of zero against a strong rival is out of reach,
so it asks for a positive mean and a two-thirds majority. This is looser than
the conditioner class, which holds its second comparator to the full pass
clause. The read's report must say so.

*Slice.* The sealed side runs from `SEAL_START` (2018-01-01) to the last day
with data at read time. It is read whole and once. The owner chose to reuse
the seal, as [`resolved.md`](../record/resolved.md) #19 did (#34). The explore side is everything before 2018-01-01 that the member's
inputs reach.

*Reported, never read.* Each leg's single worst drop over each slice (the
owner's "worst drop"), annualized return and volatility, time spent at
reduced exposure, and trades per year. The single worst drop is reported and
not read because over a slice it is one number from one episode (2008, or
2020). A bar on one observation reads luck. **And the tax brought forward**
(added at acceptance, before any look, because the owner's account is
taxable — #34). This is the gain each leg realizes per year, on an average
cost basis, and the tax on it at an effective 18.46%. That rate is the
26.375% flat tax on the 70% of an equity fund's gain that is taxable. The
yearly €1,000 allowance is left out, because it depends on the owner's other
income.

**5. What changes on acceptance.**

- [How we explore §7](../concepts/how-we-explore.md#7-the-target-space-never-a-signed-forecast)
  gains a fourth row.
- `class_bars.py` gains `RISK_RULE`, with its own reader for path statistics,
  because the existing reader is pinball-specific.
- A research-tier harness, `explore_rules.py`, walks a member on the explore
  side.
- [H-009](../record/hypotheses.md#h-009) can go to its audit.

## Consequences

- Goal 3 gets an instrument, and its first member exists as a `draft`.
- **Power is the honest problem.** 2018–2026 holds about five or six US
  corrections of 10% or more, depending on whether dividends are counted. The
  sealed read may well come back `underpowered`. A forward paper record then
  takes years, because drops arrive when they arrive.
- **The sealed side is not unseen for the flag.** [KB-013], [KB-016],
  [KB-017] and [KB-020] measured which crises the flag catches, on data that
  runs to 2026. The absorption ratio's 120-day window was chosen on
  1970–2026 ([KB-013]). What no run has measured is a rule's drop and cost on
  any slice. A reader of the sealed result should discount it for this.
- **The matched rivals follow the member's average exposure.** A member that
  is nearly always fully invested faces rivals nearly equal to buy-and-hold,
  so its saving has to come from timing alone. That is the intent.
- **Taxes are not in the bar.** The owner's account is taxable (#34). In a
  German account every sale realizes a gain, and the tax on it falls due now
  rather than at the final sale. The total paid over a lifetime is roughly
  the same, because buying back resets the cost basis higher. What is lost
  is the **deferral**: the money paid early no longer compounds in the
  portfolio. A loss, by contrast, is banked against later gains. That timing
  cost is probably the largest real cost of a rule that sells. The bar reads
  the research question. The report carries the tax brought forward, and the
  money key has to weigh it.
- A third class is one more bar to maintain and one more multiplicity ledger.
- **The bar and its first member were drafted the same day,** which is what
  [§5](../concepts/how-we-explore.md#5-the-bar-precedes-the-candidate) warns
  against. The defence is that no data has been read for either, and that the
  bar names no parameter of the member. The auditor should check both.

## Would we revisit it?

- **If the first member reads `underpowered`,** revisit the 10% episode
  threshold and the five-episode floor, before a second member is chosen and
  never to rescue the first.
- **If a passing member's tax brought forward outweighs what its smaller
  drops are worth to the owner,** the next member acts on money flows (new
  money, rebalancing) rather than on sales. That is a new member under this
  bar, not a change to it.
- **If a passing member's forward paper record contradicts its sealed read**
  over at least three episodes, the bar's episode definition is the first
  suspect.
- **If ADR-0009 is ever revisited,** the clause that keeps return as a cost
  limit goes with it.
