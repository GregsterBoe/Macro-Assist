"""
model_compare.py replays saved days through the production main-analysis call
on several models. These tests hold the parts that are code, offline:

- the user message is recovered exactly from a payload preview;
- each model is run through the production functions, with MACRO_MODEL set for
  the call and restored after;
- a structured answer that never validates is recorded as `failed`, not dropped;
- the reading aids find what they claim to and skip what they say they skip.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

import llm_analysis as la
import model_compare as mc
from schemas import AnalysisOutput

ASSETS = ("S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin")


def _analysis(**over) -> dict:
    d = {
        "executive_summary": "SPX at 7,743 with the 10Y at 5.18%; claims fell to 197k.",
        "macro_regime": "Neutral/Mixed",
        "macro_dashboard_text": "| Fed Funds | 3.63 | Bullish |",
        "equities_note": "Equities firm.", "rates_note": "Rates up 7bp.",
        "inflation_growth_note": "CPI 3.71% YoY.", "commodities_note": "Gold steady.",
        "key_risks": ["TGA rebuilding to $977bn", "Real yield 2.85%", "Oil at 61.25"],
        "predictions": [{"asset": a, "primary_driver": "Driven by real yields at 2.85%.",
                         "target_range": "1-2", "horizon_days": 5} for a in ASSETS],
    }
    d.update(over)
    return AnalysisOutput.model_validate(d).model_dump()


PAYLOAD = ('{"sp500": 7743.12, "dgs10": 5.18, "claims": 197000, "cpi_yoy": 3.71, '
           '"tga": 977084.0, "real_yield": 2.85, "wti": 61.25, "fed": 3.63}')


def test_the_payload_round_trips_through_the_preview():
    msg = "Today is Monday.\n\n## FRED Macro Indicators\n{\n  \"x\": 1\n}\n\n## Market Data\n{}"
    preview = la.build_payload_preview(msg, nonlive_block="## NON-LIVE SIGNALS\nwithheld")
    assert mc.payload_message(preview) == msg
    assert mc.payload_message(la.build_payload_preview(msg)) == msg


def test_numbers_in_the_payload_are_grounded_at_their_precision():
    prose = mc.prose_of(_analysis())
    assert mc.ungrounded_numbers(prose, PAYLOAD) == []
    # a figure the payload does not hold, and one at a precision it rounds away from
    assert mc.ungrounded_numbers("Solana +38.5% and 10Y at 5.25%", PAYLOAD) == ["+38.5", "5.25"]
    # small counts, horizons and years are not checked
    assert mc.ungrounded_numbers("3 risks over 5 days in 2026", PAYLOAD) == []


def test_call_language_is_what_the_prompt_forbids_and_the_dashboard_is_exempt():
    clean = _analysis()
    assert mc.reading_aids(clean, PAYLOAD, {})["call_language"] == []   # dashboard says Bullish
    bad = _analysis(equities_note="Bearish tape; I expect SPX to rise, a 60% chance of it.")
    assert mc.reading_aids(bad, PAYLOAD, {})["call_language"] == ["Bearish", "I expect", "60% chance"]
    assert mc.call_language("Gold is likely to fall as yields climb") == ["likely to fall"]
    assert mc.call_language("real yields are a drag; describe forces") == []


def _tool_message(payload: dict | None, text: str = "") -> SimpleNamespace:
    content = ([SimpleNamespace(type="tool_use", name="submit_analysis", input=payload, id="t1")]
               if payload is not None else [SimpleNamespace(type="text", text=text)])
    return SimpleNamespace(content=content, stop_reason="tool_use",
                           usage=SimpleNamespace(input_tokens=6000, output_tokens=2500,
                                                 cache_creation_input_tokens=0,
                                                 cache_read_input_tokens=0))


class FakeClient:
    """Answers MA-1 with `analysis` (None → an invalid tool call), MA-2 with no
    change, and records the model main_model() resolved for each call."""

    def __init__(self, analysis):
        self.analysis, self.seen = analysis, []
        self.messages = self
        self.models = SimpleNamespace(retrieve=self._retrieve)

    def _retrieve(self, m):
        if m == "claude-missing":
            raise LookupError("not_found_error")
        return SimpleNamespace(id=m)

    def create(self, **kw):
        self.seen.append((kw["model"], os.environ.get("MACRO_MODEL")))
        if kw.get("tools"):
            return _tool_message(self.analysis if self.analysis is not None else {"bad": 1})
        return _tool_message(None, text='{"added_risks": []}')


@pytest.fixture
def previews(tmp_path):
    d = tmp_path / mc.PREVIEW_DIR
    d.mkdir(parents=True)
    for day in ("2026-09-24", "2026-09-25", "2026-09-28"):
        (d / f"{day}.md").write_text(la.build_payload_preview(f"Today is {day}.\n{PAYLOAD}"),
                                     encoding="utf-8")
    return tmp_path


def test_each_model_runs_through_production_with_its_own_model(previews, monkeypatch):
    monkeypatch.delenv("MACRO_MODEL", raising=False)
    client = FakeClient(_analysis())
    rep = mc.run(previews, client=client, models=["claude-opus-4-8", "claude-sonnet-5"], days=2)
    assert rep["days"] == ["2026-09-25", "2026-09-28"]                  # newest two, oldest first
    assert [(r["day"], r["model"], r["structured"]) for r in rep["results"]] == [
        ("2026-09-25", "claude-opus-4-8", "first_try"), ("2026-09-25", "claude-sonnet-5", "first_try"),
        ("2026-09-28", "claude-opus-4-8", "first_try"), ("2026-09-28", "claude-sonnet-5", "first_try")]
    assert all(model == env for model, env in client.seen)             # main_model() saw MACRO_MODEL
    assert "MACRO_MODEL" not in os.environ                             # and it was restored
    assert rep["est_cost_usd"] > 0
    assert "## 2026-09-28" in mc.render(rep)


def test_an_answer_that_never_validates_is_recorded_as_failed(previews):
    rep = mc.run(previews, client=FakeClient(None), models=["claude-sonnet-5"], days=1)
    (r,) = rep["results"]
    assert r["structured"] == "failed" and len(r["calls"]) == 2         # the retry happened
    assert mc.summarize(rep)[0]["failed"] == 1
    assert "**failed**" in mc.render(rep)


def test_an_unknown_model_is_skipped_and_said_so(previews):
    rep = mc.run(previews, client=FakeClient(_analysis()),
                 models=["claude-missing", "claude-sonnet-5"], days=1)
    assert rep["models"] == ["claude-sonnet-5"] and "claude-missing" in rep["skipped_models"]
    assert "**Skipped** `claude-missing`" in mc.render(rep)


def test_the_spend_guard_stops_the_replay(previews):
    rep = mc.run(previews, client=FakeClient(_analysis()), models=["claude-opus-4-8"],
                 days=3, max_usd=0.01)
    assert [r["structured"] for r in rep["results"]] == ["first_try", "not_run", "not_run"]


def test_dry_run_makes_no_call(previews, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert mc.main(["--dry-run", "--days", "2", "--root", str(previews)]) == 0
    assert "no API call made" in capsys.readouterr().out
    assert mc.main(["--root", str(previews)]) == 2                      # no key: says where it runs
