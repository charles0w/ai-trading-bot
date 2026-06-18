"""Turn a TradeIntent's target_dte + strike_rule into a concrete, priced
OptionContract via the broker's chain search.

Supported strike rules:
  - "ATM"            -> strike nearest spot
  - "OTM:Npct"/"N%"  -> N% out-of-the-money (calls above spot, puts below)
  - "ITM:Npct"/"N%"  -> N% in-the-money
  - "ABS:123.5"      -> nearest listed strike to 123.5
  - "DELTA:0.55"     -> not yet supported (needs greeks); falls back to ATM

`spot_price` is supplied by the caller (data/feature layer) since the broker
interface doesn't expose an underlying quote.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ..broker.base import Broker, OptionContract
from .intent import TradeIntent

log = logging.getLogger(__name__)


def _parse_pct(token: str) -> float:
    return float(token.lower().replace("pct", "").replace("%", "").strip())


def target_strike(strike_rule: str, spot: float, option_type: str) -> float:
    rule = strike_rule.strip()
    head, _, tail = rule.partition(":")
    head = head.upper()
    if head == "ATM":
        return spot
    if head == "ABS":
        return float(tail)
    if head in ("OTM", "ITM"):
        pct = _parse_pct(tail) / 100.0
        # OTM call = above spot; OTM put = below spot. ITM is the inverse.
        up = (head == "OTM") == (option_type == "call")
        return spot * (1 + pct) if up else spot * (1 - pct)
    if head == "DELTA":
        log.warning("DELTA strike selection not yet supported; falling back to ATM")
        return spot
    raise ValueError(f"Unknown strike_rule: {strike_rule!r}")


def resolve_contract(
    broker: Broker,
    intent: TradeIntent,
    *,
    spot_price: float,
    today: date | None = None,
    expiry_window_days: int = 7,
    strike_band_pct: float = 0.08,
) -> OptionContract | None:
    """Pick the listed contract closest to (target_dte, target_strike) and
    return it priced. Returns None if the chain is empty."""
    today = today or date.today()
    target_exp = today + timedelta(days=intent.target_dte)
    lo_exp = max(today, target_exp - timedelta(days=expiry_window_days))
    hi_exp = target_exp + timedelta(days=expiry_window_days)

    # Center the strike search on the TARGET strike (not spot) and keep it tight,
    # so a strike-sorted, row-limited broker response isn't truncated before it
    # reaches our strike. (An ATM query ±20% of a $700 underlying overflows.)
    tgt_strike = target_strike(intent.strike_rule, spot_price, intent.option_type)
    band = tgt_strike * strike_band_pct
    chain = broker.list_option_contracts(
        intent.underlying,
        expiration_gte=lo_exp,
        expiration_lte=hi_exp,
        option_type=intent.option_type,
        strike_gte=round(tgt_strike - band, 2),
        strike_lte=round(tgt_strike + band, 2),
        limit=1000,
    )
    if not chain:
        log.warning("Empty chain for %s %s window %s..%s",
                    intent.underlying, intent.option_type, lo_exp, hi_exp)
        return None

    # nearest expiry to target, then nearest strike within that expiry
    best_exp = min({c.expiry for c in chain}, key=lambda e: abs((e - target_exp).days))
    candidates = [c for c in chain if c.expiry == best_exp]
    chosen = min(candidates, key=lambda c: abs(c.strike - tgt_strike))

    # fetch a priced contract (mark) for the chosen strike/expiry
    priced = broker.find_option_contract(
        intent.underlying, chosen.expiry, chosen.strike, intent.option_type
    )
    return priced or chosen
