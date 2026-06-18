"""Grade matured predictions and print the reliability scorecard.

    cd ~/Desktop/ai-trading-bot && source .venv/bin/activate
    python scripts/grade.py

Grades the THESIS (direction vs realized underlying move). Option P&L net of
premium is tracked separately from paper fills — both feed the go-live gate.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.data.yfinance_provider import YFinanceProvider
from atb.eval.grading import grade_due
from atb.eval.reliability import summary
from atb.eval.predictions import PredictionLog


def main() -> None:
    predlog = PredictionLog("data/predictions.jsonl")
    provider = YFinanceProvider()
    graded = grade_due(predlog, lambda s: provider.latest_price(s), asof=date.today())
    print(f"Newly graded: {len(graded)} {graded}")
    print("Scorecard:")
    print(json.dumps(summary(predlog.load()), indent=2, default=str))


if __name__ == "__main__":
    main()
