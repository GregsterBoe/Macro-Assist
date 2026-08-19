# Self-Managed Paper Portfolio — Design (WP-20.A, scope-lock)

Design/scope-lock for **Phase 20** (see `Project_Development.md`). This is the
**locked contract** the WP-20.B accounting core and WP-20.C sizing rule build
against. Code lives beside this file in `.macro-assist/portfolio/`.

Mirrors the Phase-19 (`exogenous/DESIGN.md`) discipline: fixed contracts,
forward-only validation, a pre-committed go/no-go bar, and a documented kill
procedure. Modular / removable — the prediction pipeline is never touched.

Decisions locked 2026-08-19:
- **v1 = mechanical sizing only** (experiment #1: *does the signal have edge?*).
  Zero discretionary LLM trading. Loosening → Phase-16 track, not here.
- **v1 = paper / forward-test only.** No broker. Simulated fills on yfinance
  closes. Real-broker integration is WP-20.E, gated on v1 showing edge.
- **Primary success bar:** a virtual book's **risk-adjusted excess return vs a
  buy-and-hold benchmark of the same universe**, measured forward.

---

## 1. Target (what v1 produces)

A weekly-rebalanced **virtual book (ledger)** per prediction arm that converts the
pipeline's already-emitted, dated predictions into **vol-targeted sized
positions**, marks them on yfinance closes, and reports **NAV vs benchmark**.

The scored payload — the only thing the go/no-go gate reads — is
**information ratio of excess return vs buy-and-hold**, plus max drawdown as a
risk guard. Everything else (per-arm comparison, turnover, hit-rate, the decision
log) is diagnostic context.

**Explicitly NOT the target for v1:** a leveraged directional index bet; a tuned
backtest equity curve; discretionary LLM allocation; real-money execution. Each is
a separate later experiment and is out of scope (Phase-16/17 discipline).

---

## 2. Scope & universe — **corrects the Phase-20 sketch**

The Phase-20 sketch named the user's Trade-Republic sleeves (ACWI / EM /
small-cap / Bund). **That was wrong for a signal test:** the book must trade the
assets the pipeline *actually predicts*, or the P&L measures something other than
the signal. The pipeline emits biases for exactly six assets
(`score_predictions.ASSET_TICKERS`):

| Predicted asset | Ticker | Tradeable in a paper cash book? | v1 universe |
|---|---|---|---|
| S&P 500 | `^GSPC` | yes (index proxy / SPY) | **core** |
| Gold | `GC=F` | yes | **core** |
| Bitcoin | `BTC-USD` | yes | **core** |
| 10Y Treasury **Yield** | `^TNX` | only via a **bond-price** proxy (IEF/TLT), **sign inverted** (Bullish-yield ⇒ short bonds) | **core (mapped)** |
| WTI Oil | `CL=F` | awkward (futures roll / contango in a long book) | **excluded v1** |
| DXY | `DX-Y.NYB` | awkward (dollar index; FX, not a cash holding) | **excluded v1** |

**v1 tradeable universe = {S&P 500, Gold, Bitcoin, 10Y-via-bond-proxy}.** WTI and
DXY are deferred — they are real predictions but poor fits for a long/short cash
book; adding them is a WP-20.D "add by measured value" decision, not a v1
dependency. Keeping the universe to four clean instruments keeps the test about
the macro signal, not instrument mechanics.

**Base currency = USD.** The predicted assets and the scorer are USD; running the
book in USD removes EUR/USD FX noise from the edge measurement. EUR conversion
(the `parse_positions.py` USD→EUR path already exists) is a WP-20.E realism
concern, not a v1 one.

**Long/short allowed** in the paper book (it is virtual) so a Bearish call is
expressible as a short. Realistic long-only-with-cash constraints are a WP-20.E
concern flagged now, not imposed on the clean signal test.

---

## 3. The sizing rule (deterministic, no LLM) — **vol-target, not Kelly**

One rule, fully transparent, recomputed each rebalance `t`. Chosen: **inverse-vol
risk budgeting with a portfolio vol target.** Kelly is rejected for v1 — it is
hypersensitive to the return estimate being right, and KB-007/KB-013 say our point
estimates are the weak link. Vol-target expresses "some risk, deliberately."

For each asset `a` in the v1 universe, at rebalance date `t`, horizon `h = 5`
(weekly cadence ⇒ the T+5 predictions):

1. **Direction** `d_a ∈ {+1, −1, 0}` from the note bias
   (`Bullish=+1`, `Bearish=−1`, `Neutral`/absent`=0`).
   **10Y is on the yield** → the bond-proxy position takes `−d_a`
   (Bullish yield ⇒ short bonds).
2. **Confidence** `c_a ∈ [0,1]` from the note's confidence field
   (for the `kimi` arm, from ensemble agreement — size *is* confidence made
   consequential; directly attacks the clamped-confidence problem, KB-007).
3. **Risk (dispersion)** `σ_a` from the **HAR-RV 5-day vol forecast**
   (`vol_forecast.py`) — the purpose-built per-asset risk input.
   Cross-check against the conditional-distribution spread
   `(p90−p10)/2.56` from `conditional.lookup_distribution(bucket, a, 5, table)`;
   if the distribution is **None after fallback**, `d_a := 0` (honest abstention —
   we hold no view we can't size).
4. **Pre-limit weight** `w̃_a = d_a · c_a / σ_a` (inverse-vol, signed, confidence-scaled).
5. **Regime gate** (gross risk-on/off): scale all `w̃` by
   `g = 1 − posterior_mass_on_high_vol_states` from `regime.predict_regime`
   (High-Vol states dial the book toward cash).
6. **Portfolio vol target:** rescale `{w̃}` so ex-ante book vol
   `≈ target` (v1 default **10% annualized**), using `σ_a` and a conservative
   correlation assumption (start with `Σ|w_a|σ_a`, refine later).
7. **Risk limits (hard clamps):** `|w_a| ≤ MAX_WEIGHT` (v1 **0.35**);
   gross `Σ|w_a| ≤ GROSS_CAP` (v1 **1.5**); remainder → cash.

All seven steps are pure functions of already-computed pipeline outputs +
constants. No new model calls. Every constant lives in one config block so v1→v2
is an edit, never a rebuild.

---

## 4. The book / ledger data contract

```
Book (one JSON per arm, e.g. results/portfolio/book__market.json):
  arm:          "market" | "exogenous" | "kimi"
  base_ccy:     "USD"
  cash:         float
  positions:    { asset: {shares|units: float, entry_px: float} }
  nav_history:  [ {date, nav, gross, net, regime_gate} ]
  benchmarks:   { buy_hold: [{date, nav}], sixty_forty: [{date, nav}] }

Rebalance record (append-only decision log, per arm per week):
  as_of:        date
  bucket:       str            # conditional-dist bucket used
  regime:       {state_label, posterior}
  targets:      { asset: {bias, confidence, sigma, w_target} }
  trades:       { asset: {from_w, to_w, shares_delta, px, cost_bps} }
  nav_before / nav_after:  float
  notes:        str            # why (belief→trade), for attribution
```

- **Fills:** yfinance close on the rebalance date (the same source the scorer
  uses; consistency > realism for v1).
- **Costs:** `COST_BPS` per traded notional (v1 default **10 bps**; BTC higher —
  a per-asset override map). No slippage model in v1.
- **Marking:** daily close mark for the NAV curve; rebalance weekly.

---

## 5. Benchmarks & metrics

**Benchmarks (the number is vanity without them):**
- **Buy-and-hold, equal-vol basket of the v1 universe** — the *scientific*
  benchmark: isolates whether timing/sizing beats just holding the same assets.
- **60/40** (S&P / bonds) — real-world context.
- (secondary, real-world) buy-and-hold **ACWI**, the user's actual TR core.

**Metrics (→ the KB entry, "KB-014" when scored):** NAV/CAGR, realized vol,
**Sharpe / Sortino**, **max drawdown**, turnover, hit-rate, and the headline
**excess return + information ratio vs buy-and-hold**. Reported per arm.

---

## 6. Per-arm books — reuse the arm machinery

Predictions already carry `arm ∈ {market, exogenous, kimi}`. Instantiate **one
book per arm** + the benchmarks. P&L then becomes a new axis of the existing
`calibration_by_arm` A/B: *whose predictions make money*, not just who is
best-calibrated. Same pattern as Phase 19's arm-keyed scoring — near-free.

---

## 7. Validation discipline (inherited from Phases 17 & 19)

- **Forward-only.** The scored result is the live book accumulating from go-live.
  A **backtest is permitted only as pipeline shakedown** (verify ledger accounting
  and the sizing rule on synthetic + historical prices), **never** as a scored
  result — a tuned backtest hides exactly the reactive/lagging weakness the whole
  point is to expose.
- **Point-in-time.** At rebalance `t` the book may read only predictions,
  distributions, vol forecasts, and regime state **dated ≤ t**. No look-ahead.
- **Confirm-on-first-run.** First live rebalance: eyeball the decision log
  (targets, gate, trades) before trusting the NAV series.

---

## 8. Cadence & wiring

- **Weekly** rebalance (matches the note cadence and the T+5 horizon). New
  workflow `portfolio_rebalance.yml`, scheduled **after** the weekly scoring job
  so the week's predictions are committed; it advances each book, commits the
  ledger JSON + a short markdown report, and appends the decision log.
- Cost ≈ **zero model calls** (deterministic); just yfinance + arithmetic.

---

## 9. Go/no-go bar & kill procedure (pre-committed)

- **Go/no-go (read at ≈1 quarter, then ≈2 quarters forward):** keep the phase iff
  **at least one arm's book beats the buy-and-hold basket on information ratio**
  at an acceptable max drawdown (v1 guard: DD not worse than buy-and-hold's).
  A calibrated-but-unprofitable result is a **valuable KB-014 finding** (confirms
  edge < costs), not a failure of the experiment.
- **Kill = near-zero risk** (paper book, isolated). **Soft-kill:** disable/delete
  `portfolio_rebalance.yml` (books freeze). **Hard-kill:** delete `portfolio/` +
  its tests + the workflow + `results/portfolio/*`. The prediction pipeline and
  every arm's scoring are untouched — the module only *reads* notes.

---

## 10. Open decisions to lock in WP-20.B/C

1. **Portfolio-vol estimator** — start `Σ|w|σ` (conservative, ignores
   diversification) vs a simple constant-correlation matrix. *Lean: start simple,
   refine only if it distorts sizing.*
2. **Bond proxy for the 10Y-yield signal** — IEF (7-10y) vs TLT (20y+). *Lean:
   IEF — duration closer to the 10Y point; TLT over-levers the call.*
3. **Cash rate** — credit idle cash at a short rate (already have `^TNX`/FRED) or
   0% for v1. *Lean: 0% v1 (conservative, one fewer moving part).*
4. **Neutral handling** — flat (weight 0) vs hold-prior. *Lean: flat (honest
   abstention, matches the ensemble-Neutral semantics).*

---

## 11. File layout (proposed)

```
.macro-assist/portfolio/
  DESIGN.md          # this file
  book.py            # ledger, NAV, cost model, benchmarks (WP-20.B, no LLM)
  sizing.py          # §3 rule: pipeline outputs → target weights (WP-20.C)
  rebalance.py       # weekly driver: targets → trades → commit ledger (WP-20.D)
  tests/             # accounting + sizing unit tests (point-in-time)
results/portfolio/
  book__<arm>.json   # one ledger per arm
  <date>-portfolio-report.md
.github/workflows/
  portfolio_rebalance.yml   # weekly, after scoring
```

Build order: **WP-20.B `book.py` first, in isolation** (the accounting is the
risky-to-get-wrong part — prove it on synthetic prices before any sizing logic),
then **WP-20.C `sizing.py`**, then **WP-20.D** wiring + forward run.
