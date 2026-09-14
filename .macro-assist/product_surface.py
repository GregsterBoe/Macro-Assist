"""
product_surface.py — the product / research boundary, as data.

Every module under `.macro-assist/` belongs to exactly one tier. The tiers are
not a taxonomy for its own sake: they encode a rule the test suite enforces —
**product code never imports research code.** A note that a user can rely on
must not be one refactor of a backtest harness away from breaking, and a harness
must be free to change without touching the live path.

Tiers
-----
PRODUCT      Runs in `pipeline.yml`, or is imported by something that does. This
             is what "ready to use" refers to. Versioned (`versions.py`),
             scored weekly, changed only through the mode ladder (ADR-0005) and
             the version rule (CLAUDE.md convention 9).
DORMANT      Product code that is soft-killed (ADR-0015): still in the product
             tree, still tested, not scheduled. Held to the product rule.
RESEARCH     Harnesses and backtests. Read history, fit models, score arms,
             write KB entries. May import product code freely (they measure
             it); must never be imported by it.
TOOLING      Release and bookkeeping scripts. Outside both rules.

Packages (`portfolio/`, `exogenous/`) are classified as units.

If the rule ever has to be broken knowingly, the edge goes in `KNOWN_LEAKS`
with a todo number, and the test then holds it exactly: it fails on a new
unpinned edge *and* on a pinned edge that has been fixed without its pin being
removed. The set is empty. It was not on 2026-09-14 — `fragility_or` and
`quant_context` both imported data feeds from `fragility_backtest.py`, the
harness that first needed them — and draining it produced `fragility_panel.py`
(resolved #20).

See docs/product/index.md, docs/research/index.md and ADR-0021.
"""
from __future__ import annotations

PRODUCT: frozenset[str] = frozenset({
    # the daily note (stage 2)
    "collect_and_analyze", "llm_analysis", "quant_context", "conditional",
    "fragility", "fragility_or", "fragility_panel", "vol_forecast",
    "market_data", "fred_data", "calendar_events", "youtube_data",
    "parse_positions", "schemas", "assets", "versions",
    "pipeline_common", "pipeline_config",
    # the weekly scorecard and accuracy report (stage 3). The scorer is product —
    # it publishes what the note is held to; the *read* of its verdict is research.
    "score_distributions", "score_predictions", "summarize_accuracy",
    "bias_separation",
    # the paper portfolio (stage 4, ADR-0019) and the weekly table rebuild (stage 5)
    "portfolio", "refit_models",
    # the point-in-time snapshot the rebalance reads; its tests are the leakage guard
    "point_in_time",
})

DORMANT: frozenset[str] = frozenset({
    "regime", "regime_features",   # HMM block, retired from the note (ADR-0004)
    "kimi_arm",                     # ensemble confidence arm, soft-killed 2026-09-04
})

RESEARCH: frozenset[str] = frozenset({
    "numeric_baseline", "input_testing", "aggregator_testing", "companion_testing",
    "fragility_backtest", "regime_backtest", "har_backtest", "backtest",
    "input_ledger", "citation_screen", "synthetic",
    "explore_conditioner",          # explore-tier shadow conditioners (register H-002 … H-007)
    "exogenous",                    # Phase 19 branch; its emitter is soft-killed
})

TOOLING: frozenset[str] = frozenset({
    "bump_version", "tag_versions",
})

# (importer, imported) pairs that cross product → research, each with a todo
# number. Exact set: the test fails on any addition AND on any removal, so
# adding or draining one means editing both the code and this pin, deliberately.
KNOWN_LEAKS: frozenset[tuple[str, str]] = frozenset()

ALL_TIERS = {"PRODUCT": PRODUCT, "DORMANT": DORMANT, "RESEARCH": RESEARCH, "TOOLING": TOOLING}


def tier_of(module: str) -> str | None:
    for name, members in ALL_TIERS.items():
        if module in members:
            return name
    return None
