from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from trader_core.execution.exit_manager import ExitManager, PT

from conftest import FakeBroker, InMemoryStore


def _em(cfg, broker=None, store=None):
    return ExitManager(store or InMemoryStore(), broker or FakeBroker(), cfg)


def _pos(entry_price=2.00, entry_at_utc=None):
    return dict(id=1, open_order_id=1, occ_symbol="NVDA260718C00200000",
                quantity=1, entry_price=entry_price,
                entry_at_utc=entry_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"))


NOW_PT = datetime(2026, 6, 16, 9, 0, tzinfo=PT)
NOW_UTC = datetime.now(timezone.utc)


def test_take_profit(cfg):
    em = _em(cfg)
    # +55% vs tp 50
    assert em.evaluate(_pos(2.00), 3.10, now_pt=NOW_PT, now_utc=NOW_UTC) == "take_profit"


def test_stop_loss(cfg):
    em = _em(cfg)
    # -35% vs sl -30
    assert em.evaluate(_pos(2.00), 1.30, now_pt=NOW_PT, now_utc=NOW_UTC) == "stop_loss"


def test_max_hold(cfg):
    em = _em(cfg)  # max_hold_days default 25
    old = (NOW_UTC - timedelta(days=26)).isoformat(timespec="seconds")
    assert em.evaluate(_pos(2.00, old), 2.00, now_pt=NOW_PT, now_utc=NOW_UTC) == "max_hold"


def test_hold_when_nothing_triggers(cfg):
    em = _em(cfg)
    recent = (NOW_UTC - timedelta(days=1)).isoformat(timespec="seconds")
    assert em.evaluate(_pos(2.00, recent), 2.05, now_pt=NOW_PT, now_utc=NOW_UTC) is None


def test_eod_only_when_enabled(cfg):
    recent = (NOW_UTC - timedelta(days=1)).isoformat(timespec="seconds")
    after_close = datetime(2026, 6, 16, 13, 0, tzinfo=PT)  # past 12:55
    em = _em(cfg)
    assert em.evaluate(_pos(2.00, recent), 2.00, now_pt=after_close, now_utc=NOW_UTC) is None
    cfg.exits.eod_close_enabled = True
    assert em.evaluate(_pos(2.00, recent), 2.00, now_pt=after_close, now_utc=NOW_UTC) == "eod"


def test_tick_closes_position_on_tp_dry_run(cfg):
    cfg.execution.dry_run = True
    store = InMemoryStore()
    oid = store.insert_order(signal_id="s1", broker="fake", submitted_at_utc="t",
                             occ_symbol="NVDA260718C00200000", side="buy", quantity=1,
                             order_type="limit", status="filled", filled_qty=1,
                             avg_fill_price=2.00)
    pid = store.open_position(open_order_id=oid, occ_symbol="NVDA260718C00200000",
                             quantity=1, entry_price=2.00,
                             entry_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    broker = FakeBroker(mark=3.10)  # +55% -> take_profit
    em = ExitManager(store, broker, cfg)
    asyncio.run(em._tick())
    assert store.positions[pid]["closed"] is True
    assert store.orders[oid]["exit_reason"] == "take_profit"
