"""trader_core — broker-agnostic options execution core.

The reusable "hands" lifted from lambos-trader and generalized: an abstract
Broker, position sizing, pre-trade risk, an entry executor, and a swing-aware
exit manager — all driven by a source-agnostic TradeIntent and a Store port.

Designed to be extracted into a standalone installable later so both
ai-trading-bot and lambos-trader import the same code. The Alpaca broker is
NOT imported here so the package works without alpaca-py installed; import it
explicitly: `from trader_core.broker.alpaca_client import AlpacaBroker`.
"""

from __future__ import annotations

from .config import Config
from .execution.intent import LONG_CALL, LONG_PUT, TradeIntent
from .ports import Store

__all__ = ["Config", "TradeIntent", "LONG_CALL", "LONG_PUT", "Store"]
