# Explore-tier shadow conditioners — pre-seal slice

**Slice:** report dates 2010-06-25 → 2017-12-29 (< `SEAL_START` 2018-01-01) · 1893 report dates · 30820 observations · inputs fetched 2026-09-26
**Verdict on every arm:** `exploratory` — `verdict(sealed=False)`; nothing here can pass.
**Multiplicity:** 13 arms (2 optional, own subsample) × 3 horizons × 6 assets looked at, all counted; this report prints Gold's tables.

## Per-asset skill vs `unconditional` — Gold

| arm | h | n dates | Gold | 95% CI | coverage P25–P75 |
|---|---|---|---|---|---|
| `dd_bin` | 5 | 1893 | +0.0012 | [-0.004, +0.007] | 0.512 |
| `dd_x_frag` | 5 | 1893 | +0.0041 | [-0.003, +0.011] | 0.507 |
| `dd_bin` | 10 | 1893 | -0.0009 | [-0.008, +0.006] | 0.519 |
| `dd_x_frag` | 10 | 1893 | +0.0036 | [-0.005, +0.012] | 0.511 |
| `dd_bin` | 20 | 1893 | -0.0031 | [-0.014, +0.008] | 0.526 |
| `dd_x_frag` | 20 | 1893 | +0.0027 | [-0.009, +0.015] | 0.514 |

## Gold structure check — realized forward change by S&P drawdown bin × OR state

Width = P75 − P25 (pct). `side` = median vs the slice's unconditional Gold median. `spells` = distinct runs of the S&P below −5% in the cell. Stressed = S&P drawdown ≤ −5%.

### Gold h=5: stressed × OR state

| dd_stressed | or_state | n | spells | p25 | p50 | p75 | width | side | uncond_p50 |
|---|---|---|---|---|---|---|---|---|---|
| dd<=-5 | Elevated | 169 | 11 | -1.62 | 0.21 | 1.71 | 3.33 | right | 0.05 |
| dd<=-5 | Normal | 286 | 27 | -1.18 | 0.18 | 1.36 | 2.54 | right | 0.05 |
| dd>-5 | Elevated | 118 | 0 | -0.97 | 0.02 | 1.04 | 2.01 | left | 0.05 |
| dd>-5 | Normal | 1320 | 0 | -0.93 | 0.04 | 1.02 | 1.95 | left | 0.05 |

### Gold h=10: stressed × OR state

| dd_stressed | or_state | n | spells | p25 | p50 | p75 | width | side | uncond_p50 |
|---|---|---|---|---|---|---|---|---|---|
| dd<=-5 | Elevated | 169 | 11 | -2.31 | 0.35 | 2.52 | 4.83 | right | 0.10 |
| dd<=-5 | Normal | 286 | 27 | -1.62 | 0.29 | 1.86 | 3.48 | right | 0.10 |
| dd>-5 | Elevated | 118 | 0 | -1.41 | 0.06 | 1.49 | 2.90 | left | 0.10 |
| dd>-5 | Normal | 1320 | 0 | -1.33 | 0.09 | 1.44 | 2.77 | left | 0.10 |

### Gold h=20: stressed × OR state

| dd_stressed | or_state | n | spells | p25 | p50 | p75 | width | side | uncond_p50 |
|---|---|---|---|---|---|---|---|---|---|
| dd<=-5 | Elevated | 169 | 11 | -3.05 | 0.52 | 3.62 | 6.67 | right | 0.21 |
| dd<=-5 | Normal | 286 | 27 | -2.24 | 0.47 | 2.15 | 4.39 | right | 0.21 |
| dd>-5 | Elevated | 118 | 0 | -2.02 | 0.15 | 2.11 | 4.13 | left | 0.21 |
| dd>-5 | Normal | 1320 | 0 | -1.91 | 0.19 | 2.03 | 3.94 | left | 0.21 |

### Gold h=20: stressed alone — the dose-response rival

| dd_stressed | n | spells | p25 | p50 | p75 | width | side | uncond_p50 |
|---|---|---|---|---|---|---|---|---|
| dd<=-5 | 455 | 31 | -2.51 | 0.49 | 2.66 | 5.17 | right | 0.21 |
| dd>-5 | 1438 | 0 | -1.92 | 0.19 | 2.04 | 3.96 | left | 0.21 |

## Gold rival check — stressed bin × OR state, forward change ÷ σ

Each row's forward change is divided by a σ known at *t*: `har_scaled`'s σ forecast for Gold at that horizon, and Gold's trailing 10-day realized σ scaled to the horizon. Widths are P75 − P25 in σ units. A state that only restates Gold's vol would put the Elevated/Normal width ratio near 1.

| h | or_state | n | spells | width ÷ har σ | width ÷ 10d σ |
|---|---|---|---|---|---|
| 5 | Elevated | 169 | 11 | 1.63 | 1.55 |
| 5 | Normal | 286 | 27 | 1.34 | 1.31 |
| 10 | Elevated | 169 | 11 | 1.67 | 1.58 |
| 10 | Normal | 286 | 27 | 1.33 | 1.32 |
| 20 | Elevated | 169 | 11 | 1.74 | 1.63 |
| 20 | Normal | 286 | 27 | 1.35 | 1.32 |

## Are the stressed days spread over the tape? — per year

| year | report dates | stressed Elevated | spells | stressed Normal | spells |
|---|---|---|---|---|---|
| 2010 | 132 | 38 | 3 | 61 | 5 |
| 2011 | 252 | 72 | 4 | 58 | 6 |
| 2012 | 250 | 0 | 0 | 49 | 4 |
| 2013 | 252 | 0 | 0 | 0 | 0 |
| 2014 | 252 | 4 | 1 | 6 | 2 |
| 2015 | 252 | 31 | 2 | 52 | 6 |
| 2016 | 252 | 24 | 1 | 60 | 4 |
| 2017 | 251 | 0 | 0 | 0 | 0 |

## Reproduce

```
cd .macro-assist && python explore_conditioner.py --cached
```

Inputs: `refit_models._fetch_price_history(TABLE_START)`, `refit_models._fetch_fred_series`, `fragility_or.build_channels(stride=1)`; flags `pit_flags(q=0.9, min_warmup=252)`; MIN_N=10; BURN_IN=252; DD_EDGES=(-0.05, -0.1); HAR_WINDOW=1250; HAR_KEYS=['Bitcoin', 'Gold', 'SP500', 'WTI Oil']; N_BOOT=2000; SEED=7.
