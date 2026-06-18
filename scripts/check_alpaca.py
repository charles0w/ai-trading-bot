"""Verify the Alpaca paper account: keys work, buying power, and whether
options Level 2 (long calls/puts) is live yet.

Run from the repo root on your Mac (NOT the sandbox — outbound to Alpaca is
blocked there):

    cd ~/Desktop/ai-trading-bot
    python3 -m venv .venv && source .venv/bin/activate
    pip install alpaca-py python-dotenv
    python scripts/check_alpaca.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # dotenv optional if vars are already exported

KEY = os.environ.get("ALPACA_API_KEY")
SECRET = os.environ.get("ALPACA_SECRET_KEY")
if not KEY or not SECRET:
    sys.exit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY (check your .env).")

from alpaca.trading.client import TradingClient

client = TradingClient(KEY, SECRET, paper=True)
acct = client.get_account()

print("=== Account ===")
print("status:           ", getattr(acct, "status", "?"))
print("cash:             ", getattr(acct, "cash", "?"))
print("buying_power:     ", getattr(acct, "buying_power", "?"))
print("options_bp:       ", getattr(acct, "options_buying_power", "n/a"))
print("options_level:    ", getattr(acct, "options_trading_level", "n/a"),
      "(approved:", getattr(acct, "options_approved_level", "n/a"), ")")

print("\n=== Options Level 2 check (resolve a near-dated SPY call) ===")
try:
    from alpaca.trading.requests import GetOptionContractsRequest
    expiry = date.today() + timedelta(days=35)
    req = GetOptionContractsRequest(
        underlying_symbols=["SPY"],
        expiration_date_gte=date.today() + timedelta(days=20),
        expiration_date_lte=expiry + timedelta(days=20),
        type="call",
        limit=1,
    )
    contracts = client.get_option_contracts(req)
    items = getattr(contracts, "option_contracts", contracts)
    if items:
        c = items[0]
        print("OK — sample contract:", getattr(c, "symbol", c))
        print("\nLevel 2 looks active. You're ready for the Phase-0 paper smoke.")
    else:
        print("Query worked but returned no contracts (try a different expiry).")
except Exception as e:
    print("Could not pull option contracts:", type(e).__name__, str(e)[:200])
    print("\nIf this is a permissions error, options Level 2 isn't approved yet —")
    print("check Account -> options level in the dashboard; paper usually clears soon.")
