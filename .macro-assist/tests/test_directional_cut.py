"""
Regression suite for WP-21.D / v1.6 — the directional product cut ([KB-024]).

The cut is easy to undo by accident: a schema field added back, a table column
re-introduced, a scorer that starts counting post-cut notes as real calls. These
tests pin the three things that must stay true.

  1. The output contract carries no direction.
  2. The published table carries the measured base rate instead, and says what
     it is — including when there is no base rate for an asset.
  3. The historical record still scores exactly as it did, and post-cut notes
     are skipped by VERSION, not by accident.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm_analysis as la
import versions
from quant_context import conditional_bucket, conditional_cells
from schemas import AssetPrediction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _pred(asset: str, driver: str = "a driver long enough to pass validation") -> AssetPrediction:
    return AssetPrediction(asset=asset, primary_driver=driver, target_range="1-2")


_ASSETS = ["S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin"]


@pytest.fixture
def quant_raw() -> dict:
    """A collect_quant_raw()-shaped dict with the three assets that have one."""
    return {
        "conditional": {
            "bucket": "NFCI:low|YC:positive|HY:tight",
            "distributions": {
                "SP500_5d":   {"p25": -0.6, "p50": 0.4,  "p75": 1.2, "n": 331},
                "Gold_5d":    {"p25": -1.1, "p50": 1.0,  "p75": 2.7, "n": 331},
                "WTI Oil_5d": {"p25": -3.0, "p50": -0.4, "p75": 3.1, "n": 331},
            },
        }
    }


# ---------------------------------------------------------------------------
# 1. The contract carries no direction
# ---------------------------------------------------------------------------

class TestSchemaHasNoDirection:

    def test_bias_and_confidence_are_gone(self):
        fields = set(AssetPrediction.model_fields)
        assert "bias" not in fields
        assert "confidence_pct" not in fields
        assert fields == {"asset", "primary_driver", "target_range", "horizon_days"}

    def test_tool_schema_offers_the_model_no_direction(self):
        """The JSON Schema is what the model actually sees — check that, not the class."""
        props = AssetPrediction.model_json_schema()["properties"]
        assert "bias" not in props and "confidence_pct" not in props

    def test_a_prediction_still_validates(self):
        p = _pred("S&P 500")
        assert p.horizon_days == 5


# ---------------------------------------------------------------------------
# 2. The published table
# ---------------------------------------------------------------------------

class TestOutlookTable:

    def test_conditional_cells_render_the_base_rate(self, quant_raw):
        cells = conditional_cells(quant_raw)
        assert cells["S&P 500"] == "median +0.4% · P25 -0.6% / P75 +1.2% · n=331"
        # sign is always explicit — a negative median must not read as a typo
        assert cells["WTI Oil"].startswith("median -0.4%")

    def test_assets_without_a_distribution_are_absent_not_invented(self, quant_raw):
        cells = conditional_cells(quant_raw)
        for asset in ("10Y Treasury Yield", "DXY", "Bitcoin"):
            assert asset not in cells

    def test_conditional_cells_never_raises_on_junk(self):
        for junk in (None, {}, {"conditional": None}, {"conditional": {"distributions": None}},
                     {"conditional": {"distributions": {"SP500_5d": {"p50": 0.4}}}}):
            assert conditional_cells(junk) == {}
        assert conditional_bucket(None) == ""

    def test_table_has_no_bias_or_confidence_column(self, quant_raw):
        table = la._outlook_table([_pred(a) for a in _ASSETS], quant_raw)
        header = table.splitlines()[0]
        assert "Bias" not in header and "Confidence" not in header
        assert header.count("|") == 5          # | Asset | Dist | Driver | Range |

    def test_table_publishes_the_base_rate_and_marks_the_gaps(self, quant_raw):
        table = la._outlook_table([_pred(a) for a in _ASSETS], quant_raw)
        assert "median +0.4% · P25 -0.6% / P75 +1.2% · n=331" in table
        # the three assets with no distribution say so, rather than showing blank
        assert table.count(la._NO_BASE_RATE) == 3

    def test_table_degrades_honestly_with_no_quant_data(self):
        """No distributions available is a worse note, never a wrong one."""
        table = la._outlook_table([_pred(a) for a in _ASSETS], None)
        assert table.count(la._NO_BASE_RATE) == 6
        assert "%" not in table.split("Target Range")[1]

    def test_footnote_states_the_cut_and_the_bucket(self, quant_raw):
        note = la._outlook_footnote(quant_raw)
        assert "makes no directional call" in note
        assert "NFCI:low|YC:positive|HY:tight" in note
        assert "KB-024" in note

    def test_analysis_markdown_uses_the_outlook_heading(self, quant_raw):
        """_build_analysis_markdown is the Python-assembly path (synthesis fallback)."""
        import datetime as _dt

        class _Out:
            executive_summary = "summary"
            macro_dashboard_text = None
            equities_note = "eq"
            rates_note = "rates"
            inflation_growth_note = "infl"
            commodities_note = "comm"
            portfolio_risk = None
            sector_opportunity = None
            key_risks = ["r1", "r2", "r3"]
            predictions = [_pred(a) for a in _ASSETS]

        md = la._build_analysis_markdown(_Out(), _dt.datetime(2026, 9, 7), quant_raw)
        assert "### 5-Day Outlook" in md
        assert "5-Day Predictions" not in md
        assert "| Asset | 5d Conditional Distribution |" in md
        assert "Review date:" in md


class TestFreeTextColumnInjection:
    """The fallback path: the model writes the table, Python adds the measured column."""

    _TABLE = (
        "### 5-Day Outlook\n\n"
        "| Asset | Primary Driver | Target Range |\n"
        "|-------|----------------|--------------|\n"
        "| S&P 500 | trend intact | 7,690-7,880 |\n"
        "| DXY | rangebound | 98.2-99.9 |\n"
        "\nReview date: 2026-09-11\n"
    )

    def test_column_is_injected_in_the_right_place(self, quant_raw):
        out = la._inject_conditional_column(self._TABLE, quant_raw)
        row = [l for l in out.splitlines() if l.startswith("| S&P 500")][0]
        cols = [c.strip() for c in row.strip("|").split("|")]
        assert cols[0] == "S&P 500"
        assert cols[1].startswith("median +0.4%")
        assert cols[2] == "trend intact"
        assert cols[3] == "7,690-7,880"

    def test_asset_without_a_base_rate_is_marked(self, quant_raw):
        out = la._inject_conditional_column(self._TABLE, quant_raw)
        dxy = [l for l in out.splitlines() if l.startswith("| DXY")][0]
        assert la._NO_BASE_RATE in dxy

    def test_missing_table_leaves_the_note_untouched(self, quant_raw):
        text = "### Equities\n\nno table here at all\n"
        assert la._inject_conditional_column(text, quant_raw) == text

    def test_footnote_is_appended_once(self, quant_raw):
        out = la._inject_conditional_column(self._TABLE, quant_raw)
        assert out.count("makes no directional call") == 1


# ---------------------------------------------------------------------------
# 3. The historical record
# ---------------------------------------------------------------------------

class TestVersionGate:

    def test_v16_is_current_and_starts_after_v15(self):
        assert versions.PIPELINE_VERSION == "v1.6"
        assert versions.version_for_date(date(2026, 9, 4)) == "v1.5"
        assert versions.version_for_date(date(2026, 9, 5)) == "v1.6"

    @pytest.mark.parametrize("v", ["v0.1", "v1.4", "v1.5"])
    def test_history_still_scores(self, v):
        assert versions.has_directional_calls(v) is True

    @pytest.mark.parametrize("v", ["v1.6", "v1.7", "v1.10", "v2.0"])
    def test_post_cut_versions_do_not(self, v):
        assert versions.has_directional_calls(v) is False

    @pytest.mark.parametrize("v", [None, "", "unknown", "garbage"])
    def test_unknown_version_is_treated_as_scoreable(self, v):
        """Fail toward scoring: mis-skipping real history is the worse error."""
        assert versions.has_directional_calls(v) is True


class TestScorerSkipsPostCutNotes:

    _FRONT = "---\ndate: {d}\nagent_version: {v}\n---\n\n"
    _TABLE = (
        "### 5-Day Predictions\n\n"
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        "|-------|------|----------------|------------|--------------|\n"
        "| S&P 500 | Bullish | because | 63% | 7,690-7,880 |\n"
        "\nReview date: 2026-09-11\n"
    )

    def _write(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "2026-09-04-Friday-macro.md"
        p.write_text(self._FRONT.format(d="2026-09-04", v=version) + self._TABLE, encoding="utf-8")
        return p

    def test_v15_report_still_parses(self, tmp_path):
        import score_predictions as sp
        preds = sp.parse_predictions(self._write(tmp_path, "v1.5"))
        assert preds is not None
        assert preds["S&P 500"]["bias"] == "Bullish"
        assert preds["S&P 500"]["confidence"] == 63

    def test_v16_report_is_skipped_even_with_a_legacy_table(self, tmp_path):
        """The gate is the version, not the table shape — a stray v1.5-shaped
        table in a v1.6 note must not re-open the scored record."""
        import score_predictions as sp
        assert sp.parse_predictions(self._write(tmp_path, "v1.6")) is None


class TestPaperPortfolioDeclines:

    def test_post_cut_note_is_detected(self):
        from portfolio.rebalance import note_is_post_cut, parse_note_signals
        post = "### 5-Day Outlook\n\n| Asset | 5d Conditional Distribution |\n\nReview date: x\n"
        assert note_is_post_cut(post) is True
        assert parse_note_signals(post) == {}

    def test_legacy_note_is_not_flagged(self):
        from portfolio.rebalance import note_is_post_cut
        legacy = "### 5-Day Predictions\n\n| Asset | Bias |\n\nReview date: x\n"
        assert note_is_post_cut(legacy) is False


class TestAdversarialPassMakesNoCall:

    def test_prompt_asks_only_for_a_risk_tag(self):
        assert "confidence_delta" not in la._ADVERSARIAL_PROMPT
        assert '"append_risk"' in la._ADVERSARIAL_PROMPT
        assert "5-Day Outlook" in la._ADVERSARIAL_PROMPT

    def test_revisions_append_a_risk_tag_without_touching_numbers(self):
        table = (
            "| Asset | Primary Driver | Target Range |\n"
            "|-------|----------------|--------------|\n"
            "| Gold | real yields bite | 4,460-4,620 |\n"
        )
        out = la._apply_adversarial_revisions(table, {"Gold": {"append_risk": "[Risk: Real yields]"}})
        assert "[Risk: Real yields]" in out
        assert "4,460-4,620" in out

    def test_a_stray_confidence_delta_is_ignored(self):
        """Belt and braces: an old-shaped model response must not reintroduce a number."""
        table = (
            "| Asset | Primary Driver | Target Range |\n"
            "|-------|----------------|--------------|\n"
            "| Gold | real yields bite | 4,460-4,620 |\n"
        )
        out = la._apply_adversarial_revisions(
            table, {"Gold": {"append_risk": None, "confidence_delta": -10}}
        )
        assert "%" not in out
        assert out.strip().endswith("| Gold | real yields bite | 4,460-4,620 |")


class TestRecordClosure:
    """The scored record is finite now — the run must say when it is complete.

    Without this the weekly cron prints "0 score file(s) written" forever, which
    is indistinguishable from a silent breakage.
    """

    _FRONT = "---\ndate: {d}\nagent_version: {v}\n---\n\n"

    def _report(self, dir_: Path, d: str, version: str) -> tuple:
        dir_.mkdir(parents=True, exist_ok=True)
        p = dir_ / f"{d}-macro.md"
        p.write_text(self._FRONT.format(d=d, v=version), encoding="utf-8")
        return (date.fromisoformat(d), p)

    @pytest.fixture
    def _dirs(self, tmp_path):
        return tmp_path

    def test_directional_reports_filters_by_version(self, tmp_path):
        import score_predictions as sp
        reports = [
            self._report(tmp_path / "a", "2026-09-01", "v1.5"),
            self._report(tmp_path / "b", "2026-09-05", "v1.6"),
        ]
        out = sp.directional_reports(reports)
        assert [d.isoformat() for d, _ in out] == ["2026-09-01"]

    def test_open_window_is_not_closed(self, _dirs):
        import score_predictions as sp
        reports = [self._report(_dirs / "a", "2026-09-04", "v1.5")]
        status = sp.record_closure(reports, date(2026, 9, 10))
        assert status["closed"] is False
        assert status["open_reports"] == 1
        assert status["last_report"] == date(2026, 9, 4)
        # ~20 trading days + buffer after the last call
        assert status["closes_on"] > date(2026, 9, 25)

    def test_all_windows_resolved_closes_the_record(self, _dirs):
        import score_predictions as sp
        reports = [self._report(_dirs / "a", "2026-09-04", "v1.5")]
        assert sp.record_closure(reports, date(2026, 12, 1))["closed"] is True

    def test_post_cut_only_history_is_closed_immediately(self, _dirs):
        """A repo whose every note is v1.6+ has no directional record at all."""
        import score_predictions as sp
        reports = [self._report(_dirs / "a", "2026-09-05", "v1.6")]
        status = sp.record_closure(reports, date(2026, 9, 6))
        assert status["closed"] is True
        assert status["last_report"] is None

    def test_closure_banner_names_the_retirement(self, _dirs, capsys):
        import score_predictions as sp
        reports = [self._report(_dirs / "a", "2026-09-04", "v1.5")]
        sp.print_closure(sp.record_closure(reports, date(2026, 12, 1)))
        out = capsys.readouterr().out
        assert "DIRECTIONAL RECORD CLOSED" in out
        assert "2026-09-04" in out
        assert "can be retired" in out

    def test_open_banner_names_the_closing_date(self, _dirs, capsys):
        import score_predictions as sp
        reports = [self._report(_dirs / "a", "2026-09-04", "v1.5")]
        sp.print_closure(sp.record_closure(reports, date(2026, 9, 10)))
        out = capsys.readouterr().out
        assert "Record closes on" in out
        assert "CLOSED" not in out


class TestDeadFeedbackLoopIsGone:

    def test_load_accuracy_context_is_removed(self):
        import pipeline_config
        assert not hasattr(pipeline_config, "load_accuracy_context")

    def test_it_is_no_longer_re_exported(self):
        import collect_and_analyze as ca
        assert "load_accuracy_context" not in ca.__all__
        assert not hasattr(ca, "load_accuracy_context")
