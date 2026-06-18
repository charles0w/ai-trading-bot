"""Persistence port.

The executor and exit-manager don't know about SQLite, lambos's schema, or
ai-trading-bot's schema — they only need an object that satisfies this
`Store` Protocol. lambos's DB adapts to it; ai-trading-bot provides its own;
tests use an InMemoryStore. This is what decouples the borrowed "hands" from
either app's database.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def mark_signal_rejected(self, signal_id: str | None, reason: str) -> None: ...

    def insert_order(
        self,
        *,
        signal_id: str | None = None,
        parent_order_id: int | None = None,
        broker: str,
        broker_order_id: str | None = None,
        client_order_id: str | None = None,
        submitted_at_utc: str,
        occ_symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        status: str,
        filled_qty: int = 0,
        avg_fill_price: float | None = None,
        exit_reason: str | None = None,
    ) -> int: ...

    def update_order(self, order_id: int, **fields: Any) -> None: ...

    def open_position(
        self,
        *,
        open_order_id: int,
        occ_symbol: str,
        quantity: int,
        entry_price: float,
        entry_at_utc: str,
    ) -> int: ...

    def open_positions(self) -> list[dict]: ...

    def update_position_mark(self, position_id: int, mark: float) -> None: ...

    def mark_position_closed(self, position_id: int) -> None: ...
