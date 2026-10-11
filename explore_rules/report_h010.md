# Explore look — h010_panel_or_double (H-010)

Verdict: **exploratory** — the sample is not the sealed side; reported, cannot pass. Explore slice 1932-01-08 → 2017-12-29 (< `SEAL_START` 2018-01-01), 1032 monthly contributions; the flag's first reading 1932-01-08, fired on 15.9% of 4500 grid readings. The member names 2.0 in 28.7% of month-ends, 0.75 in the rest.

## What the bar would read

- Drops of 10% or more: **32** (floor 5)
- Advantage over `plain`, money-weighted return a year: **-0.05 pp** at 10 bps, **-0.05 pp** at 30 bps; 90% interval (24-month blocks) [-0.05 pp, +0.00 pp]; bar ≥ 0.25 pp, interval clear of zero
- Advantage over `dip_matched` (high when the market is at least 13.4% below its peak): **-0.02 pp**; bar > 0
- Clause `forward_contrast`: held — median 12-month forward return from 292 flagged month-end(s) +0.1653, from 217 unflagged ones at least 13.4% down +0.1406; needs ≥ 12 in each and flagged > unflagged

## Reported, never read

- Reserve, in months of contributions: mean 2.781, largest 10.876, at the end 1.25.
- Starved: in 41.4% of its high months the member wanted more than its reserve held.
- Where the advantage over `plain` sits, as a share of `plain`'s final wealth: purchases inside drops -0.0080, outside -0.0238, the reserve left at the end -0.0000.
- Each half, started fresh: 1932-01-08 → 1975-01-31 -0.11 pp; 1975-02-03 → 2017-12-29 -0.05 pp.

| leg | return / yr at 10 bps | wealth per contribution | return / yr at 30 bps | wealth per contribution |
|---|---|---|---|---|
| member | 11.0% | 868.14478 | 11.0% | 866.40676 |
| plain | 11.0% | 896.7137 | 11.0% | 894.91848 |
| dip_matched | 11.0% | 879.55787 | 11.0% | 877.7977 |

## Drops

| peak | trough | depth |
|---|---|---|
| 1932-01-14 | 1932-02-10 | 14.2% |
| 1932-03-08 | 1932-07-08 | 46.8% |
| 1932-09-07 | 1933-02-27 | 36.4% |
| 1933-07-18 | 1933-10-21 | 28.8% |
| 1936-04-06 | 1936-04-29 | 12.3% |
| 1937-03-10 | 1938-03-31 | 51.0% |
| 1943-07-14 | 1943-11-29 | 10.6% |
| 1946-05-29 | 1947-05-17 | 28.3% |
| 1950-06-12 | 1950-07-13 | 12.8% |
| 1953-03-19 | 1953-09-14 | 10.6% |
| 1956-08-02 | 1957-02-12 | 11.6% |
| 1957-07-15 | 1957-10-22 | 20.6% |
| 1960-01-05 | 1960-03-08 | 10.4% |
| 1961-12-12 | 1962-06-26 | 27.7% |
| 1966-02-09 | 1966-10-07 | 20.3% |
| 1968-11-29 | 1970-05-26 | 36.8% |
| 1971-04-28 | 1971-11-23 | 12.7% |
| 1973-01-11 | 1974-10-03 | 48.2% |
| 1978-09-12 | 1978-11-14 | 15.2% |
| 1979-10-05 | 1979-10-25 | 10.8% |
| 1980-02-13 | 1980-03-27 | 18.7% |
| 1981-08-11 | 1982-08-12 | 20.2% |
| 1983-10-10 | 1984-07-24 | 13.3% |
| 1987-08-25 | 1987-12-04 | 33.1% |
| 1989-10-09 | 1990-01-30 | 10.9% |
| 1990-07-16 | 1990-10-11 | 20.8% |
| 1998-07-17 | 1998-10-08 | 21.9% |
| 1999-07-16 | 1999-10-15 | 11.3% |
| 2000-03-24 | 2002-10-09 | 49.2% |
| 2007-10-09 | 2009-03-09 | 54.6% |
| 2012-04-02 | 2012-06-04 | 10.1% |
| 2015-06-23 | 2016-02-11 | 15.5% |

No leg sells, so no tax is brought forward; taxes are outside the bar (ADR-0025 §4). An explore look is not a result: it goes to the register, never the KB.
