"""
sizing.py — Deterministic vol-target position sizing for the paper portfolio
(Phase 20, WP-20.C).

Turns the pipeline's already-emitted outputs (a bias + confidence per asset, a
HAR-RV vol forecast, the conditional-distribution spread, and the regime
posterior) into **target weights** that `book.py` executes. No LLM, no network,
no model objects — a pure function of plain numbers, so it is fully
unit-testable and point-in-time by construction. `rebalance.py` (WP-20.D) is
responsible for *extracting* these inputs from the pipeline and mapping them
onto `AssetSignal`s; this module only does the arithmetic.

Implements the seven-step rule from DESIGN.md §3:

  1. Direction   d ∈ {+1,−1,0} from the note bias (Bullish/Bearish/Neutral).
                 The 10Y signal is on the *yield*; its bond-proxy position takes
                 −d (Bullish yield ⇒ short bonds) via `invert_sign`.
  2. Confidence  c ∈ [0,1] from the note (or ensemble agreement for `kimi`).
  3. Risk        σ from the HAR-RV annualized vol forecast, cross-checked
                 against the conditional-distribution spread. Missing
                 distribution after fallback ⇒ abstain (d := 0).
  4. Pre-limit   w̃ = d · c / σ   (inverse-vol, signed, confidence-scaled).
  5. Regime gate g = 1 − posterior mass on High-Vol states (dial toward cash).
  6. Vol target  rescale {w̃} so ex-ante book vol ≈ target (default 10% ann.).
  7. Clamps      |w| ≤ MAX_WEIGHT; gross Σ|w| ≤ GROSS_CAP; remainder → cash.

Ordering note (deliberate deviation from the *numbering* in DESIGN §3): the
regime gate (5) is folded into the vol-target rescale (6) as an effective
target `vol_target · g`. Applying the gate *before* an exact rescale-to-target
would cancel it (both numerator and denominator scale with g); folding it into
the target is the only ordering that lets the gate actually dial the book toward
cash. Same result, correct behaviour.

Neutral handling is **flat** in v1 (weight 0 — honest abstention, matches the
ensemble-Neutral semantics). Hold-prior is deferred (needs prior weights; a
WP-20.D concern).

Usage:
    from portfolio.sizing import AssetSignal, RegimeState, SizingConfig, size_positions
    sigs = [
        AssetSignal("S&P 500", "Bullish", 0.7, har_sigma_annual=0.16, cond_sigma_annual=0.18),
        AssetSignal("Gold",    "Bearish", 0.4, har_sigma_annual=0.12, cond_sigma_annual=0.13),
    ]
    regime = RegimeState(posterior=[0.5, 0.2, 0.2, 0.1],
                         labels=["Risk-On Low-Vol","Risk-On High-Vol",
                                 "Risk-Off Low-Vol","Risk-Off High-Vol"])
    result = size_positions(sigs, regime, SizingConfig())
    book.rebalance(result.weights, prices, as_of)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Constants / config
# ---------------------------------------------------------------------------
BIAS_SIGN = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}


@dataclass
class SizingConfig:
    """Every knob in one place so v1 → v2 is an edit, never a rebuild."""
    horizon: int = 5                 # T+h predictions used (weekly ⇒ 5)
    vol_target_annual: float = 0.10  # ex-ante book vol target (fraction)
    max_weight: float = 0.35         # per-asset |w| hard cap
    gross_cap: float = 1.5           # Σ|w| hard cap
    trading_days: int = 252
    # Risk cross-check: how to combine HAR-RV σ with the conditional-dist σ.
    #   "max"  -> conservative: respect the larger dispersion (default)
    #   "mean" -> average the two
    #   "har"  -> HAR-RV only (ignore the conditional dispersion magnitude)
    risk_blend: str = "max"
    # DESIGN §3 step 3: a missing distribution after fallback ⇒ abstain.
    require_distribution: bool = True
    min_sigma_annual: float = 0.02   # σ floor; guards w̃ = d·c/σ from blowing up


@dataclass
class AssetSignal:
    """One asset's inputs, already extracted from the pipeline (point-in-time).

    `asset` is the key `book.py` was told to trade — for the 10Y signal that is
    the *bond-proxy* instrument name (e.g. "10Y (IEF)"), and `invert_sign=True`
    maps the yield bias onto the bond position.
    """
    asset: str
    bias: Optional[str]              # "Bullish" | "Bearish" | "Neutral" | None
    confidence: float                # 0..1 (clamped)
    har_sigma_annual: float          # HAR-RV forecast as an annualized *fraction*
    cond_sigma_annual: Optional[float] = None  # conditional-dist σ, annualized fraction; None ⇒ no dist
    invert_sign: bool = False        # True for the 10Y-yield → bond-proxy mapping


@dataclass
class RegimeState:
    """The regime posterior + state labels from `regime.predict_regime`."""
    posterior: list[float]
    labels: list[str]

    def high_vol_mass(self) -> float:
        """Posterior probability mass sitting on High-Vol states."""
        mass = 0.0
        for p, lab in zip(self.posterior, self.labels):
            if "high-vol" in lab.lower():
                mass += p
        return float(mass)


@dataclass
class AssetTarget:
    """Per-asset diagnostic breakdown — the audit trail for the decision log."""
    asset: str
    direction: float
    confidence: float
    sigma_used: float
    raw_weight: float       # w̃ before vol-target / clamps (post-abstention)
    target_weight: float    # final weight after gate + rescale + clamps
    abstained: bool
    reason: str


@dataclass
class SizingResult:
    weights: dict[str, float]              # asset -> signed target weight (for book.rebalance)
    targets: dict[str, AssetTarget]        # per-asset diagnostics
    gate: float                            # regime gate g = 1 − high-vol mass
    gross: float                           # Σ|w| after clamps
    net: float                             # Σ w after clamps
    vol_target_effective: float            # vol_target · g


# ---------------------------------------------------------------------------
# Input helpers (pure; used by rebalance.py to build AssetSignals)
# ---------------------------------------------------------------------------
def har_sigma_annual_from_forecast(forecast: dict) -> float:
    """HAR-RV `har_rv_forecast()` output → annualized vol as a *fraction*.

    `forecast_daily_vol` is already annualized but expressed in **percent**.
    """
    return float(forecast["forecast_daily_vol"]) / 100.0


def dispersion_annual_from_distribution(
    dist: Optional[dict],
    horizon: int,
    trading_days: int = 252,
) -> Optional[float]:
    """Conditional forward-return distribution → annualized 1σ, as a fraction.

    Uses a robust spread estimate: (p90 − p10) / 2.5631 ≈ 1σ for a normal, then
    annualizes the h-day figure by √(trading_days / h). Returns None if `dist`
    is None (no data after fallback) so the caller can abstain.
    """
    if dist is None:
        return None
    spread = (dist["p90"] - dist["p10"]) / 2.5631  # p90−p10 = 2.5631σ (normal)
    sigma_h = abs(spread)
    return float(sigma_h * math.sqrt(trading_days / horizon))


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------
def _direction(bias: Optional[str], invert: bool) -> float:
    if not bias:
        return 0.0
    d = BIAS_SIGN.get(bias.strip().lower(), 0.0)
    return -d if invert else d


def _effective_sigma(sig: AssetSignal, cfg: SizingConfig) -> float:
    s = sig.har_sigma_annual
    if sig.cond_sigma_annual is not None and cfg.risk_blend != "har":
        if cfg.risk_blend == "max":
            s = max(s, sig.cond_sigma_annual)
        elif cfg.risk_blend == "mean":
            s = 0.5 * (s + sig.cond_sigma_annual)
    return max(s, cfg.min_sigma_annual)


def size_positions(
    signals: list[AssetSignal],
    regime: Optional[RegimeState] = None,
    cfg: Optional[SizingConfig] = None,
) -> SizingResult:
    """Apply the seven-step vol-target rule. Pure; deterministic.

    Returns a :class:`SizingResult` whose `weights` feed straight into
    `book.rebalance(...)`. Abstentions (Neutral / no view / missing distribution)
    simply do not appear in `weights` (⇒ the book closes them to cash).
    """
    cfg = cfg or SizingConfig()
    gate = 1.0 if regime is None else max(0.0, 1.0 - regime.high_vol_mass())
    vol_target_eff = cfg.vol_target_annual * gate

    targets: dict[str, AssetTarget] = {}
    raw: dict[str, float] = {}
    sig_used: dict[str, float] = {}

    # --- steps 1-4: per-asset pre-limit weights -------------------------------
    for sig in signals:
        c = min(1.0, max(0.0, float(sig.confidence)))
        d = _direction(sig.bias, sig.invert_sign)
        sigma = _effective_sigma(sig, cfg)

        abstain = False
        reason = "sized"
        if d == 0.0:
            abstain, reason = True, "neutral/no-view"
        elif cfg.require_distribution and sig.cond_sigma_annual is None:
            abstain, reason = True, "no-distribution"  # DESIGN §3 step 3

        w_raw = 0.0 if abstain else (d * c) / sigma
        raw[sig.asset] = w_raw
        sig_used[sig.asset] = sigma
        targets[sig.asset] = AssetTarget(
            asset=sig.asset, direction=d, confidence=c, sigma_used=sigma,
            raw_weight=w_raw, target_weight=0.0, abstained=abstain, reason=reason,
        )

    # --- step 5+6: regime gate folded into the vol-target rescale -------------
    # ex-ante book vol proxy = Σ|w_a|·σ_a (conservative: assumes no diversification).
    vol_proxy = sum(abs(w) * sig_used[a] for a, w in raw.items())
    scale = 0.0 if vol_proxy <= 0.0 else vol_target_eff / vol_proxy
    scaled = {a: w * scale for a, w in raw.items()}

    # --- step 7: hard clamps --------------------------------------------------
    clamped = {
        a: max(-cfg.max_weight, min(cfg.max_weight, w))
        for a, w in scaled.items()
    }
    gross = sum(abs(w) for w in clamped.values())
    if gross > cfg.gross_cap and gross > 0.0:
        shrink = cfg.gross_cap / gross
        clamped = {a: w * shrink for a, w in clamped.items()}
        gross = cfg.gross_cap

    # Final weights: drop ~zero entries so the book leaves them in cash.
    weights = {a: w for a, w in clamped.items() if abs(w) > 1e-9}
    net = sum(weights.values())
    for a, w in clamped.items():
        targets[a].target_weight = w

    return SizingResult(
        weights=weights,
        targets=targets,
        gate=gate,
        gross=gross,
        net=net,
        vol_target_effective=vol_target_eff,
    )
