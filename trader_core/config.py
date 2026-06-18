"""Self-contained config dataclasses for trader_core.

Deliberately decoupled from any single app's config system (lambos uses
pydantic + YAML; ai-trading-bot can build whatever it likes) — both just
need to hand trader_core an object with these attributes. Defaults are
SWING-trading defaults (no EOD close, time-stop on, liquidity filter on).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradingAccountCfg:
    max_capital_usd: float = 100_000
    max_per_trade_usd: float = 5_000
    max_open_positions: int = 50
    daily_loss_kill_switch_usd: float = -10_000


@dataclass
class SizingCfg:
    mode: str = "one_contract"            # "fixed_dollar" | "one_contract"
    max_premium_per_contract: float = 50.0


@dataclass
class ExitsCfg:
    take_profit_pct: float = 50
    stop_loss_pct: float = -30
    poll_interval_seconds: int = 15
    # Swing defaults differ from lambos (a day-trader): do NOT close at EOD,
    # use a calendar time-stop instead.
    eod_close_enabled: bool = False
    eod_close_time_pt: str = "12:55"
    max_hold_days: int | None = 25


@dataclass
class MarketCfg:
    trading_window_start_pt: str = "06:30"
    trading_window_end_pt: str = "12:55"
    # Don't act on a signal older than ~1 trading day (swing, not live-alert).
    max_signal_age_seconds: float = 86_400
    # Liquidity filter (the non-negotiable rule from strategy-research):
    max_spread_pct: float | None = 15.0   # bid/ask spread as % of mid
    min_open_interest: int | None = 100


@dataclass
class ExecutionCfg:
    dry_run: bool = True
    entry_order_type: str = "limit"       # "market" | "limit"
    limit_offset_pct: float = 5
    entry_order_timeout_seconds: int = 30


@dataclass
class Config:
    trading_account: TradingAccountCfg = field(default_factory=TradingAccountCfg)
    sizing: SizingCfg = field(default_factory=SizingCfg)
    exits: ExitsCfg = field(default_factory=ExitsCfg)
    market: MarketCfg = field(default_factory=MarketCfg)
    execution: ExecutionCfg = field(default_factory=ExecutionCfg)
