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

_Last updated: 2026-08-27._

---

## Active

### IMP-4 — OR-of-channels recall mode + regime-holdout CV ✅
- **Tests:** does IMP-1's OR-of-channels recall doubling survive *honest* out-of-sample evaluation, and can it become a live high-recall fragility flag?
- **Latest:** **COMPLETE — IMP-4.3 wired the OR recall MODE live → [KB-021].** `fragility_or.py` computes the flag (composite | absorption | turbulence, each vs its own PIT top decile) off the live ETF panel; a `FRAGILITY_OR_MODE` ladder (off/log/show/active, default **off**) wires it into `quant_context.py` — a MODE, not a weight ([KB-016]). Live path reproduces the operating point (5d OR recall 0.588 vs composite 0.118); today's live reading is **quiet**. Arc: [KB-017] CV spine → [KB-020] live feed parity → [KB-021] live shadow flag. `turbulence_signal` / `fetch_sector_etfs` graduated into the library layer.
- **Next:** forward-observe. Escalate `FRAGILITY_OR_MODE=off → log` (repo var) to start the live shadow record; `log → show → active` only after it looks sane **and** the loosened A/B resolves (a new output lever would confound it).
- **Where:** `.macro-assist/fragility_or.py` · `FRAGILITY_OR_MODE` in `quant_context.py` · harness `input_testing.py` (`run_holdout_cv`, `run_etf_panel_gate`) · branch `main`.

### IMP-1 — Fragility cross-section (absorption + turbulence) ✅
- **Tests:** does a broad *homogeneous* cross-section (Fama-French industries) unlock cross-sectional co-movement measures the ~5 heterogeneous live assets can't support?
- **Latest:** **COMPLETE, positive.** Arc: [KB-012] negative → [KB-013] absorption reversed → [KB-014] turbulence = recall instrument → [KB-015] orthogonal → **[KB-016]** confirmed against the **real** `var_led_vix35`: OR-of-channels roughly *doubles* crisis recall (0.33→0.72 at 5d) at a precision cost (0.43→0.32) — a good trade for a tail-risk gauge. Equal-weight *blend* degrades the validated flag, so adoption = an OR **mode**, not a weight.
- **Next:** hands off to **IMP-4** (OR recall mode). Deliberately NOT auto-wired — needs a live sector-ETF panel, PIT-rolling thresholds, regime-holdout CV.
- **Where:** `Project_Improvement.md` (IMP-1) · harness `.macro-assist/input_testing.py` · branch `main`.

### Loosened-profile A/B (WP-16.B) — conviction floor off + Opus ⏳
- **Tests:** does loosening prompt control (floor OFF, base-rate-first, pruned overrides) beat the control arm on Brier/commitment? Baseline [KB-007]: confidence is anti-informative (BSS < 0).
- **Latest:** running **loosened-continuously**; decisive-call sample is thin (floor-off → mostly Neutral by design). [KB-011] commitment metric: loosened commits 20% vs baseline 56%, net edge −0.067 vs −0.125 — *directionally* holds, decisive n still tiny.
- **Next:** accumulate loosened-tagged scored days; read `profile` A/B in `accuracy_report.md`. The decisive-Brier read is months out.
- **Where:** `Project_Development.md` (Phase 16.B) · `MACRO_PROFILE` repo var · branch `main`.

### Phase 19 — Exogenous Information Engine ⏳
- **Tests:** can an independent, market-data-light real-world reasoning branch (expectations-gaps / regime, *not* direction) earn its tokens vs the market-only arm?
- **Latest:** monetary vertical slice code-complete L0→L4, **integrated on `main`**, running weekly cron (`exo_weekly_emit.yml`); modular/removable (`exogenous/DESIGN.md` §9). Smokes passed; **forward validation only.**
- **Next:** accumulate arm-tagged leans → go/no-go KB entry. Pre-committed kill criterion if it doesn't beat market-only after 2–3 branches.
- **Where:** `Project_Development.md` (Phase 19) · `.macro-assist/exogenous/` · integrated on `main`.

### Kimi ensemble confidence arm ⏳
- **Tests:** can ensemble self-consistency (same payload × N through Kimi K2.6; agreement → confidence, split → Neutral) fix the non-discriminative `confidence_pct` ([KB-007])?
- **Latest:** integrated on `main`, running daily cron (`kimi_arm_daily.yml`), modular. Mechanism proven (converges with other arms on rates); **calibration is the forward question.**
- **Next:** accumulate live samples → does high agreement out-hit low? Read via `calibration_by_arm`.
- **Where:** `.macro-assist/kimi_arm.py` · branch `main`.

### Fragility shadow clock ⏸
- **State:** live computation validated sane; 20-trading-day gate met, but the window was benign — **never fired Elevated live.** Held at `FRAGILITY_MODE=log` (zero output impact).
- **Next:** escalate `log → show → active` only *after* a live Elevated episode **and** once the loosened A/B resolves (escalation is a new output lever that would confound it).
- **Where:** `Project_Development.md` (Phase 16.A) · `.macro-assist/fragility.py`.

---

## Queued / dormant

- **WP-18.4 — Input ablation** ⏸ — the real LLM-cost decision gate; gated on sample. Queue (from [KB-009]/[KB-010], union of redundancy + citation screens): drop `vix3m`, collapse sector block, nasdaq-vs-sp500, real_yield-vs-10y, drop-`baa_spread`, drop raw net-liq components. Start cheapest (drop-baa_spread + net-liq).
- **WP-17.5 — Vol / conditional layers** ⏸ — fix the HY-OAS-truncation in the conditional table; safe parallel numeric work, confounds no live A/B.
## Recently closed

- **IMP-2 — Credit / funding channel** ❌ dropped ([KB-019]): credit stress has genuine *standalone* skill (5d nov-AUC ~0.61-0.68) but is **redundant in the OR set** — at the live PIT operating point it adds **zero** recall and only costs precision, because deep spreads co-move with equity vol/absorption in the tail and re-flag crises the trio already catches. **Confirmed on two sources** (Yahoo HYG/IEF proxy + canonical Moody's **BAA10Y**; same +0 PIT recall, same +1 LOCO crises). Data note: ICE HY OAS is license-truncated to ~2023+ on free FRED → BAA10Y is the deep substitute via the FRED JSON API. No `fragility.py` change; the ~0.83 OR-set recall stays where [KB-017] left it.
- **IMP-3 — Downside asymmetry** ❌ dropped ([KB-018]): downside semi-deviation / signed asymmetry do NOT sharpen the variance-trend channel — worse on the production ^GSPC (5d recall 0.318→0.227), AUC-negative on FF. The channel already captures the downside info (symmetric std = same trend on twice the data). No `fragility.py` change.
- **Phase 17 — HMM regime layer** ❌ dropped ([KB-006]): a 4-feature rule beat it (drawdown AUC 0.697 vs 0.553) and it was redundant with fragility. Full arc in `active-goals-plan` memory.
