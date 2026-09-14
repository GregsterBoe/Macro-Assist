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

The one direction the rule forbids — product → research — currently happens in
two places, both because data-feed functions live in `fragility_backtest.py`
next to the harness that first needed them. They are pinned in `KNOWN_LEAKS`
so the boundary test is green today and fails the day a *third* one appears,
or the day one of these is fixed without the pin being removed (todo #20).

See docs/product/index.md, docs/research/index.md and ADR-0021.
"""
from __future__ import annotations

PRODUCT: frozenset[str] = frozenset({
    # the daily note (stage 2)
    "collect_and_analyze", "llm_analysis", "quant_context", "conditional",
    "fragility", "fragility_or", "vol_forecast",
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
    "exogenous",                    # Phase 19 branch; its emitter is soft-killed
})

TOOLING: frozenset[str] = frozenset({
    "bump_version", "tag_versions",
})

# (importer, imported) pairs that cross product → research today. Exact set:
# the test fails on any addition AND on any removal, so draining one means
# editing both the code and this pin, deliberately.
KNOWN_LEAKS: frozenset[tuple[str, str]] = frozenset({
    ("fragility_or", "fragility_backtest"),    # fetch_histories, fetch_sector_etfs, walk_forward_fragility + self-check scorers
    ("quant_context", "fragility_backtest"),   # freshen_vol_indices
})

ALL_TIERS = {"PRODUCT": PRODUCT, "DORMANT": DORMANT, "RESEARCH": RESEARCH, "TOOLING": TOOLING}


def tier_of(module: str) -> str | None:
    for name, members in ALL_TIERS.items():
        if module in members:
            return name
    return None
