"""Intersection rule: trade only when the ML signal and the LLM thesis AGREE
and both clear their thresholds. Produces a TradeIntent or None.

This is the two-signal gate — the single most important risk control in the
brain. Either model alone is noise; requiring agreement is what makes the bot
selective (and most days it should produce no trade)."""

from __future__ import annotations

from ..features import FeatureVector
from trader_core.execution.intent import LONG_CALL, LONG_PUT, TradeIntent
from .base import SignalOutput
from .llm_analyst import Thesis

_DIR_TO_INTENT = {"up": LONG_CALL, "down": LONG_PUT}


def combine(
    signal: SignalOutput,
    thesis: Thesis,
    fv: FeatureVector,
    *,
    target_dte: int = 35,
    strike_rule: str = "ATM",
    min_probability: float = 0.55,
    min_conviction: float = 0.50,
) -> TradeIntent | None:
    if signal.direction not in _DIR_TO_INTENT:        # flat
        return None
    if thesis.direction != signal.direction:          # must agree
        return None
    if signal.probability < min_probability:
        return None
    if thesis.conviction < min_conviction:
        return None

    conviction = (signal.probability + thesis.conviction) / 2.0
    return TradeIntent(
        underlying=fv.symbol,
        direction=_DIR_TO_INTENT[signal.direction],
        target_dte=target_dte,
        strike_rule=strike_rule,
        signal_id=f"{fv.asof.isoformat()}-{fv.symbol}-pead",
        price_ref=None,
        conviction=conviction,
        meta={
            "strategy": "pead",
            "ml_version": signal.model_version,
            "ml_probability": signal.probability,
            "llm_conviction": thesis.conviction,
            "llm_rationale": thesis.rationale,
            "sue": fv.sue,
            "post_earnings_return": fv.post_earnings_return,
            "days_since_earnings": fv.days_since_earnings,
        },
    )
