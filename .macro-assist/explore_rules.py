"""
explore_rules.py — EXPLORE-TIER mechanical rules on the pre-seal slice (ADR-0023, ADR-0025, ADR-0026).

Research harness (product_surface: RESEARCH). Never touches the published table,
the quant log, or `pipeline.yml`. It walks a risk-rule member — an equity
exposure decided each day — over the history before the seal, and reads it
through `class_bars.read(sealed=False)`, which can only return `exploratory`:
the code, not this docstring, keeps a look from becoming a claim (How we
explore §1). What it saw goes to the hypothesis register, never the KB.

The slice
---------
Every input is cut at `numeric_baseline.SEAL_START` (2018-01-01) the moment it
is fetched, before anything is computed from it, so no number here can depend
on a sealed day. The slice starts on the first day the member's flag can be
read: the Fama-French panel begins in July 1926, the channels need their
covariance windows, and each channel's threshold needs `_MIN_WARMUP` prior
readings on the strided grid — the early 1930s.

The member: H-009, `h009_panel_or_half`
---------------------------------------
Exactly as the register entry fixes it, before any look:

    flag      `panel_or` — the absorption ratio (covariance window 120) OR
              turbulence (252, shrinkage 0.2, 5-day smoothing) on the
              Fama-French 30-industry value-weighted daily panel, each at or
              above the 90th percentile of its own readings strictly before
              the day, on the 5-day strided grid, ≥ 252 prior readings.
              `fragility_or.py`'s constants, unchanged, and
              `input_testing._panel_ar_turb`'s walk — the path KB-016/017/020
              validated. The composite is left out (it has no history before
              2008 and was tuned on 2008–2026). A reading exists on grid days
              only, as in the validated protocol.
    legs      equity: the Fama-French market's total return (Mkt−RF + RF);
              cash: RF.
    rule      e_t = 0.5 if the flag fired on any day in [t − 19, t], else 1.0;
              decided at the close of t, traded at the close of t + 1 (the
              class bar applies that lag).
    clause    `caught_split` on the flag, a firing up to 19 trading days
              before an episode's peak counting as caught — the hold window
              less a day (resolved.md #35).

The class bar builds the rivals (`static_matched`, `vol_matched`) and
buy-and-hold from the same path; the harness hands it the member's exposure and
the flag, nothing it could tune.

Also reported, never read (the entry's second prediction): the member's return
behind `static_matched`, split by day — inside a hold window that a 5% drop
followed within 20 days, inside one that none followed (a false alarm), and
fully invested.

The member: H-010, `h010_panel_or_double` (`--member h010`, ADR-0025)
--------------------------------------------------------------------
A contribution rule, read by the `flow_rule` class bar on the same inputs:

    flag      `panel_or`, exactly as H-009's.
    rule      at each month-end, 1 contribution enters a cash reserve (RF);
              the multiple is 2.0 if the flag fired on any of the 20 trading
              days to the month-end, else 0.75; the class bar buys
              min(multiple, reserve) at the next close and never sells.
    clause    `forward_contrast` on the flag over the same 20 days: the median
              12-month forward return from flagged month-ends above the median
              from unflagged month-ends as deep in drawdown as `dip_matched`'s
              threshold.

The class bar builds `plain` and `dip_matched` from the same path. Its report
and summary go to `report_h010.md` / `summary_h010.json`, beside H-009's.

The member: H-011, `h011_fill_gaps` (`--member h011`, ADR-0026)
---------------------------------------------------------------
An allocation rule for new money, read by the `mix_rule` class bar on its own
monthly inputs, in euros, 1973-01 → 2017-12:

    holdings  equity 70% — the Fama-French US market (Mkt−RF + RF), daily
              returns compounded within each month, converted to euros;
              bonds 20% — a constant-maturity 10-year Bund, total return
              rebuilt from the OECD yield (FRED IRLTLT01DEM156N); gold 10% —
              the World Bank's monthly price (the datasets/gold-prices
              mirror), converted to euros. Dollars per euro: the Deutsche
              Mark rate (EXGEUS) at its fixed conversion before 1999, the
              euro's (EXUSEU) from 1999. Monthly averages for the yield, the
              rates and gold; month-end compounding for equity.
    rule      at each month-end, the contribution of 1 is split across the
              holdings below their target value after it, in proportion to
              each gap; nothing is sold or held back.
    clause    `late_control`: the median control ratio over each plan's
              months 61–120 at most 0.75.

The inputs are fetched in CI (`explore_rules.yml`, which holds FRED's key);
`check_mix_inputs` checks coverage, ranges and the two dollar rates before any
leg is walked. Report and summary: `report_h011.md` / `summary_h011.json`.

Run
---
    python explore_rules.py --dry-run     # fetch, build the flag, print the slice; reads no rule
    python explore_rules.py               # the look: fetch, walk, read, report — COUNTED
    python explore_rules.py --cached      # the same on the cached inputs
    python explore_rules.py --member h010 --dry-run   # H-010: the slice, the month-ends; reads no rule
    python explore_rules.py --member h010 --cached    # H-010's look — COUNTED
    python explore_rules.py --member h011 --dry-run   # H-011: fetch, check the data, the plans; walks no leg
    python explore_rules.py --member h011             # H-011's look — COUNTED (in CI: explore_rules.yml)

Writes `results/explore_rules/{report.md, summary.json}`, caches the fetched
inputs there (`inputs.pkl`), and appends one receipt to `runs.jsonl` per look
(ADR-0022, WP-25.B), which `record_audit.py` reads from the output branch: a
dated look in a register entry with no logged run behind it is red. A dry run
writes no receipt — it reads no rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import class_bars as cb
from fragility_or import _COV_AR, _COV_TURB, _MIN_WARMUP, _Q, _SHRINK, _SMOOTH, _STRIDE
from input_testing import (
    _DEFAULT_CACHE, _KF_BASE, _download_zip_text, _panel_ar_turb, _parse_ff_block,
    fetch_ff_industries, returns_to_histories,
)
from numeric_baseline import SEAL_START

_HERE = Path(__file__).resolve().parent
RESULTS_DIR = _HERE.parent / "results" / "explore_rules"
RUN_LOG = "runs.jsonl"

ARM = "h009_panel_or_half"
SIGNAL = "panel_or"
CUT, HOLD = 0.5, 20                 # half out, for 20 trading days after any firing
CHANNELS = ("AR", "TURB")
ALARM_DROP, ALARM_HORIZON = 0.05, 20   # a hold window a 5% drop followed within 20 days

# The member's pre-registration as this harness reads it. The entry's own
# `Pre-registration` field, written after this first look, must state it.
SPEC = cb.validate({"class": "risk_rule", "arm": ARM,
                    "clauses": [{"kind": "caught_split", "signal": SIGNAL,
                                 "before_peak": HOLD - 1}]})      # resolved.md #35


# H-010 (ADR-0025): the multiple of the month's contribution, fixed before any look
ARM_H010 = "h010_panel_or_double"
LOW, HIGH, WINDOW = 0.75, 2.0, 20
FORWARD_MONTHS = 12
SPEC_H010 = cb.validate({"class": "flow_rule", "arm": ARM_H010,
                         "clauses": [{"kind": "forward_contrast", "signal": SIGNAL,
                                      "window": WINDOW, "months": FORWARD_MONTHS}]})

# H-011 (ADR-0026): where each month's contribution goes, fixed before any look
# but for one change made at build, before any data: the whole contribution to
# the one holding furthest below target read `no_control` on synthetic markets
# from its lumpiness alone, so the owner chose to fill every gap instead
# (resolved.md #38).
ARM_H011 = "h011_fill_gaps"
MIX_TARGETS = {"equity": 0.70, "bonds": 0.20, "gold": 0.10}
MIX_EQUITY = "equity"
LATE_FROM, LATE_MAX = cb.MIX_RULE.plan_months // 2 + 1, 0.75
SPEC_H011 = cb.validate({"class": "mix_rule", "arm": ARM_H011,
                         "clauses": [{"kind": "late_control", "from_month": LATE_FROM,
                                      "max_ratio": LATE_MAX}]})
MIX_FIRST, MIX_START = "1973-01", "1972-12"     # gold floats from the early 1970s; the first plan starts 1973
FRED_SERIES = {"bund_10y": "IRLTLT01DEM156N",  # OECD long-term rate, Germany, % a year, monthly
               "dem_per_usd": "EXGEUS",         # monthly average, to 2001
               "usd_per_eur": "EXUSEU"}         # monthly average, from 1999
GOLD_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"  # World Bank Pink Sheet from 1960
DEM_PER_EUR = 1.95583                           # the fixed conversion rate, 1999-01-01
EURO_START = "1999-01"
BOND_MONTHS = 120                               # a constant-maturity 10-year bond

MEMBERS = ("h009", "h010", "h011")
_OUT = {"h009": ("report.md", "summary.json"), "h010": ("report_h010.md", "summary_h010.json"),
        "h011": ("report_h011.md", "summary_h011.json")}


# ---------------------------------------------------------------------------
# the inputs, cut at the seal on arrival
# ---------------------------------------------------------------------------

def before_seal(obj, seal: date = SEAL_START):
    """Rows strictly before the seal."""
    return obj[obj.index < pd.Timestamp(seal)]


def fetch_ff_factors(cache_dir: str = _DEFAULT_CACHE) -> pd.DataFrame:
    """The Fama-French daily factors (decimal): Mkt-RF, SMB, HML, RF."""
    text = _download_zip_text(f"{_KF_BASE}F-F_Research_Data_Factors_daily_CSV.zip", cache_dir)
    return _parse_ff_block(text, r"^\s*,Mkt-RF")


def fetch_inputs() -> dict:
    industries = before_seal(fetch_ff_industries(30, "vw"))
    factors = before_seal(fetch_ff_factors())
    return {"industries": industries, "factors": factors,
            "fetched": datetime.now().astimezone().isoformat(timespec="seconds")}


# ---------------------------------------------------------------------------
# the flag
# ---------------------------------------------------------------------------

def panel_channels(industries: pd.DataFrame) -> dict[str, pd.Series]:
    """AR and turbulence on the strided grid — `fragility_or`'s constants,
    `input_testing._panel_ar_turb`'s walk."""
    AR, TURB = _panel_ar_turb(returns_to_histories(industries), industries.index,
                              cov_ar=_COV_AR, cov_turb=_COV_TURB, shrink=_SHRINK,
                              smooth=_SMOOTH, stride=_STRIDE)
    return {"AR": AR, "TURB": TURB}


def pit_or(channels: dict[str, pd.Series], q: float = _Q, min_warmup: int = _MIN_WARMUP) -> pd.Series:
    """The OR flag on the channels' common grid: each channel at or above the
    q-quantile of its own readings strictly before the day, once each has
    `min_warmup` of them — `fragility_or._pit_backtest`'s rule, less the
    composite. Days before the warm-up are dropped, not read as quiet."""
    common = channels[CHANNELS[0]].index
    for k in CHANNELS[1:]:
        common = common.intersection(channels[k].index)
    arrs = {k: channels[k].reindex(common).to_numpy(dtype=float) for k in CHANNELS}
    keep, fired = [], []
    for i in range(len(common)):
        fires = []
        for k in CHANNELS:
            past = arrs[k][:i]
            past = past[np.isfinite(past)]
            if len(past) < min_warmup:
                break
            fires.append(bool(np.isfinite(arrs[k][i]) and arrs[k][i] >= np.quantile(past, q)))
        else:
            keep.append(common[i])
            fired.append(any(fires))
    return pd.Series(fired, index=pd.DatetimeIndex(keep), dtype=bool)


def hold_exposure(fired_daily: np.ndarray, cut: float = CUT, hold: int = HOLD) -> np.ndarray:
    """e_t = `cut` if the flag fired on any of the last `hold` days to t, else 1."""
    f = np.asarray(fired_daily, bool).astype(float)
    recent = np.convolve(f, np.ones(hold), "full")[:len(f)] > 0
    return np.where(recent, cut, 1.0)


def build_path(inputs: dict, flag: pd.Series) -> dict:
    """The member on the daily calendar, from the flag's first readable day to
    the last day before the seal."""
    fac = inputs["factors"]
    days = fac.index[(fac.index >= flag.index[0]) & (fac.index < pd.Timestamp(SEAL_START))]
    fired = flag.reindex(days, fill_value=False).to_numpy(dtype=bool)   # grid days only
    fac = fac.loc[days]
    return {"dates": [d.date().isoformat() for d in days],
            "equity": (fac["Mkt-RF"] + fac["RF"]).to_numpy(dtype=float),
            "cash": fac["RF"].to_numpy(dtype=float),
            "exposure": hold_exposure(fired),
            "signals": {SIGNAL: fired}}


def contribution_multiple(fired_daily: np.ndarray, low: float = LOW, high: float = HIGH,
                          window: int = WINDOW) -> np.ndarray:
    """m_t = `high` if the flag fired on any of the last `window` days to t,
    else `low`. The class bar reads it at month-ends only."""
    f = np.asarray(fired_daily, bool).astype(float)
    recent = np.convolve(f, np.ones(window), "full")[:len(f)] > 0
    return np.where(recent, high, low)


def build_flow_path(inputs: dict, flag: pd.Series) -> dict:
    """H-010 on the daily calendar, from the flag's first readable day to the
    last day before the seal. The seal falls on a month boundary, so the last
    month on this side is complete."""
    path = build_path(inputs, flag)
    fired = path["signals"][SIGNAL]
    return {"dates": path["dates"], "equity": path["equity"], "cash": path["cash"],
            "multiple": contribution_multiple(fired), "signals": {SIGNAL: fired},
            "last_month_complete": SEAL_START.day == 1}


# ---------------------------------------------------------------------------
# the read, and what it only reports
# ---------------------------------------------------------------------------

def alarm_split(path: dict, cost_bps: float = cb.RISK_RULE.cost_bps[0]) -> dict:
    """The member's daily return behind `static_matched`, summed (as annual
    percentage points) over days in a hold window a 5% buy-and-hold drop
    followed within 20 days of its start, days in one none followed, and
    fully invested days."""
    legs = cb.risk_legs(cb.RISK_RULE, path, cost_bps)
    ret = {k: np.diff(np.r_[1.0, legs[k]["value"]]) / np.r_[1.0, legs[k]["value"][:-1]]
           for k in ("member", "static_matched")}
    gap = ret["member"] - ret["static_matched"]
    e, level = np.asarray(path["exposure"]), np.cumprod(1.0 + np.asarray(path["equity"]))
    cls = np.full(len(e), "invested", dtype=object)
    runs = np.flatnonzero(np.diff(np.r_[False, e < 1.0, False].astype(int)))
    n_true = n_false = 0
    for a, b in zip(runs[::2], runs[1::2]):
        ahead = level[a:min(a + ALARM_HORIZON + 1, len(level))]
        hit = bool(np.any(1.0 - ahead / np.maximum.accumulate(ahead) >= ALARM_DROP))
        cls[a + 2:min(b + 2, len(e))] = "followed" if hit else "false_alarm"   # held two days after decided
        n_true, n_false = n_true + hit, n_false + (not hit)
    years = cb._years(path["dates"])
    return {"n_windows_followed": n_true, "n_windows_false_alarm": n_false,
            "pp_per_year": {k: round(100 * float(gap[cls == k].sum()) / years, 3)
                            for k in ("followed", "false_alarm", "invested")}}


def look(inputs: dict) -> tuple[dict, dict]:
    flag = pit_or(panel_channels(inputs["industries"]))
    path = build_path(inputs, flag)
    result = cb.read(path, SPEC, sealed=False)
    result["alarm_split"] = alarm_split(path)
    result["flag"] = {"first_reading": flag.index[0].date().isoformat(), "n_readings": int(len(flag)),
                      "share_fired": round(float(flag.mean()), 4)}
    return result, path


def look_h010(inputs: dict) -> tuple[dict, dict]:
    flag = pit_or(panel_channels(inputs["industries"]))
    path = build_flow_path(inputs, flag)
    result = cb.read(path, SPEC_H010, sealed=False)
    result["flag"] = {"first_reading": flag.index[0].date().isoformat(), "n_readings": int(len(flag)),
                      "share_fired": round(float(flag.mean()), 4)}
    return result, path


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def render(result: dict) -> str:
    s, bar = result["summary"], cb.RISK_RULE
    lines = [f"# Explore look — {ARM} (H-009)", "",
             f"Verdict: **{result['verdict']}** — {result['reason']}. Explore slice "
             f"{s['first_date']} → {s['last_date']} (< `SEAL_START` {SEAL_START}), {s['n_days']} days; "
             f"the flag's first reading {result['flag']['first_reading']}, fired on "
             f"{_pct(result['flag']['share_fired'])} of {result['flag']['n_readings']} grid readings. "
             f"Member mean exposure {s['mean_exposure']}.", "",
             "## What the bar would read", ""]
    if s["n_episodes"]:
        sv, sav = s["saving_vs_vol"], s["saving"]
        lines += [f"- Episodes (buy-and-hold drops ≥ {bar.episode_depth:.0%}): **{s['n_episodes']}**",
                  f"- Mean share of each drop taken, member: **{s['mean_r']}**",
                  f"- Saving vs `{bar.rival}`: **{sav['mean']:+.4f}** "
                  f"[{sav['ci']['lo']:+.4f}, {sav['ci']['hi']:+.4f}] ({bar.interval:.0%}); bar ≥ {bar.min_saving}",
                  f"- Saving vs `{bar.second_rival}`: **{sv['mean']:+.4f}**, better in "
                  f"{_pct(sv['share_better'])} of episodes; bar > 0 in ≥ {_pct(bar.vol_majority)}",
                  "- Net annual return, member minus `static_matched` (negative = behind): "
                  + ", ".join(f"{float(c) * 100:+.2f} pp at {float(k):g} bps" for k, c in s["shortfall"].items())
                  + f"; budget: no more than {bar.max_shortfall * 100:.1f} pp behind"]
    else:
        lines += ["- No episode on this slice."]
    for c in result["clauses"]:
        lines.append(f"- Clause `{c['kind']}`: {'held' if c['passed'] else 'failed'} — {c['detail']}")
    a = result["alarm_split"]
    lines += ["", "## Reported, never read", "",
              f"Return, member minus `static_matched`, by day (pp a year, 10 bps; negative = behind): in the {a['n_windows_followed']} hold "
              f"windows a 5% drop followed, {a['pp_per_year']['followed']:+.2f}; in the "
              f"{a['n_windows_false_alarm']} false alarms, {a['pp_per_year']['false_alarm']:+.2f}; fully "
              f"invested, {a['pp_per_year']['invested']:+.2f}.", ""]
    for c, legs in s["legs"].items():
        lines += [f"### Legs at {float(c):g} bps", "",
                  "| leg | worst drop | return / yr | vol / yr | time reduced | trades / yr | "
                  "turnover / yr | gain realized / yr | tax brought forward / yr |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for k, v in legs.items():
            lines.append(f"| {k} | {_pct(v['worst_drop'])} | {_pct(v['annual_return'])} | {_pct(v['annual_vol'])} | "
                         f"{_pct(v['time_reduced'])} | {v['trades_per_year']} | {v['turnover_per_year']} | "
                         f"{_pct(v['realized_gain_per_year'])} | {_pct(v['tax_brought_forward_per_year'])} |")
        lines.append("")
    lines += ["## Episodes", "", "| peak | trough | depth | member | static | vol | caught |", "|---|---|---|---|---|---|---|"]
    for e in s["episodes"]:
        lines.append(f"| {e['peak']} | {e['trough']}{' (open)' if e['open'] else ''} | {_pct(e['depth'])} | "
                     f"{e['r_member']} | {e['r_static_matched']} | {e['r_vol_matched']} | {e.get('caught', '—')} |")
    lines += ["", "Tax brought forward: realized gain on an average cost basis × "
                  f"{bar.tax_rate:.2%}, as a share of the portfolio at the year's start; the yearly allowance "
                  "is left out. An explore look is not a result: it goes to the register, never the KB.", ""]
    return "\n".join(lines)


def _pp(x) -> str:
    return "—" if x is None else f"{100 * x:+.2f} pp"


def render_h010(result: dict) -> str:
    s, bar = result["summary"], cb.FLOW_RULE
    adv, ci = s["advantage"], s["advantage_ci"]
    lines = [f"# Explore look — {ARM_H010} (H-010)", "",
             f"Verdict: **{result['verdict']}** — {result['reason']}. Explore slice "
             f"{s['first_date']} → {s['last_date']} (< `SEAL_START` {SEAL_START}), {s['n_contributions']} "
             f"monthly contributions; the flag's first reading {result['flag']['first_reading']}, fired on "
             f"{_pct(result['flag']['share_fired'])} of {result['flag']['n_readings']} grid readings. "
             f"The member names {HIGH} in {_pct(s['share_high'])} of month-ends, {LOW} in the rest.", "",
             "## What the bar would read", "",
             f"- Drops of {bar.episode_depth:.0%} or more: **{s['n_episodes']}** (floor {bar.min_episodes})",
             "- Advantage over `plain`, money-weighted return a year: "
             + ", ".join(f"**{_pp(v)}** at {float(k):g} bps" for k, v in adv.items())
             + f"; {ci['level']:.0%} interval ({ci['block_months']}-month blocks) "
               f"[{_pp(ci['lo'])}, {_pp(ci['hi'])}]; bar ≥ {bar.min_advantage * 100:.2f} pp, interval clear of zero",
             f"- Advantage over `dip_matched` (high when the market is at least "
             f"{_pct(s['dip_threshold'])} below its peak): **{_pp(s['advantage_vs_dip'])}**; bar > 0"]
    for c in result["clauses"]:
        lines.append(f"- Clause `{c['kind']}`: {'held' if c['passed'] else 'failed'} — {c['detail']}")
    sp, rs = s["advantage_split"], s["reserve"]
    lines += ["", "## Reported, never read", "",
              f"- Reserve, in months of contributions: mean {rs['mean']}, largest {rs['max']}, at the end {rs['end']}.",
              f"- Starved: in {_pct(s['starved_share_of_high_months'])} of its high months the member wanted more "
              "than its reserve held.",
              f"- Where the advantage over `plain` sits, as a share of `plain`'s final wealth: purchases inside "
              f"drops {sp['in_drops']:+.4f}, outside {sp['outside_drops']:+.4f}, the reserve left at the end "
              f"{sp['reserve_left']:+.4f}."]
    if s.get("halves"):
        lines.append("- Each half, started fresh: " + "; ".join(
            f"{h['first_date']} → {h['last_date']} {_pp(h['advantage'])}" for h in s["halves"]) + ".")
    lines += ["", "| leg | " + " | ".join(f"return / yr at {float(c):g} bps | wealth per contribution"
                                         for c in s["legs"]) + " |",
              "|---|" + "---|---|" * len(s["legs"])]
    for k in cb.FLOW_LEGS:
        lines.append(f"| {k} | " + " | ".join(
            f"{_pct(s['legs'][c][k]['money_weighted_return'])} | {s['legs'][c][k]['wealth_per_contribution']}"
            for c in s["legs"]) + " |")
    lines += ["", "## Drops", "", "| peak | trough | depth |", "|---|---|---|"]
    lines += [f"| {e['peak']} | {e['trough']} | {_pct(e['depth'])} |" for e in s["episodes"]]
    lines += ["", "No leg sells, so no tax is brought forward; taxes are outside the bar (ADR-0025 §4). "
                  "An explore look is not a result: it goes to the register, never the KB.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# H-011: three holdings in euros, monthly (ADR-0026)
# ---------------------------------------------------------------------------

def _month_index(idx) -> pd.DatetimeIndex:
    """Any monthly date index as the first day of its month."""
    return pd.DatetimeIndex(pd.to_datetime(idx)).to_period("M").to_timestamp()


def _fred_series(series_id: str) -> pd.Series:
    """A FRED series: through the API when `FRED_API_KEY` is set (CI), else
    the public CSV."""
    import os
    key = os.environ.get("FRED_API_KEY")
    if key:
        from fredapi import Fred
        s = Fred(api_key=key).get_series(series_id)
    else:
        df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
        s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(),
                      index=pd.to_datetime(df.iloc[:, 0]))
    s = s.dropna()
    s.index = _month_index(s.index)
    return s.astype(float)


def fetch_mix_raw() -> dict:
    """The raw series, uncut: the Fama-French daily factors, the Bund yield and
    the two dollar rates from FRED, and the World Bank's monthly gold price.
    Only two callers: `fetch_mix_inputs`, which cuts at the seal on arrival,
    and the sealed runner's fetch, in `sealed_read.yml`'s key job."""
    gold = pd.read_csv(GOLD_URL)
    g = pd.Series(pd.to_numeric(gold.iloc[:, 1], errors="coerce").to_numpy(),
                  index=_month_index(gold.iloc[:, 0])).dropna()
    return {"factors": fetch_ff_factors(), "gold_usd": g,
            **{k: _fred_series(v) for k, v in FRED_SERIES.items()},
            "fetched": datetime.now().astimezone().isoformat(timespec="seconds")}


def fetch_mix_inputs() -> dict:
    """The raw series, each cut at the seal on arrival."""
    raw = fetch_mix_raw()
    return {k: (v if k == "fetched" else before_seal(v)) for k, v in raw.items()}


def usd_per_eur(inputs: dict) -> pd.Series:
    """Dollars per euro, monthly: through the Deutsche Mark at its fixed
    conversion rate before the euro, the euro's own rate from 1999."""
    dem = DEM_PER_EUR / inputs["dem_per_usd"]
    eur = inputs["usd_per_eur"]
    cut = pd.Timestamp(EURO_START + "-01")
    return pd.concat([dem[dem.index < cut], eur[eur.index >= cut]]).sort_index()


def bond_return(y0, y1, months: int = BOND_MONTHS):
    """One month's total return of a par bond bought at yield `y0` (decimal a
    year) with `months` months to run, monthly coupons, sold a month later at
    yield `y1`: the coupon plus the price change."""
    y0, y1 = np.asarray(y0, float), np.asarray(y1, float)
    c, n, r = y0 / 12.0, months - 1, y1 / 12.0
    disc = (1.0 + r) ** -n
    annuity = np.where(np.abs(r) > 1e-12, (1.0 - disc) / np.where(np.abs(r) > 1e-12, r, 1.0), n)
    return c * annuity + disc - 1.0 + c


def last_complete_month(inputs: dict) -> pd.Timestamp:
    """The last month every series has whole: a monthly series' last value,
    and for the daily factors the last month whose final business day they
    reach. The sealed side runs to it, as ADR-0026 fixes ("the last complete
    month with data at read time")."""
    fac = inputs["factors"].index
    last_day = fac.max()
    eq_last = last_day.to_period("M").to_timestamp()
    if last_day < eq_last + pd.offsets.BMonthEnd(0) - pd.Timedelta(days=3):
        eq_last -= pd.offsets.MonthBegin(1)
    monthly = [inputs[k].index.max() for k in ("gold_usd", "bund_10y", "usd_per_eur")]
    return min([eq_last, *monthly])


def mix_levels(inputs: dict, start: str = MIX_START, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Month-end-to-month-end levels of the three holdings in euros, from
    `start` (MIX_START: the explore side) to `end` (default: the last month
    before the seal). Equity compounds the daily market return within each
    month; bonds rebuild a 10-year Bund's total return from its yield; dollar
    assets are converted at the month's rate."""
    fac = inputs["factors"]
    eq_usd = (1.0 + fac["Mkt-RF"] + fac["RF"]).groupby(fac.index.to_period("M")).prod()
    eq_usd.index = eq_usd.index.to_timestamp()
    fx = usd_per_eur(inputs)
    y = inputs["bund_10y"] / 100.0
    end = pd.Timestamp(SEAL_START) - pd.offsets.MonthBegin(1) if end is None else end
    months = pd.date_range(start + "-01", end, freq="MS")
    need = {"equity": eq_usd, "fx": fx, "bund": y, "gold": inputs["gold_usd"]}
    missing = {k: [m.strftime("%Y-%m") for m in months if m not in v.index] for k, v in need.items()}
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        raise ValueError(f"monthly series incomplete on {start} → {months[-1]:%Y-%m}: "
                         + "; ".join(f"{k} lacks {v[:3]}{'…' if len(v) > 3 else ''}" for k, v in missing.items()))
    eq_usd, fx, y, gold = (v.reindex(months) for v in (eq_usd, fx, y, inputs["gold_usd"]))
    usd_lvl = eq_usd.cumprod() / eq_usd.iloc[0]          # the first month's own return is not used
    bond = np.r_[1.0, np.cumprod(1.0 + bond_return(y.to_numpy()[:-1], y.to_numpy()[1:]))]
    return pd.DataFrame({"equity": (usd_lvl / fx).to_numpy(), "bonds": bond,
                         "gold": (gold / fx).to_numpy()}, index=months)


def check_mix_inputs(inputs: dict, start: str = MIX_START, end: pd.Timestamp | None = None) -> dict:
    """The data errand's checks, before any leg is walked: coverage, ranges,
    and the Deutsche Mark and euro rates agreeing where both exist. Reads no
    return of any holding."""
    lv = mix_levels(inputs, start, end)
    y = inputs["bund_10y"]
    both = inputs["dem_per_usd"].index.intersection(inputs["usd_per_eur"].index)
    implied = DEM_PER_EUR / inputs["dem_per_usd"].reindex(both)
    gap = float((implied / inputs["usd_per_eur"].reindex(both) - 1.0).abs().max()) if len(both) else None
    problems = []
    if not (-0.02 < y.min() / 100 and y.max() / 100 < 0.15):
        problems.append(f"Bund yield outside −2% … 15%: {y.min():.2f} … {y.max():.2f}")
    if (inputs["gold_usd"] <= 0).any() or (inputs["dem_per_usd"] <= 0).any() or (inputs["usd_per_eur"] <= 0).any():
        problems.append("a price or rate at or below zero")
    spliced = start < EURO_START          # the Deutsche Mark rate is used only before the euro
    if spliced and (gap is None or gap > 0.01):
        problems.append(f"the Deutsche Mark and euro rates disagree by {gap} where both exist (1999–2001)")
    if problems:
        raise ValueError("; ".join(problems))
    return {"first_month": lv.index[1].strftime("%Y-%m"), "last_month": lv.index[-1].strftime("%Y-%m"),
            "n_months": len(lv) - 1, "dem_euro_overlap_months": len(both),
            "dem_euro_largest_gap": round(gap, 5) if gap is not None else None}


def fill_gaps(values: np.ndarray, targets: np.ndarray, month=None) -> np.ndarray:
    """H-011: the month's contribution split across the holdings below their
    target value after it, in proportion to each one's gap. The gaps after a
    contribution of 1 always sum to at least 1, so some holding is always
    below target."""
    V = np.asarray(values, float)
    tot = V.sum(axis=1, keepdims=True) + 1.0
    gap = np.maximum(targets * tot - V, 0.0)
    return gap / gap.sum(axis=1, keepdims=True)


MIX_ARMS = {ARM_H011: fill_gaps}           # what the sealed runner may walk under `mix_rule`


def build_mix_path(inputs: dict, start: str = MIX_START, end: pd.Timestamp | None = None,
                   arm: str = ARM_H011) -> dict:
    lv = mix_levels(inputs, start, end)
    ret = lv.pct_change().iloc[1:]
    return {"months": [m.strftime("%Y-%m") for m in ret.index],
            "returns": {k: ret[k].to_numpy() for k in MIX_TARGETS},
            "targets": dict(MIX_TARGETS), "equity": MIX_EQUITY, "allocate": MIX_ARMS[arm]}


SEALED_LEVEL_MONTH = (pd.Timestamp(SEAL_START) - pd.offsets.MonthBegin(1)).strftime("%Y-%m")


def sealed_mix_inputs(raw: dict) -> dict:
    """The sealed side's inputs: every series from the month-end before the
    seal (its level, never its return) on. Only the sealed runner calls this."""
    cut = pd.Timestamp(SEALED_LEVEL_MONTH + "-01")
    return {k: (v if k == "fetched" else v[v.index >= cut]) for k, v in raw.items()}


def sealed_mix_path(raw: dict, arm: str = ARM_H011) -> tuple[dict, dict]:
    """(the path, its checks) for the sealed read: 2018-01 to the last complete
    month, in euros, the same build as the explore side's."""
    inputs = sealed_mix_inputs(raw)
    end = last_complete_month(inputs)
    check = check_mix_inputs(inputs, SEALED_LEVEL_MONTH, end)
    return build_mix_path(inputs, SEALED_LEVEL_MONTH, end, arm), check


def look_h011(inputs: dict) -> tuple[dict, dict]:
    check = check_mix_inputs(inputs)
    path = build_mix_path(inputs)
    result = cb.read(path, SPEC_H011, sealed=False)
    result["inputs"] = check
    return result, path


def render_h011(result: dict) -> str:
    s, bar = result["summary"], cb.MIX_RULE
    mix = ", ".join(f"{a} {w:.0%}" for a, w in zip(s["assets"], s["targets"]))
    ci, sci = s["control_ratio_ci"], s["shortfall_ci"]
    lines = [f"# Explore look — {ARM_H011} (H-011)", "",
             f"Verdict: **{result['verdict']}** — {result['reason']}. Explore slice {s['first_month']} → "
             f"{s['last_month']} (< `SEAL_START` {SEAL_START}), {s['n_plans']} plans of {s['plan_months']} months, "
             f"one starting each January. Target mix: {mix}. In euros; proxies: the US market for world "
             "equities, a constant-maturity 10-year Bund rebuilt from its yield for euro government bonds, the "
             "World Bank's monthly gold price.", "",
             "## What the bar would read", "",
             f"- Equity drops of {bar.episode_depth:.0%} or more: **{s['n_episodes']}** (floor {bar.min_episodes})",
             f"- Control ratio (member's mean drift ÷ `plain`'s): **{s['control_ratio']:.3f}**, "
             f"{ci['level']:.0%} interval ({ci['block_months']}-month blocks) [{ci['lo']:.3f}, {ci['hi']:.3f}]; "
             f"bar ≤ {bar.max_ratio}, interval below 1. Mean drift: "
             + ", ".join(f"{k} {_pct(v)}" for k, v in s["mean_drift"].items()),
             "- Shortfall against `exposure_matched` (equity share "
             f"{_pct(s['matched_equity_share'])}), money-weighted return a year: "
             + ", ".join(f"**{_pp(v)}** at {float(k):g} bps" for k, v in s["shortfall"].items())
             + f"; interval [{_pp(sci['lo'])}, {_pp(sci['hi'])}]; at most {bar.max_shortfall * 100:.2f} pp"]
    for c in result["clauses"]:
        lines.append(f"- Clause `{c['kind']}`: {'held' if c['passed'] else 'failed'} — {c['detail']}")
    h, pp, sr = s["control_ratio_by_half"], s["control_ratio_by_plan"], s["sell_rebalanced"]
    lines += ["", "## Reported, never read", "",
              f"- Control ratio by half of a plan (median across plans): first {h['first']}, second {h['second']}; "
              f"by plan: median {pp['median']}, worst {pp['worst']}.",
              "- Mean equity weight: " + ", ".join(f"{k} {_pct(v)}" for k, v in s["mean_equity_weight"].items()) + ".",
              "- Where the money went: " + ", ".join(f"{a} {_pct(v)}" for a, v in s["received"].items()) + ".",
              f"- An annual sell-back to target: control ratio {sr['control_ratio']}, gains realized "
              f"{sr['gains_realized_per_plan']} contributions per plan (taxable).",
              ]
    if s.get("halves"):
        lines.append("- Each half of the plan starts: " + "; ".join(
            f"{x['first_start']} → {x['last_start']}: ratio {x['control_ratio']}, shortfall {_pp(x['shortfall'])}"
            for x in s["halves"]) + ".")
    lines += ["", "| leg | " + " | ".join(f"return / yr at {float(c):g} bps | wealth per contribution"
                                         for c in s["legs"]) + " |",
              "|---|" + "---|---|" * len(s["legs"])]
    for k in cb.MIX_LEGS:
        lines.append(f"| {k} | " + " | ".join(
            f"{_pct(s['legs'][c][k]['money_weighted_return'])} | {s['legs'][c][k]['wealth_per_contribution']}"
            for c in s["legs"]) + " |")
    lines += ["", "## Equity drops, and each leg's equity weight at the peak", "",
              "| peak | trough | depth | plans running | member | plain |", "|---|---|---|---|---|---|"]
    lines += [f"| {e['peak']} | {e['trough']} | {_pct(e['depth'])} | {e['plans']} | "
              f"{_pct(e['equity_weight_member'])} | {_pct(e['equity_weight_plain'])} |" for e in s["episodes"]]
    lines += ["", "Only the sell-back reference sells; taxes are outside the bar (ADR-0026 §4). "
                  "An explore look is not a result: it goes to the register, never the KB.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the receipt
# ---------------------------------------------------------------------------

def _code_version() -> dict:
    """The commit the harness ran from, and whether the tree differed from it."""
    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(_HERE), *args], capture_output=True, text=True)
        except OSError:
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    status = git("status", "--porcelain", "--", ".")
    return {"commit": git("rev-parse", "HEAD"), "dirty": None if status is None else bool(status)}


def log_run(out_dir: Path, report: str, summary: dict, *, cached: bool, arm: str = ARM) -> dict:
    """Append this look's receipt to `runs.jsonl` (ADR-0022, WP-25.B)."""
    rec = {"run_at": datetime.now().astimezone().isoformat(timespec="seconds"), **_code_version(),
           "cached": cached, "seal": SEAL_START.isoformat(), "arms": [arm],
           "first_date": summary.get("first_date", summary.get("first_month")),
           "last_date": summary.get("last_date", summary.get("last_month")),
           "n_days": summary.get("n_days", summary.get("n_months")),
           "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest()}
    with (out_dir / RUN_LOG).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


def _inputs(out_dir: Path, cached: bool, member: str = "h009") -> dict:
    mix = member == "h011"
    cache = out_dir / ("inputs_h011.pkl" if mix else "inputs.pkl")
    if cached and cache.is_file():
        inputs = pickle.loads(cache.read_bytes())
    else:
        inputs = fetch_mix_inputs() if mix else fetch_inputs()
        cache.write_bytes(pickle.dumps(inputs))
    for k, v in list(inputs.items()):                        # a cache from anywhere is cut again
        if k != "fetched":
            inputs[k] = before_seal(v)
    return inputs


def dry_run(out_dir: Path = RESULTS_DIR, *, cached: bool = False, member: str = "h009") -> dict:
    """The slice and the flag, no rule read: what a look would walk. For H-010
    also the month-ends and the share the member names its high multiple at —
    the flag's frequency, which decides whether its reserve can balance; it
    reads no return. For H-011 the data errand's checks, the months, the plans
    and the equity drops the floor counts; no leg is walked."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = _inputs(out_dir, cached, member)
    if member == "h011":
        info = check_mix_inputs(inputs)
        path = build_mix_path(inputs)
        level = np.r_[1.0, np.cumprod(1.0 + path["returns"][MIX_EQUITY])]
        info.update({"n_plans": len(cb._plan_starts(path["months"], cb.MIX_RULE.plan_months, False)),
                     "n_equity_episodes": len(cb.risk_episodes(level, cb.MIX_RULE.episode_depth)),
                     "targets": MIX_TARGETS})
        print(json.dumps(info, indent=2))
        return info
    flag = pit_or(panel_channels(inputs["industries"]))
    path = build_path(inputs, flag)
    level = np.r_[1.0, np.cumprod(1.0 + path["equity"])]
    eps = cb.risk_episodes(level, cb.RISK_RULE.episode_depth)
    info = {"first_date": path["dates"][0], "last_date": path["dates"][-1], "n_days": len(path["dates"]),
            "flag_share_fired": round(float(flag.mean()), 4),
            "n_buy_and_hold_episodes": len(eps)}
    if member == "h010":
        fp = build_flow_path(inputs, flag)
        ends = cb.flow_months(fp["dates"], fp["last_month_complete"])
        m = fp["multiple"][ends]
        info.update({"n_month_ends": int(len(ends)), "share_high_months": round(float(np.mean(m == HIGH)), 4),
                     "balance_share": round((1.0 - LOW) / (HIGH - LOW), 4)})
    print(json.dumps(info, indent=2))
    return info


def run(out_dir: Path = RESULTS_DIR, *, cached: bool = False, member: str = "h009") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = _inputs(out_dir, cached, member)
    if member == "h011":
        (result, _), arm = look_h011(inputs), ARM_H011
        report = render_h011(result)
    elif member == "h010":
        (result, _), arm = look_h010(inputs), ARM_H010
        report = render_h010(result)
    else:
        (result, _), arm = look(inputs), ARM
        report = render(result)
    report_name, summary_name = _OUT[member]
    (out_dir / summary_name).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out_dir / report_name).write_text(report, encoding="utf-8")
    log_run(out_dir, report, result["summary"], cached=cached, arm=arm)
    print(report)
    return result


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cached", action="store_true", help="reuse results/explore_rules/inputs.pkl")
    ap.add_argument("--dry-run", action="store_true", help="build the slice and the flag; read no rule")
    ap.add_argument("--member", choices=MEMBERS, default="h009",
                    help="which register entry to walk (default h009; h010 is ADR-0025's first member, "
                         "h011 ADR-0026's)")
    a = ap.parse_args(argv)
    (dry_run if a.dry_run else run)(cached=a.cached, member=a.member)


if __name__ == "__main__":
    main()
