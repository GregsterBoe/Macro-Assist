# Numeric directional baseline — WP-21.A

> **The question.** Can a small, regularised numeric model predict 5/10/20-day
> direction on these assets at all? If it cannot, the directional product is dead
> for every model class and the LLM was never the problem. If it can, this is the
> upper bound on achievable skill and the benchmark the LLM arm has never had.

- Panel: **2005-01-03 → 2026-09-04** (5655 business days)
- Features per asset: **20** (own-price + shared macro state; unrevised inputs only)
- Walk-forward: expanding window, min train **756** days, refit every **21** steps, embargo **horizon + 1** trading days

## Headline

| Arm | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|---|
| `ridge` | 42043 | 0.530 | 0.517 | 0.271 | -0.087 | 0.119 | inverted | **no edge** |
| `gbm` | 40173 | 0.526 | 0.514 | 0.264 | -0.059 | 0.103 | inverted | **no edge** |
| `neutral` | 0 | n/a | 0.500 | n/a | n/a | n/a | n/a | **abstains** |
| `random_walk` | 58733 | 0.498 | 0.499 | 0.253 | -0.011 | 0.052 | inverted | **no edge** |
| `always_bullish` | 61073 | 0.557 | 0.546 | 0.247 | -0.000 | 0.007 | n/a | **no edge** |

> **Sample.** all arms scored on the same 75432 calls. The comparators call exactly the (date, asset)
> pairs the models called — a model cannot predict an asset until it has
> `min_train` days of that asset's own history, and handing `always_bullish`
> the difference would flatter the benchmark the verdict turns on.

> **Bar (pre-committed).** An arm shows an edge only with n ≥ 30 decisive
> calls, decisive hit-rate > 0.52, and either BSS > 0
> or an `aligned` separation ordering. Same standard as [KB-007] / [KB-022].

> **Read the comparator rows before the model rows.** In a drifting tape
> `always_bullish` collects hit-rate for free — that is why the bar also demands
> BSS or an ordering, and why a model that edges past 0.520 while
> `always_bullish` sits at 0.520 has shown nothing.

## Per-horizon

| Arm | window | n calls | n decisive | decisive hit-rate | Brier | BSS |
|---|---|---|---|---|---|---|
| `ridge` | t5 | 25224 | 11705 | 0.540 | 0.262 | -0.054 |
| `ridge` | t10 | 25164 | 13851 | 0.529 | 0.269 | -0.080 |
| `ridge` | t20 | 25044 | 16487 | 0.524 | 0.278 | -0.116 |
| `gbm` | t5 | 25224 | 11337 | 0.530 | 0.258 | -0.035 |
| `gbm` | t10 | 25164 | 12655 | 0.523 | 0.263 | -0.052 |
| `gbm` | t20 | 25044 | 16181 | 0.526 | 0.270 | -0.081 |
| `neutral` | t5 | 25224 | 0 | n/a | n/a | n/a |
| `neutral` | t10 | 25164 | 0 | n/a | n/a | n/a |
| `neutral` | t20 | 25044 | 0 | n/a | n/a | n/a |
| `random_walk` | t5 | 25224 | 18067 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t10 | 25164 | 19658 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t20 | 25044 | 21008 | 0.504 | 0.252 | -0.009 |
| `always_bullish` | t5 | 25224 | 18786 | 0.547 | 0.248 | -0.000 |
| `always_bullish` | t10 | 25164 | 20437 | 0.557 | 0.247 | -0.000 |
| `always_bullish` | t20 | 25044 | 21850 | 0.566 | 0.246 | -0.001 |

## What each input was worth

### `ridge` — 18 streams, 3601 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `rv_20` | -0.123 | 0.826 | -0.009 |
| `ret_60` | -0.024 | 0.863 | -0.006 |
| `vol_ratio` | +0.035 | 0.800 | -0.005 |
| `vix_level` | +0.035 | 0.840 | -0.004 |
| `breakeven_chg_20` | +0.014 | 0.890 | -0.004 |
| `vix_pct_252` | -0.052 | 0.829 | -0.003 |
| `drawdown` | -0.121 | 0.806 | +0.003 |
| `ma_gap_50` | -0.023 | 0.885 | -0.002 |
| `curve` | -0.021 | 0.893 | -0.002 |
| `baa_z` | -0.011 | 0.861 | -0.001 |
| `ret_20` | -0.014 | 0.778 | -0.001 |
| `dxy_ret_20` | -0.016 | 0.815 | -0.001 |
| `ret_5` | +0.007 | 0.791 | -0.001 |
| `sp_ret_20` | -0.038 | 0.828 | +0.001 |
| `real_yield_chg_20` | -0.047 | 0.874 | -0.000 |
| `ma_gap_200` | -0.022 | 0.863 | +0.000 |
| `y10_chg_20` | -0.031 | 0.800 | +0.000 |
| `curve_chg_20` | +0.075 | 0.791 | +0.000 |
| `baa_chg_20` | -0.021 | 0.923 | -0.000 |
| `vix_chg_20` | -0.002 | 0.892 | -0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

### `gbm` — 18 streams, 3601 refits

| input | mean split importance | mean permutation drop |
|---|---|---|
| `drawdown` | 0.072 | +0.004 |
| `vol_ratio` | 0.069 | +0.003 |
| `ret_60` | 0.059 | -0.002 |
| `curve_chg_20` | 0.036 | +0.002 |
| `ma_gap_50` | 0.053 | +0.002 |
| `sp_ret_20` | 0.021 | +0.002 |
| `breakeven_chg_20` | 0.028 | -0.002 |
| `vix_chg_20` | 0.028 | +0.001 |
| `curve` | 0.107 | +0.001 |
| `baa_chg_20` | 0.049 | +0.001 |
| `baa_z` | 0.103 | +0.001 |
| `ma_gap_200` | 0.069 | -0.001 |
| `ret_5` | 0.019 | +0.001 |
| `real_yield_chg_20` | 0.033 | -0.001 |
| `y10_chg_20` | 0.029 | +0.001 |
| `dxy_ret_20` | 0.031 | +0.001 |
| `rv_20` | 0.083 | +0.001 |
| `ret_20` | 0.020 | +0.000 |
| `vix_pct_252` | 0.022 | +0.000 |
| `vix_level` | 0.068 | -0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> Split importances are unsigned and count *splits*, which rewards high-cardinality
> noise — read the permutation column, not this one, for what an input was worth.

