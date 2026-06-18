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
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--horizon-days", type=int, default=5)
    ap.add_argument("--out", default="data/model.json")
    ap.add_argument("--min-rows", type=int, default=100,
                    help="refuse to save below this many rows (avoids overfit)")
    ap.add_argument("--force", action="store_true", help="save even below --min-rows")
    args = ap.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    provider = FinnhubProvider(price_provider=YFinanceProvider())

    print(f"Building dataset: {len(syms)} symbols x {args.years}y (earnings via yfinance) ...")
    rows = build_dataset(provider, syms, years=args.years,
                         horizon_days=args.horizon_days, verbose=True, pause=0.5)
    print(f"\nLabeled rows: {len(rows)}")
    if not rows:
        print("No rows — check network/keys.")
        return
    if len(rows) < args.min_rows and not args.force:
        print(f"REFUSING to save: only {len(rows)} rows (< --min-rows={args.min_rows}). "
              f"A model this small overfits. Widen --symbols/--years, or --force to override.\n"
              f"run_once will keep using the heuristic until a real model is saved.")
        return

    # Honest check: hold out 20% (seeded shuffle) and report OUT-OF-SAMPLE accuracy
    import random
    shuffled = rows[:]
    random.Random(42).shuffle(shuffled)
    cut = int(len(shuffled) * 0.8)
    train_rows, test_rows = shuffled[:cut], shuffled[cut:]
    holdout_model = train_logistic(train_rows)
    oos = accuracy(holdout_model, test_rows)
    print(f"Held-out accuracy: {oos:.3f} on {len(test_rows)} rows "
          f"(0.50 = no edge; THIS is the number that matters, not in-sample)")
    if oos is not None and oos < 0.53:
        print("  ^ at/near coin-flip — no real directional edge yet. Expected per the "
              "research; the paper trial net of costs is the real gate.")

    # Ship a model trained on ALL rows (standard once OOS is measured)
    model = train_logistic(rows)
    model.save(args.out)
    # Persist eval metadata into the model file so the dashboard can show it.
    import json as _json
    from datetime import date as _date
    _md = _json.load(open(args.out))
    _md["held_out_acc"] = round(oos, 4) if oos is not None else None
    _md["n_rows"] = len(rows)
    _md["trained_at"] = _date.today().isoformat()
    _json.dump(_md, open(args.out, "w"), indent=2)
    print(f"Trained on all {len(rows)} rows + saved -> {args.out}")
    print(f"In-sample accuracy: {accuracy(model, rows):.3f}  (optimistic; ignore vs held-out)")
    print("Weights:")
    for f, w in model.weights.items():
        print(f"  {f:22} {w:+.4f}")
    print(f"  {'bias':22} {model.bias:+.4f}")
    print("\nNote: in-sample accuracy overstates edge. The real test is the paper "
          "trial graded by scripts/grade.py, net of option costs.")


if __name__ == "__main__":
    main()
