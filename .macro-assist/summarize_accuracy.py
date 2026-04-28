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
from collections import defaultdict
from datetime import date
from pathlib import Path

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

def aggregate(scores: list[dict]) -> dict:
    """
    Build nested stats: window -> asset -> {n, accuracy, avg_confidence, ...}
    Also compute directional accuracy: only Bullish/Bearish calls on
    non-flat moves (score is 0 or 1, not 0.5).
    """
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
# JSON output
# ---------------------------------------------------------------------------

def write_json(stats: dict, n_reports: int) -> None:
    output = {
        "generated_at":   date.today().isoformat(),
        "n_reports_total": n_reports,
        "windows":         stats,
        "_note": (
            "accuracy is on a 0–1 scale where 0.5 = random (coin-flip). "
            "directional_acc excludes flat moves and Neutral calls — "
            "it measures signal quality on clear directional bets."
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


def write_markdown(stats: dict, n_reports: int) -> None:
    today = date.today().isoformat()
    lines = [
        f"# Prediction Accuracy Report",
        f"",
        f"*Generated: {today} | Reports scored: {n_reports}*",
        f"",
        f"> Accuracy scale: 0% = always wrong, 50% = random, 100% = always right.",
        f"> **Directional accuracy** excludes flat moves and Neutral calls — it is the",
        f"> signal quality metric. Anything above ~60% with n > 10 is meaningful.",
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

def print_summary(stats: dict, n_reports: int) -> None:
    print(f"\n{'='*60}")
    print(f"Prediction Accuracy Summary  |  Reports scored: {n_reports}")
    print(f"{'='*60}")

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

    stats = aggregate(scores)
    print_summary(stats, len(scores))
    write_json(stats, len(scores))
    write_markdown(stats, len(scores))


if __name__ == "__main__":
    main()
