# IMP-9 §9.C — The commercial-paper spread (DCPF3M − DTB3, first releases) as a filter on the OR flag

Overall: **fail** (both windows must pass). CP 1997-01-02 → 2026-09-29. Decisive horizon 5d; bar in `improvement-track.md` IMP-9 §9.C, written before this run.

## live — composite ∨ AR ∨ TURB (KB-021, sector ETFs), labelled on ^GSPC

Verdict: **recall_lost** — at 5d the filter loses 1 crisis(es) under PIT (9 vs 10) and 1 under LOCO (5 vs 6); allowed 0

Readings 667 (2013-07-10 → 2026-10-01). The unfiltered flag fired on 161; the filter blocked 45 (28%); 5 stood because CP was stale. Unfiltered row reproduces `fragility_or._pit_backtest`.

| horizon | crises | caught (unfiltered) | alarms (unfiltered) | precision (unfiltered) | median lead (unfiltered) | LOCO caught (unfiltered) of crises |
|---|---|---|---|---|---|---|
| 5d | 17 | 9 (10) | 17 (18) | 0.353 (0.333) | 5.0 (5.0) | 5 (6) of 17 |
| 10d | 21 | 10 (11) | 17 (18) | 0.412 (0.444) | 9.5 (10.0) | 9 (10) of 21 |

LOCO 5d, crises the filter lost: 2022-09-12 → 2022-09-19

LOCO 10d, crises the filter lost: 2026-03-17 → 2026-03-17

Shifted filters (200): median precision 0.233, 90% quantile 0.353.

Reported, not read — CP as a fourth OR channel at its PIT p90 (663 readings from 2013-08-07):

- 5d: caught 12 vs 10 of 17, precision 0.286 vs 0.333; LOCO 10 vs 9 of 21
- 10d: caught 12 vs 11 of 21, precision 0.333 vs 0.444; LOCO 14 vs 14 of 31
- CP fires on 12% of readings; the flag is on 30% of the time with it, 24% without
- 200 shifted CP channels at 5d: caught median 11, share ≥ real 0.29; precision median 0.286, share ≥ real 0.515

Reported, not read — today's values instead of first releases, on the 667 readings from 2006-03-22: 2 filter decisions change (1 on firings of the flag); the window would read **recall_lost** — at 5d the filter loses 1 crisis(es) under PIT (9 vs 10) and 1 under LOCO (5 vs 6); allowed 0

## long — AR ∨ TURB (Fama-French 30 industries, H-009's flag), labelled on the FF market

Verdict: **recall_lost** — at 5d the filter loses 4 crisis(es) under PIT (13 vs 17) and 3 under LOCO (11 vs 14); allowed 0

Readings 1431 (1998-01-22 → 2026-06-26). The unfiltered flag fired on 289; the filter blocked 100 (35%); 11 stood because CP was stale.

| horizon | crises | caught (unfiltered) | alarms (unfiltered) | precision (unfiltered) | median lead (unfiltered) | LOCO caught (unfiltered) of crises |
|---|---|---|---|---|---|---|
| 5d | 36 | 13 (17) | 41 (55) | 0.22 (0.218) | 4.0 (4.0) | 11 (14) of 36 |
| 10d | 53 | 19 (24) | 41 (55) | 0.39 (0.364) | 8.0 (8.0) | 17 (23) of 53 |

LOCO 5d, crises the filter lost: 2000-04-11 → 2000-04-11, 2000-10-09 → 2000-11-06, 2020-06-08 → 2020-06-08

LOCO 10d, crises the filter lost: 2000-09-01 → 2000-12-12, 2001-05-22 → 2001-06-06, 2019-07-24 → 2019-07-31, 2020-06-08 → 2020-06-08, 2022-02-28 → 2022-02-28, 2024-07-26 → 2024-07-26

Shifted filters (200): median precision 0.214, 90% quantile 0.273.

Reported, not read — CP as a fourth OR channel at its PIT p90 (1179 readings from 2003-01-28):

- 5d: caught 13 vs 11 of 24, precision 0.195 vs 0.171; LOCO 22 vs 19 of 42
- 10d: caught 19 vs 17 of 40, precision 0.317 vs 0.341; LOCO 31 vs 30 of 72
- CP fires on 8% of readings; the flag is on 22% of the time with it, 18% without
- 200 shifted CP channels at 5d: caught median 12, share ≥ real 0.49; precision median 0.174, share ≥ real 0.23

Reported, not read — today's values instead of first releases, on the 1020 readings from 2006-03-22: 2 filter decisions change (1 on firings of the flag); the window would read **recall_lost** — at 5d the filter loses 4 crisis(es) under PIT (13 vs 17) and 3 under LOCO (11 vs 14); allowed 0

## The revision check (first release vs today)

| series | archive from | days | revised | max (bp) | ≥ 5 bp | revised by year | published ≤1 / ≤2 / ≤3 weekdays | before the archive: differ / of, max (bp) | no first release |
|---|---|---|---|---|---|---|---|---|---|
| DCPF3M | 2006-03-22 | 4435 | 69 | 28.0 | 20 | {2013: 1, 2016: 6, 2017: 42, 2018: 20} | 64% / 97% / 100% | 2 / 2307, 2.0 | 9 |
| DTB3 | 2005-06-28 | 5316 | 0 | 0.0 | 0 | — | 65% / 95% / 98% | 35 / 12858, 3.0 | 4 |

An improvement-track gate: the result goes to the KB either way.
