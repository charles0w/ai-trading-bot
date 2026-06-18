---
name: brain-eval-runbook-2026-06-16
type: runbook
parent: ai-trading-bot
date: 2026-06-16
updated: 2026-06-16
tags:
  - ai-trading-bot
  - brain
  - eval
  - runbook
---

# Brain + eval system — runbook (2026-06-16)

> [!summary]
> The full self-directed pipeline is built and **78 tests pass offline** (no network, no API keys needed to test). Live runs happen on the Mac. The chain: **data → features → ML signal → LLM analyst → intersection → resolve contract → risk gate → size → paper execute → log prediction → grade → reliability**. The ML "signal" is a transparent **heuristic v0** (`PeadHeuristicModel`) to be replaced by a trained model behind the same interface. The LLM analyst is Claude; the judge is a cross-family model (Ollama) by design.

## Architecture (what calls what)

```
atb/data/        provider.py (interface) · yfinance_provider.py (prices/chains)
                 finnhub_provider.py (earnings + SUE, delegates prices to yfinance)
atb/features.py  compute_features() -> FeatureVector (momentum, 52w-high, vol,
                 days-since-earnings, post-earnings drift, SUE, IV/liquidity slots)
atb/signal/      pead_model.py (heuristic ML v0) · llm_analyst.py (Claude thesis)
                 intersection.py (trade only if ML AND LLM agree -> TradeIntent)
trader_core/     broker (Alpaca paper, Level 2) · resolver (strike/expiry)
                 risk (caps, window, liquidity) · sizing · executor · exit_manager
atb/eval/        predictions.py (JSONL log) · grading.py · reliability.py · judge.py
atb/pipeline.py  run_symbol(): glues all of the above; DRY RUN by default
scripts/         check_alpaca.py · paper_smoke.py · show_features.py
                 run_once.py (brain over a universe) · grade.py (score matured calls)
```

## Test status

`cd ~/Desktop/ai-trading-bot && source .venv/bin/activate && python -m pytest -q` → **78 passing**. Suites: intent, sizing, risk, executor, exit_manager, resolver, store, features, finnhub, signal, eval, pipeline. All use fakes (FakeBroker / InMemoryStore / FakeProvider / injected LLM), so they run anywhere.

## What Charles must do (when back)

1. **Rotate the Alpaca secret** (it was pasted in chat) — dashboard → API → regenerate, update `.env`.
2. **Add two free API keys to `.env`** (already has placeholders):
   - `FINNHUB_API_KEY` — finnhub.io (earnings + SUE)
   - `ANTHROPIC_API_KEY` — console.anthropic.com (LLM analyst)
3. **Install live deps:** `pip install alpaca-py yfinance anthropic python-dotenv`
4. **Eyeball the brain on a name:** `python scripts/show_features.py NVDA` — see features + whether the naive baseline fires.
5. **Run the brain (dry run):** `python scripts/run_once.py` — prints a decision per symbol, logs predictions to `data/predictions.jsonl`, places nothing.
6. **First paper trade (market hours, 6:30am–1pm PT):** `python scripts/paper_smoke.py --underlying SPY --execute`, or `python scripts/run_once.py --execute` once you trust the dry-run output.
7. **Grade + scorecard (after a few days):** `python scripts/grade.py` — grades matured calls and prints hit rate / expectancy / calibration.

## Honest caveats (don't skip)

- **`PeadHeuristicModel` is not trained** — fixed weights, sensible signs only. It exists to make the loop real. Replacing it with a model trained on a labeled post-earnings dataset is the next real ML task.
- **Direction grading ≠ money.** `grade.py` grades the thesis (underlying move). Option P&L net of premium/theta/slippage is harsher and is what the go-live gate in [[pivot-2026-06-16]] actually requires.
- **Liquidity/IV-crush gates are partial.** The risk layer has the liquidity hook but the pipeline doesn't yet thread real OI/spread + post-crush IV from the option chain into it. That's wired next.
- **The base rate is brutal** ([[strategy-research-2026-06-16]]): expect most days = no trade, and expect the long-only edge to be thin. The whole point is to find that out on paper before any capital.

## Next build steps (in priority order)

1. Thread option-chain **OI / spread / IV-rank** into the feature vector + risk liquidity gate (uses `provider.option_chain`, already implemented).
2. Replace the heuristic with a **trained PEAD model** (label post-earnings drift outcomes; logistic/GBM; walk-forward validated via the existing [[backtest]] discipline).
3. **Exit management on paper**: run `ExitManager` against open paper positions (TP/SL/max-hold) on a schedule.
4. **Daily automation** + a ceos-enterprise fleet card reporting hit rate / expectancy / calibration.
5. **Decide:** is v1 (long-only) the strategy or the on-ramp to the Level-3 short-premium edge (account is already approved Level 3).

## Update — trained model + automation + sync (later same session)

**Live validation done** (on the Mac): Alpaca ACTIVE/Level 3, Finnhub real SUE (NVDA 2.92), yfinance prices, and the **Claude analyst all work**. `run_once` correctly returned `no_trade` — mid-June is between earnings waves, so few names are in the 1–5d PEAD window (it'll wake up as Q2 earnings ramp mid/late July). `scan.py` found ADBE (reported 6d ago, −10.3%) just outside the window.

**Trained model (replaces heuristic):**
- `atb/signal/logistic.py` — `LogisticSignal` (same Signal interface, learned weights, JSON save/load).
- `atb/train/` — `dataset.py` (labels historical post-earnings events point-in-time) + `trainer.py` (pure-Python GD logistic). `scripts/train_model.py` builds the dataset + saves `data/model.json`.
- `run_once.py` auto-loads `data/model.json` if present, else falls back to the heuristic.
- Run: `python scripts/train_model.py` (needs Finnhub + network). In-sample accuracy is optimistic — the paper trial graded net of costs is the real test.

**Daily automation (Mac launchd):** `scripts/run_daily.sh` (grade → scan → run_once) + `deploy/com.charles.atb-daily.plist` (weekdays 07:30 PT) + `deploy/README.md`. Dry run until `ATB_EXECUTE=1`. Same FDA/TCC caveat as eod-recap.

**Tests: 83 passing** (added trained-model + dataset/trainer suites).

**Push (code repo):** committed locally (92 files, no secrets — `.gitignore` covers `.env`/`data`/`logs`), remote set to `git@github.com:charles0w/ai-trading-bot.git`. The sandbox can't push (no SSH key). **On the Mac:**
```
cd ~/Desktop/ai-trading-bot && git push -u origin main --force
```
(`--force` because the GitHub repo still holds the old recap-markdown snapshot; the new codebase supersedes it.) The **vault** auto-syncs via obsidian-git.

**Evals: in place + tested, not yet exercised.** The eval system (`atb/eval/`: predictions log, grading, reliability/calibration, cross-family judge) is built and unit-tested, AND there's a second, older eval layer (`ceo_report.py`, the live dashboard) from the 6/5 build. Today's `grade.py` correctly returned an empty scorecard — **no predictions to grade yet** because the brain has (correctly) placed no trades. Evals start producing real numbers once the brain logs predictions (dry-run `run_once` already logs them when a setup qualifies; grading matures `horizon_days` later).

## See also
- [[pivot-2026-06-16]] · [[strategy-research-2026-06-16]] · [[phase0-execution-reuse-2026-06-16]] · [[alpaca-paper-setup]]
