"""Multi-agent LLM analysis: YouTube context, risk/sector/adversarial agents, synthesis, note payload."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import anthropic
from pydantic import ValidationError

from pipeline_common import (
    _log, PROMPTS_DIR, REPO_ROOT, ACCURACY_JSON, POSITIONS_CSV, next_review_date, AnalysisOutput,
    AssetPrediction,
    PortfolioRiskOutput, SectorOpportunityOutput, _STRUCTURED_OUTPUT_AVAILABLE,
)
from pipeline_config import (
    run_config, main_model, _render_prompt, load_accuracy_context,
)
from market_data import (
    compute_technicals, format_technicals_block, _TECHNICAL_ASSETS,
    fetch_cot_data, fetch_sector_fundamentals,
)
from calendar_events import fetch_upcoming_events


# ---------------------------------------------------------------------------
# YouTube channel configuration
# Each entry: (channel_id, display_name)
# Run: python .macro-assist/youtube_data.py --resolve <channel_url>
# to find the channel ID for any channel.
# ---------------------------------------------------------------------------

YOUTUBE_CHANNELS = [
    ("UCOHxDwCcOzBaLkeTazanwcw", "Bravos Research"),
]


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

TRANSCRIPT_SUMMARY_PROMPT = """\
Extract the 6-8 most important macro-relevant insights from this analyst video transcript.

Focus exclusively on:
- Specific data points and market levels cited (include the numbers)
- Cause-and-effect arguments about macro dynamics
- Forward-looking implications for bonds, equities, commodities, or Fed policy

Ignore completely: stock picks, fund promotions, subscription pitches, calls to action.

Format as a concise bullet list. Be specific — keep every number mentioned.\
"""


def summarize_transcript(client: anthropic.Anthropic, title: str, transcript: str) -> str:
    """Use Claude Haiku to extract macro signal from a raw transcript."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"Video title: {title}\n\nTranscript:\n{transcript}",
        }],
        system=TRANSCRIPT_SUMMARY_PROMPT,
    )
    return response.content[0].text.strip()


def fetch_youtube_context(client: anthropic.Anthropic) -> str:
    """
    Fetch recent transcripts from configured channels, summarize each with Haiku,
    and return a formatted context block. Returns empty string if nothing found.
    """
    from youtube_data import get_recent_transcripts
    blocks = []

    for channel_id, channel_name in YOUTUBE_CHANNELS:
        videos = get_recent_transcripts(channel_id)

        if not videos:
            _log("YOUTUBE", "INFO", f"{channel_name}: no new videos (last 36h)")
            continue

        _log("YOUTUBE", "INFO", f"{channel_name}: {len(videos)} video(s) found, summarizing...")
        for video in videos:
            summary = summarize_transcript(client, video["title"], video["transcript"])
            blocks.append(
                f"### {channel_name}: \"{video['title']}\"\n"
                f"*Published: {video['published'][:10]} | {video['url']}*\n\n"
                f"{summary}"
            )

    if not blocks:
        return ""

    _log("YOUTUBE", "OK", f"{len(blocks)} video summary/summaries added")
    header = "## Analyst Video Insights"
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


def _build_immutable_anchors(fred_data: dict, market_data: dict) -> dict:
    """Extract live numerical values that Pass 2 must not alter."""
    anchors: dict = {}
    for key, label in [
        ("real_yield_10y", "10Y Real Yield"),
        ("breakeven_10y",  "10Y Breakeven"),
        ("treasury_10y",   "10Y Treasury Yield"),
        ("treasury_2y",    "2Y Treasury Yield"),
        ("fed_funds_rate", "Fed Funds Rate"),
        ("hy_spread",      "HY Spread"),
    ]:
        entry = fred_data.get(key)
        if entry and "value" in entry:
            anchors[label] = f"{entry['value']}%"
    cpi_entry = fred_data.get("cpi", {})
    if "yoy_pct" in cpi_entry:
        anchors["CPI YoY"] = f"{cpi_entry['yoy_pct']}%"
    m2_entry = fred_data.get("m2", {})
    if "yoy_pct" in m2_entry:
        anchors["M2 YoY"] = f"{m2_entry['yoy_pct']}%"
    for key, label in [
        ("sp500",   "S&P 500"),
        ("gold",    "Gold"),
        ("wti_oil", "WTI Oil"),
        ("dxy",     "DXY"),
        ("bitcoin", "Bitcoin"),
        ("vix",     "VIX"),
    ]:
        entry = market_data.get(key)
        if entry and "price" in entry:
            anchors[label] = entry["price"]
    return anchors


_ADVERSARIAL_PROMPT = """\
Adversarial prediction review — return JSON ONLY.

Read the Key Risks & Themes and 5-Day Predictions sections in the report.

For each asset, decide: would a listed Key Risk make the directional call OUTRIGHT WRONG if it materialised?
HIGH bar: only flag when a risk directly negates the direction entirely — not merely adds uncertainty.

Rules:
- "append_risk": "[Risk: 2-3 word label]" to add to Primary Driver for Bullish/Bearish calls only. null otherwise.
- "confidence_delta": -5 or -10 when a risk directly contradicts the directional call. 0 for everything else.
  Do NOT apply a delta to Neutral calls. Do NOT apply a delta that would push below 51% for a directional call.
- Do NOT reference, restate, invent, or modify any numbers, accuracy stats, prices, or percentages.

Return ONLY this JSON structure — no text outside it:
{
  "S&P 500": {"append_risk": null, "confidence_delta": 0},
  "Gold": {"append_risk": null, "confidence_delta": 0},
  "WTI Oil": {"append_risk": null, "confidence_delta": 0},
  "10Y Treasury Yield": {"append_risk": null, "confidence_delta": 0},
  "DXY": {"append_risk": null, "confidence_delta": 0},
  "Bitcoin (proxy for crypto risk)": {"append_risk": null, "confidence_delta": 0}
}
"""

_RISK_AGENT_SYSTEM = """\
You are a portfolio risk analyst. You will receive the current macro regime label and a \
portfolio positions table. Submit your assessment via the submit_risk_assessment tool.

Rules:
- Use actual position names and P&L figures from the table. Do not generalise.
- biggest_headwind: the one position or cluster most exposed to the current macro regime. \
Name the position, its P&L, and the specific risk factor.
- biggest_tailwind: the one position best aligned with current conditions. Name it and why.
- actionable: one specific risk-management consideration (trim / hedge / watch level). \
Not a buy/sell recommendation. Plain prose, no bullet prefix.
- opportunity_gap: one asset class, sector, or instrument not in the portfolio that the \
current regime favours. Name it specifically. One-line macro rationale. State whether it \
would reduce or add portfolio concentration risk.\
"""

_SECTOR_AGENT_SYSTEM = """\
You are a sector equity research analyst. You receive a macro intelligence summary \
produced by a separate analyst today — accept it as given. Map it to 2–3 sector ETFs \
with a genuine structural tailwind. Submit via the submit_sector_opportunity tool.

Rules:
- macro_driver: name the specific data point from the macro analysis (e.g. "real yield \
2.09% restrictive — compresses growth multiples, favours value/dividend sectors"). \
Do not repeat the regime label alone.
- valuation_context: cite the trailing P/E, reference P/E, and the flag from the table \
(e.g. "17.2x vs 19x ref — Near avg").
- timing_note (optional): note if 1-month return vs SPX is strongly negative (mean-reversion \
candidate) or strongly positive (crowding risk). Omit if unremarkable.
- research_candidates: only if the sector P/E is flagged "Below avg" — name 1–2 tickers \
from the provided holdings table. Never name tickers not in that table.
- Do not use the word "undervalued" without citing P/E figures.
- If no sector has a genuine macro-grounded tailwind, produce one minimal call and explain \
in regime_note.\
"""

_STRUCTURED_SUCCESS_FILE = ACCURACY_JSON.parent / "structured_success_count.json"
_SYNTHESIS_ACTIVATE_AFTER = 5  # log free-text path retirement suggestion after N successes


def adversarial_review(
    client: anthropic.Anthropic,
    draft_analysis: str,
    immutable_anchors: dict | None = None,  # retained for API compatibility
) -> str:
    """
    Second Claude pass: outputs a JSON delta {asset: {append_risk, confidence_delta}}.
    Python applies the changes programmatically — numbers in the Primary Driver are
    never touched by the model, eliminating autoregressive drift/hallucination.
    Directional calls (Bullish/Bearish) are clamped to ≥51% confidence.
    """
    table_pattern = r'(\| Asset \| Bias \| Primary Driver \| Confidence \| Target Range \|.*?\n(?:\|[^\n]+\n)+)'
    match = re.search(table_pattern, draft_analysis, re.DOTALL)
    if not match:
        _log("REVIEW", "WARN", "could not locate predictions table — skipping adversarial review")
        return draft_analysis

    original_table = match.group(1)

    response = client.messages.create(
        model=main_model(),
        max_tokens=250,
        messages=[{"role": "user", "content": f"{_ADVERSARIAL_PROMPT}\n\nREPORT:\n{draft_analysis}"}],
    )
    raw_output = response.content[0].text.strip()

    try:
        json_match = re.search(r'\{[\s\S]+\}', raw_output)
        if not json_match:
            raise ValueError("no JSON object found")
        revisions = json.loads(json_match.group(0))
    except Exception as e:
        _log("REVIEW", "WARN", f"could not parse adversarial JSON ({e}) — using original table")
        return draft_analysis

    modified_table = _apply_adversarial_revisions(original_table, revisions)
    _log_adversarial_diff(original_table, modified_table)
    return draft_analysis[:match.start()] + modified_table + draft_analysis[match.end():]


def _apply_adversarial_revisions(table: str, revisions: dict) -> str:
    """Apply adversarial JSON deltas to the predictions table rows.
    Column order: Asset | Bias | Primary Driver | Confidence | Target Range
    Directional (Bullish/Bearish) confidence is clamped to [51%, 70%].
    """
    lines = table.rstrip("\n").split("\n")
    result = []
    for line in lines:
        if not line.startswith("|") or "---" in line or "Asset" in line:
            result.append(line)
            continue
        cells = line.split("|")
        if len(cells) < 6:
            result.append(line)
            continue
        asset  = cells[1].strip()
        bias   = cells[2].strip().lower()
        is_dir = bias in ("bullish", "bearish")
        # Column indices for new order: [0]="" [1]=Asset [2]=Bias [3]=PD [4]=Conf [5]=TR [6]=""
        pd_col, conf_col = 3, 4

        rev = next(
            (v for k, v in revisions.items()
             if k.lower() in asset.lower() or asset.lower() in k.lower()),
            None,
        )
        if rev is None:
            result.append(line)
            continue

        # Apply confidence delta
        conf_str = cells[conf_col].strip().rstrip("%").strip()
        try:
            conf_val = int(conf_str)
        except ValueError:
            result.append(line)
            continue
        delta    = int(rev.get("confidence_delta", 0) or 0)
        new_conf = conf_val + delta
        if is_dir:
            new_conf = max(51, min(70, new_conf))  # directional calls: never below 51%
        # Neutral calls stay unchanged (50%)

        cells[conf_col] = f" {new_conf}% "

        # Append risk tag to Primary Driver (never replace — append only)
        risk_tag = rev.get("append_risk")
        if risk_tag and is_dir:
            driver = cells[pd_col].strip()
            if risk_tag not in driver:
                cells[pd_col] = f" {driver} {risk_tag} "

        result.append("|".join(cells))
    return "\n".join(result)


def _log_adversarial_diff(original: str, revised: str) -> None:
    """Print a compact diff of what the adversarial pass changed."""
    orig_rows  = [r.strip() for r in original.strip().splitlines() if r.startswith("|") and "---" not in r]
    rev_rows   = [r.strip() for r in revised.strip().splitlines() if r.startswith("|") and "---" not in r]

    # Skip header row (first row)
    orig_data = orig_rows[1:]
    rev_data  = rev_rows[1:] if len(rev_rows) > 1 else rev_rows

    changes = 0
    for orig_row, rev_row in zip(orig_data, rev_data):
        if orig_row == rev_row:
            continue
        orig_cells = [c.strip() for c in orig_row.split("|")[1:-1]]
        rev_cells  = [c.strip() for c in rev_row.split("|")[1:-1]]
        asset = orig_cells[0] if orig_cells else "?"
        diffs = []
        labels = ["Bias", "Primary Driver", "Confidence", "Target Range"]
        for label, o, r in zip(labels, orig_cells[1:], rev_cells[1:]):
            if o != r:
                diffs.append(f"  {label}: {o!r} -> {r!r}")
        if diffs:
            _log("REVIEW", "WARN", f"{asset} revised:")
            for d in diffs:
                _log("REVIEW", "INFO", f"  {d.strip()}")
            changes += 1

    if changes == 0:
        _log("REVIEW", "OK", "no predictions revised")
    else:
        _log("REVIEW", "WARN", f"{changes} prediction(s) revised")


def _adversarial_review_structured(
    client: anthropic.Anthropic,
    output: "AnalysisOutput",
) -> "AnalysisOutput":
    """
    Adversarial calibration pass for the structured path (MA-2).
    Receives only predictions + key_risks — not the full prose — to avoid
    the model reading back its own reasoning and rubber-stamping it.
    Returns an updated AnalysisOutput with confidence deltas and risk tags applied.
    """
    pred_rows = "\n".join(
        f"| {p.asset} | {p.bias} | {p.primary_driver} | {p.confidence_pct}% | {p.target_range} |"
        for p in output.predictions
    )
    pred_table = (
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        "|-------|------|----------------|------------|-------------|\n"
        + pred_rows + "\n"
    )
    risks_text = "\n".join(f"- {r}" for r in output.key_risks)
    context = f"## Key Risks\n{risks_text}\n\n## 5-Day Predictions\n{pred_table}"

    response = client.messages.create(
        model=main_model(),
        max_tokens=250,
        messages=[{"role": "user", "content": f"{_ADVERSARIAL_PROMPT}\n\nREPORT:\n{context}"}],
    )
    raw_output = response.content[0].text.strip()

    try:
        json_match = re.search(r'\{[\s\S]+\}', raw_output)
        if not json_match:
            raise ValueError("no JSON object found")
        revisions = json.loads(json_match.group(0))
    except Exception as e:
        _log("REVIEW", "WARN", f"could not parse adversarial JSON ({e}) — using original predictions")
        return output

    new_predictions = []
    for p in output.predictions:
        rev = next(
            (v for k, v in revisions.items()
             if k.lower() in p.asset.lower() or p.asset.lower() in k.lower()),
            None,
        )
        if rev is None or p.bias == "Neutral":
            new_predictions.append(p)
            continue

        delta    = int(rev.get("confidence_delta", 0) or 0)
        new_conf = max(51, min(70, p.confidence_pct + delta))

        new_driver = p.primary_driver
        risk_tag   = rev.get("append_risk")
        if risk_tag and risk_tag not in new_driver:
            candidate = f"{new_driver} {risk_tag}"
            _pd_max = AssetPrediction.model_json_schema()["properties"]["primary_driver"].get("maxLength", 800)
            new_driver = candidate[:_pd_max - 3] + "..." if len(candidate) > _pd_max else candidate

        new_predictions.append(p.model_copy(update={
            "confidence_pct": new_conf,
            "primary_driver": new_driver,
        }))

    # Reuse the free-text diff logger via reconstructed table strings
    revised_rows = "\n".join(
        f"| {p.asset} | {p.bias} | {p.primary_driver} | {p.confidence_pct}% | {p.target_range} |"
        for p in new_predictions
    )
    revised_table = (
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        "|-------|------|----------------|------------|-------------|\n"
        + revised_rows + "\n"
    )
    _log_adversarial_diff(pred_table, revised_table)

    return output.model_copy(update={"predictions": new_predictions})


def _run_risk_agent(
    client: anthropic.Anthropic,
    macro_regime: str,
    portfolio_context: str,
) -> "PortfolioRiskOutput | None":
    """MA-3a: Haiku portfolio risk agent.
    Narrow context — only macro_regime + positions. No FRED data, no accuracy history.
    Returns None on any failure so the caller can silently omit portfolio_risk.
    One multi-turn correction retry on ValidationError — sends the error back to the model.
    """
    if not portfolio_context or not _STRUCTURED_OUTPUT_AVAILABLE:
        return None
    schema = PortfolioRiskOutput.model_json_schema()
    tools = [{
        "name": "submit_risk_assessment",
        "description": "Submit the structured portfolio risk assessment.",
        "input_schema": schema,
    }]
    messages: list = [{"role": "user", "content": f"## Current Macro Regime\n{macro_regime}\n\n{portfolio_context}"}]
    try:
        for attempt in range(2):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system=_RISK_AGENT_SYSTEM,
                tools=tools,
                tool_choice={"type": "tool", "name": "submit_risk_assessment"},
                messages=messages,
            )
            tool_block = next(
                (b for b in response.content
                 if b.type == "tool_use" and b.name == "submit_risk_assessment"),
                None,
            )
            if tool_block is None:
                raise ValueError("no submit_risk_assessment block in response")
            try:
                result = PortfolioRiskOutput.model_validate(tool_block.input)
                suffix = f" (attempt {attempt + 1})" if attempt > 0 else ""
                _log("RISK", "OK", f"portfolio risk assessed ({response.usage.output_tokens} tokens, Haiku){suffix}")
                return result
            except ValidationError as ve:
                if attempt == 1:
                    raise
                errs = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in ve.errors())
                messages += [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_block.id,
                                                   "content": f"Validation failed — {errs}. Please resubmit with shorter text in those fields."}]},
                ]
    except Exception as e:
        _log("RISK", "WARN", f"risk agent failed ({type(e).__name__}: {e}) — portfolio_risk omitted")
    return None


def _format_portfolio_risk(risk: "PortfolioRiskOutput") -> str:
    """Format PortfolioRiskOutput into the 4-bullet string expected by _build_analysis_markdown."""
    return (
        f"- **Biggest headwind**: {risk.biggest_headwind}\n"
        f"- **Biggest tailwind**: {risk.biggest_tailwind}\n"
        f"- **One actionable observation**: {risk.actionable}\n"
        f"- **Opportunity gap**: {risk.opportunity_gap}"
    )


def _run_sector_agent(
    client: anthropic.Anthropic,
    structured: "AnalysisOutput",
    sector_fundamentals_block: str,
) -> "SectorOpportunityOutput | None":
    """MA-3c: Haiku sector opportunity agent.
    Receives MA-1's synthesized macro conclusions + sector ETF fundamentals.
    The agent never sees raw FRED data — it reasons from MA-1's interpretation.
    Returns None on any failure so the caller can silently omit sector_opportunity.
    One multi-turn correction retry on ValidationError — sends the error back to the model.
    """
    if not sector_fundamentals_block or not _STRUCTURED_OUTPUT_AVAILABLE:
        return None
    schema = SectorOpportunityOutput.model_json_schema()
    tools = [{
        "name": "submit_sector_opportunity",
        "description": "Submit the structured sector opportunity analysis.",
        "input_schema": schema,
    }]
    risks_md = "\n".join(f"- {r}" for r in structured.key_risks)
    user_msg = (
        f"## Macro Interpretation (from today's analysis)\n"
        f"**Regime**: {structured.macro_regime}\n\n"
        f"**Equities**: {structured.equities_note}\n\n"
        f"**Rates & Fed Policy**: {structured.rates_note}\n\n"
        f"**Inflation & Growth**: {structured.inflation_growth_note}\n\n"
        f"**Key Risks**:\n{risks_md}\n\n"
        f"{sector_fundamentals_block}"
    )
    messages: list = [{"role": "user", "content": user_msg}]
    try:
        for attempt in range(2):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                system=_SECTOR_AGENT_SYSTEM,
                tools=tools,
                tool_choice={"type": "tool", "name": "submit_sector_opportunity"},
                messages=messages,
            )
            tool_block = next(
                (b for b in response.content
                 if b.type == "tool_use" and b.name == "submit_sector_opportunity"),
                None,
            )
            if tool_block is None:
                raise ValueError("no submit_sector_opportunity block in response")
            try:
                result = SectorOpportunityOutput.model_validate(tool_block.input)
                n_calls = len(result.calls)
                suffix = f" (attempt {attempt + 1})" if attempt > 0 else ""
                _log("SECTOR", "OK", f"{n_calls} sector call(s) ({response.usage.output_tokens} tokens, Haiku){suffix}")
                return result
            except ValidationError as ve:
                if attempt == 1:
                    raise
                errs = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in ve.errors())
                messages += [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_block.id,
                                                   "content": f"Validation failed — {errs}. Please resubmit with shorter text in those fields."}]},
                ]
    except Exception as e:
        _log("SECTOR", "WARN", f"sector agent failed ({type(e).__name__}: {e}) — sector_opportunity omitted")
    return None


def _format_sector_opportunity(output: "SectorOpportunityOutput") -> str:
    """Format SectorOpportunityOutput into the markdown string stored in sector_opportunity."""
    parts = []
    for call in output.calls:
        lines = [f"**{call.etf_ticker} — {call.sector_name}**"]
        lines.append(call.macro_driver)
        lines.append(f"Valuation: {call.valuation_context}")
        if call.timing_note:
            lines.append(f"Timing: {call.timing_note}")
        if call.research_candidates:
            tickers = ", ".join(call.research_candidates)
            lines.append(
                f"Research candidates (not a recommendation — verify independently): {tickers}"
            )
        parts.append("\n".join(lines))
    result = "\n\n".join(parts)
    if output.regime_note:
        result = f"{result}\n\n*{output.regime_note}*"
    return result


def _synthesize_structured(
    client: anthropic.Anthropic,
    output: "AnalysisOutput",
    today: datetime,
) -> str | None:
    """MA-3b: Synthesis agent — formats AnalysisOutput into the analysis body markdown.
    Returns the markdown string on success; None on any failure (caller uses Python assembly).
    Uses Sonnet with a tight ~15-line system prompt — no raw data in context.
    """
    synthesis_prompt_path = PROMPTS_DIR / "synthesis_prompt.md"
    if not synthesis_prompt_path.exists():
        _log("MA3B", "WARN", "synthesis_prompt.md not found — skipping")
        return None

    review_date = next_review_date(today)

    # Pre-format the predictions table in Python so the agent copies it verbatim
    pred_header = (
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        "|-------|------|----------------|------------|--------------|"
    )
    pred_rows = "\n".join(
        f"| {p.asset} | {p.bias} | {p.primary_driver} | {p.confidence_pct}% | {p.target_range} |"
        for p in output.predictions
    )
    predictions_table = f"{pred_header}\n{pred_rows}"

    input_data = {
        "executive_summary":     output.executive_summary,
        "macro_regime":          output.macro_regime,
        "macro_dashboard_text":  output.macro_dashboard_text,
        "equities_note":         output.equities_note,
        "rates_note":            output.rates_note,
        "inflation_growth_note": output.inflation_growth_note,
        "commodities_note":      output.commodities_note,
        "portfolio_risk":        output.portfolio_risk,
        "sector_opportunity":    output.sector_opportunity,
        "key_risks":             output.key_risks,
        "predictions_table":     predictions_table,
        "review_date":           review_date,
    }

    system_prompt = synthesis_prompt_path.read_text(encoding="utf-8")
    user_message = (
        "Format this structured analysis into the Macro Intelligence Note body:\n\n"
        + json.dumps(input_data, indent=2)
    )

    _SYNTHESIS_MAX_TOKENS = 5000
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=_SYNTHESIS_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        used = response.usage.output_tokens
        if used >= _SYNTHESIS_MAX_TOKENS:
            _log("MA3B", "WARN",
                 f"synthesis truncated at token ceiling ({used} tokens) — falling back to Python assembly")
            return None
        result = response.content[0].text.strip()
        # Haiku sometimes appends a spurious `\` after the last pipe on the
        # table separator row (e.g. `|--------------|\`).  Strip it so the
        # markdown table renders correctly.
        result = re.sub(r'^(\|[-| ]+)\\\s*$', r'\1', result, flags=re.MULTILINE)
        _log("MA3B", "OK", f"synthesis complete ({used} tokens)")
        return result
    except Exception as e:
        _log("MA3B", "WARN", f"synthesis agent failed ({type(e).__name__}: {e}) — will use Python assembly")
        return None


def _track_structured_success() -> int:
    """Increment and return the consecutive structured-path success count."""
    try:
        data = (
            json.loads(_STRUCTURED_SUCCESS_FILE.read_text(encoding="utf-8"))
            if _STRUCTURED_SUCCESS_FILE.exists()
            else {"count": 0}
        )
    except Exception:
        data = {"count": 0}
    data["count"] = data.get("count", 0) + 1
    try:
        _STRUCTURED_SUCCESS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
    return data["count"]


def _reset_structured_success() -> None:
    """Reset count when the pipeline falls back to the free-text path."""
    try:
        _STRUCTURED_SUCCESS_FILE.write_text(json.dumps({"count": 0}), encoding="utf-8")
    except Exception:
        pass


_BULLISH_CONTRADICTIONS = frozenset({"fade", "fade the", "short ", "expect decline"})
_BEARISH_CONTRADICTIONS = frozenset({"short squeeze", "relief rally", "buy the dip"})


def _check_prediction_consistency(analysis: str) -> None:
    """Log a WARN when Bias and Primary Driver text directly contradict each other."""
    match = re.search(
        r'\| Asset \| Bias \| Primary Driver \|.*?\n(?:\|[^\n]+\n)+', analysis, re.DOTALL
    )
    if not match:
        return
    for line in match.group(0).splitlines():
        if not line.startswith("|") or "---" in line or "Asset" in line:
            continue
        cells = line.split("|")
        if len(cells) < 5:
            continue
        asset  = cells[1].strip()
        bias   = cells[2].strip().lower()
        driver = cells[3].strip().lower()
        if bias == "bullish" and any(w in driver for w in _BULLISH_CONTRADICTIONS):
            _log("VALIDATE", "WARN", f"{asset}: Bullish bias contradicted by driver text (contains fade/short language)")
        elif bias == "bearish" and any(w in driver for w in _BEARISH_CONTRADICTIONS):
            _log("VALIDATE", "WARN", f"{asset}: Bearish bias contradicted by driver text (contains squeeze/rally language)")


def _apply_accuracy_override(analysis: str) -> str:
    """
    Code-level bias correction applied after adversarial review.

    Two passes:
    1. BIAS FLOOR: if an asset's directional accuracy is <40% at n>=8 in ANY window
       and the current prediction is Bearish, floor confidence at 50% and annotate.
       Direction is kept (scoreable) so stats can recover naturally.
    2. WASTED SIGNAL WARNING: if an asset has ≥70% directional accuracy at n≥10
       in its best window but the current call is Neutral at 50%, log a warning so
       it is visible in CI output. (Prompt rules handle the fix; this makes it auditable.)
    """
    _check_prediction_consistency(analysis)

    if not ACCURACY_JSON.exists():
        _log("OVERRIDE", "INFO", "no accuracy data — skipping")
        return analysis
    try:
        acc_data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return analysis

    all_windows = acc_data.get("windows", {})
    if not all_windows:
        return analysis

    table_pattern = r'(\| Asset \| Bias \| Primary Driver \| Confidence \| Target Range \|.*?\n(?:\|[^\n]+\n)+)'
    match = re.search(table_pattern, analysis, re.DOTALL)
    if not match:
        _log("OVERRIDE", "WARN", "could not locate predictions table")
        return analysis

    table    = match.group(0)
    modified = table
    overrides = 0

    # Build per-asset: worst bias window and best signal window
    all_assets: set[str] = set()
    for wdata in all_windows.values():
        all_assets.update(wdata.get("by_asset", {}).keys())

    for asset in all_assets:
        # --- Pass 1: bias floor (any window <40% at n≥8, Bearish call) ---
        worst_dacc, worst_wkey, worst_n = None, None, 0
        for wkey, wdata in all_windows.items():
            astat = wdata.get("by_asset", {}).get(asset, {})
            dacc  = astat.get("directional_acc")
            dn    = astat.get("directional_n", 0)
            if dacc is None or dn < 8:
                continue
            if worst_dacc is None or dacc < worst_dacc:
                worst_dacc, worst_wkey, worst_n = dacc, wkey, dn

        if worst_dacc is not None and worst_dacc < 0.40:
            row_pat   = re.compile(
                rf'(\|\s*{re.escape(asset)}\s*\|\s*)Bearish(\s*\|[^\n]+\n)',
                re.IGNORECASE,
            )
            row_match = row_pat.search(modified)
            if row_match:
                original_row = row_match.group(0)
                cells = original_row.rstrip("\n").split("|")
                if len(cells) >= 6:
                    cells[4] = " 51% "   # 51% not 50%: directional calls must be ≥51% to distinguish from Neutral
                    cells[3] = (
                        f" {cells[3].strip()} "
                        f"[Caution: {worst_wkey.upper()} Bearish dir. acc. {worst_dacc:.0%} n={worst_n} — historical bias] "
                    )
                    new_row  = "|".join(cells) + "\n"
                    modified = modified.replace(original_row, new_row, 1)
                    _log("OVERRIDE", "WARN",
                         f"{asset}: confidence floored ({worst_wkey.upper()} Bearish {worst_dacc:.0%}, n={worst_n})")
                    overrides += 1

        # --- Pass 2: wasted signal warning (best window ≥70% at n≥10, Neutral call) ---
        best_dacc, best_wkey, best_n = None, None, 0
        for wkey in reversed(list(all_windows.keys())):   # prefer longer horizon on tie
            wdata = all_windows[wkey]
            astat = wdata.get("by_asset", {}).get(asset, {})
            dacc  = astat.get("directional_acc")
            dn    = astat.get("directional_n", 0)
            if dacc is None or dn < 10:
                continue
            if best_dacc is None or dacc > best_dacc:
                best_dacc, best_wkey, best_n = dacc, wkey, dn

        if best_dacc is not None and best_dacc >= 0.70:
            neutral_pat = re.compile(
                rf'\|\s*{re.escape(asset)}\s*\|\s*Neutral\s*\|[^\|]+\|\s*50%\s*\|',
                re.IGNORECASE,
            )
            if neutral_pat.search(modified):
                _log("OVERRIDE", "WARN",
                     f"{asset}: Neutral@50% called despite {best_wkey.upper()} dir. acc. "
                     f"{best_dacc:.0%} (n={best_n}) — check prompt compliance")

    # --- Pass 3: confidence clustering and directional@50 check ---
    data_rows = [
        line for line in modified.splitlines()
        if line.startswith("|") and "---" not in line and "Asset" not in line
    ]
    directional_conf_counts: dict[str, int] = {}
    directional_at_50 = 0
    bias_values: list[str] = []
    for row in data_rows:
        cells = row.split("|")
        if len(cells) < 6:
            continue
        bias = cells[2].strip().lower()
        conf = cells[4].strip().rstrip("%").strip()
        if bias:
            bias_values.append(bias)
        # Only count directional calls for clustering — Neutral@50% is structurally expected
        if conf and bias in ("bullish", "bearish"):
            directional_conf_counts[conf] = directional_conf_counts.get(conf, 0) + 1
            if conf == "50":
                directional_at_50 += 1

    for conf_val, count in directional_conf_counts.items():
        if count >= 3:
            _log("OVERRIDE", "WARN",
                 f"confidence clustering: {count} directional calls at {conf_val}% — insufficient differentiation")
    if directional_at_50 >= 2:
        _log("OVERRIDE", "WARN",
             f"{directional_at_50} directional (Bullish/Bearish) calls at 50% — indistinguishable from Neutral; min 51%")

    # --- Pass 4: all-Neutral collapse ---
    directional_calls = [b for b in bias_values if b not in ("neutral", "")]
    if bias_values and not directional_calls:
        _log("OVERRIDE", "FAIL", "all-Neutral prediction table — minimum conviction rule violated")

    if overrides == 0:
        _log("OVERRIDE", "OK", "no accuracy-based overrides applied")
        return analysis

    return analysis[: match.start()] + modified + analysis[match.end():]


_ARTIFACT_PATTERNS = [
    re.compile(r'\*?Maximum \d+ words[^\n]*\*?', re.IGNORECASE),
    re.compile(r'\*?[Ss]ection complete\.?\*?', re.IGNORECASE),
    re.compile(r'\*?Token budget[^\n]*\*?', re.IGNORECASE),
]


def _scrub_prompt_artifacts(text: str) -> str:
    """Strip instruction text that the model echoed verbatim into its output."""
    for pattern in _ARTIFACT_PATTERNS:
        text = pattern.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', text)


def _build_analysis_markdown(output: "AnalysisOutput", today: datetime) -> str:
    """Assemble the analysis section markdown from a structured AnalysisOutput.
    Python owns the section order — the model never writes headings or constraints.
    """
    parts: list[str] = []

    parts.append(f"### Executive Summary\n\n{output.executive_summary}")

    if output.macro_dashboard_text:
        parts.append(f"### Macro Dashboard\n\n{output.macro_dashboard_text}")

    parts.append(f"### Equities\n\n{output.equities_note}")
    parts.append(f"### Rates & Fed Policy\n\n{output.rates_note}")
    parts.append(f"### Inflation & Growth\n\n{output.inflation_growth_note}")
    parts.append(f"### Commodities\n\n{output.commodities_note}")

    if output.portfolio_risk:
        parts.append(f"### Portfolio Risk Assessment\n\n{output.portfolio_risk}")

    if output.sector_opportunity:
        parts.append(f"### Sector Opportunity Research\n\n{output.sector_opportunity}")

    risks_md = "\n".join(f"- {r}" for r in output.key_risks)
    parts.append(f"### Key Risks & Themes\n\n{risks_md}")

    review_date = next_review_date(today)
    table_header = (
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        "|-------|------|----------------|------------|--------------|"
    )
    table_rows = "\n".join(
        f"| {p.asset} | {p.bias} | {p.primary_driver} | {p.confidence_pct}% | {p.target_range} |"
        for p in output.predictions
    )
    parts.append(
        f"### 5-Day Predictions\n\n{table_header}\n{table_rows}\n\nReview date: {review_date}"
    )

    return "\n\n".join(parts)


def _apply_accuracy_override_structured(output: "AnalysisOutput") -> "AnalysisOutput":
    """Accuracy-based bias corrections applied directly to AnalysisOutput.predictions.
    Structured equivalent of _apply_accuracy_override() — no regex, operates on typed fields.
    """
    _pred_table_text = (
        "| Asset | Bias | Primary Driver | Confidence | Target Range |\n"
        + "\n".join(
            f"| {p.asset} | {p.bias} | {p.primary_driver} | {p.confidence_pct}% | {p.target_range} |"
            for p in output.predictions
        )
        + "\n"
    )
    _check_prediction_consistency(_pred_table_text)

    if not ACCURACY_JSON.exists():
        _log("OVERRIDE", "INFO", "no accuracy data — skipping")
        return output
    try:
        acc_data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return output

    # Prefer feedback_windows (version-filtered, >= MIN_FEEDBACK_VERSION) when available;
    # fall back to windows so behaviour is unchanged before the next summarize run.
    all_windows = acc_data.get("feedback_windows") or acc_data.get("windows", {})
    if not all_windows:
        return output

    new_predictions: list["AssetPrediction"] = []
    for pred in output.predictions:
        asset = pred.asset

        # Pass 1: bias floor — <40% Bearish directional accuracy in any window
        worst_dacc, worst_wkey, worst_n = None, None, 0
        for wkey, wdata in all_windows.items():
            astat = wdata.get("by_asset", {}).get(asset, {})
            dacc  = astat.get("directional_acc")
            dn    = astat.get("directional_n", 0)
            if dacc is None or dn < 8:
                continue
            if worst_dacc is None or dacc < worst_dacc:
                worst_dacc, worst_wkey, worst_n = dacc, wkey, dn

        if worst_dacc is not None and worst_dacc < 0.40 and pred.bias == "Bearish":
            note = (
                f" [Caution: {worst_wkey.upper()} Bearish dir. acc. "
                f"{worst_dacc:.0%} n={worst_n} — historical bias]"
            )
            pred = pred.model_copy(update={
                "confidence_pct": 51,
                "primary_driver": (pred.primary_driver + note)[:350],
            })
            _log("OVERRIDE", "WARN",
                 f"{asset}: confidence floored ({worst_wkey.upper()} Bearish {worst_dacc:.0%}, n={worst_n})")

        # Pass 2: wasted-signal warning — ≥70% best-window, Neutral@50%
        best_dacc, best_wkey, best_n = None, None, 0
        for wkey in reversed(list(all_windows.keys())):
            astat = all_windows[wkey].get("by_asset", {}).get(asset, {})
            dacc  = astat.get("directional_acc")
            dn    = astat.get("directional_n", 0)
            if dacc is None or dn < 10:
                continue
            if best_dacc is None or dacc > best_dacc:
                best_dacc, best_wkey, best_n = dacc, wkey, dn

        if best_dacc is not None and best_dacc >= 0.70 and pred.bias == "Neutral" and pred.confidence_pct == 50:
            _log("OVERRIDE", "WARN",
                 f"{asset}: Neutral@50% despite {best_wkey.upper()} dir. acc. "
                 f"{best_dacc:.0%} (n={best_n}) — check prompt compliance")

        new_predictions.append(pred)

    # Pass 3: clustering + all-Neutral checks
    dir_conf_counts: dict[str, int] = {}
    dir_at_50 = 0
    bias_values = [p.bias for p in new_predictions]
    for p in new_predictions:
        if p.bias in ("Bullish", "Bearish"):
            key = str(p.confidence_pct)
            dir_conf_counts[key] = dir_conf_counts.get(key, 0) + 1
            if p.confidence_pct == 50:
                dir_at_50 += 1

    for conf_val, count in dir_conf_counts.items():
        if count >= 3:
            _log("OVERRIDE", "WARN",
                 f"confidence clustering: {count} directional calls at {conf_val}%")
    if dir_at_50 >= 2:
        _log("OVERRIDE", "WARN", f"{dir_at_50} directional calls at 50% — min 51%")

    if bias_values and not [b for b in bias_values if b != "Neutral"]:
        _log("OVERRIDE", "FAIL", "all-Neutral prediction table — minimum conviction rule violated")

    return output.model_copy(update={"predictions": new_predictions})


def _analyze_structured(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_message: str,
) -> "AnalysisOutput | None":
    """Try structured output via Anthropic tool_use.
    Returns validated AnalysisOutput on success, None after two failed attempts.
    Zero-downtime: caller falls back to free-text path on None.
    """
    schema = AnalysisOutput.model_json_schema()
    tools = [{
        "name": "submit_analysis",
        "description": (
            "Submit the structured macro analysis. "
            "Fill all required fields from today's FRED and market data."
        ),
        "input_schema": schema,
    }]

    messages: list[dict] = [{"role": "user", "content": user_message}]
    last_response = None

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=main_model(),
                max_tokens=5000,
                system=system_prompt,
                tools=tools,
                tool_choice={"type": "tool", "name": "submit_analysis"},
                messages=messages,
            )
            last_response = response

            tool_block = next(
                (b for b in response.content
                 if b.type == "tool_use" and b.name == "submit_analysis"),
                None,
            )
            if tool_block is None:
                raise ValueError("no submit_analysis tool_use block in response")

            result = AnalysisOutput.model_validate(tool_block.input)
            _log("CLAUDE", "OK",
                 f"structured output validated ({response.usage.output_tokens} tokens)")
            return result

        except Exception as e:
            if attempt == 0 and last_response is not None:
                _log("CLAUDE", "WARN",
                     f"structured attempt 1 failed ({type(e).__name__}: {e}) — retrying")
                # After a tool_use turn the API requires a tool_result, not plain text.
                _retry_tool_block = next(
                    (b for b in last_response.content
                     if b.type == "tool_use" and b.name == "submit_analysis"),
                    None,
                )
                if _retry_tool_block is not None:
                    correction_content: list | str = [
                        {
                            "type": "tool_result",
                            "tool_use_id": _retry_tool_block.id,
                            "content": (
                                f"Your submission failed schema validation:\n{e}\n\n"
                                "Resubmit the COMPLETE analysis via submit_analysis. Fix EVERY "
                                "error above: include all required fields (macro_regime and all "
                                "four *_note fields are mandatory), use the correct type for each "
                                "(key_risks and predictions are LISTS, not prose), and keep each "
                                "text field within its length limit."
                            ),
                            "is_error": True,
                        }
                    ]
                else:
                    correction_content = (
                        f"The previous response had an error:\n{e}\n\n"
                        "Please correct the fields and resubmit via submit_analysis."
                    )
                messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": last_response.content},
                    {"role": "user", "content": correction_content},
                ]
            else:
                _log("CLAUDE", "FAIL",
                     f"structured output failed after {attempt + 1} attempt(s) "
                     f"({type(e).__name__}) — falling back to free-text path")
                return None

    return None


def build_payload_preview(
    user_message_structured: str,
    nonlive_block: str = "",
    system_prompt_chars: int = 0,
    free_text_extras: "dict | None" = None,
    today: "datetime | None" = None,
) -> str:
    """Build a human-readable preview of what the LLM receives, plus withheld signals.

    Returns a markdown document with three parts:
      1. a section-size index (rough picture, scannable),
      2. the verbatim main-analysis payload (structured path — what is live), and
      3. the non-live signals block (computed but withheld from the model).

    `free_text_extras` (optional) names the bits the free-text *fallback* path
    additionally appends (portfolio, accuracy) so the preview is honest about the
    two code paths without dumping their full text.
    """
    date_str = (today or datetime.now()).strftime("%A, %B %d, %Y")

    # Rough index: count lines per top-level "## " section of the live payload.
    sections: list[tuple[str, int, int]] = []
    cur_name, cur_lines, cur_chars = "(preamble)", 0, 0
    for line in user_message_structured.splitlines():
        if line.startswith("## "):
            if cur_lines or cur_chars:
                sections.append((cur_name, cur_lines, cur_chars))
            cur_name, cur_lines, cur_chars = line[3:].strip(), 0, 0
        cur_lines += 1
        cur_chars += len(line) + 1
    sections.append((cur_name, cur_lines, cur_chars))

    index_lines = [f"- {name}: {ln} lines / {ch} chars" for name, ln, ch in sections]
    total_chars = len(user_message_structured)

    _cfg = run_config()
    out: list[str] = [
        f"# LLM Payload Preview — {date_str}",
        "",
        f"Rough picture of the **main analysis agent** input (model `{_cfg['model']}`, "
        f"profile `{_cfg['profile']}`, structured path — the live one). System prompt + the "
        "verbatim user message below, then signals we compute but withhold.",
        "",
        f"- System prompt: ~{system_prompt_chars} chars (`prompts/system_prompt_structured.md`)",
        f"- User message: {total_chars} chars across {len(sections)} section(s)",
        "",
        "## Section index (user message)",
        *index_lines,
    ]
    if free_text_extras:
        extra_names = ", ".join(k for k, v in free_text_extras.items() if v)
        if extra_names:
            out += [
                "",
                f"_Free-text fallback path additionally appends: {extra_names} "
                "(excluded from the live structured path)._",
            ]

    out += [
        "",
        "=" * 72,
        "MAIN ANALYSIS PAYLOAD (verbatim — what the model receives)",
        "=" * 72,
        "",
        user_message_structured,
    ]

    if nonlive_block:
        out += ["", "=" * 72, "", nonlive_block]

    return "\n".join(out)


def analyze_with_claude(
    fred_data: dict,
    market_data: dict,
    today: datetime,
    sector_data: dict | None = None,
    notable_moves: str = "",
    histories: dict | None = None,
    quant_context: str = "",
) -> "str | AnalysisOutput":
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    _cfg = run_config()
    _floor_on = _cfg["conviction_floor"]
    if _cfg["profile"] != "control":
        _log("PROFILE", "INFO",
             f"run profile '{_cfg['profile']}' — model={_cfg['model']}, floor={'on' if _floor_on else 'off'}, "
             f"base_rate_first={_cfg['base_rate_first']}, prune_rules={_cfg['prune_rules']}")
    system_prompt = _render_prompt((PROMPTS_DIR / "system_prompt.md").read_text(), _cfg)

    from parse_positions import get_portfolio_summary, format_portfolio_for_prompt

    review_date      = next_review_date(today)

    accuracy_context = load_accuracy_context(_floor_on)
    if accuracy_context:
        _log("ACCURACY", "OK", "accuracy history loaded")
    else:
        _log("ACCURACY", "INFO", "no accuracy history yet — first run")

    youtube_context = fetch_youtube_context(client)

    events_context = fetch_upcoming_events(today)
    if events_context:
        _n_events = sum(1 for ln in events_context.splitlines() if ln.startswith("- "))
        _log("EVENTS", "OK", f"{_n_events} event(s) in next 7 days")
    else:
        _log("EVENTS", "OK", "no scheduled events in next 7 days")

    portfolio_summary = get_portfolio_summary(str(POSITIONS_CSV))
    portfolio_context = format_portfolio_for_prompt(portfolio_summary) if portfolio_summary else ""
    if portfolio_summary:
        _log("PORTFOLIO", "OK", "portfolio positions loaded")
    else:
        _log("PORTFOLIO", "INFO", "no portfolio data (POSITIONS_CSV absent or empty)")

    technicals_block = ""
    if histories:
        technicals = compute_technicals(histories)
        technicals_block = format_technicals_block(technicals)
        _log("TECHNICALS", "OK", f"{len(technicals)}/{len(_TECHNICAL_ASSETS)} assets computed")

    cot_block = fetch_cot_data()

    sector_block = (
        f"\n\n## Sector ETF Data\n{json.dumps(sector_data, indent=2)}"
        if sector_data else ""
    )

    _log("SECTORS", "INFO", "fetching sector fundamentals...")
    try:
        sector_fundamentals_block = fetch_sector_fundamentals()
    except Exception as e:
        _log("SECTORS", "WARN", f"sector fundamentals unavailable: {e}")
        sector_fundamentals_block = ""

    # Structured path: accuracy_context is excluded (MA-2 — no pre-emptive hedging).
    # Portfolio context is also excluded (MA-3a — handled by dedicated risk agent below).
    # Sector fundamentals are also excluded (MA-3c — sector opportunity agent uses MA-1's
    # conclusions as input, not raw data, to avoid token competition with macro analysis).
    # The analysis agent sees only market/macro data.
    user_message_structured = f"""Today is {today.strftime('%A, %B %d, %Y')}.
Prediction review date (5 business days): {review_date}

## FRED Macro Indicators
{json.dumps(fred_data, indent=2)}

## Market Data
{json.dumps(market_data, indent=2)}
{f"{chr(10)}{sector_block}" if sector_block else ""}
{f"{chr(10)}{technicals_block}" if technicals_block else ""}
{f"{chr(10)}{cot_block}" if cot_block else ""}
{f"{chr(10)}{notable_moves}" if notable_moves else ""}
{f"{chr(10)}{quant_context}" if quant_context else ""}
{f"{chr(10)}{events_context}" if events_context else ""}
{f"{chr(10)}{youtube_context}" if youtube_context else ""}"""

    # Free-text fallback: re-add portfolio_context (removed from structured path for MA-3a)
    # and accuracy_context. Both are needed for the single-pass free-text model.
    user_message = (
        user_message_structured
        + (f"\n{portfolio_context}" if portfolio_context else "")
        + (f"\n{accuracy_context}" if accuracy_context else "")
        + "\nGenerate the macro intelligence note as specified in your instructions."
    )

    # --- LLM payload preview (transparency; reuses already-fetched data) ---
    # Writes a rough picture of what the model receives + the signals we compute
    # but withhold (shadow fragility forced to 'show', retired HMM regime). Gated
    # on MACRO_PREVIEW so the normal run is unaffected; the daily Action sets it.
    if os.environ.get("MACRO_PREVIEW"):
        try:
            from quant_context import build_nonlive_signals_block
            nonlive_block = build_nonlive_signals_block(fred_data, histories)
            # Live path is structured → its system prompt is the relevant one.
            _sp_structured = PROMPTS_DIR / "system_prompt_structured.md"
            _sp_chars = (
                len(_sp_structured.read_text()) if _STRUCTURED_OUTPUT_AVAILABLE
                and _sp_structured.exists() else len(system_prompt)
            )
            preview = build_payload_preview(
                user_message_structured,
                nonlive_block=nonlive_block,
                system_prompt_chars=_sp_chars,
                free_text_extras={
                    "portfolio": portfolio_context,
                    "accuracy": accuracy_context,
                },
                today=today,
            )
            _pv_dir = REPO_ROOT / "results" / "llm_payload_preview"
            _pv_dir.mkdir(parents=True, exist_ok=True)
            _pv_path = _pv_dir / f"{today.strftime('%Y-%m-%d')}.md"
            _pv_path.write_text(preview, encoding="utf-8")
            _log("PREVIEW", "OK", f"LLM payload preview → {_pv_path.name}")
        except Exception as _pv_exc:
            _log("PREVIEW", "WARN",
                 f"payload preview skipped: {type(_pv_exc).__name__}: {_pv_exc}")

    # --- Structured output path (MA-1 / MA-2 / MA-3a) ---
    if _STRUCTURED_OUTPUT_AVAILABLE:
        _log("CLAUDE", "INFO", "attempting structured output (tool_use)...")
        system_prompt_structured = _render_prompt(
            (PROMPTS_DIR / "system_prompt_structured.md").read_text(), _cfg
        )
        structured = _analyze_structured(client, system_prompt_structured, user_message_structured)
        if structured is not None:
            _log("OVERRIDE", "INFO", "checking accuracy-based overrides (structured path)...")
            structured = _apply_accuracy_override_structured(structured)
            _log("CLAUDE", "INFO", "running adversarial review (structured path)...")
            structured = _adversarial_review_structured(client, structured)
            # MA-3a: portfolio risk agent — Haiku, narrow context (regime + positions only)
            if portfolio_context:
                _log("RISK", "INFO", "running portfolio risk agent (Haiku)...")
                risk_output = _run_risk_agent(client, structured.macro_regime, portfolio_context)
                if risk_output is not None:
                    structured = structured.model_copy(
                        update={"portfolio_risk": _format_portfolio_risk(risk_output)}
                    )
            # MA-3c: sector opportunity agent — Haiku, MA-1 conclusions + sector fundamentals
            if sector_fundamentals_block:
                _log("SECTOR", "INFO", "running sector opportunity agent (Haiku)...")
                sector_output = _run_sector_agent(client, structured, sector_fundamentals_block)
                if sector_output is not None:
                    structured = structured.model_copy(
                        update={"sector_opportunity": _format_sector_opportunity(sector_output)}
                    )
            # MA-3b: synthesis agent — formats structured JSON into final markdown
            _log("MA3B", "INFO", "running synthesis agent...")
            synthesis_text = _synthesize_structured(client, structured, today)
            if synthesis_text is not None:
                _count = _track_structured_success()
                if _count >= _SYNTHESIS_ACTIVATE_AFTER:
                    _log("MA3B", "INFO",
                         f"full pipeline (analysis + synthesis) stable {_count}× — "
                         "free-text fallback path is safe to retire")
                return synthesis_text  # str → build_note() uses directly, skips _build_analysis_markdown()
            # Synthesis failed — reset counter, fall back to Python markdown assembly
            _reset_structured_success()
            _log("MA3B", "WARN", "synthesis failed — using Python markdown assembly")
            return structured

    # --- Free-text fallback path (pre-MA-1 behaviour, unchanged) ---
    _reset_structured_success()
    _log("CLAUDE", "INFO", "generating analysis (free-text path)...")
    response = client.messages.create(
        model=main_model(),
        max_tokens=5000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    draft = response.content[0].text
    _out  = response.usage.output_tokens
    _max  = 5000
    if _out >= _max - 50:
        _log("CLAUDE", "WARN", f"response may be truncated ({_out}/{_max} tokens)")
    else:
        _log("CLAUDE", "OK", f"analysis complete ({_out} tokens out)")

    _log("CLAUDE", "INFO", "running adversarial review...")
    immutable_anchors = _build_immutable_anchors(fred_data, market_data)
    reviewed = adversarial_review(client, draft, immutable_anchors)
    _log("OVERRIDE", "INFO", "checking accuracy-based overrides...")
    final = _apply_accuracy_override(reviewed)
    return _scrub_prompt_artifacts(final)
