"""
test_fed_docs.py — WP-19.B FOMC statement fetcher (Phase 19 monetary slice).

Pure, no network: statement-link parsing (dedup, sort, point-in-time selection)
and lenient body-text extraction, exercised with synthetic HTML.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exogenous.fed_docs import (
    FED_HOST,
    extract_statement_text,
    latest_statement_link,
    parse_statement_links,
)

_CALENDAR = """
<html><body>
  <a href="/newsevents/pressreleases/monetary20260318a.htm">Statement</a>
  <a href="/monetarypolicy/files/monetary20260318a1.pdf">PDF</a>
  <a href="/newsevents/pressreleases/monetary20260617a.htm">Statement</a>
  <a href="/newsevents/pressreleases/monetary20260128a.htm">Statement</a>
  <a href="/newsevents/pressreleases/monetary20260617a.htm">dup link</a>
  <a href="/newsevents/pressreleases/otherpress20260601a.htm">not a statement</a>
</body></html>
"""


class TestParseLinks:
    def test_finds_dedups_sorts(self):
        links = parse_statement_links(_CALENDAR)
        assert [d for d, _ in links] == [
            date(2026, 1, 28), date(2026, 3, 18), date(2026, 6, 17)
        ]

    def test_urls_absolute(self):
        links = parse_statement_links(_CALENDAR)
        assert links[-1][1] == f"{FED_HOST}/newsevents/pressreleases/monetary20260617a.htm"

    def test_ignores_non_statements(self):
        links = parse_statement_links(_CALENDAR)
        assert all("otherpress" not in u for _, u in links)

    def test_empty_html(self):
        assert parse_statement_links("<html></html>") == []


class TestLatestLink:
    def _links(self):
        return parse_statement_links(_CALENDAR)

    def test_point_in_time_selection(self):
        # as-of just after the March meeting → March is latest, not June
        got = latest_statement_link(self._links(), date(2026, 4, 1))
        assert got[0] == date(2026, 3, 18)

    def test_latest_overall(self):
        got = latest_statement_link(self._links(), date(2026, 7, 24))
        assert got[0] == date(2026, 6, 17)

    def test_none_before_any(self):
        assert latest_statement_link(self._links(), date(2026, 1, 1)) is None

    def test_none_when_empty(self):
        assert latest_statement_link([], date(2026, 7, 24)) is None


_STMT_PAGE = """
<html><head><title>Federal Reserve issues FOMC statement</title></head>
<body>
  <nav>SKIP NAV LINKS</nav>
  <header>SKIP HEADER</header>
  <div id="article">
    <p>The Committee decided to maintain the target range for the federal funds
       rate at 3-1/2 to 3-3/4 percent.</p>
    <p>Inflation remains elevated relative to the Committee's 2 percent goal.</p>
    <script>console.log('skip me')</script>
  </div>
  <footer>SKIP FOOTER CONTACT</footer>
</body></html>
"""


class TestExtractText:
    def test_pulls_statement_body(self):
        text = extract_statement_text(_STMT_PAGE)
        assert "maintain the target range" in text
        assert "Inflation remains elevated" in text

    def test_drops_chrome_and_scripts(self):
        text = extract_statement_text(_STMT_PAGE)
        for junk in ("SKIP NAV", "SKIP HEADER", "SKIP FOOTER", "console.log"):
            assert junk not in text

    def test_falls_back_without_article_div(self):
        html = "<html><body><div class='col-md-8'><p>Body only here.</p></div></body></html>"
        assert "Body only here." in extract_statement_text(html)

    def test_collapses_blank_lines(self):
        text = extract_statement_text(_STMT_PAGE)
        assert "\n\n" not in text
