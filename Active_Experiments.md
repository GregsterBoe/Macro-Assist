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

_Last updated: 2026-08-25._

---

## Active

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
- **IMP-4 — Regime-holdout CV + OR-of-channels recall mode** 🟡 next up — **validated by [KB-015]/[KB-016]** and now IMP-1's designated successor. Receives the AR (cov 120) + turbulence (cov 252) channels and the confirmed operating point (recall ~0.72 / prec ~0.32 at 5d). Build the OR recall MODE as a distinct high-recall flag; remaining plumbing: live sector-ETF panel, PIT-rolling thresholds, regime-holdout CV (n≈7 crises).
- **IMP-2/3** ⏸ — improvement backlog (credit/funding channel; downside semivariance).

## Recently closed

- **Phase 17 — HMM regime layer** ❌ dropped ([KB-006]): a 4-feature rule beat it (drawdown AUC 0.697 vs 0.553) and it was redundant with fragility. Full arc in `active-goals-plan` memory.
