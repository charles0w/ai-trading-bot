"""
See the REAL Anthropic judge score a recap today — no recap pipeline needed.

Setup (PowerShell), from a folder that also has the UPDATED ceo_report.py
(apply eval-judge-anthropic.patch to ceos-enterprise first, then copy
reporter/ceo_report.py here):

    $env:ANTHROPIC_API_KEY = "<your anthropic key>"
    # optional, to also post the score to the live dashboard:
    $env:CEOS_REPORT_SECRET = "<REPORT_SECRET from Vercel>"

Run:
    python judge_demo.py                  # judge the built-in sample, print score
    python judge_demo.py my_recap.txt     # judge a file's contents
    python judge_demo.py my_recap.txt --report   # also post the score to the dashboard
"""
import sys
from ceo_report import judge, track_reliability, report

# Same rubric as research/ai-evals/criteria/finance-eod-recap.md
CRITERIA = """\
Grade this end-of-day options/markets recap on:
1. Faithfulness — every number (prices, %, P/L, tickers) is supported by the
   day's actual market data. Penalize ANY invented or unverifiable figure hard.
2. Completeness — covers the day's key movers, the portfolio's positions and
   P/L, and any triggered watch-list levels. Missing a held position is a major gap.
3. Calibration — claims are appropriately hedged; no overconfident directional
   calls stated as fact. Reward reasoning, penalize hype.
4. Actionability — a reader could act on it: clear next-day levels or flags.
Score 1.0 only if all four hold. Drop fast for hallucinated numbers.
"""

SAMPLE = (
    "EOD recap — 2026-06-04. SPX closed +0.6% at 6,012; NVDA +2.3% into the "
    "close on heavy call flow. Portfolio day P/L +1.8%; held NVDA 6/20 1100C "
    "(+14%) and SPY puts (-5%). Watch level: NVDA 1180 resistance tomorrow; "
    "trim if it gaps above on weak breadth. No earnings in the book this week."
)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_report = "--report" in sys.argv
    text = open(args[0], encoding="utf-8").read() if args else SAMPLE

    ev = judge(text, CRITERIA)
    print(f"\nscore   : {ev['score']}")
    print(f"summary : {ev['summary']}\n")

    if ev["score"] is None:
        print("Judge not configured — set ANTHROPIC_API_KEY and use the updated ceo_report.py.")
        return
    if do_report:
        rel = track_reliability("finance", passed=ev["score"] >= 0.7)
        ok = report(
            "finance", ok=True, summary="judge demo — real Anthropic score",
            eval_score=ev["score"], eval_reliability=rel, eval_summary=ev["summary"],
        )
        print(f"reported to dashboard: {'OK' if ok else 'FAILED (set CEOS_REPORT_SECRET?)'}")


if __name__ == "__main__":
    main()
