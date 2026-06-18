"""Pre-trade risk checks (lifted from lambos; copy-trade 'alert age' -> 'signal age',
plus an options liquidity gate from the strategy research)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
PT = ZoneInfo("America/Los_Angeles")

PAUSE_FLAG = Path("data/paused.flag")


def is_paused() -> bool:
    """User-controlled pause. Drop a file at data/paused.flag to halt new
    entries (existing positions continue to be managed)."""
    return PAUSE_FLAG.exists()


# US equity market holidays. Update annually. NYSE closures only.
US_MARKET_HOLIDAYS: set[date] = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}


@dataclass
class RiskState:
    daily_realized_pnl_usd: float = 0.0
    kill_switch_engaged: bool = False

    def engage_kill_switch(self, reason: str) -> None:
        log.error("KILL SWITCH ENGAGED: %s", reason)
        self.kill_switch_engaged = True


def in_trading_window(now_pt: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    if now_pt.weekday() >= 5:
        return False
    if now_pt.date() in US_MARKET_HOLIDAYS:
        return False
    return time(sh, sm) <= now_pt.time() <= time(eh, em)


def passes_liquidity(*, spread_pct, open_interest, config_market) -> tuple[bool, str]:
    """Options liquidity gate. Wide spreads/thin OI are how paper edges die in
    real fills (see strategy-research-2026-06-16)."""
    if config_market.max_spread_pct is not None and spread_pct is not None:
        if spread_pct > config_market.max_spread_pct:
            return False, "spread_too_wide"
    if config_market.min_open_interest is not None and open_interest is not None:
        if open_interest < config_market.min_open_interest:
            return False, "open_interest_too_low"
    return True, "ok"


def approve(
    *,
    state: RiskState,
    now_pt: datetime,
    open_position_count: int,
    open_exposure_usd: float,
    config_trading_account,
    config_market,
    signal_age_seconds: float,
    spread_pct: float | None = None,
    open_interest: int | None = None,
) -> tuple[bool, str]:
    if state.kill_switch_engaged:
        return False, "kill_switch"
    if is_paused():
        return False, "paused_by_user"
    if state.daily_realized_pnl_usd <= config_trading_account.daily_loss_kill_switch_usd:
        state.engage_kill_switch(
            f"daily loss {state.daily_realized_pnl_usd:.2f} "
            f"<= {config_trading_account.daily_loss_kill_switch_usd}"
        )
        return False, "daily_loss_breach"
    if open_position_count >= config_trading_account.max_open_positions:
        return False, "max_open_positions"
    if open_exposure_usd >= config_trading_account.max_capital_usd:
        return False, "max_capital"
    if not in_trading_window(
        now_pt,
        config_market.trading_window_start_pt,
        config_market.trading_window_end_pt,
    ):
        return False, "outside_trading_window"
    if signal_age_seconds > config_market.max_signal_age_seconds:
        return False, "stale_signal"
    ok, why = passes_liquidity(
        spread_pct=spread_pct, open_interest=open_interest, config_market=config_market
    )
    if not ok:
        return False, why
    return True, "ok"
