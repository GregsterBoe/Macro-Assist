"""
rebalance.py — Weekly driver for the Phase-20 paper portfolio (WP-20.D).

This is the wiring layer that turns a committed macro note into an advanced book:

    note (bias / confidence / conditional P25-P75)  ─┐
    yfinance prices  ──────────────────────────────┤→ AssetSignals → size_positions
    regime posterior (best-effort)  ────────────────┘        │
                                                             ▼
                                          book.rebalance(...)  +  buy-and-hold benchmark
                                                             │
                                                             ▼
                                     results/portfolio/book__<arm>.json  +  a report

Design split (mirrors book.py / sizing.py): the risky-to-get-wrong logic — note
parsing, instrument mapping, signal assembly, benchmark weighting, and the
book-advancing orchestration — is **pure** and injected with prices/regime, so
it is fully unit-tested with no network. The live wrappers (`fetch_prices`,
`live_regime`, `run`) lazy-import yfinance / the quant modules and are the only
network-touching code. Everything is point-in-time: a rebalance at date `t`
reads only the note dated `t` and prices ≤ `t`.

STATUS (2026-09-04, WP-21.D): **this book has no input as of v1.6.** The daily
note no longer publishes a bias or a confidence — [KB-024] found the directional
call anti-informative and it was cut — and those two fields are what
`size_positions` sizes from. `run()` now detects a post-cut note and declines to
advance the book rather than substituting a signal. Re-pointing the sizer at the
conditional distribution (median sign + IQR) is a plausible v2 and is *not* done
here: it would be a new, unvalidated strategy wearing an existing track record's
clothes, and it deserves its own pre-registered test.

Extraction choices (v1, documented so v2 is an edit not a surprise):
  * **bias / confidence** come from the note's 5-Day Predictions table (clean).
    Present in v1.5 and earlier only.
  * **conditional σ** is parsed from the driver prose's "P25-P75 x%/y%" band
    (IQR→σ, annualized) — this is exactly the distribution the note author saw,
    so it is point-in-time-faithful without reloading the table. A row with no
    band (e.g. a purely reasoning-driven 10Y call, or any exogenous note) yields
    σ=None, which **enriches** rather than gates: the uniform rule
    (`require_distribution=False`, TODO #2) falls back to HAR σ, so a missing band
    no longer flatlines the book — it only forgoes the conditional cross-check.
  * **HAR-RV σ** is recomputed from a yfinance price history ending at `t`
    (the loosened-profile notes don't carry a structured vol block to parse).
  * **regime gate** is best-effort: if the live HMM isn't wired/available the
    gate defaults to 1.0 (no haircut) and the decision log records that. Full
    point-in-time regime reconstruction is a follow-up; the hook is here.

v1 universe = {S&P 500, Gold, Bitcoin, 10Y-via-IEF (sign-inverted)}; WTI / DXY
excluded (DESIGN §2). Base currency USD. One book per arm.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from portfolio.book import Book, Instrument
from portfolio.sizing import AssetSignal, RegimeState, SizingConfig, size_positions

# ---------------------------------------------------------------------------
# Paths & universe
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE.parent.parent / "results"
PORTFOLIO_DIR = RESULTS_DIR / "portfolio"

HORIZON = 5           # T+5 predictions (weekly cadence)
TRADING_DAYS = 252
IQR_TO_SIGMA = 1.349  # p75 − p25 = 1.349σ for a normal


def sizing_config_for(arm: str) -> SizingConfig:
    """Per-arm sizing config — **the same rule for every arm** (TODO #2 / DESIGN §6).

    All arms size off direction + HAR-RV σ, with the conditional band *enriching* σ
    when it parses (the `risk_blend="max"` cross-check) rather than gating whether
    the book trades at all: `require_distribution=False` uniformly. HAR σ is a
    measured, point-in-time risk input available for every instrument from prices
    alone, so abstention is reserved for "no directional view" (Neutral), not "this
    note's prose carried no P25/P75 band".

    This replaces the old split (kimi False, market/exogenous True). The split made
    the exogenous book — whose monetary-stance notes never carry a band —
    structurally flat forever, so DESIGN §6's "whose predictions make money" could
    never be measured. It also made the market book hostage to prompt wording (the
    2026-08-24 flat-book incident). A uniform HAR-based rule removes both: the
    conditional band, when present, still sharpens σ; when absent, HAR carries it.

    The `arm` param is retained so a future, deliberate per-arm divergence is a
    one-line edit rather than a signature change."""
    return SizingConfig(horizon=HORIZON, require_distribution=False)


@dataclass(frozen=True)
class InstrumentMap:
    """Maps a predicted asset (note key) onto a tradeable book instrument."""
    note_asset: str       # key as it appears in the note / ASSET_TICKERS
    book_name: str        # canonical Book key
    ticker: str           # yfinance ticker for the *tradeable* instrument
    asset_class: str
    invert_sign: bool = False
    cost_bps: float = 10.0


# The 10Y *yield* signal is traded via a bond-price proxy (IEF), sign-inverted:
# Bullish yield ⇒ short bonds. BTC carries a higher cost assumption.
V1_INSTRUMENTS: list[InstrumentMap] = [
    InstrumentMap("S&P 500", "S&P 500", "^GSPC", "equity"),
    InstrumentMap("Gold", "Gold", "GC=F", "commodity"),
    InstrumentMap("Bitcoin", "Bitcoin", "BTC-USD", "crypto", cost_bps=30.0),
    InstrumentMap("10Y Treasury Yield", "10Y (IEF)", "IEF", "bond", invert_sign=True),
]
_BY_NOTE_ASSET = {m.note_asset: m for m in V1_INSTRUMENTS}


def v1_instruments() -> list[Instrument]:
    """The Instrument objects the books register."""
    return [
        Instrument(m.book_name, m.ticker, m.asset_class, "USD", m.cost_bps)
        for m in V1_INSTRUMENTS
    ]


# ---------------------------------------------------------------------------
# Note parsing (pure — string in, structured out)
# ---------------------------------------------------------------------------
@dataclass
class NoteSignal:
    asset: str            # note key (normalized)
    bias: str             # Bullish | Bearish | Neutral
    confidence_pct: int   # 0..100
    driver: str           # the Primary-Driver prose (for the conditional band)


def _normalize_asset(raw: str) -> str:
    raw = raw.strip()
    if "Bitcoin" in raw:
        return "Bitcoin"
    if "Treasury" in raw or "10Y" in raw:
        return "10Y Treasury Yield"
    return raw


def note_is_post_cut(text: str) -> bool:
    """True when the note is a v1.6+ one that makes no directional call.

    WP-21.D / [KB-024] cut Bias and Confidence from the daily note, and this
    module sizes positions from exactly those two fields. Detecting it explicitly
    means `run()` can say why the book did not advance instead of reporting a
    missing table, which would read as a parsing bug.
    """
    return "### 5-Day Outlook" in text and "### 5-Day Predictions" not in text


def parse_note_signals(text: str) -> dict[str, NoteSignal]:
    """Parse the 5-Day Predictions table (asset / bias / driver / confidence).

    Captures the driver column too (unlike score_predictions.parse_predictions)
    because the conditional band lives there. Returns {} if the block is absent
    — including for every v1.6+ note, which has no directional call to parse.
    """
    block = re.search(r"### 5-Day Predictions\s*\n+(.*?)\nReview date:", text, re.DOTALL)
    if not block:
        return {}
    out: dict[str, NoteSignal] = {}
    for line in block.group(1).splitlines():
        if not line.startswith("|") or "---" in line or "Asset" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 5:
            continue
        asset_raw, bias_raw, driver_raw, conf_raw, *_ = cols
        asset = _normalize_asset(asset_raw)
        if "Bullish" in bias_raw:
            bias = "Bullish"
        elif "Bearish" in bias_raw:
            bias = "Bearish"
        else:
            bias = "Neutral"
        cm = re.search(r"(\d+)", conf_raw)
        conf = int(cm.group(1)) if cm else 50
        out[asset] = NoteSignal(asset=asset, bias=bias, confidence_pct=conf, driver=driver_raw)
    return out


# Every dash/minus codepoint an LLM may emit, normalized to ASCII "-" before
# matching. The previous parser normalized U+2212 only, so a plain hyphen in
# "P25-P75" fell outside its separator class and the band was missed.
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_DASH_MAP = {ord(c): "-" for c in _DASHES}

_NUM = r"([+\-]?\d+(?:\.\d+)?)\s*%"

# Two band layouts occur in the wild and both must parse:
#   interleaved — "(P25 -0.8%/P75 +1.2%)"   ← what the daily pipeline emits
#   paired      — "P25-P75 -0.8%/+1.2%"     ← the layout DESIGN/older notes used
# The separator classes span "-", "–", " to ", ": " and friends without being
# able to swallow the sign or the digits of the number that follows.
_BAND_INTERLEAVED = re.compile(rf"P\s*25\D{{0,4}}?{_NUM}\s*[/,]?\s*P\s*75\D{{0,4}}?{_NUM}")
_BAND_PAIRED = re.compile(rf"P\s*25[^0-9%]{{0,4}}?P\s*75\D{{0,4}}?{_NUM}\s*/\s*{_NUM}")


def parse_conditional_band(driver: str) -> Optional[tuple[float, float]]:
    """Extract (p25, p75) as fractions from a driver's conditional band, or None.

    Tolerant of both band layouts and of any unicode dash/minus, because this is
    LLM prose: the risk input must not depend on which hyphen the model picked.
    """
    norm = driver.translate(_DASH_MAP)
    m = _BAND_INTERLEAVED.search(norm) or _BAND_PAIRED.search(norm)
    if not m:
        return None
    return float(m.group(1)) / 100.0, float(m.group(2)) / 100.0


def conditional_sigma_annual(
    driver: str,
    horizon: int = HORIZON,
    trading_days: int = TRADING_DAYS,
) -> Optional[float]:
    """Parse the conditional P25/P75 band from driver prose → annualized 1σ.

    Uses the IQR estimator (p75−p25)/1.349, then annualizes by √(trading_days/h).
    Returns None when the row carries no band (⇒ the sizer abstains, DESIGN §3
    step 3).

    NOTE (see TODO.md, open decision #1): this reads the band out of the *note
    prose* rather than calling `conditional.lookup_distribution`. That keeps it
    point-in-time-faithful — it is exactly the distribution the note author saw —
    but it makes the book's risk input hostage to prompt wording, which is how
    the 2026-08-24 flat-book incident happened. Reading the table directly needs
    a point-in-time bucket and is a design decision, not a bug fix.
    """
    band = parse_conditional_band(driver)
    if band is None:
        return None
    p25, p75 = band
    sigma_h = (p75 - p25) / IQR_TO_SIGMA
    if sigma_h <= 0:
        return None
    return float(sigma_h * math.sqrt(trading_days / horizon))


# ---------------------------------------------------------------------------
# Signal assembly (pure)
# ---------------------------------------------------------------------------
def build_asset_signals(
    note_signals: dict[str, NoteSignal],
    har_sigmas: dict[str, float],
    horizon: int = HORIZON,
) -> list[AssetSignal]:
    """Merge note signals + HAR-RV σ into `AssetSignal`s, keyed by book instrument.

    Only the v1 universe is included; the 10Y map carries `invert_sign`. HAR σ is
    looked up by *book* name; a missing HAR σ falls back to the conditional σ (and
    if both are missing the sizer's σ floor applies).
    """
    signals: list[AssetSignal] = []
    for note_asset, m in _BY_NOTE_ASSET.items():
        ns = note_signals.get(note_asset)
        if ns is None:
            continue
        cond = conditional_sigma_annual(ns.driver, horizon)
        har = har_sigmas.get(m.book_name)
        if har is None:
            # No price history for HAR — lean on the conditional band if present.
            har = cond if cond is not None else 0.0
        signals.append(
            AssetSignal(
                asset=m.book_name,
                bias=ns.bias,
                confidence=ns.confidence_pct / 100.0,
                har_sigma_annual=har,
                cond_sigma_annual=cond,
                invert_sign=m.invert_sign,
            )
        )
    return signals


def equal_vol_weights(sigmas: dict[str, float]) -> dict[str, float]:
    """Long-only inverse-vol weights (∑=1) for the buy-and-hold benchmark basket.

    The 'scientific' benchmark of DESIGN §5: holds the same universe at equal
    *risk*, so the book is judged on timing/sizing, not on which assets it picked.
    """
    inv = {a: (1.0 / s) for a, s in sigmas.items() if s and s > 0}
    total = sum(inv.values())
    if total <= 0:
        return {}
    return {a: w / total for a, w in inv.items()}


# ---------------------------------------------------------------------------
# HAR-RV σ from a return series (thin wrapper; lazy import)
# ---------------------------------------------------------------------------
def har_sigma_from_returns(returns) -> Optional[float]:
    """Annualized HAR-RV σ (fraction) from a daily log-return series, or None
    if there isn't enough history (needs ≥30 returns)."""
    from vol_forecast import har_rv_forecast
    from portfolio.sizing import har_sigma_annual_from_forecast

    try:
        fc = har_rv_forecast(returns)
    except ValueError:
        return None
    return har_sigma_annual_from_forecast(fc)


# ---------------------------------------------------------------------------
# Orchestration (pure — prices & regime injected)
# ---------------------------------------------------------------------------
def advance_books(
    asof: date,
    arm: str,
    signals: list[AssetSignal],
    prices: dict[str, float],
    book: Book,
    bench: Book,
    regime: Optional[RegimeState] = None,
    har_sigmas: Optional[dict[str, float]] = None,
    cfg: Optional[SizingConfig] = None,
    note_path: Optional[str] = None,
    gate: Optional[float] = None,
    gate_info: Optional[dict] = None,
) -> dict:
    """Advance the arm book and its benchmark by one weekly step.

    - The arm **book** is sized (`size_positions`) and rebalanced to the targets.
    - The **benchmark** is a static equal-vol buy-and-hold: initialized once (on
      its first advance) and marked forward thereafter (weights drift).
    Returns a decision record (targets, gate, trades, NAVs) for the log/report.

    The risk-off `gate` (fragility, DESIGN §3 step 5) is injected — pure here,
    fetched by `run()`. `gate_info` carries the reading (label/composite/trend)
    into the decision log for transparency. `regime` remains as the retired-HMM
    revival path (used only when no explicit `gate` is passed).
    """
    cfg = cfg or sizing_config_for(arm)
    result = size_positions(signals, regime, cfg, gate=gate)

    sleeve_of = {a: "macro" for a in result.weights}
    gate_info = gate_info or {}
    _gate_src = gate_info.get("source", "regime" if regime is not None else "none")
    gate_note = f"gate={result.gate:.3f} (src={_gate_src}"
    if gate_info.get("label"):
        gate_note += f", fragility={gate_info['label']} {gate_info.get('composite')}"
    gate_note += ")"
    rec = book.rebalance(
        result.weights, prices, asof,
        regime_gate=result.gate, note=gate_note, sleeve_of=sleeve_of,
    )

    # Benchmark: init once, then mark forward.
    if not bench.positions:
        sigmas = har_sigmas or {s.asset: s.har_sigma_annual for s in signals}
        bench.rebalance(
            equal_vol_weights(sigmas), prices, asof, note="benchmark init (equal-vol)",
        )
    else:
        bench.mark(prices, asof, note="benchmark mark")

    return {
        "as_of": asof.isoformat(),
        "arm": arm,
        "note": note_path,
        "gate": result.gate,
        "gate_info": gate_info,
        "vol_target_effective": result.vol_target_effective,
        "vol_ex_ante": result.vol_ex_ante,
        "vol_shortfall": result.vol_shortfall,
        "capped": result.capped,
        "gross_capped": result.gross_capped,
        # A book with no positions at all now means *every* call was Neutral —
        # under the uniform HAR rule (TODO #2) a band-less directional call still
        # sizes off HAR, so a flat book is a genuine no-directional-view week, not
        # a parse failure. Still worth the DESIGN §7 eyeball (an all-Neutral table
        # is unusual), so it stays flagged.
        "flat_book": not result.weights and bool(signals),
        "targets": {
            a: {
                "direction": t.direction,
                "confidence": round(t.confidence, 4),
                "sigma": round(t.sigma_used, 4),
                "weight": round(t.target_weight, 4),
                "abstained": t.abstained,
                "reason": t.reason,
            }
            for a, t in result.targets.items()
        },
        "trades": rec["trades"],
        "book_nav": rec["nav_after"],
        "bench_nav": bench.nav(prices),
    }


def format_report(record: dict) -> str:
    """A short markdown report for the week's rebalance."""
    lines = [
        f"# Paper Portfolio — {record['arm']} — {record['as_of']}",
        "",
        f"- Risk-off gate: **{record['gate']:.3f}** "
        + (
            f"(fragility {record['gate_info']['label']} "
            f"{record['gate_info'].get('composite')}, "
            f"trend {record['gate_info'].get('trend')}) "
            if record.get("gate_info", {}).get("source") == "fragility"
            else f"(source: {record.get('gate_info', {}).get('source', 'none')}) "
        )
        + f"→ effective vol target {record['vol_target_effective'] * 100:.1f}%",
        f"- Ex-ante book vol: **{record.get('vol_ex_ante', 0.0) * 100:.1f}%**"
        + (
            f"  ·  ⚠️ {record['vol_shortfall'] * 100:.1f}pp under target — "
            + (
                f"MAX_WEIGHT binds on {', '.join(record['capped'])}"
                if record.get("capped")
                else "GROSS_CAP binds"
            )
            # Only meaningful when the cap is what held the book back; a fully
            # flat book is a different failure and gets its own warning below.
            if record.get("vol_shortfall", 0.0) > 5e-4
            and (record.get("capped") or record.get("gross_capped"))
            else ""
        ),
        # NAV comparison (TODO #6). While the book holds no risk, any gap to the
        # benchmark is the benchmark paying its entry/holding costs against a book
        # sitting in cash — an entry-cost artifact, not alpha. Label it as such so
        # a flat-week +Xbp is never read as outperformance; the excess-return read
        # only means something once the book has taken exposure (DESIGN §5).
        f"- Book NAV: **{record['book_nav']:,.2f}**  ·  Benchmark NAV: "
        f"**{record['bench_nav']:,.2f}**"
        + (
            "  ·  _(book flat — the gap is the benchmark's entry cost, not alpha;"
            " excess return is meaningful only from first exposure)_"
            if not any(t["weight"] for t in record["targets"].values())
            else ""
        ),
        "",
        "| Instrument | Dir | Conf | σ (ann) | Weight | Note |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for a, t in record["targets"].items():
        # `+.0f` renders an inverted Neutral as "-0"; force the sign off a zero.
        d = t["direction"] or 0.0
        lines.append(
            f"| {a} | {d:+.0f} | {t['confidence']:.0%} | "
            f"{t['sigma']:.1%} | {t['weight']:+.2%} | {t['reason']} |"
            if d else
            f"| {a} | 0 | {t['confidence']:.0%} | "
            f"{t['sigma']:.1%} | {t['weight']:+.2%} | {t['reason']} |"
        )
    if record.get("flat_book"):
        lines += [
            "",
            "> ⚠️ **Book fully flat** — every instrument is Neutral (no directional "
            "view). Under the uniform HAR rule a band-less directional call would "
            "still size, so this is a genuine no-view week rather than a parse "
            "failure — but an all-Neutral table is unusual, so confirm the note "
            "actually holds no conviction (DESIGN §7).",
        ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Live layer (lazy imports; the only network / model-touching code)
# ---------------------------------------------------------------------------
def note_arm(text: str) -> str:
    """The arm a note belongs to, from its frontmatter `arm:` field. Notes with
    no `arm` field are the original market pipeline ⇒ 'market'."""
    if not text.startswith("---"):
        return "market"
    end = text.find("---", 3)
    fm = text[3:end] if end != -1 else ""
    m = re.search(r"^arm:\s*(\S+)", fm, re.MULTILINE)
    return m.group(1).strip() if m else "market"


def find_note(asof: date, arm: str, results_dir: Path = RESULTS_DIR) -> Optional[Path]:
    """Locate the committed macro note for (date, arm), matched by the note's
    frontmatter `arm:` field. Returns None if no note for that arm exists on the
    date — the caller then skips (no silent fallback to another arm's note)."""
    for path in sorted(results_dir.rglob(f"{asof.isoformat()}*-macro.md")):
        if "test" in path.name.lower():
            continue
        if note_arm(path.read_text(encoding="utf-8")) == arm:
            return path
    return None


def fetch_prices_and_har(asof: date, lookback_days: int = 130) -> tuple[dict[str, float], dict[str, float]]:
    """Fetch close prices at `asof` and HAR-RV σ per book instrument (yfinance)."""
    import numpy as np
    import pandas as pd
    import yfinance as yf

    start = asof - timedelta(days=lookback_days)
    prices: dict[str, float] = {}
    har: dict[str, float] = {}
    for m in V1_INSTRUMENTS:
        try:
            raw = yf.download(
                m.ticker, start=start.isoformat(),
                end=(asof + timedelta(days=1)).isoformat(),
                progress=False, auto_adjust=True,
            )
            col = raw["Close"].dropna()
            if hasattr(col, "columns"):
                col = col.iloc[:, 0]
            col.index = pd.to_datetime(col.index).tz_localize(None).normalize()
            if col.empty:
                continue
            prices[m.book_name] = float(col.iloc[-1])
            if len(col) >= 32:
                returns = pd.Series(np.log(col.values[1:] / col.values[:-1]))
                s = har_sigma_from_returns(returns)
                if s is not None:
                    har[m.book_name] = s
        except Exception as exc:  # network / ticker hiccup — skip, don't crash the run
            print(f"  Warning: price fetch for {m.ticker} failed: {exc}")
    return prices, har


def live_regime(asof: date) -> Optional[RegimeState]:
    """Best-effort **point-in-time** regime posterior for the gate.

    Reconstructs the regime the way the pipeline does — an ALFRED-vintage macro
    snapshot as knowable on `asof` (`point_in_time.historical_snapshot`) → the
    4-feature vector (`regime_features`) → the fitted HMM (`regime.predict_regime`).
    Returns None (⇒ gate 1.0) on any missing piece — no model artifact, no
    FRED_API_KEY, or a network hiccup — so a rebalance never crashes on the gate.
    """
    import os

    import numpy as np

    from regime import (
        DEFAULT_MODEL_PATH, label_states, load_regime_model, predict_regime,
        regime_enabled,
    )
    from regime_features import regime_features

    # REGIME-RETIRED (KB-006): the HMM gate is off by default — no regime gating,
    # book runs ungated (gate=1.0). Set REGIME_ENABLED=1 to revive it.
    if not regime_enabled():
        print("  live_regime: HMM regime retired (KB-006) — gate defaults to 1.0")
        return None

    if not DEFAULT_MODEL_PATH.exists() or not os.environ.get("FRED_API_KEY"):
        print("  live_regime: no model artifact or FRED_API_KEY — gate defaults to 1.0")
        return None
    try:
        from point_in_time import historical_snapshot

        model = load_regime_model()
        snapshot = historical_snapshot(asof)
        features = regime_features(snapshot)
        features = np.where(np.isnan(features), 0.0, features)
        result = predict_regime(model, features)
        labels = label_states(model)
        ordered = [labels.get(i, f"State {i}") for i in range(len(result["posterior"]))]
        return RegimeState(posterior=[float(p) for p in result["posterior"]], labels=ordered)
    except Exception as exc:  # vintage/network/feature failure — degrade, don't crash
        print(f"  live_regime: reconstruction failed ({exc}) — gate defaults to 1.0")
        return None


# ---------------------------------------------------------------------------
# Fragility gate — the live risk-off dial (DESIGN §3 step 5)
# ---------------------------------------------------------------------------
# Replaces the retired HMM regime gate (KB-006). The fragility index is the one
# risk signal in the system validated look-ahead-safe (KB-001/002: Elevated flag
# 0.53–0.73 precision, 4–8 trading-day lead to the drawdown trough), and it reads
# only yfinance prices ≤ t, so it is point-in-time-safe by construction (prices
# aren't revised — no ALFRED-vintage / FRED-key dependency the regime gate had).
#
# The gate is a THRESHOLD step on the validated Elevated *label*, NOT a continuous
# dial: the A.2/A.3 backtest validated the level flag, not a calibrated g-curve.
# Directionally neutral — it only dials gross exposure toward cash, never flips a
# call — so it preserves the book's clean "does the signal have edge" test.
GATE_ELEVATED = 0.5   # Elevated fragility ⇒ halve the effective vol target
# The universe the fragility index reads (matches fragility.py's expectations).
_FRAG_TICKERS = {
    "sp500": "^GSPC", "gold": "GC=F", "treasury_10y": "^TNX", "dxy": "DX-Y.NYB",
    "bitcoin": "BTC-USD", "vix": "^VIX", "vix3m": "^VIX3M",
}


def fragility_gate(frag: Optional[dict]) -> tuple[float, dict]:
    """Map a `fragility.fragility_index()` reading → gate g ∈ (0,1] + a log record.

    Pure. `frag=None` (or a reading with no label) ⇒ g=1.0 (ungated) and an empty
    record, so a degraded fetch never haircuts the book. Only the validated
    `Elevated` label dials down (`GATE_ELEVATED`); Normal/Resilient stay at 1.0.
    """
    if not frag or "label" not in frag:
        return 1.0, {}
    label = frag["label"]
    g = GATE_ELEVATED if label == "Elevated" else 1.0
    info = {
        "source": "fragility",
        "composite": round(float(frag.get("composite", 0.0)), 1),
        "label": label,
        "trend": frag.get("trend"),
    }
    return g, info


def live_fragility_gate(asof: date, lookback_days: int = 400) -> tuple[float, dict]:
    """Best-effort **point-in-time** fragility gate for `asof` (yfinance only).

    Fetches ~1y of close history ≤ `asof` for the fragility universe, runs
    `fragility_index`, and maps the label to a gate. Returns (1.0, {}) on any
    missing piece — no network, an empty pull, or a compute error — so a
    rebalance never crashes on the gate and an unavailable reading means "ungated"
    rather than a silent haircut. The 180-day fragility window fits inside 400
    calendar days of history with margin.
    """
    try:
        import pandas as pd
        import yfinance as yf

        from fragility import fragility_index

        start = asof - timedelta(days=lookback_days)
        histories: dict[str, "pd.Series"] = {}
        for name, ticker in _FRAG_TICKERS.items():
            try:
                raw = yf.download(
                    ticker, start=start.isoformat(),
                    end=(asof + timedelta(days=1)).isoformat(),
                    progress=False, auto_adjust=True,
                )
                col = raw["Close"].dropna()
                if hasattr(col, "columns"):
                    col = col.iloc[:, 0]
                if not col.empty:
                    histories[name] = col
            except Exception:
                continue

        frag = fragility_index(histories) if histories else None
        g, info = fragility_gate(frag)
        if info:
            print(f"  live_fragility_gate: {info['label']} "
                  f"(composite {info['composite']}) → gate={g:.3f}")
        else:
            print("  live_fragility_gate: no reading — gate defaults to 1.0")
        return g, info
    except Exception as exc:  # import/network hiccup — degrade, don't crash
        print(f"  live_fragility_gate: failed ({exc}) — gate defaults to 1.0")
        return 1.0, {}


def _new_book(arm: str) -> Book:
    """A fresh, instrument-registered book (starting NAV, no history)."""
    book = Book(arm=arm)
    for inst in v1_instruments():
        book.register(inst)
    return book


def _load_or_init(path: Path, arm: str) -> Book:
    return Book.load(path) if path.exists() else _new_book(arm)


def already_rebalanced(book: Book, asof: date) -> bool:
    """True if the book's decision log already has a rebalance for `asof` — the
    guard that keeps `run()` idempotent (a re-run or CI retry must not double-stamp
    the same weekly signal onto the NAV series)."""
    return any(r.get("as_of") == asof.isoformat() for r in book.decision_log)


def booked_weeks(book: Book) -> set[str]:
    """The distinct as-of dates the book has already booked — the reset guard's
    view of a book's history."""
    return {r.get("as_of") for r in book.decision_log if r.get("as_of")}


def run(
    asof: date,
    arm: str = "market",
    portfolio_dir: Path = PORTFOLIO_DIR,
    force: bool = False,
    reset: bool = False,
) -> Optional[dict]:
    """Live weekly rebalance for one arm: read the note, fetch prices, size,
    advance the book + benchmark, and persist ledger + report. Idempotent per
    (date, arm) unless `force=True`.

    `reset=True` ("rewrite this week"): discard the current week's entry and
    re-book both the arm book and its benchmark from a clean slate. Only valid
    while `asof` is the *only* week the book has booked — a single-week rewind of
    a multi-week book would need pre-trade state the ledger doesn't store, so if
    any prior week exists the reset is refused rather than silently destroying a
    track record. Implies `force` for the (now empty) idempotency guard.
    """
    note_path = find_note(asof, arm)
    if note_path is None:
        print(f"No macro note found for {asof} / arm={arm}; skipping.")
        return None
    note_text = note_path.read_text(encoding="utf-8")
    note_signals = parse_note_signals(note_text)
    if not note_signals:
        if note_is_post_cut(note_text):
            # Not a parsing failure — the input was withdrawn. v1.6 (WP-21.D)
            # cut the bias/confidence this book sizes from, so there is nothing
            # to size. The book is left exactly as it was rather than advanced
            # with an improvised signal: a paper track record built on a
            # substitute input is not the track record it claims to be.
            print(f"{note_path.name} is a v1.6+ note: no directional call to size from "
                  f"(WP-21.D / KB-024). Book not advanced.")
        else:
            print(f"No predictions table in {note_path.name}; skipping.")
        return None

    book_path = portfolio_dir / f"book__{arm}.json"
    bench_path = portfolio_dir / f"book__{arm}__benchmark.json"
    book = _load_or_init(book_path, arm)
    bench = _load_or_init(bench_path, f"{arm}-benchmark")

    if reset:
        prior = booked_weeks(book) - {asof.isoformat()}
        if prior:
            print(f"Refusing --reset on {arm}: book has prior week(s) "
                  f"{sorted(prior)}; reset would discard them. A single-week "
                  f"rewind of a multi-week book is not supported — reset is only "
                  f"for rewriting the first/only week.")
            return None
        # Clean slate: re-book this week from a fresh book + benchmark, so the
        # persisted JSON is a single day-1 entry rather than a doubled ledger.
        book = _new_book(arm)
        bench = _new_book(f"{arm}-benchmark")
        force = True

    # Idempotency: skip a date the book has already booked (before any network).
    if already_rebalanced(book, asof) and not force:
        print(f"{arm} book already rebalanced for {asof}; skipping (use --force to redo).")
        return None

    prices, har = fetch_prices_and_har(asof)
    if not prices:
        print("No prices fetched; skipping rebalance.")
        return None

    signals = build_asset_signals(note_signals, har)

    # Risk-off gate (DESIGN §3 step 5). Fragility is the live gate; the retired
    # HMM regime is used only when explicitly revived (REGIME_ENABLED=1), in which
    # case it takes precedence and the fragility gate is not applied.
    regime = live_regime(asof)
    if regime is not None:
        gate, gate_info = None, {"source": "regime"}
    else:
        gate, gate_info = live_fragility_gate(asof)

    record = advance_books(
        asof, arm, signals, prices, book, bench,
        regime=regime, har_sigmas=har, cfg=sizing_config_for(arm),
        note_path=str(note_path.name), gate=gate, gate_info=gate_info,
    )

    book.save(book_path)
    bench.save(bench_path)
    report_path = portfolio_dir / f"{asof.isoformat()}__{arm}__portfolio.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(format_report(record), encoding="utf-8")
    print(f"Rebalanced {arm} book @ {asof}: NAV {record['book_nav']:,.2f} "
          f"vs bench {record['bench_nav']:,.2f} → {report_path.name}")
    return record


def main(argv: Optional[list[str]] = None) -> None:
    import argparse

    p = argparse.ArgumentParser(description="Weekly paper-portfolio rebalance (Phase 20).")
    p.add_argument("--date", type=date.fromisoformat, default=date.today(),
                   help="Rebalance date (YYYY-MM-DD); default today.")
    p.add_argument("--arm", default="market", choices=["market", "exogenous", "kimi"])
    p.add_argument("--force", action="store_true",
                   help="Redo a date already booked (overrides the idempotency guard).")
    p.add_argument("--reset", action="store_true",
                   help="Rewrite this week: discard the current week's entry and "
                        "re-book from a clean slate. Refused if the book already "
                        "has a prior week (only rewrites the first/only week).")
    args = p.parse_args(argv)
    run(args.date, args.arm, force=args.force, reset=args.reset)


if __name__ == "__main__":
    main()
