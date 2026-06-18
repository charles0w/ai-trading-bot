---
name: strategy-research-2026-06-16
type: research
parent: ai-trading-bot
date: 2026-06-16
updated: 2026-06-16
tags:
  - ai-trading-bot
  - research
  - strategy
  - options
  - evidence
---

# Strategy research — what actually works, and what to build first (2026-06-16)

> [!summary] The honest headline
> Net of realistic option bid-ask spreads (5–15% **per side**) and post-publication decay, the *average* documented market anomaly nets ≈**4 bps/month** — effectively zero — and most retail options traders lose **5–9% per trade**. **Our backtest's null result is the modal outcome, not bad luck.** The single most robust options-native edge (the **variance risk premium**) pays the *seller*, which means a v1 bot that only **buys** calls/puts is fighting a documented structural headwind. Within that constraint, the one long-premium configuration with replicated academic support and a structure that actually fits long options is **post-earnings drift entered *after* the IV crush**. That's the recommended Phase-1 strategy — with momentum/52-week-high and the call-minus-put volatility spread as confirming features, and a serious recommendation to scope the **defined-risk short-premium** upgrade (higher Alpaca option levels) as the real long-term edge.

Feeds [[pivot-2026-06-16]]. Respects the [[backtest]] null result. Research method: 5 parallel evidence sweeps (momentum, PEAD/event, VRP/short-premium, flow/IV-timing, anomaly-decay meta), adversarially weighted toward replicated peer-reviewed evidence over backtested-blog claims.

---

## 1. The base rate: assume no edge until proven net-of-cost

This is the frame for everything below. The meta-evidence is brutal and should haircut every backtest we ever run:

- **Post-publication decay ≈ 58%.** Published predictors fall ~26% out-of-sample and ~58% after publication (McLean & Pontiff, *JF* 2016). Rule of thumb: **halve any backtested edge** before believing it forward.
- **Most "anomalies" are noise.** The correct significance hurdle after multiple testing is **t > ~3.0, not 2.0** (Harvey-Liu-Zhu). Hou-Xue-Zhang: 65% of 452 anomalies fail even t>1.96, 82% fail the multiple-testing bar; **96% of "trading-frictions" anomalies fail** once microcaps are removed.
- **Costs finish the job.** Only strategies with **<50% monthly turnover** tend to survive costs (Novy-Marx & Velikov). Chen & Velikov: net of spreads + decay, the average anomaly nets **~4 bps/month**, the strongest ~10 bps — before price impact.
- **Options costs are far worse than equities.** Retail option spreads routinely exceed **23% of the trade**; a Stanford study finds retail option traders lose **~5–9% per trade** (up to 16% over 3 days). A ~65% *win rate* still produced net losses (winners +1.2%, losers −2.8%) — **high hit-rate strategies are the ones most likely to fool you.**

> [!danger] The takeaway
> Take any backtest → **halve it for decay → subtract 5–15% option spread per side**. If it isn't still clearly positive, it isn't an edge. This is exactly why the paper-trial gate in [[pivot-2026-06-16]] must measure P&L *net of modeled slippage and commissions*, not mid-price fantasy.

---

## 2. The central tension: long premium is a structurally taxed position

The most replicated edge in all of options is the **variance risk premium (VRP)**: implied vol exceeds subsequently realized vol **~85% of the time** (a persistent ~3-vol-point gap). The mechanism is insurance demand — investors overpay for protection, and *sellers* collect.

- Zero-beta ATM straddles lose **~3% per week** on average — i.e., **buyers systematically lose** (Coval & Shumway, 2001), replicated via the "overpriced puts puzzle," variance-swap premia, and the general "selling insurance pays" finding (Ilmanen/AQR). Quantpedia rates VRP confidence **"Strong."**
- The CBOE **PutWrite (PUT)** index returned **10.13%/yr since 1986 at ~⅔ the volatility** of the S&P (max drawdown 32.7% vs 50.9%). But the catch is the whole story: it's **short a fat left tail** — Volmageddon (5 Feb 2018) wiped **>90% off short-vol ETPs in a single day**; much of the apparent outperformance is just equity beta (Israelov-Nielsen).

> [!important] What this means for *our* v1
> Buying calls/puts means **paying the very premium that sellers harvest.** A long-options bot wins only in the minority of cases where the move is **large, fast, and underpriced** — it needs to be right on **direction AND magnitude AND timing**. Israelov/Tummala: buying 1-month SPX options was profitable **only in the top decile of vol increases** and lost in the bottom seven. The strategically sound long-term path points toward **selling defined-risk premium** (cash-secured puts / spreads), not buying it. We can still build a disciplined long-options bot (Alpaca Level 2) — but only by hunting the specific conditions where long premium is +EV (catalysts / mispriced expected moves), never "buy cheap vol and hope."

---

## 3. Strategy-by-strategy evidence

| Strategy | Evidence quality | Natural horizon | Long-call/put fit | Verdict for v1 |
|---|---|---|---|---|
| **PEAD, post-IV-crush** | Strong (most-replicated equity anomaly) but decayed + cost-sensitive | 3–6 weeks drift | **Good** — enter after crush = cheap premium; drift is directional | **Best Phase-1 fit** |
| **Momentum (12-1 / 52-wk-high)** | Strongest-replicated factor; but gross, pre-decay | Months (not weeks) | **Poor** unless high-delta LEAPS | Confirming feature |
| **Volatility spread (call IV − put IV)** | Rigorous (Cremers-Weinbaum ~50bp/wk) but decayed; best signed-flow not cheap | ~1 week | Feature, not a structure | Confirming feature |
| **VRP / short premium** | **Strongest options-native edge** | Monthly | **Not executable in v1** (CSP = L1, spreads/condors = L3) | Future upgrade — the real edge |
| **Put-call ratio / UOA / GEX / IV-rank timing** | Weak / folklore / intraday / vendor-marketing | 1 day–1 wk | Noise at swing horizon | Mostly discard |
| **Merger arb / FDA binaries** | Arb real but not a long-option structure; biotech ≈ gambling | Deal-bound | Poor | Out of scope |

**Momentum.** The most replicated anomaly (12-1 winners earned ~1.0–1.3%/mo gross, survived 30 yrs / 40 countries per AQR), but: (1) the underlying drift is a *slow grind* far too gentle to pay for short-dated theta; (2) at sub-month horizons stocks **reverse, not trend** (so any formation must skip the recent month); (3) it carries forecastable **crash risk** (−45.6% in 2009) in post-decline/high-VIX rebounds — a naked long-call momentum book is exposed exactly there. Only plausible via **high-delta, long-dated (60–120+ DTE) options, vol-scaled, with a VIX/regime kill-switch.** → secondary confirmation, not standalone.

**PEAD / earnings drift.** Bernard-Thomas SUE spread ~8–9%/quarter gross, drifting ~60 trading days; positive in 41/48 quarters. **But** ~58% decayed and **70–100% eaten by costs**, with surviving alpha trapped in illiquid small caps (where option spreads are 10–30%+). The IV dimension is decisive: post-earnings **IV crush averages ~38%**, so a correct directional call held *through* the print can still lose on vega. The **one defensible long-option config**: enter long calls/puts **T+1/T+2, after the crush**, on **liquid** names with a **strong SUE + confirming analyst-revision** signal — you buy cheap directional premium and harvest only the drift. This is the rare spot where structure (cheap post-crush premium, multi-week directional drift) and signal (replicated underreaction) actually align with long options.

**Volatility spread (Cremers-Weinbaum).** The most rigorously documented options→equity signal: stocks with relatively expensive calls beat those with expensive puts by **~50bp/week**. But the authors themselves report it decaying over the sample, and the *genuinely* predictive part (Pan-Poteshman: buyer-initiated, position-opening flow) is **not in cheap retail data**. Use the computable version (call IV − put IV and its change) as a **confirmation feature**, not a trigger.

**Flow / IV-rank / GEX.** Put-call ratio edge decays within days; "unusual options activity" feeds are largely **marketing on a noise base** (and reverse once media-reported); IV-rank-as-timing is **broker-blog folklore** (low IV is often low *because* the stock won't move — still loses to theta); GEX is a real **intraday** effect with no swing-horizon directional edge. → at most one or two confirming features; mostly discard.

---

## 4. Evidence-ranked shortlist

1. **PEAD post-IV-crush directional drift** (liquid large-caps) — *best long-option fit with real evidence.*
2. **Defined-risk short premium / VRP** (IV-timed, tail-capped) — *strongest edge overall, but needs higher option levels (CSP at L1, spreads/condors at L3).*
3. **52-week-high / residual momentum** via high-delta long-dated options — *durable signal, weak as a long-option standalone; best as a confirmation layer.*
4. **Volatility-spread (call−put IV) tilt** — *a feature, not a standalone strategy.*
5. *(Discard for now)* PCR / UOA / GEX / IV-rank timing — *folklore or wrong horizon.*

---

## 5. Recommended Phase-1 strategy

> [!important] Build first: **PEAD, entered after the earnings IV crush, on liquid optionable names — as a hybrid ML+LLM intersection trade.**

Rationale: it is the **only** candidate that is simultaneously (a) backed by replicated peer-reviewed evidence, (b) **catalyst-driven** — the regime where long premium is *least* disadvantaged because there's a real, datable expected move, (c) structurally aligned with long calls/puts when entered **post-crush** (cheap premium + multi-week directional drift), and (d) a clean fit for the architecture in [[pivot-2026-06-16]]: the **ML layer** scores the drift probability from SUE + revisions + history; the **LLM analyst** reads the report/guidance for narrative confirmation; the **intersection rule** only fires when both agree on a *liquid* name with acceptable spread.

Hard rules baked in from the evidence:
- **Enter T+1/T+2 only** — never hold long premium *through* a print (IV-crush tax).
- **Liquidity filter is non-negotiable** — only tight-spread, high-OI underlyings (mega-caps, liquid ETFs); the academic edge that survives in illiquid names is uncapturable at retail spreads.
- **Cost-first grading** — model 5–15%/side spread + slippage in every paper fill; the go-live gate must beat naive "buy ATM call on every signal" *and* SPY net of those costs.
- **Structure:** near-ATM, ~30–45 DTE to give the 3–6 week drift room without peak theta bleed.
- **Regime kill-switch:** stand down in high-VIX/risk-off tape where drift reverses and long premium gets repriced.

> [!warning] The strategic decision you should make consciously
> The research says the **real** options edge is *selling* premium (VRP), which v1 can't do. Recommended sequencing: prove the PEAD-post-crush long strategy on paper as Phase 1 (it's the best long-only bet), **and in parallel scope the short-premium upgrade** (defined-risk: cash-secured puts / iron condors, IV-percentile-timed, tail-capped — higher Alpaca option levels) as Phase 2's likely center of gravity. If after a paper trial the long-only edge is thin (the base rate says it will be), the short-premium path is where the durable edge actually lives. Decide now whether v1 is "the strategy" or "the on-ramp to the strategy."

---

## 6. Data + ML features this requires

**Data sources (cost reality):**
- `yfinance` — free, but **snapshot-only chains, no history, no signed flow** → inadequate beyond prototyping.
- **Polygon (~$79/mo)** — tick-level options history to 2014 with IV/Greeks → the realistic **floor for backtesting** the IV-spread and post-crush features.
- Earnings calendar + estimates/revisions: FMP / Finnhub / Nasdaq (free-to-cheap tiers).
- Signed/initiated flow (the truly alpha-bearing data) is **hundreds/mo** and **not worth it at this stage** — edge is thin and decaying.

**ML features (PEAD model):** SUE (actual − consensus, scaled by surprise std), analyst-revision breadth & magnitude, pre/post-print IV term structure & IV rank, **realized-vs-implied move history** (does this name usually move less than priced?), post-crush IV level, drift-to-date, liquidity/spread + OI filters, sector/market regime (trend + VIX). **Confirmation features (cross-strategy):** 12-1 & 52-week-high momentum (recent-month skipped), call-minus-put **volatility spread** and its change.

---

## Sources

Momentum: [Jegadeesh-Titman](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf) · [TSMOM (Moskowitz-Ooi-Pedersen)](https://elmwealth.com/wp-content/uploads/2017/06/timeseriesmomentum.pdf) · [Momentum crashes (Daniel-Moskowitz)](https://www.nber.org/system/files/working_papers/w20439/w20439.pdf) · [52-week-high (George-Hwang)](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf) · [AQR Fact/Fiction/Momentum](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Momentum-Investing.pdf)
PEAD/event: [Bernard-Thomas review](https://jkatz.caltech.edu/documents/28622/peads.pdf) · [Quantpedia PEAD](https://quantpedia.com/strategies/post-earnings-announcement-effect) · [Transaction costs & PEAD (Minnesota)](https://experts.umn.edu/en/publications/implications-of-transaction-costs-for-the-post-earnings-announcem/) · [Liquidity & PEAD (FAJ)](https://www.tandfonline.com/doi/abs/10.2469/faj.v65.n4.3) · [IV crush](https://www.ipresage.com/research/earnings-iv-crush) · [Post-crush drift config](https://optionspilot.app/blog/post-earnings-drift-options-trading-strategy)
VRP/short premium: [Eraker, Volatility Premium](http://www.marginalq.com/eraker/volPremiumPaperJune08.pdf) · [Coval-Shumway](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=189840) · [Bondarenko PutWrite](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2750188) · [Israelov-Nielsen Covered Calls Uncovered](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2444999) · [Volmageddon (FAJ)](https://rpc.cfainstitute.org/research/financial-analysts-journal/2021/volmageddon-failure-short-volatility-products) · [Quantpedia VRP](https://quantpedia.com/strategies/volatility-risk-premium-effect)
Flow/IV: [Cremers-Weinbaum vol spread](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968237) · [Pan-Poteshman](https://www.mit.edu/~junpan/volume.pdf) · [Jiang-Strong UOA](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3618427) · [Long straddle through earnings backtest](https://steadyoptions.com/articles/long-straddle-through-earnings-backtest-r342/)
Meta/decay/costs: [McLean-Pontiff](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623) · [Harvey-Liu-Zhu](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2249314) · [Hou-Xue-Zhang Replicating Anomalies](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2961979) · [Chen-Zimmermann OSAP](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3604626) · [Novy-Marx-Velikov](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2535173) · [Chen-Velikov net anomaly returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3073681) · [Stanford retail option losses](https://www.gsb.stanford.edu/faculty-research/working-papers/losing-optional-retail-option-trading-expected-announcement)
