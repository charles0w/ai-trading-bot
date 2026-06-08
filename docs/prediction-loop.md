---
name: prediction-loop
type: design
updated: 2026-06-05
tags:
  - ai-trading-bot
  - eval
  - design
---

# Prediction loop — grade calls vs outcomes

The upgrade that actually improves results. Recap-quality evals grade *prose*; this grades whether the bot's **calls were right**. It's the same eval infrastructure (`eval_runs`, dashboard, `pass^k`) pointed at outcomes instead of writing quality — the daloopa "guidance-tracker" pattern aimed at the bot itself.

## The flywheel

```
recap makes a directional call ──► log to ledger (open)
                                      │  wait `horizon_days`
                                      ▼
            on/after horizon ──► pull actual price ──► grade right/wrong + magnitude
                                      │
                                      ▼
        rolling accuracy = % correct over last k calls  ──►  finance agent
        (this is pass^k for predictions)                      evalReliability on the dashboard
```

Keep what works, kill what doesn't — and the dashboard's drift cron now flags **declining predictive accuracy**, not just declining prose.

## Prediction ledger (vault, append-only JSONL)

`repos/ai-trading-bot/predictions.jsonl` — one line per call:

```json
{"id":"2026-06-05-NVDA","date":"2026-06-05","ticker":"NVDA","direction":"up",
 "horizon_days":5,"entry_ref":218.66,"rationale":"held green vs semi weakness; idiosyncratic AVGO drop",
 "signals":["technical:relative-strength","sector:tech+1.3%"],"conviction":"medium",
 "status":"open","graded_date":null,"exit_ref":null,"correct":null,"return_pct":null}
```

- **direction**: `up` | `down` | `level:<price>` (a target/level call).
- **signals**: which inputs drove it — lets you later see *which signal types* actually predict (technical vs sentiment vs smart-money).
- **conviction**: gate for the two-signal rule below.
- Grading fills `exit_ref`, `correct`, `return_pct`, `status:graded`.

## Grading rule

On/after `date + horizon_days`: fetch the ticker's price, compare to `entry_ref`. `up` correct if higher (beyond a small threshold to ignore noise), `down` if lower, `level` if it hit the target. Record signed `return_pct`. Reliability = correct / graded over the last `k` (e.g. 20).

> **Price-source dependency:** grading needs a per-symbol price, which is *gated* on the current FMP plan (see [[data-roadmap]]). Use **yfinance** for grading (free, has history) — the cleanest unblock.

## Two-signal intersection (raise hit-rate)

Your [[../polymarket-copy-trader/overview|polymarket-copy-trader]] rule, applied here: only mark a call **high-conviction** when a **technical** signal and a **sentiment** signal agree. Track conviction in the ledger, then measure: do high-conviction (2-signal) calls actually beat single-signal ones? That's a testable, data-backed edge claim — and exactly the kind of thing the eval loop can prove or kill.

## What reports to the dashboard

The finance agent posts two numbers:
- `evalScore` — today's recap **quality** (judge, grounded — [[grounded-recap-demo]]).
- `evalReliability` — rolling **predictive accuracy** from this ledger.

Two different questions ("is the writeup good?" vs "are the calls right?"), both surfaced on the Fleet Quality card. Reliability is the one that matters for money.

## Automation — split across the network boundary

First live run (2026-06-05) found the **Cowork sandbox blocks direct outbound HTTP** (yfinance and the dashboard POST both 403). MCP connectors work (proxied); plain `urllib` does not. So the loop is split along that line:

```
[ Cowork scheduled task: ai-trading-eval-loop ]   (has MCP, no outbound HTTP)
   pull FMP data → grounded recap → self-judge → log new calls
   → write latest-report.json + recaps/<date>.md + predictions.jsonl  (to the vault = your disk)
                                   │
                                   ▼  (vault is on your local disk)
[ Local: sync_dashboard.py ]   (real network — the rigor layer)
   backfill entry_ref with REAL closes (yfinance) → grade matured calls
   → CROSS-FAMILY re-judge the recap (Gemini) → compute reliability
   → POST cross-family quality + reliability to the dashboard
```

Run `sync_dashboard.py` on your machine after the cloud task each weekday (or schedule via Windows Task Scheduler). Needs `pip install yfinance`, `REPORT_SECRET`, and the Gemini judge env vars (below). Grading + judging + posting live locally because the sandbox can't reach Yahoo or a judge API.

### Foundation fixes (2026-06-06) — why the local script is the rigor layer

Two cracks in the first version, both fixed locally because the sandbox can't do either:

1. **Real prices, not proxies.** The cloud recap infers some index/single-name levels from leveraged-ETF proxies (FMP `quote` is plan-gated). `sync_dashboard.py` now **backfills `entry_ref` with direct yfinance closes** (tagged `entry_ref_source: yfinance`) before grading, so entry and exit are measured on the same real basis.
2. **Cross-family judge.** The cloud task self-judges (Claude grading Claude = self-preference bias, per [[../../research/ai-evals/kb/judge-biases]]). The local script **re-judges the recap with a different family** via any OpenAI-compatible endpoint and posts *that* score, overriding the provisional self-judge. The cloud `evalScore` is now explicitly labeled provisional. The posted label reflects the actual model (`EVAL_JUDGE_MODEL`), not a hardcoded name.

> [!success] Validated 2026-06-06 with **local Ollama** (Llama 3.1) → scored the 2026-06-05 recap **0.85**. Cloud free tiers all rate-limited during setup (Gemini 429, Groq 403), so local Ollama is the reliable judge — no keys, no quota, no rate limits.

Env — **working config (local Ollama, recommended):** install Ollama, `ollama pull llama3.1`, then:
```
EVAL_JUDGE_PROVIDER=openai
EVAL_JUDGE_URL=http://localhost:11434/v1/chat/completions
EVAL_JUDGE_KEY=ollama
EVAL_JUDGE_MODEL=llama3.1
```
Cloud alternative (any OpenAI-compatible endpoint — Gemini, Groq, OpenAI): set `EVAL_JUDGE_URL`/`KEY`/`MODEL` accordingly. Do NOT set `ANTHROPIC_API_KEY` locally, or `judge()` auto-picks Claude (same family as the writer). Free tiers rate-limit; local avoids it.

## CoinDesk connector (crypto derivatives — connected 2026-06-05)

The CoinDesk MCP is now available and works **in-sandbox** (it's a connector). It exposes serious crypto-derivatives data: spot/futures/options OHLCV, **open interest**, **funding rates**, orderbook metrics, trades, and news. For the equity/options core it's crypto-only, but it's a strong signal source for the crypto-adjacent side ([[../polymarket-copy-trader/overview|polymarket]], crypto options). A natural future lane: a crypto recap + prediction track using OI + funding-rate divergence as signals — same loop, crypto data.

## See also

- [[grounded-recap-demo]] · [[data-roadmap]] · [[eval-reporting]]
- [[../../research/ai-evals/kb/pass-k-reliability]] · [[../ceos-enterprise/eval-trends-cron]]
