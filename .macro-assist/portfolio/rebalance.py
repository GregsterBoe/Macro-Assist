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

Extraction choices (v1, documented so v2 is an edit not a surprise):
  * **bias / confidence** come from the note's 5-Day Predictions table (clean).
  * **conditional σ** is parsed from the driver prose's "P25-P75 x%/y%" band
    (IQR→σ, annualized) — this is exactly the distribution the note author saw,
    so it is point-in-time-faithful without reloading the table. A row with no
    band (e.g. a purely reasoning-driven 10Y call) yields σ=None ⇒ the sizer
    abstains (DESIGN §3 step 3). Reloading the full conditional table for such
    rows is a later refinement.
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

from portfolio.book import Book, Instrument, buy_and_hold
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
    """Per-arm sizing config. The **kimi** arm is the ensemble-confidence
    experiment: its notes carry ensemble-agreement (not conditional base rates),
    so it sizes off direction + HAR vol + agreement-as-confidence with
    `require_distribution=False` — otherwise every kimi call would abstain and the
    arm would never trade. Market / exogenous keep the conservative default
    (abstain without a measurable distribution)."""
    if arm == "kimi":
        return SizingConfig(horizon=HORIZON, require_distribution=False)
    return SizingConfig(horizon=HORIZON)


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


def parse_note_signals(text: str) -> dict[str, NoteSignal]:
    """Parse the 5-Day Predictions table (asset / bias / driver / confidence).

    Captures the driver column too (unlike score_predictions.parse_predictions)
    because the conditional band lives there. Returns {} if the block is absent.
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


def conditional_sigma_annual(
    driver: str,
    horizon: int = HORIZON,
    trading_days: int = TRADING_DAYS,
) -> Optional[float]:
    """Parse the 'P25-P75 x%/y%' band from driver prose → annualized 1σ (fraction).

    Uses the IQR estimator (p75−p25)/1.349, then annualizes by √(trading_days/h).
    Returns None if no band is present (⇒ the sizer abstains).
    """
    norm = driver.replace("−", "-")  # unicode minus → ASCII
    m = re.search(
        r"P25[^0-9+\-]{0,4}P75\s*([+\-]?\d+(?:\.\d+)?)\s*%\s*/\s*([+\-]?\d+(?:\.\d+)?)\s*%",
        norm,
    )
    if not m:
        return None
    p25, p75 = float(m.group(1)) / 100.0, float(m.group(2)) / 100.0
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
) -> dict:
    """Advance the arm book and its benchmark by one weekly step.

    - The arm **book** is sized (`size_positions`) and rebalanced to the targets.
    - The **benchmark** is a static equal-vol buy-and-hold: initialized once (on
      its first advance) and marked forward thereafter (weights drift).
    Returns a decision record (targets, gate, trades, NAVs) for the log/report.
    """
    cfg = cfg or SizingConfig(horizon=HORIZON)
    result = size_positions(signals, regime, cfg)

    sleeve_of = {a: "macro" for a in result.weights}
    gate_note = f"regime_gate={result.gate:.3f}"
    if regime is None:
        gate_note += " (no live regime — gate=1.0)"
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
        "vol_target_effective": result.vol_target_effective,
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
        f"- Regime gate: **{record['gate']:.3f}** "
        f"(effective vol target {record['vol_target_effective'] * 100:.1f}%)",
        f"- Book NAV: **{record['book_nav']:,.2f}**  ·  Benchmark NAV: "
        f"**{record['bench_nav']:,.2f}**",
        "",
        "| Instrument | Dir | Conf | σ (ann) | Weight | Note |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for a, t in record["targets"].items():
        lines.append(
            f"| {a} | {t['direction']:+.0f} | {t['confidence']:.0%} | "
            f"{t['sigma']:.1%} | {t['weight']:+.2%} | {t['reason']} |"
        )
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
    )
    from regime_features import regime_features

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


def _load_or_init(path: Path, arm: str) -> Book:
    if path.exists():
        return Book.load(path)
    book = Book(arm=arm)
    for inst in v1_instruments():
        book.register(inst)
    return book


def run(asof: date, arm: str = "market", portfolio_dir: Path = PORTFOLIO_DIR) -> Optional[dict]:
    """Live weekly rebalance for one arm: read the note, fetch prices, size,
    advance the book + benchmark, and persist ledger + report."""
    note_path = find_note(asof, arm)
    if note_path is None:
        print(f"No macro note found for {asof} / arm={arm}; skipping.")
        return None
    note_signals = parse_note_signals(note_path.read_text(encoding="utf-8"))
    if not note_signals:
        print(f"No predictions table in {note_path.name}; skipping.")
        return None

    prices, har = fetch_prices_and_har(asof)
    if not prices:
        print("No prices fetched; skipping rebalance.")
        return None

    signals = build_asset_signals(note_signals, har)
    regime = live_regime(asof)

    book_path = portfolio_dir / f"book__{arm}.json"
    bench_path = portfolio_dir / f"book__{arm}__benchmark.json"
    book = _load_or_init(book_path, arm)
    bench = _load_or_init(bench_path, f"{arm}-benchmark")

    record = advance_books(
        asof, arm, signals, prices, book, bench,
        regime=regime, har_sigmas=har, cfg=sizing_config_for(arm),
        note_path=str(note_path.name),
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
    args = p.parse_args(argv)
    run(args.date, args.arm)


if __name__ == "__main__":
    main()
