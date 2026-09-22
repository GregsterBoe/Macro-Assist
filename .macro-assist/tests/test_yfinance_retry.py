"""
The 2026-09-16 → 09-18 `vix_term` hole ([KB-034]) was not an outage. yfinance's
`^VIX3M` returned an EMPTY FRAME at ~06:04 UTC — no exception, no status code —
and current data at 16:24 UTC the same day. Every live fetch path made exactly
one attempt and read that empty frame as "this ticker has no history", so the
composite lost its calibrated label on three consecutive readings.

These tests pin todo #26 work item 1: two attempts before a leg is called
absent, an empty frame counted as a failure rather than an answer, and a reason
the caller's own warning can still print.

`time.sleep` is injected, never waited through.
"""
from __future__ import annotations

import pandas as pd
import pytest

import fragility_panel
import market_data
import pipeline_common
import quant_context
from pipeline_common import yf_history_with_retry


def _frame(rows: int = 3) -> pd.DataFrame:
    idx = pd.date_range("2026-09-14", periods=rows, tz="UTC")
    return pd.DataFrame({"Close": [10.0 + i for i in range(rows)]}, index=idx)


EMPTY = pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([], tz="UTC"))


class _Sleeper:
    """Records the backoff schedule instead of sleeping it."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


# ---------------------------------------------------------------------------
# The helper itself
# ---------------------------------------------------------------------------

def test_first_attempt_succeeds_costs_one_call():
    calls = []
    sleep = _Sleeper()

    def fetch():
        calls.append(1)
        return _frame()

    hist, reason = yf_history_with_retry(fetch, "^VIX3M", sleep=sleep)
    assert reason is None
    assert len(hist) == 3
    assert len(calls) == 1, "a working feed must not pay for the retry budget"
    assert sleep.waits == []


def test_empty_frame_is_retried_not_accepted():
    """The 2026-09-16 failure mode: no exception, just nothing."""
    results = [EMPTY, _frame()]
    sleep = _Sleeper()

    hist, reason = yf_history_with_retry(lambda: results.pop(0), "^VIX3M", sleep=sleep)
    assert reason is None
    assert len(hist) == 3, "the second attempt's data must be the answer"
    assert sleep.waits == [pipeline_common._YF_BACKOFF_SECONDS]


def test_empty_twice_reports_empty_not_an_exception():
    sleep = _Sleeper()
    hist, reason = yf_history_with_retry(lambda: EMPTY, "^VIX3M", sleep=sleep)
    assert hist is None
    assert "empty frame" in reason and "2 attempts" in reason


def test_exception_is_retried_and_named():
    calls = []
    sleep = _Sleeper()

    def fetch():
        calls.append(1)
        raise ConnectionResetError("peer hung up")

    hist, reason = yf_history_with_retry(fetch, "^VIX3M", sleep=sleep)
    assert hist is None
    assert len(calls) == 2
    # the reason must stay diagnosable — an exception and an empty frame are
    # different failures and the log has to tell them apart
    assert "ConnectionResetError" in reason and "peer hung up" in reason


def test_exception_then_success():
    results = [ConnectionResetError("reset"), _frame()]

    def fetch():
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    hist, reason = yf_history_with_retry(fetch, "^VIX", sleep=_Sleeper())
    assert reason is None and len(hist) == 3


def test_helper_never_raises():
    """Every call site degrades on a missing leg; a new exception type would
    change what a dead leg does."""
    def fetch():
        raise KeyboardInterrupt  # not even a subclass of Exception

    with pytest.raises(KeyboardInterrupt):
        yf_history_with_retry(fetch, "^VIX", sleep=_Sleeper())


def test_budget_is_two_attempts():
    """Pinned deliberately: same ceiling as the CBOE client. A feed that is
    genuinely down should be reported, not hammered."""
    assert pipeline_common._YF_ATTEMPTS == fragility_panel._CBOE_ATTEMPTS == 2


# ---------------------------------------------------------------------------
# The three live call sites
# ---------------------------------------------------------------------------

class _Ticker:
    """Stands in for yf.Ticker, counting attempts per symbol."""

    calls: dict[str, int] = {}
    script: dict[str, list] = {}

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, *_a, **_kw):
        _Ticker.calls[self.symbol] = _Ticker.calls.get(self.symbol, 0) + 1
        queue = _Ticker.script.get(self.symbol)
        if not queue:
            return _frame(300)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def ticker(monkeypatch):
    _Ticker.calls, _Ticker.script = {}, {}
    monkeypatch.setattr(pipeline_common, "_YF_BACKOFF_SECONDS", 0.0)
    for mod in (market_data, fragility_panel, quant_context):
        yf = getattr(mod, "yf", None)
        if yf is not None:
            monkeypatch.setattr(yf, "Ticker", _Ticker)
    return _Ticker


def test_ticker_snapshot_retries_an_empty_frame(monkeypatch, ticker):
    monkeypatch.setattr(market_data.yf, "Ticker", _Ticker)
    ticker.script["^VIX3M"] = [EMPTY, _frame(5)]

    snapshot, close = market_data._ticker_snapshot("^VIX3M", "5d")
    assert snapshot is not None, "the second attempt's data must reach the payload"
    assert ticker.calls["^VIX3M"] == 2


def test_ticker_snapshot_gives_up_after_two(monkeypatch, ticker):
    monkeypatch.setattr(market_data.yf, "Ticker", _Ticker)
    ticker.script["^VIX3M"] = [EMPTY, EMPTY]

    snapshot, close = market_data._ticker_snapshot("^VIX3M", "5d")
    assert snapshot is None and close is None
    assert ticker.calls["^VIX3M"] == 2


def test_fragility_histories_retry_the_vol_leg(monkeypatch, ticker):
    """The live path that actually produced the three `Unavailable` readings."""
    import yfinance as yf_real
    monkeypatch.setattr(yf_real, "Ticker", _Ticker)
    monkeypatch.setattr(quant_context, "_FEED_REPORT", {}, raising=False)
    monkeypatch.setattr(fragility_panel, "freshen_vol_indices",
                        lambda hist, **kw: hist)
    ticker.script["^VIX3M"] = [EMPTY, _frame(300)]

    out = quant_context._fetch_fragility_histories()
    assert "vix3m" in out, "an empty first frame must not drop the leg"
    assert ticker.calls["^VIX3M"] == 2


def test_panel_fetch_histories_retries(monkeypatch, ticker):
    import yfinance as yf_real
    monkeypatch.setattr(yf_real, "Ticker", _Ticker)
    monkeypatch.setattr(fragility_panel, "freshen_vol_indices",
                        lambda hist, **kw: hist)
    ticker.script["^VIX3M"] = [EMPTY, _frame(300)]

    out = fragility_panel.fetch_histories(start=None, period="1y")
    assert "vix3m" in out
    assert ticker.calls["^VIX3M"] == 2
