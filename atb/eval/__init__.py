"""Eval system: log every call, grade it against outcomes, track reliability,
and (optionally) judge recap/thesis quality with a cross-family LLM.

This is the gate keeper of the whole project — the go-live decision in
pivot-2026-06-16 rests on these numbers (hit rate, expectancy, calibration)
being real net of costs over a meaningful sample.
"""

from __future__ import annotations

from .grading import grade, grade_due, directional_return_pct
from .judge import Judge, JudgeScore, parse_judge
from .predictions import Prediction, PredictionLog
from .reliability import calibration_buckets, expectancy, hit_rate, brier, summary

__all__ = [
    "Prediction", "PredictionLog",
    "grade", "grade_due", "directional_return_pct",
    "hit_rate", "expectancy", "brier", "calibration_buckets", "summary",
    "Judge", "JudgeScore", "parse_judge",
]
