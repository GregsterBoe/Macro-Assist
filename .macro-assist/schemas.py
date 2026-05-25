"""
Pydantic v2 output contracts for the structured analysis pipeline (Phase MA-1).

AssetPrediction — one row of the 5-Day Predictions table.
AnalysisOutput  — full structured output from the analysis agent.

These models are used two ways:
  1. As a tool input_schema (JSON Schema) for Anthropic tool_use.
  2. For runtime validation of the model's response via model_validate().

The @model_validator on AssetPrediction catches bias/narrative contradictions at
parse time, making them hard errors rather than logged warnings (MA-0.3 soft check).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

_FADE_WORDS = frozenset({"fade", "fade the", "expect decline", "downside risk if"})


class AssetPrediction(BaseModel):
    asset: str
    bias: Literal["Bullish", "Bearish", "Neutral"]
    primary_driver: str = Field(min_length=10, max_length=500)
    confidence_pct: int = Field(ge=50, le=80)
    target_range: str
    horizon_days: int = Field(default=5)

    @model_validator(mode="after")
    def bias_narrative_consistent(self) -> "AssetPrediction":
        if self.bias == "Bullish":
            driver_lower = self.primary_driver.lower()
            for w in _FADE_WORDS:
                if w in driver_lower:
                    raise ValueError(
                        f"Primary driver contradicts Bullish bias: '{w}' found in driver text"
                    )
        return self


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
