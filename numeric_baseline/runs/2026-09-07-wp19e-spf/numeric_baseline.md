# Numeric directional baseline — WP-21.A

> **The question.** Can a small, regularised numeric model predict 5/10/20-day
> direction on these assets at all? If it cannot, the directional product is dead
> for every model class and the LLM was never the problem. If it can, this is the
> upper bound on achievable skill and the benchmark the LLM arm has never had.

- Panel: **2005-01-03 → 2026-09-07** (5656 business days)
- Features per asset: **20** market (own-price + shared macro state) + **7** exogenous (SPF consensus); unrevised inputs only
- Walk-forward: expanding window, min train **756** days, refit every **21** steps, embargo **horizon + 1** trading days

## Headline

| Arm | inputs | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `ridge` | market | 42054 | 0.530 | 0.517 | 0.271 | -0.087 | 0.118 | inverted | **no edge** |
| `gbm` | market | 40181 | 0.526 | 0.514 | 0.264 | -0.059 | 0.102 | inverted | **no edge** |
| `exogenous_spf` | exogenous | 41050 | 0.561 | 0.533 | 0.254 | -0.030 | 0.078 | mixed | **no edge** |
| `market_plus_exo` | market+exogenous | 46628 | 0.537 | 0.523 | 0.280 | -0.124 | 0.141 | mixed | **no edge** |
| `neutral` | comparator | 0 | n/a | 0.500 | n/a | n/a | n/a | n/a | **abstains** |
| `random_walk` | comparator | 58747 | 0.498 | 0.499 | 0.253 | -0.011 | 0.052 | inverted | **no edge** |
| `always_bullish` | comparator | 61087 | 0.557 | 0.546 | 0.247 | -0.000 | 0.007 | n/a | **no edge** |

> **Sample.** all arms scored on the same 75450 calls. The comparators call exactly the (date, asset)
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

## The exogenous arms (Phase 19, re-pointed)

> `exogenous_spf` is fit on the Phase-19 anchor **alone** — the Philadelphia
> Fed SPF economist consensus, no price and no market input. `market_plus_exo`
> is the same ridge on the market panel **plus** those columns. Two questions,
> not one: does the anchor carry direction by itself (row 1 against the
> comparators), and does it add anything on top of the market panel
> (`market_plus_exo` against `ridge` — same model, same sample, same rows).

> **Why this is the whole branch's test and not a sixth arm.** Phase 19's own
> gate was an A/B against the market-only LLM arm, and v1.6 cut that arm's
> calls — the comparator froze. Scoring the anchor here re-points the gate at
> the WP-21.A benchmark [KB-024], which is a real bar and a hard one.

> **What is missing from it, deliberately.** The SEP dot plot (FRED serves the
> current vintage; each release rewrites earlier years) and the branch's LLM
> extraction layers (trained on the dated text they would read — DESIGN §6.2).
> So this scores the branch's *deterministic, point-in-time* half. A null here
> is a null for the SPF anchor as a directional input, not for the
> expectations-gap mechanism, which needs the FOMC-drift layer this cannot test.

### Increment over the market panel

| metric | `ridge` | `market_plus_exo` | Δ |
|---|---|---|---|
| decisive hit-rate | 0.530 | 0.537 | +0.007 |
| Brier | 0.271 | 0.280 | +0.009 |
| BSS | -0.087 | -0.124 | -0.037 |
| ECE | 0.118 | 0.141 | +0.022 |

> A Δ inside the noise of a walk-forward this size is a null, not a small
> gain: the two arms differ by seven columns on tens of thousands of shared
> calls, so read the sign only if the pre-committed bar also moves.

## Per-horizon

| Arm | window | n calls | n decisive | decisive hit-rate | Brier | BSS |
|---|---|---|---|---|---|---|
| `ridge` | t5 | 25230 | 11708 | 0.540 | 0.262 | -0.054 |
| `ridge` | t10 | 25170 | 13855 | 0.529 | 0.269 | -0.080 |
| `ridge` | t20 | 25050 | 16491 | 0.524 | 0.278 | -0.116 |
| `gbm` | t5 | 25230 | 11340 | 0.530 | 0.258 | -0.035 |
| `gbm` | t10 | 25170 | 12658 | 0.523 | 0.263 | -0.052 |
| `gbm` | t20 | 25050 | 16183 | 0.526 | 0.270 | -0.081 |
| `exogenous_spf` | t5 | 25230 | 11314 | 0.551 | 0.252 | -0.019 |
| `exogenous_spf` | t10 | 25170 | 13742 | 0.559 | 0.253 | -0.028 |
| `exogenous_spf` | t20 | 25050 | 15994 | 0.568 | 0.255 | -0.041 |
| `market_plus_exo` | t5 | 25230 | 13174 | 0.537 | 0.268 | -0.076 |
| `market_plus_exo` | t10 | 25170 | 15346 | 0.535 | 0.278 | -0.116 |
| `market_plus_exo` | t20 | 25050 | 18108 | 0.538 | 0.290 | -0.166 |
| `neutral` | t5 | 25230 | 0 | n/a | n/a | n/a |
| `neutral` | t10 | 25170 | 0 | n/a | n/a | n/a |
| `neutral` | t20 | 25050 | 0 | n/a | n/a | n/a |
| `random_walk` | t5 | 25230 | 18071 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t10 | 25170 | 19663 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t20 | 25050 | 21013 | 0.504 | 0.252 | -0.009 |
| `always_bullish` | t5 | 25230 | 18790 | 0.547 | 0.248 | -0.000 |
| `always_bullish` | t10 | 25170 | 20442 | 0.557 | 0.247 | -0.000 |
| `always_bullish` | t20 | 25050 | 21855 | 0.566 | 0.246 | -0.001 |

## What each input was worth

### `ridge` — 18 streams, 3601 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `rv_20` | -0.123 | 0.826 | -0.009 |
| `ret_60` | -0.024 | 0.863 | -0.005 |
| `vol_ratio` | +0.035 | 0.800 | -0.004 |
| `vix_level` | +0.035 | 0.840 | -0.004 |
| `breakeven_chg_20` | +0.014 | 0.890 | -0.003 |
| `vix_pct_252` | -0.052 | 0.829 | -0.003 |
| `ma_gap_50` | -0.023 | 0.885 | -0.003 |
| `drawdown` | -0.121 | 0.806 | +0.002 |
| `curve` | -0.021 | 0.893 | -0.002 |
| `baa_z` | -0.011 | 0.861 | -0.001 |
| `dxy_ret_20` | -0.016 | 0.815 | -0.001 |
| `real_yield_chg_20` | -0.047 | 0.874 | -0.001 |
| `baa_chg_20` | -0.021 | 0.923 | -0.001 |
| `y10_chg_20` | -0.031 | 0.800 | -0.001 |
| `sp_ret_20` | -0.038 | 0.828 | +0.001 |
| `ma_gap_200` | -0.022 | 0.863 | -0.000 |
| `vix_chg_20` | -0.002 | 0.892 | +0.000 |
| `ret_20` | -0.014 | 0.778 | -0.000 |
| `ret_5` | +0.007 | 0.791 | -0.000 |
| `curve_chg_20` | +0.075 | 0.791 | -0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

### `gbm` — 18 streams, 3601 refits

| input | mean split importance | mean permutation drop |
|---|---|---|
| `drawdown` | 0.072 | +0.003 |
| `vol_ratio` | 0.069 | +0.003 |
| `ma_gap_50` | 0.053 | +0.002 |
| `curve_chg_20` | 0.036 | +0.002 |
| `baa_chg_20` | 0.049 | +0.002 |
| `breakeven_chg_20` | 0.028 | -0.002 |
| `vix_chg_20` | 0.028 | +0.002 |
| `ret_60` | 0.059 | -0.002 |
| `curve` | 0.107 | +0.001 |
| `sp_ret_20` | 0.021 | +0.001 |
| `baa_z` | 0.103 | +0.001 |
| `y10_chg_20` | 0.029 | +0.001 |
| `rv_20` | 0.083 | +0.001 |
| `dxy_ret_20` | 0.031 | +0.001 |
| `ma_gap_200` | 0.069 | -0.001 |
| `ret_5` | 0.019 | +0.001 |
| `ret_20` | 0.020 | +0.000 |
| `real_yield_chg_20` | 0.033 | -0.000 |
| `vix_pct_252` | 0.022 | +0.000 |
| `vix_level` | 0.068 | -0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> Split importances are unsigned and count *splits*, which rewards high-cardinality
> noise — read the permutation column, not this one, for what an input was worth.

### `exogenous_spf` — 18 streams, 3803 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `spf_curve` | -0.048 | 0.878 | +0.011 |
| `spf_10y_revision` | -0.056 | 0.849 | -0.004 |
| `spf_10y_path` | +0.067 | 0.850 | -0.004 |
| `spf_3m_revision` | +0.004 | 0.835 | +0.003 |
| `spf_staleness` | -0.004 | 0.917 | +0.001 |
| `spf_policy_path` | -0.032 | 0.952 | -0.001 |
| `spf_unemp_revision` | +0.012 | 0.736 | -0.001 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

### `market_plus_exo` — 18 streams, 3601 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `spf_10y_path` | +0.077 | 0.843 | -0.008 |
| `spf_policy_path` | -0.045 | 0.828 | +0.005 |
| `spf_unemp_revision` | +0.032 | 0.693 | -0.005 |
| `curve` | -0.021 | 0.837 | +0.004 |
| `vix_pct_252` | -0.040 | 0.775 | +0.002 |
| `spf_staleness` | +0.001 | 0.944 | +0.002 |
| `ma_gap_200` | -0.024 | 0.771 | +0.002 |
| `ret_60` | -0.100 | 0.851 | +0.002 |
| `breakeven_chg_20` | +0.016 | 0.902 | -0.001 |
| `rv_20` | -0.157 | 0.783 | -0.001 |
| `spf_3m_revision` | +0.032 | 0.772 | +0.001 |
| `baa_z` | -0.011 | 0.864 | +0.001 |
| `vix_level` | +0.022 | 0.802 | -0.001 |
| `curve_chg_20` | +0.057 | 0.840 | +0.001 |
| `spf_10y_revision` | -0.082 | 0.815 | -0.001 |
| `drawdown` | -0.086 | 0.802 | -0.001 |
| `ret_5` | +0.007 | 0.784 | +0.001 |
| `sp_ret_20` | -0.039 | 0.822 | +0.001 |
| `ma_gap_50` | -0.079 | 0.885 | +0.000 |
| `vix_chg_20` | -0.001 | 0.869 | -0.000 |
| `baa_chg_20` | -0.017 | 0.897 | +0.000 |
| `spf_curve` | +0.002 | 0.849 | -0.000 |
| `ret_20` | -0.010 | 0.793 | +0.000 |
| `vol_ratio` | +0.043 | 0.789 | -0.000 |
| `dxy_ret_20` | -0.025 | 0.813 | -0.000 |
| `real_yield_chg_20` | -0.040 | 0.848 | -0.000 |
| `y10_chg_20` | -0.023 | 0.805 | +0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

