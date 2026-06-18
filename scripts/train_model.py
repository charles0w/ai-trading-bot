"""Train the PEAD logistic model on historical earnings + prices, save data/model.json.

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    python scripts/train_model.py                 # default universe, 2 years
    python scripts/train_model.py --years 3 --symbols AAPL,MSFT,NVDA,...

Needs FINNHUB_API_KEY (earnings) + network (yfinance prices). Heavy on Finnhub
calls (rate-limited free tier) — keep the universe modest or run off-hours.
After training, run_once.py automatically picks up data/model.json.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.data.finnhub_provider import FinnhubProvider
from atb.data.yfinance_provider import YFinanceProvider
from atb.train.dataset import build_dataset
from atb.train.trainer import accuracy, train_logistic

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "AMD", "NFLX",
    "CRM", "ORCL", "ADBE", "INTC", "QCOM", "MU", "JPM", "BAC", "GS", "V", "MA",
    "UNH", "LLY", "WMT", "COST", "HD", "NKE", "MCD", "DIS", "XOM", "CVX", "BA",
    "CAT", "PG", "KO", "PEP", "UBER", "SHOP", "PLTR", "MRVL", "PANW", "SNOW",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--horizon-days", type=int, default=5)
    ap.add_argument("--out", default="data/model.json")
    args = ap.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    provider = FinnhubProvider(price_provider=YFinanceProvider())

    print(f"Building dataset: {len(syms)} symbols x {args.years}y ...")
    rows = build_dataset(provider, syms, years=args.years, horizon_days=args.horizon_days)
    print(f"Labeled rows: {len(rows)}")
    if len(rows) < 50:
        print("WARNING: very few rows — model will be weak. Widen universe/years.")
    if not rows:
        return

    model = train_logistic(rows)
    model.save(args.out)
    print(f"Trained + saved -> {args.out}")
    print(f"In-sample accuracy: {accuracy(model, rows):.3f}  (in-sample is optimistic)")
    print("Weights:")
    for f, w in model.weights.items():
        print(f"  {f:22} {w:+.4f}")
    print(f"  {'bias':22} {model.bias:+.4f}")
    print("\nNote: in-sample accuracy overstates edge. The real test is the paper "
          "trial graded by scripts/grade.py, net of option costs.")


if __name__ == "__main__":
    main()
