"""
Pydantic v2 output contracts for the structured analysis pipeline (Phase MA-1).

AssetPrediction — one row of the 5-Day Outlook table.
AnalysisOutput  — full structured output from the analysis agent.

These models are used two ways:
  1. As a tool input_schema (JSON Schema) for Anthropic tool_use.
  2. For runtime validation of the model's response via model_validate().

WP-21.D / v1.6 — the directional product is CUT. `bias` and `confidence_pct` are
gone from AssetPrediction, so the model is no longer asked to produce a
Bullish/Bearish call or a confidence number at all. This is a removal, not a
suppression: three independent measurements say the call is anti-informative
([KB-007] 36% decisive accuracy and BSS −0.195; [KB-022] inverted separation;
[KB-024] no numeric model class beats a constant, and both invert the same way),
so asking for it and hiding it would just move the problem.

What replaces it is rendered by Python, not by the model: the conditional return
distribution for each asset (median, P25/P75, n) out of
`data/conditional_distributions.json`. It is computed from data, carries its own
sample size, and is not what failed. `primary_driver` and `target_range` stay —
the narrative and the plausible-move band were never scored as directional calls.

The bias/narrative contradiction validator went with `bias`; there is no longer a
direction for a driver to contradict.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AssetPrediction(BaseModel):
    """One row of the 5-Day Outlook table.

    Name kept (rather than renamed to AssetOutlook) so the tool schema, the
    JSONL logs and the historical fixtures keep resolving; the contents are what
    changed. Nothing in this model states or implies a direction.
    """
    asset: str
    primary_driver: str = Field(min_length=10, max_length=1200)
    target_range: str
    horizon_days: int = Field(default=5)


class AnalysisOutput(BaseModel):
    executive_summary: str = Field(max_length=1000)
    macro_regime: Literal["Risk-On", "Risk-Off", "Stagflation", "Reflation", "Neutral/Mixed"]
    macro_dashboard_text: Optional[str] = Field(default=None, max_length=1800)
    equities_note: str = Field(max_length=900)
    rates_note: str = Field(max_length=900)
    inflation_growth_note: str = Field(max_length=900)
    commodities_note: str = Field(max_length=900)
    key_risks: list[str] = Field(min_length=3, max_length=5)
    predictions: list[AssetPrediction] = Field(min_length=6, max_length=6)
    sector_opportunity: Optional[str] = Field(default=None, max_length=1800)
    portfolio_risk: Optional[str] = Field(default=None, max_length=1600)


class PortfolioRiskOutput(BaseModel):
    """MA-3a: Structured output from the Haiku portfolio risk agent.
    Receives only macro_regime + portfolio positions — no FRED data or market context.
    """
    biggest_headwind: str = Field(max_length=700)
    biggest_tailwind: str = Field(max_length=500)
    actionable: str = Field(max_length=700)
    opportunity_gap: str = Field(max_length=900)


class SectorCall(BaseModel):
    """One sector ETF opportunity call from MA-3c."""
    etf_ticker: str = Field(max_length=6)
    sector_name: str = Field(max_length=50)
    macro_driver: str = Field(max_length=500)       # specific data point from MA-1 analysis
    valuation_context: str = Field(max_length=400)  # P/E vs reference + flag from table
    timing_note: Optional[str] = Field(default=None, max_length=280)
    research_candidates: list[str] = Field(default_factory=list)  # only for Below-avg P/E


class SectorOpportunityOutput(BaseModel):
    """MA-3c: Structured output from the Haiku sector opportunity agent.
    Receives MA-1's synthesized macro conclusions + sector ETF fundamentals block.
    """
    calls: list[SectorCall] = Field(min_length=1, max_length=3)
    regime_note: Optional[str] = Field(default=None, max_length=800)
