"""Exit manager (generalized from lambos, extended for swing).

Reuses lambos's TP / SL / EOD poll loop, but:
  * EOD close is OFF by default (that's a day-trader default) and gated by
    cfg.exits.eod_close_enabled,
  * adds a calendar time-stop (cfg.exits.max_hold_days) for multi-week swings,
  * persists through the Store port instead of lambos's DB.

The exit DECISION is factored into a pure `evaluate()` for easy testing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from ..broker.base import Broker, OptionContract
from ..config import Config
from ..ports import Store

log = logging.getLogger(__name__)
PT = ZoneInfo("America/Los_Angeles")


def _parse_hhmm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


class ExitManager:
    def __init__(self, store: Store, broker: Broker, cfg: Config):
        self.store = store
        self.broker = broker
        self.cfg = cfg
        self._stopping = False

    def evaluate(self, position_row: dict, mark: float, *, now_pt: datetime,
                 now_utc: datetime) -> str | None:
        """Pure exit decision. Returns an exit reason or None."""
        entry = float(position_row["entry_price"])
        pnl_pct = (mark - entry) / entry * 100 if entry > 0 else 0.0

        if pnl_pct >= self.cfg.exits.take_profit_pct:
            return "take_profit"
        if pnl_pct <= self.cfg.exits.stop_loss_pct:
            return "stop_loss"

        if self.cfg.exits.max_hold_days is not None and position_row.get("entry_at_utc"):
            entry_dt = datetime.fromisoformat(position_row["entry_at_utc"])
            held_days = (now_utc - entry_dt).days
            if held_days >= self.cfg.exits.max_hold_days:
                return "max_hold"

        if self.cfg.exits.eod_close_enabled:
            eod = _parse_hhmm(self.cfg.exits.eod_close_time_pt)
            if now_pt.time() >= eod and now_pt.weekday() < 5:
                return "eod"

        return None

    async def run(self) -> None:
        log.info("Exit manager started.")
        while not self._stopping:
            try:
                await self._tick()
            except Exception:
                log.exception("exit manager tick failed")
            await asyncio.sleep(self.cfg.exits.poll_interval_seconds)

    def stop(self) -> None:
        self._stopping = True

    async def _tick(self) -> None:
        positions = self.store.open_positions()
        if not positions:
            return
        now_pt = datetime.now(PT)
        now_utc = datetime.now(timezone.utc)
        for p in positions:
            mark = self.broker.get_option_mark(p["occ_symbol"])
            if mark is None:
                log.warning("No mark for %s; skipping this tick", p["occ_symbol"])
                continue
            self.store.update_position_mark(p["id"], mark)
            reason = self.evaluate(p, mark, now_pt=now_pt, now_utc=now_utc)
            if reason:
                await self._close_position(p, mark, reason)

    async def _close_position(self, position_row: dict, mark: float, reason: str) -> None:
        log.info("Closing %s qty=%d entry=%.2f mark=%.2f reason=%s",
                 position_row["occ_symbol"], position_row["quantity"],
                 position_row["entry_price"], mark, reason)

        if self.cfg.execution.dry_run:
            self.store.update_order(position_row["open_order_id"], exit_reason=reason)
            self.store.mark_position_closed(position_row["id"])
            return

        contract = OptionContract(
            occ_symbol=position_row["occ_symbol"],
            underlying="", option_type="", strike=0,
            expiry=datetime.now().date(), bid=mark, ask=mark, last=mark,
        )
        is_limit = self.cfg.execution.entry_order_type == "limit"
        limit = round(mark * (1 - self.cfg.execution.limit_offset_pct / 100), 2) if is_limit else None
        result = self.broker.place_order(
            contract=contract, side="sell", quantity=int(position_row["quantity"]),
            order_type=self.cfg.execution.entry_order_type, limit_price=limit,
        )

        close_order_id = self.store.insert_order(
            parent_order_id=position_row["open_order_id"],
            broker=self.broker.name,
            broker_order_id=result.broker_order_id,
            submitted_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            occ_symbol=position_row["occ_symbol"], side="sell",
            quantity=int(position_row["quantity"]),
            order_type=self.cfg.execution.entry_order_type, limit_price=limit,
            status=result.status, filled_qty=result.filled_qty,
            avg_fill_price=result.avg_fill_price, exit_reason=reason,
        )

        for _ in range(30):
            await asyncio.sleep(1)
            r = self.broker.get_order(result.broker_order_id)
            self.store.update_order(close_order_id, status=r.status,
                                    filled_qty=r.filled_qty, avg_fill_price=r.avg_fill_price)
            if r.status in ("filled", "canceled", "rejected"):
                break

        self.store.mark_position_closed(position_row["id"])
