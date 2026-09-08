# ADR-0004 — Retire the HMM regime layer from the note, keep the code

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | Phase 17 (WP-17.4) |
| **Evidence** | [KB-003], [KB-004], [KB-005], **[KB-006]** |
| **Related** | [ADR-0015](ADR-0015-soft-kill-convention.md) |

## Context

Phase 10 shipped a 4-state Gaussian HMM over NFCI percentile, yield-curve slope,
HY z-score and realized-vol percentile, and wired it into the prompt. It was
never validated the way the fragility index had been.

Phase 17 applied that scrutiny, and found four things in sequence:

- **[KB-003]** — live labelling is look-ahead-safe, but validation must use
  walk-forward, never the persisted full-sample model, which is
  startprob-dominated and collapses to one label. Walk-forward and full-sample
  labels disagree **70.5%** of the time. This audit also caught a *shipped* bug:
  the HY-OAS credit feature had only ~3 years of FRED history and was truncating
  training to ~2 years.
- **[KB-004]** — no out-of-sample skill as wired.
- **[KB-005]** — the inference path was the bug, not the concept. Fixing it
  produced a working classifier.
- **[KB-006]** — and it still lost. A four-feature rule beats it (drawdown alone
  reaches AUC 0.697 against the HMM's 0.553), and it is redundant with fragility.

## Decision

Remove the regime block from the note. **Keep `regime.py`, `regime_features.py`,
the weekly refit and the persisted model.**

## Consequences

- The note lost a section that was not earning it.
- The regime is still computed, still logged, and still used by the paper
  portfolio's gate and by `point_in_time` reconstruction — so the code is not
  dead, only unpublished.
- Anyone reading the code will find a fitted HMM and reasonably assume it feeds
  the note. It does not. This is called out in
  [Data sources](../reference/data-sources.md) and
  [The signal stack](../concepts/the-signal-stack.md).

## Would we revisit it?

Only with a materially different feature set or state count, and only through the
same walk-forward gate. The conditional-distribution bucketing (`NFCI × YC × HY`)
already occupies the "macro state" role in the published product, and does it
without a latent-state model.
