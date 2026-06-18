from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..features import FeatureVector


@dataclass
class SignalOutput:
    direction: str                 # "up" | "down" | "flat"
    probability: float             # P(chosen direction correct); 0.5 = no edge
    expected_move: float | None    # fractional move estimate, optional
    rationale: str
    model_version: str
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Signal(Protocol):
    """A model that scores a FeatureVector into a directional SignalOutput.
    The heuristic model below is v0; a trained model can implement the same
    interface and be swapped in without touching the pipeline."""

    def score(self, fv: FeatureVector) -> SignalOutput: ...
