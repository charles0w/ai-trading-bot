"""Print the PEAD feature vector (and whether the naive baseline would fire)
for a symbol, using Finnhub earnings + yfinance prices.

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    pip install yfinance        # if not already
    # add FINNHUB_API_KEY to .env (free at finnhub.io)
    python scripts/show_features.py NVDA
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.data.finnhub_provider import FinnhubProvider
from atb.data.yfinance_provider import YFinanceProvider
from atb.features import compute_features, pead_baseline_intent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    args = ap.parse_args()

    # Finnhub for earnings/SUE, yfinance for prices/options
    provider = FinnhubProvider(price_provider=YFinanceProvider())
    fv = compute_features(provider, args.symbol.upper())

    print(f"=== Features: {fv.symbol} @ {fv.asof} ===")
    for k, v in asdict(fv).items():
        if k in ("symbol", "asof"):
            continue
        if isinstance(v, float):
            print(f"  {k:22} {v:.4f}")
        else:
            print(f"  {k:22} {v}")

    intent = pead_baseline_intent(fv)
    print("\n=== Naive baseline intent (placeholder for ML+LLM) ===")
    if intent is None:
        print("  No trade — outside the post-earnings window or no drift signal.")
    else:
        print(f"  {intent.direction} {intent.underlying}  {intent.strike_rule} "
              f"~{intent.target_dte}DTE  conviction={intent.conviction:.2f}")
        print(f"  meta: {intent.meta}")


if __name__ == "__main__":
    main()
