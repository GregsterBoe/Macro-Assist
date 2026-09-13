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
| Tree models learning conditional thresholds | 12–28 crisis episodes, ~7 macro events; [KB-017]/[KB-018]/[KB-019] refused even parameter sweeps on this n. The worked example (AND-gate on composite ≥ p80) *lowers* recall | Reduced to its honest floor: a 3-parameter logistic under LOCO (IMP-6.3). If that cannot beat OR, trees will not |
| HMM regime-switching | Tested four times and retired: [KB-004] no skill, [KB-005] sequence inference reaches 0.55–0.65, [KB-006] loses to a 4-feature linear rule and adds nothing within stress terciles | **Closed.** Re-proposing it argues against KB-006 |
| Rolling / dynamic thresholds | The OR flag already uses expanding-PIT deciles; [KB-017] showed static cuts leaked negligibly. A trailing-252 percentile fires at a fixed rate by construction and discards level | Half done. The remaining half — the composite *label* cut is static — is IMP-5.3 |
| ΔCoVaR | Needs an institution cross-section and quantile regression; the published measure is contemporaneous and its forward form needs quarterly balance-sheet data. [KB-019]: everything financial co-moves in a ≥5% equity drawdown | Not planned |
| SRISK | Slow capital-shortfall measure for financial-system crises; needs leverage data; no free daily feed; horizon mismatch with a 5/10-day label | Not planned |
| Eigenvector centrality | The absorption ratio *is* the dominant-eigenvalue read, live since IMP-4; 9 sector ETFs carry ~2 meaningful eigenvectors | Rides along in IMP-7 as a fourth companion; expected redundant |
| Critical slowing down (lag-1 AR) | **Falsified here**: AUC 0.44/0.50 [KB-001], weight 0 since [KB-002], "exactly as the literature predicted for equities". The "coupled with variance expansion" half *is* the live leading component | **Closed** |
| Shannon entropy | On returns, entropy ≈ ½·log(2πeσ²): variance in disguise, and an entropy *drop* means falling variance — the opposite of [KB-001]. Permutation/sample entropy measures ordering = predictability = the autocorrelation negative again | Not planned; reasoning recorded so it is not re-proposed |

Two framing points, for the next time this comes up: the OR does **not** weight
channels equally — each fires against its *own* PIT top-decile, so severity is
per-channel calibrated; and weighting *was* tested — the rank blend lifted AUC and
degraded the flag [KB-016], which is why OR is a mode and not a weight.

What the review did do was send us back to the live record, which held a finding
none of the proposals would have found — IMP-5.

## IMP-5 — Composite degradation: the calibrated cut only applies to the calibrated composite

**Status:** 🟡 **IMP-5.1–5.2 shipped 2026-09-13 → [KB-029]; IMP-5.3 open.**

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
- [ ] **IMP-5.3 — Align the composite label cut to expanding-PIT.** The OR flag's
  thresholds are the 90th percentile of each channel's *own prior* readings; the
  composite's Elevated cut is a static 56.5 fitted over 2008–2026. Bring the
  label onto the same footing so the two flags in the note are on one method.
  **Gate:** re-walk 2008–2026 with the PIT cut (warm-up 252); the episode
  recall/precision must reproduce [KB-002] within ±1 crisis per horizon, as
  [KB-017] found for the OR flag. If it does not, the static cut stays and the
  discrepancy is a KB entry.

## IMP-6 — Precision at held recall: the aggregator question, asked honestly

**Status:** ⏸ **queued behind IMP-5.3.** Bar written 2026-09-13, before any variant
was run.

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

## IMP-7 — The companion measures IMP-1 listed and never ran

**Status:** ⏸ **queued; expected negative; costs an afternoon.**

IMP-1's candidate list named cross-sectional **dispersion**, **average pairwise
correlation** and **breadth** as "cheap companions computable from the same
panel". They were never run — the arc went AR → turbulence → OR and stopped.
**Eigenvector loading concentration** (from the review) rides along as a fourth.

- Same panel (nine sector ETFs), same standalone gate (`walk_forward_signal` →
  `evaluate_signal`, GO ≈ nov-AUC > 0.60), then the [KB-017] OR-admission gate
  (PIT recall must rise at precision within −0.02).
- **Prior after [KB-019]:** redundant in the tail — orthogonal in calm ≠ orthogonal
  in a ≥5% drawdown. Run so the next session does not have to; one KB entry for
  all four.
