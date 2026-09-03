"""
bias_separation.py — Does the stated bias separate realized forward returns?

The accuracy score cannot answer "is the model any good?" in a trending market.
A Neutral call is hard-coded to 0.5, and a Bullish call scores 1.0 whenever the
market happens to rise — so in a sustained bull phase a model that always says
"Bullish" looks competent while carrying no information at all.

This module asks the *discrimination* question instead, which is regime-robust:

    Conditional on what the model said, what did the market actually do?

If Bullish and Neutral calls are followed by the same return distribution, the
label is noise — whatever accuracy the scoreboard shows is market drift, not
skill. If they separate, the label carries information, and the *sign* of the
separation says whether to read it forward or backward.

Method
------
1. Every resolved call contributes its realized `pct_change` at T+5 / T+10 / T+20.
   The sign convention is uniform: positive `pct_change` is always the direction a
   Bullish call claims (score_predictions.py scores 10Y yield on level change, so
   "Bullish" = yield up = positive pct_change there too).
2. Returns are standardized within (window, asset) before pooling. Bitcoin moves
   ~10% in a fortnight and DXY ~0.5%; pooling raw percentages would make the
   result an artefact of which assets the model happened to call Bullish.
3. Significance uses a **block permutation test**. Reports are daily but the
   T+20 window spans 20 trading days, so consecutive observations share almost
   their entire evaluation window. Permuting individual labels would treat ~2000
   heavily overlapping observations as independent and return absurdly small
   p-values. Contiguous blocks of report-dates are permuted instead, which keeps
   the overlap intact under the null.

The block count is reported alongside every p-value: with a few months of daily
reports there are only a handful of independent blocks, so these p-values are
indicative, not confirmatory. Lead with the effect sizes and their consistency
across assets and horizons.

Arm scoping
-----------
The pipeline runs several prediction arms (`market`, `exogenous`, `kimi`) and
they write **separate score files that share a `report_date`** — `2026-08-03.json`,
`2026-08-03__kimi.json` and `2026-08-03__exogenous.json` all carry
`report_date: 2026-08-03`. Two consequences, both learned the hard way [KB-023]:

  * Any dict or join keyed on `report_date` silently overwrites one arm's
    metadata with another's. Attribution must key on the **file**, which is why
    `observations()` reads `arm`/`profile` off each report as it flattens it.
  * Pooling arms measures three different systems as if they were one. Analysis
    is therefore scoped to a single arm (default `market`, the production
    pipeline); pass `arm=None` to deliberately pool.

Usage:
    python .macro-assist/bias_separation.py            # market arm
    python .macro-assist/bias_separation.py --arm all  # pool every arm
"""

from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
SCORES_DIR = BASE_DIR / "results" / "scores"

# The production prediction arm. Analyses default to this one so a result is
# never an average over three different systems (see "Arm scoping" above).
PRIMARY_ARM = "market"

WINDOWS = ["t5", "t10", "t20"]
WINDOW_LABELS = {"t5": "T+5 (1 week)", "t10": "T+10 (2 weeks)", "t20": "T+20 (1 month)"}
ASSET_ORDER = ["S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin"]
BIASES = ["Bullish", "Neutral", "Bearish"]

# Block length in report-dates. 21 ≈ the T+20 horizon, so two observations in
# different blocks never share an evaluation window.
BLOCK_DAYS = 21
# Permutation draws. 2000 keeps the daily CI summary fast; the resolution floor
# is ~1/2001, well below any threshold worth acting on.
N_PERM = 2000
# Bootstrap draws for the gap confidence interval. The interval is what separates
# "no effect" from "not enough data to see one" (KB-023) — see block_bootstrap_ci.
N_BOOT = 2000
# Below this many observations in a bucket the comparison is not reported.
MIN_BUCKET_N = 15
# Fixed seed so the same score files always render the same report.
SEED = 7


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

# score_predictions.py stamps this literal string on fields that predate the
# experiment that introduced them, so "absent" arrives as a value, not a gap.
UNTAGGED = "unknown"


def arm_of(report: dict) -> str:
    """The arm a score file belongs to.

    An untagged `arm` means the file predates the arm machinery, which only ever
    ran the production pipeline — so it resolves to PRIMARY_ARM rather than to a
    separate bucket that would silently drop the entire early history from every
    arm-scoped analysis.
    """
    v = report.get("arm")
    return PRIMARY_ARM if not v or v == UNTAGGED else v


# The untagged pre-WP-16.B population. Named rather than left as UNTAGGED
# because it is the comparator the loosened arm is measured against, and the
# commitment metric has always called it this.
BASELINE_PROFILE = "baseline"


def profile_of(report: dict) -> str:
    """The run profile a score file belongs to.

    An untagged `profile` means the file predates the WP-16.B experiment and so
    belongs to the control population. Resolving it to "baseline" rather than
    leaving it as UNTAGGED matters twice over: `calibration_by` drops the untagged
    bucket, so an unresolved value silently rendered the profile A/B as a single
    row with nothing to compare; and "baseline" is the label the commitment metric
    has always used for exactly this population.
    """
    v = report.get("profile")
    return BASELINE_PROFILE if not v or v == UNTAGGED else v


def observations(scores: list[dict]) -> list[dict]:
    """Flatten score files into one record per resolved call.

    Returns dicts of {date, window, asset, bias, pct_change, confidence, arm,
    profile}. Calls with no realized move (unscored windows, missing prices) are
    dropped.

    `arm` and `profile` are read off each report as it is flattened, never
    looked up by `report_date` afterwards — sibling arms reuse the same date and
    a date-keyed lookup would mis-attribute them (see "Arm scoping").
    """
    obs: list[dict] = []
    for report in scores:
        report_date = report.get("report_date")
        arm     = arm_of(report)
        profile = profile_of(report)
        for window, wdata in report.get("windows", {}).items():
            if window not in WINDOWS:
                continue
            for asset, adata in wdata.get("assets", {}).items():
                pct = adata.get("pct_change")
                if pct is None or adata.get("score") is None:
                    continue
                obs.append({
                    "date":       report_date,
                    "window":     window,
                    "asset":      asset,
                    "bias":       adata.get("bias", "Neutral"),
                    "pct_change": float(pct),
                    "confidence": adata.get("confidence", 50),
                    "arm":        arm,
                    "profile":    profile,
                })
    return obs


def arm_composition(scores: list[dict]) -> dict:
    """{arm: {n_reports, n_calls, first_date, last_date}} — the provenance block.

    Rendered with every result so a pooled number can never again be read as if
    it described one system.
    """
    out: dict = {}
    for report in scores:
        arm = arm_of(report)
        rec = out.setdefault(arm, {"n_reports": 0, "n_calls": 0,
                                   "first_date": None, "last_date": None})
        rec["n_reports"] += 1
        rec["n_calls"] += len(observations([report]))
        d = report.get("report_date")
        if d:
            rec["first_date"] = min(rec["first_date"] or d, d)
            rec["last_date"]  = max(rec["last_date"] or d, d)
    return out


def filter_arm(scores: list[dict], arm: str | None = PRIMARY_ARM) -> list[dict]:
    """Restrict score files to one arm. `arm=None` pools every arm."""
    if arm is None:
        return list(scores)
    return [s for s in scores if arm_of(s) == arm]


def _standardize(obs: list[dict]) -> list[dict]:
    """Attach a `z` field: pct_change standardized within (window, asset).

    Pooling across assets requires this — a +3% Bitcoin move and a +3% DXY move
    are not the same event. Groups too small or with no dispersion are dropped
    rather than divided by a fabricated spread.
    """
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for o in obs:
        groups[(o["window"], o["asset"])].append(o["pct_change"])

    moments: dict[tuple[str, str], tuple[float, float]] = {}
    for key, vals in groups.items():
        if len(vals) < 3:
            continue
        sd = st.pstdev(vals)
        if sd > 0:
            moments[key] = (st.mean(vals), sd)

    out = []
    for o in obs:
        m = moments.get((o["window"], o["asset"]))
        if m is None:
            continue
        mean, sd = m
        out.append({**o, "z": (o["pct_change"] - mean) / sd})
    return out


# ---------------------------------------------------------------------------
# Block permutation test
# ---------------------------------------------------------------------------

def _blocks(obs: list[dict], block_days: int = BLOCK_DAYS) -> list[list[dict]]:
    """Group observations into contiguous blocks of report-dates."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        by_date[o["date"]].append(o)
    dates = sorted(by_date)
    return [
        [o for d in dates[i:i + block_days] for o in by_date[d]]
        for i in range(0, len(dates), block_days)
    ]


def _gap(obs: list[dict], a: str, b: str, labels: list[str] | None = None) -> float | None:
    """Mean standardized return under bias `a` minus that under bias `b`."""
    za, zb = [], []
    for i, o in enumerate(obs):
        lab = o["bias"] if labels is None else labels[i]
        if lab == a:
            za.append(o["z"])
        elif lab == b:
            zb.append(o["z"])
    if not za or not zb:
        return None
    return st.mean(za) - st.mean(zb)


def block_permutation(obs: list[dict], a: str, b: str,
                      n_perm: int = N_PERM, block_days: int = BLOCK_DAYS,
                      seed: int = SEED) -> dict | None:
    """Two-sided block-permutation test on the `a` minus `b` return gap.

    Under the null the bias labels carry no information about forward returns.
    Each block draws its labels from another block's label pool, so the label
    *composition* of a period and the overlap structure of returns both survive
    the shuffle — only the pairing between them is broken.

    Returns {gap, p_value, n_a, n_b, n_blocks}, or None if either bucket is
    too small to compare.
    """
    n_a = sum(1 for o in obs if o["bias"] == a)
    n_b = sum(1 for o in obs if o["bias"] == b)
    if n_a < MIN_BUCKET_N or n_b < MIN_BUCKET_N:
        return None

    blocks = _blocks(obs, block_days)
    if len(blocks) < 2:
        return None

    flat = [o for blk in blocks for o in blk]
    observed = _gap(flat, a, b)
    if observed is None:
        return None

    pools = [[o["bias"] for o in blk] for blk in blocks]
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        order = list(range(len(blocks)))
        rng.shuffle(order)
        labels: list[str] = []
        for i, blk in enumerate(blocks):
            pool = pools[order[i]][:]
            rng.shuffle(pool)
            # Blocks differ in size (holidays, missing prices); cycle to fill.
            labels.extend(pool[j % len(pool)] for j in range(len(blk)))
        g = _gap(flat, a, b, labels)
        if g is not None and abs(g) >= abs(observed):
            extreme += 1

    return {
        "gap":      round(observed, 4),
        "p_value":  round((extreme + 1) / (n_perm + 1), 4),
        "n_a":      n_a,
        "n_b":      n_b,
        "n_blocks": len(blocks),
    }


def block_bootstrap_ci(obs: list[dict], a: str, b: str,
                      n_boot: int = N_BOOT, block_days: int = BLOCK_DAYS,
                      seed: int = SEED, alpha: float = 0.05) -> dict | None:
    """Block-bootstrap confidence interval for the `a` minus `b` return gap.

    The permutation test answers "could this gap arise under the null?" — it says
    nothing about how *wide* the estimate is. On a short arm that distinction is
    the whole story: the loosened arm's Bull-Neut gap of -0.008 (p=0.93) reads as
    "no separation" until the interval shows it spans [-0.250, +0.424] and so
    comfortably contains the inverted baseline estimate [KB-023]. A high p-value
    on few blocks means *underpowered*, not *null*, and only the interval can
    tell the two apart.

    Resamples whole blocks of report-dates with replacement, preserving the
    within-block overlap structure that makes daily T+20 observations dependent.
    """
    n_a = sum(1 for o in obs if o["bias"] == a)
    n_b = sum(1 for o in obs if o["bias"] == b)
    if n_a < MIN_BUCKET_N or n_b < MIN_BUCKET_N:
        return None

    by_date: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        by_date[o["date"]].append(o)
    dates = sorted(by_date)
    blocks = [dates[i:i + block_days] for i in range(0, len(dates), block_days)]
    if len(blocks) < 2:
        return None

    rng = random.Random(seed)
    gaps: list[float] = []
    for _ in range(n_boot):
        flat = [o for blk in (rng.choice(blocks) for _ in blocks)
                for d in blk for o in by_date[d]]
        g = _gap(flat, a, b)
        if g is not None:
            gaps.append(g)
    if len(gaps) < n_boot // 2:
        return None

    gaps.sort()
    lo = gaps[int((alpha / 2) * len(gaps))]
    hi = gaps[min(int((1 - alpha / 2) * len(gaps)), len(gaps) - 1)]
    return {"lo": round(lo, 4), "hi": round(hi, 4),
            "width": round(hi - lo, 4), "n_boot": len(gaps)}


def _compare(obs: list[dict], a: str, b: str) -> dict | None:
    """Permutation test plus bootstrap interval for one bucket comparison."""
    test = block_permutation(obs, a, b)
    if test is None:
        return None
    ci = block_bootstrap_ci(obs, a, b)
    if ci:
        test = {**test, "ci_lo": ci["lo"], "ci_hi": ci["hi"], "ci_width": ci["width"]}
    return test


def date_overlap(scores: list[dict], field: str = "profile") -> dict:
    """Shared report-dates between every pair of values of `field`.

    The guardrail [KB-023] exists for: `MACRO_PROFILE` was switched in one block,
    so the baseline and loosened arms share **zero** report-dates and "arm" and
    "market period" are the same partition of the data. No test can separate them,
    and nothing in the output said so. Now it does.
    """
    resolve = {"profile": profile_of, "arm": arm_of}.get(
        field, lambda r: r.get(field) or "unknown")

    dates: dict[str, set] = defaultdict(set)
    for s in scores:
        d = s.get("report_date")
        if d:
            dates[resolve(s)].add(d)

    pairs = {}
    keys = sorted(dates)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            shared = dates[a] & dates[b]
            pairs[f"{a}|{b}"] = {
                "n_shared": len(shared),
                "n_a": len(dates[a]),
                "n_b": len(dates[b]),
                "confounded": len(shared) == 0,
                "span_a": [min(dates[a]), max(dates[a])] if dates[a] else None,
                "span_b": [min(dates[b]), max(dates[b])] if dates[b] else None,
            }
    return pairs


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _buckets(obs: list[dict]) -> dict:
    """Per-bias n, mean/median standardized return, and mean raw pct_change."""
    out = {}
    for bias in BIASES:
        vals = [o for o in obs if o["bias"] == bias]
        if not vals:
            out[bias] = {"n": 0, "mean_z": None, "median_z": None, "mean_pct": None}
            continue
        z = [o["z"] for o in vals]
        out[bias] = {
            "n":        len(vals),
            "mean_z":   round(st.mean(z), 3),
            "median_z": round(st.median(z), 3),
            "mean_pct": round(st.mean([o["pct_change"] for o in vals]), 3),
        }
    return out


def _monotonic(buckets: dict) -> str | None:
    """Classify the Bearish / Neutral / Bullish ordering of realized returns.

    'aligned'  — Bullish > Neutral > Bearish: the label reads forward.
    'inverted' — Bearish > Neutral > Bullish: the label reads backward.
    'mixed'    — no monotone ordering.
    """
    vals = {b: buckets[b]["mean_z"] for b in BIASES}
    if any(v is None for v in vals.values()):
        return None
    if vals["Bullish"] > vals["Neutral"] > vals["Bearish"]:
        return "aligned"
    if vals["Bearish"] > vals["Neutral"] > vals["Bullish"]:
        return "inverted"
    return "mixed"


def _by_asset(obs: list[dict]) -> dict:
    """Per-asset mean raw pct_change per bias — the sanity check behind the pool."""
    out = {}
    for asset in ASSET_ORDER:
        sub = [o for o in obs if o["asset"] == asset]
        if not sub:
            continue
        entry = {}
        for bias in BIASES:
            vals = [o["pct_change"] for o in sub if o["bias"] == bias]
            entry[bias] = {
                "n":        len(vals),
                "mean_pct": round(st.mean(vals), 3) if vals else None,
            }
        out[asset] = entry
    return out


def _section(sub: list[dict]) -> dict | None:
    """Buckets, ordering and the two comparisons that matter, for one subset."""
    if not sub:
        return None
    buckets = _buckets(sub)
    return {
        "n":                  len(sub),
        "n_dates":            len({o["date"] for o in sub}),
        "buckets":            buckets,
        "ordering":           _monotonic(buckets),
        "bullish_vs_neutral": _compare(sub, "Bullish", "Neutral"),
        "bearish_vs_bullish": _compare(sub, "Bearish", "Bullish"),
    }


def bias_separation(scores: list[dict], arm: str | None = PRIMARY_ARM) -> dict | None:
    """Full separation analysis: per-window and pooled across all windows.

    Each section carries the per-bias return buckets plus the two comparisons
    that matter: Bullish vs Neutral (does calling a direction beat declining to?)
    and Bearish vs Bullish (does the label order the returns at all?).

    Scoped to a single `arm` (default `market`) so the result describes one
    system rather than an average of three [KB-023]; `arm=None` pools them. The
    `provenance` block records what was included and what was dropped, and
    `profile_overlap` flags any profile A/B whose arms share no report-dates —
    the confound that made the first loosened-vs-baseline read unusable.
    """
    scoped = filter_arm(scores, arm)
    obs = _standardize(observations(scoped))
    if not obs:
        return None

    # Standardize once over the scoped pool so every sub-section below (windows,
    # profiles) is expressed on the same z scale and the numbers are comparable.
    windows = {}
    for window in WINDOWS:
        sec = _section([o for o in obs if o["window"] == window])
        if sec:
            windows[window] = sec

    profiles = {}
    for prof in sorted({o["profile"] for o in obs}):
        sec = _section([o for o in obs if o["profile"] == prof])
        if sec:
            profiles[prof] = sec

    return {
        "overall":  _section(obs),
        "windows":  windows,
        "profiles": profiles,
        "by_asset": _by_asset(obs),
        "provenance": {
            "arm":         arm or "all (pooled)",
            "composition": arm_composition(scores),
            "n_reports_used": len(scoped),
            "n_reports_total": len(scores),
        },
        "profile_overlap": date_overlap(scoped, "profile"),
        "params":   {
            "block_days":   BLOCK_DAYS,
            "n_perm":       N_PERM,
            "n_boot":       N_BOOT,
            "min_bucket_n": MIN_BUCKET_N,
        },
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

# A gap interval wider than this cannot distinguish "no effect" from an effect
# the size of the ones already measured (|Bull-Neut| ~ 0.24 in KB-022), so a
# high p-value on such a section means underpowered, not null.
INCONCLUSIVE_CI_WIDTH = 0.40


def _verdict(sec: dict) -> str:
    """One-line read of a section's separation."""
    bn = sec.get("bullish_vs_neutral")
    ordering = sec.get("ordering")
    if bn is None:
        return "not enough data to separate the buckets"
    gap, p = bn["gap"], bn["p_value"]
    ci_lo, ci_hi = bn.get("ci_lo"), bn.get("ci_hi")
    # Absence of evidence is not evidence of absence: only call it "no
    # separation" when the interval is tight enough to have excluded one [KB-023].
    if p > 0.10 and ci_lo is not None and (ci_hi - ci_lo) > INCONCLUSIVE_CI_WIDTH:
        return (
            f"**inconclusive — underpowered.** The gap is {gap:+.3f} (p={p:.2f}), but "
            f"its 95% interval spans [{ci_lo:+.3f}, {ci_hi:+.3f}] — wide enough to "
            "contain effects as large as any measured so far. This says the sample "
            "cannot see a separation, *not* that there isn't one"
        )
    if p > 0.10 and abs(gap) < 0.10:
        return (
            "**no separation** — Bullish and Neutral calls are followed by the same "
            "returns, so the label carries no information"
        )
    if ordering == "inverted":
        return (
            "**inverted separation** — the label orders returns backwards "
            "(Bearish > Neutral > Bullish); it is informative, but read forward it is "
            "worse than useless"
        )
    if ordering == "aligned":
        return "**aligned separation** — the label orders returns the way it claims to"
    return "**mixed** — the buckets differ but do not order monotonically"


def _ci(test: dict | None) -> str:
    """Render a comparison's bootstrap interval, or an em dash."""
    if not test or test.get("ci_lo") is None:
        return "—"
    return f"[{test['ci_lo']:+.2f}, {test['ci_hi']:+.2f}]"


def _provenance_md_lines(sep: dict) -> list[str]:
    """Which arm this section describes, and what was left out."""
    prov = sep.get("provenance")
    if not prov:
        return []
    comp = prov.get("composition") or {}
    lines = [f"**Arm:** `{prov['arm']}` "
             f"({prov['n_reports_used']} of {prov['n_reports_total']} score files).",
             ""]
    if len(comp) > 1:
        lines += [
            "> Arms are scored separately — they are different systems, and the score",
            "> files share a `report_date`, so pooling them (or joining on the date)",
            "> silently mixes them [KB-023].",
            "",
            "| Arm | reports | resolved calls | span |",
            "|-----|--------:|---------------:|------|",
        ]
        for arm, c in sorted(comp.items()):
            span = (f"{c['first_date']} → {c['last_date']}"
                    if c["first_date"] else "—")
            mark = " **(this section)**" if arm == prov["arm"] else ""
            lines.append(f"| `{arm}`{mark} | {c['n_reports']} | {c['n_calls']} | {span} |")
        lines.append("")
    return lines


def _profile_md_lines(sep: dict) -> list[str]:
    """Per-profile separation, with a hard warning when the arms never overlap."""
    profiles = sep.get("profiles") or {}
    if len(profiles) < 2:
        return []

    lines = [
        "### By run profile *(WP-16.B conviction-floor A/B)*",
        "",
        f"> `{BASELINE_PROFILE}` is the untagged pre-WP-16.B population — the control the",
        "> loosened arm is measured against.",
        "",
        "| Profile | n | dates | Bullish z | Neutral z | Bull−Neut | 95% CI | p |",
        "|---------|--:|------:|----------:|----------:|----------:|:------:|--:|",
    ]
    for name, sec in sorted(profiles.items()):
        b = sec["buckets"]

        def z(bias: str) -> str:
            v = b[bias]["mean_z"]
            return f"{v:+.3f} (n={b[bias]['n']})" if v is not None else "—"

        bn = sec.get("bullish_vs_neutral")
        gap = f"{bn['gap']:+.3f}" if bn else "—"
        pv = f"{bn['p_value']:.3f}" if bn else "—"
        lines.append(
            f"| `{name}` | {sec['n']} | {sec.get('n_dates', '—')} | {z('Bullish')} "
            f"| {z('Neutral')} | {gap} | {_ci(bn)} | {pv} |"
        )
    lines.append("")

    confounded = [(k, v) for k, v in (sep.get("profile_overlap") or {}).items()
                  if v.get("confounded")]
    for pair, info in confounded:
        a, b = pair.split("|")
        span_a = " → ".join(info["span_a"]) if info["span_a"] else "?"
        span_b = " → ".join(info["span_b"]) if info["span_b"] else "?"
        lines += [
            f"> ⛔ **`{a}` and `{b}` share zero report-dates** "
            f"(`{a}`: {span_a}; `{b}`: {span_b}). The profile was switched in one "
            "block, so *profile* and *market period* are the same partition of the "
            "data — no test above can tell them apart, and the rows should not be "
            "read as an A/B. Assign the profile per report-date (alternating) to "
            "make this comparison mean anything [KB-023, WP-21.B].",
            "",
        ]
    return lines


def separation_md_lines(sep: dict | None) -> list[str]:
    """Render the bias-separation section of the accuracy report."""
    if not sep or not sep.get("overall"):
        return []

    p = sep["params"]
    lines = [
        "---",
        "",
        "## Bias Separation — does the call predict the move?",
        "",
        "> The accuracy score cannot answer this in a trending market: Neutral is",
        "> hard-coded to 0.5 and Bullish scores 1.0 whenever the market rises, so a",
        "> permanently-bullish model looks skilled while saying nothing. This section",
        "> asks the regime-robust question instead — **conditional on what the model",
        "> said, what did the market actually do?**",
        ">",
        "> Returns are standardized within (window, asset), so **z** is in standard",
        "> deviations of that asset's own move over that horizon. Positive z is always",
        "> the direction a Bullish call claims.",
        ">",
        f"> p-values come from a **block permutation test** ({p['block_days']}-day blocks,",
        f"> {p['n_perm']} draws) because daily reports with a T+20 horizon overlap almost",
        "> completely. Blocks are few, so treat p as indicative — the signal to trust is",
        "> whether the effect holds its sign across assets and horizons.",
        ">",
        f"> Each gap also carries a **95% block-bootstrap interval** ({p.get('n_boot', N_BOOT)}",
        "> draws). Read it before the p-value: on a short sample a high p means the",
        "> interval is too wide to see an effect, not that there is none [KB-023].",
        "",
    ]

    lines += _provenance_md_lines(sep)

    ov = sep["overall"]
    lines += [f"**All windows pooled (n={ov['n']}):** {_verdict(ov)}", ""]

    lines += [
        "| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | 95% CI | p | Bear−Bull | p |",
        "|--------|--:|----------:|----------:|----------:|----------:|:------:|--:|----------:|--:|",
    ]
    for key, label in [("overall", "**all**")] + [(w, WINDOW_LABELS[w]) for w in WINDOWS]:
        sec = ov if key == "overall" else sep["windows"].get(key)
        if not sec:
            continue
        b = sec["buckets"]

        def z(bias: str) -> str:
            v = b[bias]["mean_z"]
            return f"{v:+.3f} (n={b[bias]['n']})" if v is not None else "—"

        def cmp(test: dict | None) -> tuple[str, str]:
            if not test:
                return "—", "—"
            return f"{test['gap']:+.3f}", f"{test['p_value']:.3f}"

        bn_gap, bn_p = cmp(sec.get("bullish_vs_neutral"))
        eb_gap, eb_p = cmp(sec.get("bearish_vs_bullish"))
        lines.append(
            f"| {label} | {sec['n']} | {z('Bullish')} | {z('Neutral')} | {z('Bearish')} "
            f"| {bn_gap} | {_ci(sec.get('bullish_vs_neutral'))} | {bn_p} | {eb_gap} | {eb_p} |"
        )
    lines.append("")

    lines += _profile_md_lines(sep)

    # Per-asset raw means — confirms the pooled result is not one asset's doing.
    lines += [
        "### Mean realized move by call, per asset *(raw %, all windows)*",
        "",
        "| Asset | Bullish | Neutral | Bearish |",
        "|-------|--------:|--------:|--------:|",
    ]
    for asset in ASSET_ORDER:
        entry = sep["by_asset"].get(asset)
        if not entry:
            continue
        cells = []
        for bias in BIASES:
            v, n = entry[bias]["mean_pct"], entry[bias]["n"]
            cells.append(f"{v:+.2f}% (n={n})" if v is not None else "—")
        lines.append(f"| {asset} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.append("")

    ordering = ov.get("ordering")
    if ordering == "inverted":
        lines += [
            "> ⚠️ **The ordering is inverted.** Realized returns run "
            "Bearish > Neutral > Bullish — the model's calls are informative but "
            "point the wrong way. This is invisible to the accuracy score, which "
            "rewards a Bullish call for any rise. Before reading it as a contrarian "
            "signal, check the per-asset table above: an inversion carried by one or "
            "two high-volatility assets, or by one stretch of the sample, is a "
            "small-sample artefact rather than a tradable edge.",
            "",
        ]
    elif ordering == "aligned":
        lines += [
            "> The ordering is aligned: Bullish calls precede the strongest moves and "
            "Bearish calls the weakest. This is the signal the accuracy score is "
            "supposed to be measuring, confirmed independently of the market regime.",
            "",
        ]

    return lines


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", default=PRIMARY_ARM,
                    help=f"prediction arm to analyse (default {PRIMARY_ARM!r}); "
                         "'all' pools every arm, which mixes different systems")
    args = ap.parse_args()
    arm = None if args.arm == "all" else args.arm

    if not SCORES_DIR.exists() or not any(SCORES_DIR.glob("*.json")):
        print("No score files found. Run score_predictions.py first.")
        return

    scores = []
    for f in sorted(SCORES_DIR.glob("*.json")):
        try:
            scores.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"  Warning: could not load {f.name}: {exc}")

    sep = bias_separation(scores, arm=arm)
    if not sep:
        print(f"No resolved calls to analyse for arm {args.arm!r}.")
        return

    print(f"Loaded {len(scores)} score file(s).\n")
    print("\n".join(separation_md_lines(sep)))


if __name__ == "__main__":
    main()
