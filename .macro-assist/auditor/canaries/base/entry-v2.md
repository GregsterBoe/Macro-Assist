## H-101 — In a stressed S&P tape, the OR state widens Gold's forward distribution on both sides {: #h-101 }

**Status:** `draft` · drafted 2026-08-03 · explore look 2026-08-12 · prepared for promotion 2026-08-13; needs an independent audit before it is a hypothesis (§6, ADR-0022).

**What was seen.** Nothing yet specific to this entry. The question comes from [KB-016]'s precision trade: the OR flag fires on many days that are not followed by an S&P drawdown, and nobody has asked what the *other* assets do on those days.

**Where.** `explore_conditioner.py` arms `dd_bin` and `dd_x_frag`, which already quote Gold, conditioned on the S&P's drawdown bin and on the S&P drawdown bin × `fragility_or` state. Report: `results/explore_conditioner/report.md`, once the look has run.

**Mechanism it would imply.** In a stressed S&P tape (drawdown ≤ −5%), Gold faces two opposite flows: a haven bid, and forced selling to meet margin calls elsewhere. When the tape is also structurally fragile (the OR flag: correlation, term structure and turbulence at their own point-in-time top decile), both flows are stronger at once. Gold's outcomes should spread in *both* directions. The flag should say nothing about which way Gold goes.

**The prediction that is not the score.** Within the stressed bin, the OR-Elevated cell's P25–P75 width is at least 1.2 times the Normal cell's at every horizon (5, 10, 20 days), and the ratio does not shrink from 5d to 20d. The widening is two-sided: the Elevated cell's P25 sits below the Normal cell's *and* its P75 sits above it, at every horizon. A level shift would move one tail; the two-flow mechanism moves both.

**The confound.** Gold's own volatility clustering. A fragile S&P tape may simply be a high-vol week for Gold as well, and the width split would then be a vol forecast restated ([KB-033]). The rival is `har_scaled` on Gold within the stressed bin. If splitting the stressed bin by `har_scaled`'s σ tercile reproduces the Elevated/Normal width split, the state is not doing the work. Secondary: the stressed bin is small, so its episodes are counted as well as its rows.

**What would test it.** One counted explore look first, with its rival in the same run: Gold's realized forward change by S&P drawdown bin × OR state, widths and P25/P75 at 5, 10 and 20 days, with distinct stress spells counted per cell; and the stressed bin split by `har_scaled`'s σ tercile, with the OR state inside each tercile. If the Elevated/Normal split survives inside the top σ tercile, the state carries something the vol forecast does not. Then, only if both hold, a shadow conditioner under WP-23.B's class bar: pinball loss on Gold's P25/P50/P75 against `unconditional`, and against `har_scaled` as the second comparator, with the two-sided widening as the mechanism clause. **Underpowered floor**, fixed now, before any cell size is known: a sealed cell with fewer than 150 rows or fewer than 8 distinct stress spells makes the read `underpowered`. **Slice:** the whole sealed side, from `SEAL_START` 2018-01-01 (`resolved.md` #19). **One read**, with the result going to the Knowledge Base either way.

**Target-space check.** A width, and a two-sided one: a property of the conditional distribution, read by the distribution scorer. No location claim. Passes.

**Read first.** [KB-016] · [KB-017] · [KB-033] · WP-23.B · `fragility_or.py::_pit_backtest`.

**Explore-tier looks (ledger).** *2026-08-12* — `explore_conditioner.py --cached`, one run, the first look specific to this entry. Arms read: `dd_bin` and `dd_x_frag`, Gold only, plus the two structure tables in `results/explore_conditioner/report.md` (§ *Gold structure check* and § *Gold rival check*). Configuration as the harness shipped it: `DD_EDGES = (−5%, −10%)`, `MIN_N = 10`, `BURN_IN = 252`, `HAR_WINDOW = 1250`. The run scored 13 arms against `unconditional` (the report's multiplicity line); this entry read two of them, at three horizons, on one asset. The prediction and the floor above were committed on 2026-08-03, nine days before the run.

What the run showed, stressed bin (S&P drawdown ≤ −5%), OR-Elevated vs Normal:
- Width (P75−P25): 3.33 vs 2.54 at 5d (ratio 1.31) · 4.83 vs 3.48 at 10d (1.39) · 6.67 vs 4.39 at 20d (1.52). At least 1.2 at every horizon, and growing: the pre-registered prediction held.
- Two-sided at every horizon: Elevated P25 below Normal's (−1.62 vs −1.18 · −2.31 vs −1.62 · −3.05 vs −2.24) and P75 above it (1.71 vs 1.36 · 2.52 vs 1.86 · 3.62 vs 2.15).
- Cell sizes: 169 and 286 rows (11 and 27 distinct stress spells), above the floor of 150 rows and 8 spells.
- Rival: inside the top `har_scaled` σ tercile, Elevated is still wider than Normal at 20d (7.12 vs 5.48, ratio 1.30). The split shrinks inside the tercile but does not vanish. Those two cells are small (100 and 51 rows; 9 and 8 spells), under the 150-row floor, which is written for the sealed read's cells. So this reading is claimed only as a direction: it does not show that the state beats the vol forecast. The sealed read tests that, with `har_scaled` as its second comparator.

Not claimed: anything about Gold's median, any other asset, or any horizon beyond 20 days.
