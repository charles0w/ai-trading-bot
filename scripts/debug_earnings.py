"""Diagnose which earnings data source actually returns history for a symbol.

    python scripts/debug_earnings.py NVDA

Prints what each source yields so we can pick the working one instead of guessing.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.data.finnhub_provider import FinnhubProvider
from atb.data.yfinance_provider import YFinanceProvider

sym = (sys.argv[1] if len(sys.argv) > 1 else "NVDA").upper()
yp = YFinanceProvider()
fp = FinnhubProvider(price_provider=yp)

print(f"### Diagnosing earnings sources for {sym} ###\n")

print("[1] yfinance earnings_history():")
try:
    ev = yp.earnings_history(sym, years=3)
    print(f"    {len(ev)} events")
    for e in ev[:5]:
        print(f"      {e.day}  actual={e.eps_actual}  est={e.eps_estimate}")
except Exception as e:
    print("    ERROR", repr(e))

print("\n[2] raw yfinance get_earnings_dates(limit=24):")
try:
    import yfinance as yf
    df = yf.Ticker(sym).get_earnings_dates(limit=24)
    print(f"    rows: {0 if df is None else len(df)}; columns: {list(df.columns) if df is not None else '-'}")
    if df is not None and len(df):
        print(df.head(6).to_string())
except Exception as e:
    print("    ERROR", repr(e))

print("\n[3] Finnhub /stock/earnings (surprise series):")
try:
    rows = fp._fetch("/stock/earnings", {"symbol": sym}) or []
    print(f"    {len(rows)} rows; sample: {rows[:2]}")
except Exception as e:
    print("    ERROR", repr(e))

print("\n[4] Finnhub /calendar/earnings last 150 days:")
try:
    c = fp.earnings_calendar(date.today() - timedelta(days=150), date.today(), sym)
    print(f"    {len(c)} events; sample: {c[:2]}")
except Exception as e:
    print("    ERROR", repr(e))

print("\n[5] Finnhub /calendar/earnings 3y single call:")
try:
    c = fp.earnings_calendar(date.today() - timedelta(days=1095), date.today(), sym)
    print(f"    {len(c)} events")
except Exception as e:
    print("    ERROR", repr(e))

print("\n[6] Finnhub chunked 3y (what training now uses as fallback):")
try:
    ev = fp._finnhub_earnings_history(sym, years=3)
    print(f"    {len(ev)} events")
    for e in ev[:5]:
        print(f"      {e.day}  actual={e.eps_actual}  est={e.eps_estimate}")
except Exception as e:
    print("    ERROR", repr(e))
