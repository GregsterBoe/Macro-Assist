"""feed_audit.py — the fragility monitor's feed gate (IMP-5.4).

WHY THIS EXISTS

[KB-029] fixed the wrong half of a failure and left the right half open. When
yfinance's `^VIX3M` stopped updating in July 2026 the composite renormalised
onto what was left and printed its first-ever live `Elevated` out of a data
gap. The fix made that impossible: a composite missing a required component is
labelled `Unavailable`, the OR engine masks the day, and CBOE's own CSV became
the fallback feed.

What the fix did NOT do is tell anyone. On 2026-09-16 the `vix_term` leg went
missing again — with the CBOE fallback in place — and the monitor published
`Unavailable` on the 16th, the 17th and the 18th. Every check was green. The
daily log carried a WARN, which is a line in a passing Action that nobody
reads. It was caught by a human reading the note on day three.

A WARN that nobody reads is not a detector. This script is: it reads the live
readings back out of the quant log and exits non-zero once the monitor has been
degraded for more than `MAX_DEGRADED_STREAK` consecutive readings, which turns
the day's pipeline run red and sends the notification GitHub already sends for
a failed run.

WHY IT IS ITS OWN JOB, AFTER THE NOTE

A dead vol feed must not cost the day's note. Everything else in the note is
independent of it, and the Fragility Monitor block already says `Unavailable`
in plain words. So this runs as `feed_gate` in pipeline.yml, needing `daily`:
by the time it can fail, the note is written, pushed to the vault and published
to the output branch.

It began as the last *step* of the daily stage, which was a defect. A failing
step fails the job; `scoring` requires `needs.daily.result == 'success'` and
`rebalance` requires `scoring`; so a dead vol feed on a Monday would have
skipped the week's scorecard and the paper-portfolio rebalance — neither of
which has anything to do with the vol legs. As a sibling job it still turns the
RUN red, which is the notification this exists to send, and every weekly stage
proceeds. Re-running the failed job is harmless.

THE THRESHOLD IS 2, NOT 1

One degraded reading is a bad afternoon at a data vendor and self-heals by the
next run; the existing WARN covers it. Two in a row is a feed that is not
coming back on its own, which is the shape both outages had. The same argument
as WP-24.B's cadence + 1 day: red where a human would have to act, not where
the system is merely having a bad day.

Run:
    python .macro-assist/feed_audit.py                 # exit 1 on a live streak
    python .macro-assist/feed_audit.py --asof 2026-09-18
    python .macro-assist/feed_audit.py --max-streak 3
    python .macro-assist/feed_audit.py --warn-only     # report, never exit 1
    python .macro-assist/feed_audit.py --probe         # why is it missing RIGHT NOW (network)
    python .macro-assist/feed_audit.py --probe-cboe    # does the issuer fallback work AT ALL
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from pipeline_common import REPO_ROOT, _log

# Consecutive degraded readings tolerated before the run goes red. See the
# module docstring: 1 is a vendor hiccup, 2 is a feed that has stopped.
MAX_DEGRADED_STREAK = 2

QUANT_LOG_DIR = REPO_ROOT / "results" / "quant_context_log"


@dataclass
class Reading:
    """One day's fragility reading, as the quant log recorded it."""
    day: date
    degraded: list[str]
    label: str
    detail: dict = field(default_factory=dict)
    feed: dict = field(default_factory=dict)

    def why(self) -> str:
        """The recorded cause, or a note that the run did not record one."""
        bits = [f"{k}: {v}" for k, v in (self.detail or {}).items()]
        for leg, rec in (self.feed or {}).items():
            rec = rec or {}
            part = f"{leg} from {rec.get('source', '?')}"
            if rec.get("last"):
                part += f" (last {rec['last']})"
            if rec.get("error"):
                part += f" — {rec['error']}"
            bits.append(part)
        return "; ".join(bits) or "cause not recorded by that run"


def read_log(log_dir: Path = QUANT_LOG_DIR,
             asof: Optional[date] = None) -> list[Reading]:
    """Every fragility reading in the quant log up to `asof`, oldest first.

    One file per day, appended to — a day re-run twice has two lines and the
    LAST one is that day's reading, so later lines overwrite earlier ones.
    Unreadable lines and files without a fragility block are skipped, never
    fatal: this is a detector, and a detector that crashes detects nothing.
    """
    by_day: dict[date, Reading] = {}
    if not log_dir.is_dir():
        return []
    for path in sorted(log_dir.glob("*.jsonl")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if asof is not None and day > asof:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(rec, dict):
                continue
            frag = rec.get("fragility")
            if not isinstance(frag, dict):
                continue
            by_day[day] = Reading(
                day=day,
                degraded=list(frag.get("degraded") or []),
                label=str(frag.get("label", "?")),
                detail=dict(frag.get("degraded_detail") or {}),
                feed=dict(frag.get("feed") or {}),
            )
    return [by_day[d] for d in sorted(by_day)]


def degraded_streak(readings: list[Reading]) -> list[Reading]:
    """The run of degraded readings ending at the most recent one, oldest
    first. `[]` when the latest reading is healthy — a streak that has already
    healed is history, not an open failure."""
    streak: list[Reading] = []
    for reading in reversed(readings):
        if not reading.degraded:
            break
        streak.append(reading)
    return list(reversed(streak))


def audit(log_dir: Path = QUANT_LOG_DIR,
          asof: Optional[date] = None,
          max_streak: int = MAX_DEGRADED_STREAK) -> tuple[int, list[tuple[str, str, str]]]:
    """(exit code, (section, level, message) log lines). 1 when the streak exceeds
    `max_streak`, 0 otherwise. Never raises."""
    readings = read_log(log_dir, asof)
    if not readings:
        return 0, [("FEED", "INFO", "no fragility readings in the quant log — nothing to audit")]

    streak = degraded_streak(readings)
    latest = readings[-1]
    if not streak:
        return 0, [("FEED", "OK",
                    f"fragility feeds healthy — {latest.day} reading is {latest.label}, "
                    f"{len(readings)} readings on file")]

    missing = ", ".join(sorted({c for r in streak for c in r.degraded}))
    span = f"{streak[0].day} → {streak[-1].day}" if len(streak) > 1 else str(streak[0].day)
    head = (f"composite degraded {len(streak)} reading(s) in a row ({span}) — "
            f"{missing} missing, calibrated label withheld")
    lines = [("FEED", "WARN" if len(streak) <= max_streak else "FAIL", head),
             ("FEED", "INFO", f"latest cause — {latest.why()}")]
    if len(streak) <= max_streak:
        lines.append(("FEED", "INFO",
                      f"within tolerance ({len(streak)}/{max_streak}) — red at "
                      f"{max_streak + 1} consecutive readings"))
        return 0, lines
    lines.append(("FEED", "FAIL",
                  f"over tolerance ({len(streak)} > {max_streak}). The Fragility Monitor "
                  f"has published no calibrated label since {streak[0].day}. The note itself "
                  f"is unaffected and was written. Fix the feed (see IMP-5 in "
                  f"docs/record/improvement-track.md), or raise --max-streak deliberately."))
    return 1, lines


def probe_cboe() -> tuple[int, list[tuple[str, str, str]]]:
    """Fetch CBOE's own CSV for each vol leg directly, bypassing the freshness
    short-circuit `freshen_vol_indices` applies.

    This exists because the fallback is only invoked when a leg is already
    stale or missing — `if not stale: continue` — so on a normal day it is
    never exercised and a broken fallback looks exactly like a working one.
    The record bears that out: CBOE's first three live invocations
    (2026-09-16..18) all failed, and there is no run on file where it
    succeeded. A fallback nobody can test is a fallback nobody should count on.

    Exit 1 if either leg cannot be fetched. Costs one CSV per leg.
    """
    from fragility_panel import _CBOE_SYMBOLS, cboe_error, fetch_cboe_index

    lines: list[tuple[str, str, str]] = []
    failed = False
    for leg, symbol in sorted(_CBOE_SYMBOLS.items()):
        series = fetch_cboe_index(symbol)
        if series is None or len(series) == 0:
            failed = True
            lines.append(("PROBE", "FAIL",
                          f"CBOE {symbol}: unavailable — {cboe_error(symbol) or 'no data'}"))
            continue
        lines.append(("PROBE", "OK",
                      f"CBOE {symbol}: {len(series)} rows, last {series.index[-1].date()} "
                      f"= {float(series.iloc[-1]):.2f}"))
    lines.append(("PROBE", "FAIL" if failed else "OK",
                  "the issuer fallback is NOT usable — a stale yfinance leg has nothing "
                  "behind it" if failed else
                  "the issuer fallback is usable — a stale yfinance leg would be covered"))
    return (1 if failed else 0), lines


def probe() -> tuple[int, list[tuple[str, str, str]]]:
    """Fetch the vol legs live and report what each one did — the answer to
    "why is `vix_term` missing *right now*", without waiting for tomorrow's
    pipeline run. Costs one yfinance call per ticker and at most one CBOE CSV
    per stale leg, so it is opt-in (`--probe`) and never part of the gate.

    Exit 1 when the term structure cannot be computed from what came back.
    """
    from fragility import vix_term_reason
    from quant_context import _fetch_fragility_histories, vol_feed_report

    histories = _fetch_fragility_histories()
    if not histories:
        return 1, [("PROBE", "FAIL", "the fragility fetch returned nothing at all "
                                     "(yfinance unavailable, or no network)")]

    lines = [("PROBE", "INFO",
              f"fetched {len(histories)} series: {', '.join(sorted(histories))}")]
    for leg, rec in sorted(vol_feed_report().items()):
        rec = rec or {}
        msg = f"{leg}: source={rec.get('source', '?')}"
        if rec.get("last"):
            msg += f", last={rec['last']}"
        if rec.get("stale_obs") is not None:
            msg += f", {rec['stale_obs']} obs behind the anchor"
        if rec.get("error"):
            msg += f" — {rec['error']}"
        lines.append(("PROBE", "WARN" if rec.get("error") else "OK", msg))

    reason = vix_term_reason(histories.get("vix"), histories.get("vix3m"))
    if reason is None:
        lines.append(("PROBE", "OK", "vix_term computes from these feeds — "
                                     "the composite would carry its calibrated label"))
        return 0, lines
    lines.append(("PROBE", "FAIL", f"vix_term cannot be computed — {reason}"))
    return 1, lines


def check_lines(result: tuple[int, list[tuple[str, str, str]]],
                strict: bool) -> tuple[list[tuple[str, str, str]], bool]:
    """Map a `probe()` result onto the data check's log lines and whether it
    should fail the run.

    The whole strictness rule, in one pure function so it can be read and
    tested without a network: a dead vol leg is a `WARN` on a normal stage-1
    run — it costs the composite its calibrated label, never the day's note —
    and a `FAIL` only when the run was dispatched to answer for it
    (`--strict-feeds`, which `pipeline.yml mode=validate` passes).
    """
    code, lines = result
    out = [("CHECK", "FAIL" if (level == "FAIL" and strict) else
                     ("WARN" if level == "FAIL" else level),
            f"Fragility feeds: {msg}")
           for _section, level, msg in lines]
    return out, bool(code) and strict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log-dir", default=str(QUANT_LOG_DIR),
                        help="quant_context_log directory (default: results/quant_context_log)")
    parser.add_argument("--asof", default=None, metavar="YYYY-MM-DD",
                        help="ignore readings after this date (the pipeline pins the run's date)")
    parser.add_argument("--max-streak", type=int, default=MAX_DEGRADED_STREAK,
                        help=f"consecutive degraded readings tolerated (default {MAX_DEGRADED_STREAK})")
    parser.add_argument("--warn-only", action="store_true",
                        help="report and always exit 0")
    parser.add_argument("--probe", action="store_true",
                        help="fetch the vol legs live and say why vix_term is missing "
                             "right now (costs network; not part of the daily gate)")
    parser.add_argument("--probe-cboe", action="store_true",
                        help="fetch CBOE's own CSV directly — the only way to find out "
                             "whether the fallback works, since it is never invoked "
                             "while yfinance is fresh")
    args = parser.parse_args()

    if args.probe_cboe:
        code, lines = probe_cboe()
    elif args.probe:
        code, lines = probe()
    else:
        asof = date.fromisoformat(args.asof) if args.asof else None
        code, lines = audit(Path(args.log_dir), asof, args.max_streak)
    for section, level, msg in lines:
        _log(section, level, msg)
    return 0 if args.warn_only else code


if __name__ == "__main__":
    sys.exit(main())
