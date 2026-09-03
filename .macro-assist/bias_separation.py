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

Usage:
    python .macro-assist/bias_separation.py
"""

from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
SCORES_DIR = BASE_DIR / "results" / "scores"

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
# Below this many observations in a bucket the comparison is not reported.
MIN_BUCKET_N = 15
# Fixed seed so the same score files always render the same report.
SEED = 7


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def observations(scores: list[dict]) -> list[dict]:
    """Flatten score files into one record per resolved call.

    Returns dicts of {date, window, asset, bias, pct_change, confidence}. Calls
    with no realized move (unscored windows, missing prices) are dropped.
    """
    obs: list[dict] = []
    for report in scores:
        report_date = report.get("report_date")
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
                })
    return obs


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


def bias_separation(scores: list[dict]) -> dict | None:
    """Full separation analysis: per-window and pooled across all windows.

    Each section carries the per-bias return buckets plus the two comparisons
    that matter: Bullish vs Neutral (does calling a direction beat declining to?)
    and Bearish vs Bullish (does the label order the returns at all?).
    """
    obs = _standardize(observations(scores))
    if not obs:
        return None

    def section(sub: list[dict]) -> dict | None:
        if not sub:
            return None
        buckets = _buckets(sub)
        return {
            "n":                len(sub),
            "buckets":          buckets,
            "ordering":         _monotonic(buckets),
            "bullish_vs_neutral": block_permutation(sub, "Bullish", "Neutral"),
            "bearish_vs_bullish": block_permutation(sub, "Bearish", "Bullish"),
        }

    windows = {}
    for window in WINDOWS:
        sec = section([o for o in obs if o["window"] == window])
        if sec:
            windows[window] = sec

    return {
        "overall":  section(obs),
        "windows":  windows,
        "by_asset": _by_asset(obs),
        "params":   {
            "block_days":   BLOCK_DAYS,
            "n_perm":       N_PERM,
            "min_bucket_n": MIN_BUCKET_N,
        },
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _verdict(sec: dict) -> str:
    """One-line read of a section's separation."""
    bn = sec.get("bullish_vs_neutral")
    ordering = sec.get("ordering")
    if bn is None:
        return "not enough data to separate the buckets"
    gap, p = bn["gap"], bn["p_value"]
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
        "",
    ]

    ov = sep["overall"]
    lines += [f"**All windows pooled (n={ov['n']}):** {_verdict(ov)}", ""]

    lines += [
        "| Window | n | Bullish z | Neutral z | Bearish z | Bull−Neut | p | Bear−Bull | p |",
        "|--------|--:|----------:|----------:|----------:|----------:|--:|----------:|--:|",
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
            f"| {bn_gap} | {bn_p} | {eb_gap} | {eb_p} |"
        )
    lines.append("")

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
    if not SCORES_DIR.exists() or not any(SCORES_DIR.glob("*.json")):
        print("No score files found. Run score_predictions.py first.")
        return

    scores = []
    for f in sorted(SCORES_DIR.glob("*.json")):
        try:
            scores.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"  Warning: could not load {f.name}: {exc}")

    sep = bias_separation(scores)
    if not sep:
        print("No resolved calls to analyse.")
        return

    print(f"Loaded {len(scores)} score file(s).\n")
    print("\n".join(separation_md_lines(sep)))


if __name__ == "__main__":
    main()
