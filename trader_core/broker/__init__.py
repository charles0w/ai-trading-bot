"""Broker interface. AlpacaBroker is intentionally NOT imported here so the
package stays importable without alpaca-py; do `from trader_core.broker.alpaca_client
import AlpacaBroker` when you need it."""

from __future__ import annotations

from .base import Broker, OptionContract, OrderResult, PositionSnapshot

__all__ = ["Broker", "OptionContract", "OrderResult", "PositionSnapshot"]
