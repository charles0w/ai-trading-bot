"""Entry-order orchestration (generalized from lambos).

Same crash-safe place -> poll-to-fill -> open-position machinery, but the
input is a source-agnostic TradeIntent (+ signal_id) instead of a
copy-trade ParsedAlert, and persistence goes through the Store port.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from ..broker.base import Broker, OptionContract
from ..config import Config
from ..ports import Store
from .intent import TradeIntent
from .sizing import SizingDecision

log = logging.getLogger(__name__)


def make_client_order_id(signal_id: str, occ_symbol: str, side: str) -> str:
    """Deterministic ID so a crash-and-restart can't double-submit."""
    raw = f"{signal_id}|{occ_symbol}|{side}"
    return "atb-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def execute_entry(
    *,
    store: Store,
    broker: Broker,
    cfg: Config,
    intent: TradeIntent,
    sizing: SizingDecision,
    contract: OptionContract,
    sleep=asyncio.sleep,
) -> int | None:
    """Place the entry for `intent`. Returns the opened position id, or None
    (dry-run, rejected, no fill, or timeout). `sleep` is injectable for tests."""
    cost_basis = contract.mid or intent.price_ref
    if cost_basis is None:
        log.warning("No price reference for %s; skipping", contract.occ_symbol)
        store.mark_signal_rejected(intent.signal_id, "no_price_reference")
        return None

    if cfg.execution.entry_order_type == "limit":
        limit_price = round(cost_basis * (1 + cfg.execution.limit_offset_pct / 100), 2)
    else:
        limit_price = None

    client_oid = make_client_order_id(intent.signal_id, contract.occ_symbol, "buy")
    submitted_at = _utc_now_iso()

    if cfg.execution.dry_run:
        log.info("DRY RUN — would buy %d x %s @ %s [client_oid=%s]",
                 sizing.contracts, contract.occ_symbol, limit_price or "MKT", client_oid)
        store.insert_order(
            signal_id=intent.signal_id,
            broker=broker.name,
            broker_order_id=None,
            client_order_id=client_oid,
            submitted_at_utc=submitted_at,
            occ_symbol=contract.occ_symbol,
            side="buy",
            quantity=sizing.contracts,
            order_type=cfg.execution.entry_order_type,
            limit_price=limit_price,
            status="dry_run",
            filled_qty=0,
        )
        return None

    result = broker.place_order(
        contract=contract,
        side="buy",
        quantity=sizing.contracts,
        order_type=cfg.execution.entry_order_type,
        limit_price=limit_price,
    )

    order_id = store.insert_order(
        signal_id=intent.signal_id,
        broker=broker.name,
        broker_order_id=result.broker_order_id,
        client_order_id=client_oid,
        submitted_at_utc=submitted_at,
        occ_symbol=contract.occ_symbol,
        side="buy",
        quantity=sizing.contracts,
        order_type=cfg.execution.entry_order_type,
        limit_price=limit_price,
        status=result.status,
        filled_qty=result.filled_qty,
        avg_fill_price=result.avg_fill_price,
    )

    # Poll for fill
    deadline = asyncio.get_event_loop().time() + cfg.execution.entry_order_timeout_seconds
    while result.status not in ("filled", "canceled", "rejected"):
        await sleep(1)
        if asyncio.get_event_loop().time() > deadline:
            log.info("Entry order timeout, canceling %s", result.broker_order_id)
            broker.cancel_order(result.broker_order_id)
            store.update_order(order_id, status="canceled")
            return None
        result = broker.get_order(result.broker_order_id)
        store.update_order(
            order_id,
            status=result.status,
            filled_qty=result.filled_qty,
            avg_fill_price=result.avg_fill_price,
        )

    if result.status != "filled":
        return None

    position_id = store.open_position(
        open_order_id=order_id,
        occ_symbol=contract.occ_symbol,
        quantity=result.filled_qty,
        entry_price=result.avg_fill_price or 0.0,
        entry_at_utc=submitted_at,
    )
    log.info("Position opened: %s qty=%d entry=$%.2f",
             contract.occ_symbol, result.filled_qty, result.avg_fill_price or 0)
    return position_id
