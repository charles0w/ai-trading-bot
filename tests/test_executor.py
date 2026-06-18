from __future__ import annotations

import asyncio
from datetime import date

import pytest

from trader_core.broker.base import OptionContract
from trader_core.execution.executor import execute_entry, make_client_order_id
from trader_core.execution.intent import LONG_CALL, TradeIntent
from trader_core.execution.sizing import SizingDecision

from conftest import FakeBroker, InMemoryStore


async def _instant(_s):
    return None


def _intent():
    return TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=35,
                       strike_rule="ATM", signal_id="2026-06-16-NVDA", price_ref=2.50)


def _contract():
    return OptionContract(occ_symbol="NVDA260718C00200000", underlying="NVDA",
                          option_type="call", strike=200.0, expiry=date(2026, 7, 18),
                          bid=2.45, ask=2.55)


def _sizing():
    return SizingDecision(contracts=1, cost_usd=250.0, reason="ok")


def test_client_order_id_is_deterministic():
    a = make_client_order_id("sig1", "NVDA260718C00200000", "buy")
    b = make_client_order_id("sig1", "NVDA260718C00200000", "buy")
    c = make_client_order_id("sig2", "NVDA260718C00200000", "buy")
    assert a == b and a != c and a.startswith("atb-")


def test_dry_run_logs_order_no_position(cfg, store):
    cfg.execution.dry_run = True
    pos_id = asyncio.run(execute_entry(
        store=store, broker=FakeBroker(), cfg=cfg, intent=_intent(),
        sizing=_sizing(), contract=_contract(), sleep=_instant,
    ))
    assert pos_id is None
    assert len(store.orders) == 1
    assert next(iter(store.orders.values()))["status"] == "dry_run"
    assert not store.positions


def test_immediate_fill_opens_position(cfg, store):
    broker = FakeBroker(fill_sequence=("filled",), avg_fill_price=2.55)
    pos_id = asyncio.run(execute_entry(
        store=store, broker=broker, cfg=cfg, intent=_intent(),
        sizing=_sizing(), contract=_contract(), sleep=_instant,
    ))
    assert pos_id is not None
    pos = store.positions[pos_id]
    assert pos["occ_symbol"] == "NVDA260718C00200000"
    assert pos["entry_price"] == 2.55 and pos["quantity"] == 1
    assert len(broker.placed) == 1 and broker.placed[0]["side"] == "buy"


def test_poll_until_filled(cfg, store):
    broker = FakeBroker(fill_sequence=("pending", "pending", "filled"), avg_fill_price=2.60)
    pos_id = asyncio.run(execute_entry(
        store=store, broker=broker, cfg=cfg, intent=_intent(),
        sizing=_sizing(), contract=_contract(), sleep=_instant,
    ))
    assert pos_id is not None
    assert store.positions[pos_id]["entry_price"] == 2.60


def test_timeout_cancels(cfg, store):
    cfg.execution.entry_order_timeout_seconds = -1   # deadline already past
    broker = FakeBroker(fill_sequence=("pending",))
    pos_id = asyncio.run(execute_entry(
        store=store, broker=broker, cfg=cfg, intent=_intent(),
        sizing=_sizing(), contract=_contract(), sleep=_instant,
    ))
    assert pos_id is None
    assert broker.canceled == ["ord-1"]
    assert next(iter(store.orders.values()))["status"] == "canceled"


def test_no_price_reference_rejects(cfg, store):
    intent = TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=35,
                         strike_rule="ATM", signal_id="s1", price_ref=None)
    contract = OptionContract(occ_symbol="X", underlying="NVDA", option_type="call",
                              strike=200.0, expiry=date(2026, 7, 18))  # no bid/ask/last -> mid None
    pos_id = asyncio.run(execute_entry(
        store=store, broker=FakeBroker(), cfg=cfg, intent=intent,
        sizing=_sizing(), contract=contract, sleep=_instant,
    ))
    assert pos_id is None
    assert store.rejections == [("s1", "no_price_reference")]
