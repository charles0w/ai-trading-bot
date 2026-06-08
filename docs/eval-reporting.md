---
name: Eval Reporting — ai-trading-bot
type: design
updated: 2026-06-04
tags:
  - ai-trading-bot
  - eval
  - design
---

# Eval Reporting (first agent on the fleet quality layer)

> [!summary]
> Drop-in block that makes ai-trading-bot the **first agent to report output quality** to the [[../ceos-enterprise/eval-integration|ceos-enterprise fleet dashboard]]. It judges each EOD recap with [[../../research/ai-evals/kb/llm-as-judge|LLM-as-judge]] (Anthropic API), tracks [[../../research/ai-evals/kb/pass-k-reliability|reliability]], and posts both. This is **Week 4 (Proof)** of the [[../../research/ai-evals/02-learning-path|eval learning path]] — the depth→proof step.

> [!note] Status (2026-06-04): no real recap pipeline yet
> The EOD recap isn't produced by runnable repo code yet, so the `report_eod_recap()` block below is the **target** for when that pipeline exists. To exercise the real judge *today* without a pipeline, use `judge_demo.py` (scores sample or file text) and `smoke_eval.py` (proves the dashboard pipe). When you build the recap job, drop in the block below.

## Prereqs

1. Apply `eval-judge-anthropic.patch` to ceos-enterprise (adds the native Anthropic judge), then copy the updated `reporter/ceo_report.py` to wherever the recap job runs.
2. Set env vars (`.env` or GitHub Actions secrets):

```bash
CEOS_REPORT_URL=https://ceos-enterprise.vercel.app/api/report
CEOS_REPORT_SECRET=<= REPORT_SECRET in the Vercel project>
# judge() — Anthropic (native)
ANTHROPIC_API_KEY=<key>
EVAL_JUDGE_MODEL=claude-haiku-4-5-20251001   # optional; this is the default
```

> [!warning] Self-preference bias ([[../../research/ai-evals/kb/judge-biases]])
> Judge with a **different model family** than the one that *generates* the recap. If you ever generate recaps with Claude, judge with Gemini/OpenAI instead (or vice-versa) — a model grading its own output inflates the score.

The agent reports under id **`finance`** (how this repo maps on the fleet — see `lib/agents.ts`).

## Drop-in block

```python
from ceo_report import report, judge, track_reliability

# Rubric — derived from the eval KB, versioned HERE not scattered inline.
# Faithfulness + completeness + calibration (see research/ai-evals/kb).
EOD_RECAP_CRITERIA = """\
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

PROMOTION_THRESHOLD = 0.7  # tune AFTER validating the judge (see below)

def report_eod_recap(recap_text: str, headline: str) -> None:
    """Judge the recap, track reliability, report quality to CEO Enterprise."""
    ev = judge(recap_text, criteria=EOD_RECAP_CRITERIA)
    score = ev["score"]

    if score is None:
        # Judge not configured or errored — report completion only, never a fake score.
        report("finance", ok=True, summary=headline)
        return

    rel = track_reliability("finance", passed=score >= PROMOTION_THRESHOLD)
    report(
        "finance",
        ok=True,
        summary=headline,
        eval_score=score,
        eval_reliability=rel,
        eval_summary=ev["summary"],
    )
```

## Wire it into the EOD job

At the end of the recap run, where it currently just finishes (or already calls `report`):

```python
recap = build_eod_recap()          # your existing generator → returns the recap string
report_eod_recap(recap, headline="EOD recap done — NVDA +2.3%, 3 positions marked")
```

That single call lands the first real **quality %** and **reliability %** on the agent's dashboard card.

## Validate the judge BEFORE trusting the number

> [!warning] An unvalidated judge is a confident guess — [[../../research/ai-evals/kb/who-validates-the-validators]]
> Do this once before relying on the scores:
> 1. Pull ~30 past EOD recaps (the golden set — a reusable asset).
> 2. Hand-grade each pass/fail against the rubric above.
> 3. Run `judge()` on the same 30; compute agreement with your grades.
> 4. If agreement is weak, sharpen `EOD_RECAP_CRITERIA` and/or move `PROMOTION_THRESHOLD`. Re-check.
>
> Watch for verbosity bias (judge rewarding longer recaps) — the rubric's "penalize hype / reward reasoning" line is the guard.

## Why this is the right first agent

Finance is the highest-stakes, most-quantitative output in the fleet — "is this recap faithful and not hallucinating numbers" is exactly where an undetected quality drop costs the most. Reliability (`pass^k`-style) matters doubly here: an inconsistent recap pipeline is untradeable even at high average quality.

## See also

- [[../ceos-enterprise/eval-integration]] — the layer this feeds
- [[../../research/ai-evals/02-learning-path]] — this is Week 4
- [[../../research/ai-evals/kb/llm-as-judge]] · [[../../research/ai-evals/kb/pass-k-reliability]] · [[../../research/ai-evals/kb/who-validates-the-validators]]
