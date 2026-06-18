"""Alpaca paper trading broker.

Uses alpaca-py. Options trading must be enabled on the paper account
(Account Settings -> Options Trading). Long calls/puts require options
**Level 2** on Alpaca (Level 1 is only covered calls / cash-secured puts);
that Level-2 long-premium surface is what this system trades.

Notes:
  - Alpaca uses OCC-style symbols: SPY240517C00580000
    (root + YYMMDD + C/P + strike*1000, zero-padded to 8 digits)
  - For paper accounts the base URL is automatically chosen by alpaca-py
    when paper=True.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from .base import Broker, OptionContract, OrderResult, PositionSnapshot

if TYPE_CHECKING:
    from alpaca.trading.client import TradingClient  # noqa: F401

log = logging.getLogger(__name__)


def make_occ_symbol(underlying: str, expiry: date, option_type: str, strike: float) -> str:
    """Build an OCC option symbol. e.g. SPY240517C00580000."""
    ot = "C" if option_type.lower().startswith("c") else "P"
    strike_int = int(round(strike * 1000))
    return f"{underlying.upper()}{expiry.strftime('%y%m%d')}{ot}{strike_int:08d}"


class AlpacaBroker(Broker):
    name = "alpaca_paper"

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical.option import OptionHistoricalDataClient
            from alpaca.trading.requests import GetOptionContractsRequest
        except ImportError as e:
            raise RuntimeError(
                "alpaca-py is not installed. `pip install alpaca-py`"
            ) from e

        self._trading = TradingClient(api_key, api_secret, paper=paper)
        self._option_data = OptionHistoricalDataClient(api_key, api_secret)
        self._GetOptionContractsRequest = GetOptionContractsRequest

    # --- account --------------------------------------------------------

    def buying_power_usd(self) -> float:
        acct = self._trading.get_account()
        # Options BP is typically tracked separately on real accounts;
        # for paper Alpaca returns regular cash bp.
        return float(acct.options_buying_power or acct.buying_power or 0)

    # --- contracts ------------------------------------------------------

    def find_option_contract(
        self, underlying: str, expiry: date, strike: float, option_type: str
    ) -> OptionContract | None:
        from alpaca.trading.enums import AssetStatus, ContractType

        req = self._GetOptionContractsRequest(
            underlying_symbols=[underlying.upper()],
            expiration_date=expiry,
            strike_price_gte=str(strike - 0.01),
            strike_price_lte=str(strike + 0.01),
            type=ContractType.CALL if option_type == "call" else ContractType.PUT,
            status=AssetStatus.ACTIVE,
            limit=10,
        )
        try:
            resp = self._trading.get_option_contracts(req)
        except Exception:
            log.exception("get_option_contracts failed")
            return None

        contracts = getattr(resp, "option_contracts", []) or []
        if not contracts:
            log.warning("No contract found for %s %s %s %s",
                        underlying, expiry, strike, option_type)
            return None

        # exact strike match if available
        exact = [c for c in contracts if float(c.strike_price) == strike]
        chosen = exact[0] if exact else contracts[0]

        mark = self.get_option_mark(chosen.symbol)
        return OptionContract(
            occ_symbol=chosen.symbol,
            underlying=underlying.upper(),
            option_type=option_type,
            strike=float(chosen.strike_price),
            expiry=expiry,
            last=mark,
            bid=mark,
            ask=mark,
        )

    def list_option_contracts(
        self, underlying, *, expiration_gte, expiration_lte, option_type,
        strike_gte=None, strike_lte=None, limit=200,
    ):
        from alpaca.trading.enums import AssetStatus, ContractType
        kwargs = dict(
            underlying_symbols=[underlying.upper()],
            expiration_date_gte=expiration_gte,
            expiration_date_lte=expiration_lte,
            type=ContractType.CALL if option_type == "call" else ContractType.PUT,
            status=AssetStatus.ACTIVE,
            limit=limit,
        )
        if strike_gte is not None:
            kwargs["strike_price_gte"] = str(strike_gte)
        if strike_lte is not None:
            kwargs["strike_price_lte"] = str(strike_lte)
        try:
            resp = self._trading.get_option_contracts(self._GetOptionContractsRequest(**kwargs))
        except Exception:
            log.exception("list_option_contracts failed")
            return []
        out = []
        for c in (getattr(resp, "option_contracts", []) or []):
            exp = c.expiration_date
            if isinstance(exp, str):
                exp = date.fromisoformat(exp)
            out.append(OptionContract(
                occ_symbol=c.symbol, underlying=underlying.upper(),
                option_type=option_type, strike=float(c.strike_price), expiry=exp,
            ))
        return out

    def get_option_mark(self, occ_symbol: str) -> float | None:
        try:
            from alpaca.data.requests import OptionLatestQuoteRequest
            req = OptionLatestQuoteRequest(symbol_or_symbols=[occ_symbol])
            resp = self._option_data.get_option_latest_quote(req)
            q = resp.get(occ_symbol)
            if q and q.bid_price and q.ask_price:
                return (float(q.bid_price) + float(q.ask_price)) / 2
            if q and q.ask_price:
                return float(q.ask_price)
        except Exception:
            log.exception("get_option_mark failed for %s", occ_symbol)
        return None

    # --- orders ---------------------------------------------------------

    def place_order(
        self,
        contract: OptionContract,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        time_in_force: str = "day",
    ) -> OrderResult:
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
        tif = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "opg": TimeInForce.OPG,
        }.get(time_in_force.lower(), TimeInForce.DAY)

        if order_type == "limit":
            if limit_price is None:
                raise ValueError("limit_price required for limit order")
            req = LimitOrderRequest(
                symbol=contract.occ_symbol,
                qty=quantity,
                side=side_enum,
                time_in_force=tif,
                limit_price=round(limit_price, 2),
            )
        else:
            req = MarketOrderRequest(
                symbol=contract.occ_symbol,
                qty=quantity,
                side=side_enum,
                time_in_force=tif,
            )

        order = self._trading.submit_order(req)
        return OrderResult(
            broker_order_id=str(order.id),
            status=str(order.status).lower(),
            filled_qty=int(order.filled_qty or 0),
            avg_fill_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            raw={"alpaca_order_id": str(order.id)},
        )

    def get_order(self, broker_order_id: str) -> OrderResult:
        order = self._trading.get_order_by_id(broker_order_id)
        return OrderResult(
            broker_order_id=str(order.id),
            status=str(order.status).lower(),
            filled_qty=int(order.filled_qty or 0),
            avg_fill_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            raw={"status": str(order.status)},
        )

    def cancel_order(self, broker_order_id: str) -> None:
        try:
            self._trading.cancel_order_by_id(broker_order_id)
        except Exception:
            log.exception("cancel_order failed for %s", broker_order_id)

    def get_position(self, occ_symbol: str) -> PositionSnapshot | None:
        try:
            pos = self._trading.get_open_position(occ_symbol)
        except Exception:
            return None
        return PositionSnapshot(
            occ_symbol=occ_symbol,
            quantity=int(pos.qty),
            entry_price=float(pos.avg_entry_price),
            mark_price=float(pos.current_price) if pos.current_price else None,
        )
