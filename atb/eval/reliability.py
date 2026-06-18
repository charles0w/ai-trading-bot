"""Reliability + calibration metrics over graded predictions.

hit_rate     — fraction of graded calls that were directionally correct
expectancy   — mean directional return_pct per call
brier        — calibration of conviction vs. outcome (lower is better; needs conviction)
calibration_buckets — hit rate within conviction bands (is 0.7 conviction ~70% right?)
"""

from __future__ import annotations

from .predictions import Prediction


def _graded(preds: list[Prediction]) -> list[Prediction]:
    return [p for p in preds if p.status == "graded" and p.correct is not None]


def hit_rate(preds: list[Prediction]) -> float | None:
    g = _graded(preds)
    return sum(1 for p in g if p.correct) / len(g) if g else None


def expectancy(preds: list[Prediction]) -> float | None:
    g = [p for p in preds if p.return_pct is not None]
    return sum(p.return_pct for p in g) / len(g) if g else None


def brier(preds: list[Prediction]) -> float | None:
    g = [p for p in _graded(preds) if p.conviction is not None]
    if not g:
        return None
    return sum((p.conviction - (1.0 if p.correct else 0.0)) ** 2 for p in g) / len(g)


def calibration_buckets(preds: list[Prediction],
                        edges=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)) -> list[dict]:
    g = [p for p in _graded(preds) if p.conviction is not None]
    out = []
    for lo, hi in zip(edges, edges[1:]):
        bucket = [p for p in g if lo <= p.conviction < hi]
        if bucket:
            out.append({
                "range": f"{lo:.2f}-{hi:.2f}", "n": len(bucket),
                "hit_rate": sum(1 for p in bucket if p.correct) / len(bucket),
            })
    return out


def summary(preds: list[Prediction]) -> dict:
    g = _graded(preds)
    return {
        "n_total": len(preds),
        "n_graded": len(g),
        "hit_rate": hit_rate(preds),
        "expectancy_pct": expectancy(preds),
        "brier": brier(preds),
        "calibration": calibration_buckets(preds),
    }
