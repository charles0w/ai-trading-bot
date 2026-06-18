"""The 'brain': ML-style signal + LLM analyst + intersection rule.

Pipeline of the brain:
    features -> Signal.score()  ->\
                                    intersection.combine() -> TradeIntent | None
    features -> LLMAnalyst.analyze() ->/

Only trades when the (heuristic/ML) signal and the LLM thesis AGREE and both
clear their thresholds (the two-signal rule from the polymarket sibling).
"""

from __future__ import annotations

from .base import Signal, SignalOutput
from .intersection import combine
from .llm_analyst import LLMAnalyst, Thesis, parse_thesis
from .pead_model import PeadHeuristicModel

__all__ = ["Signal", "SignalOutput", "PeadHeuristicModel", "LLMAnalyst",
           "Thesis", "parse_thesis", "combine"]
