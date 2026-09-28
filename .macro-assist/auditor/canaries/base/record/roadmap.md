# Roadmap

<!-- Frozen verbatim from docs/record/roadmap.md at commit d5df1f3: the work packages the fixture entry cites, and nothing else. Frozen so a later edit to the live page cannot date the cited text after the entry that cites it. Refresh only together with the fixture's timeline. -->

### WP-23.B — The class bars *(written before any candidate is promoted)*

One pre-registered bar per hypothesis *class*, not per hypothesis — the
[ADR-0020](../decisions/ADR-0020-the-numeric-bar-has-a-skill-margin.md) move
made a rule. Two classes are visible in the register today:

- **Shadow conditioner vs `unconditional`** (H-004, H-008): Phase 22's bar as
  is — `MIN_SKILL = 0.02`, block-bootstrap interval clear of zero,
  `underpowered → miscalibrated → inverted` first — **plus a mechanism clause**
  named by the entry (H-002 held this slot until it closed 2026-09-24, its
  clause — Elevated width > Normal width *and* medians on opposite sides of
  unconditional — failing on the location half; **H-008's clause is not yet
  written**, because the width-ratio prediction in the entry is flagged `seen`
  rather than pre-registered and so cannot serve as one),
  **plus `har_scaled` as a second comparator** (`resolved.md` #22): a promoted
  conditioner must beat not only `unconditional` but the vol forecast the
  product already has, applied to the empirical shape — on the explore slice
  that rival matched the best arm at every horizon, so a conditioner that
  clears `unconditional` and not `har_scaled` has found width, not a state.
- **Gap → width** (H-003): no scorer exists. Pinball loss on a quantile pair of
  the next-quarter rate change against `trailing_250` and `unconditional`,
  quarterly blocks, an explicit `underpowered` floor given ~55 observations.

Each bar ships with the tests [the method §10](../concepts/the-method.md#10-a-bar-is-not-tested-by-the-results-that-fail-it)
requires: every disqualifier driven independently, and a planted-signal
positive control.
