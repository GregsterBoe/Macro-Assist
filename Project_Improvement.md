# Macro-Assist — Project Improvement Track

A separate home for **improvement experiments on components that already exist** —
sharpening the quant layer, the fragility monitor, the prompt levers, etc. Kept
apart from the main roadmap on purpose:

| Doc | Holds |
|---|---|
| `Project_Development.md` | The main plan — phases, work packages, the forward roadmap. |
| `Knowledge_Base.md` | **Measured findings** — falsifiable results with their caveats. |
| **`Project_Improvement.md`** (this) | **Improvement experiments** — the design, the staging, and the current status of attempts to make an existing piece better. |

This doc holds the *plan and status* of an improvement. It does **not** hold
results — see the convention immediately below.

---

## Working convention — improvement knowledge lives in the Knowledge Base

**Every improvement experiment that produces a measured result gets written up as
a `Knowledge_Base.md` (KB-###) entry** — the same discipline the fragility track
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
