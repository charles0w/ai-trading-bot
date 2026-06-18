"""Trained logistic signal — replaces the heuristic once weights exist.

Same Signal interface as PeadHeuristicModel, but coefficients are LEARNED by
atb/train (gradient-descent logistic regression on labeled post-earnings
events). Loads/saves weights as JSON (data/model.json). Only expresses a view
inside the post-earnings entry window.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from ..features import FeatureVector
from .base import SignalOutput

FEATURES = ["sue", "post_earnings_return", "mom_12_1", "mom_6_1", "realized_vol_20d"]
VERSION = "pead-logistic-v1"


def sigmoid(z: float) -> float:
    if z < -700:
        return 0.0
    if z > 700:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class LogisticSignal:
    weights: dict[str, float]
    bias: float = 0.0
    features: list[str] = field(default_factory=lambda: list(FEATURES))
    version: str = VERSION
    entry_window: tuple[int, int] = (1, 5)

    def _vec(self, fv: FeatureVector) -> dict[str, float]:
        return {f: (float(getattr(fv, f)) if getattr(fv, f, None) is not None else 0.0)
                for f in self.features}

    def _z(self, x: dict[str, float]) -> float:
        return self.bias + sum(self.weights.get(f, 0.0) * x.get(f, 0.0) for f in self.features)

    def score(self, fv: FeatureVector) -> SignalOutput:
        lo, hi = self.entry_window
        if fv.days_since_earnings is None or not (lo <= fv.days_since_earnings <= hi):
            return SignalOutput("flat", 0.5, None, "outside post-earnings window",
                                self.version, {"in_window": False})
        x = self._vec(fv)
        p_up = sigmoid(self._z(x))
        if abs(p_up - 0.5) < 0.02:
            return SignalOutput("flat", 0.5, None, "no directional edge", self.version,
                                {"p_up": p_up})
        direction = "up" if p_up > 0.5 else "down"
        probability = p_up if direction == "up" else 1 - p_up
        return SignalOutput(direction, probability, x.get("post_earnings_return") or None,
                            f"p_up={p_up:.2f}", self.version, {"p_up": p_up})

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "weights": self.weights, "bias": self.bias, "features": self.features,
            "version": self.version, "entry_window": list(self.entry_window),
        }, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "LogisticSignal":
        d = json.loads(Path(path).read_text())
        return cls(weights=d["weights"], bias=d.get("bias", 0.0),
                   features=d.get("features", list(FEATURES)),
                   version=d.get("version", VERSION),
                   entry_window=tuple(d.get("entry_window", (1, 5))))
