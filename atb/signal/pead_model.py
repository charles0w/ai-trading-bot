"""PEAD heuristic signal (v0).

A transparent, dependency-free logistic scorer over the PEAD-relevant features
(SUE, post-earnings drift, 12-1 momentum). It is NOT trained — the weights are
hand-set so the sign/strength behave sensibly — and exists so the pipeline is
end-to-end and testable now. A trained model (logistic/GBM on a labeled
post-earnings dataset) can replace it behind the Signal interface later.

The edge thesis (from strategy-research-2026-06-16): post-earnings drift in the
direction of a strong surprise, confirmed by trend, harvested AFTER the IV
crush. So the model only expresses conviction inside the post-earnings window.
"""

from __future__ import annotations

import math

from ..features import FeatureVector
from .base import SignalOutput

VERSION = "pead-heuristic-v0"


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class PeadHeuristicModel:
    def __init__(self, *, entry_window=(1, 5), w_sue=0.6, w_drift=8.0,
                 w_mom=1.5, bias=0.0):
        self.entry_window = entry_window
        self.w_sue, self.w_drift, self.w_mom, self.bias = w_sue, w_drift, w_mom, bias

    def score(self, fv: FeatureVector) -> SignalOutput:
        lo, hi = self.entry_window
        in_window = fv.days_since_earnings is not None and lo <= fv.days_since_earnings <= hi
        if not in_window:
            return SignalOutput("flat", 0.5, None,
                                "outside post-earnings window", VERSION,
                                {"in_window": False})

        z = self.bias
        if fv.sue is not None:
            z += self.w_sue * _clip(fv.sue, -3, 3)
        if fv.post_earnings_return is not None:
            z += self.w_drift * _clip(fv.post_earnings_return, -0.25, 0.25)
        if fv.mom_12_1 is not None:
            z += self.w_mom * _clip(fv.mom_12_1, -0.5, 0.5)

        p_up = 1.0 / (1.0 + math.exp(-z))
        if abs(p_up - 0.5) < 0.02:
            return SignalOutput("flat", 0.5, None, "no directional edge", VERSION,
                                {"p_up": p_up, "z": z})
        direction = "up" if p_up > 0.5 else "down"
        probability = p_up if direction == "up" else 1 - p_up
        return SignalOutput(
            direction=direction, probability=probability,
            expected_move=fv.post_earnings_return, rationale=f"z={z:.2f}, p_up={p_up:.2f}",
            model_version=VERSION, meta={"p_up": p_up, "z": z, "sue": fv.sue},
        )
