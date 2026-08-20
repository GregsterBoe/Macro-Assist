"""Economic-calendar / FOMC event lookups for the daily pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from pipeline_common import (
    _log,
)


# ---------------------------------------------------------------------------
# Economic calendar
# ---------------------------------------------------------------------------

# FOMC meeting dates (start of 2-day meeting; decision on day 2).
# !! UPDATE THIS LIST EVERY JANUARY !!
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def _check_fomc_dates_expiry(today: datetime) -> None:
    """Warn in CI if the hardcoded FOMC list runs out within 60 days."""
    if not FOMC_DATES:
        _log("EVENTS", "WARN", "FOMC_DATES list is empty — update required")
        return
    last = datetime.strptime(FOMC_DATES[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days_remaining = (last - today).days
    if days_remaining < 60:
        _log("EVENTS", "WARN",
             f"FOMC_DATES expires in {days_remaining}d ({FOMC_DATES[-1]}) — "
             "update list from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")

# BLS release names to watch (matched as substrings against BLS schedule)
BLS_RELEASES_OF_INTEREST = {"consumer price index", "employment situation", "producer price index"}


def fetch_upcoming_events(today: datetime, lookahead_days: int = 7) -> str:
    """
    Returns a formatted ## Upcoming Events block covering:
    - BLS high-impact releases (CPI, PPI, NFP) within the next `lookahead_days`
    - FOMC meeting dates within the next `lookahead_days`
    Returns empty string on any fetch failure so the pipeline never crashes.
    """
    today_date = today.date()
    cutoff     = today_date + timedelta(days=lookahead_days)
    events     = []

    # --- BLS releases ---
    try:
        resp = requests.get(
            "https://www.bls.gov/schedule/news_release/schedule.json",
            timeout=10,
            headers={"User-Agent": "macro-assist/1.0"},
        )
        if resp.ok:
            for item in resp.json().get("releases", []):
                name     = item.get("release_name", "").lower()
                date_str = item.get("date", "")
                if not any(k in name for k in BLS_RELEASES_OF_INTEREST):
                    continue
                try:
                    rel_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if today_date <= rel_date <= cutoff:
                    days_away = (rel_date - today_date).days
                    label = "TODAY" if days_away == 0 else f"in {days_away}d"
                    events.append((rel_date, f"BLS: {item.get('release_name')} ({label})"))
    except Exception as e:
        print(f"  Warning: BLS calendar fetch failed: {e}")

    # --- FOMC dates ---
    for date_str in FOMC_DATES:
        try:
            fomc_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        # Show the decision day (day after start) and the start day
        for offset, label in [(0, "FOMC meeting begins"), (1, "FOMC decision day")]:
            event_date = fomc_date + timedelta(days=offset)
            if today_date <= event_date <= cutoff:
                days_away = (event_date - today_date).days
                tag = "TODAY" if days_away == 0 else f"in {days_away}d"
                events.append((event_date, f"Fed: {label} ({tag})"))

    if not events:
        return ""

    events.sort(key=lambda x: x[0])
    lines = ["## Upcoming Events (next 7 days)"]
    for _, desc in events:
        lines.append(f"- {desc}")
    return "\n".join(lines)
