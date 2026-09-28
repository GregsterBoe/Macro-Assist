## H-101 — In a stressed S&P tape, the OR state widens Gold's forward distribution on both sides {: #h-101 }

**Status:** `draft` — drafted 2026-08-03, before any look specific to it; needs an independent audit before it is a hypothesis (§6, ADR-0022).

**What was seen.** Nothing yet specific to this entry. The question comes from [KB-016]'s precision trade: the OR flag fires on many days that are not followed by an S&P drawdown, and nobody has asked what the *other* assets do on those days.

**Where.** `explore_conditioner.py` arms `dd_bin` and `dd_x_frag`, which already quote Gold, conditioned on the S&P's drawdown bin and on the S&P drawdown bin × `fragility_or` state. Report: `results/explore_conditioner/report.md`, once the look has run.

**Mechanism it would imply.** In a stressed S&P tape (drawdown ≤ −5%), Gold faces two opposite flows: a haven bid, and forced selling to meet margin calls elsewhere. When the tape is also structurally fragile (the OR flag: correlation, term structure and turbulence at their own point-in-time top decile), both flows are stronger at once. Gold's outcomes should spread in *both* directions. The flag should say nothing about which way Gold goes.

**The prediction that is not the score.** Within the stressed bin, the OR-Elevated cell's P25–P75 width is at least 1.2 times the Normal cell's at every horizon (5, 10, 20 days), and the ratio does not shrink from 5d to 20d. The widening is two-sided: the Elevated cell's P25 sits below the Normal cell's *and* its P75 sits above it, at every horizon. A level shift would move one tail; the two-flow mechanism moves both.

**The confound.** Gold's own volatility clustering. A fragile S&P tape may simply be a high-vol week for Gold as well, and the width split would then be a vol forecast restated ([KB-033]). The rival is `har_scaled` on Gold within the stressed bin. If splitting the stressed bin by `har_scaled`'s σ tercile reproduces the Elevated/Normal width split, the state is not doing the work. Secondary: the stressed bin is small, so its episodes are counted as well as its rows.

**What would test it.** One counted explore look first, with its rival in the same run: Gold's realized forward change by S&P drawdown bin × OR state, widths and P25/P75 at 5, 10 and 20 days, with distinct stress spells counted per cell; and the stressed bin split by `har_scaled`'s σ tercile, with the OR state inside each tercile. If the Elevated/Normal split survives inside the top σ tercile, the state carries something the vol forecast does not. Then, only if both hold, a shadow conditioner under WP-23.B's class bar: pinball loss on Gold's P25/P50/P75 against `unconditional`, and against `har_scaled` as the second comparator, with the two-sided widening as the mechanism clause. **Underpowered floor**, fixed now, before any cell size is known: a sealed cell with fewer than 150 rows or fewer than 8 distinct stress spells makes the read `underpowered`. **Slice:** the whole sealed side, from `SEAL_START` 2018-01-01 (`resolved.md` #19). **One read**, with the result going to the Knowledge Base either way.

**Target-space check.** A width, and a two-sided one: a property of the conditional distribution, read by the distribution scorer. No location claim. Passes.

**Read first.** [KB-016] · [KB-017] · [KB-033] · WP-23.B · `fragility_or.py::_pit_backtest`.
