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


# ---------------------------------------------------------------------------
# todo #31 — a rescued leg must be recorded, not just printed
#
# The retry above fixes the cheapest failure and hides it in the same move: a
# day where `^VIX3M` came back empty and then answered was logged exactly like
# a healthy day. Watching the 06:23 slot is the alternative to moving the run,
# so a retry that carries the slot every morning has to be visible in the log.
# ---------------------------------------------------------------------------

def test_report_on_a_first_attempt_success_has_no_failures():
    report: dict = {}
    yf_history_with_retry(_frame, "^VIX3M", sleep=_Sleeper(), report=report)
    assert report == {"attempts": 1, "failures": []}


def test_report_records_a_rescue():
    results = [EMPTY, _frame()]
    report: dict = {}
    hist, _ = yf_history_with_retry(lambda: results.pop(0), "^VIX3M",
                                    sleep=_Sleeper(), report=report)
    assert hist is not None
    assert report == {"attempts": 2, "failures": ["empty frame"]}


def test_report_records_every_failure_when_the_leg_is_lost():
    results = [ConnectionResetError("reset"), EMPTY]

    def fetch():
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    report: dict = {}
    hist, _ = yf_history_with_retry(fetch, "^VIX3M", sleep=_Sleeper(), report=report)
    assert hist is None
    assert report == {"attempts": 2,
                      "failures": ["ConnectionResetError: reset", "empty frame"]}


def test_live_fetch_records_only_the_legs_that_retried(monkeypatch, ticker):
    import yfinance as yf_real
    monkeypatch.setattr(yf_real, "Ticker", _Ticker)
    monkeypatch.setattr(quant_context, "_FEED_REPORT", {}, raising=False)
    monkeypatch.setattr(quant_context, "_RETRY_REPORT", {"stale": {}}, raising=False)
    monkeypatch.setattr(fragility_panel, "freshen_vol_indices",
                        lambda hist, **kw: hist)
    ticker.script["^VIX3M"] = [EMPTY, _frame(300)]
    ticker.script["GC=F"] = [EMPTY, EMPTY]

    quant_context._fetch_fragility_histories()
    assert quant_context.yf_retry_report() == {
        "vix3m": {"attempts": 2, "rescued": True, "failures": ["empty frame"]},
        "gold": {"attempts": 2, "rescued": False,
                 "failures": ["empty frame", "empty frame"]},
    }, "a previous run's record must be cleared, and a healthy leg must be absent"


def test_live_fetch_on_a_healthy_day_records_nothing(monkeypatch, ticker):
    import yfinance as yf_real
    monkeypatch.setattr(yf_real, "Ticker", _Ticker)
    monkeypatch.setattr(quant_context, "_FEED_REPORT", {}, raising=False)
    monkeypatch.setattr(quant_context, "_RETRY_REPORT", {}, raising=False)
    monkeypatch.setattr(fragility_panel, "freshen_vol_indices",
                        lambda hist, **kw: hist)

    quant_context._fetch_fragility_histories()
    assert quant_context.yf_retry_report() == {}


_FRAG = {"composite": 24.0, "label": "Resilient", "trend": "Falling",
         "components": {"variance_trend": {"score": 23.0}},
         "weights": {"variance_trend": 0.9}, "degraded": []}


def _quant_raw(monkeypatch, retries: dict) -> dict:
    from datetime import date
    monkeypatch.setattr(quant_context, "_compute_fragility", lambda *a, **kw: dict(_FRAG))
    monkeypatch.setattr(quant_context, "_compute_or_mode", lambda *a, **kw: None)
    monkeypatch.setattr(quant_context, "vol_feed_report", lambda: {})
    monkeypatch.setattr(quant_context, "yf_retry_report", lambda: retries)
    return quant_context.collect_quant_raw({}, date(2026, 10, 1), histories={"x": 1},
                                           distribution_table={})


def test_a_rescued_leg_reaches_the_log_on_an_otherwise_healthy_day(monkeypatch):
    rescued = {"vix3m": {"attempts": 2, "rescued": True, "failures": ["empty frame"]}}
    frag = _quant_raw(monkeypatch, rescued)["fragility"]
    assert frag["degraded"] == [] and "feed" not in frag, "the reading itself is whole"
    assert frag["retries"] == rescued


def test_a_first_attempt_day_logs_exactly_as_before(monkeypatch):
    assert "retries" not in _quant_raw(monkeypatch, {})["fragility"]


def test_the_log_line_names_a_rescue_and_stays_ok():
    raw = {"fragility": {**_FRAG, "components": {"variance_trend": 23.0}, "mode": "log",
                         "retries": {"vix3m": {"attempts": 2, "rescued": True,
                                               "failures": ["empty frame"]}}}}
    (_, level, msg), = quant_context.fragility_log_lines(raw)
    assert level == "OK", "a rescued leg is not a degraded reading"
    assert "retry rescued vix3m" in msg


# ---------------------------------------------------------------------------
# todo #26 — the payload's vol legs get the issuer fallback the fragility path has
#
# On 2026-09-16 → 09-18 `^VIX3M` came back empty and `vix_term_ratio` vanished
# from the prompt with nothing standing in. And VIX is critical: a missing one
# aborts the note. CBOE's own file may now fill either payload value — only
# when it is dated the S&P's last session, so a ratio is never one day's VIX
# over an older VIX3M (the KB-029 shape).
# ---------------------------------------------------------------------------

def _cboe_series(rows: int = 300, lag: int = 0) -> pd.Series:
    """CBOE's file as `fetch_cboe_index` returns it: tz-naive, plain dates."""
    idx = pd.date_range("2026-09-14", periods=rows - lag)
    return pd.Series([20.0 + 0.01 * i for i in range(rows - lag)], index=idx)


@pytest.fixture
def cboe(monkeypatch):
    """Route `freshen_vol_indices` to a scripted CBOE and count its calls."""
    calls: list[str] = []
    script: dict = {}
    real = fragility_panel.freshen_vol_indices

    def fake_fetch(symbol):
        calls.append(symbol)
        return script.get(symbol, _cboe_series())

    monkeypatch.setattr(fragility_panel, "freshen_vol_indices",
                        lambda hist, **kw: real(hist, fetch=fake_fetch, **kw))
    return calls, script


def test_a_normal_day_never_asks_cboe(monkeypatch, ticker, cboe):
    calls, _ = cboe
    data, _hist = market_data.fetch_market_data()
    assert calls == [], "both legs fresh: the fallback must be a no-op"
    assert market_data.market_feed_report() == {}
    assert data["vix3m"]["date"] == data["sp500"]["date"]


def test_an_empty_vix3m_is_filled_from_cboe_on_the_same_day(monkeypatch, ticker, cboe):
    calls, _ = cboe
    ticker.script["^VIX3M"] = [EMPTY, EMPTY]
    data, hist = market_data.fetch_market_data()
    assert calls == ["VIX3M"]
    assert data["vix3m"]["date"] == data["sp500"]["date"]
    assert data["vix3m"]["price"] == round(_cboe_series().iloc[-1], 2)
    assert "vix3m" not in hist, "only the payload value is replaced"
    report = market_data.market_feed_report()
    assert report["vol"]["vix3m"]["source"] == "cboe" and report["vol"]["vix3m"]["used"]
    assert report["retries"]["vix3m"] == {"attempts": 2, "rescued": False,
                                          "failures": ["empty frame", "empty frame"]}


def test_a_cboe_value_from_an_older_session_is_refused(monkeypatch, ticker, cboe):
    """A missing ratio is honest; one day's VIX over yesterday's VIX3M is not."""
    _, script = cboe
    script["VIX3M"] = _cboe_series(lag=1)
    ticker.script["^VIX3M"] = [EMPTY, EMPTY]
    data, _ = market_data.fetch_market_data()
    assert "vix3m" not in data
    rec = market_data.market_feed_report()["vol"]["vix3m"]
    assert rec["used"] is False and "is not the S&P's" in rec["error"]


def test_a_missing_vix_no_longer_costs_the_note(monkeypatch, ticker, cboe):
    """VIX is in `_CRITICAL_MARKET`; before the fallback this day aborted."""
    import collect_and_analyze
    ticker.script["^VIX"] = [EMPTY, EMPTY]
    data, _ = market_data.fetch_market_data()
    assert "vix" in data
    assert all(k in data for k in collect_and_analyze._CRITICAL_MARKET)


def test_a_dead_fallback_leaves_the_leg_missing_and_says_why(monkeypatch, ticker, cboe):
    _, script = cboe
    script["VIX3M"] = None
    ticker.script["^VIX3M"] = [EMPTY, EMPTY]
    data, _ = market_data.fetch_market_data()
    assert "vix3m" not in data
    assert market_data.market_feed_report()["vol"]["vix3m"]["source"] == "none"


def test_a_rescued_payload_ticker_is_recorded(monkeypatch, ticker, cboe):
    ticker.script["^GSPC"] = [EMPTY, _frame(300)]
    market_data.fetch_market_data()
    assert market_data.market_feed_report() == {
        "retries": {"sp500": {"attempts": 2, "rescued": True,
                              "failures": ["empty frame"]}}}
