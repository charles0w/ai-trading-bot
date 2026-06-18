---
name: phase0-execution-reuse-2026-06-16
type: spike
parent: ai-trading-bot
date: 2026-06-16
updated: 2026-06-16
tags:
  - ai-trading-bot
  - phase0
  - execution
  - reuse
  - lambos
---

# Phase 0 spike — lambos execution-reuse map (2026-06-16)

> [!summary]
> Read the actual `lambos-w-andy` code. **Good news: the execution layer is cleanly decoupled from the copy-trade front end.** `broker/` and most of `execution/` lift with zero or trivial change; the only Discord/copy-trade coupling lives in `ingest/`, `parser/`, and three concepts (`ParsedAlert`, `alert_age`, author/expert). The clean seam is a single new `TradeIntent` dataclass that the ai-trading-bot **brain** produces and the shared **executor** consumes. Recommended reuse mechanic (answers [[pivot-2026-06-16]] open-Q1): **extract a shared `trader_core` package** both repos import. This is a small, test-backed refactor. Feeds Phase 0 of [[pivot-2026-06-16]] and the strategy from [[strategy-research-2026-06-16]] (PEAD-post-crush long options).

## What lambos actually has (verified by reading the source)

- `trader/broker/base.py` (77 LOC) — abstract `Broker` ABC + `OptionContract` / `OrderResult` / `PositionSnapshot` dataclasses. **Zero copy-trade coupling.** OCC-symbol options, bid/ask/mid, place/poll/cancel/position/mark.
- `trader/broker/alpaca_client.py` (192 LOC) — Alpaca **paper** impl (`alpaca-py`), OCC symbol builder, long calls/puts — exactly our v1 surface. (Requires options **Level 2** on Alpaca; the lifted lambos comment said "Level 1" and was wrong — fixed in `trader_core`.) Account-key-driven, so a *separate* paper account is just different `.env` keys.
- `trader/execution/sizing.py` (55 LOC) — pure function, fully generic. Caps by per-trade $, per-contract premium, capital headroom, buying power.
- `trader/execution/risk.py` (112 LOC) — pre-trade gate: kill switch, daily-loss limit, max positions, max capital, trading-window + NYSE-holiday calendar, **`alert_age_seconds`** (the one copy-trade-ism: staleness of a Discord alert).
- `trader/execution/executor.py` (127 LOC) — entry orchestration: deterministic client-order-id (crash-safe, no double-submit), dry-run path, place → poll-to-fill w/ timeout → open position. **Coupled only by its input type** (`alert: ParsedAlert`, `parsed_alert_id`).
- `trader/execution/exit_manager.py` (147 LOC) — TP / SL / **EOD-close** poll loop over open positions using broker marks. **Generic**, but EOD-close is a *day-trade* default we must change for swing.
- `trader/db.py` (359 LOC) — SQLite: `parsed_alerts`, `orders`, `positions`, author/expert columns, heartbeat.
- `trader/pipeline.py` (324) wires it all; `ingest/` + `parser/` + `reports/daily.py` are **copy-trade-specific** (Discord self-bot, OCR, BAKE regex, per-expert leaderboard).
- Tests exist for `risk`, `sizing`, `parser`, `config`, OCC symbol — the refactor is protected.

## The brain/hands seam

Today the executor's signature is the only thing tying execution to copy-trading:

```python
execute_entry(*, db, broker, cfg, alert: ParsedAlert, parsed_alert_id, sizing, contract, ...)
```

`ParsedAlert` is "a human expert said buy X." Replace it with a source-agnostic **`TradeIntent`** that *either* front end can emit:

```python
@dataclass
class TradeIntent:
    underlying: str                 # "SPY"
    direction: str                  # "long_call" | "long_put"
    # strike/expiry: either resolved, or a selection rule the resolver applies
    target_dte: int                 # e.g. 35  (swing: 30–45)
    strike_rule: str                # "ATM" | "DELTA:0.55" | "OTM:2pct" | resolved abs strike
    price_ref: float | None         # for limit pricing / sizing if contract mid missing
    signal_id: str                  # FK to predictions.jsonl / signals table (replaces parsed_alert_id)
    conviction: float | None = None # from the ML∧LLM intersection
    meta: dict | None = None        # strategy tag, SUE, IV-rank, model version, etc.
```

With that, `execute_entry(intent, sizing, contract)` and the whole place→poll→open-position body are **shared verbatim**. lambos's parser produces a `TradeIntent`; ai-trading-bot's analyzer produces a `TradeIntent`. One seam, one type.

## Per-file disposition

| lambos file | Action | Why |
|---|---|---|
| `broker/base.py` | **Lift as-is** → `trader_core` | Fully generic |
| `broker/alpaca_client.py` | **Lift as-is** | Paper Level-1 long calls/puts = our surface; separate acct via `.env` |
| `execution/sizing.py` | **Lift as-is** | Pure function |
| `execution/risk.py` | **Lift + rename** | `alert_age_seconds` → `signal_age_seconds`; keep kill-switch/caps/window/holidays |
| `execution/executor.py` | **Lift + generalize input** | Swap `ParsedAlert`/`parsed_alert_id` → `TradeIntent`/`signal_id` |
| `execution/exit_manager.py` | **Lift + extend exits** | Disable EOD-close for swing; add **max-hold-days** + strategy exit + optional trailing stop |
| `db.py` | **Fork/generalize** | Keep `orders`/`positions`; replace `parsed_alerts` w/ `signals`; drop author/expert cols |
| `ingest/`, `parser/`, `reports/daily.py` | **Leave in lambos** | Discord/OCR/expert-specific — not reused |
| `pipeline.py` | **Rewrite thin** | New brain pipeline: data → features → ML → LLM → intersection → `TradeIntent` → shared executor |

## Reuse mechanic — recommendation

**Extract a shared `trader_core` package** (broker/, sizing, risk, executor, exit_manager, the dataclasses) that both `lambos-w-andy` and `ai-trading-bot` import. Rationale: one Alpaca/execution stack to maintain and fix; lambos's tests move with it. Cost: a modest refactor of lambos *while it's mid paper-trial* — so do it **behind its existing tests**, in a branch, and verify `pytest` + a `--dry-run` still pass before merging. If you'd rather not touch lambos during the trial, the fallback is **vendor a snapshot** of these files into ai-trading-bot now and reconcile into a shared package after lambos's Aug-20 live cutover. *Recommended: shared package, but only if we can green the lambos test suite first; else vendor now.*

## Swing-specific changes (from [[strategy-research-2026-06-16]])

The recommended Phase-1 strategy is **PEAD entered after the IV crush** — multi-week holds, not day trades. Concretely:
- **Exits:** turn off `eod_close` (that's a lambos day-trade default); add `max_hold_days` (e.g. 20–30), keep TP/SL on premium %, consider a trailing stop once green. The exit *loop* is reused; the *rules* extend.
- **Risk/window:** entries fire once/day around a chosen time, not on live alerts; `signal_age` becomes "don't act on a signal older than today's close."
- **Sizing/structure:** near-ATM, ~30–45 DTE; the existing `max_premium_per_contract` cap + one-contract paper mode are fine to start.
- **Liquidity filter (new, non-negotiable):** only tight-spread, high-OI underlyings — add a pre-trade spread/OI check in the risk gate (the research's hard rule).

## What the ai-trading-bot brain must implement (the new code)

1. **Data/feature layer** → earnings calendar, SUE, revisions, IV term structure / post-crush IV, realized-vs-implied move history, liquidity/spread.
2. **ML signal + LLM analyst + intersection** → emit a `TradeIntent` only when both agree on a liquid name (T+1/T+2 post-earnings).
3. **Strike/expiry resolver** → turn `strike_rule`+`target_dte` into a concrete `OptionContract` via `broker.find_option_contract` (already exists).
4. **`signals` table + grading** → reuse `predictions.jsonl`; grade on horizon; feed the eval loop.

## Concrete next steps

- [ ] Confirm reuse mechanic: shared `trader_core` vs vendored snapshot (recommend shared, tests-gated).
- [ ] Create a **separate Alpaca paper account**; enable options **Level 2**; put keys in ai-trading-bot `.env` — see [[alpaca-paper-setup]] (blocked on you — needs the account).
- [ ] Land `TradeIntent` + generalize `executor.py`/`risk.py` behind lambos tests.
- [ ] Extend `exit_manager` for swing (max-hold, no EOD close).
- [ ] Smoke test: hand-built `TradeIntent` → place one paper long call → confirm TP/SL/max-hold exit + DB logging (this is the Phase 0 "gate" in [[pivot-2026-06-16]]).

> [!warning] Blocked-on-you items
> A real **Alpaca paper account + keys** (separate from lambos) is required before any order actually places. Everything above (the refactor, the seam, the resolver) can be built and unit-tested without it.

## See also
- [[pivot-2026-06-16]] · [[strategy-research-2026-06-16]] · [[../lambos-trader/overview|lambos-trader]]
