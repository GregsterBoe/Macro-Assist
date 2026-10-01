"""
explore_rules.py — EXPLORE-TIER mechanical risk rules on the pre-seal slice (ADR-0023).

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

Run
---
    python explore_rules.py --dry-run     # fetch, build the flag, print the slice; reads no rule
    python explore_rules.py               # the look: fetch, walk, read, report — COUNTED
    python explore_rules.py --cached      # the same on the cached inputs

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


def log_run(out_dir: Path, report: str, summary: dict, *, cached: bool) -> dict:
    """Append this look's receipt to `runs.jsonl` (ADR-0022, WP-25.B)."""
    rec = {"run_at": datetime.now().astimezone().isoformat(timespec="seconds"), **_code_version(),
           "cached": cached, "seal": SEAL_START.isoformat(), "arms": [ARM],
           "first_date": summary["first_date"], "last_date": summary["last_date"],
           "n_days": summary["n_days"],
           "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest()}
    with (out_dir / RUN_LOG).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


def _inputs(out_dir: Path, cached: bool) -> dict:
    cache = out_dir / "inputs.pkl"
    if cached and cache.is_file():
        inputs = pickle.loads(cache.read_bytes())
    else:
        inputs = fetch_inputs()
        cache.write_bytes(pickle.dumps(inputs))
    for k in ("industries", "factors"):                      # a cache from anywhere is cut again
        inputs[k] = before_seal(inputs[k])
    return inputs


def dry_run(out_dir: Path = RESULTS_DIR, *, cached: bool = False) -> dict:
    """The slice and the flag, no rule read: what a look would walk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = _inputs(out_dir, cached)
    flag = pit_or(panel_channels(inputs["industries"]))
    path = build_path(inputs, flag)
    level = np.r_[1.0, np.cumprod(1.0 + path["equity"])]
    eps = cb.risk_episodes(level, cb.RISK_RULE.episode_depth)
    info = {"first_date": path["dates"][0], "last_date": path["dates"][-1], "n_days": len(path["dates"]),
            "flag_share_fired": round(float(flag.mean()), 4),
            "n_buy_and_hold_episodes": len(eps)}
    print(json.dumps(info, indent=2))
    return info


def run(out_dir: Path = RESULTS_DIR, *, cached: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result, _ = look(_inputs(out_dir, cached))
    report = render(result)
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    log_run(out_dir, report, result["summary"], cached=cached)
    print(report)
    return result


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cached", action="store_true", help="reuse results/explore_rules/inputs.pkl")
    ap.add_argument("--dry-run", action="store_true", help="build the slice and the flag; read no rule")
    a = ap.parse_args(argv)
    (dry_run if a.dry_run else run)(cached=a.cached)


if __name__ == "__main__":
    main()
