"""
fed_docs.py — WP-19.B L0 fetcher: auto-pull the latest FOMC policy statement.

The evolving-signal source for the monetary branch (DESIGN §3/§6.5). Statements
live at a stable URL pattern on federalreserve.gov and are linked from the FOMC
calendar page; each carries its release date IN the URL (`monetaryYYYYMMDDa.htm`),
which is the point-in-time `published` key (DESIGN §6.2) — no guessing.

Same split as the rest of the package: **link parsing + text extraction are pure**
(unit-tested with synthetic HTML, no network); the `requests` calls are a thin
shell (user/CI-run), matching how `collect_and_analyze` / `point_in_time` fetch.

Robustness: statements are monthly, so this runs weekly and re-emits only when the
newest statement date changes (the caller caches). Text extraction is deliberately
lenient — the L1 extractor already ignores boilerplate, so we only need the body
present, not surgically clean.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

FED_HOST = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = f"{FED_HOST}/monetarypolicy/fomccalendars.htm"

# Post-meeting statement press releases: /newsevents/pressreleases/monetaryYYYYMMDDa.htm
_STMT_HREF = re.compile(r"/newsevents/pressreleases/monetary(\d{8})a\.htm", re.I)

_UA = "Macro-Assist/1.0 (research; +https://github.com/GregsterBoe/Macro-Assist)"


# ---------------------------------------------------------------------------
# Pure: parse statement links + extract statement text (no network)
# ---------------------------------------------------------------------------

def parse_statement_links(html: str) -> list[tuple[date, str]]:
    """All FOMC-statement press-release links in `html`, as (release_date, url).

    Deduplicated and sorted ascending by date. The date comes from the URL slug
    (YYYYMMDD) — the statement's release date, our point-in-time key.
    """
    seen: dict[date, str] = {}
    for m in _STMT_HREF.finditer(html):
        ymd = m.group(1)
        try:
            d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
        except ValueError:
            continue
        seen[d] = FED_HOST + m.group(0)
    return sorted(seen.items())


def latest_statement_link(
    links: list[tuple[date, str]], asof: Optional[date] = None
) -> Optional[tuple[date, str]]:
    """Newest (release_date, url) on/before `asof` (point-in-time). None if empty."""
    asof = asof or date.today()
    prior = [(d, u) for d, u in links if d <= asof]
    return prior[-1] if prior else None


def extract_statement_text(html: str) -> str:
    """Statement body text from a Fed press-release page.

    Prefers the article container; falls back to the main content column, then the
    whole document. Collapses whitespace. Lenient by design (see module docstring).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    node = (
        soup.find("div", id="article")
        or soup.find("div", class_=re.compile(r"col-md-8"))
        or soup.body
        or soup
    )
    # Drop obvious non-statement chrome.
    for tag in node.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = node.get_text(separator="\n")
    # Collapse runs of blank lines / trailing spaces.
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


# ---------------------------------------------------------------------------
# IO shell — fetch from federalreserve.gov (needs network; user/CI-run)
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30) -> str:
    import requests
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
    resp.raise_for_status()
    # Fed pages are UTF-8 but the header often omits it → requests guesses latin-1
    # and mangles en-dashes ("12 – 0" → mojibake). Prefer the detected encoding.
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_latest_statement(asof: Optional[date] = None) -> Optional[dict]:
    """Pull the most recent FOMC statement available on/before `asof`.

    Returns {"published": iso, "source_id": url, "text": str} or None if no
    statement link is found. `published` is the URL-slug date (point-in-time safe).
    """
    calendar = _get(FOMC_CALENDAR_URL)
    latest = latest_statement_link(parse_statement_links(calendar), asof)
    if latest is None:
        return None
    published, url = latest
    text = extract_statement_text(_get(url))
    return {"published": published.isoformat(), "source_id": url, "text": text}


def _main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Fetch the latest FOMC statement")
    ap.add_argument("--asof", type=str, default=None, help="point-in-time date (YYYY-MM-DD)")
    ap.add_argument("--text", action="store_true", help="print the full statement text")
    args = ap.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else None
    got = fetch_latest_statement(asof)
    if got is None:
        print("No FOMC statement link found.")
        return
    if args.text:
        print(got["text"])
    else:
        print(json.dumps({k: v for k, v in got.items() if k != "text"}, indent=2))
        print(f"\n(text: {len(got['text'])} chars — pass --text to print)")


if __name__ == "__main__":
    _main()
