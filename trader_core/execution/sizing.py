"""Position sizing.

Given a configured trading-account cap and per-trade cap, compute how
many contracts to buy at a given premium. Always returns an integer in
[0, max_contracts]. Returns 0 when the trade should be skipped.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SizingDecision:
    contracts: int
    cost_usd: float
    reason: str         # "ok" | "premium_too_high" | "cap_exceeded" | "no_buying_power" | ...


def size_position(
    *,
    premium_per_share: float,        # e.g. 2.50 -> $250/contract
    sizing_mode: str,                # "fixed_dollar" | "one_contract"
    max_per_trade_usd: float,
    max_premium_per_contract: float,
    max_capital_usd: float,
    current_open_exposure_usd: float,
    broker_buying_power_usd: float,
) -> SizingDecision:
    if premium_per_share <= 0:
        return SizingDecision(0, 0.0, "premium_invalid")
    if premium_per_share > max_premium_per_contract:
        return SizingDecision(0, 0.0, "premium_too_high")

    cost_per_contract = premium_per_share * 100  # options multiplier

    headroom_capital = max_capital_usd - current_open_exposure_usd
    if headroom_capital <= 0:
        return SizingDecision(0, 0.0, "cap_exceeded")

    effective_per_trade = min(max_per_trade_usd, headroom_capital, broker_buying_power_usd)
    if effective_per_trade < cost_per_contract:
        return SizingDecision(0, 0.0, "no_buying_power")

    if sizing_mode == "one_contract":
        contracts = 1
    else:
        contracts = math.floor(effective_per_trade / cost_per_contract)

    cost = contracts * cost_per_contract
    return SizingDecision(contracts, cost, "ok")
