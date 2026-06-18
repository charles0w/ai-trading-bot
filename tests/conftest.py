"""Test doubles for trader_core: an in-memory Store and a scriptable FakeBroker.

These let us exercise the full entry/exit machinery without alpaca-py, network,
or a database.
"""

from __future__ import annotations

from datetime import date

import pytest

from trader_core.broker.base import Broker, OptionContract, OrderResult, PositionSnapshot
from trader_core.config import Config


class InMemoryStore:
    def __init__(self) -> None:
        self.orders: dict[int, dict] = {}
        self.positions: dict[int, dict] = {}
        self.rejections: list[tuple[str | None, str]] = []
        self._oid = 0
        self._pid = 0

    def mark_signal_rejected(self, signal_id, reason):
        self.rejections.append((signal_id, reason))

    def insert_order(self, **fields):
        self._oid += 1
        self.orders[self._oid] = dict(id=self._oid, **fields)
        return self._oid

    def update_order(self, order_id, **fields):
        self.orders[order_id].update(fields)

    def open_position(self, *, open_order_id, occ_symbol, quantity, entry_price, entry_at_utc):
        self._pid += 1
        self.positions[self._pid] = dict(
            id=self._pid, open_order_id=open_order_id, occ_symbol=occ_symbol,
            quantity=quantity, entry_price=entry_price, entry_at_utc=entry_at_utc,
            mark=None, closed=False,
        )
        return self._pid

    def open_positions(self):
        return [p for p in self.positions.values() if not p["closed"]]

    def update_position_mark(self, position_id, mark):
        self.positions[position_id]["mark"] = mark

    def mark_position_closed(self, position_id):
        self.positions[position_id]["closed"] = True


class FakeBroker(Broker):
    """Scriptable broker. `fill_sequence` is the list of statuses returned by
    successive get_order() calls; place_order() returns the first."""

    name = "fake"

    def __init__(self, *, fill_sequence=("filled",), avg_fill_price=2.50,
                 mark=2.50, buying_power=100_000.0, spot=200.0, strike_step=5.0):
        self._seq = list(fill_sequence)
        self._avg = avg_fill_price
        self._mark = mark
        self._bp = buying_power
        self._spot = spot
        self._strike_step = strike_step
        self.placed: list[dict] = []
        self.canceled: list[str] = []
        self._poll_i = 0

    def buying_power_usd(self) -> float:
        return self._bp

    def find_option_contract(self, underlying, expiry, strike, option_type):
        return OptionContract(
            occ_symbol=f"{underlying}{expiry:%y%m%d}{option_type[0].upper()}{int(strike*1000):08d}",
            underlying=underlying, option_type=option_type, strike=strike,
            expiry=expiry, bid=self._mark - 0.05, ask=self._mark + 0.05,
        )

    def _result(self, status):
        return OrderResult(
            broker_order_id="ord-1", status=status,
            filled_qty=1 if status == "filled" else 0,
            avg_fill_price=self._avg if status == "filled" else None,
        )

    def place_order(self, *, contract, side, quantity, order_type, limit_price=None,
                    time_in_force="day"):
        self.placed.append(dict(occ=contract.occ_symbol, side=side, qty=quantity,
                                order_type=order_type, limit_price=limit_price))
        return self._result(self._seq[0])

    def get_order(self, broker_order_id):
        self._poll_i = min(self._poll_i + 1, len(self._seq) - 1)
        return self._result(self._seq[self._poll_i])

    def cancel_order(self, broker_order_id):
        self.canceled.append(broker_order_id)

    def get_position(self, occ_symbol):
        return None

    def get_option_mark(self, occ_symbol):
        return self._mark

    def list_option_contracts(self, underlying, *, expiration_gte, expiration_lte,
                              option_type, strike_gte=None, strike_lte=None, limit=200):
        from datetime import timedelta
        expiries = []
        d = expiration_gte
        while d <= expiration_lte:
            if d.weekday() == 4:  # weekly Friday expiries
                expiries.append(d)
            d += timedelta(days=1)
        if not expiries:
            expiries = [expiration_lte]
        lo = strike_gte if strike_gte is not None else self._spot * 0.8
        hi = strike_lte if strike_lte is not None else self._spot * 1.2
        out = []
        for exp in expiries:
            k = int(lo / self._strike_step) * self._strike_step
            while k <= hi:
                if k >= lo:
                    occ = (f"{underlying.upper()}{exp:%y%m%d}"
                           f"{option_type[0].upper()}{int(k*1000):08d}")
                    out.append(OptionContract(occ_symbol=occ, underlying=underlying.upper(),
                                              option_type=option_type, strike=float(k), expiry=exp))
                k += self._strike_step
        return out[:limit]


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def cfg():
    c = Config()
    c.execution.dry_run = False
    c.execution.entry_order_type = "limit"
    c.execution.entry_order_timeout_seconds = 30
    return c


async def _instant_sleep(_seconds):  # used to skip real waiting in poll loops
    return None
