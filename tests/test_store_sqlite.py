from __future__ import annotations

import asyncio
from datetime import date

from trader_core.broker.base import OptionContract
from trader_core.execution.executor import execute_entry
from trader_core.execution.intent import LONG_CALL, TradeIntent
from trader_core.execution.sizing import SizingDecision
from trader_core.ports import Store

from atb.store_sqlite import SQLiteStore
from conftest import FakeBroker


async def _instant(_s):
    return None


def test_satisfies_store_protocol():
    s = SQLiteStore(":memory:")
    assert isinstance(s, Store)


def test_order_and_position_lifecycle():
    s = SQLiteStore(":memory:")
    oid = s.insert_order(signal_id="s1", broker="fake", submitted_at_utc="t",
                         occ_symbol="NVDA260710C00200000", side="buy", quantity=1,
                         order_type="limit", status="pending", filled_qty=0)
    assert isinstance(oid, int)
    s.update_order(oid, status="filled", filled_qty=1, avg_fill_price=4.05)

    pid = s.open_position(open_order_id=oid, occ_symbol="NVDA260710C00200000",
                          quantity=1, entry_price=4.05, entry_at_utc="t")
    assert len(s.open_positions()) == 1
    s.update_position_mark(pid, 5.00)
    s.mark_position_closed(pid)
    assert s.open_positions() == []


def test_signal_rejection_recorded():
    s = SQLiteStore(":memory:")
    s.mark_signal_rejected("s9", "no_price_reference")
    row = s.conn.execute("SELECT status, reason FROM signals WHERE signal_id='s9'").fetchone()
    assert row["status"] == "rejected" and row["reason"] == "no_price_reference"


def test_executor_against_real_store(cfg):
    """The real SQLite store works with the generic executor end-to-end."""
    s = SQLiteStore(":memory:")
    broker = FakeBroker(fill_sequence=("filled",), avg_fill_price=4.05)
    intent = TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=35,
                         strike_rule="ATM", signal_id="s1", price_ref=4.00)
    contract = OptionContract(occ_symbol="NVDA260710C00200000", underlying="NVDA",
                              option_type="call", strike=200.0, expiry=date(2026, 7, 10),
                              bid=4.00, ask=4.10)
    pos_id = asyncio.run(execute_entry(
        store=s, broker=broker, cfg=cfg, intent=intent,
        sizing=SizingDecision(1, 405.0, "ok"), contract=contract, sleep=_instant,
    ))
    assert pos_id is not None
    assert len(s.open_positions()) == 1
