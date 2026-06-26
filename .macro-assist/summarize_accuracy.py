"""
summarize_accuracy.py — Aggregate prediction scores into accuracy stats.

Reads all JSON score files from results/scores/, computes per-asset and
per-window accuracy, and writes:
  - .macro-assist/data/accuracy_summary.json  (machine-readable, read by daily pipeline)
  - results/accuracy_summary.json             (copy for human review / vault)
  - results/accuracy_report.md                (human-readable markdown)

Usage:
    python .macro-assist/summarize_accuracy.py
"""

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

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


def calibration_by_floor(scores: list[dict]) -> dict:
    """Overall calibration split by the WP-16.B.1 conviction-floor arm.

    Returns {"on": <overall calib>, "off": <overall calib>} for whichever arms
    have scored data — the A/B readout for "does allowing all-Neutral improve
    calibration?". Empty/absent until floor-off notes have been scored.
    """
    arms: dict = {}
    for arm in ("on", "off"):
        subset = [s for s in scores if s.get("conviction_floor") == arm]
        if subset:
            arms[arm] = calibration(subset)["overall"]
    return arms


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
) -> None:
    output = {
        "generated_at":        date.today().isoformat(),
        "n_reports_total":     n_reports,
        "windows":             stats,
        "min_feedback_version": MIN_FEEDBACK_VERSION,
        "n_feedback_reports":  n_feedback,
        "feedback_windows":    feedback_stats,
        "version_windows":     version_stats,
        "calibration":         calib,
        "calibration_feedback": calib_feedback,
        "calibration_by_conviction_floor": calib_by_floor,
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
            "decisive directional calls only. calibration_feedback restricts to MIN_FEEDBACK_VERSION+."
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


def _floor_ab_md_lines(by_floor: dict) -> list[str]:
    """One-line A/B readout of conviction-floor on vs off (WP-16.B.1)."""
    if not by_floor or not ({"on", "off"} <= set(by_floor)):
        return []   # need both arms scored before the comparison means anything
    lines = ["**Conviction-floor A/B (WP-16.B.1):**", ""]
    for arm in ("on", "off"):
        c = by_floor[arm]
        bss = f"{c['brier_skill_score']:+.3f}" if c["brier_skill_score"] is not None else "n/a"
        lines.append(
            f"- floor **{arm}**: Brier {c['brier']:.3f} | BSS {bss} | ECE {c['ece']:.3f} | "
            f"base-rate {c['base_rate']:.0%} | n={c['n']}"
        )
    lines.append("")
    return lines


def _calibration_md_lines(calib: dict, by_floor: dict | None = None) -> list[str]:
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

    lines += _floor_ab_md_lines(by_floor or {})

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


def write_markdown(
    stats: dict,
    n_reports: int,
    n_feedback: int = 0,
    version_stats: dict | None = None,
    calib: dict | None = None,
    calib_by_floor: dict | None = None,
) -> None:
    today = date.today().isoformat()
    lines = [
        f"# Prediction Accuracy Report",
        f"",
        f"*Generated: {today} | Reports scored: {n_reports} "
        f"| Feedback-loop reports ({MIN_FEEDBACK_VERSION}+): {n_feedback}*",
        f"",
        f"> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.",
        f"> **Directional accuracy** excludes flat moves and Neutral calls — it is the",
        f"> signal quality metric. Anything above ~60% with n > 10 is meaningful.",
        f">",
        f"> The **bias override** (daily pipeline) uses only {MIN_FEEDBACK_VERSION}+ reports",
        f"> (adversarial review era). Earlier reports appear below for historical reference.",
        f"",
    ]

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
            f"",
            f"**Overall accuracy:** {ov:.0%}  |  "
            f"**Directional:** {f'{ov_d:.0%}' if ov_d is not None else 'n/a'}  |  "
            f"**Reports:** {n_rep}",
            f"",
            f"| Asset | Accuracy | Directional | n | Avg Confidence |",
            f"|-------|----------|-------------|---|----------------|",
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
                    f"| Asset | Accuracy | Directional | n | Avg Confidence |",
                    f"|-------|----------|-------------|---|----------------|",
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
        lines += _calibration_md_lines(calib, calib_by_floor)

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

def print_summary(stats: dict, n_reports: int, calib: dict | None = None) -> None:
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not SCORES_DIR.exists() or not any(SCORES_DIR.glob("*.json")):
        print("No score files found. Run score_predictions.py first.")
        return

    scores = load_scores()
    print(f"Loaded {len(scores)} score file(s).")

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

    calib          = calibration(scores)
    calib_feedback = calibration(scores, min_version=MIN_FEEDBACK_VERSION)
    calib_by_floor = calibration_by_floor(scores)

    print_summary(stats, len(scores), calib)
    write_json(stats, len(scores), feedback_stats, n_feedback, version_stats,
               calib, calib_feedback, calib_by_floor)
    write_markdown(stats, len(scores), n_feedback, version_stats, calib, calib_by_floor)


if __name__ == "__main__":
    main()
