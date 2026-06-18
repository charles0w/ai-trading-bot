"""Abstract broker interface so we can swap in real brokers later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class OptionContract:
    occ_symbol: str             # e.g. SPY240517C00580000
    underlying: str
    option_type: str            # "call" | "put"
    strike: float
    expiry: date
    bid: float | None = None
    ask: float | None = None
    last: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return self.last
        return (self.bid + self.ask) / 2


@dataclass
class OrderResult:
    broker_order_id: str
    status: str                 # "pending" | "filled" | "partial" | "canceled" | "rejected"
    filled_qty: int = 0
    avg_fill_price: float | None = None
    raw: dict | None = None


@dataclass
class PositionSnapshot:
    occ_symbol: str
    quantity: int
    entry_price: float
    mark_price: float | None


class Broker(ABC):
    name: str

    @abstractmethod
    def buying_power_usd(self) -> float: ...

    @abstractmethod
    def find_option_contract(
        self, underlying: str, expiry: date, strike: float, option_type: str
    ) -> OptionContract | None: ...

    @abstractmethod
    def place_order(
        self,
        contract: OptionContract,
        side: str,                     # "buy" | "sell"
        quantity: int,
        order_type: str,               # "market" | "limit"
        limit_price: float | None = None,
        time_in_force: str = "day",
    ) -> OrderResult: ...

    @abstractmethod
    def get_order(self, broker_order_id: str) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None: ...

    @abstractmethod
    def get_position(self, occ_symbol: str) -> PositionSnapshot | None: ...

    @abstractmethod
    def get_option_mark(self, occ_symbol: str) -> float | None: ...

    @abstractmethod
    def list_option_contracts(
        self,
        underlying: str,
        *,
        expiration_gte: date,
        expiration_lte: date,
        option_type: str,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
        limit: int = 200,
    ) -> list[OptionContract]: ...
