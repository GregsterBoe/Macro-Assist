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


# ---------------------------------------------------------------------------
# yfinance retry
# ---------------------------------------------------------------------------

# yfinance's characteristic failure is not an exception — it is an EMPTY FRAME
# returned with no error at all, and every caller here read that as "this ticker
# has no history". `^VIX3M` did exactly that at ~06:04 UTC on 2026-09-16, 09-17
# and 09-18, and returned current data at 16:24 UTC the same days ([KB-034]); the
# composite lost its calibrated label on all three. One attempt cannot tell a
# ticker that is delisted from one that will answer a second later.
#
# Two attempts and a short pause is the whole budget — the same as the CBOE
# client's `_CBOE_ATTEMPTS`, for the same reason: a feed that is genuinely down
# should be reported, not hammered. The cost ceiling is one extra call per dead
# ticker per run.
_YF_ATTEMPTS = 2
_YF_BACKOFF_SECONDS = 2.0


def yf_history_with_retry(
    fetch,
    label: str,
    *,
    attempts: int = _YF_ATTEMPTS,
    backoff: float = _YF_BACKOFF_SECONDS,
    sleep=None,
):
    """Call `fetch()` until it returns a non-empty frame, or the budget runs out.

    `fetch` is a zero-argument callable returning a DataFrame-like (anything
    with `.empty`); `label` names the ticker in the retry log.

    Returns `(frame, None)` on success and `(None, reason)` when every attempt
    failed — an exception and an empty frame are both failures, and the reason
    distinguishes them so the caller's own warning stays diagnosable. Never
    raises: every call site already degrades on a missing leg, and a helper that
    introduced a new exception type would change what a dead leg does.
    """
    if sleep is None:
        import time
        sleep = time.sleep
    attempts = max(1, attempts)
    reason: str | None = None
    for attempt in range(attempts):
        try:
            hist = fetch()
        except Exception as exc:   # noqa: BLE001 — the reason is the product here
            reason = f"{type(exc).__name__}: {exc}"
            hist = None
        else:
            if hist is not None and not getattr(hist, "empty", False):
                return hist, None
            reason = "empty frame"
        if attempt + 1 < attempts:
            _log("YFINANCE", "WARN",
                 f"{label}: {reason} — retrying in {backoff:g}s "
                 f"(attempt {attempt + 2} of {attempts})")
            sleep(backoff)
    return None, f"{reason} after {attempts} attempts"
