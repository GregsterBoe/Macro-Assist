# Knowledge Base

<!-- Frozen verbatim from docs/record/knowledge-base.md at commit d5df1f3: the entries the fixture entry cites, and nothing else. Frozen so a later edit to the live page cannot date the cited text after the entry that cites it. Refresh only together with the fixture's timeline. -->

## KB-016 — Confirmed against the REAL composite: the cross-section doubles crisis recall, but it's a precision TRADE, not a free lunch (IMP-1.6)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_real_composite_gate`; traded assets via
yfinance + FF panel cached; **zero LLM/API cost**). Reproduce: `python
input_testing.py real`. The adoption gate for KB-015 — replaces the proxy baseline
with the real production signal.

**What we tested.** KB-015 showed the industry cross-section adds skill to a
*variance-trend-only proxy*, but flagged that the honest test is against the **full
live composite** (which also has the VIX-term arm the proxy lacked). So here the
baseline is the actual `var_led_vix35`, walked forward look-ahead-safe on the real
traded assets (SP500/VIX/VIX3M/gold/oil/DXY), scored against the real **^GSPC** ≥5%
drawdown label — the exact production setup (KB-002). Common window: 904 readings,
2008-07..2026-06 (composite ∩ industry channels, stride 5). Baseline reproduces
KB-002 (nov-AUC 0.744/0.664, recall ~0.33, precision 0.43-0.57).

**Headline — additivity CONFIRMED, but the shape changes vs KB-015.** OR-of-channels
(fire if composite OR AR OR turbulence hits its top decile) still roughly **doubles**
crisis recall against the full composite:

| horizon | composite recall / prec | OR-channels recall / prec | Δ |
|---|---|---|---|
| 5d  | 0.333 (6/18) / 0.429 | **0.722 (13/18)** / 0.323 | recall ×2.2, prec −0.11 |
| 10d | 0.321 (9/28) / 0.571 | **0.643 (18/28)** / 0.387 | recall ×2.0, prec −0.18 |

The cross-section catches crises the traded-asset composite misses — orthogonality
holds against the *real* signal, not just the proxy. **BUT** precision now **drops**
(unlike KB-015, where it held against the weak baseline): the real composite's VIX arm
already gives it strong top-decile precision, so OR-ing in the weaker-precision channels
trades ~0.11-0.18 precision for the doubled recall. Against the full composite it is a
**precision/recall trade, not a free lunch.**

**The nuance that's easy to forget.** (1) **The equal-weight continuous blend is the
WRONG adoption form.** Blending (composite+AR+TURB, rank-mean) *lifts* threshold-free
nov-AUC (0.744→0.787 at 5d, 0.664→0.689 at 10d) — the channels do carry orthogonal rank
info — but it *degrades* the validated top-decile flag (recall 0.333→0.278, precision
0.429→0.312), because averaging dilutes the composite's already-strong best alarms. So
the AUC gain and the flag-quality loss point in opposite directions; a naive blend
throws away the composite's edge. (2) **The trade is acceptable *for this product
specifically*:** fragility is a tail-risk / range-widening gauge that is NEVER a
directional call, so a false alarm is cheap (it over-widens a range) while a missed
crisis is expensive — an operating point of recall 0.72 / precision 0.32 (still ~8×
the 4% base rate) is a *good* trade here, though it would be a bad one for a directional
signal.

**Caveats.** (a) Small crisis count — 18 (5d) / 28 (10d) episodes over ~7 real macro
events (GFC, 2011, 2015-16, 2018, COVID, 2022, …); episode metrics are small integers,
indicative not precise. Regime-holdout CV (IMP-4) still owed. (b) Full-sample rank
thresholds (look-ahead in the *threshold*) — a live flag needs PIT-rolling cuts, which
will move absolute numbers. (c) Window capped at FF cache end (2026-06-30); stride 5;
single (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5) config. (d) Industry channels
run on FF (backtest only); a live feed needs a daily sector/industry panel (sector ETFs).

**What it changes.**
- **IMP-1 CLOSES positive.** The cross-section adds genuine orthogonal skill to the real
  composite; the ~0.30 recall ceiling is breakable. Concept proven end-to-end
  (KB-012 negative → KB-013/014 skill → KB-015 orthogonal → KB-016 confirmed live-baseline).
- **Adoption form is decided:** an explicit **OR-of-channels recall MODE** (a distinct
  high-recall flag), NOT a weight in the composite and NOT an equal blend. This is exactly
  backlog **IMP-4** — KB-016 hands it a validated mechanism and a live operating point.
- **Deliberately NOT auto-wired.** Because it's a precision trade (not a free lunch) and
  needs (i) a live daily industry panel and (ii) PIT-rolling thresholds and (iii) regime-
  holdout CV, promotion is IMP-4 work, not a silent live change. AR & turbulence stay
  shadow/diagnostic until then.
- A small *weighted* addition (composite-dominant + channels at low weight) is an open
  alternative to test in the WEIGHT_SCHEMES ablation — it might capture the blend's AUC
  gain without the top-decile dilution. Untested; noted for IMP-4.

→ **Both owed caveats [(a) regime-holdout CV, (b) PIT thresholds] resolved by KB-017.**

---

## KB-017 — The OR-of-channels recall doubling SURVIVES honest CV: leakage was negligible, live-safe thresholds hold it (IMP-4)

**Date:** 2026-08-25 · **Branch:** `main` · **Harness:**
`.macro-assist/input_testing.py` (`run_holdout_cv`; same channels as
`run_real_composite_gate`, **zero LLM/API cost**). Reproduce: `python
input_testing.py holdout`. Closes the two caveats [KB-016] left open.

**What we tested.** KB-016 confirmed the OR-of-channels flag (fire if the real
`var_led_vix35` composite OR industry-panel absorption OR turbulence hits its top
decile) roughly *doubles* crisis recall — but with two honest-evaluation debts: the
decile cut was ranked over the **whole window** (the thresholds had already seen the
test crises), and it had never been checked out-of-sample across regimes. This
re-scores the identical channels under three protocols on the same 904-reading window
(2008-07..2026-06): **[1] in-sample** (KB-016 protocol, reference), **[2] in-sample
restricted to the post-warmup window** (isolates window-shrink from leakage), **[3]
PIT expanding-window thresholds** — each day's decile cut fit only on that channel's
own past, 252-day warm-up, 652 evaluable readings (the realistic LIVE protocol), and
**[4] leave-one-crisis-out** — each drawdown episode is a fold, thresholds fit on every
day *outside* it (the generalization headline).

**Headline — the doubling is REAL, not a thresholding artifact.**

| protocol | composite recall (5d/10d) | OR-channels recall (5d/10d) | OR precision (5d) |
|---|---|---|---|
| [1] in-sample (KB-016) | 0.333 / 0.321 | 0.722 / 0.643 | 0.323 |
| [3] PIT (live-safe) | 0.25 / 0.333 | **0.833 / 0.867** | 0.320 |
| [4] leave-one-crisis-out | 0.333 / 0.321 | **0.611 / 0.643** | (see nuance) |

[1] reproduces KB-016 to the digit (regression check on the refactor). The decisive
comparison is **[2] vs [3]: they are nearly identical** (OR 5d 0.75 vs 0.833; 10d 0.867
vs 0.867) — so replacing full-sample thresholds with strictly PIT-safe ones **barely
moves the result**. The look-ahead in the threshold that KB-016 flagged was **negligible**;
the doubling was never an artifact of it. Under the strictest test (LOCO, thresholds
that never saw the held-out crisis) OR recall still ~doubles composite-alone. Precision
holds at ~0.32 (5d) across protocols — the same operating point, not a new cost.

**The nuance that's easy to forget.** (1) **PIT recall > in-sample recall here**
(0.833 vs 0.722 at 5d) — not because live is magically better, but because the warm-up
drops the 2008 window down to 12/15 episodes and the survivors are the ones the
expanding cut calls easily; read PIT and in-sample as *the same story on a smaller,
cleaner denominator*, not as a live improvement. (2) **LOCO 5d (0.611) sits below PIT
(0.833)** because LOCO scores all 18 crises including the early GFC ones on a
leave-one-out cut; it is the *conservative floor*, and the floor is still ~2× composite.
(3) **LOCO precision is deliberately not computed** — leave-one-out test windows are too
short for an honest precision denominator; precision is read from PIT (~0.32), where the
non-crisis days exist to divide by. (4) The whole exercise **validated the yardstick, not
just the signal**: `run_holdout_cv` is now the honest gate, so a NEW channel's "recall
went up again" only counts if it survives PIT+LOCO — otherwise it is the mechanical
artifact of OR-ing another signal onto ~7 crises.

**Caveats.** (a) Small crisis count persists — 12–28 episodes; the point estimates are
indicative, but the *robustness across four protocols* is the real evidence, not any
single number. (b) FF industry channels are still the backtest feed; a live flag needs a
daily sector/industry panel (the ONE remaining plumbing item — thresholds are now shown
PIT-safe). (c) Single (cov_ar=120, cov_turb=252, shrink=0.2, smooth=5, q=0.90, warmup=252)
config; window capped at FF cache end (2026-06). (d) LOCO fits on all *other* crises
(leave-one-out, not leave-one-regime-block-out); with n≈7 macro events that is the honest
maximum, but it is not a train-early/test-late split.

**What it changes.**
- **Resolves KB-016 caveats (a) and (b).** Regime-holdout CV done; PIT-safe thresholds
  done; the doubling survives both. The OR-of-channels recall mode is validated end-to-end
  on honest evaluation, not just the in-sample gate.
- **Operating point for the IMP-4 build is set:** OR recall MODE at the PIT point
  (recall ~0.83 / precision ~0.32 at 5d, ~0.87 / ~0.36 at 10d) — a distinct high-recall
  flag, NOT a composite weight (confirmed by KB-016's blend-degradation).
- **`run_holdout_cv` is now the adoption GATE for new channels.** Before IMP-2
  (credit/funding) or IMP-3 (downside semivariance) may enter the OR set, each must lift
  PIT/LOCO recall without collapsing precision through this harness — the guard against
  overfitting the OR knob on ~7 crises.
- **Remaining IMP-4 plumbing narrows to one item:** a live daily sector/industry ETF panel
  (thresholds are no longer a blocker). No live wiring yet — still IMP-4 work, not a silent
  change.

---

## KB-033 — The HAR-RV vol forecast as wired is a 4-parameter OLS on a few dozen rows: degenerate on every asset, worse than trailing 22-day realized vol at every horizon, and it has published `0.0% ann-vol` on 9 % of S&P and 13 % of Bitcoin note dates (WP-17.5)

**Date:** 2026-09-13 · **Branch:** `main` · **Harness:** `har_backtest.py`
(`python har_backtest.py [cache.pkl]`, ~3 min; 19 tests in
`tests/test_har_backtest.py`) · **Bar:** pre-registered in `roadmap.md` WP-17.5
before the run, reproduced below · **Live evidence:** `results/quant_context_log/`,
76 note dates 2026-05-29 → 2026-09-11.

**What we tested.** `vol_forecast.har_rv_forecast` exactly as shipped — its design
matrix, its `max(0, ·)` clip, its annualisation — called walk-forward at every
date on a window of the length the live caller hands it. `market_data` fetches
`period="90d"` and `quant_context` passes the whole thing to the function, whose
design matrix starts at lag 21. What `period="90d"` returns is **not pinned**: on
2026-09-13 under yfinance 1.4.1 it is 90 closes for `^GSPC` and `BTC-USD` and 74
for `GC=F`, i.e. an OLS of **four parameters on ~50–70 rows**.
`portfolio/rebalance.fetch_prices_and_har` uses 130 calendar days — ~90 closes
for the equity-hours instruments, ~130 for Bitcoin. The read covers 62 / 90 /
130 (the wired range) and 252 / 1000 as the counterfactual, on the four
published assets (SP500, Gold, WTI, Bitcoin) and IEF (the sizer's bond proxy),
daily from 2007 (Bitcoin 2014), 3,400–4,900 readings each.

*Target:* realized daily variance over the next `h` days, `h ∈ {1, 5, 20}` — 1
is what the OLS fits, 5 the sizer's week and the table's first horizon, 20 the
table's last. *Benchmark for the verdict:* trailing 22-day realized variance
(`rv22`), the model's own monthly regressor and what a sizing rule would fall
back to; `rv5`, `rv60` and RiskMetrics `ewma94` reported as context. *Loss:*
QLIKE (proper, robust to the noisy r² proxy); skill `= 1 − QLIKE(har)/QLIKE(rv22)`
with a 21-day block-bootstrap 95 % interval. *Bar, disqualifier first:*
`degenerate` if > 1 % of readings are a zero forecast or > 10× `rv22`; then
`skill` (> 0.02, interval above 0) / `worse` (< −0.02, interval below 0) /
`parity`. *Two secondary reads with thresholds fixed in advance:* the fetch
period is a **wiring defect** if the 1000-day window is `skill` where the wired
window is not on ≥ 3 of 4 published assets; and the consumers' IID scaling is
*calibrated at horizon* if `mean(RV_h)/mean(σ̂²) ∈ [0.75, 1.33]` and the zero-mean
Gaussian 50 % / 90 % bands cover within `[0.45, 0.55]` / `[0.86, 0.94]`. *Prior
as written:* `parity` or `worse` for the wired window at `h=5`, `skill` at `h=1`
for 1000 days, 90 % band under-covers everywhere.

### Headline — every wired window is `degenerate`, and the trailing month beats it

QLIKE skill vs `rv22` at `h=5` with the 95 % interval, zero-forecast share of
readings, verdict. The full table (`h ∈ {1, 5, 20}`, all windows, all four
benchmarks, MSE, calibration) is the harness output.

| Asset | W = 62 | **W = 90 (note, as wired)** | W = 130 (sizer, BTC) | W = 252 | W = 1000 |
|---|---|---|---|---|---|
| SP500 | −1.42 [−2.26, −0.79] · 4.8 % zero · `degenerate` | **−0.49** [−0.82, −0.23] · 2.6 % · `degenerate` | −0.43 [−0.93, −0.09] · 1.2 % · `degenerate` | +0.03 [−0.19, +0.18] · `parity` | **+0.18** [+0.07, +0.26] · `skill` |
| Gold | −2.15 [−4.98, −0.54] · 4.9 % · `degenerate` | **−0.61** [−1.20, −0.20] · 2.1 % · `degenerate` | −0.07 [−0.18, +0.03] · 1.0 % · `degenerate` | −0.13 [−0.31, +0.01] · `parity` | **+0.08** [+0.005, +0.14] · `skill` |
| WTI Oil | −2.99 [−6.05, −0.96] · 4.2 % · `degenerate` | **−1.04** [−2.11, −0.39] · 1.7 % · `degenerate` | −0.31 [−0.53, −0.11] · 0.5 % · `worse` | −0.34 [−0.81, +0.01] · `parity` | −0.02 [−0.15, +0.09] · `parity` |
| Bitcoin | −1.81 [−3.04, −0.84] · 7.4 % · `degenerate` | **−0.77** [−1.65, −0.14] · 3.7 % · `degenerate` | −2.52 [−7.25, −0.01] · 1.2 % · `degenerate` | +0.11 [−0.17, +0.29] · 0.8 % wild · `degenerate` | **+0.31** [+0.17, +0.43] · `skill` |
| IEF | −2.46 [−4.80, −1.05] · 3.1 % · `degenerate` | −0.64 [−1.30, −0.27] · 1.5 % · `degenerate` | −0.24 [−0.45, −0.05] · 0.7 % · `worse` | +0.04 [−0.05, +0.11] · `parity` | −0.01 [−0.11, +0.08] · `parity` |

- **The disqualifier fires on every instrument at 62 and 90 days, and on three
  of five at 130; the two that clear it at 130 are `worse`.** At 62 days 4–7 %
  of readings are a zero forecast (the clip on a negative OLS prediction); at 90
  days 1.5–3.7 %; at 130, 0.5–1.2 %. The zeros are not a stress artefact —
  they land in the calm, middle and stressed terciles of `rv22` at 5.2 / 5.2 /
  4.0 % (SP500, 62 days).
- **Excluding the zeros, the wired forecast still loses to the trailing month
  by a wide margin.** QLIKE skill of −0.5 to −1.0 at 90 days and −1.4 to −3.0
  at 62, at `h=5`; the intervals exclude zero on every asset at both. At `h=1`,
  the horizon the OLS actually fits, −0.10 to −0.28 at 90 days. `rv22`, `rv60`
  and `ewma94` sit within a few percent of each other; the wired HAR is 1.5–4×
  their loss. MSE skill is worse still (−2 to −80) because the wild readings
  dominate a squared loss — Bitcoin's 130-day QLIKE at `h=1` is 12.1 against
  `rv22`'s 2.2.
- **The mechanism is coefficient signs that are essentially random.** On 62-day
  SP500 fits the monthly β is negative on **70 %** of dates, the daily on 61 %,
  the weekly on 45 %; at 90 days 62 / 61 / 31 %. Three near-collinear regressors
  on a few dozen rows. At 1000 days the weekly and monthly β are never negative
  and the forecast/`rv22` ratio has a p10–p90 of 0.68–2.39 with a max of 4; at
  62 days the max is 42.
- **The forecast is a function of the window boundary.** For the 2026-06-10
  note (last close 06-09) the SP500 forecast is **0.0 %** with 58–61 closes in
  the window, **3.4 %** with 62, **9–19 %** with 66–90. For Bitcoin on
  2026-08-31 it is 0.0 % at every window from 62 to 90 and 16 % at 100; `rv22`
  was 42 % and the 1000-day fit 35 %.
- **It reached the note.** Of 76 logged dates since 2026-05-29, **SP500
  published `0.0% ann-vol (60d pct 0)` on 7** and **Bitcoin on 10** (`06-03/04`,
  then `08-20` → `09-03`, eight of eleven dates). The SP500 line carries the
  VRP with it: `VIX 15.2% → VRP +15.2 (Normal)` — the "premium" is the whole
  VIX, labelled Normal, handed to the model as context. Six of the seven SP500
  zeros do **not** reproduce from a re-fetch at any window between 58 and 130
  closes, so the history CI's yfinance handed the pipeline on those mornings
  differed from today's — the fetch is not pinned and the live zero rate (9 % /
  13 %) sits above the backtest's at any wired window.
  `score_distributions.logged_har_sigma` skips those dates (no `har_gaussian`
  arm). The sizer would floor a zero σ at `min_sigma_annual = 0.02` and size
  the asset as a 2 %-vol instrument up to the 35 % cap; the 2026-08-31 book
  carried a Bitcoin σ of **15.6 %** against a trailing month of 42 %.

### The two secondary reads

- **Wiring read: defect, by the rule as written.** The 1000-day window is
  `skill` where the wired window is not on **SP500, Gold and Bitcoin** — three
  of four. The model is not the problem: fit on four years of squared daily
  returns, HAR beats the trailing month by 8–31 % of QLIKE at `h=5` and 19–54 %
  at `h=20` on those three, and is `parity` on WTI and IEF. It is the fetch
  period. The existing `test_vol_forecast.py` fits on 1,500 observations and
  beats "yesterday's r²" — it validated the function at a length it never sees
  live, against a rival nobody would use. 252 days is not enough either:
  `parity` at best, and still `degenerate` on Bitcoin (34 wild readings).
- **Horizon read: the IID scaling is right in variance and wrong in shape,
  which is what fat tails look like.** At 1000 days `mean(RV_h)/mean(σ̂²)` is
  0.86–0.97 at `h=5` and `h=20` (a 3–14 % over-forecast, inside the band). The
  Gaussian 50 % band **over**-covers at `h=5` (0.55–0.60; too many small days)
  and the 90 % band is inside its band on SP500/Gold/WTI (0.91–0.93) but not
  Bitcoin (0.897); at `h=20` the 20-day sum is Gaussian enough that SP500, Gold
  and WTI pass both bands and only Bitcoin fails (0.548 / 0.868). At the wired
  90-day window the variance ratio is **0.73–0.82** — the published number
  overstates variance by a quarter on average, because the wild readings
  dominate the mean — and SP500, WTI and Bitcoin are `biased at horizon` (Gold
  passes on the bands, at a ratio of 0.82).

### Nuances that are easy to forget

- (a) **The verdict benchmark was `rv22`, pre-named, not the best of four.**
  `ewma94` is the best trailing estimator on every asset; against it the
  1000-day HAR's `h=5` skill is +0.05 (SP500), −0.01 (Gold), −0.08 (WTI),
  +0.14 (Bitcoin). A rule that judged against the best rival would have called
  Gold `parity`. The `skill` verdicts are real but modest, and `ewma94` is the
  honest "no model" rival if HAR is ever dropped rather than re-windowed.
- (b) **The pre-registration described the note window as ≈ 62 closes; it is
  74–90 today and unpinned.** The wiring was read as "90 calendar days ≈ 62
  trading days"; yfinance returns 90 *bars* for the two 7-day and 5-day tickers
  alike and 74 for gold futures. Both 62 and 90 were in the pre-registered
  window set and both are `degenerate` on every instrument, so the verdict is
  unchanged; the headline is reported at 90 and the correction is recorded
  here rather than edited into the bar.
- (c) **This is the third input-window finding in the same shape.** [KB-003]:
  the regime model's credit feature was a 3-year FRED series and training
  truncated to 2y. [KB-028]: the conditional table's date range was set by the
  retired HMM's warm-ups, its credit input a rolling 3-year window. Here: a
  volatility model's fit window set by a `period="90d"` chosen for RSI and a
  50-day MA (`market_data.py`, "90d needed for RSI/50dMA/Z-score"). The
  history a component is fit on was, each time, whatever the fetch happened to
  return — never a number the method asked for.
- (d) **The Phase 22 `har_gaussian` comparator on the sealed record is built
  from the wired forecast.** It reads the logged `forecast_daily_vol`, so every
  sealed observation from 2026-09-07 compares the published quantiles against a
  Gaussian whose σ this entry has just measured as degenerate. Fixing the window
  changes that comparator from the fix date on — the same shape as [KB-028]'s
  conditioner change and, like it, to be named against the seal rather than
  slipped in. The exploratory backfill note in `roadmap.md` (WP-22.C, "a
  constant beat the model") stands: `har_gaussian`'s median is zero by
  construction and that read was about drift, not σ.
- (e) **Zero is published as a number, not as an absence.** `quant_context`
  prints `0.0% ann-vol (60d pct 0)` and computes `VRP = VIX − 0`; only the
  scorer treats `≤ 0` as "no forecast". A guard that drops a non-positive
  forecast from the note and the sizer is required whichever window is chosen —
  the clip in `har_rv_forecast` documents that the OLS can go negative, and
  nothing downstream honours it.
- (f) **Stride 1 and overlapping targets.** 4,900 daily readings at `h=20` are
  ~245 independent windows; the block bootstrap (21-day blocks) is what makes
  the intervals honest, and the wired-window intervals are wide for exactly
  that reason. None of them touch zero at 62 or 90 days.
- (g) **The prior was right about the direction and wrong about the size.** It
  said `parity` or `worse` for the wired window; the disqualifier fired first on
  every instrument, which the prior did not anticipate, and the skill number
  behind it is −0.5 to −3.0, not a few hundredths. It said `skill` at `h=1` for
  1000 days and `parity` at `h=5`; the 1000-day skill *grows* with horizon
  (SP500 +0.05 / +0.18 / +0.25 at 1 / 5 / 20) because the monthly regressor is
  doing the work and `rv22` cannot mean-revert.

**What it changes.**
- **WP-17.5 closes.** Both halves measured; Phase 17's numerical-layer audit is
  complete (regime cut → [KB-006]; conditional input rebuilt → [KB-028]; vol
  forecast → this entry).
- **The note's vol forecast has negative skill as wired and no consumer should
  read it as a measured σ** until the window is fixed. The fix — fetch ≥ 1000
  returns for `har_rv_forecast` in both callers, and drop a non-positive
  forecast rather than print it — changes published numbers, the sizer's σ and
  the sealed `har_gaussian` comparator, so it is **an open decision, not a
  silent fix → `todo.md` #17**, per the pre-registration. Not a version bump on
  its own (a fit-window correction, not a capability change); the seal note is
  the cost. *Landed 2026-09-13 → `resolved.md` #17:* separate 5y fetch
  (`market_data.fetch_vol_histories`), sizer lookback 130 → 1600 calendar days,
  and `vol_forecast.har_forecast_or_none` gates every live consumer at
  `HAR_MIN_RETURNS = 1000` and `forecast > 0`. First note on the new window
  2026-09-14; named against the seal in WP-22.C.
- **`test_vol_forecast.py`'s "outperforms naive" tests are not a skill claim
  about the live number** and should not be cited as one. The walk-forward
  read is `har_backtest.py`.
- **`what-we-believe.md`'s open-questions table** loses its "WP-17.5 — not
  started" row; the answer is here.

---
