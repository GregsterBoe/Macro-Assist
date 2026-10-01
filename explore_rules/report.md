# Explore look — h009_panel_or_half (H-009)

Verdict: **exploratory** — the sample is not the sealed side; reported, cannot pass. Explore slice 1932-01-08 → 2017-12-29 (< `SEAL_START` 2018-01-01), 22500 days; the flag's first reading 1932-01-08, fired on 15.9% of 4500 grid readings. Member mean exposure 0.8544.

## What the bar would read

- Episodes (buy-and-hold drops ≥ 10%): **32**
- Mean share of each drop taken, member: **0.8573**
- Saving vs `static_matched`: **-0.0028** [-0.0432, +0.0384] (90%); bar ≥ 0.1
- Saving vs `vol_matched`: **-0.0689**, better in 46.9% of episodes; bar > 0 in ≥ 66.7%
- Net annual return behind `static_matched`: -1.12 pp at 10 bps, -1.50 pp at 30 bps; budget 0.5 pp
- Clause `caught_split`: held — mean saving in 19 caught episode(s) +0.0685, in 13 missed -0.1071; needs both present and caught > missed

## Reported, never read

Return behind `static_matched` by day (pp a year, 10 bps): in the 43 hold windows a 5% drop followed, +0.16; in the 111 false alarms, -1.77; fully invested, +0.56.

### Legs at 10 bps

| leg | worst drop | return / yr | vol / yr | time reduced | trades / yr | turnover / yr | gain realized / yr | tax brought forward / yr |
|---|---|---|---|---|---|---|---|---|
| member | 46.6% | 8.9% | 14.1% | 29.1% | 3.57 | 1.927 | 7.9% | 1.5% |
| static_matched | 48.2% | 10.0% | 14.2% | 100.0% | 0.0 | 0.217 | 4.8% | 0.9% |
| vol_matched | 47.8% | 9.5% | 11.1% | 44.7% | 16.6 | 2.936 | 8.0% | 1.5% |
| buy_and_hold | 54.6% | 11.0% | 16.6% | 0.0% | 0.0 | 0.0 | 0.0% | 0.0% |

### Legs at 30 bps

| leg | worst drop | return / yr | vol / yr | time reduced | trades / yr | turnover / yr | gain realized / yr | tax brought forward / yr |
|---|---|---|---|---|---|---|---|---|
| member | 46.6% | 8.5% | 14.1% | 29.1% | 3.57 | 1.928 | 7.9% | 1.5% |
| static_matched | 48.3% | 10.0% | 14.2% | 100.0% | 0.0 | 0.217 | 4.8% | 0.9% |
| vol_matched | 50.5% | 8.9% | 11.1% | 44.7% | 16.6 | 2.936 | 7.9% | 1.5% |
| buy_and_hold | 54.6% | 11.0% | 16.6% | 0.0% | 0.0 | 0.0 | 0.0% | 0.0% |

## Episodes

| peak | trough | depth | member | static | vol | caught |
|---|---|---|---|---|---|---|
| 1932-01-14 | 1932-02-10 | 14.2% | 1.0 | 0.8596 | 0.3669 | False |
| 1932-03-08 | 1932-07-08 | 46.8% | 0.9959 | 0.8858 | 0.4321 | False |
| 1932-09-07 | 1933-02-27 | 36.4% | 0.9591 | 0.8703 | 0.3668 | True |
| 1933-07-18 | 1933-10-21 | 28.8% | 1.0121 | 0.8644 | 0.4716 | False |
| 1936-04-06 | 1936-04-29 | 12.3% | 1.0 | 0.8608 | 0.8088 | False |
| 1937-03-10 | 1938-03-31 | 51.0% | 0.7852 | 0.8887 | 0.6779 | True |
| 1943-07-14 | 1943-11-29 | 10.6% | 0.8231 | 0.8587 | 0.9711 | True |
| 1946-05-29 | 1947-05-17 | 28.3% | 1.0708 | 0.8685 | 0.9466 | False |
| 1950-06-12 | 1950-07-13 | 12.8% | 0.7286 | 0.8603 | 0.7651 | True |
| 1953-03-19 | 1953-09-14 | 10.6% | 0.6913 | 0.8438 | 1.0014 | True |
| 1956-08-02 | 1957-02-12 | 11.6% | 0.947 | 0.8447 | 1.0286 | True |
| 1957-07-15 | 1957-10-22 | 20.6% | 0.8759 | 0.863 | 0.869 | True |
| 1960-01-05 | 1960-03-08 | 10.4% | 0.676 | 0.8515 | 0.9981 | True |
| 1961-12-12 | 1962-06-26 | 27.7% | 0.675 | 0.8656 | 0.7442 | True |
| 1966-02-09 | 1966-10-07 | 20.3% | 0.933 | 0.8461 | 0.9652 | True |
| 1968-11-29 | 1970-05-26 | 36.8% | 0.8831 | 0.8535 | 0.9098 | False |
| 1971-04-28 | 1971-11-23 | 12.7% | 0.9468 | 0.8325 | 0.99 | False |
| 1973-01-11 | 1974-10-03 | 48.2% | 0.9187 | 0.8665 | 0.7288 | True |
| 1978-09-12 | 1978-11-14 | 15.2% | 0.8338 | 0.8514 | 0.9348 | False |
| 1979-10-05 | 1979-10-25 | 10.8% | 0.7954 | 0.8534 | 0.8584 | False |
| 1980-02-13 | 1980-03-27 | 18.7% | 0.4845 | 0.8553 | 0.7538 | True |
| 1981-08-11 | 1982-08-12 | 20.2% | 1.0 | 0.7922 | 0.9161 | False |
| 1983-10-10 | 1984-07-24 | 13.3% | 1.0 | 0.7889 | 0.9908 | False |
| 1987-08-25 | 1987-12-04 | 33.1% | 0.888 | 0.8639 | 0.6655 | False |
| 1989-10-09 | 1990-01-30 | 10.9% | 1.0081 | 0.8298 | 0.8593 | True |
| 1990-07-16 | 1990-10-11 | 20.8% | 0.5654 | 0.8555 | 0.7558 | True |
| 1998-07-17 | 1998-10-08 | 21.9% | 0.7084 | 0.8587 | 0.6579 | True |
| 1999-07-16 | 1999-10-15 | 11.3% | 0.7373 | 0.8432 | 0.7709 | True |
| 2000-03-24 | 2002-10-09 | 49.2% | 0.8373 | 0.8668 | 0.7462 | True |
| 2007-10-09 | 2009-03-09 | 54.6% | 0.7779 | 0.8842 | 0.4749 | True |
| 2012-04-02 | 2012-06-04 | 10.1% | 1.0 | 0.8591 | 0.9129 | False |
| 2015-06-23 | 2016-02-11 | 15.5% | 0.8778 | 0.8578 | 0.8914 | True |

Tax brought forward: realized gain on an average cost basis × 18.46%, as a share of the portfolio at the year's start; the yearly allowance is left out. An explore look is not a result: it goes to the register, never the KB.
