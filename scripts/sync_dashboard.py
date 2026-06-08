"""
Local bridge + rigor layer for the ai-trading-bot eval loop.

WHY LOCAL: the Cowork scheduled task runs in a sandbox that blocks outbound HTTP
(yfinance and any judge API 403 there), so the cloud task does ANALYSIS -> VAULT
and this script does the network-dependent RIGOR from your machine:

  1. Backfill entry_ref with REAL closes via yfinance (the cloud recap infers some
     prices from leveraged-ETF proxies because FMP's quote endpoint is plan-gated;
     this replaces those with direct quotes so grading is honest).
  2. Re-judge the recap with a DIFFERENT model family (Gemini) — the cloud task
     self-judges (Claude grading Claude = self-preference bias). This cross-family
     score overrides the provisional self-judge before posting. (kb/judge-biases,
     kb/who-validates-the-validators.)
  3. Grade matured calls vs actual prices, compute rolling reliability, and post
     recap-quality + reliability to the dashboard.

Setup (once):
    pip install yfinance
    $env:REPORT_SECRET       = "<= REPORT_SECRET in Vercel>"
    # cross-family judge = Gemini via its OpenAI-compatible endpoint:
    $env:EVAL_JUDGE_PROVIDER = "openai"
    $env:EVAL_JUDGE_URL      = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    $env:EVAL_JUDGE_KEY      = "<your Gemini API key>"
    $env:EVAL_JUDGE_MODEL    = "gemini-2.0-flash"
    # NOTE: do NOT set ANTHROPIC_API_KEY here, or the judge would auto-pick Claude
    # (same family as the recap writer). Forcing provider=openai keeps it cross-family.

Run after the cloud task each weekday (or schedule via Windows Task Scheduler):
    python sync_dashboard.py

Keep this file next to ceo_report.py.
"""
import json
import os
import datetime
from pathlib import Path

from ceo_report import judge, report

JUDGE_LABEL = os.environ.get("EVAL_JUDGE_MODEL", "cross-family")

VAULT = Path(r"C:\Users\charl\Desktop\obi-secondbrain\repos\ai-trading-bot")
LEDGER = VAULT / "predictions.jsonl"
LATEST = VAULT / "latest-report.json"
RECAPS = VAULT / "recaps"
NOISE = 0.01     # 1% band: smaller moves count as flat, not a hit
WINDOW = 20      # rolling reliability window

# Same rubric as research/ai-evals/criteria/finance-eod-recap.md
FINANCE_CRITERIA = """\
Grade this end-of-day options/markets recap on:
1. Faithfulness — every number (prices, %, P/L, tickers) is supported by the day's
   actual market data. Penalize ANY invented or unverifiable figure hard.
2. Completeness — covers the day's key movers, positions/P&L, and triggered levels.
3. Calibration — claims appropriately hedged; no overconfident calls as fact.
4. Actionability — a reader could act on it: clear next-day levels or flags.
Score 1.0 only if all four hold. Drop fast for hallucinated numbers.
"""


def load_ledger():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]


def save_ledger(rows):
    LEDGER.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def close_on(ticker, date_str=None):
    """Real close via yfinance. If date_str given, the close on/just-before that date; else latest."""
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="3mo")
    if hist.empty:
        return None
    if date_str:
        hist = hist[hist.index.strftime("%Y-%m-%d") <= date_str]
        if hist.empty:
            return None
    return float(hist["Close"].iloc[-1])


def backfill_entries(rows):
    """Replace proxy-inferred / null entry_ref with the real close on the call date."""
    changed = False
    for r in rows:
        if r.get("status") != "open":
            continue
        if r.get("entry_ref_source") == "yfinance":
            continue  # already grounded
        px = close_on(r["ticker"], r["date"])
        if px is None:
            continue
        old = r.get("entry_ref")
        r["entry_ref"] = round(px, 2)
        r["entry_ref_source"] = "yfinance"
        changed = True
        print(f"entry  {r['id']}: {old} -> {px:.2f} (yfinance)")
    return changed


def grade(rows):
    today = datetime.date.today()
    changed = False
    for r in rows:
        if r.get("status") != "open":
            continue
        if (today - datetime.date.fromisoformat(r["date"])).days < r.get("horizon_days", 5):
            continue
        entry, px = r.get("entry_ref"), close_on(r["ticker"])
        if entry is None or px is None:
            print(f"skip   {r['id']}: no price/entry")
            continue
        ret = (px - entry) / entry
        d = r["direction"]
        correct = ret > NOISE if d == "up" else ret < -NOISE if d == "down" else abs(ret) <= NOISE
        r.update(status="graded", exit_ref=round(px, 2), return_pct=round(ret * 100, 2),
                 correct=bool(correct), graded_date=today.isoformat())
        changed = True
        print(f"grade  {r['id']}: {d} {entry} -> {px:.2f} ({ret*100:+.1f}%) {'HIT' if correct else 'MISS'}")
    return changed


def reliability(rows, k=WINDOW):
    graded = [r for r in rows if r.get("status") == "graded"][-k:]
    if len(graded) < 3:
        return None
    return round(sum(1 for r in graded if r.get("correct")) / len(graded), 4)


def latest_recap():
    """Return (date_str, recap_text) for the most recent recap, preferring latest-report.json's date."""
    date_str = None
    if LATEST.exists():
        try:
            date_str = json.loads(LATEST.read_text()).get("date")
        except Exception:
            pass
    f = (RECAPS / f"{date_str}.md") if date_str else None
    if not (f and f.exists()):
        mds = sorted(RECAPS.glob("*.md")) if RECAPS.exists() else []
        f = mds[-1] if mds else None
    return (f.stem, f.read_text()) if f else (None, None)


def cross_family_judge():
    """Re-judge the latest recap with a different model family (whatever EVAL_JUDGE_MODEL is). Returns dict or None."""
    _, text = latest_recap()
    if not text:
        return None
    ev = judge(text, FINANCE_CRITERIA)
    if ev.get("score") is None:
        print(f"cross-family judge unavailable: {ev.get('summary')}")
        return None
    print(f"cross-family judge ({JUDGE_LABEL}): {ev['score']} — {ev['summary']}")
    return ev


def main():
    rows = load_ledger()
    if backfill_entries(rows) | grade(rows):   # run both, save if either changed
        save_ledger(rows)
    rel = reliability(rows)

    # Prefer the cross-family score; fall back to the cloud self-judge only if it's unavailable.
    ev = cross_family_judge()
    latest = json.loads(LATEST.read_text()) if LATEST.exists() else {}
    if ev:
        score = ev["score"]
        summary_note = f"[cross-family judge: {JUDGE_LABEL}] " + ev["summary"]
    else:
        score = latest.get("evalScore")
        summary_note = "[self-judged, cross-family unavailable] " + latest.get("evalSummary", "")

    ok = report("finance", ok=True, summary=latest.get("summary", "EOD recap"),
                eval_score=score, eval_reliability=rel, eval_summary=summary_note)
    print(f"reliability={rel}  score={score}  posted={'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
