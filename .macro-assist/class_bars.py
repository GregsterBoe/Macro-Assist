"""
class_bars.py — the class bars a promoted hypothesis is read against (WP-23.B).

Research tier (product_surface: RESEARCH). One pre-registered bar per
hypothesis *class*, written before any member of the class is promoted — the
ADR-0020 move made a rule (How we explore §5). A bar here is code, so what a
member is judged by cannot be re-read after the number is visible; a member
adds only what its own entry states — its arm, its horizon, a stricter floor,
and its mechanism clause — in a `Pre-registration` field the independent audit
stamps with the rest of the entry (ADR-0022).

Two classes
-----------
    conditioner   a shadow conditioner vs `unconditional` (H-004, H-008).
                  Phase 22's bar as is — MIN_SKILL, a block-bootstrap interval
                  clear of zero, disqualifiers first — plus `har_scaled` as a
                  second comparator (resolved.md #22) and the entry's
                  mechanism clause. Read on the sealed side resolved.md #19
                  fixed: report dates 2018-01-01 → the day before Phase 22's
                  live record, once.
    gap_width     a quarterly gap vs the realized width of what follows
                  (H-003). Pinball loss on a P25/P75 pair against
                  `unconditional`, `trailing_250` as the rival, four-quarter
                  blocks, an explicit floor. **Its seal is not decided**
                  (todo.md): a sealed read under this class is refused until
                  it is.

The verdict — disqualifiers first, each returning its own verdict
---------------------------------------------------------------------
    exploratory         the sample is not the sealed side; reported, never passed
    underpowered        too few blocks (the headline or the rival's subsample),
                        too few report dates, or a clause cell under the floor
                        in report dates *or* distinct episodes
    miscalibrated       the arm's P25–P75 coverage interval excludes 0.50
    inverted            skill vs the benchmark reliably below zero
    no_edge             did not clear MIN_SKILL with an interval clear of zero
    explained_by_rival  cleared the benchmark and not the rival, by the same
                        pass clause: a conditioner that beats `unconditional`
                        and not `har_scaled` has found width, not a state
    unexplained         cleared both, and the mechanism clause failed — or the
                        entry named none (How we explore §9, question 4)
    edge                every disqualifier cleared, both comparators beaten by
                        the margin, every clause held

[KB-027] is why this is the order and why every stage has a test driving it
alone: a pass clause that can be reached without consulting a disqualifier is
the hole that bar had. Every stage's number is reported whichever verdict
fires, so a read never hides the checks it did not need.

The mechanism clause
--------------------
Three kinds, each over *cells* — sets of observations matched on the labels
the harness writes (`or_state`, `dd_bin`, …; a list is any-of):

    width_contrast  cell a's realized P75−P25 exceeds `min_ratio` × cell b's,
                    block-bootstrap interval of the ratio clear of min_ratio
    median_side     cell a's realized median sits `left` / `right` of the
                    slice's, interval clear of zero
    skill_in_state  the arm's pooled skill vs the benchmark on the dates in a
                    cell has an interval clear of zero; with `null_in`, the
                    skill in that other cell has an interval spanning zero

Every cell a clause names is held to the class floor — report dates and
distinct episodes, both — before its result is looked at: a cell of 70 rows
can be two episodes, and a median on two episodes is not a measurement. An
episode is a run of the cell's dates with no gap longer than a block; a run
longer than a year counts once per year.

    python class_bars.py              # print both bars
    python class_bars.py H-008        # does this entry's pre-registration parse?
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from assets import ASSETS, BY_KEY, HORIZONS, ORIGINAL_KEYS
from numeric_baseline import SEAL_START as SEALED_FROM
from score_distributions import (
    BLOCK_DAYS, MIN_BLOCKS, MIN_POOL_BLOCKS, MIN_SKILL, N_BOOT, NOMINAL_COVERAGE, SEED,
    SEAL_START as LIVE_RECORD_START, skill_vs,
)

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# the bars
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassBar:
    name: str
    benchmark: str
    rival: str
    headline_keys: frozenset[str] | None   # None: every series the observations carry
    block: int                             # report dates per bootstrap block
    min_blocks: int
    min_report_dates: int
    cell_min_report_dates: int
    cell_min_episodes: int
    episode_gap: int                       # report dates apart before a cell's run is a new episode
    episode_span: int                      # a run longer than this counts one episode per span
    horizons: tuple
    default_horizon: object
    sealed_from: date | None               # None: the class's seal is not decided
    sealed_until: date | None              # exclusive


CONDITIONER = ClassBar(
    name="conditioner", benchmark="unconditional", rival="har_scaled",
    headline_keys=frozenset(ORIGINAL_KEYS),
    block=BLOCK_DAYS, min_blocks=MIN_BLOCKS, min_report_dates=0,
    # Three blocks of report dates, and three episodes: "a median on two
    # episodes is not a measurement" (How we explore §9, question 8).
    # A run longer than a year counts one episode per year: a stress spell is
    # never that long, and a calm cell spanning three years is three years of
    # evidence, not one.
    cell_min_report_dates=3 * BLOCK_DAYS, cell_min_episodes=3, episode_gap=BLOCK_DAYS,
    episode_span=252,
    horizons=tuple(HORIZONS), default_horizon=5,        # 5d is the horizon the note publishes
    sealed_from=SEALED_FROM, sealed_until=date.fromisoformat(LIVE_RECORD_START),
)

GAP_WIDTH = ClassBar(
    name="gap_width", benchmark="unconditional", rival="trailing_250",
    headline_keys=None,
    # One observation a quarter, windows that do not overlap; a block is a
    # year, because a rate regime outlasts a quarter. Ten blocks is ten years:
    # more than one cycle. Twelve quarters in a cell is three of those years.
    block=4, min_blocks=10, min_report_dates=40,
    cell_min_report_dates=12, cell_min_episodes=3, episode_gap=1, episode_span=4,
    horizons=("1q",), default_horizon="1q",
    sealed_from=None, sealed_until=None,
)

BARS: dict[str, ClassBar] = {b.name: b for b in (CONDITIONER, GAP_WIDTH)}

VERDICTS = ("exploratory", "underpowered", "miscalibrated", "inverted", "no_edge",
            "explained_by_rival", "unexplained", "edge")


class PreregError(ValueError):
    """An entry's pre-registration that no class bar can read."""


# ---------------------------------------------------------------------------
# the statistics: `explore_conditioner.pooled`'s design, with the block a parameter
# ---------------------------------------------------------------------------

def _block_ids(obs: list[dict], block: int) -> np.ndarray:
    dates = sorted({o["date"] for o in obs})
    blk = {d: i // block for i, d in enumerate(dates)}
    return np.array([blk[o["date"]] for o in obs])


def _ordered(keys) -> list[str]:
    return [a.key for a in ASSETS if a.key in keys] + sorted(k for k in keys if k not in BY_KEY)


def pooled_skill(obs: list[dict], arm: str, benchmark: str, keys, block: int,
                 n_boot: int = N_BOOT, seed: int = SEED) -> dict | None:
    """Per-series skill vs `benchmark`, averaged equally over the series in
    `keys` with at least MIN_POOL_BLOCKS blocks; a block-bootstrap interval
    that re-pools exactly those series on shared blocks."""
    obs = [o for o in obs if arm in o["arms"] and benchmark in o["arms"]]
    if not obs:
        return None
    qualifying = []
    for k in _ordered(keys):
        sub = [o for o in obs if o["asset"] == k]
        if not sub:
            continue
        nb = len({o["date"] for o in sub}) // block + 1
        if nb < MIN_POOL_BLOCKS or skill_vs(sub, arm, benchmark) is None:
            continue
        qualifying.append(k)
    if not qualifying:
        return None
    blk_all = _block_ids(obs, block)
    nb = blk_all.max() + 1
    sums = []
    for k in qualifying:
        idx = np.array([i for i, o in enumerate(obs) if o["asset"] == k])
        la = np.array([obs[i]["arms"][arm]["pinball_mean"] for i in idx])
        lb = np.array([obs[i]["arms"][benchmark]["pinball_mean"] for i in idx])
        sums.append((np.bincount(blk_all[idx], weights=la, minlength=nb),
                     np.bincount(blk_all[idx], weights=lb, minlength=nb)))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nb, size=(n_boot, nb))
    sk = np.zeros(n_boot)
    for sa, sb in sums:
        num, den = sa[draws].sum(axis=1), sb[draws].sum(axis=1)
        sk += 1.0 - num / np.where(den > 0, den, np.nan)
    sk = sk / len(sums)
    sk = sk[np.isfinite(sk)]
    point = float(np.mean([skill_vs([o for o in obs if o["asset"] == k], arm, benchmark)
                           for k in qualifying]))
    lo, hi = np.percentile(sk, [2.5, 97.5])
    return {"skill": round(point, 4), "ci": {"lo": round(float(lo), 4), "hi": round(float(hi), 4),
                                             "n_boot": int(len(sk)), "n_blocks": int(nb)},
            "assets": qualifying}


def coverage_ci(obs: list[dict], arm: str, block: int,
                n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float | None, dict | None]:
    """The share of realized values inside the arm's P25–P75, and its
    block-bootstrap interval."""
    obs = [o for o in obs if arm in o["arms"]]
    if not obs:
        return None, None
    blk = _block_ids(obs, block)
    nb = blk.max() + 1
    inside = np.array([float(o["arms"][arm]["inside_iqr"]) for o in obs])
    point = round(float(inside.mean()), 4)
    if nb < 2:
        return point, None
    hits = np.bincount(blk, weights=inside, minlength=nb)
    counts = np.bincount(blk, minlength=nb).astype(float)
    draws = np.random.default_rng(seed).integers(0, nb, size=(n_boot, nb))
    cov = hits[draws].sum(axis=1) / counts[draws].sum(axis=1)
    lo, hi = np.percentile(cov, [2.5, 97.5])
    return point, {"lo": round(float(lo), 4), "hi": round(float(hi), 4), "n_blocks": int(nb)}


def _n_blocks(obs: list[dict], block: int) -> int:
    n = len({o["date"] for o in obs})
    return (n + block - 1) // block


def _clears(stat: dict | None) -> bool:
    """The one pass clause, for the benchmark and the rival alike."""
    return bool(stat and stat.get("skill") is not None and stat["skill"] > MIN_SKILL
                and stat.get("ci") and stat["ci"]["lo"] > 0)


def summarize(bar: ClassBar, obs: list[dict], arm: str, horizon=None) -> dict:
    """Everything the verdict reads, at the member's horizon, on the headline
    series: skill vs the benchmark, coverage, and skill vs the rival on the
    subsample where the rival quotes."""
    horizon = bar.default_horizon if horizon is None else horizon
    sub = [o for o in obs if o["horizon"] == horizon]
    keys = bar.headline_keys if bar.headline_keys is not None else {o["asset"] for o in sub}
    head = [o for o in sub if o["asset"] in keys and arm in o["arms"] and bar.benchmark in o["arms"]]
    rival = [o for o in head if bar.rival in o["arms"]]
    cov, cov_ci = coverage_ci(head, arm, bar.block)
    dates = sorted({o["date"] for o in head})
    return {
        "class": bar.name, "arm": arm, "horizon": horizon, "series": _ordered(keys),
        "n": len(head), "n_report_dates": len(dates), "n_blocks": _n_blocks(head, bar.block),
        "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
        "skill": pooled_skill(head, arm, bar.benchmark, keys, bar.block),
        "coverage": cov, "coverage_ci": cov_ci,
        "rival": {"name": bar.rival, "n_report_dates": len({o["date"] for o in rival}),
                  "n_blocks": _n_blocks(rival, bar.block),
                  "skill": pooled_skill(rival, arm, bar.rival, keys, bar.block)},
    }


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------

def class_floor(bar: ClassBar) -> dict:
    return {"report_dates": bar.cell_min_report_dates, "episodes": bar.cell_min_episodes}


def _ci(s: dict | None) -> str:
    if not s or s.get("skill") is None:
        return "none"
    ci = s.get("ci") or {}
    return f"{s['skill']:+.4f} [{ci.get('lo', float('nan')):+.4f}, {ci.get('hi', float('nan')):+.4f}]"


def verdict(bar: ClassBar, summary: dict, clauses: list[dict] | None, *,
            sealed: bool, floor: dict | None = None) -> dict:
    """Apply the class bar to one member's summary and its evaluated clauses.
    The disqualifiers are evaluated in order and each returns at once; every
    number is carried in the result whichever fires."""
    floor = floor or class_floor(bar)
    clauses = clauses or []
    out = {"class": bar.name, "summary": summary, "clauses": clauses, "floor": floor}

    def done(v: str, reason: str) -> dict:
        return {**out, "verdict": v, "reason": reason}

    if not sealed:
        return done("exploratory", "the sample is not the sealed side; reported, cannot pass")

    # --- Disqualifier 1: power, the headline's, the rival's and every cell's
    if summary["n_blocks"] < bar.min_blocks:
        return done("underpowered", f"{summary['n_blocks']} blocks < {bar.min_blocks} required")
    if summary["n_report_dates"] < bar.min_report_dates:
        return done("underpowered", f"{summary['n_report_dates']} report dates < "
                                    f"{bar.min_report_dates} required")
    if summary["rival"]["n_blocks"] < bar.min_blocks:
        return done("underpowered", f"the rival `{bar.rival}` quotes on {summary['rival']['n_blocks']} "
                                    f"blocks < {bar.min_blocks}; it can be neither beaten nor not")
    for c in clauses:
        for cell in c["cells"]:
            if cell["n_report_dates"] < floor["report_dates"] or cell["n_episodes"] < floor["episodes"]:
                return done("underpowered", f"{c['kind']} cell {cell['name']} holds "
                                            f"{cell['n_report_dates']} report dates in {cell['n_episodes']} "
                                            f"episodes; the floor is {floor['report_dates']} in "
                                            f"{floor['episodes']}")
    skill = summary["skill"]
    if not skill or skill.get("skill") is None or not skill.get("ci"):
        return done("underpowered", f"no skill estimate against `{bar.benchmark}`")
    if summary["coverage_ci"] is None:
        return done("underpowered", "no coverage interval")

    # --- Disqualifier 2: calibration ------------------------------------
    ci = summary["coverage_ci"]
    if not ci["lo"] <= NOMINAL_COVERAGE <= ci["hi"]:
        return done("miscalibrated", f"coverage {summary['coverage']} [{ci['lo']}, {ci['hi']}] "
                                     f"excludes {NOMINAL_COVERAGE}")

    # --- Disqualifier 3: inversion --------------------------------------
    if skill["ci"]["hi"] < 0:
        return done("inverted", f"skill vs `{bar.benchmark}` {_ci(skill)} lies entirely below zero")

    # --- Only now the pass clause, against the benchmark, then the rival
    if not _clears(skill):
        return done("no_edge", f"skill vs `{bar.benchmark}` {_ci(skill)} did not clear "
                               f"{MIN_SKILL} with an interval clear of zero")
    if not _clears(summary["rival"]["skill"]):
        return done("explained_by_rival", f"cleared `{bar.benchmark}` ({_ci(skill)}) but not "
                                          f"`{bar.rival}` ({_ci(summary['rival']['skill'])})")

    # --- and the mechanism clause ---------------------------------------
    if not clauses:
        return done("unexplained", "the entry names no mechanism clause")
    failed = [c for c in clauses if not c["passed"]]
    if failed:
        return done("unexplained", "; ".join(f"{c['kind']} failed: {c['detail']}" for c in failed))
    return done("edge", f"skill {_ci(skill)} vs `{bar.benchmark}`, {_ci(summary['rival']['skill'])} "
                        f"vs `{bar.rival}`, {len(clauses)} clause(s) held")


# ---------------------------------------------------------------------------
# the mechanism clause
# ---------------------------------------------------------------------------

KINDS = {
    "width_contrast": {"required": {"kind", "series", "a", "b"},
                       "optional": {"min_ratio", "horizons"}},
    "median_side": {"required": {"kind", "series", "cell", "side"},
                    "optional": {"horizons"}},
    "skill_in_state": {"required": {"kind", "cell"},
                       "optional": {"null_in", "horizons"}},
}


def _matches(o: dict, cell: dict) -> bool:
    for k, v in cell.items():
        if o.get(k) not in (v if isinstance(v, list) else [v]):
            return False
    return True


def _cell_name(cell: dict) -> str:
    return " ∧ ".join(f"{k}={'|'.join(map(str, v)) if isinstance(v, list) else v}" for k, v in cell.items())


def episodes(cell_dates, all_dates, gap: int, span: int) -> int:
    """Distinct runs of a cell's report dates — a new run starts when the next
    date is more than `gap` report dates after the last — with a run longer
    than `span` report dates counted once per span."""
    pos = {d: i for i, d in enumerate(sorted(set(all_dates)))}
    p = np.array(sorted(pos[d] for d in set(cell_dates)))
    if not len(p):
        return 0
    cuts = np.where(np.diff(p) > gap)[0]
    starts, ends = np.r_[p[0], p[cuts + 1]], np.r_[p[cuts], p[-1]]
    return int(sum(max(1, (e - s + 1) // span) for s, e in zip(starts, ends)))


def _cell_size(bar: ClassBar, cell_obs: list[dict], universe: list[dict], name: str) -> dict:
    dates = {o["date"] for o in cell_obs}
    return {"name": name, "n_report_dates": len(dates),
            "n_episodes": episodes(dates, [o["date"] for o in universe], bar.episode_gap, bar.episode_span)}


def _check_labels(obs: list[dict], *cells: dict) -> None:
    carried = set().union(*(o.keys() for o in obs)) if obs else set()
    for cell in cells:
        missing = set(cell) - carried
        if missing:
            raise PreregError(f"a cell names label(s) {sorted(missing)} the observations do not carry")


def _boot_stat(universe: list[dict], block: int, stat, n_boot: int = N_BOOT, seed: int = SEED):
    """Block-bootstrap a statistic of `universe` (whole blocks of report dates
    resampled with replacement); draws where it is undefined are dropped."""
    blk = _block_ids(universe, block)
    nb = int(blk.max()) + 1
    groups = [[o for o, b in zip(universe, blk) if b == i] for i in range(nb)]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        draw = [o for i in rng.integers(0, nb, size=nb) for o in groups[i]]
        v = stat(draw)
        if v is not None and np.isfinite(v):
            vals.append(v)
    if not vals:
        return None
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return {"lo": round(float(lo), 4), "hi": round(float(hi), 4), "n_boot": len(vals), "n_blocks": nb}


def _iqr(vals) -> float | None:
    return float(np.subtract(*np.percentile(vals, [75, 25]))) if len(vals) >= 2 else None


def _eval_width(bar, clause, obs, horizon):
    uni = [o for o in obs if o["asset"] == clause["series"] and o["horizon"] == horizon]
    _check_labels(uni, clause["a"], clause["b"])
    a = [o for o in uni if _matches(o, clause["a"])]
    b = [o for o in uni if _matches(o, clause["b"])]
    ratio_min = float(clause.get("min_ratio", 1.0))

    def ratio(sample):
        wa = _iqr([o["realized"] for o in sample if _matches(o, clause["a"])])
        wb = _iqr([o["realized"] for o in sample if _matches(o, clause["b"])])
        return None if wa is None or not wb else wa / wb

    point = ratio(uni)
    ci = _boot_stat(uni, bar.block, ratio) if a and b else None
    ok = point is not None and ci is not None and ci["lo"] > ratio_min
    cells = [_cell_size(bar, a, uni, f"a@{horizon}"), _cell_size(bar, b, uni, f"b@{horizon}")]
    detail = (f"{clause['series']} h={horizon}: width ratio {_cell_name(clause['a'])} / {_cell_name(clause['b'])} "
              f"= {point if point is None else round(point, 3)}, interval "
              f"{None if ci is None else [ci['lo'], ci['hi']]}, needs lower bound > {ratio_min}")
    return ok, cells, detail


def _eval_median(bar, clause, obs, horizon):
    uni = [o for o in obs if o["asset"] == clause["series"] and o["horizon"] == horizon]
    _check_labels(uni, clause["cell"])
    a = [o for o in uni if _matches(o, clause["cell"])]

    def shift(sample):
        cell = [o["realized"] for o in sample if _matches(o, clause["cell"])]
        return None if not cell else float(np.median(cell) - np.median([o["realized"] for o in sample]))

    point = shift(uni)
    ci = _boot_stat(uni, bar.block, shift) if a else None
    side = clause["side"]
    ok = ci is not None and (ci["hi"] < 0 if side == "left" else ci["lo"] > 0)
    detail = (f"{clause['series']} h={horizon}: median of {_cell_name(clause['cell'])} minus the slice's "
              f"= {point if point is None else round(point, 4)}, interval "
              f"{None if ci is None else [ci['lo'], ci['hi']]}, needs it clear of zero on the {side}")
    return ok, [_cell_size(bar, a, uni, f"cell@{horizon}")], detail


def _eval_skill(bar, clause, obs, horizon, arm):
    sub = [o for o in obs if o["horizon"] == horizon]
    keys = bar.headline_keys if bar.headline_keys is not None else {o["asset"] for o in sub}
    sub = [o for o in sub if o["asset"] in keys]
    _check_labels(sub, clause["cell"], *([clause["null_in"]] if "null_in" in clause else []))
    a = [o for o in sub if _matches(o, clause["cell"])]
    sa = pooled_skill(a, arm, bar.benchmark, keys, bar.block)
    ok = bool(sa and sa["ci"]["lo"] > 0)
    cells = [_cell_size(bar, a, sub, f"cell@{horizon}")]
    detail = f"h={horizon}: skill in {_cell_name(clause['cell'])} {_ci(sa)}, needs its interval above zero"
    if "null_in" in clause:
        b = [o for o in sub if _matches(o, clause["null_in"])]
        sb = pooled_skill(b, arm, bar.benchmark, keys, bar.block)
        ok = ok and bool(sb and sb["ci"]["lo"] <= 0 <= sb["ci"]["hi"])
        cells.append(_cell_size(bar, b, sub, f"null_in@{horizon}"))
        detail += f"; in {_cell_name(clause['null_in'])} {_ci(sb)}, needs its interval to span zero"
    return ok, cells, detail


def evaluate_clause(bar: ClassBar, clause: dict, obs: list[dict], arm: str, horizon) -> dict:
    """One clause at every horizon it names (the member's horizon if none);
    it holds only if it holds at each."""
    oks, cells, details = [], [], []
    for h in clause.get("horizons") or [horizon]:
        if clause["kind"] == "width_contrast":
            ok, c, d = _eval_width(bar, clause, obs, h)
        elif clause["kind"] == "median_side":
            ok, c, d = _eval_median(bar, clause, obs, h)
        else:
            ok, c, d = _eval_skill(bar, clause, obs, h, arm)
        oks.append(ok)
        cells += c
        details.append(d)
    return {"kind": clause["kind"], "passed": all(oks), "cells": cells, "detail": " · ".join(details)}


# ---------------------------------------------------------------------------
# the member's pre-registration, as its entry states it
# ---------------------------------------------------------------------------

PREREG_FIELD = "Pre-registration"
_JSON_RE = re.compile(r"```json\s*\n(.*?)\n\s*```", re.S)
_PREREG_KEYS = {"class", "arm", "horizon", "floor", "clauses"}


def _check_cell(where: str, cell) -> None:
    if not isinstance(cell, dict) or not cell:
        raise PreregError(f"{where} must be a non-empty object of label → value(s)")


def validate(spec) -> dict:
    """The pre-registration, normalised, or PreregError naming what is wrong.
    Unknown keys are refused rather than ignored: a misspelt floor that fell
    back to the class default would be a looser bar nobody chose."""
    if not isinstance(spec, dict):
        raise PreregError("the pre-registration must be a JSON object")
    extra = set(spec) - _PREREG_KEYS
    if extra:
        raise PreregError(f"unknown key(s) {sorted(extra)}")
    bar = BARS.get(spec.get("class"))
    if bar is None:
        raise PreregError(f"class must be one of {sorted(BARS)}, not {spec.get('class')!r}")
    arm = spec.get("arm")
    if not isinstance(arm, str) or not arm or arm in (bar.benchmark, bar.rival):
        raise PreregError(f"arm must name the candidate, not the benchmark or the rival: {arm!r}")
    horizon = spec.get("horizon", bar.default_horizon)
    if horizon not in bar.horizons:
        raise PreregError(f"horizon must be one of {list(bar.horizons)}, not {horizon!r}")
    floor = dict(class_floor(bar))
    for k, v in (spec.get("floor") or {}).items():
        if k not in floor or not isinstance(v, int):
            raise PreregError(f"floor takes integer report_dates / episodes, not {k!r}: {v!r}")
        if v < floor[k]:
            raise PreregError(f"floor {k} = {v} is looser than the class floor {floor[k]}")
        floor[k] = v
    clauses = spec.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        raise PreregError("clauses must be a non-empty list — an entry with no mechanism clause "
                          "cannot pass the bar (How we explore §9, question 4)")
    for i, c in enumerate(clauses):
        kind = c.get("kind") if isinstance(c, dict) else None
        if kind not in KINDS:
            raise PreregError(f"clause {i}: kind must be one of {sorted(KINDS)}, not {kind!r}")
        missing = KINDS[kind]["required"] - set(c)
        unknown = set(c) - KINDS[kind]["required"] - KINDS[kind]["optional"]
        if missing or unknown:
            raise PreregError(f"clause {i} ({kind}): missing {sorted(missing)}, unknown {sorted(unknown)}")
        for k in ("a", "b", "cell", "null_in"):
            if k in c:
                _check_cell(f"clause {i} ({kind}) `{k}`", c[k])
        if kind == "median_side" and c["side"] not in ("left", "right"):
            raise PreregError(f"clause {i}: side must be left or right, not {c['side']!r}")
        if kind == "width_contrast" and float(c.get("min_ratio", 1.0)) < 1.0:
            raise PreregError(f"clause {i}: min_ratio below 1 is not a widening")
        for h in c.get("horizons") or []:
            if h not in bar.horizons:
                raise PreregError(f"clause {i}: horizon {h!r} is not one of {list(bar.horizons)}")
    return {"class": bar.name, "arm": arm, "horizon": horizon, "floor": floor, "clauses": clauses}


def parse_preregistration(entry: str) -> dict:
    """The `Pre-registration` field of a register entry: prose, then one
    ```json block the class bar reads. The audit stamps it with the entry."""
    import decision_packet as dp
    block = dp.field_block(entry, PREREG_FIELD)
    if block is None:
        raise PreregError(f"no `{PREREG_FIELD}` field")
    found = _JSON_RE.findall(block)
    if len(found) != 1:
        raise PreregError(f"the `{PREREG_FIELD}` field must hold exactly one ```json block, not {len(found)}")
    try:
        spec = json.loads(found[0])
    except json.JSONDecodeError as e:
        raise PreregError(f"its JSON does not parse: {e}") from None
    return validate(spec)


def read(obs: list[dict], prereg: dict, *, sealed: bool) -> dict:
    """The member's read: summary, clauses, verdict. A sealed read under a
    class whose seal is not decided is refused, not scored."""
    bar = BARS[prereg["class"]]
    if sealed and bar.sealed_from is None:
        raise PreregError(f"the {bar.name} class has no decided seal; a sealed read is refused")
    summary = summarize(bar, obs, prereg["arm"], prereg["horizon"])
    clauses = [evaluate_clause(bar, c, obs, prereg["arm"], prereg["horizon"]) for c in prereg["clauses"]]
    return verdict(bar, summary, clauses, sealed=sealed, floor=prereg["floor"])


# ---------------------------------------------------------------------------

def describe(bar: ClassBar) -> str:
    seal = ("not decided — a sealed read is refused" if bar.sealed_from is None
            else f"report dates {bar.sealed_from} → before {bar.sealed_until}, read once")
    return "\n".join([
        f"{bar.name}: vs `{bar.benchmark}`, rival `{bar.rival}`",
        f"  pass clause, both comparators: skill > {MIN_SKILL}, interval clear of zero",
        f"  power: ≥ {bar.min_blocks} blocks of {bar.block} report dates"
        + (f", ≥ {bar.min_report_dates} report dates" if bar.min_report_dates else ""),
        f"  clause cells: ≥ {bar.cell_min_report_dates} report dates in ≥ {bar.cell_min_episodes} episodes",
        f"  horizons {list(bar.horizons)}, default {bar.default_horizon}; coverage nominal {NOMINAL_COVERAGE}",
        f"  seal: {seal}",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("hid", nargs="?", help="a register entry whose pre-registration to parse")
    args = ap.parse_args(argv)
    if args.hid is None:
        print("\n\n".join(describe(b) for b in BARS.values()))
        return 0
    import decision_packet as dp
    root = _HERE.parent
    try:
        spec = parse_preregistration(dp.entry_text((root / dp.HYPOTHESES).read_text(), args.hid))
    except KeyError:
        print(f"{args.hid}: no such entry")
        return 2
    except PreregError as e:
        print(f"{args.hid}: {e}")
        return 1
    print(json.dumps(spec, indent=2, ensure_ascii=False))
    print("\n" + describe(BARS[spec["class"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
