# Explore look — h012_ipo_hot_half (H-012)

Verdict: **exploratory** — the sample is not the sealed side; reported, cannot pass. Explore slice 1986-01-31 → 2017-12-29 (< `SEAL_START` 2018-01-01), 8046 days; the net IPO count from 1975-01, the first decision at the end of 1986-01; cut in 16.4% of 384 months. Member mean exposure 0.9175.

## What the bar would read

- Episodes (buy-and-hold drops ≥ 10%): **9**
- Mean share of each drop taken, member: **1.0**
- Saving vs `static_matched`: **-0.0801** [-0.0846, -0.0758] (90%); bar ≥ 0.1
- Saving vs `vol_matched`: **-0.1147**, better in 0.0% of episodes; bar > 0 in ≥ 66.7%
- Net annual return, member minus `static_matched` (negative = behind): -0.46 pp at 10 bps, -0.48 pp at 30 bps; budget: no more than 0.5 pp behind
- Clause `caught_split`: failed — mean saving in 0 caught episode(s) +nan, in 9 missed -0.0801; needs both present and caught > missed

## Reported, never read

### Legs at 10 bps

| leg | worst drop | return / yr | vol / yr | time reduced | trades / yr | turnover / yr | gain realized / yr | tax brought forward / yr |
|---|---|---|---|---|---|---|---|---|
| member | 54.6% | 9.7% | 17.1% | 16.5% | 0.31 | 0.211 | 4.4% | 0.8% |
| static_matched | 51.1% | 10.1% | 16.1% | 100.0% | 0.0 | 0.14 | 3.4% | 0.6% |
| vol_matched | 46.0% | 10.3% | 13.6% | 29.9% | 10.72 | 1.883 | 6.9% | 1.3% |
| buy_and_hold | 54.6% | 10.7% | 17.6% | 0.0% | 0.0 | 0.0 | 0.0% | 0.0% |

### Legs at 30 bps

| leg | worst drop | return / yr | vol / yr | time reduced | trades / yr | turnover / yr | gain realized / yr | tax brought forward / yr |
|---|---|---|---|---|---|---|---|---|
| member | 54.6% | 9.6% | 17.1% | 16.5% | 0.31 | 0.211 | 4.4% | 0.8% |
| static_matched | 51.1% | 10.1% | 16.1% | 100.0% | 0.0 | 0.14 | 3.4% | 0.6% |
| vol_matched | 47.3% | 9.9% | 13.6% | 29.9% | 10.72 | 1.884 | 6.9% | 1.3% |
| buy_and_hold | 54.6% | 10.7% | 17.6% | 0.0% | 0.0 | 0.0 | 0.0% | 0.0% |

## Episodes

| peak | trough | depth | member | static | vol | caught |
|---|---|---|---|---|---|---|
| 1987-08-25 | 1987-12-04 | 33.1% | 1.0 | 0.9235 | 0.8745 | False |
| 1989-10-09 | 1990-01-30 | 10.9% | 1.0 | 0.9038 | 0.9652 | False |
| 1990-07-16 | 1990-10-11 | 20.8% | 1.0 | 0.9187 | 0.9098 | False |
| 1998-07-17 | 1998-10-08 | 21.9% | 1.0 | 0.9204 | 0.797 | False |
| 1999-07-16 | 1999-10-15 | 11.3% | 1.0 | 0.9113 | 0.9443 | False |
| 2000-03-24 | 2002-10-09 | 49.2% | 1.0 | 0.9261 | 0.9334 | False |
| 2007-10-09 | 2009-03-09 | 54.6% | 1.0 | 0.9357 | 0.6178 | False |
| 2012-04-02 | 2012-06-04 | 10.1% | 1.0 | 0.9203 | 1.0 | False |
| 2015-06-23 | 2016-02-11 | 15.5% | 1.0 | 0.9196 | 0.9254 | False |

Tax brought forward: realized gain on an average cost basis × 18.46%, as a share of the portfolio at the year's start; the yearly allowance is left out. An explore look is not a result: it goes to the register, never the KB.
