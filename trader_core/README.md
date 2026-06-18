# trader_core

Broker-agnostic options **execution core** — the reusable "hands" lifted from
`lambos-trader` and generalized so both that copy-trader and this self-directed
swing bot share one tested execution stack.

## What's here

| Module | Role |
|---|---|
| `broker/base.py` | Abstract `Broker` + `OptionContract` / `OrderResult` / `PositionSnapshot` |
| `broker/alpaca_client.py` | Alpaca **paper** broker (long calls/puts → Alpaca **Level 2**). Lazy-imports `alpaca-py` so the package loads without it. |
| `execution/intent.py` | **`TradeIntent`** — the brain/hands seam. Any front end emits one. |
| `execution/sizing.py` | Pure position sizing (per-trade $, premium cap, capital headroom). |
| `execution/risk.py` | Pre-trade gate: kill switch, caps, trading window + NYSE holidays, `signal_age`, **options liquidity filter**. |
| `execution/executor.py` | Crash-safe entry: place → poll-to-fill → open position. Consumes a `TradeIntent`. |
| `execution/exit_manager.py` | TP / SL / **max-hold (swing time-stop)** / optional EOD. Pure `evaluate()` for testing. |
| `ports.py` | `Store` Protocol — persistence seam (SQLite, in-memory, whatever). |
| `config.py` | Self-contained config dataclasses (swing defaults). |

## Design seams

- **TradeIntent** replaces lambos's copy-trade `ParsedAlert`. lambos's parser
  produces one; ai-trading-bot's ML+LLM analyzer produces one; `execute_entry`
  is identical for both.
- **Store port** decouples execution from any database. Provide your own
  implementation (see `tests/conftest.py:InMemoryStore`).

## Test

```bash
cd ~/Desktop/ai-trading-bot && python3 -m pytest tests/ -q   # 34 tests, no network / no alpaca-py needed
```

The suite uses a `FakeBroker` + `InMemoryStore`, so it exercises the full
entry/exit machinery offline.

## Reuse from lambos (later)

To make lambos import this instead of its own copy: `pip install -e` this
package (or split it to its own repo), then map lambos's `ParsedAlert` →
`TradeIntent` and its `DB` → the `Store` protocol. Do it behind lambos's
existing tests while its paper trial runs. See
`docs/phase0-execution-reuse-2026-06-16.md`.
