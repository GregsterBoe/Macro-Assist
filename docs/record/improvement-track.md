# Macro-Assist — Project Improvement Track

A separate home for **improvement experiments on components that already exist** —
sharpening the quant layer, the fragility monitor, the prompt levers, etc. Kept
apart from the main roadmap on purpose:

| Doc | Holds |
|---|---|
| `roadmap.md` | The main plan — phases, work packages, the forward roadmap. |
| `knowledge-base.md` | **Measured findings** — falsifiable results with their caveats. |
| `todo.md` | **The single inbox** — every open decision and carried finding. |
| **`improvement-track.md`** (this) | **Improvement experiments** — the design, the staging, and the current status of attempts to make an existing piece better. |

This doc holds the *plan and status* of an improvement. It does **not** hold
results — see the convention immediately below.

---

## Working convention — improvement knowledge lives in the Knowledge Base

**Every improvement experiment that produces a measured result gets written up as
a `knowledge-base.md` (KB-###) entry** — the same discipline the fragility track
already follows (KB-001/002/012). Specifically:

- **A result is a KB entry, not a note here.** Whatever the input/component
  backtest measured — AUC, episode recall/precision, Brier, lead time — goes to
  the KB in the standard `what we tested → headline → the nuance that's easy to
  forget → what it changes` format, with caveats attached to the headline.
- **Negatives count.** A "this input has no skill" result is as valuable as a win
  and MUST be logged (KB-012, the absorption-ratio negative, is the template). It
  stops the next session from re-running a dead end.
- **This doc points at the KB, it doesn't duplicate it.** An IMP-# section keeps a
  one-line status and a link to the KB entry(ies) it produced; the numbers live in
  the KB.
- **Same gate as WP-16.A.** No new input reaches the live pipeline before it has
  passed the standalone backtest gate below and been logged.

---

## The improvement workflow — the "step in between"

The step between *"here's a promising new input"* and *"it's in the live note"* is
a **standalone input-testing gate**. It exists so we spend compute (and later, LLM
budget) only on inputs the data has already vouched for. Stages:

1. **Propose** an input or component (what it measures, why it should lead stress).
2. **Acquire the data** — prefer **free, zero-API-cost, and decoupled from the
   traded/predicted assets**. A fragility input is a *risk gauge*, so it does not
   have to be one of the assets we forecast; any free, well-suited cross-section is
   fair game.
3. **Standalone backtest gate** (the in-between step) — walk the candidate signal
   forward look-ahead-safe and score it against the forward-drawdown label with the
   **de-overlapped** metrics from `fragility_backtest.py`: non-overlapping AUC +
   episode recall/precision + lead time. Reuse the KB-002 bar:
   - **GO** ≈ non-overlap AUC > ~0.60 **and** episode recall/precision that beat
     the current baseline (`var_led_vix35`);
   - **NO-GO** ≈ AUC ≈ 0.50 or metrics no better than baseline → log the negative,
     stop.
4. **Shadow-wire** a GO input at **weight 0** (computed + logged, zero composite
   impact) — the `FRAGILITY_MODE` / weight-0 pattern already used for `acceleration`
   and `absorption`.
5. **Escalate weight** and re-run the composite ablation; keep only if the honest
   episode metrics improve.
6. **KB entry at every gate** (GO or NO-GO).

---

## IMP-1 — Expand fragility cross-sections + input-testing stage

**Status:** ✅ **COMPLETE (positive).** IMP-1.1–1.6 done → **[KB-013]** (absorption
reversed on a homogeneous cross-section) + **[KB-014]** (turbulence = complementary
recall instrument) + **[KB-015]** (the cross-section is ORTHOGONAL) + **[KB-016]**
(confirmed against the REAL `var_led_vix35`: OR-of-channels doubles crisis recall —
0.33→0.72 at 5d — a worthwhile precision *trade* for a tail-risk gauge). Full arc:
KB-012 negative → skill → orthogonal → confirmed live-baseline. **Adoption decided:**
an explicit **OR-of-channels recall MODE** (not a composite weight, not an equal blend)
— handed off to **IMP-4**. AR & turbulence stay shadow/diagnostic pending IMP-4.
Harness lives in `input_testing.py`. Motivating negative: [KB-012].

**Motivation.** [KB-012] showed the absorption ratio (and, by the same logic,
other cross-sectional co-movement measures — turbulence, dispersion, breadth) has
**no skill on the current ~5 heterogeneous assets** (equities, gold, oil, DXY,
BTC), because a tiny heterogeneous correlation matrix has no stable factor
structure. These measures need a **broad, homogeneous cross-section** (Kritzman
used dozens of US industry portfolios). Since a fragility input need not be one of
the traded assets, we can simply **add such a cross-section** as a dedicated
fragility data source.

### Data options (free, decoupled from the live assets)

- **Fama-French industry daily portfolios (recommended)** — Ken French Data
  Library, free, daily, **homogeneous by construction**, decades of history (a far
  deeper backtest than the 2008-start yfinance set). The 30- or 49-industry sets
  give a genuine cross-section for a clean top-eigenvector "market factor." Best
  choice for actually settling whether AR/turbulence work.
- **SPDR sector ETFs (simpler)** — XLK/XLF/XLE/… via the existing yfinance path,
  zero new plumbing, but coarser (~11 names) and shorter history (~1998+).
- (Later) a broader global-equity or single-country basket if we want a non-US
  cross-section.

*Recommendation:* start with **Fama-French 30/49** for the backtest depth and
homogeneity; keep sector ETFs as the live-pipeline feed if a daily fresh pull is
easier there.

### Candidate measures this unlocks (each goes through the gate)

- **Absorption ratio** — the proper retest [KB-012] deferred; the direct question
  is whether AR earns skill on a homogeneous cross-section.
- **Turbulence / Mahalanobis distance** (+ its "correlation surprise" split) —
  works on this cross-section too, and also on the existing heterogeneous set.
- **Cross-sectional dispersion / average pairwise correlation / breadth** — cheap
  companions computable from the same panel.

### Staged plan

- [x] **IMP-1.1** — cross-section fetch (`input_testing.fetch_ff_industries` /
  `fetch_ff_market`, cached under `~/.cache/macro-assist/ff`, offline after first
  pull, independent of the traded assets).
- [x] **IMP-1.2** — **generic input-testing harness** (`walk_forward_signal` +
  `evaluate_signal`): walk any candidate signal forward look-ahead-safe and print
  the de-overlapped gate metrics. The reusable "step in between" for every IMP-#.
- [x] **IMP-1.3** — retested the **absorption ratio** on FF 30 industries → **[KB-013]**:
  genuine skill (nov-AUC 0.62-0.68, best at cov 60-120), but modest and below the
  `var_led_vix35` baseline; still shadow weight 0.
- [x] **IMP-1.4** — **turbulence / Mahalanobis** through the same gate → **[KB-014]**:
  a *recall* instrument (recall ~0.44 at 5d, beating baseline) with poor precision
  (~0.19) and marginal/noisy AUC — the mirror image of AR's high-precision/low-recall.
  Not a standalone GO; the value is complementarity with AR.
- [x] **IMP-1.5** — **orthogonality/ensemble test** → **[KB-015]**: the cross-section IS
  orthogonal. A rank blend (B+AR+TURB) adds +0.06-0.10 nov-AUC and precision over a
  variance-led baseline; an **OR-of-channels** flag catches **31/48** 5d crises (recall
  0.65) vs the baseline's 13/48 (0.27) — *more than double* — with precision **held/improved**
  (0.20→0.22). That precision-holding-while-recall-doubles is the signature of channels
  catching DIFFERENT crises. GO on the ensemble concept; strong support for IMP-4 (OR
  recall mode). Caveat: baseline is variance-trend-only (no VIX arm) — see KB-015.
- [x] **IMP-1.6** — **confirmed against the real composite** → **[KB-016]**: OR-of-channels
  vs the actual `var_led_vix35` on traded assets (^GSPC label, 2008-2026) still roughly
  *doubles* crisis recall (0.33→0.72 at 5d, 0.32→0.64 at 10d), now at a precision cost
  (0.43→0.32) — a good trade for a tail-risk gauge, a bad one for a directional call. Key
  negative-within-the-positive: the equal-weight *blend* lifts AUC but *degrades* the
  validated top-decile flag, so adoption must be an OR **mode**, not a composite weight.
  Deliberately NOT auto-wired (needs live industry feed + PIT thresholds + regime-holdout CV).

**Hand-off:** the OR-of-channels recall mode, its channels (AR cov=120, turbulence cov=252
on a homogeneous panel), and the live operating point go to **IMP-4** (below). Remaining
plumbing before any live flag: (i) a daily sector/industry ETF panel to replace the FF
backtest feed, (ii) PIT-rolling top-decile thresholds, (iii) regime-holdout CV given n≈7 crises.

### Open design questions

- Fama-French 30 vs 49 industries (more granular = cleaner factor, but noisier tails)?
- How many top eigenvectors for AR on a ~30-name panel (Kritzman's ~1/5 rule → ~6)?
- Should the cross-section feed the live pipeline daily, or only the backtest for
  now (measure first, wire later)?

---

## Backlog (unstarted improvement ideas)

Parked directions from the fragility review, pending IMP-1:

- **IMP-2 — Credit / funding channel** ❌ **CLOSED negative → [KB-019]** (confirmed
  on two sources). Tested HY/credit stress as a 4th OR channel. Credit has genuine
  **standalone** skill (5d nov-AUC ~0.61-0.68) but is **REDUNDANT in the OR set**: at
  the live PIT operating point it adds **zero** recall and only costs precision — deep
  spreads co-move with equity vol/absorption in the tail, so it re-flags crises the
  trio already catches. Confirmed on both a Yahoo **HYG/IEF** proxy and the canonical
  Moody's **BAA10Y** spread (same +0 PIT recall, same +1 LOCO crises 2015-08/2010-05).
  Data note: ICE HY OAS (`BAMLH0A0HYM2`) is license-truncated to ~2023+ on free FRED —
  BAA10Y (daily, 1986+, unrevised) is the deep substitute, pulled via the FRED JSON API
  (`FRED_API_KEY`). No `fragility.py` change; `run_credit_gate` stays in the harness.
  Not parameter-swept ([KB-017]/[KB-018] discipline). **All "add-a-channel" bids
  (IMP-2/IMP-3) now exhausted → the lever is IMP-4.2/4.3 (operating point of the trio).**
- **IMP-3 — Downside asymmetry** ❌ **CLOSED negative → [KB-018].** Swapped downside
  semi-deviation and signed (down−up) asymmetry into the variance-trend pipeline (`sym`
  mode reproduces the live channel to the digit). Neither beats symmetric: a marginal
  +1-crisis FF recall bump paid for by lower AUC, and outright *worse* on the production
  ^GSPC (5d recall 0.318→0.227). Signed asymmetry decisively worse everywhere. Reason: a
  rising-variance regime is already downside-dominated, so symmetric std is the same trend
  measured on twice the data (lower variance). Variance-trend stays symmetric; no
  `fragility.py` change. Harness: `run_semivariance_gate`.
- **IMP-4 — Regime-holdout CV + OR-of-channels recall mode** ✅ **COMPLETE** ([KB-017]/[KB-020]/[KB-021]).
  - [x] **IMP-4.1 — CV spine** (`run_holdout_cv`) → **[KB-017]**: re-scored the
    OR-of-channels flag under PIT expanding-window thresholds and leave-one-crisis-out
    holdout. The KB-016 recall doubling **survives honest evaluation** — leakage from
    full-sample thresholds was *negligible* (in-sample-on-eval-window ≈ PIT), and OR
    recall still ~doubles composite-alone under LOCO. Both [KB-016] caveats (regime-holdout
    CV; PIT thresholds) are now closed. **This harness is now the adoption gate for any new
    channel** (IMP-2/3 must clear PIT+LOCO before entering the OR set).
  - [x] **IMP-4.2 — live daily sector/industry ETF panel** → **[KB-020] (GO).** Built
    `fetch_sector_etfs` (nine SPDR sectors, daily-fresh via yfinance, cached) and a
    feed-parity gate `run_etf_panel_gate`: on one shared window/anchor the ETF panel
    **reproduces the FF-fed OR operating point** — identical 5d PIT recall (0.647) at
    *higher* precision (0.318 vs 0.241), standalone channels match/beat FF, LOCO within ±1
    crisis (catching slightly different marginal events — ETF uniquely gets the 2022 onset).
    Coarseness (9 vs 30 names) didn't bite. Closes [KB-017] caveat (b). No `fragility.py`
    change. `python input_testing.py etf`.
  - [x] **IMP-4.3 — build the OR recall MODE** → **[KB-021] (DONE).** The OR flag (composite |
    absorption | turbulence, each vs its own PIT top decile) is now a distinct, live-computable
    flag — `fragility_or.py` (engine) + a `FRAGILITY_OR_MODE` ladder in `quant_context.py`
    (off/log/show/active, default **off**, mirroring FRAGILITY_MODE's shadow pattern). Adopted
    as a MODE, NOT a composite weight ([KB-016]). Fed off the live ETF panel ([KB-020]). The
    live code path reproduces the operating point (self-check 5d OR recall 0.588 vs composite
    0.118 — ~5×); the harness gate still reproduces [KB-020] byte-for-byte after two library
    graduations (`turbulence_signal` → `fragility.py`, `fetch_sector_etfs` → `fragility_backtest.py`).
    Today's live reading: **quiet** (no channel in its top decile). Output-neutral until the mode
    is escalated. `python fragility_or.py`.
  - Validated by [KB-015]/[KB-016]/[KB-017]/[KB-020]/[KB-021]. Receives IMP-1's channels (AR cov=120,
    turbulence cov=252 on a homogeneous panel). **IMP-4 CLOSED.**

---

## Fragility monitor — the 2026-09-13 review

**Where this came from.** With every "add a channel" bid exhausted (IMP-2, IMP-3)
and IMP-4 live, an external review proposed upgrading the OR aggregation (tree
models, an HMM, rolling thresholds) and adding ΔCoVaR, SRISK, eigenvector
centrality, critical slowing down and Shannon entropy. Checked against the record
before any of it was scheduled — most of it had already been measured here:

| Proposed | Record | Outcome |
|---|---|---|
| Tree models learning conditional thresholds | 12–28 crisis episodes, ~7 macro events; [KB-017]/[KB-018]/[KB-019] refused even parameter sweeps on this n. The worked example (AND-gate on composite ≥ p80) *lowers* recall | Reduced to its honest floor: a 3-parameter logistic under LOCO (IMP-6.3). **Run: it could not beat OR** — loses 4 crises at 10d under LOCO at the same alarm budget ([KB-031]). **Closed**, trees with it |
| HMM regime-switching | Tested four times and retired: [KB-004] no skill, [KB-005] sequence inference reaches 0.55–0.65, [KB-006] loses to a 4-feature linear rule and adds nothing within stress terciles | **Closed.** Re-proposing it argues against KB-006 |
| Rolling / dynamic thresholds | The OR flag already uses expanding-PIT deciles; [KB-017] showed static cuts leaked negligibly. A trailing-252 percentile fires at a fixed rate by construction and discards level | Half done. The remaining half — the composite *label* cut is static — is IMP-5.3 |
| ΔCoVaR | Needs an institution cross-section and quantile regression; the published measure is contemporaneous and its forward form needs quarterly balance-sheet data. [KB-019]: everything financial co-moves in a ≥5% equity drawdown | Not planned |
| SRISK | Slow capital-shortfall measure for financial-system crises; needs leverage data; no free daily feed; horizon mismatch with a 5/10-day label | Not planned |
| Eigenvector centrality | The absorption ratio *is* the dominant-eigenvalue read, live since IMP-4; 9 sector ETFs carry ~2 meaningful eigenvectors | Ran in IMP-7 as the participation ratio of the top eigenvector: standalone AUC 0.72, but under its own expanding PIT p90 it fires on **zero** readings post-2013 (GFC-anchored, like the composite in [KB-030]). **Closed**, redundant ([KB-032]) |
| Critical slowing down (lag-1 AR) | **Falsified here**: AUC 0.44/0.50 [KB-001], weight 0 since [KB-002], "exactly as the literature predicted for equities". The "coupled with variance expansion" half *is* the live leading component | **Closed** |
| Shannon entropy | On returns, entropy ≈ ½·log(2πeσ²): variance in disguise, and an entropy *drop* means falling variance — the opposite of [KB-001]. Permutation/sample entropy measures ordering = predictability = the autocorrelation negative again | Not planned; reasoning recorded so it is not re-proposed |

Two framing points, for the next time this comes up: the OR does **not** weight
channels equally — each fires against its *own* PIT top-decile, so severity is
per-channel calibrated; and weighting *was* tested — the rank blend lifted AUC and
degraded the flag [KB-016], which is why OR is a mode and not a weight.

What the review did do was send us back to the live record, which held a finding
none of the proposals would have found — IMP-5.

## IMP-5 — Composite degradation: the calibrated cut only applies to the calibrated composite

**Status:** ✅ **CLOSED 2026-09-18** (reopened 2026-09-18 for IMP-5.4).
IMP-5.1–5.2 shipped → [KB-029]; IMP-5.3 **negative** → [KB-030] — the static
cut stays; IMP-5.4 shipped → [KB-034] — the fallback's own failure is now
visible and a degraded streak is red.

**Finding.** The composite's first-ever live Elevated (2026-08-13 → 08-19, five
days, 59–62 vs the 56.5 cut) was a data-feed artifact: yfinance's `^VIX3M`
stopped updating on 2026-07-17, the live `vix_term` froze, then vanished for ten
trading days, and the weights renormalised onto `variance_trend` at ~0.90. With
`vix_term` present the same days read ~36 → Normal; nothing followed (−2.7% max).
Detail and the counterfactual in [KB-029].

- [x] **IMP-5.1 — Stale means missing; degraded means unlabelled.** A VIX3M leg
  more than 5 VIX observations behind is treated as absent. A composite missing a
  member of `_LABEL_REQUIRES` (`variance_trend`, `vix_term`) reports its number
  but carries the label **`Unavailable`** and a `degraded` list; the OR engine
  masks such days out of its `comp` channel. Surfaced in the JSONL, the Action log
  (WARN) and the note block. The 2008–2026 walk has 0 degraded days — KB-002
  stands.
- [x] **IMP-5.2 — Issuer fallback for the vol legs.** `freshen_vol_indices` splices
  CBOE's own `VIX_History.csv` / `VIX3M_History.csv` under a missing or stale leg
  in both the live and the backtest fetch; a no-op when yfinance is fresh.
- [x] **IMP-5.3 — Align the composite label cut to expanding-PIT → NO, [KB-030].**
  The OR flag's thresholds are the 90th percentile of each channel's *own prior*
  readings; the composite's Elevated cut is a static 56.5 fitted over 2008–2026.
  **Gate (written before the run):** re-walk 2008–2026 with the PIT cut (warm-up
  252); episode recall must reproduce the static cut within ±1 crisis per
  horizon on the same window, as [KB-017] found for the OR flag.
  **Result: −2 crises at both horizons** (7/37 vs 9/37 at 5d; 11/50 vs 13/50 at
  10d), nothing gained. The composite's warm-up year is the GFC, so the
  expanding cut starts near 92 and does not reach 56.5 until ~2017; June 2010 is
  lost outright, Dec 2018 / Mar 2022 by a hair. The static cut stays; the two
  flags in the note are on two methods **for a measured reason**. Harness:
  `python fragility_backtest.py pit-cut`.
- [x] **IMP-5.4 — A fallback is not a fix unless its own failure is visible →
  [KB-034].** `vix_term` went missing again on 2026-09-16 *with IMP-5.2's CBOE
  fallback in place* and published three `Unavailable` readings; every check was
  green and a human caught it on day three. IMP-5.1 held perfectly — no false
  Elevated, the OR channel masked itself — but nothing recorded *which* feed had
  died (`fetch_cboe_index` returned `None` for a 403, an outage and a renamed
  column alike; `vix_term_backwardation` returned `None` for absent, stale and
  non-overlapping alike), and nothing escalated. Shipped: `vix_term_reason` +
  `degraded_detail`; `cboe_error` + one retry; `freshen_vol_indices(report=...)`
  naming each leg's source, staleness, last date and error; both in the JSONL and
  the WARN line; and `feed_audit.py` as the pipeline's own **`feed_gate` job** —
  after the note is written and published — exiting 1 once the live degraded
  streak passes 2. A job, not a step of `daily`: a failing step would have
  skipped Monday's scoring and rebalance, which gate on
  `daily.result == 'success'`. Replayed on 09-14 → 09-18 it is red on the 18th. Stage 1 also gained
  the vol-leg check it never had (it stayed green through all three days), and
  `pipeline.yml` gained **`mode: validate`** — plan + stage 1 with strict vol
  legs, writing nothing — so a day can be re-checked without an LLM call or a
  rewritten note. **Cause found the same day → [KB-034] addendum:** yfinance's
  `^VIX3M` returns nothing at ~06:04 UTC and current data at 16:24 UTC, three
  mornings running — intermittent, not the [KB-029] upstream stop — and the CBOE
  fallback has never once succeeded in production (it short-circuits on a fresh
  leg, so 09-16 was its first live call). `todo.md` #26 is
  reframed around that cause: retry the primary, let the 10:47 UTC catch-up call
  re-check the feeds (it no-ops on an existing note today), or move the run —
  all cheaper than a new feed, and all blocked on `feed_audit.py --probe-cboe`
  coming back green from CI, since until it does the vol legs have no working
  fallback at all.

## IMP-6 — Precision at held recall: the aggregator question, asked honestly

**Status:** ✅ **CLOSED 2026-09-13 — negative → [KB-031].** All three variants
disqualified on `recall_lost`; none raised precision at either horizon. The
aggregation stays a plain OR; the tree-model / learned-weighting question is
closed with the logistic. Harness `.macro-assist/aggregator_testing.py`
(`python aggregator_testing.py`). Bar written 2026-09-13 before any variant
ran, and kept as written. Caveat inherited from [KB-030] (the composite's PIT
percentile is GFC-anchored in 2009–2016) applied to variant 3 and did not
decide anything — its losses are 2018–2026 folds.

**Question.** The OR mode's operating point is recall ~0.6–0.8 / precision ~0.32
at 5d ([KB-017]/[KB-021]) — roughly two alarms in three are false. Can precision
rise *without* paying recall, using only the existing trio? All "add a channel"
routes are closed; this is the operating point of what exists.

**Three pre-registered variants, one run, one KB entry (positive or negative):**

1. **Persistence** — the OR flag must be set on **two consecutive readings** (the
   anchor grid is strided, so "consecutive" means consecutive readings, not days).
   The classic false-positive filter. Its cost is lead time — [KB-002]'s median
   Elevated→trough lead is 4 days at 5d — so lead time is measured and is a
   disqualifier, not a footnote.
2. **k-of-n / severity tiers** — `watch` = any channel ≥ its PIT p90 (today's
   flag, unchanged); `alert` = **two of three ≥ p90, or any one ≥ p97**. A graded
   output rather than a sharper binary; `alert` is what gets scored here.
3. **Fitted logistic** on the three channels' PIT percentiles, **leave-one-crisis-
   out**, threshold chosen on training folds only. The honest floor for "learn the
   weighting": three parameters, fitted out-of-sample. If it cannot beat OR, the
   tree-model question is closed with it.

**The bar — under `run_holdout_cv` (PIT + LOCO) on the [KB-021] live window
(`comp ∩ ETF`), both horizons, fixed config, no sweeps:**

- **Disqualifiers, evaluated first, each its own verdict:** `underpowered` —
  fewer than 10 alarms on the PIT window; `too_late` — median lead to trough
  below 2 days at 5d; `recall_lost` — more than 1 crisis lost vs the 3-channel OR
  at either horizon under LOCO.
- **Pass** = PIT precision **+0.05 absolute or more at both horizons** with recall
  within 1 crisis of OR, **or** LOCO recall **+2 crises or more** at PIT precision
  within −0.02.
- Anything between is `no_edge` and is logged as such. A variant that passes goes
  to the shadow ladder as a *separate* flag, not a replacement — the validated OR
  operating point keeps accumulating its live record regardless.

**Prior, stated so it can be checked later:** persistence buys precision at a
lead-time cost and probably fails `too_late` at 5d; tiers reshuffle the same
alarms; the logistic reproduces OR. Honest expectation is one `no_edge` and two
disqualifications — which would close the aggregator question and is worth having
in the KB for exactly that reason.

**Result (2026-09-13, [KB-031]):** three `recall_lost`, zero `no_edge`, and —
against the prior — **no variant bought precision anywhere** (5d: persist
0.235, tiers 0.235, logit 0.316 vs OR 0.333 / 0.429 on their windows).
Mechanism: on the strided grid a 5-day label episode is one reading wide in 15
of 17 cases, and the OR's catch is that single first-channel p90 crossing;
persistence shifts every alarm a reading later past it, tiers' severity comes
at the trough, the logistic splits the same budget into more alarms.
`too_late` never fired because it measured the median lead of *surviving* true
positives — the next lead-time bar is written as crises-caught-with-lead. A
hindsight observation (10 of 12 false 5d alarms are turbulence-only) was
`todo.md` #15, declined 2026-09-14 → `resolved.md`; not a change.

## IMP-7 — The companion measures IMP-1 listed and never ran

**Status:** ✅ **CLOSED 2026-09-13 — negative → [KB-032].** All four have
standalone skill; DISP `precision_lost`, BREADTH and EIGC `redundant`, CORR
`admit` by the letter of the bar — on one post-crash aftershock crisis, via two
readings in 664 where the trio was silent. Not wired; the deployment call is
`resolved.md` #16 (closed 2026-09-14). Bar written 2026-09-13 before any companion was computed, kept
as written. Harness `.macro-assist/companion_testing.py`.

IMP-1's candidate list named cross-sectional **dispersion**, **average pairwise
correlation** and **breadth** as "cheap companions computable from the same
panel". They were never run — the arc went AR → turbulence → OR and stopped.
**Eigenvector loading concentration** (from the review) rides along as a fourth.

**The four measures, defined here so the run cannot choose them.** All on the
nine-sector SPDR panel, walked on the [KB-021] live anchor grid (the same strided
`comp ∩ ETF` dates the AR and turbulence channels sit on), from the panel's
history up to the anchor date only. Each has a **fixed sign** — higher = more
fragile — chosen from the hypothesis that motivated it, not from the data:

1. **DISP** — cross-sectional dispersion: the standard deviation across the nine
   sectors' daily log returns, averaged over the trailing **20** days.
   Hypothesis: sector returns fan out before and into stress.
2. **CORR** — average pairwise correlation: the mean of the upper triangle of
   the **60**-day correlation matrix of daily log returns (signed, not absolute —
   sectors are positively correlated; `correlation_tightening`'s window). The
   *level* form of what the absorption ratio reads as a standardised shift.
3. **BREADTH** — narrowing participation: the fraction of the nine sectors
   closing **below** their own **50**-day simple moving average, averaged over
   the trailing 20 days (so nine names do not leave a ten-valued signal).
   Hypothesis: the index is carried by fewer sectors before it falls.
4. **EIGC** — eigenvector loading concentration: the participation ratio
   `1 / Σ vᵢ⁴` of the unit-norm top eigenvector of the **120**-day correlation
   matrix (the AR window), i.e. the effective number of sectors the dominant
   factor loads on (range 1–9). Hypothesis: a systemic factor that loads on
   everything is the one a shock propagates through. Expected redundant with AR.

A 5d non-overlap AUC clearly **below 0.5** means the sign hypothesis was wrong;
that is logged as the negative it is. Flipping the sign and re-running would be a
second look at the same data and is not done.

**The bar — per companion, evaluated independently, fixed config, no sweeps:**

1. **Standalone gate** (`evaluate_signal` on the anchor-grid readings, the
   [KB-002] bar as IMP-1/IMP-2 applied it): `no_standalone_skill` if the **5d
   non-overlap AUC ≤ 0.60**. The 10d AUC and the top-decile recall/precision are
   reported, not gated. A companion failing here is still run through step 2 so
   the KB carries the number, but cannot be admitted.
2. **OR-admission gate** (the [KB-017] protocol on the [KB-021] live window):
   the trio OR versus the trio-plus-companion OR, each channel against its own
   expanding-PIT p90 (warm-up 252), scored on the **shared** evaluable window
   (a companion with fewer finite readings shrinks the window for both rows —
   the IMP-5.3 discipline). Disqualifiers first, each its own verdict:
   `underpowered` — fewer than 10 drawdown episodes at 5d on the shared PIT
   window; `precision_lost` — 4-channel PIT precision below the 3-channel's by
   more than 0.02 at either horizon. **Admit** = PIT recall **up by at least one
   crisis at both horizons** at that held precision, **and** LOCO recall not
   below the trio's at either horizon. Anything else is `redundant` — the
   [KB-019] outcome, logged as such.

An admitted companion goes to the shadow ladder as a fourth channel of a
*separate* flag, not into the live OR — the [KB-021] operating point keeps its
record regardless.

**Prior, stated so it can be checked later:** CORR and EIGC are the absorption
ratio's level and loading views and re-flag its crises; DISP is turbulence's
cross-sectional cousin; BREADTH is a trend measure that fires during the fall,
not before it. Honest expectation: zero admits, one or two with standalone skill
(as credit had, [KB-019]), all `redundant`. Harness
`.macro-assist/companion_testing.py` (`python companion_testing.py`).

**Result (2026-09-13, [KB-032]):** four standalone passes (5d nov-AUC 0.70–0.79;
DISP 0.945 at 10d), zero crises gained *with lead*. CORR met the admit clause —
+1 crisis at both horizons at the same 18 alarms — but the crisis is the
2020-06-08 aftershock of the COVID alarm, caught by extending an alarm already
sounding by two readings; EIGC never reaches its GFC-anchored PIT p90 at all.
The bar had no lead clause, the hole [KB-031] nuance (a) had already named; the
correction is written into the next OR-admission bar (a gained crisis counts
only if the trio's alarm was not already active), not into this verdict.
Wiring the admitted flag was judged uninformative (it would agree with the live
OR on 662 of 664 readings) and is `resolved.md` #16, not done silently. **The
candidate list IMP-1 opened is exhausted; the fragility track is forward
observation only.**

---

## IMP-8 — The note's main model: Opus 4.8 → a current Sonnet

**Status:** ❌ **closed unrun 2026-10-01 — moot.** The owner turned the model-written
analysis off ([ADR-0024](../decisions/ADR-0024-the-note-makes-no-llm-call.md), v2.2), so no model writes the note and there is no model to
choose. Nothing was run, so there is no KB entry. The harness and its bar stay
(soft-kill), and apply as written if `NOTE_ANALYSIS=llm` is ever switched back on.
Harness `.macro-assist/model_compare.py`, run by `model_compare.yml` (dispatch-only).

**Why.** The main analysis call (MA-1, structured `tool_use` → `AnalysisOutput`)
and its review (MA-2) run on `claude-opus-4-8`, selected by the repo variable
`MACRO_PROFILE=loosened` — the model half of a WP-16 A/B that closed with the
cut. The reference docs say Sonnet ([Analysis pipeline](../reference/analysis-pipeline.md),
[Architecture](../reference/architecture.md)); the notes' frontmatter says
`claude-opus-4-8`. Since v1.6 the call writes description, not a forecast: the
dashboard, the notes, the key risks, one driver paragraph and one dispersion
band per asset. A current Sonnet is newer than Opus 4.8 and costs 40% of it per
token. **The money is small** — the main call is about $0.10–0.15 a day on Opus
4.8, so the saving is roughly $2 a month; the reasons are a current model and a
record that says what runs.

**The test.** The last ten saved payloads (`results/llm_payload_preview/`, the
verbatim user message of each day) through the production MA-1 and MA-2
functions, with today's system prompt, once per model: `claude-opus-4-8`
(production, the reference), `claude-sonnet-5` and `claude-sonnet-5-5` (a model
the API does not recognise is skipped and the record says so). Same inputs, so
every difference is the model.

**The bar — written 2026-09-28, before any candidate's output was seen.** A
candidate replaces Opus 4.8 only if, over the ten days, all of:

1. **Valid:** no day `failed` (the answer validated, retry allowed — a failure
   is a day production would have fallen back to free text), and no more
   `after_retry` days than Opus 4.8 plus one.
2. **No call language:** no more uses of the wording the prompt forbids since
   v1.6 than Opus 4.8, and every use read: a real call in the prose — a
   direction or a likelihood stated as the note's view — fails the candidate
   outright, whatever Opus 4.8's count.
3. **No invented figures:** the *numbers not in payload* lists are read, day by
   day. Most entries are figures the model derived (a spread, a change, a unit
   conversion); a figure that is neither in the payload nor derivable from it is
   invented, and a candidate with more invented figures than Opus 4.8 fails.
4. **As broad:** it names, on average, at least 80% as many distinct inputs per
   note as Opus 4.8 (`citation_screen`'s alias map) — a cheaper model that
   quietly reads less of the payload is worse even if nothing it says is wrong.
5. **The owner's read:** the owner reads the three newest days side by side in
   the report and does not find the candidate's note worse to use. This is the
   owner's veto, and it comes last.

If two candidates pass, the cheaper one; at equal price, the newer. **If none
passes, Opus 4.8 stays** and the negative is logged. Either way the result goes
to the Knowledge Base, and the reference docs are corrected to name the model
that runs — they are wrong today regardless of the outcome.

**What it does not test.** The free-text fallback path (it runs only when MA-1
fails twice) and the Haiku sub-agents (MA-3a/b/c, unchanged). The note is
unscored since the cut, so there is no outcome metric: the bar is about
validity, adherence to the prompt, and grounding, which is what the call is for
now.

**The switch, if it passes.** Set the repo variable `MACRO_MODEL` to the
candidate (`macro_daily.yml` passes it; `pipeline_config.run_config` lets it
override the profile). No code change; unsetting it reverts. Every note's
frontmatter records the model, so the change is visible in the record from the
first note. No version bump: the note's structure and contract do not change
(convention 9).

## IMP-9 — An outside input as a filter on the OR flag: which data could carry it

**Status:** ❌ **closed 2026-10-01: both candidates the owner chose
(`resolved.md` #36) fail as filters, on both windows, at `recall_lost`.**
- **9.A, CBOE SKEW → [KB-035].** Anti-selective: it kept 2 of 10 live crises,
  at precision 0.10, below random timing.
- **9.C, the commercial-paper spread → [KB-036].** Not selective: it cut real
  and false alarms alike, losing 1 of 10 live and 4 of 17 long crises. Its
  live precision of 0.353 sat on the shifted filters' 90th percentile.
  - It was built from ALFRED first releases, because the CP leg is revised on
    1.6% of days.
  - Today's values would have changed 2 decisions per window and no verdict.

#36 left the VIX's own volatility unrun, so nothing in step 1's table
remains. Step 3 (a risk-rule member) is never reached. Step 1 (feasibility)
2026-10-01. Step 1 read no
candidate's values: coverage was checked by listing dates only (first, last,
row count, gaps).

**Why.** Goal 2 ([What is worth doing §2](../concepts/what-is-worth-doing.md#2-the-standing-goals))
asks for OR-flag precision of 0.4 at 5d, with recall no worse than today;
today's is about 0.3 ([KB-017], [KB-021]). H-009's explore look (2026-10-01,
[hypotheses.md](hypotheses.md#h-009)) showed what that precision costs a
real decision. 111 of the rule's 154 hold windows were false alarms, and
they carried nearly all of its return cost. The goal ranks above goal 3,
and a flag with fewer false alarms is what a later risk rule would need.

**What is already closed, so this does not repeat it.**
- *Adding a channel* (OR admission): credit [KB-019], downside variance
  [KB-018], and four panel companions [KB-032]. Each was redundant in the OR set.
- *Recombining the trio*: persistence, two-of-three tiers and a logistic
  [KB-031]. Each lost crises without buying precision.

**What is new here.** An input from **outside** the equity panel and the VIX
term structure, used as a **filter**: a firing of the trio stands only when
the outside input agrees. As far as the record shows, this role has not been
tested. The KB-019 / KB-032 gates asked whether an input *adds* crises.
A filter can only remove firings. So its way to fail is losing a crisis, and
"no crisis lost" is the disqualifier it has to clear first.

**Honest prior: low.** Every route that changed the flag's parts has failed so far,
and on 17–21 crises at 5d in the live window ([KB-031] caveat e), a move from
0.3 to 0.4 is hard to tell from luck. This is why candidates with long
histories rank first: they can also be checked on the panel-only flag (AR OR
TURB on the Fama-French industries, the H-009 flag) over far more crises.

### Step 1 — the candidates, checked 2026-10-01

Eligibility follows [ADR-0014](../decisions/ADR-0014-point-in-time-without-alfred.md):
only never-revised inputs may enter a backtest. The budget is the €20 a
month in [What is worth doing](../concepts/what-is-worth-doing.md).

| Candidate | What it measures | History (dates only, checked) | Point in time | Cost / licence | Overlap with what is in | Step 2? |
|---|---|---|---|---|---|---|
| **A. CBOE SKEW** | Price of far out-of-the-money S&P puts: the market's fear of a tail, separate from the vol level | CBOE CSV `SKEW_History.csv`: 1990-01-02 → 2026-09-30, 9,238 rows, one gap over 7 days (13 days) | Market-observed, never revised: eligible like `VIXCLS` | Free. Same CBOE endpoint the composite's fallback uses (`fragility_panel._CBOE_URL`). CBOE's website terms to be read before any live use | Low by construction: it is the shape of the option smile, not its level | **Yes, first** |
| **B. Volatility of the VIX** | How unstable the fear gauge itself is | VVIX: 2006-03-06 →, 5,115 rows, six gaps over 7 days (longest 21). The long form is the 21-day realized vol of the VIX, from CBOE VIX 1990-01-02 → (9,284 rows, no gap over 7 days) | Both market-observed: eligible | Free | **High.** The composite already reads the VIX term structure and the S&P variance trend. VVIX starts too late to add crises beyond the 2008+ window | Only the realized long form, after A |
| **C. Funding stress: commercial paper over T-bills** | What banks pay to borrow for 90 days, over the risk-free rate | FRED `DCPF3M` (90-day AA financial CP) − `DTB3`: daily, 1997-01-02 → 2026-09-29. `CPFF` (CP − fed funds) same start | Rates, but a Fed compilation, not a quote. **Checked 2026-10-01: `DCPF3M` revised on 1.6% of days (one 2018 batch), `DTB3` never.** Usable from first releases (§9.C) | Free (FRED key in hand) | **Moderate to high.** [KB-019] found credit redundant, and funding stress moves with credit in a crash | After A, behind the revision check |
| TED spread | The classic funding gauge | FRED `TEDRATE` 1986 → **2022-01-21, discontinued** (LIBOR) | — | — | — | **No:** cannot run live |
| NFCI and its risk / leverage subindices; St. Louis `STLFSI4` | Composite financial-conditions indices | Weekly from 1971 / 1993 | **Re-estimated every week** (798 / 204 vintages, first vintage 2011 / 2022) | Free | Includes credit and vol | **No:** ADR-0014 excludes it |
| VXO | S&P 100 vol, from 1986 | FRED `VXOCLS` **ends 2021-09-23**; the CBOE file refuses (403) | — | — | Vol level | **No:** discontinued |
| Option-surface tail measures (risk-neutral skew, tail-loss prices) | The full options tail | Academic and commercial (OptionMetrics) | — | **Paid, far above €20 a month** | — | **No** |
| Short-dated vol (VIX9D, VIX1D) | Very near-term fear | 2011 → / 2022 → | Eligible | Free | Vol level | **No:** too short |
| Treasury market noise (Hu–Pan–Wang) | Liquidity in the bond market | Research dataset, not a maintained daily feed | — | Free, unmaintained | — | **No:** cannot run live |

### Step 2 — what would run, once a candidate is chosen (not started)

One candidate at a time, A first. For each, a bar is written here before its
values are read:

1. **Role.** The filter: a trio firing stands only if the candidate is at or
   above one cut of its own point-in-time history. The cut is fixed in the
   bar, not swept. As a secondary read, OR admission under the [KB-019]
   protocol (in-sample → PIT → LOCO), so the record says both.
2. **Disqualifier first:** any crisis the trio catches with lead that the
   filtered flag loses under LOCO. Then the goal-2 bar: precision ≥ 0.40 at
   5d.
3. **Windows.** The live trio, 2008-07 →, on the KB-021 grid. Then, for A,
   B-long and C, the panel-only flag over the candidate's whole history. Its
   crisis count is taken from the label before the candidate is read.
4. **Scored the de-overlapped way:** episodes, not daily readings.
5. **A KB entry either way.** If one passes, its next test is a decision: a
   new risk-rule member using the filtered flag, read against `static_matched`
   and `vol_matched` ([ADR-0023](../decisions/ADR-0023-a-risk-rule-is-read-on-drawdown-against-a-matched-rival.md)).

### 9.A — CBOE SKEW as a filter: the bar, written 2026-10-01 before any SKEW value was read

Harness `.macro-assist/filter_testing.py`. Constants are fixed here and not
swept.

**The input.** `x_t` is the 5-trading-day mean of CBOE SKEW ending the CBOE
day **before** *t*, minus the median of the 252 SKEW closes ending on that
same day.
- *One day's lag:* [ADR-0014]'s shift. The note runs before the US open, so
  yesterday's close is what is known live.
- *5-day mean:* turbulence's smoothing, so one noisy print does not decide.
- *Measured against the trailing year:* SKEW's level has drifted up over
  decades, so a percentile of its whole history would read "high" in every
  recent year. This is a property of the published series, known before
  this run.
- *Stale data fails open:* with no SKEW print in the 10 calendar days before
  *t*, the filter lets a firing stand. A missing feed never silences a
  warning ([KB-029]'s lesson).
- *Too little history drops the reading:* with fewer than 252 + 5 prior
  closes, the reading is out of the window. Both rows are scored on the same
  readings.

**The filtered flag.** OR(trio) ∧ (`x_t` ≥ 0): a warning stands only when tail
fear is at or above its own past-year median.

**Windows. Both must pass.**
1. **Live.** The KB-021 trio (composite ∨ AR ∨ TURB) on its grid, 2008-07 →,
   labelled on ^GSPC. This is the flag goal 2 names.
2. **Long.** The panel-only flag (AR ∨ TURB, the Fama-French 30 industries,
   `fragility_or`'s constants: H-009's flag), labelled on the FF market. It
   runs from where both it and SKEW are warmed up (about 1991) to the FF
   data's end. It exists for power: more crises than the live window's 17–21.

**Scored** with `fragility_backtest`'s de-overlapped episode metrics, against
the unfiltered flag on the same readings. The protocols are PIT and LOCO,
both as in IMP-6. In LOCO the trio's cuts are fit outside the held-out crisis.
The filter fits nothing: it is trailing by construction. **Decisive horizon:
5d** (goal 2). 10d is reported.

**The verdict, per window, in this order. Each disqualifier returns at once:**
1. `underpowered`: fewer than 10 alarm episodes for the filtered flag at
   5d (PIT).
2. `too_late`: median lead to trough at 5d (PIT true positives) below 2
   days, or undefined.
3. `recall_lost`: **any** crisis lost against the unfiltered flag at 5d,
   under PIT or under LOCO. Goal 2 says "recall no worse than today".
4. `no_edge`: PIT precision at 5d below the unfiltered flag's + 0.05.
   On the live window it must also reach **0.40**, goal 2's target.
5. `luck`: the precision does not beat the 90th percentile of 200 shifted
   filters. Each shifts the filter's pass / block series against the grid by
   a random 52 readings (about a year) up to n − 52, seed fixed. Each keeps
   the filter's rate and runs and breaks its timing.
6. `pass`.

**9.A passes only if both windows read `pass`.** Either way, the result goes
to the KB.

**Reported, not read.**
- SKEW as a fourth OR channel instead of a filter (`x_t` at its own PIT p90,
  the [KB-019] admission protocol), so the record has both roles.
- Which crises and which alarms the filter removed, and the share of firings
  it blocks.

**Prior, the proposer's, written before the run.** `recall_lost` on at least
one window. A filter that blocks about half the firings has to lose no crisis
among about 20 live and more long ones, and SKEW's record as a crash
predictor is weak in the published literature.

### 9.C — The commercial-paper spread as a filter: the bar, written 2026-10-01 before any spread value was read

The second of the owner's two candidates (`resolved.md` #36), run after 9.A
failed ([KB-035]). Same harness, `.macro-assist/filter_testing.py
--candidate cp`. Constants are fixed here and not swept. **Everything not
stated below is 9.A's bar, unchanged**: the windows, the scoring, the
verdict's order and its constants. A second candidate read on the same two
windows is a second look. The bar is kept identical so the two read alike,
and 9.C's KB entry says it was the second.

**The revision check, done first (2026-10-01).** It compared each
observation's first-published value (ALFRED, `output_type=4`) with today's.
Only counts, sizes and publication dates were printed, never a level.
- `DTB3` (3-month Treasury bill): archive from 2005-06-28. **0 of 5,316
  observations ever revised.** Before the archive, its first vintage differs
  from today's on 35 of 3,873 days, by at most 3 bp.
- `DCPF3M` (90-day AA financial commercial paper): archive from 2006-03-22.
  **69 of 4,435 observations revised (1.6%), at most 28 bp, 20 by 5 bp or
  more.** 62 of them came in one batch in August 2018, restating 2017–2018
  values. The other 7 were corrections within 90 days (2013, 2016). Before
  the archive, its first vintage differs from today's on 2 of 2,307 days, by
  at most 2 bp.
- **Publication lag.** Each observation's first appearance is 1 business day
  after its date on 63–65% of days. It is within 2 business days on 95–97%,
  and within 3 on 98–99.7%.

So `DCPF3M` is **revised**, and [ADR-0014] excludes it as published today.
That ADR also keeps ALFRED reconstruction "where the call volume is bounded".
Here it is about a dozen calls for the whole archive. **The input is
therefore built from first releases, not today's values.**

**The input.**
- *The spread*: `DCPF3M − DTB3` on each day both legs have an observation.
- *Values*: each leg's **first-published** value. Before the archive (CP
  before 2006-03-22, bills before 2005-06-28), the archive's first vintage is
  used. Those nine years cannot be checked for revisions made at the time.
  The evidence above (one batch in twenty years, old values unchanged since
  2006) is why they are used rather than dropped, and the caveat goes with
  the result.
- *When it is readable*: an observation is readable on reading date *t* only
  if it was published **strictly before** *t*. The note runs before the US
  open, and the Fed's release lands during the US day. Publication is the
  later of the two legs' first-release dates. Before the archive it is taken
  as 3 business days after the observation, beyond the lag of 98–99.7% of
  archived days. An observation counts as readable only once every earlier
  one is.
- *x_t*: the mean of the 5 latest readable spread observations, minus the
  median of the 252 ending on the same observation. This is 9.A's form, for
  9.A's reasons: smoothing one noisy print, and a level measured against its
  own trailing year.
- *Stale data fails open*: if the latest readable observation is more than
  10 calendar days before *t*, the firing stands.
- *Too little history drops the reading*: under 252 + 5 readable
  observations.

**The filtered flag.** OR(trio) ∧ (`x_t` ≥ 0): a warning stands only when
funding stress is at or above its own past-year median. The same cut as 9.A,
not tuned for this series.

**Windows, verdict, scoring: as 9.A.**
- Live: the KB-021 trio, labelled on ^GSPC, with the live floor of 0.40.
- Long: AR ∨ TURB on the FF 30 industries, from where the spread is warmed
  up (about 1998) to the FF data's end.
- The verdict runs `underpowered` → `too_late` → `recall_lost` (any crisis
  lost at 5d, PIT or LOCO) → `no_edge` (+0.05, and 0.40 live) → `luck` (90%
  of 200 shifted filters) → `pass`.
- **9.C passes only if both windows read `pass`.** A KB entry either way.

**Reported, not read.**
1. The spread as a fourth OR channel at its own PIT p90 (the [KB-019] role),
   **now with [KB-035]'s two controls built into the harness**:
   - time on alarm, with and without the channel;
   - 200 circular shifts of the channel's firing series (seed and range as
     the filter's null), with the share of shifts that catch at least as many
     crises, and the share at least as precise.
2. **Revision sensitivity.** On the readings after the archive starts, how
   many of the filter's pass/block decisions change when today's values
   replace the first releases, and the verdict each window would read with
   today's values. This measures what ADR-0014 guards against, for this one
   input.
3. The revision check above, recomputed by the run.
4. The share of firings blocked, and which crises were lost.

**Known before any value was read (from history, not from the data).**
- Both rates sat near zero in 2009–2015 and 2020–2021, so the spread was
  compressed then.
- The Fed's Commercial Paper Funding Facility (2008-10 → 2010-02 and
  2020-03 → 2021-03) bought commercial paper during two of the crises, which
  caps the spread exactly then.
- Funding stress led the trouble in 2007–2008. It barely moved in sell-offs
  that did not start in funding (2015-08, 2018-02, 2022).

**Prior, the proposer's, written before the run.** `recall_lost` on at least
one window. A filter that waits for funding stress should block warnings
before sell-offs that never reach the funding market, and the live window
holds several of those. [KB-019] already found the related credit channel
redundant.
