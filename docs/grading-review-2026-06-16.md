---
name: grading-review-2026-06-16
type: review
parent: ai-trading-bot
date: 2026-06-16
updated: 2026-06-16
tags:
  - ai-trading-bot
  - grading-review
  - eval
---

# Prediction-grading review — 2026-06-16

> [!summary]
> First prediction-grading review (was due 6/12, run 6/16). Sample is tiny: **4 directional calls from 2026-06-05, graded 2026-06-10** on a 5-session horizon. Hit rate **1/4 (25%)** — matches the 0.25 `evalReliability` baseline already on the dashboard. The one correct call was the lone *bearish* thesis; the three losers were all *long* calls into a tape that fell broadly. n is far too small to validate or kill the LLM directional layer. **Verdict: revert to recaps-only** until the pipeline is unblocked and the prediction-logging step is fixed.

---

## What was graded

| Ticker | Call | Conviction | Entry | Exit (6/10) | Return | Correct? |
|---|---|---|---|---|---|---|
| NVDA | up | medium | 205.10 | 200.42 | −2.28% | ❌ |
| SPY | up | low | 737.55 | 725.43 | −1.64% | ❌ |
| AVGO | down | low | 385.73 | 372.10 | −3.53% | ✅ |
| NFLX | up | low | 82.18 | 82.00 | −0.22% | ❌ |

Source: `predictions.jsonl` (all four `status: graded`, `graded_date: 2026-06-10`, `entry_ref_source: yfinance`). **Hit rate 1/4 = 0.25.**

---

## Patterns

**1. Net-long into a down tape.** Three of the four calls were "up" (NVDA, SPY, NFLX) and all three lost; the market fell over the window (SPY −1.64%). The only winner was the single "down" call. The 6/5 batch was systematically long-biased on a tape that rolled over — directional bias, not stock selection, drove the miss.

**2. The winner was a concentrated bearish catalyst; the losers were weak-edge "relative strength" theses.** AVGO worked because it was a high-magnitude, multi-signal, idiosyncratic-epicenter thesis (the −7.9% semi-breakdown leader on a −4.5% tech tape). The losers were "it held green vs. the index" relative-strength longs (NVDA, NFLX) and one broad "breadth risk-on" macro call (SPY) the tape immediately reversed. This is consistent with the [[backtest]] null result: idiosyncratic/structural signals are the only ones that carried any edge; "relative strength" framings are noise.

**3. Conviction is not yet trustworthy.** The single highest-conviction call (NVDA, medium) was wrong; lows went 1/3. Too few points to calibrate, but there is no evidence yet that the conviction label carries information — do not size on it.

---

## Pipeline gaps found (more important than the score)

> [!warning] The logging + recap pipeline broke after 6/11 — there is nothing newer to grade
> 1. **6/11 predictions were never logged.** The 2026-06-11 recap generated four fresh calls (ORCL down/high, ADBE down/medium, MU flat, XOM·XLE down) in its JSON block, but **none were appended to `predictions.jsonl`** — the recap→prediction-log step did not run. Nothing from 6/11 exists to grade on its 6/18 horizon.
> 2. **Recaps stopped entirely after 6/11.** No 6/12, 6/15, or 6/16 recap. Root cause is the known `launchd` TCC blocker — `com.charles.eod-recap` fires but can't write the Desktop-resident vault without **Full Disk Access granted to `/bin/bash`** (carried unchecked 6 days). See [[notes#2026-06-10 — Recap pipeline stopped (migration) + rebuilt local on macOS]].

So the prediction loop has produced exactly one gradeable batch (6/5) and then went dark. There is no ongoing stream to evaluate.

---

## Verdict

n=4 cannot validate or kill the LLM directional layer — no statistical conclusion is possible, and the dashboard's 0.25 reliability is just this one batch. What the sample *does* weakly suggest aligns with the backtest: only concentrated, idiosyncratic catalyst calls show any edge; relative-strength longs are noise.

**Decision (per the 6/12 daily-todo: "run the grading review or revert to recaps-only"): revert `ai-trading-bot` to recaps-only.**

- Stop logging directional predictions. Keep the EOD recap as market-research discipline only — zero-maintenance, consistent with the paused-trading posture.
- Do **not** resume the grading experiment until: (a) FDA is granted so the recap `launchd` job runs unattended, (b) the recap→`predictions.jsonl` logging step is fixed so calls are actually captured, and (c) a revenue Phase 0 has cleared (the 2026-04-28 pause receipt still gates all trading-research build work).
- Re-run a grading review only after ≥20 graded calls exist — below that the score is anecdote.

---

> [!check] Verification
> 4 predictions read from `predictions.jsonl`; all `graded` with real yfinance exits. Hit rate recomputed by hand: AVGO correct (down, −3.53%); NVDA/SPY/NFLX incorrect → 1/4 = 0.25, matches dashboard reliability. 6/11 recap JSON checked against `predictions.jsonl` — confirmed not logged. Recap directory confirmed empty after 2026-06-11.
