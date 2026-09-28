# Explore-tier shadow conditioners — pre-seal slice

**Slice:** report dates 2010-06-25 → 2017-12-29 (< `SEAL_START` 2018-01-01) · 1893 report dates · 30820 observations · inputs fetched 2026-08-12
**Verdict on every arm:** `exploratory` — `verdict(sealed=False)`; nothing here can pass.
**Multiplicity:** 13 arms (2 optional, own subsample) × 3 horizons × 6 assets looked at, all reported.

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

## Gold rival check — stressed bin × `har_scaled` σ tercile × OR state, h=20

Tercile edges are the stressed bin's own `har_scaled` σ terciles on Gold, computed known-by-*t*.

| sigma_tercile | or_state | n | spells | p25 | p50 | p75 | width |
|---|---|---|---|---|---|---|---|
| low | Elevated | 21 | 4 | -1.88 | 0.44 | 2.14 | 4.02 |
| low | Normal | 131 | 17 | -1.69 | 0.41 | 1.82 | 3.51 |
| mid | Elevated | 48 | 7 | -2.49 | 0.50 | 2.88 | 5.37 |
| mid | Normal | 104 | 13 | -2.07 | 0.46 | 2.23 | 4.30 |
| high | Elevated | 100 | 9 | -3.33 | 0.55 | 3.79 | 7.12 |
| high | Normal | 51 | 8 | -2.61 | 0.52 | 2.87 | 5.48 |

### σ tercile alone — the rival without the state

| sigma_tercile | n | spells | p25 | p50 | p75 | width |
|---|---|---|---|---|---|---|
| low | 152 | 19 | -1.71 | 0.42 | 1.91 | 3.62 |
| mid | 152 | 16 | -2.21 | 0.47 | 2.50 | 4.71 |
| high | 151 | 13 | -3.08 | 0.54 | 3.47 | 6.55 |

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
