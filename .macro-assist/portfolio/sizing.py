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

Steps 6 and 7 are solved *jointly*, not in sequence: a per-name cap applied
after a one-shot rescale throws away the capped name's unused risk budget,
leaving the book under target with cap-distorted ratios. See
`_capped_vol_target`. Where the cap binds on every name the target is
unreachable by construction and `SizingResult.vol_shortfall` reports it.

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
from dataclasses import dataclass, field
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
    vol_ex_ante: float = 0.0               # realized ex-ante book vol proxy Σ|w|·σ
    capped: list[str] = field(default_factory=list)  # names frozen at ±max_weight
    gross_capped: bool = False             # True when Σ|w| hit GROSS_CAP

    @property
    def vol_shortfall(self) -> float:
        """Risk budget the cap prevented the book from using (0.0 when on target).

        Non-zero means a hard clamp bound (`capped` / `gross_capped` say which):
        the book is running *below* its vol target and the sizing rule's
        inverse-vol ratios were overridden by the clamp. Surfaced in the report
        so a structurally under-risked book cannot pass unnoticed (DESIGN §7
        confirm-on-first-run). It is also non-zero for a fully abstaining book —
        callers distinguish that case by an empty `capped` and `gross_capped`
        False.
        """
        return max(0.0, self.vol_target_effective - self.vol_ex_ante)


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
    gate: Optional[float] = None,
) -> SizingResult:
    """Apply the seven-step vol-target rule. Pure; deterministic.

    Returns a :class:`SizingResult` whose `weights` feed straight into
    `book.rebalance(...)`. Abstentions (Neutral / no view / missing distribution)
    simply do not appear in `weights` (⇒ the book closes them to cash).

    The risk-off **gate** g ∈ [0,1] dials the whole book toward cash (DESIGN §3
    step 5). Precedence: an explicit ``gate`` (e.g. the fragility gate wired by
    ``rebalance.py``) wins; else it is derived from a ``regime`` posterior
    (``1 − high-vol mass`` — the retired HMM revival path); else 1.0 (ungated).
    """
    cfg = cfg or SizingConfig()
    if gate is not None:
        gate = min(1.0, max(0.0, float(gate)))
    elif regime is not None:
        gate = max(0.0, 1.0 - regime.high_vol_mass())
    else:
        gate = 1.0
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

    # --- steps 5-7: gate + vol target + clamps, solved jointly ---------------
    # Rescale-then-clamp (the naive order) silently loses risk budget: any name
    # truncated at MAX_WEIGHT has its slack dropped rather than reallocated, so
    # the book lands *below* target and the inverse-vol ratios among the
    # surviving names are distorted by the cap. `_capped_vol_target` runs the
    # standard capped allocation instead — rescale the un-capped names onto the
    # remaining risk budget, freeze whatever breaches the cap, repeat.
    clamped, capped_assets = _capped_vol_target(raw, sig_used, vol_target_eff, cfg)

    gross = sum(abs(w) for w in clamped.values())
    gross_capped = gross > cfg.gross_cap and gross > 0.0
    if gross_capped:
        # A separate constraint from MAX_WEIGHT: it shrinks every name
        # proportionally, so it preserves the inverse-vol ratios rather than
        # distorting them, and it is tracked separately from `capped`.
        shrink = cfg.gross_cap / gross
        clamped = {a: w * shrink for a, w in clamped.items()}
        gross = cfg.gross_cap

    vol_ex_ante = sum(abs(w) * sig_used[a] for a, w in clamped.items())

    # Final weights: drop ~zero entries so the book leaves them in cash.
    weights = {a: w for a, w in clamped.items() if abs(w) > 1e-9}
    net = sum(weights.values())
    for a, w in clamped.items():
        targets[a].target_weight = w
        if a in capped_assets and not targets[a].abstained:
            targets[a].reason = "sized (cap)"

    return SizingResult(
        weights=weights,
        targets=targets,
        gate=gate,
        gross=gross,
        net=net,
        vol_target_effective=vol_target_eff,
        vol_ex_ante=vol_ex_ante,
        capped=capped_assets,
        gross_capped=gross_capped,
    )


def _capped_vol_target(
    raw: dict[str, float],
    sigmas: dict[str, float],
    vol_target: float,
    cfg: SizingConfig,
) -> tuple[dict[str, float], list[str]]:
    """Scale `raw` onto `vol_target` subject to |w| <= cfg.max_weight.

    Iterative capped allocation: each pass rescales the still-free names onto
    the risk budget the already-capped names left behind, then freezes any name
    the rescale pushed through the cap. Terminates in at most len(raw) passes
    because every non-final pass freezes at least one name.

    Uses the same conservative ex-ante vol proxy as DESIGN §3 step 6 — Σ|w|·σ,
    no diversification credit. When the cap binds on *every* name the target is
    genuinely unreachable (e.g. four low-vol instruments at |w| <= 0.35 cannot
    add up to 10% book vol); that is a real constraint rather than an error, and
    the caller reports the shortfall via `SizingResult.vol_shortfall`.

    Returns (weights, capped_asset_names).
    """
    weights: dict[str, float] = {a: 0.0 for a in raw}
    capped: dict[str, float] = {}
    free = {a for a, w in raw.items() if w != 0.0}

    while free:
        used = sum(abs(w) * sigmas[a] for a, w in capped.items())
        budget = vol_target - used
        free_vol = sum(abs(raw[a]) * sigmas[a] for a in free)
        if budget <= 0.0 or free_vol <= 0.0:
            # The capped names already consume the whole budget — the remaining
            # views stay flat rather than pushing the book through its target.
            break
        scale = budget / free_vol
        breaching = {a for a in free if abs(raw[a] * scale) > cfg.max_weight}
        if not breaching:
            for a in free:
                weights[a] = raw[a] * scale
            break
        for a in breaching:
            capped[a] = math.copysign(cfg.max_weight, raw[a])
            free.discard(a)

    weights.update(capped)
    return weights, sorted(capped)
