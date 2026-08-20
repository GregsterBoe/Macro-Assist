"""Shared foundation for the daily macro pipeline.

Holds the pieces every layer needs — the structured logger, the on-disk path
constants, and the optional structured-output (pydantic schema) availability
flag. Imports **nothing** from the pipeline's own modules, so it can be imported
freely without creating cycles.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Pipeline logger
# ---------------------------------------------------------------------------

def _log(section: str, level: str, msg: str) -> None:
    """Structured one-line logger. level: OK | WARN | FAIL | INFO"""
    icons = {"OK": "✓", "WARN": "⚠", "FAIL": "✗", "INFO": "→"}
    print(f"[{section:<10}] {icons.get(level, ' ')} {msg}", flush=True)


def next_review_date(today: datetime) -> str:
    """Return the date 5 business days from today (for prediction tracking)."""
    d, count = today, 0
    while count < 5:
        d += timedelta(days=1)
        if d.weekday() < 5:   # Mon–Fri
            count += 1
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# VAULT_ROOT can be overridden via env var (used by GitHub Actions).
# Falls back to the parent of .macro-assist/ for local runs.
VAULT_ROOT     = Path(os.environ.get("VAULT_ROOT", _HERE.parent))
PROMPTS_DIR    = _HERE / "prompts"
DATA_DIR       = _HERE / "data"
ACCURACY_JSON  = DATA_DIR / "accuracy_summary.json"
REPO_ROOT      = _HERE.parent
POSITIONS_CSV  = Path(os.environ.get("POSITIONS_CSV", REPO_ROOT / "data" / "tr_positions.csv"))


# ---------------------------------------------------------------------------
# Structured-output (pydantic schema) availability
# ---------------------------------------------------------------------------

try:
    from schemas import AnalysisOutput, AssetPrediction, PortfolioRiskOutput, SectorOpportunityOutput
    _STRUCTURED_OUTPUT_AVAILABLE = True
except ImportError:
    AnalysisOutput = AssetPrediction = PortfolioRiskOutput = SectorOpportunityOutput = None
    _STRUCTURED_OUTPUT_AVAILABLE = False
