# Explore look — h011_fill_gaps (H-011)

Verdict: **exploratory** — the sample is not the sealed side; reported, cannot pass. Explore slice 1973-01 → 2017-12 (< `SEAL_START` 2018-01-01), 36 plans of 120 months, one starting each January. Target mix: equity 70%, bonds 20%, gold 10%. In euros; proxies: the US market for world equities, a constant-maturity 10-year Bund rebuilt from its yield for euro government bonds, the World Bank's monthly gold price.

## What the bar would read

- Equity drops of 10% or more: **13** (floor 5)
- Control ratio (member's mean drift ÷ `plain`'s): **0.322**, 90% interval (24-month blocks) [0.262, 0.456]; bar ≤ 0.5, interval below 1. Mean drift: member 1.7%, plain 5.3%, exposure_matched 5.4%
- Shortfall against `exposure_matched` (equity share 67.9%), money-weighted return a year: **+0.12 pp** at 10 bps, **+0.12 pp** at 30 bps; interval [-0.17 pp, +0.42 pp]; at most 0.25 pp
- Clause `late_control`: held — median control ratio over each plan's second half 0.303 across 36 plan(s); needs ≤ 0.75

## Reported, never read

- Control ratio by half of a plan (median across plans): first 0.3313, second 0.3034; by plan: median 0.3222, worst 0.4925.
- Mean equity weight: member 69.4%, plain 71.4%, exposure_matched 69.4%.
- Where the money went: equity 61.0%, bonds 24.3%, gold 14.7%.
- An annual sell-back to target: control ratio 0.4244, gains realized 9.0234 contributions per plan (taxable).
- Each half of the plan starts: 1973-01 → 1990-01: ratio 0.3213, shortfall +0.06 pp; 1991-01 → 2008-01: ratio 0.3232, shortfall +0.12 pp.

| leg | return / yr at 10 bps | wealth per contribution | return / yr at 30 bps | wealth per contribution |
|---|---|---|---|---|
| member | 9.8% | 1.72367 | 9.8% | 1.72023 |
| plain | 10.0% | 1.74812 | 10.0% | 1.74462 |
| exposure_matched | 10.0% | 1.73849 | 9.9% | 1.73501 |

## Equity drops, and each leg's equity weight at the peak

| peak | trough | depth | plans running | member | plain |
|---|---|---|---|---|---|
| start | 1974-09 | 55.4% | 0 | — | — |
| 1981-07 | 1982-05 | 15.8% | 9 | 72.1% | 75.8% |
| 1984-01 | 1984-03 | 10.1% | 10 | 70.8% | 77.0% |
| 1985-02 | 1986-09 | 17.1% | 10 | 72.8% | 79.3% |
| 1987-08 | 1987-11 | 36.4% | 10 | 71.0% | 75.0% |
| 1989-09 | 1990-10 | 33.2% | 10 | 71.2% | 76.4% |
| 1991-08 | 1991-11 | 10.1% | 10 | 70.5% | 75.2% |
| 1992-04 | 1992-08 | 12.2% | 10 | 70.2% | 73.8% |
| 1994-01 | 1994-11 | 15.8% | 10 | 70.6% | 72.7% |
| 1998-04 | 1998-08 | 17.8% | 10 | 71.3% | 79.7% |
| 2000-08 | 2009-02 | 57.9% | 10 | 72.4% | 81.2% |
| 2015-04 | 2015-09 | 11.0% | 3 | 70.9% | 79.1% |
| 2015-11 | 2016-02 | 10.8% | 3 | 71.1% | 79.8% |

Only the sell-back reference sells; taxes are outside the bar (ADR-0026 §4). An explore look is not a result: it goes to the register, never the KB.
