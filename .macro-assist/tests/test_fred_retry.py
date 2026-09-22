"""
The 2026-09-22 06:00 UTC run (Actions run 35692953937) aborted the day's
pipeline on a transient FRED failure that was never retried. The abort itself —
whether a critical series should take the note down at all — is todo #28.

`_fred_get_with_retry` decided whether to retry by substring-matching the
exception *text* against rate-limit keywords. `fredapi` re-raises every HTTP
error as `ValueError(root.get('message'))`, and FRED's error body does not
always carry a `message`, so the text was the literal string `"None"` — it
matched nothing, the call re-raised on the first attempt, `fed_funds_rate`
went missing, and `validate_data` aborted before the note was written.

These tests pin the inverted rule: retry unless the error is *known* to be
permanent, and make the log name the status code.

Every test drives the real `_fred_get_with_retry`; `time.sleep` is patched out
so the backoff schedule is asserted rather than waited through.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

import fred_data


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Record the backoff schedule instead of sleeping it."""
    waits: list[float] = []
    monkeypatch.setattr(fred_data.time, "sleep", waits.append)
    return waits


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://api.stlouisfed.org/fred/series", code, "err", {}, None)


def _fredapi_reraise(code: int, message):
    """Reproduce what `fredapi` actually raises for an HTTP error.

    It catches `HTTPError`, parses the body, and raises
    `ValueError(root.get('message'))` — which is `None` when the body has no
    `message` attribute. Raising inside `except` sets `__context__`, which is
    the only reason the status code is still recoverable.

    `__context__` is attached when the exception is *raised*, not when it is
    constructed, so this has to go through a real raise to be faithful.
    """
    try:
        try:
            raise _http_error(code)
        except HTTPError:
            raise ValueError(message)
    except ValueError as exc:
        return exc


def _server(*outcomes):
    """A fake `Fred` whose `get_series` yields each outcome in turn."""
    calls = {"n": 0}

    def get_series(series_id, observation_start=None):
        i = calls["n"]
        calls["n"] += 1
        outcome = outcomes[min(i, len(outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    fred = MagicMock()
    fred.get_series.side_effect = get_series
    return fred, calls


def _ok() -> pd.Series:
    return pd.Series([1.0, 2.0], index=pd.date_range("2026-09-01", periods=2))


# ---------------------------------------------------------------------------
# The regression itself
# ---------------------------------------------------------------------------

def test_the_2026_09_22_failure_is_now_retried(_no_sleeping):
    """`ValueError(None)` behind a 5xx — the exact shape that lost the note."""
    fred, calls = _server(_fredapi_reraise(503, None), _ok())
    out = fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22")
    assert list(out) == [1.0, 2.0]
    assert calls["n"] == 2, "the first failure must have been retried"
    assert _no_sleeping, "a retry must back off rather than hammer FRED"


def test_a_message_less_error_is_not_read_as_permanent():
    """No status code, no message: the default must be 'try again'."""
    assert fred_data._fred_error_is_permanent(ValueError(None)) is False


def test_exhausting_the_retries_still_raises(_no_sleeping):
    fred, calls = _server(_fredapi_reraise(503, None))
    with pytest.raises(ValueError):
        fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22", max_retries=2)
    assert calls["n"] == 3, "max_retries=2 means one attempt plus two retries"


# ---------------------------------------------------------------------------
# What must NOT be retried
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [400, 403, 404])
def test_client_errors_are_permanent_and_cost_one_attempt(code, _no_sleeping):
    fred, calls = _server(_fredapi_reraise(code, "Bad Request. The series does not exist."))
    with pytest.raises(ValueError):
        fred_data._fred_get_with_retry(fred, "NOPE", "2021-09-22")
    assert calls["n"] == 1
    assert _no_sleeping == []


@pytest.mark.parametrize("code", [400, 403, 404])
def test_a_client_error_is_permanent_on_its_status_alone(code):
    """No keyword can help here — the message is `None`, as on 2026-09-22.

    Without this, `_FRED_PERMANENT_KEYWORDS` would be doing all the work and
    the status-code branch could rot unnoticed.
    """
    assert fred_data._fred_error_is_permanent(_fredapi_reraise(code, None)) is True
    # The two 4xx that describe the moment, not the request.
    assert fred_data._fred_error_is_permanent(_fredapi_reraise(429, None)) is False
    assert fred_data._fred_error_is_permanent(_fredapi_reraise(408, None)) is False


def test_permanent_message_is_honoured_when_no_status_code_survives(_no_sleeping):
    """A bare `ValueError` with no `__context__` — the code is gone, the text is not."""
    fred, calls = _server(ValueError("Bad Request. The series does not exist."))
    with pytest.raises(ValueError):
        fred_data._fred_get_with_retry(fred, "NOPE", "2021-09-22")
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# What must be retried
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failure", [
    pytest.param(_fredapi_reraise(500, None), id="500-no-message"),
    pytest.param(_fredapi_reraise(502, "Bad Gateway"), id="502"),
    pytest.param(_fredapi_reraise(429, "Too Many Requests"), id="429"),
    pytest.param(_fredapi_reraise(408, None), id="408-request-timeout"),
    pytest.param(URLError("timed out"), id="transport"),
    pytest.param(TimeoutError("read timed out"), id="timeout"),
])
def test_transient_failures_are_retried(failure, _no_sleeping):
    fred, calls = _server(failure, _ok())
    fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22")
    assert calls["n"] == 2


def test_rate_limits_wait_longer_than_a_server_wobble(_no_sleeping):
    """A 429 needs the window to roll over; a 5xx usually clears in seconds.

    One schedule for both would put ~20 minutes of sleeping between the note
    and a FRED-wide wobble across 17 series.
    """
    fred, _ = _server(_fredapi_reraise(429, "Too Many Requests"), _ok())
    fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22")
    rate_limited = list(_no_sleeping)
    _no_sleeping.clear()

    fred, _ = _server(_fredapi_reraise(503, None), _ok())
    fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22")
    transient = list(_no_sleeping)

    assert rate_limited == [10]
    assert transient == [2]
    assert transient[0] < rate_limited[0]


def test_the_full_transient_backoff_stays_short(_no_sleeping):
    """17 series × this schedule must not dominate the run."""
    fred, _ = _server(_fredapi_reraise(503, None))
    with pytest.raises(ValueError):
        fred_data._fred_get_with_retry(fred, "FEDFUNDS", "2021-09-22")
    assert _no_sleeping == [2, 4, 8]
    assert sum(_no_sleeping) * 17 < 5 * 60


# ---------------------------------------------------------------------------
# The log has to be diagnosable
# ---------------------------------------------------------------------------

def test_the_status_code_reaches_the_log():
    """`unavailable: None` is what made 2026-09-22 need log archaeology."""
    described = fred_data._describe_fred_error(_fredapi_reraise(503, None))
    assert "503" in described
    assert described != "None"
    assert "ValueError" in described


def test_describe_survives_an_error_with_no_context():
    assert "boom" in fred_data._describe_fred_error(ValueError("boom"))


def test_status_code_lookup_terminates_on_a_cyclic_chain():
    """`__context__` chains are not guaranteed acyclic; the walk is bounded."""
    a, b = ValueError("a"), ValueError("b")
    a.__context__ = b
    b.__context__ = a
    assert fred_data._fred_status_code(a) is None


# ---------------------------------------------------------------------------
# The critical-series abort, end to end
# ---------------------------------------------------------------------------

def test_a_retried_critical_series_no_longer_aborts_the_run(monkeypatch, _no_sleeping):
    """The whole point: FEDFUNDS wobbles once, the fetch still returns it.

    `validate_data` aborts when `fed_funds_rate` is absent, so a series that
    recovers on retry is the difference between a note and no note.
    """
    import collect_and_analyze

    served = {sid: _ok() for sid in fred_data.FRED_SERIES.values()}
    first_call = {"FEDFUNDS": True}

    def get_series(series_id, observation_start=None):
        if series_id == "FEDFUNDS" and first_call.pop("FEDFUNDS", False):
            raise _fredapi_reraise(503, None)
        return served[series_id]

    fred = MagicMock()
    fred.get_series.side_effect = get_series
    monkeypatch.setattr(fred_data.time, "sleep", lambda _s: None)

    data = fred_data.fetch_fred_data(fred)
    assert "fed_funds_rate" in data

    # Nothing critical is missing, so validate_data must not call sys.exit.
    collect_and_analyze.validate_data(
        data, {k: {} for k in collect_and_analyze._CRITICAL_MARKET}
    )
