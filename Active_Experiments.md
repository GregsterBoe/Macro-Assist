# Macro-Assist — Active Experiments

**A living status board.** One glance = what is running, where it stands, and what
comes next. This is the *dashboard*; the depth lives elsewhere. If a row and a
detailed doc disagree, the detailed doc wins — fix the row.

| Doc | Role |
|---|---|
| `Project_Development.md` | The main roadmap — phases & work packages (plans). |
| `Project_Improvement.md` | Improvement experiments on existing components (plans/status). |
| `Knowledge_Base.md` | **Measured findings** (KB-###), incl. negatives — the durable record. |
| **`Active_Experiments.md`** (this) | **Live status board** — the quick overview across all tracks. |

**Status legend:** 🟢 running / on-track · 🟡 in progress, needs work · ⏳ forward-accumulating (waiting on live data) · ⏸ holding / queued · ✅ done · ❌ dropped

_Last updated: 2026-09-04 — Phase 21 resolved; the directional product is cut (v1.6),
both remaining directional arms are stood down, and the scoring loop is winding down.
What is left running is the fragility track and the numeric/quant work._

---

## Active

### IMP-4 — OR-of-channels fragility flag 🟢 LIVE (the note's headline risk read)
- **Tests:** does IMP-1's OR-of-channels recall doubling survive *honest* out-of-sample evaluation, and can it become a live high-recall fragility flag?
- **Latest:** **COMPLETE — IMP-4.3 wired the OR recall MODE live → [KB-021].** `fragility_or.py` computes the flag (composite | absorption | turbulence, each vs its own PIT top decile) off the live ETF panel; a `FRAGILITY_OR_MODE` ladder (off/log/show/active; code default **off**, daily workflow now passes **`show`**) wires it into `quant_context.py` — a MODE, not a weight ([KB-016]). Live path reproduces the operating point (5d OR recall 0.588 vs composite 0.118); today's live reading is **quiet**. Arc: [KB-017] CV spine → [KB-020] live feed parity → [KB-021] live shadow flag. `turbulence_signal` / `fetch_sector_etfs` graduated into the library layer.
- **Next:** **escalated `log → show` (2026-09-04, v1.6)** — the loosened A/B that blocked this is closed with Phase 21, so the confound the ladder was waiting on is gone. The OR flag now renders in the prompt and the Fragility Monitor is a **headline block** in the note, not a footnote in the Data Snapshot. Held at `show`, **not** `active`: `active` would let it widen Target Ranges, and there is still no live forward record. Honest limit stays attached — precision ≈0.32 [KB-016/017], a high-recall "not a normal tape" warning, never a forecast. Next gate: a live firing episode → then consider `active`.
- **Where:** `.macro-assist/fragility_or.py` · `FRAGILITY_OR_MODE` in `quant_context.py` · harness `input_testing.py` (`run_holdout_cv`, `run_etf_panel_gate`) · branch `main`.

### Fragility shadow clock ⏸
- **State:** live computation validated sane; 20-trading-day gate met, but the window was benign — **never fired Elevated live.** Held at `FRAGILITY_MODE=log` (zero output impact).
- **Next:** the A/B half of the gate is gone (closed with Phase 21), so this now waits on **one thing only: a live Elevated episode.** Note that `FRAGILITY_OR_MODE` (the OR flag, IMP-4) has moved to `show` — this row is the *composite* clock (`FRAGILITY_MODE`), still at `log`.
- **Where:** `Project_Development.md` (Phase 16.A) · `.macro-assist/fragility.py`.

---

## Queued / dormant

- **WP-21.E — Bounded indicator search** ⏸ — the honest way back to a directional column. **Capped at 3 feature families, VIX term structure first** (nearly free given the `numeric_baseline.py` panel, and `vix_term` is the strongest fragility component [KB-001] never tested for *direction*). Scored on **sealed holdout** against the same pre-committed `verdict()` bar as WP-21.A. Blocks nothing; if a family clears it the column returns with the base rate published underneath, and if none does it is a KB negative and the search closes for good.
- **WP-18.4 — Input ablation** ⏸ — the real LLM-cost decision gate; gated on sample. Queue (from [KB-009]/[KB-010], union of redundancy + citation screens): drop `vix3m`, collapse sector block, nasdaq-vs-sp500, real_yield-vs-10y, drop-`baa_spread`, drop raw net-liq components. Start cheapest (drop-baa_spread + net-liq).
- **WP-17.5 — Vol / conditional layers** ⏸ — fix the HY-OAS-truncation in the conditional table; safe parallel numeric work, confounds no live A/B. **Higher value than it was:** the conditional table is now the note's published product, not a prompt input.
- **Retire the weekly scoring stage** ⏸ — dated, not open-ended. The last directional note is 2026-09-04 and its T+20 window resolves ~**2026-10-02**; the run prints a `DIRECTIONAL RECORD CLOSED` banner when every window has resolved. Delete stage 3 from `pipeline.yml` then. The readers (`summarize_accuracy.py`, `bias_separation.py`) stay — they read the history.
- **Phase 20 paper portfolio** ⏸ — still scheduled, but its input was withdrawn: it sizes from bias + confidence. `rebalance.run()` detects a post-cut note and declines to advance the book with a message saying why. Left running so the withdrawn input stays visible weekly rather than a track record quietly stopping. Re-pointing the sizer at the conditional distribution is a plausible v2 and needs its own pre-registered test.

---

## Recently closed

### Phase 21 — Directional product validation ✅ RESOLVED → **product cut**
- **Tested:** the rival hypothesis nobody had tested — is 5/10/20-day direction on these assets learnable from this payload by *any* model, or was the LLM being blamed for the task's difficulty?
- **Answer: not learnable. → [KB-024].** Aligned re-run 2026-09-04 (`origin/output` `b3e4255`), all five arms on the same **75,432 calls**: `ridge` 0.530 / BSS −0.087 and `gbm` 0.526 / BSS −0.059 both lose to the constant `always_bullish` (0.557, BSS −0.000, ECE 0.007) on hit-rate, Brier, BSS *and* calibration at once. Both invert on separation (bear−bull +0.093, p=0.002, CI [+0.021, +0.165]), strengthening t5→t20. `ridge`'s 90–100% confidence bin resolves at **0.404**. Mechanism: `drawdown` is the only input both classes find load-bearing, signed *stress → bearish*, and stress mean-reverts at 10–20d — the one stable relationship in the panel is contrarian. `ret_20` closes the 20-day reversion errand negatively (sign stability 0.778, lowest of 20).
- **Shipped:** **WP-21.A ✅** (harness + `horizon+1` embargo + planted-signal positive control + pre-committed bar) and **WP-21.A.2 ✅** (sample alignment — comparators had been scored on 78,656 calls to the models' 75,414, free sample for the benchmark the verdict turns on). The fix moved `always_bullish` 0.560 → 0.557 and left both models unchanged to three decimals: **the direction of the result never depended on it.**
- **Decision (WP-21.D): CUT, shipped as v1.6.** `Bias` and `Confidence` are gone from the daily note. The conditional distribution that already sat underneath each call — median, P25/P75, n — is now the published product, rendered by Python from `conditional_distributions.json`. `Primary Driver` and `Target Range` stay. `score_predictions.py` gates on version, so v1.5-and-earlier history stays scoreable and [KB-007]/[KB-011]/[KB-022] stay reproducible.
- **Closed with it:** **WP-21.B.2 ❌** (day-alternating A/B — could only ever rank two prompt configs, never establish the target exists; not started, so waiting on it meant months of publishing ~36%-accurate calls at ~63% confidence). **WP-21.C ❌** (base rates *into* the prompt — inverted: the base rate is now the product, not an input the model overwrites). Promoting `loosened` to default ❌ — no directional product left to improve. WP-21.B.1's reader fixes ✅ are kept; they read the history.
- **Next:** **WP-21.E** — bounded pre-registered indicator search, **capped at 3 families, VIX term structure first**, scored on sealed holdout against the same `verdict()` bar. Blocks nothing. If a family clears it, the column comes back with the base rate underneath. Also open: **close the Kimi arm** (recommended, not done — it calibrates a `confidence_pct` that no longer exists).
- **Where:** `Project_Development.md` (Phase 21) · [KB-024] · `.macro-assist/numeric_baseline.py` · `numeric_baseline/` on `origin/output`.

### Phase 19 — Exogenous Information Engine ❌ DEACTIVATED (mechanism untested)
- **Tests:** can an independent, market-data-light real-world reasoning branch (expectations-gaps / regime, *not* direction) earn its tokens vs the market-only arm?
- **The leverage (worth restating — it is *not* market-vs-institutions):** market data was **deliberately barred** as a core input. The natural rates consensus is the market-implied path (fed-funds / SOFR futures), and using it would have let the arm secretly re-derive from prices and contaminate the A/B (DESIGN §6.1). So the anchor is two **free, official, non-market, point-in-time** consensus sources — the **Philly Fed SPF** (economist consensus: TBOND/TBILL/UNEMP/CPI/RGDP) and the Fed's own **SEP dot plot** (policymaker consensus, `FEDTARMD`) — and the bet is two-layered: **(1)** the gap *between* them is itself a signal (economists disagreeing with the Fed's own dots), and **(2)** both update only quarterly, so between updates the anchor is fixed and the branch tracks **new FOMC communication** (statements, minutes, speeches) drifting away from it. The drift is the tradeable gap. So: *economists vs policymakers vs what the Fed is now saying* — institutions against each other, with the market excluded on purpose.
- **Latest:** monetary vertical slice code-complete L0→L4, **integrated on `main`**, **cron removed 2026-09-04** (`exo_weekly_emit.yml`, manual only); modular/removable (`exogenous/DESIGN.md` §9). Smokes passed; **forward validation only.**
- **Next:** **deactivated 2026-09-04** — removed as stage 3 of `pipeline.yml`. Its pre-committed gate is a scored directional lean A/B'd head-to-head against market-only, and v1.6 cut market-only's calls [KB-024], so the comparator froze and the gate became unreadable. **This pauses the scoring contract, not the thesis:** the expectations-gap mechanism above was never actually tested — it never reached n. Two live ways back: **(a)** re-point the gate at the WP-21.A benchmark (`always_bullish` / `neutral` on the same dates — a real bar, and [KB-024] shows it is hard to beat), or **(b)** re-cut the output the way the main note was, since DESIGN §1 says the branch is about expectations-gaps and regime **not** direction — the directional lean was a scoring convenience, and it is exactly the part that became unscoreable. **(a) is the cheaper read; (b) is the more coherent product.** Soft-kill per DESIGN §9: nothing deleted, `workflow_dispatch` still works.
- **Where:** `Project_Development.md` (Phase 19) · `.macro-assist/exogenous/` · integrated on `main`.

### Kimi ensemble confidence arm ❌ DEACTIVATED
- **Tests:** can ensemble self-consistency (same payload × N through Kimi K2.6; agreement → confidence, split → Neutral) fix the non-discriminative `confidence_pct` ([KB-007])?
- **Latest:** integrated on `main`; **stage removed from `pipeline.yml` 2026-09-04** (`kimi_arm_daily.yml`, manual only), modular. Mechanism proven (converges with other arms on rates); **calibration is the forward question.**
- **Next:** **none — deactivated 2026-09-04.** Removed as stage 4 of `pipeline.yml`; it no longer runs. The arm's question was whether ensemble agreement could calibrate `confidence_pct`, and v1.6 cut `confidence_pct` [KB-024] — calibrating a signal that does not exist is an empty task, not a smaller one. **Soft-kill, nothing deleted:** `kimi_arm.py`, its tests, the emitted notes and the scored history all stay, `calibration_by_arm` still reads them, and `workflow_dispatch` still fires it by hand. Restore the stage in `pipeline.yml` to resume.
- **Where:** `.macro-assist/kimi_arm.py` · branch `main`.

### Loosened-profile A/B (WP-16.B) — conviction floor off + Opus ❌ CLOSED
- **Tests:** does loosening prompt control (floor OFF, base-rate-first, pruned overrides) beat the control arm on Brier/commitment? Baseline [KB-007]: confidence is anti-informative (BSS < 0).
- **Latest:** **UNREADABLE AS RUN — [KB-023].** `MACRO_PROFILE` was switched in one block, so the two arms share **zero** report-dates (baseline 03-13→06-26, loosened 06-29→08-21): arm and market period are the same partition of the data. The apparent repair (Bull−Neut −0.008, p=0.93) does not survive — WTI/Bitcoin/Gold, the assets carrying the [KB-022] inversion, flipped sign across the arm boundary (T+20 WTI −5.9%→+6.2%); the loosened 95% CI [−0.250, +0.424] contains the baseline estimate; and excluding those three the loosened arm is **still inverted** (−0.184 vs −0.280). [KB-011]'s commitment read inherits the same defect.
- **Next:** none — **closed 2026-09-04 with Phase 21**. The re-run (WP-21.B.2) never started and is now superseded: [KB-024] says there is no directional signal for either arm to capture, so ranking the two prompt configs answers a question that no longer matters. `loosened` was never promoted. `MACRO_PROFILE` stays wired (it still switches model + prompt-rule blocks); its A/B is over.
- **Where:** `Project_Development.md` (Phase 16.B → superseded by Phase 21.B) · `MACRO_PROFILE` repo var · branch `main`.

### IMP-1 — Fragility cross-section (absorption + turbulence) ✅
- **Tests:** does a broad *homogeneous* cross-section (Fama-French industries) unlock cross-sectional co-movement measures the ~5 heterogeneous live assets can't support?
- **Latest:** **COMPLETE, positive.** Arc: [KB-012] negative → [KB-013] absorption reversed → [KB-014] turbulence = recall instrument → [KB-015] orthogonal → **[KB-016]** confirmed against the **real** `var_led_vix35`: OR-of-channels roughly *doubles* crisis recall (0.33→0.72 at 5d) at a precision cost (0.43→0.32) — a good trade for a tail-risk gauge. Equal-weight *blend* degrades the validated flag, so adoption = an OR **mode**, not a weight.
- **Next:** hands off to **IMP-4** (OR recall mode). Deliberately NOT auto-wired — needs a live sector-ETF panel, PIT-rolling thresholds, regime-holdout CV.
- **Where:** `Project_Improvement.md` (IMP-1) · harness `.macro-assist/input_testing.py` · branch `main`.

- **IMP-2 — Credit / funding channel** ❌ dropped ([KB-019]): credit stress has genuine *standalone* skill (5d nov-AUC ~0.61-0.68) but is **redundant in the OR set** — at the live PIT operating point it adds **zero** recall and only costs precision, because deep spreads co-move with equity vol/absorption in the tail and re-flag crises the trio already catches. **Confirmed on two sources** (Yahoo HYG/IEF proxy + canonical Moody's **BAA10Y**; same +0 PIT recall, same +1 LOCO crises). Data note: ICE HY OAS is license-truncated to ~2023+ on free FRED → BAA10Y is the deep substitute via the FRED JSON API. No `fragility.py` change; the ~0.83 OR-set recall stays where [KB-017] left it.
- **IMP-3 — Downside asymmetry** ❌ dropped ([KB-018]): downside semi-deviation / signed asymmetry do NOT sharpen the variance-trend channel — worse on the production ^GSPC (5d recall 0.318→0.227), AUC-negative on FF. The channel already captures the downside info (symmetric std = same trend on twice the data). No `fragility.py` change.
- **Phase 17 — HMM regime layer** ❌ dropped ([KB-006]): a 4-feature rule beat it (drawdown AUC 0.697 vs 0.553) and it was redundant with fragility. Full arc in `active-goals-plan` memory.
