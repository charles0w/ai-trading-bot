# ai-trading-bot

Options trading research bot. Claude Opus 4.7 sits at the analyst layer of an otherwise deterministic signal pipeline. Live capital is gated behind an explicit benchmark that proves the LLM beats a rules-only baseline.

> **Status:** scoping. No code yet. Read the vault planning notes before opening a PR.

## The pitch in one paragraph

Most LLM "trading bots" are toys: prompt the model with a chart screenshot, ask "buy or sell?" That's not a system. This project flips it — the LLM is the analyst, not the executor. A deterministic pipeline ingests data, fires named signals, and screens to ≤10 candidates per day. Opus 4.7 is invoked once per candidate to produce a structured trade thesis. A separate rules-based decision engine picks the option structure and position size. Before any live capital, Opus 4.7 must beat a deterministic baseline on out-of-sample backtests across 3 time-series folds. If it doesn't, the LLM layer is removed and the bot ships as a screener-only research tool.

## Where the planning lives

This repo's design, scoping, and roadmap live in the second-brain vault, not in this repo:

```
C:\Users\charl\Desktop\obi-secondbrain\repos\ai-trading-bot\
  overview.md          — top-level summary
  scoping.md           — honest feasibility assessment
  architecture.md      — pipeline design, where Opus 4.7 fits
  signals.md           — indicator catalog (the screener's signals)
  benchmark-plan.md    — the gate that decides whether we ship
  data-sources.md      — APIs, free vs. paid, ToS notes
  roadmap.md           — phased plan with kill-switch gates
  legal.md             — brokerage ToS, suitability, tax
  notes.md             — running session log
```

The vault is also where the **options indicators playbook** lives, which is the source of truth for the signals this bot screens on:

```
C:\Users\charl\Desktop\obi-secondbrain\market-research\options\
  index.md             — folder index
  playbook.md          — accumulating cheat sheet of leading indicators
  2026-04-26.md        — daily reviews of best-performing options
```

## Stack (planned)

- Python 3.12
- DuckDB (file-based analytical store)
- pandas (data wrangling)
- Anthropic SDK (Opus 4.7, with prompt caching)
- FastAPI (ops console, localhost-only)
- Alpaca paper-trading API (auto-execute during benchmark phase)
- Tradier sandbox (options chain EOD)
- yfinance / Polygon free tier (equities EOD)
- SEC EDGAR (filings, Form 4)
- Finnhub free tier (earnings calendar + actuals)

## Roadmap at a glance

1. **Phase 0** — validate the deterministic baseline beats SPY before writing any LLM code. (1 week)
2. **Phase 1** — wire Opus 4.7 thesis call with prompt caching + structured output. (1 week)
3. **Phase 2** — run the benchmark. Pass = paper trade. Fail = remove LLM layer. (2 weeks)
4. **Phase 3** — paper trade for ≥ 3 months. (calendar-bound)
5. **Phase 4** — small-size live trading for ≥ 3 months. (calendar-bound)
6. **Phase 5** — scale only if all prior phases pass.

Minimum elapsed time before scaled live trading: ~7–8 months. Intentional.

## What this is *not*

- Not a chat-with-the-model demo
- Not financial advice
- Not high-frequency or intraday — daily/swing only
- Not auto-execution from day one
- Not a multi-user product

See [`legal.md`](../obi-secondbrain/repos/ai-trading-bot/legal.md) in the vault for the full disclaimer set.

## Getting started (when there's code)

```bash
# Not yet implemented. Phase 0 setup will live here.
```

## License

Personal-use research project. Not open-source.
