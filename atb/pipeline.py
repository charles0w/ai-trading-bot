"""End-to-end brain pipeline for one symbol:

    features -> ML signal -> LLM thesis -> [log each non-flat thesis]
            -> intersection -> [log combined intent] -> resolve contract
            -> risk gate -> size -> (paper) execute -> [stamp decision stage]

Predictions are logged at THESIS time, not fill time: every non-flat ML/LLM
call and every intersection intent is gradeable data for the go-live gate,
regardless of whether a trade survives contract/risk/sizing.

Everything is injected (provider, signal, analyst, broker, store, predlog) so the
whole thing runs offline with fakes in tests and live on the Mac with real
Alpaca + Finnhub + Anthropic. Defaults to DRY RUN — pass execute=True to place.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from trader_core.config import Config
from trader_core.execution.executor import execute_entry
from trader_core.execution.intent import LONG_CALL, TradeIntent
from trader_core.execution.resolver import resolve_contract
from trader_core.execution.risk import PT, RiskState, approve
from trader_core.execution.sizing import size_position

from .eval.predictions import Prediction, PredictionLog
from .features import compute_features
from .signal.intersection import combine


@dataclass
class Decision:
    symbol: str
    decision: str                 # no_trade | rejected | dry_run | placed
    reason: str = ""
    features: Any = None
    signal: Any = None
    thesis: Any = None
    intent: TradeIntent | None = None
    contract: Any = None
    sizing: Any = None
    prediction_id: str | None = None
    position_id: int | None = None
    extra: dict = field(default_factory=dict)


def _open_exposure_usd(store) -> float:
    return sum(float(p["entry_price"]) * int(p["quantity"]) * 100
               for p in store.open_positions())


_UPDOWN = {"up", "down"}


def _log_component_theses(predlog: PredictionLog, symbol: str, asof: date,
                          fv, so, th, horizon: int) -> None:
    """Thesis-level logging (2026-07-27): every non-flat ML signal and LLM
    thesis is logged as its own gradeable prediction, whether or not a trade
    results. The intersection fires rarely by design, so without this the
    go-live dataset starves; grading a thesis needs no order, and per-component
    rows let the weekly eval score the ML and LLM layers separately."""
    day = asof.isoformat()
    for comp, direction, conv, rationale, extra in (
        ("ml", so.direction, so.probability, so.rationale,
         {"model_version": so.model_version}),
        ("llm", th.direction, th.conviction, th.rationale,
         {"model": th.meta.get("model")}),
    ):
        if direction not in _UPDOWN:
            continue
        pid = f"{day}-{symbol}-{comp}"
        if predlog.has(pid):
            continue  # idempotent across same-day re-runs
        predlog.append(Prediction(
            id=pid, date=day, symbol=symbol, direction=direction,
            horizon_days=horizon, entry_ref=fv.spot, conviction=conv,
            rationale=rationale or "", meta={"component": comp, **extra},
        ))


def _set_stage(predlog: PredictionLog, pred: Prediction, stage: str,
               **extra_meta) -> None:
    predlog.update(pred.id, meta={**pred.meta, "stage": stage, **extra_meta})


def run_symbol(
    symbol: str,
    *,
    provider,
    signal,
    analyst,
    broker,
    store,
    predlog: PredictionLog,
    cfg: Config | None = None,
    asof: date | None = None,
    now_pt: datetime | None = None,
    grade_horizon_days: int = 5,
    execute: bool = False,
) -> Decision:
    cfg = cfg or Config()
    asof = asof or date.today()
    now_pt = now_pt or datetime.now(PT)

    fv = compute_features(provider, symbol, asof=asof)
    if not fv.spot:  # None or 0.0 (e.g. provider returned only partial/NaN bars)
        return Decision(symbol, "no_trade", "no_spot", features=fv)

    so = signal.score(fv)
    th = analyst.analyze(fv)
    _log_component_theses(predlog, symbol, asof, fv, so, th, grade_horizon_days)
    intent = combine(so, th, fv)
    if intent is None:
        return Decision(symbol, "no_trade", "signal_no_trade", features=fv,
                        signal=so, thesis=th)

    # Combined system call — logged at INTENT time (not after sizing) so that
    # contract/risk/sizing rejections still produce gradeable predictions; the
    # decision stage is recorded in meta as the intent progresses.
    pred = Prediction(
        id=intent.signal_id, date=asof.isoformat(), symbol=symbol,
        direction="up" if intent.direction == LONG_CALL else "down",
        horizon_days=grade_horizon_days, entry_ref=fv.spot,
        conviction=intent.conviction, rationale=th.rationale,
        meta={**intent.meta, "component": "combined", "stage": "intent"},
    )
    if not predlog.has(pred.id):
        predlog.append(pred)

    contract = resolve_contract(broker, intent, spot_price=fv.spot, today=asof)
    if contract is None:
        _set_stage(predlog, pred, "no_contract")
        return Decision(symbol, "rejected", "no_contract", features=fv,
                        signal=so, thesis=th, intent=intent, prediction_id=pred.id)
    premium = contract.mid or contract.last
    if premium is None:
        _set_stage(predlog, pred, "no_mark")
        return Decision(symbol, "rejected", "no_mark", features=fv, signal=so,
                        thesis=th, intent=intent, contract=contract,
                        prediction_id=pred.id)
    intent.price_ref = premium

    ok, why = approve(
        state=RiskState(), now_pt=now_pt,
        open_position_count=len(store.open_positions()),
        open_exposure_usd=_open_exposure_usd(store),
        config_trading_account=cfg.trading_account, config_market=cfg.market,
        signal_age_seconds=0,
        spread_pct=contract.spread_pct if hasattr(contract, "spread_pct") else None,
    )
    if not ok:
        _set_stage(predlog, pred, f"risk_rejected:{why}")
        return Decision(symbol, "rejected", f"risk:{why}", features=fv, signal=so,
                        thesis=th, intent=intent, contract=contract,
                        prediction_id=pred.id)

    sz = size_position(
        premium_per_share=premium, sizing_mode=cfg.sizing.mode,
        max_per_trade_usd=cfg.trading_account.max_per_trade_usd,
        max_premium_per_contract=cfg.sizing.max_premium_per_contract,
        max_capital_usd=cfg.trading_account.max_capital_usd,
        current_open_exposure_usd=_open_exposure_usd(store),
        broker_buying_power_usd=broker.buying_power_usd(),
    )
    if sz.contracts == 0:
        _set_stage(predlog, pred, f"sizing_rejected:{sz.reason}")
        return Decision(symbol, "rejected", f"sizing:{sz.reason}", features=fv,
                        signal=so, thesis=th, intent=intent, contract=contract,
                        sizing=sz, prediction_id=pred.id)

    cfg.execution.dry_run = not execute
    pos_id = asyncio.run(execute_entry(store=store, broker=broker, cfg=cfg,
                                       intent=intent, sizing=sz, contract=contract))
    outcome = "placed" if pos_id else ("dry_run" if not execute else "no_fill")
    _set_stage(predlog, pred, outcome,
               occ_symbol=contract.occ_symbol, premium=premium)
    return Decision(
        symbol, "placed" if pos_id else ("dry_run" if not execute else "rejected"),
        "ok" if (pos_id or not execute) else "no_fill",
        features=fv, signal=so, thesis=th, intent=intent, contract=contract,
        sizing=sz, prediction_id=pred.id, position_id=pos_id,
    )
