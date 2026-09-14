"""
Tests for the product / research boundary (product_surface.py, ADR-0021).

The rule: product code never imports research code. It is enforced here by a
static import scan — nothing is imported, so no network, no model fits — and it
is exact in both directions: a new product → research import fails, and so does
a pinned leak that has been fixed without its pin being removed.

The classification itself is also checked for completeness, so a new module
cannot land unclassified.

All pure unit tests — no network.

Run:
    pytest .macro-assist/tests/test_product_boundary.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import product_surface as ps

_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = ("portfolio", "exogenous")
_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)


def _units() -> dict[str, list[Path]]:
    """Top-level module name → the .py files that make it up (packages fold)."""
    units: dict[str, list[Path]] = {}
    for f in _ROOT.glob("*.py"):
        units[f.stem] = [f]
    for pkg in _PACKAGES:
        units[pkg] = sorted((_ROOT / pkg).glob("*.py"))
    return units


def _imports(unit: str, files: list[Path], known: set[str]) -> set[str]:
    out: set[str] = set()
    for f in files:
        for a, b in _IMPORT_RE.findall(f.read_text()):
            name = (a or b).split(".")[0]
            if name in known and name != unit:
                out.add(name)
    return out


UNITS = _units()
KNOWN = set(UNITS)
DEPS = {u: _imports(u, fs, KNOWN) for u, fs in UNITS.items()}


def test_every_module_is_classified_exactly_once():
    classified = {}
    for tier, members in ps.ALL_TIERS.items():
        for m in members:
            assert m not in classified, f"{m} is in both {classified[m]} and {tier}"
            classified[m] = tier
    unclassified = KNOWN - set(classified) - {"product_surface"}
    assert not unclassified, f"add these to a tier in product_surface.py: {sorted(unclassified)}"
    missing = set(classified) - KNOWN
    assert not missing, f"classified but no such module: {sorted(missing)}"


def test_product_never_imports_research_except_the_pinned_leaks():
    product_side = ps.PRODUCT | ps.DORMANT
    leaks = {
        (u, d)
        for u in product_side
        for d in DEPS.get(u, ())
        if d in ps.RESEARCH
    }
    new = leaks - ps.KNOWN_LEAKS
    assert not new, f"new product → research import(s): {sorted(new)} — fix the import or argue in ADR-0021"
    drained = ps.KNOWN_LEAKS - leaks
    assert not drained, f"pinned leak(s) no longer exist — remove from KNOWN_LEAKS: {sorted(drained)}"


def test_pipeline_entry_points_are_product():
    for entry in ("collect_and_analyze", "refit_models", "score_predictions",
                  "score_distributions", "summarize_accuracy", "portfolio"):
        assert entry in ps.PRODUCT, entry


def test_research_closure_of_each_entry_point_is_only_the_pinned_leaks():
    """Transitively, the only research code any pipeline stage can reach is
    what KNOWN_LEAKS names — nothing sneaks in two hops deep."""
    def closure(root: str) -> set[str]:
        seen, stack = set(), [root]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(DEPS.get(x, ()))
        return seen - {root}

    allowed = {d for _, d in ps.KNOWN_LEAKS}
    for entry in ("collect_and_analyze", "refit_models", "score_predictions",
                  "score_distributions", "summarize_accuracy", "portfolio"):
        reached = closure(entry) & ps.RESEARCH
        assert reached <= allowed, f"{entry} reaches research code {sorted(reached - allowed)}"


@pytest.mark.parametrize("pair", sorted(ps.KNOWN_LEAKS))
def test_each_pinned_leak_is_tracked_in_todo(pair):
    todo = (_ROOT.parent / "docs" / "record" / "todo.md").read_text()
    assert pair[0] in todo and pair[1] in todo, f"{pair} pinned but not in todo.md"
