"""
book.py — Virtual portfolio ledger for the Phase-20 paper portfolio (WP-20.B).

An instrument-agnostic, deterministic accounting core. It holds positions in
*any* instrument (the 6 predicted macro assets, or — later — sector / materials
ETFs), marks them on a supplied price map, executes target-weight rebalances with
a per-instrument transaction-cost model, and tracks a NAV history. It enforces
**no** risk limits and makes **no** allocation decisions — the sizing layer
(`sizing.py`, WP-20.C) hands it target weights; the book just executes them.

Design notes (see DESIGN.md):
  * No network here. Prices are always passed in as `{instrument_name: price}`.
    yfinance fetching lives in `rebalance.py` (WP-20.D). This keeps the ledger a
    pure, fully unit-testable function of its inputs.
  * Positions may be negative (shorts) — the paper book is virtual.
  * Every position carries a `sleeve` tag so position value / P&L can be
    attributed per signal sleeve *within* a book. For the cleanest independent
    A/B, prefer one Book per sleeve (macro / exogenous / kimi / sector); the tag
    is for the case where sleeves share one book.
  * A static-weight buy-and-hold benchmark is just a Book rebalanced once and then
    marked forward (weights drift) — see `buy_and_hold`.

Usage:
    from portfolio.book import Book, Instrument
    book = Book(arm="market")
    book.register(Instrument("S&P 500", "^GSPC", "equity"))
    book.rebalance({"S&P 500": 0.5}, prices={"S&P 500": 100.0}, as_of=date(2026,8,19))
    book.mark({"S&P 500": 102.0}, as_of=date(2026,8,20))
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

DEFAULT_STARTING_NAV = 100_000.0  # USD; NAV is reported as an index off this.
DEFAULT_COST_BPS = 10.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Instrument:
    """A tradeable instrument. `name` is the canonical key used everywhere
    (matches the pipeline's asset names, e.g. 'S&P 500'); `ticker` is for the
    price fetcher only."""
    name: str
    ticker: str
    asset_class: str = "equity"      # equity | commodity | crypto | bond | fx
    currency: str = "USD"
    cost_bps: float = DEFAULT_COST_BPS


@dataclass
class Position:
    shares: float = 0.0              # signed: negative = short
    avg_px: float = 0.0              # cost basis of the current open position
    sleeve: str = "macro"

    def market_value(self, price: float) -> float:
        return self.shares * price


# ---------------------------------------------------------------------------
# The book
# ---------------------------------------------------------------------------
class Book:
    """A single virtual portfolio: one cash pool + positions + a NAV history.

    Weights passed to :meth:`rebalance` are fractions of current NAV. A weight of
    0.5 means 'hold 50% of NAV in this instrument'. Instruments omitted from the
    target map are closed (target 0). Gross > 1 (leverage) is allowed and shows up
    as negative cash — the book does not police it; the sizing layer does.
    """

    def __init__(
        self,
        arm: str = "market",
        base_ccy: str = "USD",
        starting_nav: float = DEFAULT_STARTING_NAV,
    ) -> None:
        self.arm = arm
        self.base_ccy = base_ccy
        self.starting_nav = starting_nav
        self.cash: float = starting_nav
        self.instruments: dict[str, Instrument] = {}
        self.positions: dict[str, Position] = {}
        self.nav_history: list[dict] = []
        self.decision_log: list[dict] = []

    # -- registry -----------------------------------------------------------
    def register(self, instrument: Instrument) -> None:
        self.instruments[instrument.name] = instrument

    def _require(self, name: str) -> Instrument:
        if name not in self.instruments:
            raise KeyError(f"instrument not registered: {name!r}")
        return self.instruments[name]

    # -- valuation ----------------------------------------------------------
    def market_value(self, prices: dict[str, float]) -> float:
        """Signed market value of all open positions (longs +, shorts −)."""
        return sum(
            pos.shares * prices[name]
            for name, pos in self.positions.items()
            if pos.shares != 0.0
        )

    def nav(self, prices: dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def gross_exposure(self, prices: dict[str, float]) -> float:
        """Sum of |position value|, as a fraction of NAV."""
        nav = self.nav(prices)
        if nav == 0:
            return 0.0
        gross = sum(abs(pos.shares * prices[name]) for name, pos in self.positions.items())
        return gross / nav

    def net_exposure(self, prices: dict[str, float]) -> float:
        nav = self.nav(prices)
        return self.market_value(prices) / nav if nav else 0.0

    def exposure_by_sleeve(self, prices: dict[str, float]) -> dict[str, float]:
        """Signed market value per sleeve — the well-defined per-sleeve
        attribution (cash stays at book level)."""
        out: dict[str, float] = {}
        for name, pos in self.positions.items():
            if pos.shares == 0.0:
                continue
            out[pos.sleeve] = out.get(pos.sleeve, 0.0) + pos.shares * prices[name]
        return out

    def weights(self, prices: dict[str, float]) -> dict[str, float]:
        nav = self.nav(prices)
        if nav == 0:
            return {}
        return {
            name: (pos.shares * prices[name]) / nav
            for name, pos in self.positions.items()
            if pos.shares != 0.0
        }

    # -- mutation -----------------------------------------------------------
    def mark(self, prices: dict[str, float], as_of: date, note: str = "") -> dict:
        """Record a NAV point without trading (daily mark-to-market)."""
        point = self._nav_point(prices, as_of, note)
        self.nav_history.append(point)
        return point

    def rebalance(
        self,
        target_weights: dict[str, float],
        prices: dict[str, float],
        as_of: date,
        regime_gate: Optional[float] = None,
        note: str = "",
        sleeve_of: Optional[dict[str, str]] = None,
    ) -> dict:
        """Move the book to `target_weights` (fractions of *pre-trade* NAV).

        Instruments held but absent from `target_weights` are closed. Returns the
        rebalance record (also appended to `decision_log`), and appends a NAV
        point to `nav_history`.
        """
        nav_pre = self.nav(prices)
        sleeve_of = sleeve_of or {}
        trades: dict[str, dict] = {}

        # Union of currently-held and newly-targeted instruments.
        names = set(self.positions) | set(target_weights)
        for name in sorted(names):
            price = prices.get(name)
            if price is None:
                if target_weights.get(name):
                    raise KeyError(f"no price for targeted instrument {name!r}")
                continue  # can't mark/close without a price; skip
            inst = self._require(name)
            old_shares = self.positions.get(name, Position()).shares
            target_w = target_weights.get(name, 0.0)
            new_shares = (target_w * nav_pre) / price if price else 0.0
            delta = new_shares - old_shares
            if delta == 0.0:
                continue

            traded_notional = abs(delta) * price
            cost = traded_notional * inst.cost_bps / 1e4
            self.cash -= delta * price      # buying (delta>0) reduces cash
            self.cash -= cost               # costs always reduce cash

            sleeve = sleeve_of.get(name, self.positions.get(name, Position()).sleeve)
            self.positions[name] = Position(
                shares=new_shares,
                avg_px=price if new_shares != 0.0 else 0.0,
                sleeve=sleeve,
            )
            trades[name] = {
                "from_shares": round(old_shares, 6),
                "to_shares": round(new_shares, 6),
                "px": price,
                "traded_notional": round(traded_notional, 2),
                "cost": round(cost, 2),
                "target_w": target_w,
            }

        record = {
            "as_of": as_of.isoformat(),
            "nav_before": round(nav_pre, 2),
            "nav_after": round(self.nav(prices), 2),
            "regime_gate": regime_gate,
            "targets": dict(target_weights),
            "trades": trades,
            "note": note,
        }
        self.decision_log.append(record)
        self.nav_history.append(self._nav_point(prices, as_of, note))
        return record

    # -- helpers ------------------------------------------------------------
    def _nav_point(self, prices: dict[str, float], as_of: date, note: str) -> dict:
        return {
            "date": as_of.isoformat(),
            "nav": round(self.nav(prices), 2),
            "cash": round(self.cash, 2),
            "gross": round(self.gross_exposure(prices), 4),
            "net": round(self.net_exposure(prices), 4),
            "note": note,
        }

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "base_ccy": self.base_ccy,
            "starting_nav": self.starting_nav,
            "cash": self.cash,
            "instruments": {n: asdict(i) for n, i in self.instruments.items()},
            "positions": {n: asdict(p) for n, p in self.positions.items()},
            "nav_history": self.nav_history,
            "decision_log": self.decision_log,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        book = cls(
            arm=d.get("arm", "market"),
            base_ccy=d.get("base_ccy", "USD"),
            starting_nav=d.get("starting_nav", DEFAULT_STARTING_NAV),
        )
        book.cash = d["cash"]
        book.instruments = {n: Instrument(**i) for n, i in d.get("instruments", {}).items()}
        book.positions = {n: Position(**p) for n, p in d.get("positions", {}).items()}
        book.nav_history = list(d.get("nav_history", []))
        book.decision_log = list(d.get("decision_log", []))
        return book

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: Path) -> "Book":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# ---------------------------------------------------------------------------
# Benchmark convenience
# ---------------------------------------------------------------------------
def buy_and_hold(
    weights: dict[str, float],
    instruments: list[Instrument],
    price_history: list[tuple[date, dict[str, float]]],
    arm: str = "benchmark",
    starting_nav: float = DEFAULT_STARTING_NAV,
) -> Book:
    """Build a static-weight buy-and-hold benchmark book: allocate once on the
    first date (paying costs), then mark forward as weights drift naturally.

    `price_history` is chronological [(date, {name: price}), ...].
    """
    book = Book(arm=arm, starting_nav=starting_nav)
    for inst in instruments:
        book.register(inst)
    if not price_history:
        return book
    first_date, first_prices = price_history[0]
    book.rebalance(weights, first_prices, first_date, note="buy-and-hold init")
    for d, prices in price_history[1:]:
        book.mark(prices, d, note="buy-and-hold mark")
    return book
