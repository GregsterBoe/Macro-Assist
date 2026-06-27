"""
versions.py — Single source of truth for pipeline versioning.

To bump the version after a structural capability change:
  1. Change PIPELINE_VERSION to the new "vX.Y" string.
  2. Close the last entry in VERSION_MILESTONES (update its end date to yesterday).
  3. Append a new entry with the new version string, today as start, 2099-12-31 as end.
  4. Run: python .macro-assist/tag_versions.py && python .macro-assist/summarize_accuracy.py

Notes:
  - All version strings include the "v" prefix (e.g. "v1.4").
  - Zero-range milestone entries (start > end) are never matched by version_for_date();
    they document versions superseded on the same day they were deployed.
  - MIN_FEEDBACK_VERSION marks the earliest version whose predictions are included in the
    accuracy feedback loop. Raise it when a quality gate invalidates older predictions.
"""
from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# Current pipeline version — stamped into every generated note's YAML frontmatter.
# ---------------------------------------------------------------------------
PIPELINE_VERSION: str = "v1.5"

# ---------------------------------------------------------------------------
# Minimum version included in the accuracy feedback loop.
# v0.3 (2026-04-05) introduced adversarial review — the first structural quality
# gate on prediction output. Reports before this are scored for historical
# completeness but excluded from the bias override that drives the daily pipeline.
# ---------------------------------------------------------------------------
MIN_FEEDBACK_VERSION: str = "v0.3"

# ---------------------------------------------------------------------------
# Version milestone date ranges (both bounds inclusive).
# Used by tag_versions.py to retroactively tag report and score files.
# ---------------------------------------------------------------------------
VERSION_MILESTONES: list[tuple[str, date, date]] = [
    ("v0.1", date(2026, 3, 12), date(2026, 4,  2)),  # Baseline: FRED + market data, signal matrix
    ("v0.2", date(2026, 4,  3), date(2026, 4,  4)),  # + Accuracy scoring, feedback loop
    ("v0.3", date(2026, 4,  5), date(2026, 4,  7)),  # + Opus, adversarial review, HY/ISM data
    ("v0.4", date(2026, 4,  8), date(2026, 4, 27)),  # + YouTube transcript integration
    ("v0.5", date(2026, 4, 28), date(2026, 5, 16)),  # + Portfolio positions (TR), Nasdaq data
    ("v0.6", date(2026, 5, 17), date(2026, 5, 18)),  # + Sector research, COT positioning
    ("v0.7", date(2026, 5, 19), date(2026, 5, 24)),  # + COT XLS fix, Pass 2 numerical anchoring
    ("v1.0", date(2026, 5, 25), date(2026, 5, 25)),  # + Multi-agent: MA-1/MA-2/MA-3a
    ("v1.1", date(2026, 5, 26), date(2026, 5, 25)),  # + MA-3b: synthesis agent (superseded same day by v1.2)
    ("v1.2", date(2026, 5, 26), date(2026, 5, 28)),  # + Phase 9/10: HAR-RV vol + HMM regime
    ("v1.3", date(2026, 5, 29), date(2026, 5, 28)),  # + Phase 11: conditional distributions (superseded same day by v1.4)
    ("v1.4", date(2026, 5, 29), date(2026, 6, 26)),  # + Phase 12: quant context block; Phase 14: weekly refit + monitoring
    ("v1.5", date(2026, 6, 27), date(2099, 12, 31)), # + WP-16: run profiles (control/loosened), conviction-floor flag, Brier calibration
]


# ---------------------------------------------------------------------------
# Helper — used by tag_versions.py to assign a version to a given date.
# ---------------------------------------------------------------------------

def version_for_date(d: date) -> str:
    """Return the pipeline version active on date d, or 'unknown'."""
    for version, start, end in VERSION_MILESTONES:
        if start <= d <= end:
            return version
    return "unknown"
