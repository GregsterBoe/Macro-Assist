"""
bar_headroom.py — how good must a signal be to pass a goal-3 class bar? (KB-038)

Research harness (product_surface: RESEARCH). Reads no candidate signal and no
register entry, and writes nothing: it prints. It feeds a class bar a
synthetic month-end signal that sees the market's own future with correlation
rho (rho = 1 is perfect foresight, rho = 0 is noise) and reports whether a
rule built on it would clear the bar. A bar no realistic rho clears cannot be
passed by any member, whatever its data; that is worth knowing before a
member's data is built.

The slice
---------
H-009's cached explore inputs (`results/explore_rules/inputs.pkl`, the
Fama-French daily market and RF), cut at `numeric_baseline.SEAL_START` again
on load. Nothing here reads a sealed day.

The two bars
------------
`flow_rule` (ADR-0025)  each month-end the signal names a high or a low
                        contribution multiple; the target is the market's
                        log return over the next 252 trading days.
`risk_rule` (ADR-0023)  each month-end the signal cuts equity exposure to
                        `low` for the month, else 1; the target is the
                        market's worst fall over the next 63 trading days.

The member's share of firing months is fixed per row, ranks are taken over
the window, and each rho < 1 is averaged over fixed seeds. Both choices see
the window whole — a synthetic signal is allowed what a member is not.

    python bar_headroom.py              # both bars (~25 min)
    python bar_headroom.py --bar flow   # or one
"""
from __future__ import annotations

import argparse
import pickle

import numpy as np

import class_bars as cb
from explore_rules import RESULTS_DIR, before_seal
from numeric_baseline import SEAL_START

RHOS = (0.1, 0.2, 0.3, 0.5, 1.0)
FLOW_WINDOWS = (("1932-01-01", "1932-2017 (H-010's slice)"),
                ("2003-07-01", "2003-2017 (free insider data)"),
                ("2009-03-01", "2009-2017 (as long as the sealed side)"))
RISK_WINDOWS = FLOW_WINDOWS[:2]
H010_MULTIPLES = (0.75, 2.0)
OTHER_MULTIPLES = ((0.5, 2.0), (0.5, 3.0), (0.0, 3.0), (0.9, 1.5))
FLOW_HORIZON, RISK_HORIZON = 252, 63
FLOW_BOOT = 50                     # the interval is reported, not read: the mean is the number


def load_market() -> tuple[list[str], np.ndarray, np.ndarray]:
    inp = pickle.loads((RESULTS_DIR / "inputs.pkl").read_bytes())
    fac = before_seal(inp["factors"])
    if fac.index.max().date() >= SEAL_START:
        raise RuntimeError("the cached inputs reach the sealed side")
    return ([d.strftime("%Y-%m-%d") for d in fac.index],
            (fac["Mkt-RF"] + fac["RF"]).to_numpy(float), fac["RF"].to_numpy(float))


def window(market, start: str):
    dates, eq, rf = market
    i = next(k for k, d in enumerate(dates) if d >= start)
    return dates[i:], eq[i:], rf[i:]


def forward_return(eq: np.ndarray, ends: np.ndarray, horizon: int = FLOW_HORIZON) -> np.ndarray:
    """The market's log return over the `horizon` days after each month-end."""
    lg = np.r_[0.0, np.cumsum(np.log1p(eq))]
    out = np.empty(len(ends))
    for j, e in enumerate(ends):
        a, b = e + 1, min(e + 1 + horizon, len(eq))
        out[j] = lg[b] - lg[a] if b > a else 0.0
    return out


def forward_drop(eq: np.ndarray, ends: np.ndarray, horizon: int = RISK_HORIZON) -> np.ndarray:
    """The market's deepest fall from its running high over the `horizon` days after each month-end."""
    lv = np.r_[1.0, np.cumprod(1.0 + eq)]
    out = np.empty(len(ends))
    for j, e in enumerate(ends):
        w = lv[e + 1:min(e + 2 + horizon, len(lv))]
        out[j] = float(np.max(1.0 - w / np.maximum.accumulate(w))) if len(w) > 1 else 0.0
    return out


def synthetic(target: np.ndarray, rho: float, share: float, seed: int) -> np.ndarray:
    """Which month-ends fire: the top `share` of rho·z(target) + noise."""
    z = (target - target.mean()) / target.std()
    rng = np.random.default_rng(seed)
    sig = rho * z + np.sqrt(max(0.0, 1 - rho ** 2)) * rng.standard_normal(len(z))
    return sig >= np.quantile(sig, 1 - share)


def flow_row(market, start: str, share: float, rho: float, multiples=H010_MULTIPLES,
             seeds: int = 30) -> dict:
    low, high = multiples
    dates, eq, rf = window(market, start)
    ends = cb.flow_months(dates, True)
    target = forward_return(eq, ends)
    res = []
    for s in range(seeds if rho < 1 else 1):
        mult = np.full(len(dates), low)
        mult[ends] = np.where(synthetic(target, rho, share, s), high, low)
        sm = cb.flow_summary(cb.FLOW_RULE, {"dates": dates, "equity": eq, "cash": rf, "multiple": mult,
                                            "last_month_complete": True}, "headroom", n_boot=FLOW_BOOT)
        w = sm["legs"]["10.0"]
        res.append((sm["advantage"]["10.0"], sm["advantage_vs_dip"],
                    w["member"]["wealth_per_contribution"] / w["plain"]["wealth_per_contribution"] - 1,
                    sm["n_episodes"], sm["starved_share_of_high_months"]))
    r = np.array(res, float)
    m = r.mean(0)
    return {"vs_plain": m[0], "lo": r[:, 0].min(), "hi": r[:, 0].max(), "vs_dip": m[1],
            "wealth": m[2], "drops": m[3], "starved": m[4]}


def risk_row(market, start: str, share: float, rho: float, low: float, seeds: int = 20) -> dict:
    bar = cb.RISK_RULE
    dates, eq, rf = window(market, start)
    ends = cb.flow_months(dates, True)
    target = forward_drop(eq, ends)
    res = []
    for s in range(seeds if rho < 1 else 1):
        fire = synthetic(target, rho, share, s)
        expo = np.ones(len(dates))
        for j, e in enumerate(ends):                     # decided at the month-end close, held the month
            if fire[j]:
                expo[e:ends[j + 1] if j + 1 < len(ends) else len(dates) - 1] = low
        sm = cb.risk_summary(bar, {"dates": dates, "equity": eq, "cash": rf, "exposure": expo}, "headroom")
        short = min(sm["shortfall"].values())
        sav, sv = sm["saving"], sm["saving_vs_vol"]
        passes = (sm["mean_r"] <= 1 and short >= -bar.max_shortfall and sav["mean"] >= bar.min_saving
                  and sav["ci"]["lo"] > 0 and sv["mean"] > 0 and sv["share_better"] >= bar.vol_majority)
        res.append((short, sav["mean"], sav["ci"]["lo"], sv["mean"], sv["share_better"], passes,
                    sm["n_episodes"]))
    m = np.array(res, float).mean(0)
    return dict(zip(("shortfall", "saving", "saving_lo", "vs_vol", "vol_wins", "passes", "drops"), m))


def run_flow(market) -> None:
    print("flow_rule (ADR-0025): needs +0.25 pp a year over plain, and more than dip_matched")
    for start, label in FLOW_WINDOWS:
        print(f"\n== {label}, H-010's multiples {H010_MULTIPLES}")
        for share in (0.20, 0.287):
            for rho in RHOS:
                r = flow_row(market, start, share, rho)
                print(f"share {share:.3f} rho {rho:.1f}: vs plain {r['vs_plain'] * 100:+.3f} pp/yr "
                      f"[{r['lo'] * 100:+.3f},{r['hi'] * 100:+.3f}]  vs dip {r['vs_dip'] * 100:+.3f}  "
                      f"wealth {r['wealth'] * 100:+.2f}%  drops {r['drops']:.0f}  starved {r['starved']:.2f}")
    print("\n== other multiples, firing at the share that balances the reserve")
    for low, high in OTHER_MULTIPLES:
        share = (1 - low) / (high - low)
        for start, _ in FLOW_WINDOWS:
            cells = []
            for rho in (0.3, 1.0):
                r = flow_row(market, start, share, rho, (low, high), seeds=10)
                cells.append(f"rho {rho}: {r['vs_plain'] * 100:+.3f} pp/yr, wealth {r['wealth'] * 100:+.2f}%, "
                             f"vs dip {r['vs_dip'] * 100:+.3f}")
            print(f"m=({low},{high}) share {share:.2f} from {start}: " + " | ".join(cells))


def run_risk(market) -> None:
    print("risk_rule (ADR-0023): return within 0.5 pp of static_matched, saving >= 0.10 clear of zero, "
          "beats vol_matched in two thirds of drops")
    for start, label in RISK_WINDOWS:
        print(f"\n== {label}")
        for low in (0.5, 0.0):
            for share in (0.15, 0.25):
                for rho in RHOS:
                    r = risk_row(market, start, share, rho, low)
                    print(f"cut to {low:.1f}, fires {share:.0%} of months, rho {rho:.1f}: "
                          f"return vs same-avg-stock {r['shortfall'] * 100:+.2f} pp/yr | "
                          f"drop saved {r['saving']:+.3f} (ci lo {r['saving_lo']:+.3f}) | "
                          f"vs vol rule {r['vs_vol']:+.3f}, wins {r['vol_wins']:.0%} | "
                          f"passes {r['passes']:.0%} | drops {r['drops']:.0f}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bar", choices=("flow", "risk", "both"), default="both")
    a = ap.parse_args(argv)
    market = load_market()
    if a.bar in ("flow", "both"):
        run_flow(market)
    if a.bar in ("risk", "both"):
        print()
        run_risk(market)


if __name__ == "__main__":
    main()
