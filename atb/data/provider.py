"""Market-data provider interface + DTOs.

Free providers (yfinance) implement what they can; fields needing paid data
(SUE, full IV history, signed flow) are Optional and left None until a richer
provider fills them. The feature builder degrades gracefully on None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass
class PriceBar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class EarningsEvent:
    symbol: str
    day: date
    eps_actual: float | None = None
    eps_estimate: float | None = None
    sue: float | None = None            # standardized unexpected earnings (needs history)


@dataclass
class OptionQuote:
    occ_symbol: str
    strike: float
    expiry: date
    option_type: str                    # "call" | "put"
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    open_interest: int | None = None

    @property
    def spread_pct(self) -> float | None:
        if self.bid and self.ask and self.ask > 0:
            mid = (self.bid + self.ask) / 2
            return (self.ask - self.bid) / mid * 100 if mid else None
        return None


@runtime_checkable
class MarketDataProvider(Protocol):
    def daily_bars(self, symbol: str, *, lookback_days: int = 500) -> list[PriceBar]:
        """Ascending by day, oldest first."""
        ...

    def latest_price(self, symbol: str) -> float | None: ...

    def recent_earnings(self, symbol: str, *, asof: date) -> EarningsEvent | None:
        """Most recent earnings on or before `asof`, if known."""
        ...

    def option_chain(self, symbol: str, *, expiry: date, option_type: str) -> list[OptionQuote]:
        """Best-effort; may return [] if the provider lacks options data."""
        ...
