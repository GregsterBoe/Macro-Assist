"""FRED data fetching for the daily macro pipeline (net liquidity, retry/backoff)."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from fredapi import Fred

from pipeline_common import (
    _log, REPO_ROOT,
)


# ---------------------------------------------------------------------------
# FRED data
# ---------------------------------------------------------------------------

FRED_SERIES = {
    "fed_funds_rate":    "FEDFUNDS",
    "cpi":               "CPIAUCSL",
    "gdp":               "GDP",
    "unemployment":      "UNRATE",
    "m2":                "M2SL",
    "treasury_10y":      "DGS10",
    "treasury_2y":       "DGS2",
    "hy_spread":         "BAMLH0A0HYM2",        # HY corporate bond OAS spread (%) — free FRED
                                                 # serves only a ~3y rolling window (KB-021)
    # baa_spread (BAA10Y) removed from the PAYLOAD 2026-06-27 (WP-18.4 cleanup): its only
    # consumer was the retired HMM regime credit feature (KB-006); 0/78 model citations
    # (KB-010). Since 2026-09-13 it is the conditional bucket's credit input again
    # (WP-17.5) — fetched by fetch_quant_inputs() below, merged into the quant layer's
    # snapshot only, never into the model's message.
    "philly_fed_mfg":    "GACDFSA066MSFRBPHI",  # Philly Fed diffusion index; >0 expanding
    "real_yield_10y":    "DFII10",              # 10Y TIPS real yield (daily)
    "breakeven_10y":     "T10YIE",              # 10Y inflation breakeven rate (daily)
    # --- Phase 1 additions ---
    "fed_total_assets":  "WALCL",       # Fed balance sheet (millions USD; scaled ÷1000 → billions)
    "treasury_gen_acct": "WTREGEN",     # Treasury General Account (millions USD → ÷1000 = billions)
    "reverse_repo":      "RRPONTSYD",   # Overnight reverse repo (billions USD)
    "jobless_claims":    "ICSA",        # Initial jobless claims (weekly, thousands)
    "nfci":              "NFCI",        # Chicago Fed National Financial Conditions Index
}

# Keys whose raw Series are retained after the fetch loop for net-liquidity calculation
_NET_LIQ_KEYS = {"fed_total_assets", "treasury_gen_acct", "reverse_repo"}

# Series the quant layer needs that are deliberately NOT in the LLM payload.
# `conditional.assign_bucket` reads `baa_spread` (conditional.CREDIT_SERIES_KEY)
# for its credit tertile; the payload keeps `hy_spread`, which the model cites.
QUANT_FRED_SERIES = {
    "baa_spread": "BAA10Y",   # Moody's Baa − 10Y Treasury (pp), daily, 1986+
}

# Release frequency per series — injected as metadata so Claude applies the right staleness threshold
FRED_SERIES_FREQUENCY = {
    "fed_funds_rate":    "monthly",    # FOMC sets rate at ~6-week intervals; data dated month-start
    "cpi":               "monthly",
    "gdp":               "quarterly",
    "unemployment":      "monthly",
    "m2":                "monthly",
    "treasury_10y":      "daily",
    "treasury_2y":       "daily",
    "hy_spread":         "daily",
    "philly_fed_mfg":    "monthly",
    "real_yield_10y":    "daily",
    "breakeven_10y":     "daily",
    "fed_total_assets":  "weekly",
    "treasury_gen_acct": "weekly",
    "reverse_repo":      "daily",
    "jobless_claims":    "weekly",
    "nfci":              "weekly",
}


def _compute_net_liquidity(raw_series: dict) -> dict | None:
    """
    Net Liquidity = (WALCL / 1000) - WTREGEN - RRPONTSYD  (all in billions USD).
    WALCL is reported in millions on FRED; the other two in billions.
    Resamples to weekly frequency so all three series align cleanly.
    Returns a signal dict or None if data is insufficient.
    """
    if not all(k in raw_series for k in _NET_LIQ_KEYS):
        return None

    combined = pd.DataFrame({
        "walcl": raw_series["fed_total_assets"] / 1000,    # millions → billions
        "tga":   raw_series["treasury_gen_acct"] / 1000,   # millions → billions (WTREGEN is in millions, same as WALCL)
        "rrp":   raw_series["reverse_repo"],                # already in billions
    }).resample("W").last().ffill().dropna()

    if len(combined) < 5:
        return None

    combined["nl"] = combined["walcl"] - combined["tga"] - combined["rrp"]
    nl = combined["nl"]

    current = float(nl.iloc[-1])
    # Sanity check: Fed net liquidity should be in the range $0–$20T (0–20,000 B).
    # Values outside this range indicate a unit mismatch in one of the component series.
    if not (0 <= current <= 20_000):
        _log("FRED", "WARN",
             f"net liquidity sanity check FAILED: {current:.1f}B — possible unit mismatch; "
             f"walcl={combined['walcl'].iloc[-1]:.0f}B, tga={combined['tga'].iloc[-1]:.0f}B, "
             f"rrp={combined['rrp'].iloc[-1]:.0f}B")
        return None
    wow_ref = float(nl.iloc[-2])
    mom_ref = float(nl.iloc[-5]) if len(nl) >= 5 else None

    wow_pct = round(((current - wow_ref) / abs(wow_ref)) * 100, 2) if wow_ref != 0 else None
    mom_pct = round(((current - mom_ref) / abs(mom_ref)) * 100, 2) if mom_ref and mom_ref != 0 else None

    # 4-week rolling mean trend is more stable than single-week WoW
    roll4 = nl.rolling(4).mean().dropna()
    if len(roll4) >= 2:
        trend = "Expanding" if float(roll4.iloc[-1]) > float(roll4.iloc[-2]) else "Contracting"
    else:
        trend = "Expanding" if (wow_pct or 0) > 0 else "Contracting"
    parts  = [trend]
    if wow_pct is not None:
        parts.append(f"{'+' if wow_pct >= 0 else ''}{wow_pct:.1f}% WoW")
    if mom_pct is not None:
        parts.append(f"{'+' if mom_pct >= 0 else ''}{mom_pct:.1f}% MoM")

    # Cap at today — weekly resampling (resample("W")) assigns period-end Sunday,
    # which places the date in the future when the pipeline runs mid-week.
    as_of = min(combined.index[-1].date(), datetime.now(timezone.utc).date())
    return {
        "value_bn":      round(current, 1),
        "wow_pct":       wow_pct,
        "mom_pct":       mom_pct,
        "trend":         trend,
        "trend_summary": ", ".join(parts),
        "date":          as_of.strftime("%Y-%m-%d"),
    }


_FRED_RATE_LIMIT_KEYWORDS = ("too many requests", "rate limit", "429")
_FRED_INTER_REQUEST_DELAY = 0.6    # seconds between FRED calls — 16 series = ~10s, safely under 120/min

# Messages FRED returns for a request that will never succeed however often it
# is repeated: an unknown series id, an unregistered key, a malformed argument.
# Consulted only when no HTTP status code survived (see `_fred_status_code`).
_FRED_PERMANENT_KEYWORDS = ("does not exist", "api_key", "is not a valid",
                            "not registered")

# The 4xx codes that describe the moment rather than the request, so repeating
# it unchanged can succeed: 408 request timeout, 429 too many requests.
_FRED_TRANSIENT_CLIENT_CODES = frozenset({408, 429})


def _fred_status_code(exc: BaseException) -> int | None:
    """The HTTP status behind a failed FRED call, if it can still be recovered.

    `fredapi` catches `HTTPError` and re-raises `ValueError(root.get('message'))`,
    which throws the status code away. Raising inside an `except` block sets
    `__context__` to the original error, so the `HTTPError` — and its `.code` —
    is usually still reachable one link down the chain.
    """
    seen = 0
    cur: BaseException | None = exc
    while cur is not None and seen < 5:      # bounded: chains can be cyclic
        code = getattr(cur, "code", None)
        if isinstance(code, int):
            return code
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return None


def _describe_fred_error(exc: BaseException) -> str:
    """A one-line description of a failed FRED call that can be acted on.

    The 2026-09-22 06:00 run logged `series FEDFUNDS (fed_funds_rate)
    unavailable: None` and aborted the day's pipeline. The text was literally
    "None" because FRED's error body carried no `message` attribute and
    `fredapi` re-raises `ValueError(root.get('message'))` — so the log named
    neither the status code nor the failure. Recover the code where it survives
    and always name the exception type, so the next failure is diagnosable from
    the log alone.
    """
    detail = f"{type(exc).__name__}: {exc}"
    code = _fred_status_code(exc)
    return f"HTTP {code} — {detail}" if code is not None else detail


def _fred_error_is_permanent(exc: BaseException) -> bool:
    """Would repeating this exact request fail in exactly the same way?

    The default is False. A needless retry costs seconds; a wrong "permanent"
    verdict on a critical series costs the day's note (2026-09-22).
    """
    code = _fred_status_code(exc)
    if code is not None:
        # Every 4xx is a request FRED will reject identically on attempt two —
        # except the two that describe the *moment* rather than the request:
        # 408 (the request timed out) and 429 (too many, too fast). 5xx and
        # anything else is the server having a bad minute.
        return 400 <= code < 500 and code not in _FRED_TRANSIENT_CLIENT_CODES
    return any(kw in str(exc).lower() for kw in _FRED_PERMANENT_KEYWORDS)


def _fred_get_with_retry(fred: Fred, series_id: str, observation_start: str,
                         max_retries: int = 3) -> pd.Series:
    """Fetch a FRED series, retrying anything that is not definitively permanent.

    This predicate used to be the other way round: it retried only when the
    error *text* matched a rate-limit keyword, and re-raised everything else on
    the first attempt. Two failures follow from that, and on the 2026-09-22
    06:00 UTC run (Actions run 35692953937) both fired at once:

    * a transient 5xx or dropped connection — the common FRED failure, and what
      happened that morning — got no retry at all; and
    * the text it matched on is frequently `None` (see `_describe_fred_error`),
      so even a genuine 429 was caught only by luck.

    `fed_funds_rate` is on `_CRITICAL_FRED`, so the pipeline aborted and no note
    was published, over a *monthly* series whose value could not have changed
    that day. The rule is now opt-out: retry unless the error is known to be
    permanent, and let the caller's own error handling deal with the rest.

    This is the policy `trigger_pipeline.sh` already applies to the dispatch
    call it makes — retry transport failures, 429 and 5xx; never retry auth or
    not-found.
    """
    for attempt in range(max_retries + 1):
        try:
            return fred.get_series(series_id, observation_start=observation_start).dropna()
        except Exception as exc:
            if _fred_error_is_permanent(exc) or attempt >= max_retries:
                raise
            # A rate limit needs the window to actually roll over; a 5xx
            # usually clears in seconds. Waiting 70s per series on a FRED-wide
            # wobble would delay the note by ~20 minutes across 17 series.
            code = _fred_status_code(exc)
            rate_limited = code == 429 or (
                code is None
                and any(kw in str(exc).lower() for kw in _FRED_RATE_LIMIT_KEYWORDS)
            )
            wait = (10 * (2 ** attempt)) if rate_limited else (2 * (2 ** attempt))
            _log("FRED", "WARN",
                 f"{series_id} {'rate-limited' if rate_limited else 'transient failure'} "
                 f"({_describe_fred_error(exc)}) — waiting {wait}s "
                 f"(attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
    # Unreachable: the loop either returns or raises on its final attempt.
    raise AssertionError(f"retry loop fell through for {series_id}")


def _mean_window(series: pd.Series) -> dict:
    """The window a `five_yr_mean` was actually computed over.

    `fetch_*` ask FRED for five years, but free FRED serves some series on a
    *rolling* window (`BAMLH0A0HYM2` ≈ 3 years — [KB-028] nuance (d), todo
    #13), so the mean can be of far less than five years of one regime.
    Emitting the true window beside the number is what stops the model being
    told "5-yr average" for something that is not.
    """
    first, last = series.index[0].date(), series.index[-1].date()
    return {
        "mean_window_start": first.isoformat(),
        "mean_window_years": round((last - first).days / 365.25, 1),
    }


def fetch_quant_inputs(fred: Fred) -> dict:
    """
    Fetch QUANT_FRED_SERIES in the fetch_fred_data() entry shape.

    Returned separately so the caller merges it into the snapshot handed to
    `quant_context.build_quant_context` and nowhere else — the LLM payload is
    `json.dumps(fred_data)`, so adding a key to that dict adds it to the model's
    message. A failed series is logged and omitted; `assign_bucket` then falls
    back and the note still renders.
    """
    today_date = datetime.now(timezone.utc).date()
    data: dict = {}
    for name, series_id in QUANT_FRED_SERIES.items():
        try:
            observation_start = (today_date - timedelta(days=365 * 5)).isoformat()
            series = _fred_get_with_retry(fred, series_id, observation_start)
            time.sleep(_FRED_INTER_REQUEST_DELAY)
        except Exception as e:
            _log("FRED", "WARN", f"quant input {series_id} ({name}) unavailable: {_describe_fred_error(e)}")
            continue
        latest      = series.iloc[-1]
        prev        = series.iloc[-2] if len(series) > 1 else latest
        latest_date = series.index[-1].date()
        data[name] = {
            "value":        round(float(latest), 3),
            "prev":         round(float(prev), 3),
            "date":         latest_date.strftime("%Y-%m-%d"),
            "days_stale":   (today_date - latest_date).days,
            "frequency":    "daily",
            "five_yr_mean": round(float(series.mean()), 3),
            "vs_mean":      round(float(latest) - float(series.mean()), 3),
            **_mean_window(series),
        }
    _log("FRED", "OK" if len(data) == len(QUANT_FRED_SERIES) else "WARN",
         f"{len(data)}/{len(QUANT_FRED_SERIES)} quant-only series")
    return data


def fetch_fred_data(fred: Fred) -> dict:
    today_date = datetime.now(timezone.utc).date()
    data: dict = {}
    _raw_series: dict = {}   # raw Series retained for net-liquidity calculation
    _fetched, _failed, _stale_30d = 0, [], []

    for name, series_id in FRED_SERIES.items():
        try:
            observation_start = (datetime.now(timezone.utc).date() - timedelta(days=365 * 5)).isoformat()
            series = _fred_get_with_retry(fred, series_id, observation_start)
            time.sleep(_FRED_INTER_REQUEST_DELAY)
        except Exception as e:
            _log("FRED", "WARN", f"series {series_id} ({name}) unavailable: {_describe_fred_error(e)}")
            _failed.append(name)
            continue
        latest = series.iloc[-1]
        prev   = series.iloc[-2] if len(series) > 1 else latest
        latest_date = series.index[-1].date()
        data[name] = {
            "value":      round(float(latest), 3),
            "prev":       round(float(prev), 3),
            "date":       latest_date.strftime("%Y-%m-%d"),
            "days_stale": (today_date - latest_date).days,
            "frequency":  FRED_SERIES_FREQUENCY.get(name, "unknown"),
        }
        _fetched += 1
        if data[name]["days_stale"] > 30:
            _stale_30d.append(f"{name}({data[name]['days_stale']}d)")
        # Year-over-year for CPI and M2
        if name in ("cpi", "m2") and len(series) >= 13:
            year_ago = series.iloc[-13]
            data[name]["yoy_pct"] = round(((latest - year_ago) / year_ago) * 100, 2)
        # 5-year mean YoY for CPI and M2
        if name in ("cpi", "m2") and len(series) >= 25:
            yoy_series = series.pct_change(12).dropna() * 100
            if len(yoy_series) >= 12:
                data[name]["five_yr_mean_yoy"] = round(float(yoy_series.mean()), 2)
        # 5-year mean of raw value for spread/index/rate series
        # Note: philly_fed_mfg mean includes COVID-era extremes (~-56 in Apr 2020)
        # Note: jobless_claims' 5yr window excludes the 2020 COVID spike — post-crisis baseline
        # `hy_spread` is served on a rolling ~3y window by free FRED; `_mean_window` names it
        if name in ("hy_spread", "philly_fed_mfg", "real_yield_10y",
                    "breakeven_10y", "nfci", "jobless_claims") and len(series) >= 12:
            data[name]["five_yr_mean"] = round(float(series.mean()), 3)
            data[name]["vs_mean"]      = round(float(latest) - float(series.mean()), 3)
            data[name].update(_mean_window(series))
        # MoM point change for diffusion indices — absolute swing reveals regime shifts
        # that level-vs-mean comparisons miss (e.g. -0.4 looks mild; -27pt drop from +26.7 is a shock)
        if name == "philly_fed_mfg" and len(series) >= 2:
            data[name]["mom_change"] = round(float(latest) - float(prev), 1)
        # WoW % change for jobless claims (trend direction matters more than level)
        if name == "jobless_claims" and len(series) >= 2:
            wow = round(((float(latest) - float(prev)) / float(prev)) * 100, 2)
            data[name]["wow_pct"] = wow
            data[name]["trend"]   = "Rising" if wow > 0 else "Falling"
        # Retain raw series for net-liquidity components
        if name in _NET_LIQ_KEYS:
            _raw_series[name] = series

    _stale_str = f" | stale>30d: {', '.join(_stale_30d)}" if _stale_30d else ""
    _fail_str  = f" | missing: {', '.join(_failed)}"      if _failed    else ""
    _log("FRED", "WARN" if _failed else "OK",
         f"{_fetched}/{len(FRED_SERIES)} series{_fail_str}{_stale_str}")

    if "treasury_10y" in data and "treasury_2y" in data:
        data["yield_curve_spread"] = round(
            data["treasury_10y"]["value"] - data["treasury_2y"]["value"], 3
        )
    else:
        _log("FRED", "WARN", "yield_curve_spread skipped — treasury data incomplete")

    net_liq = _compute_net_liquidity(_raw_series)
    if net_liq:
        data["net_liquidity"] = net_liq

    return data


# ---------------------------------------------------------------------------
# Carrying a slow-moving critical series forward (todo #28)
# ---------------------------------------------------------------------------
#
# WHAT THIS FIXES. `validate_data` aborts when a `_CRITICAL_FRED` key is absent
# from the fetched dict, and absent meant *not fetched today* — the dict is
# built from scratch each run and nothing was carried forward. On 2026-09-22
# what went missing was `fed_funds_rate`: a MONTHLY series, dated month-start,
# whose value could not have changed between the 06:00 failure and the 12:48
# rerun that used it. The pipeline discarded a day's note over a number it
# already had, because it could not re-download it.
#
# So "critical" now means "the analysis is unsound without a value", not
# "without a freshly fetched one". Three decisions bound that (todo #28):
#
#   WHICH, AND FOR HOW LONG — monthly series only, seven days. `fed_funds_rate`
#   and `cpi` are monthly and month-dated; carrying one for a week cannot
#   invent a move it did not make. `treasury_10y` is daily and is NOT carryable
#   at any window: yesterday's 10Y published as today's is a different claim,
#   and the note would be asserting it.
#
#   HOW IT IS MARKED — `carried_forward` and `carried_from` sit beside the
#   existing `days_stale`, and ride into `results/quant_context_log/`. A scored
#   history that silently contains a stale number is the [KB-029] failure in a
#   new costume: correct-looking readings nobody can later tell apart from real
#   ones. There is no look-ahead risk — a carried value is strictly
#   backward-looking, so `test_point_in_time.py` is unaffected.
#
#   WHETHER THE SCORER MAY READ A CARRIED DAY — not decided here, deliberately.
#   Phase 22's bar is sealed with its first honest read ~2027-05, and changing
#   what the scorer reads mid-flight is the convention #7 hazard. The flag is
#   recorded so the question can be answered at the read, with data.
#
# A carried entry is never written back into a snapshot, so a carry cannot
# chain: the window is always measured against a value that was really fetched.

FRED_SNAPSHOT_DIR = REPO_ROOT / "results" / "fred_snapshot"

CARRYABLE_FREQUENCIES = frozenset({"monthly"})
CARRY_MAX_DAYS = 7


def write_fred_snapshot(data: dict, asof, directory=None) -> "Path | None":
    """Persist the day's freshly-fetched FRED entries so a later run can carry
    one forward. Entries that were themselves carried are excluded — the point
    of the window is that it is measured from a real observation.

    Best-effort: a snapshot that cannot be written is a warning, never the
    day's note. Returns the path written, or None.
    """
    fresh = {
        name: entry for name, entry in data.items()
        if isinstance(entry, dict) and not entry.get("carried_forward")
    }
    if not fresh:
        return None
    directory = Path(directory) if directory is not None else FRED_SNAPSHOT_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{asof.isoformat()}.json"
        path.write_text(json.dumps({"asof": asof.isoformat(), "series": fresh},
                                   indent=1, sort_keys=True), encoding="utf-8")
        return path
    except Exception as exc:   # noqa: BLE001 — never cost the note a snapshot
        _log("FRED", "WARN", f"snapshot not written: {type(exc).__name__}: {exc}")
        return None


def _snapshots_newest_first(directory, asof) -> list:
    """(date, payload) for every snapshot on or before `asof` and inside the
    carry window, newest first."""
    directory = Path(directory) if directory is not None else FRED_SNAPSHOT_DIR
    if not directory.is_dir():
        return []
    out = []
    for path in directory.glob("*.json"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        age = (asof - day).days
        if not 0 <= age <= CARRY_MAX_DAYS:
            continue
        try:
            out.append((day, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:   # noqa: BLE001 — a corrupt snapshot is not an outage
            continue
    return sorted(out, key=lambda pair: pair[0], reverse=True)


def carry_forward(data: dict, names, asof, directory=None) -> list[str]:
    """Fill any of `names` missing from `data` from the most recent snapshot
    inside the carry window. Mutates `data`; returns the names carried.

    A series is only eligible if the snapshot recorded it as one of
    `CARRYABLE_FREQUENCIES` — the frequency comes from the snapshot rather than
    from `FRED_SERIES_FREQUENCY` so that reclassifying a series later cannot
    retroactively license a carry that was never allowed when it was written.
    """
    missing = [n for n in names if n not in data]
    if not missing:
        return []
    carried: list[str] = []
    for day, payload in _snapshots_newest_first(directory, asof):
        for name in list(missing):
            entry = (payload.get("series") or {}).get(name)
            if not isinstance(entry, dict):
                continue
            if entry.get("frequency") not in CARRYABLE_FREQUENCIES:
                continue
            entry = dict(entry)
            entry["carried_forward"] = True
            entry["carried_from"] = day.isoformat()
            observed = entry.get("date")
            if observed:
                try:
                    entry["days_stale"] = (asof - date.fromisoformat(observed)).days
                except ValueError:
                    pass
            data[name] = entry
            carried.append(name)
            missing.remove(name)
            _log("FRED", "WARN",
                 f"{name} unavailable today — carried forward from {day.isoformat()} "
                 f"(observed {observed}, {entry.get('days_stale')}d stale); "
                 f"marked carried_forward")
        if not missing:
            break
    return carried
