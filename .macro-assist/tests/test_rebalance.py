"""
Tests for portfolio/rebalance.py (Phase 20, WP-20.D).

Pure unit tests — no network, no model artifacts. The live layer (yfinance /
regime) is lazy-imported and not exercised here; everything below runs on
injected prices/regime and an inline note fixture, so it stays fast and offline.

Run:
    pytest .macro-assist/tests/test_rebalance.py -v
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from portfolio.book import Book
from portfolio.rebalance import (
    GATE_ELEVATED,
    advance_books,
    already_rebalanced,
    booked_weeks,
    build_asset_signals,
    conditional_sigma_annual,
    equal_vol_weights,
    find_note,
    format_report,
    fragility_gate,
    note_arm,
    parse_note_signals,
    sizing_config_for,
    v1_instruments,
)

# A trimmed predictions block in the layout the daily pipeline **actually
# emits** — "(P25 -0.8%/P75 +1.2%)", the two percentiles interleaved with their
# labels and plain ASCII hyphens. The previous fixture used "P25–P75 −0.8%/+1.2%"
# (en-dash + U+2212), a layout no live note has ever carried; it passed while
# production silently parsed nothing and flattened the market book. WTI keeps
# the older paired layout so both stay covered.
NOTE = """\
### 5-Day Predictions

| Asset | Bias | Primary Driver | Confidence | Target Range |
|-------|------|----------------|------------|--------------
| S&P 500 | Neutral | 5d conditional median +0.4% (P25 -0.8%/P75 +1.2%) in the current NFCI-low bucket, n=336. | 58% | -1.0% to +1.3% |
| Gold | Bullish | 5d conditional median +0.9% (P25 -1.1%/P75 +2.6%), n=336 — skewed. | 57% | $4,380–$4,520 |
| WTI Oil | Neutral | 5d conditional median −0.4%, P25–P75 −2.9%/+3.0% — wide. | 60% | $81.50–$88.00 |
| 10Y Treasury Yield | Bullish | Directional view: yields drift higher, real yields elevated. | 51% | 4.65%–4.85% |
| Bitcoin | Neutral | No conditional base rate provided for BTC; no quant edge. | 54% | $60,500–$68,500 |

Review date: 2026-08-26
"""

PRICES = {"S&P 500": 5000.0, "Gold": 2400.0, "Bitcoin": 64000.0, "10Y (IEF)": 95.0}
HAR = {"S&P 500": 0.16, "Gold": 0.14, "Bitcoin": 0.55, "10Y (IEF)": 0.06}


# ---------------------------------------------------------------------------
# Note parsing
# ---------------------------------------------------------------------------
def test_parse_note_signals_reads_table():
    sigs = parse_note_signals(NOTE)
    assert sigs["S&P 500"].bias == "Neutral"
    assert sigs["Gold"].bias == "Bullish"
    assert sigs["Gold"].confidence_pct == 57
    assert sigs["10Y Treasury Yield"].bias == "Bullish"
    assert sigs["Bitcoin"].bias == "Neutral"


def test_parse_returns_empty_without_block():
    assert parse_note_signals("no predictions here") == {}


GOLD_SIGMA = (0.026 - (-0.011)) / 1.349 * math.sqrt(252 / 5)


def test_conditional_sigma_from_band_and_annualizes():
    # Gold band −1.1%/+2.6% -> IQR 3.7% -> sigma_5d = 0.037/1.349, annualized *sqrt(252/5)
    s = conditional_sigma_annual("... P25–P75 −1.1%/+2.6% ...")
    assert s == pytest.approx(GOLD_SIGMA, rel=1e-6)


def test_conditional_sigma_parses_the_live_note_layout():
    """Regression: the exact driver prose from the 2026-08-24 market note.

    The old parser returned None here — it required both percentiles *after*
    "P75" — so every market-arm asset abstained "no-distribution" and the book
    booked zero positions on its first live run.
    """
    driver = (
        "5d conditional median +0.9% (P25 -1.1%/P75 +2.6%), n=336 — constructive "
        "base rate supported by M2 reflation and soft DXY."
    )
    assert conditional_sigma_annual(driver) == pytest.approx(GOLD_SIGMA, rel=1e-6)


@pytest.mark.parametrize("driver", [
    "P25 -1.1%/P75 +2.6%",       # interleaved, ASCII hyphen (live layout)
    "P25 −1.1%/P75 +2.6%",       # interleaved, U+2212 minus
    "P25-P75 -1.1%/+2.6%",       # paired, ASCII hyphen  (regressed: hyphen was excluded)
    "P25–P75 −1.1%/+2.6%",       # paired, en-dash + U+2212
    "P25 to P75: -1.1% / +2.6%",  # paired, prose separator
])
def test_conditional_sigma_is_layout_and_dash_agnostic(driver):
    """The risk input must not depend on which dash the model happened to emit."""
    assert conditional_sigma_annual(driver) == pytest.approx(GOLD_SIGMA, rel=1e-6)


def test_conditional_sigma_none_without_band():
    assert conditional_sigma_annual("Directional view: yields drift higher.") is None
    assert conditional_sigma_annual("No conditional base rate provided for BTC.") is None


# ---------------------------------------------------------------------------
# Signal assembly
# ---------------------------------------------------------------------------
def test_build_asset_signals_maps_universe_and_inverts_10y():
    note_signals = parse_note_signals(NOTE)
    signals = build_asset_signals(note_signals, HAR)
    by = {s.asset: s for s in signals}
    # WTI / DXY are not in the v1 universe -> excluded
    assert set(by) == {"S&P 500", "Gold", "Bitcoin", "10Y (IEF)"}
    assert by["10Y (IEF)"].invert_sign is True
    assert by["Gold"].confidence == pytest.approx(0.57)
    assert by["Gold"].har_sigma_annual == pytest.approx(0.14)
    # 10Y row has no conditional band -> cond σ is None (⇒ sizer abstains by default)
    assert by["10Y (IEF)"].cond_sigma_annual is None
    # BTC row explicitly has no base rate -> None
    assert by["Bitcoin"].cond_sigma_annual is None


def test_equal_vol_weights_are_inverse_vol_and_sum_to_one():
    w = equal_vol_weights({"A": 0.10, "B": 0.20})
    assert w["A"] == pytest.approx(2 / 3)   # lower vol -> larger weight
    assert w["B"] == pytest.approx(1 / 3)
    assert sum(w.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Orchestration (injected prices/regime)
# ---------------------------------------------------------------------------
def _fresh_books():
    book, bench = Book(arm="market"), Book(arm="market-benchmark")
    for inst in v1_instruments():
        book.register(inst)
        bench.register(inst)
    return book, bench


def test_advance_books_sizes_only_actionable_names():
    note_signals = parse_note_signals(NOTE)
    signals = build_asset_signals(note_signals, HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    # Uniform HAR rule (TODO #2): both directional names size, band or not.
    # Gold (Bullish, has band) and 10Y (Bullish yield, band-less -> HAR σ, inverted
    # to a short bond proxy) both trade; S&P/BTC are Neutral -> abstain.
    assert "Gold" in book.positions and book.positions["Gold"].shares > 0
    assert rec["targets"]["Gold"]["abstained"] is False
    assert rec["targets"]["10Y (IEF)"]["abstained"] is False
    assert rec["targets"]["10Y (IEF)"]["weight"] < 0   # Bullish yield -> short bonds
    assert rec["targets"]["S&P 500"]["reason"] == "neutral/no-view"


def test_advance_books_no_live_regime_notes_gate_one():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench,
                        regime=None, har_sigmas=HAR)
    assert rec["gate"] == 1.0


def test_benchmark_inits_then_marks_forward():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    assert bench.positions  # initialized equal-vol on first advance
    nav0 = bench.nav(PRICES)
    # a week later, SPX +10%, no rebalance of the benchmark -> it just marks up
    later = dict(PRICES, **{"S&P 500": 5500.0})
    advance_books(date(2026, 8, 26), "market", signals, later, book, bench, har_sigmas=HAR)
    assert bench.nav(later) > nav0
    # benchmark did not re-trade (still the same as its init close-out set)
    assert bench.decision_log[-1]["as_of"] == "2026-08-19"  # only one rebalance record


def test_live_regime_degrades_to_none_without_fred_key(monkeypatch):
    # No FRED_API_KEY -> point-in-time snapshot can't be built -> gate defaults to 1.0.
    from portfolio import rebalance as R

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert R.live_regime(date(2026, 8, 19)) is None


# A kimi note: ensemble-vote drivers, no conditional bands (the real format).
KIMI_NOTE = """\
---
date: 2026-08-19
arm: kimi
---
### 5-Day Predictions

| Asset | Bias | Driver | Confidence | Target |
| --- | --- | --- | --- | --- |
| S&P 500 | Bearish | ensemble n=12 votes Bear×8 (agreement 67%) | 67% | directional |
| Gold | Bullish | ensemble n=12 votes Bull×11 (agreement 92%) | 92% | directional |
| 10Y Treasury Yield | Bullish | ensemble n=12 votes Bull×12 (agreement 100%) | 100% | directional |
| Bitcoin | Bearish | ensemble n=12 votes Bear×9 (agreement 75%) | 75% | directional |

Review date: 2026-08-24
"""


# ---------------------------------------------------------------------------
# Arm routing (regression: exogenous must not borrow the market note)
# ---------------------------------------------------------------------------
def test_note_arm_from_frontmatter():
    assert note_arm(KIMI_NOTE) == "kimi"
    assert note_arm(NOTE) == "market"           # no frontmatter -> market
    assert note_arm("---\narm: exogenous\n---\nx") == "exogenous"


def test_find_note_matches_arm_and_skips_when_absent(tmp_path):
    (tmp_path / "2026-08-19-Wednesday-macro.md").write_text(NOTE)
    (tmp_path / "2026-08-19-kimi-macro.md").write_text(KIMI_NOTE)
    assert find_note(date(2026, 8, 19), "market", tmp_path).name.endswith("Wednesday-macro.md")
    assert find_note(date(2026, 8, 19), "kimi", tmp_path).name.endswith("kimi-macro.md")
    # No exogenous note exists -> skip, never fall back to another arm's note.
    assert find_note(date(2026, 8, 19), "exogenous", tmp_path) is None


# ---------------------------------------------------------------------------
# Kimi arm: ensemble confidence, no conditional band -> must still trade
# ---------------------------------------------------------------------------
def test_kimi_arm_sizes_without_conditional_bands():
    signals = build_asset_signals(parse_note_signals(KIMI_NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "kimi", signals, PRICES, book, bench,
                        har_sigmas=HAR, cfg=sizing_config_for("kimi"))
    # With require_distribution=False the kimi book actually takes positions.
    assert book.positions, "kimi book should not be inert"
    # Bearish S&P -> short; Bullish 10Y -> short the bond proxy (invert).
    assert rec["targets"]["S&P 500"]["weight"] < 0
    assert rec["targets"]["Gold"]["weight"] > 0
    assert rec["targets"]["10Y (IEF)"]["weight"] < 0


def test_market_arm_sizes_without_band_uniform_rule():
    # TODO #2: every arm runs the same rule now. A band-less directional note sizes
    # off HAR σ for the market arm exactly as it does for kimi — no more per-arm
    # abstention that left market/exogenous structurally flat.
    signals = build_asset_signals(parse_note_signals(KIMI_NOTE), HAR)
    book, bench = _fresh_books()
    advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench,
                  har_sigmas=HAR, cfg=sizing_config_for("market"))
    assert book.positions  # directional calls size off HAR even with no band


def test_already_rebalanced_guards_the_date():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    assert already_rebalanced(book, date(2026, 8, 19)) is False
    advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    # After booking that date, the guard reports it as done (⇒ run() would skip).
    assert already_rebalanced(book, date(2026, 8, 19)) is True
    assert already_rebalanced(book, date(2026, 8, 26)) is False


# ---------------------------------------------------------------------------
# --reset ("rewrite this week"): clean-slate re-book, guarded against history
# ---------------------------------------------------------------------------
def test_booked_weeks_collects_distinct_asofs():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    assert booked_weeks(book) == set()
    advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    advance_books(date(2026, 8, 26), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    assert booked_weeks(book) == {"2026-08-19", "2026-08-26"}


def _patch_live_layer(monkeypatch, tmp_path):
    """Point run()'s network wrappers at deterministic in-memory stand-ins."""
    from portfolio import rebalance as R

    note = tmp_path / "2026-08-19-Wednesday-macro.md"
    note.write_text(NOTE)
    monkeypatch.setattr(R, "find_note", lambda asof, arm, *a, **k: note)
    monkeypatch.setattr(R, "fetch_prices_and_har", lambda asof, **k: (PRICES, HAR))
    monkeypatch.setattr(R, "live_regime", lambda asof: None)
    monkeypatch.setattr(R, "live_fragility_gate", lambda asof, **k: (1.0, {}))


def test_reset_rewrites_the_only_week_as_a_single_entry(monkeypatch, tmp_path):
    from portfolio import rebalance as R

    _patch_live_layer(monkeypatch, tmp_path)
    asof = date(2026, 8, 19)
    # First run books the week; a plain re-run is idempotent (no double-stamp).
    R.run(asof, "market", portfolio_dir=tmp_path)
    assert R.run(asof, "market", portfolio_dir=tmp_path) is None
    book = Book.load(tmp_path / "book__market.json")
    assert booked_weeks(book) == {asof.isoformat()}
    n_before = len(book.decision_log)
    # --reset re-books from scratch: still exactly one entry, not a doubled ledger.
    R.run(asof, "market", portfolio_dir=tmp_path, reset=True)
    book = Book.load(tmp_path / "book__market.json")
    assert booked_weeks(book) == {asof.isoformat()}
    assert len(book.decision_log) == n_before == 1
    assert len(book.nav_history) == 1


def test_reset_refuses_to_discard_a_prior_week(monkeypatch, tmp_path):
    from portfolio import rebalance as R

    _patch_live_layer(monkeypatch, tmp_path)
    book_path = tmp_path / "book__market.json"
    # Seed a book that already carries an *earlier* week's entry.
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    advance_books(date(2026, 8, 12), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    book.save(book_path)
    bench.save(tmp_path / "book__market__benchmark.json")

    # Resetting *this* week must not nuke the prior week — it refuses and no-ops.
    assert R.run(date(2026, 8, 19), "market", portfolio_dir=tmp_path, reset=True) is None
    reloaded = Book.load(book_path)
    assert booked_weeks(reloaded) == {"2026-08-12"}  # untouched


def test_format_report_renders_table():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 19), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    md = format_report(rec)
    assert "# Paper Portfolio — market — 2026-08-19" in md
    assert "| Gold |" in md
    assert "Risk-off gate" in md


# ---------------------------------------------------------------------------
# Fragility gate (DESIGN §3 step 5 — replaces the retired HMM regime gate)
# ---------------------------------------------------------------------------
def test_fragility_gate_elevated_dials_down():
    g, info = fragility_gate({"composite": 61.2, "label": "Elevated", "trend": "Rising"})
    assert g == GATE_ELEVATED
    assert info["source"] == "fragility"
    assert info["label"] == "Elevated"
    assert info["composite"] == 61.2


@pytest.mark.parametrize("label", ["Normal", "Resilient"])
def test_fragility_gate_calm_stays_ungated(label):
    g, info = fragility_gate({"composite": 20.0, "label": label, "trend": "Stable"})
    assert g == 1.0
    assert info["label"] == label


@pytest.mark.parametrize("frag", [None, {}, {"composite": 50.0}])  # None / empty / no label
def test_fragility_gate_degrades_to_ungated(frag):
    g, info = fragility_gate(frag)
    assert g == 1.0
    assert info == {}


def test_advance_books_applies_fragility_gate():
    # An Elevated fragility gate must halve the effective vol target and be
    # recorded in the decision log (transparency), independent of the retired HMM.
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    g, info = fragility_gate({"composite": 60.0, "label": "Elevated", "trend": "Rising"})
    rec = advance_books(
        date(2026, 8, 19), "market", signals, PRICES, book, bench,
        har_sigmas=HAR, gate=g, gate_info=info,
    )
    assert rec["gate"] == GATE_ELEVATED
    assert rec["gate_info"]["label"] == "Elevated"
    assert "fragility" in format_report(rec)


# ---------------------------------------------------------------------------
# Flat-book alarm (DESIGN §7 confirm-on-first-run, automated)
# ---------------------------------------------------------------------------
_FLAT_NOTE = """\
### 5-Day Predictions

| Asset | Bias | Primary Driver | Confidence | Target Range |
|-------|------|----------------|------------|--------------
| S&P 500 | Neutral | No directional conviction this week. | 50% | 7,610-7,790 |
| Gold | Neutral | No directional conviction this week. | 50% | 4,610-4,800 |

Review date: 2026-08-31
"""


def test_flat_book_is_flagged_and_warned_about():
    """A fully-flat book still gets the DESIGN §7 eyeball flag.

    Under the uniform HAR rule (TODO #2) a band-less *directional* call sizes off
    HAR, so the only way a book holds nothing is an **all-Neutral** table — a
    genuine no-view week, not a parse failure. It is unusual enough to still flag,
    and the warning text says so (no longer blaming a missing conditional band).
    """
    signals = build_asset_signals(parse_note_signals(_FLAT_NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 24), "market", signals, PRICES, book, bench, har_sigmas=HAR)

    assert rec["flat_book"] is True
    assert all(t["abstained"] for t in rec["targets"].values())
    assert all(t["reason"] == "neutral/no-view" for t in rec["targets"].values())
    assert "Book fully flat" in format_report(rec)


def test_sized_book_is_not_flagged_flat():
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 24), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    assert rec["flat_book"] is False
    assert "Book fully flat" not in format_report(rec)


def test_report_renders_inverted_neutral_without_a_signed_zero():
    """A Neutral 10Y call inverts to -0.0 and used to render as "-0"."""
    signals = build_asset_signals(parse_note_signals(NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 24), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    rec["targets"]["10Y (IEF)"]["direction"] = -0.0
    assert "| -0 |" not in format_report(rec)


def test_flat_book_does_not_claim_the_cap_bound():
    """A flat book has a full 'shortfall' but nothing was capped — say so once."""
    signals = build_asset_signals(parse_note_signals(_FLAT_NOTE), HAR)
    book, bench = _fresh_books()
    rec = advance_books(date(2026, 8, 24), "market", signals, PRICES, book, bench, har_sigmas=HAR)
    report = format_report(rec)
    assert rec["capped"] == []
    assert "MAX_WEIGHT binds" not in report
    assert "Book fully flat" in report
