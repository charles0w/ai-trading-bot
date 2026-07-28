"""Weekly eval — serverless scorecard + Claude-written verdict.

Runs Mondays in GitHub Actions (.github/workflows/weekly-eval.yml) after the
daily run has graded matured predictions. Reads the canonical
data/predictions.jsonl, computes the scorecard deterministically, asks Claude
for an honest narrative verdict, and writes evals/weekly-<date>.md +
evals/latest.md (committed back to main by the workflow).

Honesty rules are structural: the scorecard numbers are computed, never
generated; Claude only narrates them. NO DATA weeks say NO DATA. The script
always exits 0 — problems are reported inside the eval doc, not by failing
the workflow.

    python scripts/weekly_eval.py            # writes evals/weekly-YYYY-MM-DD.md
    python scripts/weekly_eval.py --no-llm   # scorecard only, skip the narrative
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRED = REPO / "data" / "predictions.jsonl"
OUT_DIR = REPO / "evals"
MODEL = "claude-sonnet-4-6"


def load_predictions() -> list[dict]:
    if not PRED.exists():
        return []
    rows = []
    for line in PRED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def conviction_label(r: dict) -> str:
    """Robust across schemas: legacy string convictions, normalized rows with
    meta.conviction_label, and the new pipeline's numeric convictions."""
    meta = r.get("meta") or {}
    if isinstance(meta.get("conviction_label"), str):
        return meta["conviction_label"]
    c = r.get("conviction")
    if isinstance(c, str):
        return c
    if isinstance(c, (int, float)):
        return "high" if c >= 0.7 else "medium" if c >= 0.45 else "low"
    return "unknown"


def scorecard(rows: list[dict]) -> dict:
    graded = [r for r in rows if r.get("status") == "graded"]
    open_ = [r for r in rows if r.get("status") == "open"]
    correct = [r for r in graded if r.get("correct")]
    rets = [r["return_pct"] for r in graded if isinstance(r.get("return_pct"), (int, float))]
    dates = sorted(r["date"] for r in rows if r.get("date"))

    by_conv: dict[str, dict] = {}
    for r in graded:
        b = by_conv.setdefault(conviction_label(r), {"graded": 0, "correct": 0})
        b["graded"] += 1
        b["correct"] += int(bool(r.get("correct")))

    # Per-component: "ml" / "llm" / "combined" (rows without a component tag are
    # the pre-pivot morning-watch era → "legacy"). This is what answers "which
    # layer adds edge" — the gate question for Aug 20.
    by_comp: dict[str, dict] = {}
    for r in graded:
        comp = (r.get("meta") or {}).get("component") or "legacy"
        b = by_comp.setdefault(comp, {"graded": 0, "correct": 0, "rets": []})
        b["graded"] += 1
        b["correct"] += int(bool(r.get("correct")))
        if isinstance(r.get("return_pct"), (int, float)):
            b["rets"].append(r["return_pct"])
    by_component = {
        c: {"graded": b["graded"], "correct": b["correct"],
            "hit_rate": round(b["correct"] / b["graded"], 3),
            "mean_return_pct": round(sum(b["rets"]) / len(b["rets"]), 2) if b["rets"] else None}
        for c, b in by_comp.items()
    }

    newest = dates[-1] if dates else None
    days_stale = (date.today() - date.fromisoformat(newest)).days if newest else None
    return {
        "asof": date.today().isoformat(),
        "total": len(rows),
        "graded": len(graded),
        "open": len(open_),
        "hit_rate": round(len(correct) / len(graded), 3) if graded else None,
        "mean_return_pct": round(sum(rets) / len(rets), 2) if rets else None,
        "by_conviction": by_conv,
        "by_component": by_component,
        "newest_entry": newest,
        "days_since_newest_entry": days_stale,
    }


def narrative(card: dict) -> str:
    try:
        import anthropic
    except ImportError:
        return "_(narrative skipped: anthropic SDK not installed)_"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "_(narrative skipped: ANTHROPIC_API_KEY not set)_"
    prompt = (
        "You are writing the weekly eval verdict for an options paper-trading "
        "research bot (PEAD strategy, two-signal ML+LLM gate, Alpaca paper). "
        "The Aug 20 2026 live-capital decision depends on honest weekly reads.\n\n"
        f"Computed scorecard (source of truth — do not alter or invent numbers):\n"
        f"{json.dumps(card, indent=2)}\n\n"
        "Write <=150 words: one-line VERDICT (e.g. 'NO DATA', 'ACCUMULATING', "
        "'EDGE-POSITIVE', 'EDGE-NEGATIVE'), then 2-4 sentences of honest read, "
        "then at most 3 concrete action items. If graded count is small, say the "
        "sample is too thin for conclusions — never dress up thin data. If "
        "days_since_newest_entry > 4, flag the pipeline as possibly stalled."
    )
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=400,
                                     messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in msg.content).strip()
    except Exception as e:  # eval must not fail on LLM hiccups
        return f"_(narrative skipped: {type(e).__name__}: {str(e)[:120]})_"


def render(card: dict, verdict: str) -> str:
    conv_rows = "\n".join(
        f"| {c} | {b['graded']} | {b['correct']} | "
        f"{(b['correct'] / b['graded']):.0%} |"
        for c, b in sorted(card["by_conviction"].items())
    ) or "| — | 0 | 0 | — |"
    comp_rows = "\n".join(
        f"| {c} | {b['graded']} | {b['hit_rate']:.0%} | "
        f"{(f'{b['mean_return_pct']:+.2f}%' if b['mean_return_pct'] is not None else '—')} |"
        for c, b in sorted(card["by_component"].items())
    ) or "| — | 0 | — | — |"
    hit = f"{card['hit_rate']:.1%}" if card["hit_rate"] is not None else "—"
    mean = f"{card['mean_return_pct']:+.2f}%" if card["mean_return_pct"] is not None else "—"
    return f"""# Weekly eval — {card['asof']}

Generated by `scripts/weekly_eval.py` in GitHub Actions ({datetime.now(timezone.utc).isoformat(timespec='seconds')}).
Scorecard is computed from `data/predictions.jsonl`; the narrative only interprets it.

## Verdict

{verdict}

## Scorecard

| Metric | Value |
|---|---|
| Total predictions | {card['total']} |
| Graded | {card['graded']} |
| Open | {card['open']} |
| Hit rate | {hit} |
| Mean return (graded) | {mean} |
| Newest entry | {card['newest_entry'] or '—'} |
| Days since newest entry | {card['days_since_newest_entry'] if card['days_since_newest_entry'] is not None else '—'} |

### By conviction

| Conviction | Graded | Correct | Hit rate |
|---|---|---|---|
{conv_rows}

### By component (ml = signal alone, llm = analyst alone, combined = the gate; legacy = pre-pivot era)

| Component | Graded | Hit rate | Mean return |
|---|---|---|---|
{comp_rows}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip the Claude narrative")
    args = ap.parse_args()

    rows = load_predictions()
    card = scorecard(rows)
    if not rows:
        verdict = ("**NO DATA** — data/predictions.jsonl is missing or empty. The daily "
                   "pipeline has not logged any predictions yet; check the daily-run "
                   "workflow history.")
    elif args.no_llm:
        verdict = "_(scorecard-only run)_"
    else:
        verdict = narrative(card)

    doc = render(card, verdict)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"weekly-{card['asof']}.md").write_text(doc, encoding="utf-8")
    (OUT_DIR / "latest.md").write_text(doc, encoding="utf-8")
    print(doc)
    sys.exit(0)


if __name__ == "__main__":
    main()
