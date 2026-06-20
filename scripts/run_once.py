"""Run the brain once over a universe (live, on your Mac).

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    pip install alpaca-py yfinance anthropic python-dotenv
    # .env needs: ALPACA_API_KEY/SECRET, FINNHUB_API_KEY, ANTHROPIC_API_KEY
    python scripts/run_once.py                       # dry run over default universe
    python scripts/run_once.py --symbols NVDA,SPY    # specific names
    python scripts/run_once.py --execute             # place paper orders (market hours)

Dry run by default — logs predictions + prints decisions but places no orders.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.data.finnhub_provider import FinnhubProvider
from atb.data.yfinance_provider import YFinanceProvider
from atb.eval.predictions import PredictionLog
from atb.llm import anthropic_completion
from atb.pipeline import run_symbol
from atb.signal.llm_analyst import LLMAnalyst
from atb.signal.logistic import LogisticSignal
from atb.signal.pead_model import PeadHeuristicModel
from atb.store_sqlite import SQLiteStore
from trader_core.broker.alpaca_client import AlpacaBroker

MODEL_PATH = "data/model.json"


def _load_signal():
    if os.path.exists(MODEL_PATH):
        print(f"(using trained model: {MODEL_PATH})")
        return LogisticSignal.load(MODEL_PATH)
    print("(no trained model found — using heuristic v0; run scripts/train_model.py)")
    return PeadHeuristicModel()

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "SPY", "QQQ"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--execute", action="store_true", help="place paper orders (default: dry run)")
    args = ap.parse_args()

    key, secret = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    provider = FinnhubProvider(price_provider=YFinanceProvider())
    signal = _load_signal()
    analyst = LLMAnalyst(anthropic_completion())
    broker = AlpacaBroker(key, secret, paper=True)
    store = SQLiteStore("data/atb.db")
    predlog = PredictionLog("data/predictions.jsonl")

    print(f"{'SYMBOL':8} {'DECISION':10} REASON / DETAIL")
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        try:
            d = run_symbol(sym, provider=provider, signal=signal, analyst=analyst,
                           broker=broker, store=store, predlog=predlog, execute=args.execute)
            detail = d.reason
            if d.intent:
                detail += f"  {d.intent.direction} conv={d.intent.conviction:.2f}"
                if d.contract:
                    detail += f"  {d.contract.occ_symbol}"
            print(f"{sym:8} {d.decision:10} {detail}")
        except Exception as e:  # one bad symbol shouldn't kill the run
            print(f"{sym:8} {'error':10} {type(e).__name__}: {str(e)[:80]}")
            traceback.print_exc()  # full trace to stderr/log for pinpointing


if __name__ == "__main__":
    main()
