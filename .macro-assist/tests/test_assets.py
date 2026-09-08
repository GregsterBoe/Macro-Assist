"""
Tests for assets.py — the canonical asset registry.

The point of this module is that three call sites (build, render, score) agree on
what a forward change *is*. These tests pin the two things that would silently
break that agreement: the level-vs-percent convention, and the stability of the
keys the persisted table and the live forward record are written under.

All pure unit tests — no network.

Run:
    pytest .macro-assist/tests/test_assets.py -v
"""
from __future__ import annotations

import pytest

from assets import (
    ASSETS,
    BY_KEY,
    BY_NOTE_NAME,
    HORIZONS,
    ORIGINAL_KEYS,
    forward_change,
    format_change,
    get,
)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_keys_are_unique_and_stable():
    keys = [a.key for a in ASSETS]
    assert len(keys) == len(set(keys))
    # These three key the persisted distribution table and every quant-context
    # log line written since 2026-05-29. Renaming one silently orphans the
    # forward record it belongs to.
    assert ORIGINAL_KEYS <= set(keys)
    assert {"SP500", "Gold", "WTI Oil"} == ORIGINAL_KEYS


def test_note_names_are_unique():
    names = [a.note_name for a in ASSETS]
    assert len(names) == len(set(names))


def test_every_asset_has_a_coherent_convention():
    for a in ASSETS:
        assert a.convention in ("pct", "level")
        assert a.unit == ("bp" if a.convention == "level" else "%")


def test_the_ten_year_is_the_only_level_asset():
    # ^TNX quotes a yield *level*; everything else quotes a price. If another
    # level-quoted series is ever added this test should be updated, not deleted.
    level = {a.key for a in ASSETS if a.is_level}
    assert level == {"UST10Y"}


def test_lookup_by_key_and_by_note_name():
    assert get("SP500") is BY_KEY["SP500"]
    assert get("S&P 500") is BY_NOTE_NAME["S&P 500"]
    assert get("10Y Treasury Yield").key == "UST10Y"
    assert get("nonsense") is None


def test_horizons_cover_the_published_and_logged_windows():
    assert 5 in HORIZONS and 20 in HORIZONS


# ---------------------------------------------------------------------------
# forward_change — the convention that actually bites
# ---------------------------------------------------------------------------

def test_pct_asset_is_a_percent_return():
    assert forward_change(100.0, 101.0, "SP500") == pytest.approx(1.0)
    assert forward_change(100.0, 99.0, "SP500") == pytest.approx(-1.0)


def test_level_asset_is_an_absolute_basis_point_change():
    # 4.77% -> 4.83% is +6bp, NOT +1.26%.
    assert forward_change(4.77, 4.83, "UST10Y") == pytest.approx(6.0, abs=1e-9)
    assert forward_change(4.77, 4.71, "UST10Y") == pytest.approx(-6.0, abs=1e-9)


def test_level_convention_is_not_the_percent_of_a_percent_bug():
    """The bug this convention exists to prevent, stated as a test.

    Treating a yield level as a price inflates a 6bp move into a 1.26% "return" —
    a ~13x error on any threshold, which is exactly what
    score_predictions.ABSOLUTE_DIFF_ASSETS documents for the directional scorer.
    """
    correct = forward_change(4.77, 4.83, "UST10Y")
    wrong_if_treated_as_price = (4.83 / 4.77 - 1) * 100
    assert correct == pytest.approx(6.0, abs=1e-9)
    assert wrong_if_treated_as_price == pytest.approx(1.258, abs=0.01)
    assert abs(correct / wrong_if_treated_as_price) > 4


def test_pct_asset_rejects_a_non_positive_entry():
    # Returning a number here is how a bad price becomes a plausible score.
    with pytest.raises(ValueError):
        forward_change(0.0, 101.0, "SP500")
    with pytest.raises(ValueError):
        forward_change(-5.0, 101.0, "SP500")


def test_level_asset_accepts_a_zero_entry():
    # A 0% yield is a real level, not a data error, and the difference is defined.
    assert forward_change(0.0, 0.25, "UST10Y") == pytest.approx(25.0)


def test_unknown_asset_raises():
    with pytest.raises(KeyError):
        forward_change(100.0, 101.0, "NotAnAsset")


def test_accepts_an_asset_object_or_a_key():
    a = BY_KEY["Gold"]
    assert forward_change(100.0, 102.0, a) == forward_change(100.0, 102.0, "Gold")


# ---------------------------------------------------------------------------
# format_change — units follow the registry, not the call site
# ---------------------------------------------------------------------------

def test_percent_rendering_carries_sign_and_one_decimal():
    assert format_change(1.21, "SP500") == "+1.2%"
    assert format_change(-0.63, "SP500") == "-0.6%"


def test_basis_point_rendering_is_whole_bp():
    # A tenth of a basis point is noise on a daily yield series.
    assert format_change(6.0, "UST10Y") == "+6bp"
    assert format_change(-12.4, "UST10Y") == "-12bp"


def test_rendering_never_labels_a_yield_move_as_a_percent():
    """The rendering half of the same bug: '+6bp' must not print as '+6.0%'."""
    assert format_change(6.0, "UST10Y").endswith("bp")
    assert "%" not in format_change(6.0, "UST10Y")


# ---------------------------------------------------------------------------
# resolve_note_name — a decorated spelling must not hide a real base rate
# ---------------------------------------------------------------------------

def test_exact_note_name_and_key_both_resolve():
    from assets import resolve_note_name
    assert resolve_note_name("S&P 500") == "S&P 500"
    assert resolve_note_name("SP500") == "S&P 500"
    assert resolve_note_name("  Gold  ") == "Gold"


def test_the_prompt_templates_decorated_bitcoin_row_resolves():
    # system_prompt.md labels the row "Bitcoin (proxy for crypto risk)". The
    # model usually trims it; "usually" is not a contract, and a miss would
    # print "no conditional base rate" over a distribution that exists.
    from assets import resolve_note_name
    assert resolve_note_name("Bitcoin (proxy for crypto risk)") == "Bitcoin"


def test_common_variant_spellings_resolve():
    from assets import resolve_note_name
    assert resolve_note_name("10Y Treasury") == "10Y Treasury Yield"
    assert resolve_note_name("Crude Oil (WTI)") == "WTI Oil"
    assert resolve_note_name("US Dollar Index (DXY)") == "DXY"


def test_an_untracked_asset_resolves_to_none_rather_than_guessing():
    from assets import resolve_note_name
    assert resolve_note_name("Nasdaq") is None
    assert resolve_note_name("") is None
    assert resolve_note_name("Silver") is None
