"""Find liquid optionable names that JUST reported earnings (the PEAD window)
and show their features. These are the symbols worth running the brain on today.

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    python scripts/scan.py                 # last 6 days of reporters in the liquid set
    python scripts/scan.py --days 5
    # then act on the candidates it prints:
    python scripts/run_once.py --symbols <list>
"""

from __future__ import annotations

import argparse
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
from atb.features import compute_features

from atb.universe import LIQUID


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="window size (days)")
    ap.add_argument("--upcoming", action="store_true",
                    help="list liquid names reporting in the NEXT --days days")
    args = ap.parse_args()

    today = date.today()
    provider = FinnhubProvider(price_provider=YFinanceProvider())

    if args.upcoming:
        cal = provider.earnings_calendar(today, today + timedelta(days=args.days))
        up = sorted([it for it in cal if it.get("symbol") in LIQUID and it.get("date")],
                    key=lambda it: it["date"])
        if not up:
            print(f"No liquid names reporting in the next {args.days} days.")
            return
        print(f"Liquid names reporting in the next {args.days} days: {len(up)}\n")
        print(f"{'SYM':6} {'DATE':12} {'WHEN':5} EPS est")
        for it in up:
            when = {"bmo": "BMO", "amc": "AMC", "dmh": "DMH"}.get(it.get("hour", ""), it.get("hour") or "—")
            est = it.get("epsEstimate")
            est = f"{est:.2f}" if isinstance(est, (int, float)) else "—"
            print(f"{it['symbol']:6} {it['date']:12} {when:5} {est}")
        print("\nThese become tradeable 1-2 days AFTER they report (post-IV-crush window).")
        return

    cal = provider.earnings_calendar(today - timedelta(days=args.days), today)
    reported = sorted({it["symbol"] for it in cal
                       if it.get("symbol") in LIQUID and it.get("epsActual") is not None})
    if not reported:
        print(f"No liquid names reported in the last {args.days} days.")
        return

    print(f"Liquid names that reported in the last {args.days} days: {len(reported)}\n")
    print(f"{'SYM':6} {'d_since':>7} {'SUE':>7} {'drift%':>7} {'mom12_1':>8}  window")
    in_window = []
    for sym in reported:
        try:
            fv = compute_features(provider, sym, asof=today)
        except Exception as e:
            print(f"{sym:6} error {type(e).__name__}")
            continue
        d = fv.days_since_earnings
        flag = "<-- PEAD" if (d is not None and 1 <= d <= 5) else ""
        if flag:
            in_window.append(sym)
        sue = f"{fv.sue:.2f}" if fv.sue is not None else "  -"
        drift = f"{fv.post_earnings_return*100:.1f}" if fv.post_earnings_return is not None else "  -"
        mom = f"{fv.mom_12_1:.2f}" if fv.mom_12_1 is not None else "   -"
        print(f"{sym:6} {str(d):>7} {sue:>7} {drift:>7} {mom:>8}  {flag}")

    print()
    if in_window:
        print("In the PEAD window now. Run the brain on them:")
        print(f"  python scripts/run_once.py --symbols {','.join(in_window)}")
    else:
        print("None currently in the 1-5 day post-earnings window. Check back after "
              "the next earnings cluster (or widen the model's entry_window).")


if __name__ == "__main__":
    main()
