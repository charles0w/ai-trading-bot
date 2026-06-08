---
name: backtest
type: design
updated: 2026-06-08
tags:
  - ai-trading-bot
  - backtest
  - eval
---

# Backtest harness

> [!summary]
> `backtest.py` replays a **signal strategy** over years of historical prices and grades every call with the **exact same rule** the live loop uses ([[prediction-loop]] / `sync_dashboard.py`: same `direction`/`NOISE`/return logic, same record shape). It's the fast version of the prediction loop — instead of waiting 5 days per call, you get decades of graded outcomes in seconds — so you can answer "does this signal have edge?" *before* trusting it. The hard part isn't running it; it's not fooling yourself, so the rigor is built in.

## What it tests (and what it deliberately does NOT)

- **Does:** backtest the **deterministic signal rules** (the screener layer) — e.g. "do big 1-day drops mean-revert?" That's the right thing to validate first, and it's the baseline the LLM analyst must beat (see [[benchmark-plan]]).
- **Does NOT:** replay the LLM analyst over history (too slow/costly, and not the question yet). It also isn't "training a model on prices" — that's the [[overview|overfitting trap]] we explicitly avoided.

## How it plugs into the grading code

```
strategy(date, history≤date)  ->  [(ticker, direction, conviction)]   # decision, no lookahead
        │
        ▼  entry = close[date]   exit = close[date + HORIZON]          # future used ONLY to grade
grade_call(direction, entry, exit)  ──  same rule as sync_dashboard.py
        │   correct = ret > NOISE (up) / ret < -NOISE (down); realized = ±ret − cost
        ▼
records (same shape as predictions.jsonl)  ->  metrics, split IN-SAMPLE vs OUT-OF-SAMPLE
```

Because the grade rule and record shape match the live loop, a strategy that backtests well can be dropped into the daily loop as a real signal and its forward results will be directly comparable.

## The anti-self-deception checklist (baked in)

1. **No lookahead.** The strategy only sees `close.loc[:date]`; the exit price is touched only by the grader. This is the #1 backtest killer and it's structurally prevented.
2. **Baseline + significance.** Every result is shown against the **base rate of up-moves** over the same windows, with a normal-approx z/p-test. An edge smaller than baseline+noise is not an edge.
3. **Out-of-sample split.** `TRAIN_END` divides tune-here (in-sample) from the **only number that counts** (OOS). Don't tune on OOS.
4. **Costs.** `COST_BPS` is subtracted from every trade. Zero-cost backtests lie.
5. **Conviction check.** Reports hit-rate by conviction tier — directly tests the [[prediction-loop|two-signal "high-conviction beats low"]] claim.

What it **can't** fix, and you must keep in mind:
- **Survivorship bias** — yfinance only has tickers that still exist; losers that delisted are missing, inflating results.
- **Multiple comparisons** — run 50 strategies and one looks great by pure chance. This is [[../../research/ai-evals/kb/benchmark-contamination|benchmark contamination]] in disguise. Decide the strategy *before* you look, or correct for the number of tries.

## Run it

```powershell
pip install yfinance pandas
cd C:\Users\charl\Desktop\obi-secondbrain\repos\ai-trading-bot
python backtest.py
```

Swap the hypothesis by setting `STRATEGY = strat_dip_reversion | strat_momentum | strat_baseline_spy` (or write your own `strategy(date, hist)`).

## How to read the output

The headline is the **OUT-OF-SAMPLE** block. A signal is interesting only if, on OOS data, its hit-rate **beats the baseline up-rate**, the **edge is significant (p<0.05)**, **and** the avg realized return is positive **after costs**. If `strat_baseline_spy` matches your "smart" strategy, the strategy adds nothing. Most first ideas fail this — which is the harness doing its job and saving you from deploying noise.

## Pre-registered hypotheses (committed 2026-06-06, BEFORE running v2)

To avoid the multiple-comparisons trap (try enough strategies and one "works" by chance), these three are committed up front with success criteria. Because we test **3**, the significance bar is Bonferroni-corrected to **p < 0.017** (the harness prints this).

- **H-A · Weekly reversal** (`strat_weekly_reversal`, horizon 5d). *Hypothesis:* the documented short-term reversal effect — the worst 5-day losers bounce. *Success:* OOS hit-rate beats baseline at p<0.017, positive after costs, **and** portfolio beats buy-hold SPY risk-adjusted (higher Sharpe).
- **H-B · 200-DMA trend filter** (`strat_trend_200dma`, horizon 5d). *Hypothesis:* NOT an alpha claim — tests whether being long only above the 200-day MA gives SPY-like return with materially **lower drawdown** (risk-managed beta). *Success:* maxDD meaningfully smaller than buy-hold SPY at comparable CAGR.
- **H-C · 12-1 cross-sectional momentum** (`strat_xsec_momentum`, **run with `HORIZON=21`**). *Hypothesis:* the classic momentum anomaly — top trailing-12-month (skip last month) names continue. *Success:* same bar as H-A.

> Honest prior, stated up front: low. H-A and H-C are real documented anomalies but weak, crowded, and largely arbitraged in liquid large-caps — finding nothing significant is the likely and honest outcome. H-B should "work" only in the narrow drawdown sense. Writing this down *now* is the point: it stops a post-hoc "I always thought H-X would work."

## v2 results — 2026-06-06 (the "wins" are SURVIVORSHIP BIAS, not edge)

| Hypothesis | OOS hit edge | p | OOS CAGR vs SPY | maxDD | Sharpe | formal verdict |
|---|---|---|---|---|---|---|
| H-A weekly reversal | +3.7% | 0.004 | +43.0% vs +22.7% | -23% | 1.42 | passes the bar |
| H-B 200-DMA trend | **−1.3%** | 0.000 | +20.2% vs +22.7% (**LAGS**) | -20% | 1.40 | **FAILS** |
| H-C 12-1 momentum | +5.0% | ~0 | **+67.5%** vs +22.7% | -31% | 1.64 | passes the bar |

**Two "passing" is a red flag, not a victory.** The result is dominated by **survivorship bias**: the 30-name universe was hand-picked in June 2026, so it's *today's* mega-cap winners (NVDA, AVGO, META, AMD, MSFT…). Backtesting "buy strength/dips in these names" over 2018–26 is circular — we already know they went up; that's *why* they're in the universe. The tell is the ordering: the strategy that concentrates hardest into winners (**H-C momentum**) looks best, exactly as survivorship predicts (momentum > reversal > trend). The p-values are real arithmetic, but they test edge against a base rate computed on the *same* survivor universe — significance can't rescue a result from the selection bias the metric is blind to.

**Verdict: do not trust H-A/H-C; H-B fails outright.** The deepest lesson of the whole eval arc: statistical significance is *necessary, not sufficient* — you must also rule out the structural bias the test can't see. The harness passed its formal checks; the final human gate ("what bias explains this?") is what saves the day.

**Decisive next test (pre-registered now):** re-run H-A and H-C on a **survivorship-free universe** — sector ETFs only (`SPY, QQQ, XLF, XLK, XLE, XLV, XLY, XLP, XLI, XLU`). ETFs don't delist for bad performance, so no single-name survivorship. *If the edge survives on sector ETFs → credible. If it collapses → it was survivorship.* Honest expectation: it largely collapses.

## v3 fix — point-in-time universe (2026-06-06)

The proper fix for the survivorship bias above. `backtest.py` now has `UNIVERSE_MODE`:

- **`snapshot2018`** (default, runnable now) — a ~75-name large-cap universe fixed as of the 2018 START, deliberately including the *laggards* (GE, IBM, INTC, T, WBA, KHC, F, GM…) alongside the winners. No 2026 hindsight in the pick, so the dominant survivorship driver is removed.
- **`etf`** — sector ETFs only; fully survivorship-free (ETFs don't delist for performance). The cleanest free control.
- **`pit_csv`** — gold standard: true point-in-time index membership from a free constituents CSV (download once, e.g. github.com/fja05680/sp500 → set `PIT_CSV`). Only trades names that were index members as-of each date.
- **`winners2026`** — the old biased list, kept to reproduce the trap.

> **Honest free-data limit:** even point-in-time *membership* can't fully fix delisted *prices* — yfinance has no data for names that delisted, so the dogs that went to zero are still missing. A truly survivorship-free single-name backtest needs paid data (CRSP / Norgate / Sharadar). `snapshot2018` + `etf` are the best *free* approximations; treat single-name results as suggestive, not proof.

**Pre-registered re-test (committed 2026-06-06, before running):** run H-A (`strat_weekly_reversal`, h=5) and H-C (`strat_xsec_momentum`, h=21) under both `snapshot2018` and `etf`. *Expectation, on record now: the OOS edge shrinks materially vs the winners2026 universe — H-C momentum shrinks most, since it concentrated into the hindsight winners. An edge that survives on BOTH de-biased universes at p<.017 after costs is worth a closer look; otherwise it was survivorship.*

## v3 results — full 2×2 de-biasing battery (2026-06-08) · VERDICT: no deployable edge

Four runs completed: {H-A weekly reversal, H-C 12-1 momentum} × {`snapshot2018` de-biased single names, `etf` survivorship-free control}, plus the earlier `winners2026` biased baseline for reference. OOS is the only column that counts.

| Strategy × universe | OOS edge | p | OOS port vs SPY | IS↔OOS stable? |
|---|---|---|---|---|
| Reversal × winners2026 | +3.7% | .004 | beats | — |
| Reversal × **snapshot2018** | +4.5% | <.001 | beats | **NO** — IS edge +0.1% (p=.91), **−55% IS maxDD** |
| Reversal × **etf (control)** | +0.9% | **.49** | **LAGS** | NO — insignificant both halves |
| Momentum × winners2026 | +5.0% | <.001 | beats | — |
| Momentum × **snapshot2018** | +5.9% | <.001 | beats | **YES** — IS +3.6% (p<.001), beats SPY both halves |
| Momentum × **etf (control)** | +0.7% | **.50** | **LAGS** | NO OOS (sig IS, dead OOS) |

**H-A weekly reversal → dead.** Insignificant on the survivorship-free ETF control (p=.49, lags SPY both halves), and on de-biased single names it's regime-fragile: *zero* edge in-sample with a **−55% drawdown** through 2020/2022. It "works" only in bull-dip regimes and gets vaporized in crashes. Catching falling knives. Do not pursue.

**H-C 12-1 momentum → the only real signal, but not deployable.** On the de-biased single-name universe it's significant (p<0.001) **and beats SPY in BOTH the in-sample and out-of-sample halves** — the cross-period robustness reversal lacked, and the signature of the genuine, decades-documented stock-momentum anomaly. It *failed* the sector-ETF control OOS (p=.50) — **but that's a weak test for momentum, not a disproof**: cross-sectional momentum needs breadth (many names to rank); 10 correlated sector ETFs can't express it. The honest read is "real single-name effect, wrong control," not "edge disproven." It is still **not deploy-ready**: survivorship is reduced-not-eliminated (snapshot2018 still omits names that delisted to zero, flattering any long strategy); 5bps understates real momentum turnover/capacity; momentum-crash risk (2009/2020-style) is underweighted in this window; it's long-only here so part of the return is bull-decade beta; and it's the most-published, most-crowded anomaly on earth.

**Pre-registered prediction — scored honestly (I was wrong).** I committed: *"OOS edge shrinks materially; H-C momentum shrinks most."* Reality: H-A reversal collapsed on the proper control, but **momentum HELD and was the most robust** result — significant and SPY-beating in both halves on the de-biased universe. My forecast missed; momentum looks more real than I gave it credit for. Logging the miss is the point of pre-registration.

**Meta-lesson — the battery worked, and no single check would have.** The ETF control killed reversal; the IS/OOS split exposed reversal's −55% fragility *and* confirmed momentum's stability; the de-biased universe tested survivorship; pre-registration forced a wrong prediction onto the record. Different gates caught different things. That layered rigor — the same eval discipline as the KB — is what separates research from backtest-mining.

**Decision (2026-06-08): experiment closed.** No edge clears all gates (significance + IS/OOS stability + survives a survivorship-free control). That is a **successful, money-saving null result.** Stock momentum is the only thing showing a real signal; everything else was survivorship or regime luck. Not deploying anything off these backtests. A true single-name, survivorship-free momentum stress-test (paid PIT data + realistic costs + momentum-crash windows + capacity) is the *only* path that could change this verdict — deferred, not scheduled.

## v1 first run — 2026-06-06 · `strat_dip_reversion` (verdict: NO proven edge)

| | trades | hit | baseline | edge | p | avg realized | "cumulative" |
|---|---|---|---|---|---|---|---|
| In-sample (2021→24-06) | 406 | 44.8% | 44.6% | +0.3% | 0.91 | +0.22% | +89% |
| **Out-of-sample** (24-06→26-06) | 210 | 48.6% | 44.6% | +4.0% | **0.24** | +1.51% | +316% |

**Verdict: fails the bar.** By the harness's own rule (beat baseline **AND** significant **AND** survive costs), dip-reversion does **not** clear it — the hit-rate edge is not significant in either period (p=0.91, p=0.24). No deployable edge demonstrated.

**Why the "+316% cumulative" is a trap, not a win** — the exact self-deception this harness exists to expose:
1. **Hit-rate ≈ baseline, but avg return is +** → the payoff is right-skewed (big dips that bounce, bounce hard). Real, but it's a *payoff shape*, not predictive edge.
2. **The cumulative is overstated.** "Cumulative (equal-size)" sums per-trade returns, but the 210 trades **overlap** (many names dip the same day, 5-day holds run concurrently) — you can't take them all at full size. It is **not** a deployable equity curve. (Known limitation — see below.)
3. **Bull-market drift.** The OOS window was a strong up-market; "buy the dip" rides the market's upward drift, which is beta, not alpha. The edge *over the up-rate baseline* is what counts, and it's noise.
4. **`high` tier (53.8% hit, +1.82%)** looks better but n=52 and we're now slicing within one run — underpowered + multiple-comparisons. Promising-but-unproven, not a green light.

Bottom line: the *harness* works perfectly; *this strategy* doesn't. That's a successful run — it stopped you from deploying a +316% mirage.

## Known limitations (be honest about these)

- **Overlapping-trade cumulative** overstates returns (see above). A faithful equity curve needs one-position-at-a-time or explicit capital allocation across concurrent signals — a worthwhile next upgrade.
- **Survivorship bias** (yfinance current tickers only) and **multiple comparisons** (every new strategy is a fresh p<0.05 coin-flip — try 20, one "works" by chance). Pre-commit to a hypothesis, or correct for the number tried.

## See also

- [[prediction-loop]] — the forward (live) version of this loop · [[benchmark-plan]] — the gate to going live
- [[../../research/ai-evals/kb/eval-statistics]] · [[../../research/ai-evals/kb/benchmark-contamination]]
