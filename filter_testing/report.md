# IMP-9 §9.A — CBOE SKEW as a filter on the OR flag

Overall: **fail** (both windows must pass). SKEW 1990-01-02 → 2026-09-30. Decisive horizon 5d; bar in `improvement-track.md` IMP-9 §9.A, written before this run.

## live — composite ∨ AR ∨ TURB (KB-021, sector ETFs), labelled on ^GSPC

Verdict: **recall_lost** — at 5d the filter loses 8 crisis(es) under PIT (2 vs 10) and 4 under LOCO (2 vs 6); allowed 0

Readings 667 (2013-07-10 → 2026-10-01). The unfiltered flag fired on 161; the filter blocked 103 (64%); 0 stood because SKEW was stale. Unfiltered row reproduces `fragility_or._pit_backtest`.

| horizon | crises | caught (unfiltered) | alarms (unfiltered) | precision (unfiltered) | median lead (unfiltered) | LOCO caught (unfiltered) of crises |
|---|---|---|---|---|---|---|
| 5d | 17 | 2 (10) | 20 (18) | 0.1 (0.333) | 5.0 (5.0) | 2 (6) of 17 |
| 10d | 21 | 6 (11) | 20 (18) | 0.3 (0.444) | 9.5 (10.0) | 6 (10) of 21 |

LOCO 5d, crises the filter lost: 2018-02-01 → 2018-02-01, 2018-12-17 → 2018-12-17, 2022-06-08 → 2022-06-08, 2022-09-12 → 2022-09-19

LOCO 10d, crises the filter lost: 2018-01-25 → 2018-02-01, 2018-11-08 → 2018-12-17, 2022-04-11 → 2022-06-08, 2022-08-12 → 2022-09-19

Shifted filters (200): median precision 0.263, 90% quantile 0.375.

Reported, not read — SKEW as a fourth OR channel at its PIT p90 (667 readings from 2013-07-10):

- 5d: caught 15 vs 10 of 17, precision 0.391 vs 0.333; LOCO 10 vs 9 of 21
- 10d: caught 16 vs 11 of 21, precision 0.478 vs 0.444; LOCO 16 vs 14 of 31

## long — AR ∨ TURB (Fama-French 30 industries, H-009's flag), labelled on the FF market

Verdict: **recall_lost** — at 5d the filter loses 8 crisis(es) under PIT (10 vs 18) and 7 under LOCO (8 vs 15); allowed 0

Readings 1787 (1991-01-08 → 2026-06-26). The unfiltered flag fired on 393; the filter blocked 226 (58%); 0 stood because SKEW was stale.

| horizon | crises | caught (unfiltered) | alarms (unfiltered) | precision (unfiltered) | median lead (unfiltered) | LOCO caught (unfiltered) of crises |
|---|---|---|---|---|---|---|
| 5d | 37 | 10 (18) | 50 (76) | 0.18 (0.171) | 4.5 (4.0) | 8 (15) of 37 |
| 10d | 57 | 12 (26) | 50 (76) | 0.22 (0.289) | 7.0 (8.0) | 11 (25) of 57 |

LOCO 5d, crises the filter lost: 2000-04-11 → 2000-04-11, 2002-11-06 → 2002-11-06, 2007-08-08 → 2007-08-08, 2011-08-03 → 2011-10-27, 2018-02-01 → 2018-02-01, 2022-04-19 → 2022-05-03, 2022-06-08 → 2022-06-08

LOCO 10d, crises the filter lost: 1996-06-28 → 1996-06-28, 1999-12-31 → 2000-01-14, 2000-04-04 → 2000-05-17, 2002-11-06 → 2002-11-06, 2007-07-18 → 2007-08-08, 2007-12-21 → 2008-01-08, 2011-07-20 → 2011-11-10, 2018-01-25 → 2018-02-01, 2019-07-24 → 2019-07-31, 2022-02-28 → 2022-02-28, 2022-04-11 → 2022-06-08, 2022-08-12 → 2022-09-19, 2024-07-26 → 2024-07-26, 2025-02-18 → 2025-04-01

Shifted filters (200): median precision 0.167, 90% quantile 0.207.

Reported, not read — SKEW as a fourth OR channel at its PIT p90 (1535 readings from 1996-01-02):

- 5d: caught 24 vs 18 of 37, precision 0.213 vs 0.213; LOCO 22 vs 19 of 42
- 10d: caught 34 vs 26 of 55, precision 0.347 vs 0.361; LOCO 33 vs 30 of 72

An improvement-track gate: the result goes to the KB either way.
