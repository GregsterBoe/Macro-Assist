# Numeric directional baseline — WP-21.A / WP-19.E / WP-21.E

> **The question.** Can a small, regularised numeric model predict 5/10/20-day
> direction on these assets at all? If it cannot, the directional product is dead
> for every model class and the LLM was never the problem. If it can, this is the
> upper bound on achievable skill and the benchmark the LLM arm has never had.

- Panel: **2005-01-03 → 2026-09-07** (5656 business days)
- Features per asset: **20** market (own-price + shared macro state) + **0** exogenous (SPF consensus) + **4** VIX term structure; unrevised inputs only
- Walk-forward: expanding window, min train **756** days, refit every **21** steps, embargo **horizon + 1** trading days
- **Seal (WP-21.E): calls dated from 2018-01-01 are the sealed holdout** — 15827 of 27132 scored reports; the bar is read there and nowhere else

## Headline — sealed holdout, from 2018-01-01 (**the bar**)

| Arm | inputs | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `ridge` | market | 21202 | 0.535 | 0.519 | 0.264 | -0.061 | 0.104 | inverted | **no edge** |
| `gbm` | market | 20234 | 0.522 | 0.511 | 0.262 | -0.051 | 0.100 | inverted | **no edge** |
| `vix_term` | vix_term | 15215 | 0.573 | 0.528 | 0.244 | +0.003 | 0.028 | inverted | **edge** |
| `market_plus_vixterm` | market+vix_term | 23172 | 0.528 | 0.516 | 0.270 | -0.083 | 0.126 | inverted | **no edge** |
| `neutral` | comparator | 0 | n/a | 0.500 | n/a | n/a | n/a | n/a | **abstains** |
| `random_walk` | comparator | 31361 | 0.496 | 0.497 | 0.253 | -0.012 | 0.054 | mixed | **no edge** |
| `always_bullish` | comparator | 32525 | 0.567 | 0.554 | 0.246 | -0.001 | 0.017 | n/a | **no edge** |

> **This is the only table a WP-21.E verdict may be read from.** The seal date
> is a constant in `numeric_baseline.py`, committed before the family was
> fitted; that commit is the whole of the claim that the slice was held out
> before the family was chosen.

> **Multiplicity.** Phase 21 capped the search at three feature families and
> they share this one sealed slice. One family clearing a 0.52 bar once is
> therefore worth about a third of what it looks like — and the cap is what
> bounds the problem, so it is not a licence to run a fourth family.

## Explore slice (not the bar)

| Arm | inputs | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `ridge` | market | 13032 | 0.533 | 0.518 | 0.265 | -0.064 | 0.106 | n/a | _not the bar_ |
| `gbm` | market | 12403 | 0.527 | 0.514 | 0.263 | -0.053 | 0.096 | n/a | _not the bar_ |
| `vix_term` | vix_term | 9640 | 0.528 | 0.511 | 0.256 | -0.029 | 0.079 | n/a | _not the bar_ |
| `market_plus_vixterm` | market+vix_term | 14731 | 0.530 | 0.518 | 0.286 | -0.148 | 0.151 | n/a | _not the bar_ |
| `neutral` | comparator | 0 | n/a | 0.500 | n/a | n/a | n/a | n/a | _not the bar_ |
| `random_walk` | comparator | 18005 | 0.498 | 0.499 | 0.253 | -0.011 | 0.052 | n/a | _not the bar_ |
| `always_bullish` | comparator | 18795 | 0.537 | 0.529 | 0.249 | -0.001 | 0.013 | n/a | _not the bar_ |

> The development surface: everything before the seal. A family may be shaped
> against these numbers, which is exactly why a verdict here would be circular.
> Separation is not computed for this slice — nothing binding is read off it.

## Full sample (this run's whole shared window)

| Arm | inputs | n decisive | decisive hit-rate | mean score | Brier | BSS | ECE | separation | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `ridge` | market | 34234 | 0.534 | 0.518 | 0.264 | -0.062 | 0.105 | inverted | **no edge** |
| `gbm` | market | 32637 | 0.524 | 0.512 | 0.262 | -0.052 | 0.098 | inverted | **no edge** |
| `vix_term` | vix_term | 24855 | 0.555 | 0.521 | 0.249 | -0.007 | 0.047 | inverted | **no edge** |
| `market_plus_vixterm` | market+vix_term | 37903 | 0.528 | 0.517 | 0.276 | -0.108 | 0.136 | inverted | **no edge** |
| `neutral` | comparator | 0 | n/a | 0.500 | n/a | n/a | n/a | n/a | **abstains** |
| `random_walk` | comparator | 49366 | 0.497 | 0.498 | 0.253 | -0.011 | 0.053 | mixed | **no edge** |
| `always_bullish` | comparator | 51320 | 0.556 | 0.545 | 0.247 | -0.000 | 0.006 | n/a | **no edge** |

> The slice earlier runs reported — **but read the window before comparing**.
> `shared_call_keys` intersects across every arm, so the feature set with the
> shortest input history sets the start date for all of them, comparators
> included. Adding a family whose input begins later than the market panel's
> therefore moves this window, and the numbers here are **not** a like-for-like
> reproduction of [KB-024] / [KB-026] whenever the spans differ. The way to
> reproduce those is `--no-exogenous --no-vix-term`, which restores the
> original market-only sample.

> This also **overlaps the sealed slice** and is not independent confirmation
> of anything in the table above it. The sealed slice is unaffected by the
> window question: it starts at 2018-01-01, well after every arm's first call, so
> the arms are compared at full width exactly where the bar is read.


> **Sample.** all arms scored on the same 64035 calls, spanning **2011-10-24 → 2026-08-31**. The comparators call exactly the (date, asset)
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

## WP-21.E family 1 — VIX term structure

> **Scope: the sealed holdout (calls from 2018-01-01).**

> `vix_term` is ridge on the term-structure family **alone** — the VIX/VIX3M
> ratio, its 20-day backwardation persistence, its 5-day change and its
> one-year percentile. `market_plus_vixterm` is the same ridge on the market
> panel **plus** those four columns. Two questions: does the curve carry
> direction by itself, and does it add anything to a panel that already has
> the VIX *level* (`market_plus_vixterm` against `ridge`).

> **Why this family first.** [KB-024] closed 'this payload, these model
> classes', not 'no feature family predicts direction'. Phase 21 capped the
> search at three families and named this one first: `vix_term` is the
> strongest single fragility component ([KB-001], AUC 0.77/0.67) and has never
> been tested for *direction*, and it costs one extra unrevised FRED series.

> **The [KB-009] objection, answered in the columns.** That screen found VIX and
> VIX3M correlate at 0.98 in levels and put `vix3m` on the prune queue. This
> family is not the level — it is the ratio of two series correlated at 0.98,
> i.e. what is left once the shared component is divided out.

> **What clearing this would mean.** Not a restored product: an argument for
> putting the column back *with the conditional distribution published
> underneath it*, which is what v1.6 made the product. A null closes family 1
> and leaves two of the three the cap allows.

### Increment over the market panel *(sealed)*

| metric | `ridge` | `market_plus_vixterm` | Δ |
|---|---|---|---|
| decisive hit-rate | 0.535 | 0.528 | -0.008 |
| Brier | 0.264 | 0.270 | +0.006 |
| BSS | -0.061 | -0.083 | -0.022 |
| ECE | 0.104 | 0.126 | +0.022 |

> [KB-026] is why this read is not a formality: seven plausible
> point-in-time columns added to this same panel made every calibration
> metric worse and the model a third more decisive. Ablate before adding.

## Per-horizon — sealed sample  *(the bar's slice)*

| Arm | window | n calls | n decisive | decisive hit-rate | Brier | BSS |
|---|---|---|---|---|---|---|
| `ridge` | t5 | 13350 | 5822 | 0.549 | 0.255 | -0.031 |
| `ridge` | t10 | 13315 | 7012 | 0.536 | 0.262 | -0.054 |
| `ridge` | t20 | 13245 | 8368 | 0.524 | 0.272 | -0.089 |
| `gbm` | t5 | 13350 | 5800 | 0.529 | 0.256 | -0.029 |
| `gbm` | t10 | 13315 | 6160 | 0.516 | 0.261 | -0.047 |
| `gbm` | t20 | 13245 | 8274 | 0.521 | 0.267 | -0.069 |
| `vix_term` | t5 | 13350 | 3736 | 0.568 | 0.246 | -0.001 |
| `vix_term` | t10 | 13315 | 5145 | 0.579 | 0.243 | +0.004 |
| `vix_term` | t20 | 13245 | 6334 | 0.571 | 0.244 | +0.004 |
| `market_plus_vixterm` | t5 | 13350 | 6283 | 0.541 | 0.260 | -0.046 |
| `market_plus_vixterm` | t10 | 13315 | 7632 | 0.526 | 0.266 | -0.068 |
| `market_plus_vixterm` | t20 | 13245 | 9257 | 0.520 | 0.280 | -0.121 |
| `neutral` | t5 | 13350 | 0 | n/a | n/a | n/a |
| `neutral` | t10 | 13315 | 0 | n/a | n/a | n/a |
| `neutral` | t20 | 13245 | 0 | n/a | n/a | n/a |
| `random_walk` | t5 | 13350 | 9679 | 0.490 | 0.254 | -0.014 |
| `random_walk` | t10 | 13315 | 10472 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t20 | 13245 | 11210 | 0.503 | 0.252 | -0.009 |
| `always_bullish` | t5 | 13350 | 10034 | 0.557 | 0.247 | -0.000 |
| `always_bullish` | t10 | 13315 | 10859 | 0.568 | 0.246 | -0.001 |
| `always_bullish` | t20 | 13245 | 11632 | 0.574 | 0.245 | -0.002 |

## Per-horizon — full sample

| Arm | window | n calls | n decisive | decisive hit-rate | Brier | BSS |
|---|---|---|---|---|---|---|
| `ridge` | t5 | 21425 | 9367 | 0.543 | 0.257 | -0.037 |
| `ridge` | t10 | 21365 | 11331 | 0.535 | 0.262 | -0.054 |
| `ridge` | t20 | 21245 | 13536 | 0.527 | 0.271 | -0.088 |
| `gbm` | t5 | 21425 | 9167 | 0.530 | 0.256 | -0.028 |
| `gbm` | t10 | 21365 | 10205 | 0.522 | 0.261 | -0.044 |
| `gbm` | t20 | 21245 | 13265 | 0.521 | 0.268 | -0.074 |
| `vix_term` | t5 | 21425 | 6548 | 0.552 | 0.249 | -0.006 |
| `vix_term` | t10 | 21365 | 8086 | 0.558 | 0.247 | -0.003 |
| `vix_term` | t20 | 21245 | 10221 | 0.556 | 0.250 | -0.012 |
| `market_plus_vixterm` | t5 | 21425 | 10412 | 0.538 | 0.265 | -0.065 |
| `market_plus_vixterm` | t10 | 21365 | 12539 | 0.527 | 0.273 | -0.095 |
| `market_plus_vixterm` | t20 | 21245 | 14952 | 0.523 | 0.287 | -0.149 |
| `neutral` | t5 | 21425 | 0 | n/a | n/a | n/a |
| `neutral` | t10 | 21365 | 0 | n/a | n/a | n/a |
| `neutral` | t20 | 21245 | 0 | n/a | n/a | n/a |
| `random_walk` | t5 | 21425 | 15140 | 0.491 | 0.253 | -0.014 |
| `random_walk` | t10 | 21365 | 16515 | 0.495 | 0.253 | -0.012 |
| `random_walk` | t20 | 21245 | 17711 | 0.503 | 0.252 | -0.009 |
| `always_bullish` | t5 | 21425 | 15734 | 0.547 | 0.248 | -0.000 |
| `always_bullish` | t10 | 21365 | 17171 | 0.556 | 0.247 | -0.000 |
| `always_bullish` | t20 | 21245 | 18415 | 0.563 | 0.246 | -0.001 |


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

### `vix_term` — 18 streams, 3108 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `vix_term_ratio` | +0.077 | 0.734 | -0.003 |
| `vix_term_pct_252` | -0.018 | 0.824 | +0.003 |
| `vix_term_persist_20` | -0.037 | 0.779 | +0.002 |
| `vix_term_chg_5` | -0.003 | 0.765 | +0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

### `market_plus_vixterm` — 18 streams, 3061 refits

| input | mean coefficient | sign stability | mean permutation drop |
|---|---|---|---|
| `vix_level` | +0.091 | 0.822 | -0.004 |
| `vix_term_ratio` | +0.086 | 0.775 | +0.002 |
| `baa_chg_20` | +0.005 | 0.805 | +0.001 |
| `vol_ratio` | +0.044 | 0.846 | +0.001 |
| `sp_ret_20` | -0.046 | 0.816 | +0.001 |
| `baa_z` | -0.033 | 0.839 | +0.001 |
| `drawdown` | -0.121 | 0.762 | +0.001 |
| `curve_chg_20` | +0.187 | 0.932 | -0.001 |
| `vix_pct_252` | -0.142 | 0.830 | +0.001 |
| `ma_gap_200` | -0.061 | 0.838 | +0.001 |
| `curve` | +0.020 | 0.799 | -0.001 |
| `dxy_ret_20` | -0.028 | 0.804 | +0.001 |
| `vix_term_persist_20` | -0.064 | 0.815 | -0.001 |
| `rv_20` | -0.099 | 0.817 | -0.001 |
| `ret_20` | -0.064 | 0.845 | -0.001 |
| `y10_chg_20` | -0.062 | 0.820 | +0.000 |
| `vix_chg_20` | -0.019 | 0.852 | +0.000 |
| `real_yield_chg_20` | -0.079 | 0.889 | +0.000 |
| `ret_60` | -0.023 | 0.883 | -0.000 |
| `breakeven_chg_20` | +0.006 | 0.836 | +0.000 |
| `ret_5` | -0.020 | 0.850 | +0.000 |
| `vix_term_pct_252` | +0.074 | 0.851 | -0.000 |
| `vix_term_chg_5` | -0.025 | 0.749 | -0.000 |
| `ma_gap_50` | +0.013 | 0.778 | -0.000 |

> A positive permutation drop means shuffling that input *cost* out-of-sample
> accuracy — the input was load-bearing. Values at or below zero mean it was not.
> `ret_20` is the 20-day reversion candidate: a reliably negative coefficient
> with high sign stability is what would confirm the effect.

