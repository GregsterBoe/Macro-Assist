"""
summarize_accuracy.py — Aggregate prediction scores into accuracy stats.

Reads all JSON score files from results/scores/, computes per-asset and
per-window accuracy, and writes:
  - .macro-assist/data/accuracy_summary.json  (machine-readable, read by daily pipeline)
  - results/accuracy_summary.json             (copy for human review / vault)
  - results/accuracy_report.md                (human-readable markdown)

Arm scoping
-----------
Several prediction arms (`market`, `exogenous`, `kimi`) write score files, and
sibling arms share a `report_date`. The headline numbers are therefore scoped to
the **production `market` arm** — pooling three different systems into one
"pipeline accuracy" figure describes none of them, and joining on the date mixes
their metadata outright [KB-023]. The other arms are not discarded: they get
their own rows in the arm A/B (`calibration_by_arm`), which is the one place a
cross-arm comparison belongs.

Usage:
    python .macro-assist/summarize_accuracy.py            # market arm
    python .macro-assist/summarize_accuracy.py --arm all  # pool every arm
"""

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from bias_separation import (
    PRIMARY_ARM,
    arm_composition,
    arm_of,
    bias_separation,
    date_overlap,
    filter_arm,
    profile_of,
    separation_md_lines,
)
from versions import MIN_FEEDBACK_VERSION, PIPELINE_VERSION

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).resolve().parent.parent
SCORES_DIR = BASE_DIR / "results" / "scores"

# accuracy_summary.json lives in .macro-assist/data/ so it is tracked in git
# and available to collect_and_analyze.py in the daily CI workflow.
DATA_DIR          = Path(__file__).resolve().parent / "data"
SUMMARY_JSON      = DATA_DIR / "accuracy_summary.json"
SUMMARY_JSON_COPY = BASE_DIR / "results" / "accuracy_summary.json"
SUMMARY_MD        = BASE_DIR / "results" / "accuracy_report.md"

WINDOWS = ["t5", "t10", "t20"]
WINDOW_LABELS = {"t5": "T+5 (1 week)", "t10": "T+10 (2 weeks)", "t20": "T+20 (1 month)"}

# Asset display order
ASSET_ORDER = ["S&P 500", "Gold", "WTI Oil", "10Y Treasury Yield", "DXY", "Bitcoin"]

# Number of most-recent pipeline versions shown in per-version accuracy section.
TRACK_LATEST_N_VERSIONS = 5


def _version_key(v: str) -> tuple[int, ...]:
    """Convert 'v1.0' → (1, 0) for numeric comparison."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except (ValueError, AttributeError):
        return (0, 0)


def _scan_report_versions() -> dict[str, int]:
    """Return {agent_version: n_reports} by scanning all *-macro.md frontmatters."""
    counts: dict[str, int] = {}
    for path in (BASE_DIR / "results").rglob("*-macro.md"):
        m = re.search(r"^agent_version:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            v = m.group(1)
            counts[v] = counts.get(v, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_scores() -> list[dict]:
    files = sorted(SCORES_DIR.glob("*.json"))
    scores = []
    for f in files:
        try:
            scores.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"  Warning: could not load {f.name}: {exc}")
    return scores


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(scores: list[dict], min_version: str | None = None) -> dict:
    """
    Build nested stats: window -> asset -> {n, accuracy, avg_confidence, ...}
    Also compute directional accuracy: only Bullish/Bearish calls on
    non-flat moves (score is 0 or 1, not 0.5).

    If min_version is given (e.g. "v0.3"), only reports from that version
    onward are included in the stats.
    """
    if min_version is not None:
        min_vk = _version_key(min_version)
        scores = [s for s in scores if _version_key(s.get("agent_version", "v0.0")) >= min_vk]

    # Collect raw observations: window -> asset -> list of {score, confidence, bias, pct_change}
    obs: dict[str, dict[str, list]] = {w: defaultdict(list) for w in WINDOWS}

    for report in scores:
        for window, wdata in report.get("windows", {}).items():
            for asset, adata in wdata.get("assets", {}).items():
                if adata.get("score") is None:
                    continue
                obs[window][asset].append({
                    "score":      adata["score"],
                    "confidence": adata["confidence"],
                    "bias":       adata["bias"],
                    "pct_change": adata.get("pct_change"),
                })

    result = {}
    for window in WINDOWS:
        window_stats = {}
        all_scores = []

        for asset in ASSET_ORDER:
            items = obs[window].get(asset, [])
            if not items:
                continue

            scores_all = [i["score"] for i in items]
            avg_score  = sum(scores_all) / len(scores_all)
            avg_conf   = sum(i["confidence"] for i in items) / len(items)

            # Directional accuracy: only score 0 or 1 outcomes (exclude 0.5)
            directional = [i for i in items if i["score"] in (0.0, 1.0)]
            dir_acc = (
                sum(i["score"] for i in directional) / len(directional)
                if directional else None
            )

            window_stats[asset] = {
                "n":               len(items),
                "accuracy":        round(avg_score, 3),
                "directional_acc": round(dir_acc, 3) if dir_acc is not None else None,
                "directional_n":   len(directional),
                "avg_confidence":  round(avg_conf, 1),
            }
            all_scores.extend(scores_all)

        overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else None
        dir_all  = [s for s in all_scores if s in (0.0, 1.0)]
        overall_dir = round(sum(dir_all) / len(dir_all), 3) if dir_all else None

        result[window] = {
            "n_reports":        len([s for s in scores if window in s.get("windows", {})]),
            "overall_accuracy": overall,
            "overall_dir_acc":  overall_dir,
            "by_asset":         window_stats,
        }

    return result


# ---------------------------------------------------------------------------
# Calibration (WP-16.B.2) — Brier score + reliability diagram
# ---------------------------------------------------------------------------
#
# A directional call carries a stated confidence (0-100), which we read as the
# model's P(this call is correct). For decisive calls (score 0 or 1 — Bullish/
# Bearish on a non-flat move) the realized outcome is binary, so confidence is a
# probability forecast we can score for *calibration*, not just accuracy:
#
#   Brier = mean((confidence/100 - outcome)^2)         lower is better; 0 = perfect
#   Base-rate forecast Brier = p*(1-p)                  "always predict the base rate"
#   Brier Skill Score = 1 - Brier/Brier_ref             >0 ⇒ confidence beats the base rate
#   ECE  = sum_bins (n_bin/N) * |hit_rate - mean_conf|  expected calibration error
#
# The reliability diagram bins calls by stated confidence and compares mean
# predicted confidence to the realized hit-rate per bin (gap > 0 ⇒ underconfident,
# gap < 0 ⇒ overconfident). Neutral / flat (score 0.5) calls are excluded: there
# is no binary directional outcome to calibrate against.

CALIB_BIN_EDGES = [0, 50, 60, 70, 80, 90, 100]


def _brier_and_reliability(items: list[dict]) -> dict | None:
    """Compute Brier / BSS / ECE + reliability bins from decisive observations.

    `items` is a list of {"confidence": int 0-100, "score": float}. Only score
    in {0.0, 1.0} (decisive directional calls) is used. Returns None if no
    decisive calls are present.
    """
    decisive = [i for i in items if i["score"] in (0.0, 1.0)]
    n = len(decisive)
    if n == 0:
        return None

    probs    = [i["confidence"] / 100.0 for i in decisive]
    outcomes = [float(i["score"]) for i in decisive]  # 1.0 correct / 0.0 wrong

    brier     = sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n
    base_rate = sum(outcomes) / n
    brier_ref = base_rate * (1.0 - base_rate)  # Brier of the constant base-rate forecast
    bss       = (1.0 - brier / brier_ref) if brier_ref > 0 else None

    bins: list[dict] = []
    ece = 0.0
    for lo, hi in zip(CALIB_BIN_EDGES[:-1], CALIB_BIN_EDGES[1:]):
        # Bins are [lo, hi); the final bin includes 100.
        in_bin = [
            (p, o) for p, o in zip(probs, outcomes)
            if lo <= p * 100 < hi or (hi == CALIB_BIN_EDGES[-1] and p * 100 == hi)
        ]
        if not in_bin:
            continue
        bn        = len(in_bin)
        mean_conf = sum(p for p, _ in in_bin) / bn
        hit_rate  = sum(o for _, o in in_bin) / bn
        ece += (bn / n) * abs(hit_rate - mean_conf)
        bins.append({
            "range":     f"{lo}-{hi}",
            "n":         bn,
            "mean_conf": round(mean_conf, 3),
            "hit_rate":  round(hit_rate, 3),
            "gap":       round(hit_rate - mean_conf, 3),  # + underconfident / - overconfident
        })

    return {
        "n":                 n,
        "brier":             round(brier, 4),
        "base_rate":         round(base_rate, 3),
        "brier_skill_score": round(bss, 3) if bss is not None else None,
        "ece":               round(ece, 4),
        "bins":              bins,
    }


def calibration(scores: list[dict], min_version: str | None = None) -> dict:
    """Per-window + overall calibration stats from the score files.

    Pools decisive calls across assets within each window (calibration is a
    property of the confidence numbers, not the asset). `overall` pools every
    window together for the headline figure.
    """
    if min_version is not None:
        min_vk = _version_key(min_version)
        scores = [s for s in scores if _version_key(s.get("agent_version", "v0.0")) >= min_vk]

    per_window: dict = {}
    all_items: list[dict] = []
    for window in WINDOWS:
        items: list[dict] = []
        for report in scores:
            wdata = report.get("windows", {}).get(window)
            if not wdata:
                continue
            for adata in wdata.get("assets", {}).values():
                if adata.get("score") is None:
                    continue
                items.append({"confidence": adata["confidence"], "score": adata["score"]})
        per_window[window] = _brier_and_reliability(items)
        all_items.extend(items)

    return {"windows": per_window, "overall": _brier_and_reliability(all_items)}


def calibration_by(scores: list[dict], field: str,
                   resolve=None) -> dict:
    """Overall calibration split by any score-file frontmatter field.

    Returns {value: <overall calib>} for each distinct value of `field` that has
    scored data, ignoring the 'unknown'/absent bucket (pre-experiment notes).
    The A/B readout for "does this arm calibrate better?".

    `resolve` overrides how a report's value is read, for fields where *absent*
    carries meaning rather than being a gap — a missing `profile` is the control
    arm, not an unknown one, and dropping it left the profile A/B with a single
    row and nothing to compare (see `profile_of`).
    """
    get = resolve or (lambda s: s.get(field))
    arms: dict = {}
    values = sorted({get(s) for s in scores if get(s) not in (None, "unknown")})
    for v in values:
        subset = [s for s in scores if get(s) == v]
        c = calibration(subset)["overall"]
        if c:
            arms[v] = c
    return arms


def calibration_by_floor(scores: list[dict]) -> dict:
    """Calibration split by the WP-16.B.1 conviction-floor arm (on/off).

    Scoped to the production arm: only it ever ran the floor experiment, so
    pooling would compare `floor=off` against a mixture of pipelines.
    """
    return calibration_by(filter_arm(scores, PRIMARY_ARM), "conviction_floor")


def calibration_by_profile(scores: list[dict]) -> dict:
    """Calibration split by WP-16 run profile (control/loosened) — the headline A/B.

    Scoped to the production arm for the same reason as `calibration_by_floor`.
    Note that this split is currently **confounded with the market period** —
    see `profile_confound` and [KB-023] before reading it as an A/B.
    """
    return calibration_by(filter_arm(scores, PRIMARY_ARM), "profile",
                          resolve=profile_of)


def profile_confound(scores: list[dict]) -> dict:
    """Report-date overlap between run profiles, within the production arm.

    A profile A/B is only readable if both arms saw the same markets. Switching
    `MACRO_PROFILE` in one block produced two profiles with **zero** shared
    dates, making profile and market period the same partition [KB-023]; the
    numbers looked like a result and were not one. This surfaces the overlap so
    the next reader does not have to rediscover it.
    """
    return date_overlap(filter_arm(scores, PRIMARY_ARM), "profile")


def calibration_by_arm(scores: list[dict]) -> dict:
    """PHASE-19-EXO (removable hook): calibration split by arm (market vs exogenous).

    Only shows once ≥2 arms have scored data, i.e. once the exogenous engine has
    resolved leans alongside the market-only arm (DESIGN §4/§5). Inert with a single
    arm (renders nothing). Safe to leave or delete when killing the engine (DESIGN §9).
    """
    return calibration_by(scores, "arm")


# ---------------------------------------------------------------------------
# Commitment metric (WP-16.B.1 reframe) — measurable at low n
# ---------------------------------------------------------------------------
# KB-007 showed decisive directional calls are below chance, so the loosened
# arm's thesis is "commit less". The decisive-only Brier that judges that needs
# n>=30 decisive calls, which floor-off makes rare (→ months away). This metric
# instead scores the *commitment decision itself* over ALL resolved calls, so it
# yields a directional read now:
#   - commitment_rate     : fraction of calls the model made directional (not Neutral)
#   - wrong/right_decisive_rate : per resolved call, how often a commitment
#                           resolved wrong (score 0) / right (score 1)
#   - net_decisive_edge   : (right - wrong) / resolved — KB-007 baseline is < 0;
#                           committing less should raise it toward 0 by cutting
#                           wrong commitments faster than right ones.
# Uses the model's stated `bias` (Neutral vs Bullish/Bearish) to separate "the
# model declined to commit" from "the market was flat" — the score 0.5 bucket
# conflates the two; bias does not.

def commitment_stats(scores: list[dict]) -> dict | None:
    """Aggregate commitment quality over every *resolved* call (score not None)."""
    total = neutral = directional = wrong = right = flat_outcome = 0
    bullish = bearish = 0
    for report in scores:
        for window in WINDOWS:
            wdata = report.get("windows", {}).get(window)
            if not wdata:
                continue
            for adata in wdata.get("assets", {}).values():
                score = adata.get("score")
                if score is None:
                    continue
                total += 1
                bias = str(adata.get("bias", "")).strip().lower()
                if bias == "neutral":
                    neutral += 1
                elif bias in ("bullish", "bearish"):
                    directional += 1
                    bullish += int(bias == "bullish")
                    bearish += int(bias == "bearish")
                    if score == 1.0:
                        right += 1
                    elif score == 0.0:
                        wrong += 1
                    else:
                        flat_outcome += 1     # committed, but the market didn't move enough
                else:
                    # Bias missing/odd — fall back to the score's own signal.
                    if score in (0.0, 1.0):
                        directional += 1
                        right += int(score == 1.0)
                        wrong += int(score == 0.0)
                    else:
                        neutral += 1
    if total == 0:
        return None
    decisive = wrong + right
    return {
        "n_resolved":             total,
        "commitment_rate":        round(directional / total, 3),
        "neutral_rate":           round(neutral / total, 3),
        "bullish_rate":           round(bullish / total, 3),
        "bearish_rate":           round(bearish / total, 3),
        # Directional symmetry: share of committed calls that were bearish.
        # ~0.5 = symmetric; near 0 = a one-sided "long or abstain" book that
        # cannot call a decline (looks calibrated only while markets rise).
        "bearish_share_of_directional": round(bearish / directional, 3) if directional else None,
        "decisive_rate":          round(decisive / total, 3),
        "wrong_decisive_rate":    round(wrong / total, 3),
        "right_decisive_rate":    round(right / total, 3),
        "net_decisive_edge":      round((right - wrong) / total, 3),
        "hit_rate_when_decisive": round(right / decisive, 3) if decisive else None,
        "n_decisive":             decisive,
        "n_directional":          directional,
        "n_bullish":              bullish,
        "n_bearish":              bearish,
    }


def commitment_by_arm(scores: list[dict]) -> dict:
    """Commitment stats split as loosened vs baseline (everything not loosened).

    Scoped to the production arm — 'baseline' previously pooled every non-loosened
    file, which swept the `kimi` and `exogenous` arms into the comparator [KB-023].

    The deeper problem this cannot fix: the two profiles share **zero** report-dates,
    because `MACRO_PROFILE` was switched in one block. 'baseline' is therefore also
    'March-June' and 'loosened' is also 'July-August', and the assets that drove the
    original result reversed sign between those periods. Read `profile_confound()`
    alongside this, and treat the split as descriptive until WP-21.B assigns the
    profile per report-date.
    """
    scoped = filter_arm(scores, PRIMARY_ARM)
    loosened = [s for s in scoped if s.get("profile") == "loosened"]
    baseline = [s for s in scoped if s.get("profile") != "loosened"]
    out: dict = {}
    b = commitment_stats(baseline)
    l = commitment_stats(loosened)
    if b:
        out["baseline"] = b
    if l:
        out["loosened"] = l
    return out


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def write_json(
    stats: dict,
    n_reports: int,
    feedback_stats: dict,
    n_feedback: int,
    version_stats: dict,
    calib: dict | None = None,
    calib_feedback: dict | None = None,
    calib_by_floor: dict | None = None,
    calib_by_profile: dict | None = None,
    calib_by_arm: dict | None = None,
    commitment: dict | None = None,
    separation: dict | None = None,
    arm: str = PRIMARY_ARM,
    composition: dict | None = None,
    confound: dict | None = None,
) -> None:
    output = {
        "generated_at":        date.today().isoformat(),
        # Every number below describes this arm alone (see "Arm scoping").
        "arm":                 arm,
        "arm_composition":     composition or {},
        "profile_confound":    confound or {},
        "n_reports_total":     n_reports,
        "windows":             stats,
        "min_feedback_version": MIN_FEEDBACK_VERSION,
        "n_feedback_reports":  n_feedback,
        "feedback_windows":    feedback_stats,
        "version_windows":     version_stats,
        "calibration":         calib,
        "calibration_feedback": calib_feedback,
        "calibration_by_profile": calib_by_profile,
        "calibration_by_conviction_floor": calib_by_floor,
        "calibration_by_arm":  calib_by_arm,
        "commitment_by_arm":   commitment,
        "bias_separation":     separation,
        "_note": (
            "accuracy is on a 0-1 scale where 0.5 = random (coin-flip). "
            "directional_acc excludes flat moves and Neutral calls - "
            "it measures signal quality on clear directional bets. "
            f"feedback_windows includes only reports from {MIN_FEEDBACK_VERSION}+ "
            "(adversarial review era) and is used by the daily bias override logic. "
            f"version_windows shows per-version stats for the {TRACK_LATEST_N_VERSIONS} most recent pipeline versions. "
            "calibration (WP-16.B.2) scores stated confidence as a probability forecast: "
            "brier (lower=better, 0=perfect), brier_skill_score (>0 beats the base-rate forecast), "
            "ece (expected calibration error), and reliability bins (gap>0 underconfident, <0 overconfident); "
            "decisive directional calls only. calibration_feedback restricts to MIN_FEEDBACK_VERSION+. "
            "bias_separation asks whether realized forward returns differ by stated bias - "
            "the regime-robust discrimination test the accuracy score cannot answer while "
            "the market trends; z is in per-(window, asset) standard deviations and p comes "
            "from a block permutation test that respects overlapping evaluation windows. "
            "arm scopes every headline number to one prediction system (default 'market'); "
            "arm_composition lists what else was scored and excluded, and calibration_by_arm "
            "is the only cross-arm comparison. profile_confound reports report-date overlap "
            "between run profiles - a pair with n_shared=0 means the profile A/B is "
            "indistinguishable from a before/after market comparison and must not be read "
            "as an A/B (KB-023)."
        ),
    }
    payload = json.dumps(output, indent=2)
    SUMMARY_JSON.write_text(payload, encoding="utf-8")
    print(f"Summary JSON written to: {SUMMARY_JSON}")
    SUMMARY_JSON_COPY.write_text(payload, encoding="utf-8")
    print(f"Summary JSON copy written to: {SUMMARY_JSON_COPY}")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _acc_bar(accuracy: float | None, n: int, width: int = 20) -> str:
    """Simple ASCII bar for accuracy display."""
    if accuracy is None or n == 0:
        return "no data"
    filled = round(accuracy * width)
    bar    = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {accuracy:.0%}  (n={n})"


def _calibration_verdict(c: dict | None) -> str:
    """One-word calibration read from the n-weighted signed gap + ECE."""
    if not c or not c.get("bins"):
        return "no data"
    n = c["n"]
    signed_gap = sum((b["n"] / n) * b["gap"] for b in c["bins"])
    if c["ece"] < 0.03:
        return "well-calibrated"
    return "underconfident" if signed_gap > 0 else "overconfident"


def _ab_md_lines(title: str, by_value: dict) -> list[str]:
    """One-line-per-arm A/B readout of a calibration split. Needs ≥2 arms."""
    if not by_value or len(by_value) < 2:
        return []   # need at least two arms scored before the comparison means anything
    lines = [f"**{title}:**", ""]
    for arm, c in by_value.items():
        bss = f"{c['brier_skill_score']:+.3f}" if c["brier_skill_score"] is not None else "n/a"
        lines.append(
            f"- **{arm}**: Brier {c['brier']:.3f} | BSS {bss} | ECE {c['ece']:.3f} | "
            f"base-rate {c['base_rate']:.0%} | n={c['n']}"
        )
    lines.append("")
    return lines


def _calibration_md_lines(calib: dict, by_floor: dict | None = None,
                          by_profile: dict | None = None,
                          by_arm: dict | None = None,
                          confound: dict | None = None) -> list[str]:
    """Render the Brier / reliability-diagram section as markdown lines."""
    lines = [
        "---",
        "",
        "## Calibration — Brier / Reliability *(WP-16.B.2)*",
        "",
        "> **Brier**: mean squared error of stated confidence vs outcome — lower is better "
        "(0 = perfect, 0.25 = always guessing 50/50).",
        "> **BSS** (Brier Skill Score) > 0 ⇒ the confidence numbers beat simply predicting the base rate.",
        "> **Gap** = actual hit-rate − predicted confidence: **+ underconfident**, **− overconfident**.",
        "> Decisive directional calls only (Neutral / flat excluded — no binary outcome to calibrate).",
        "",
    ]

    ov = calib.get("overall")
    if ov:
        bss = f"{ov['brier_skill_score']:+.3f}" if ov["brier_skill_score"] is not None else "n/a"
        lines += [
            f"**Overall (all windows):** Brier **{ov['brier']:.3f}** | BSS {bss} | "
            f"ECE {ov['ece']:.3f} | base-rate {ov['base_rate']:.0%} | n={ov['n']} "
            f"— *{_calibration_verdict(ov)}*",
            "",
        ]
    else:
        lines += ["*No decisive directional calls scored yet.*", ""]
        return lines

    profile_ab = _ab_md_lines("Profile A/B (WP-16 — control vs loosened)", by_profile or {})
    lines += profile_ab
    if profile_ab:
        lines += _confound_warning_lines(confound, "The profile A/B")
    lines += _ab_md_lines("Conviction-floor A/B (WP-16.B.1)", by_floor or {})
    lines += _ab_md_lines("Arm A/B (market vs exogenous vs kimi)", by_arm or {})

    for window in WINDOWS:
        c = calib.get("windows", {}).get(window)
        if not c:
            continue
        bss = f"{c['brier_skill_score']:+.3f}" if c["brier_skill_score"] is not None else "n/a"
        lines += [
            f"### {WINDOW_LABELS[window]} — Brier {c['brier']:.3f} | BSS {bss} | "
            f"ECE {c['ece']:.3f} | n={c['n']} — *{_calibration_verdict(c)}*",
            "",
            "| Confidence bin | n | Predicted | Actual | Gap |",
            "|----------------|---|-----------|--------|-----|",
        ]
        for b in c["bins"]:
            tag = "under" if b["gap"] > 0 else ("over" if b["gap"] < 0 else "exact")
            lines.append(
                f"| {b['range']} | {b['n']} | {b['mean_conf']:.0%} | "
                f"{b['hit_rate']:.0%} | {b['gap']:+.0%} ({tag}) |"
            )
        lines.append("")

    return lines


def _confound_warning_lines(confound: dict | None, what: str) -> list[str]:
    """A ⛔ block for every profile pair that shares no report-dates.

    `what` names the comparison being warned about, so the same guardrail can sit
    under the calibration A/B and under the commitment table without either
    reading as a copy of the other.
    """
    lines: list[str] = []
    for pair, info in (confound or {}).items():
        if not info.get("confounded"):
            continue
        a, b = pair.split("|")
        span_a = " → ".join(info["span_a"]) if info.get("span_a") else "?"
        span_b = " → ".join(info["span_b"]) if info.get("span_b") else "?"
        lines += [
            f"> ⛔ **{what} is confounded: `{a}` and `{b}` share zero report-dates** "
            f"(`{a}`: {span_a}; `{b}`: {span_b}). `MACRO_PROFILE` was switched in one "
            "block, so the profile split *is* a time split — the rows differ by market "
            "period as much as by prompt. Assign the profile per report-date "
            "(alternating) before reading this as an A/B [KB-023, WP-21.B].",
            "",
        ]
    return lines


def _commitment_md_lines(by_arm: dict, confound: dict | None = None) -> list[str]:
    """Render the commitment metric (loosened vs baseline) as markdown.

    `confound` is the `profile_confound()` overlap map. When the two profiles
    share no report-dates the comparison is a before/after on the market, not an
    A/B, and the verdict line says so instead of crediting the arm [KB-023].
    """
    if not by_arm:
        return []
    lines = [
        "---",
        "",
        "## Commitment — does the loosened arm commit *less* and *better*? *(WP-16.B.1 reframe)*",
        "",
        "> KB-007: decisive calls are below chance, so the loosened arm (floor off) "
        "aims to **commit less**. This scores the commitment decision over *all* resolved "
        "calls (usable at low n, unlike the decisive-only Brier).",
        "> **commit-rate** = calls made directional (not Neutral). "
        "**bull / bear** = share of *all* resolved calls made Bullish / Bearish. "
        "**bear-share** = bearish ÷ directional (~50% = symmetric; near 0 = a one-sided "
        "'long or abstain' book that cannot call a decline — looks calibrated only while "
        "markets rise). "
        "**wrong/right-decisive** = per resolved call, a commitment that resolved wrong/right. "
        "**net edge** = right − wrong per call (KB-007 baseline < 0; higher is better).",
        "",
        "| Arm | n resolved | commit-rate | bull | bear | bear-share | wrong-dec | right-dec | net edge | hit-rate\\|decisive |",
        "|-----|-----------:|------------:|-----:|-----:|-----------:|----------:|----------:|---------:|-------------------:|",
    ]
    for arm in ("baseline", "loosened"):
        c = by_arm.get(arm)
        if not c:
            continue
        hr = f"{c['hit_rate_when_decisive']:.0%}" if c["hit_rate_when_decisive"] is not None else "n/a"
        bs = (
            f"{c['bearish_share_of_directional']:.0%}"
            if c.get("bearish_share_of_directional") is not None else "n/a"
        )
        lines.append(
            f"| {arm} | {c['n_resolved']} | {c['commitment_rate']:.0%} | "
            f"{c.get('bullish_rate', 0):.0%} | {c.get('bearish_rate', 0):.0%} | {bs} | "
            f"{c['wrong_decisive_rate']:.0%} | {c['right_decisive_rate']:.0%} | "
            f"{c['net_decisive_edge']:+.3f} | {hr} (n={c['n_decisive']}) |"
        )

    b, l = by_arm.get("baseline"), by_arm.get("loosened")
    if b and l:
        commit_delta = l["commitment_rate"] - b["commitment_rate"]
        edge_delta   = l["net_decisive_edge"] - b["net_decisive_edge"]
        wrong_delta  = l["wrong_decisive_rate"] - b["wrong_decisive_rate"]
        blocked = [k for k, v in (confound or {}).items() if v.get("confounded")]
        if blocked:
            verdict = (
                "**not attributable to the arm** — the profiles share no dates, so this "
                "is a before/after on the market as much as an A/B"
            )
        else:
            verdict = (
                "loosened commits less **and** bleeds less — the thesis holds so far"
                if commit_delta < 0 and wrong_delta < 0 and edge_delta >= 0
                else "loosened commits less but the edge did not improve — watch"
                if commit_delta < 0
                else "loosened is not committing less — unexpected"
            )
        lines += [
            "",
            f"Loosened vs baseline: commit-rate {commit_delta:+.0%}, "
            f"wrong-decisive {wrong_delta:+.0%}, net edge {edge_delta:+.3f} — _{verdict}._",
            "",
        ]
        lines += _confound_warning_lines(confound, "The commitment A/B")
        l_bear_share = l.get("bearish_share_of_directional")
        if l_bear_share is not None and l["n_directional"] >= 10 and l_bear_share < 0.15:
            lines += [
                f"> ⚠️ **One-sided book**: only {l_bear_share:.0%} of the loosened arm's "
                f"{l['n_directional']} directional calls were Bearish "
                f"({l['n_bearish']} bear / {l['n_bullish']} bull). It abstains from the "
                "downside rather than calling it, so any decisive hit-rate is inflated by "
                "a rising-market regime and untested against a drawdown. The target arm is "
                "abstain-capable **and** symmetric — watch bear-share into the next risk-off.",
                "",
            ]
        lines += [
            "> Directional read only — small loosened n. Confirm with the decisive-only "
            "Brier A/B above once it reaches n≥30.",
            "",
        ]
    return lines


def write_markdown(
    stats: dict,
    n_reports: int,
    n_feedback: int = 0,
    version_stats: dict | None = None,
    calib: dict | None = None,
    arm: str = PRIMARY_ARM,
    composition: dict | None = None,
    confound: dict | None = None,
    calib_by_floor: dict | None = None,
    calib_by_profile: dict | None = None,
    calib_by_arm: dict | None = None,
    commitment: dict | None = None,
    separation: dict | None = None,
) -> None:
    today = date.today().isoformat()
    lines = [
        "# Prediction Accuracy Report",
        "",
        f"*Generated: {today} | Arm: `{arm}` | Reports scored: {n_reports} "
        f"| Feedback-loop reports ({MIN_FEEDBACK_VERSION}+): {n_feedback}*",
        "",
        f"> **Scope: the `{arm}` arm only.** Several prediction arms write score files",
        "> and sibling arms share a `report_date`, so a pooled figure would average",
        "> different systems and a date-keyed join would mix their metadata outright",
        "> [KB-023]. Cross-arm comparison lives in the arm A/B further down.",
        "",
        "> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.",
        "> **Directional accuracy** excludes flat moves and Neutral calls — it is the",
        "> signal quality metric. Anything above ~60% with n > 10 is meaningful.",
        ">",
        f"> The **bias override** (daily pipeline) uses only {MIN_FEEDBACK_VERSION}+ reports",
        "> (adversarial review era). Earlier reports appear below for historical reference.",
        "",
    ]

    if composition and len(composition) > 1:
        lines += [
            "| Arm | reports | resolved calls | span | in this report |",
            "|-----|--------:|---------------:|------|:--------------:|",
        ]
        for a, c in sorted(composition.items()):
            span = f"{c['first_date']} → {c['last_date']}" if c["first_date"] else "—"
            lines.append(
                f"| `{a}` | {c['n_reports']} | {c['n_calls']} | {span} | "
                f"{'✅' if a == arm else '—'} |"
            )
        lines.append("")

    for window in WINDOWS:
        wdata = stats.get(window)
        if not wdata or wdata["overall_accuracy"] is None:
            lines.append(f"## {WINDOW_LABELS[window]}")
            lines.append("")
            lines.append("*No data yet.*")
            lines.append("")
            continue

        n_rep = wdata["n_reports"]
        ov    = wdata["overall_accuracy"]
        ov_d  = wdata["overall_dir_acc"]

        lines += [
            f"## {WINDOW_LABELS[window]}",
            "",
            f"**Overall accuracy:** {ov:.0%}  |  "
            f"**Directional:** {f'{ov_d:.0%}' if ov_d is not None else 'n/a'}  |  "
            f"**Reports:** {n_rep}",
            "",
            "| Asset | Accuracy | Directional | n | Avg Confidence |",
            "|-------|----------|-------------|---|----------------|",
        ]

        for asset in ASSET_ORDER:
            astat = wdata["by_asset"].get(asset)
            if not astat:
                continue
            acc   = f"{astat['accuracy']:.0%}"
            dacc  = f"{astat['directional_acc']:.0%}" if astat["directional_acc"] is not None else "—"
            n     = astat["n"]
            dn    = astat["directional_n"]
            conf  = f"{astat['avg_confidence']:.0f}%"
            lines.append(f"| {asset} | {acc} | {dacc} (n={dn}) | {n} | {conf} |")

        lines.append("")

    # Per-version breakdown
    if version_stats:
        tracked = sorted(version_stats.keys(), key=_version_key)
        lines += [
            "---",
            "",
            f"## Per-Version Accuracy (latest {TRACK_LATEST_N_VERSIONS} versions)",
            "",
            f"Accuracy broken out by the {TRACK_LATEST_N_VERSIONS} most recently deployed pipeline versions.",
            "Use this to confirm that structural improvements translate into better predictions.",
            "",
        ]
        for version in tracked:
            vdata = version_stats[version]
            n_scored = vdata.get("n_reports_scored", 0)
            n_total  = vdata.get("n_reports_in_pipeline", 0)
            lines.append(f"### {version}  ({n_scored} scored / {n_total} total reports in this version)")
            lines.append("")
            has_data = False
            for window in WINDOWS:
                wdata = vdata.get("windows", {}).get(window)
                if not wdata or wdata["overall_accuracy"] is None:
                    continue
                has_data = True
                ov   = wdata["overall_accuracy"]
                ov_d = wdata["overall_dir_acc"]
                n_rep = wdata["n_reports"]
                dir_str = f"{ov_d:.0%}" if ov_d is not None else "n/a"
                lines += [
                    f"**{WINDOW_LABELS[window]}** — overall: {ov:.0%} | directional: {dir_str} | reports: {n_rep}",
                    "",
                    "| Asset | Accuracy | Directional | n | Avg Confidence |",
                    "|-------|----------|-------------|---|----------------|",
                ]
                for asset in ASSET_ORDER:
                    astat = wdata["by_asset"].get(asset)
                    if not astat:
                        continue
                    acc  = f"{astat['accuracy']:.0%}"
                    dacc = f"{astat['directional_acc']:.0%}" if astat["directional_acc"] is not None else "—"
                    dn   = astat["directional_n"]
                    conf = f"{astat['avg_confidence']:.0f}%"
                    lines.append(f"| {asset} | {acc} | {dacc} (n={dn}) | {astat['n']} | {conf} |")
                lines.append("")
            if not has_data:
                lines.append(
                    f"*No scored predictions yet — T+5 window has not closed on any {version} reports.*"
                )
                lines.append("")

    # Calibration — Brier / reliability (WP-16.B.2)
    if calib:
        lines += _calibration_md_lines(calib, calib_by_floor, calib_by_profile,
                                       calib_by_arm, confound)
        lines += _commitment_md_lines(commitment or {}, confound)

    # Bias separation - does the stated call predict the realized move?
    lines += separation_md_lines(separation)

    # Calibration note
    lines += [
        "---",
        "",
        "## Calibration Notes",
        "",
        "- **50%** = coin-flip — no signal value",
        "- **55-60%** = weak signal, worth monitoring",
        "- **>65%** with n>10 = genuine predictive value",
        "- **<40%** = systematic bias; consider reversing the signal",
        "",
        "Flat-move threshold: 0.5% for prices, 3 bps for 10Y yield.",
        "Neutral calls always score 0.5 (excluded from directional accuracy).",
    ]

    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Summary markdown written to: {SUMMARY_MD}")


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def print_summary(stats: dict, n_reports: int, calib: dict | None = None,
                  separation: dict | None = None) -> None:
    print(f"\n{'='*60}")
    print(f"Prediction Accuracy Summary  |  Reports scored: {n_reports}")
    print(f"{'='*60}")

    if calib and calib.get("overall"):
        ov = calib["overall"]
        bss = f"{ov['brier_skill_score']:+.3f}" if ov["brier_skill_score"] is not None else "n/a"
        print(
            f"\nCalibration (decisive calls, n={ov['n']}):  "
            f"Brier {ov['brier']:.3f}  BSS {bss}  ECE {ov['ece']:.3f}  "
            f"→ {_calibration_verdict(ov)}"
        )

    if separation and separation.get("overall"):
        ov = separation["overall"]
        b  = ov["buckets"]
        bn = ov.get("bullish_vs_neutral")
        gap_str = (
            f"Bull−Neut {bn['gap']:+.3f} sd (p={bn['p_value']:.3f})"
            if bn else "Bull−Neut n/a"
        )
        print(
            f"\nBias separation (n={ov['n']}, forward return in sd):  "
            f"Bull {b['Bullish']['mean_z']:+.3f}  "
            f"Neut {b['Neutral']['mean_z']:+.3f}  "
            f"Bear {b['Bearish']['mean_z']:+.3f}  |  {gap_str}  "
            f"→ ordering: {ov['ordering']}"
        )

    for window in WINDOWS:
        wdata = stats.get(window)
        if not wdata or wdata["overall_accuracy"] is None:
            print(f"\n{WINDOW_LABELS[window]}: no data yet")
            continue

        ov   = wdata["overall_accuracy"]
        ov_d = wdata["overall_dir_acc"]
        n    = wdata["n_reports"]
        dir_str = f"{ov_d:.0%}" if ov_d is not None else "n/a"
        print(f"\n{WINDOW_LABELS[window]}  |  overall: {ov:.0%}  directional: {dir_str}  ({n} reports)")
        print(f"  {'Asset':<22} {'Accuracy':>9} {'Directional':>12} {'n':>4} {'Avg Conf':>9}")
        print(f"  {'-'*60}")
        for asset in ASSET_ORDER:
            astat = wdata["by_asset"].get(asset)
            if not astat:
                continue
            dacc = f"{astat['directional_acc']:.0%}" if astat["directional_acc"] is not None else "  —"
            print(
                f"  {asset:<22} {astat['accuracy']:>8.0%} "
                f"{dacc:>12}  {astat['n']:>3}  {astat['avg_confidence']:>7.0f}%"
            )

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Aggregate prediction scores.")
    ap.add_argument("--arm", default=PRIMARY_ARM,
                    help=f"prediction arm for the headline stats (default {PRIMARY_ARM!r}); "
                         "'all' pools every arm, which averages different systems together")
    args = ap.parse_args()
    arm = None if args.arm == "all" else args.arm

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not SCORES_DIR.exists() or not any(SCORES_DIR.glob("*.json")):
        print("No score files found. Run score_predictions.py first.")
        return

    all_scores = load_scores()
    composition = arm_composition(all_scores)
    # The headline describes ONE system. Cross-arm comparison lives in the arm
    # A/B below, which is handed the full set on purpose.
    scores = filter_arm(all_scores, arm)
    print(f"Loaded {len(all_scores)} score file(s); "
          f"{len(scores)} in arm {args.arm!r}.")
    if len(composition) > 1:
        for a, c in sorted(composition.items()):
            print(f"    {a:<12} {c['n_reports']:>4} reports  "
                  f"{c['first_date']} → {c['last_date']}")

    min_vk = _version_key(MIN_FEEDBACK_VERSION)
    n_feedback = sum(
        1 for s in scores
        if _version_key(s.get("agent_version", "v0.0")) >= min_vk
    )

    stats = aggregate(scores)
    feedback_stats = aggregate(scores, min_version=MIN_FEEDBACK_VERSION)

    # Per-version stats for the N most recent versions (discovered from report files).
    # Always include the current PIPELINE_VERSION even if no reports have been produced yet.
    report_counts = _scan_report_versions()
    report_counts.setdefault(PIPELINE_VERSION, 0)
    all_versions  = sorted(report_counts.keys(), key=_version_key)
    latest_versions = all_versions[-TRACK_LATEST_N_VERSIONS:]
    version_stats: dict = {}
    for v in latest_versions:
        v_scores = [s for s in scores if s.get("agent_version") == v]
        version_stats[v] = {
            "n_reports_in_pipeline": report_counts.get(v, 0),
            "n_reports_scored":      len(v_scores),
            "windows":               aggregate(v_scores),
        }
    print(f"Per-version tracking: {', '.join(latest_versions) or 'none'}")

    calib            = calibration(scores)
    calib_feedback   = calibration(scores, min_version=MIN_FEEDBACK_VERSION)
    calib_by_floor   = calibration_by_floor(scores)
    calib_by_profile = calibration_by_profile(scores)
    # The arm A/B is the one comparison that must see every arm.
    calib_by_arm     = calibration_by_arm(all_scores)
    commitment       = commitment_by_arm(scores)
    separation       = bias_separation(all_scores, arm=arm)
    confound         = profile_confound(scores)

    blocked = [k for k, v in confound.items() if v.get("confounded")]
    if blocked:
        print(f"  ⛔ profile A/B is confounded — no shared dates: {', '.join(blocked)}")

    print_summary(stats, len(scores), calib, separation)
    write_json(stats, len(scores), feedback_stats, n_feedback, version_stats,
               calib, calib_feedback, calib_by_floor, calib_by_profile, calib_by_arm,
               commitment, separation, arm=args.arm, composition=composition,
               confound=confound)
    write_markdown(stats, len(scores), n_feedback, version_stats, calib,
                   arm=args.arm, composition=composition, confound=confound,
                   calib_by_floor=calib_by_floor, calib_by_profile=calib_by_profile,
                   calib_by_arm=calib_by_arm, commitment=commitment,
                   separation=separation)


if __name__ == "__main__":
    main()
