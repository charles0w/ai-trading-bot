"""Phase-0 paper smoke: TradeIntent -> resolve -> size -> execute, end-to-end,
against the live Alpaca PAPER account. Run on your Mac (the sandbox can't reach
Alpaca).

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    # safe preview (no order placed):
    python scripts/paper_smoke.py --underlying SPY --direction long_call --dte 35 --strike-rule ATM
    # actually place ONE paper order (during market hours for a fill):
    python scripts/paper_smoke.py --underlying SPY --execute

Defaults to a DRY RUN. Nothing is placed unless you pass --execute. Paper money
only — but this is the same code path that will later face real capital, so the
default is deliberately cautious.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date

# Make the repo root importable when run as `python scripts/paper_smoke.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from trader_core.broker.alpaca_client import AlpacaBroker
from trader_core.config import Config
from trader_core.execution.executor import execute_entry
from trader_core.execution.intent import TradeIntent
from trader_core.execution.resolver import resolve_contract
from trader_core.execution.sizing import size_position

from atb.store_sqlite import SQLiteStore


def get_spot(key: str, secret: str, symbol: str) -> float:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest
    client = StockHistoricalDataClient(key, secret)
    resp = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=[symbol]))
    return float(resp[symbol].price)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default="SPY")
    ap.add_argument("--direction", default="long_call", choices=["long_call", "long_put"])
    ap.add_argument("--dte", type=int, default=35)
    ap.add_argument("--strike-rule", default="ATM", help='ATM | OTM:5pct | ABS:600')
    ap.add_argument("--execute", action="store_true",
                    help="actually place the PAPER order (default: dry run, no order)")
    args = ap.parse_args()

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY (check .env).")

    broker = AlpacaBroker(key, secret, paper=True)
    store = SQLiteStore("data/atb.db")
    cfg = Config()
    cfg.execution.dry_run = not args.execute

    spot = get_spot(key, secret, args.underlying)
    print(f"Spot {args.underlying} = {spot:.2f}")

    sig_id = f"{date.today().isoformat()}-{args.underlying}-smoke"
    intent = TradeIntent(underlying=args.underlying, direction=args.direction,
                         target_dte=args.dte, strike_rule=args.strike_rule, signal_id=sig_id)
    store.record_signal(signal_id=sig_id, underlying=args.underlying,
                        direction=args.direction, meta={"source": "paper_smoke"})

    contract = resolve_contract(broker, intent, spot_price=spot)
    if contract is None:
        print("No contract resolved — try a different DTE/strike or check market hours.")
        return
    print(f"Resolved: {contract.occ_symbol}  strike={contract.strike}  "
          f"exp={contract.expiry}  mid={contract.mid}")

    premium = contract.mid or contract.last
    if premium is None:
        print("No live mark (market likely closed). Resolution works; "
              "re-run during market hours to size + fill.")
        return

    sz = size_position(
        premium_per_share=premium, sizing_mode=cfg.sizing.mode,
        max_per_trade_usd=cfg.trading_account.max_per_trade_usd,
        max_premium_per_contract=cfg.sizing.max_premium_per_contract,
        max_capital_usd=cfg.trading_account.max_capital_usd,
        current_open_exposure_usd=0,
        broker_buying_power_usd=broker.buying_power_usd(),
    )
    print(f"Sizing: {sz.contracts} contract(s)  cost≈${sz.cost_usd:.0f}  reason={sz.reason}")
    if sz.contracts == 0:
        print("Sizing rejected — adjust caps in Config (e.g. max_premium_per_contract).")
        return

    print("DRY RUN — no order placed." if cfg.execution.dry_run
          else "EXECUTING paper order...")
    pos_id = asyncio.run(execute_entry(store=store, broker=broker, cfg=cfg,
                                       intent=intent, sizing=sz, contract=contract))
    print("Opened position id:", pos_id)
    print("Open positions:", store.open_positions())


if __name__ == "__main__":
    main()
