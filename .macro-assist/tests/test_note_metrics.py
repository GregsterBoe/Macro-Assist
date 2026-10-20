"""
note_metrics — the note's table numbers copied into its frontmatter, for vault charts.

Pins:
  1. Each metric is read from the row it names, not from a decoy row that reuses
     the label (the v1.x dashboard, the prediction table, the dial).
  2. A value the body does not show (`nan` feed, absent row) is left out — never
     written as a blank or a zero.
  3. `stamp` touches only the frontmatter, places the keys above `tags:`, and is
     idempotent — the backfill re-runs safely.

The fixture lines are copied from `results/06-June/2026-06-10-Wednesday-macro.md`
and `results/10-October/2026-10-14-Wednesday-macro.md` (convention #10). The
June note is the useful one: its S&P 500 feed was `nan` and its dashboard
reuses the VIX, Gold and yield-curve labels.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backfill_note_metrics import DAILY_NOTE, backfill
from note_metrics import METRICS, extract, stamp

JUNE = """---
date: 2026-06-10
day: Wednesday
type: macro-intelligence
agent_version: v1.4
tags: [macro, daily-note, economics]
---

# Macro Intelligence — 2026-06-10

| Yield Curve (10Y–2Y) | +0.41% | Re-steepening | Neutral | Neutral | Neutral | Neutral |
| VIX | 21.12 (ratio 1.016) | Backwardation/Acute Stress | Bearish | Bullish | Caution | Bearish |
| Gold | Bullish | Gold at $4,189 is -9.2% below its 50dMA | 55% | 4,150–4,350 |

| S&P 500 | nan | ▼ nan% |
| Gold | 4,189.10 | ▼ 1.66% |
| VIX | 21.12 | ▲ 11.63% |

| 10Y Treasury        | 4.56%   | 2026-06-08 |
| Yield Curve (10-2Y) | 0.41%      | — |
| NFCI                | -0.494 (0=neutral, +tight, -loose) | 2026-05-29 |
"""

OCTOBER = """---
date: 2026-10-14
day: Wednesday
type: macro-intelligence
agent_version: v2.2
prune_rules: off
tags: [macro, daily-note, economics]
---

# Macro Intelligence — 2026-10-14

| Composite | 14/100 — **Resilient** |

| SP500 | 12.0% | 17.0% | **100%** of normal |
| Gold | 17.2% | 19.2% | **100%** of normal |

| S&P 500 | median +0.3% · P25 -1.0% / P75 +1.3% · n=836 |

| S&P 500 | 7,805.45 | ▼ 0.02% |
| Gold | 4,183.50 | ▲ 0.15% |
| Bitcoin | 83,451.47 | ▲ 2.07% |
"""


def _front(note: str) -> list[str]:
    return note.split("\n---", 1)[0].splitlines()[1:]


class TestExtract:
    def test_reads_the_snapshot_rows_not_the_decoys(self):
        assert extract(JUNE) == {"gold": 4189.1, "vix": 21.12, "us10y": 4.56,
                                 "yield_curve": 0.41, "nfci": -0.494}

    def test_nan_feed_is_absent_not_zero(self):
        assert "sp500" not in extract(JUNE)

    def test_fragility_and_thousands_separators(self):
        m = extract(OCTOBER)
        assert m["fragility"] == 14
        assert m["sp500"] == 7805.45 and m["bitcoin"] == 83451.47
        assert m["gold"] == 4183.5          # the market row, not the dial's 17.2%


class TestStamp:
    def test_keys_go_above_tags_in_metric_order(self):
        front = _front(stamp(OCTOBER))
        assert front[-1].startswith("tags:")
        assert front[front.index("prune_rules: off") + 1:-1] == [
            "fragility: 14", "sp500: 7805.45", "gold: 4183.5", "bitcoin: 83451.47"]

    def test_body_is_untouched(self):
        for note in (JUNE, OCTOBER):
            assert stamp(note).split("\n---", 1)[1] == note.split("\n---", 1)[1]

    def test_idempotent(self):
        once = stamp(JUNE)
        assert stamp(once) == once
        assert sum(ln.startswith("vix:") for ln in _front(once)) == 1

    def test_stale_value_is_replaced(self):
        stale = stamp(JUNE).replace("vix: 21.12", "vix: 99")
        assert stamp(stale) == stamp(JUNE)

    def test_no_frontmatter_or_no_metrics_unchanged(self):
        assert stamp("| VIX | 21.12 | ▲ 11.63% |\n") == "| VIX | 21.12 | ▲ 11.63% |\n"
        bare = "---\ndate: 2026-06-10\ntags: [macro]\n---\n\nno tables\n"
        assert stamp(bare) == bare

    def test_metric_keys_do_not_collide_with_the_contract(self):
        # The frontmatter keys historical readers parse must never be overwritten.
        contract = {"date", "day", "type", "agent_version", "config", "profile", "model",
                    "conviction_floor", "base_rate_first", "prune_rules", "tags"}
        assert not contract & set(METRICS)


class TestBackfill:
    def test_daily_notes_only(self):
        assert DAILY_NOTE.match("2026-06-10-Wednesday-macro.md")
        assert not DAILY_NOTE.match("2026-08-11-kimi-macro.md")
        assert not DAILY_NOTE.match("2026-08-11-exogenous-macro.md")

    def test_stamps_then_leaves_current_notes_alone(self, tmp_path):
        (tmp_path / "06-June").mkdir()
        daily = tmp_path / "06-June" / "2026-06-10-Wednesday-macro.md"
        arm = tmp_path / "06-June" / "2026-06-10-kimi-macro.md"
        daily.write_text(JUNE, encoding="utf-8")
        arm.write_text(JUNE, encoding="utf-8")

        assert backfill(tmp_path, dry_run=True) == {"stamped": 1, "unchanged": 0, "skipped": 1}
        assert daily.read_text(encoding="utf-8") == JUNE
        assert backfill(tmp_path) == {"stamped": 1, "unchanged": 0, "skipped": 1}
        assert daily.read_text(encoding="utf-8") == stamp(JUNE)
        assert arm.read_text(encoding="utf-8") == JUNE
        assert backfill(tmp_path) == {"stamped": 0, "unchanged": 1, "skipped": 1}
