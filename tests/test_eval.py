from __future__ import annotations

from datetime import date

from atb.eval.grading import directional_return_pct, grade, grade_due
from atb.eval.judge import Judge, parse_judge
from atb.eval.predictions import Prediction, PredictionLog
from atb.eval.reliability import brier, calibration_buckets, expectancy, hit_rate, summary


# --- prediction log roundtrip ---

def test_predictionlog_roundtrip(tmp_path):
    log = PredictionLog(tmp_path / "p.jsonl")
    log.append(Prediction(id="a", date="2026-06-10", symbol="NVDA", direction="up",
                          horizon_days=5, entry_ref=200.0, conviction=0.7))
    log.append(Prediction(id="b", date="2026-06-11", symbol="SPY", direction="down",
                          horizon_days=5, entry_ref=740.0, conviction=0.6))
    assert len(log.load()) == 2
    assert log.update("a", status="graded", correct=True, return_pct=3.0)
    reloaded = {p.id: p for p in log.load()}
    assert reloaded["a"].status == "graded" and reloaded["a"].correct is True
    assert reloaded["b"].status == "open"


# --- grading ---

def test_grade_up_and_down():
    assert grade("up", 100, 110) == (True, 10.0)
    assert grade("down", 100, 90) == (True, 10.0)
    assert grade("up", 100, 90) == (False, -10.0)
    assert directional_return_pct("long_put", 100, 90) == 10.0


def test_grade_due_only_matured(tmp_path):
    log = PredictionLog(tmp_path / "p.jsonl")
    log.append(Prediction(id="old", date="2026-06-05", symbol="NVDA", direction="up",
                          horizon_days=5, entry_ref=100.0))
    log.append(Prediction(id="new", date="2026-06-16", symbol="SPY", direction="up",
                          horizon_days=5, entry_ref=100.0))
    graded = grade_due(log, lambda s: 110.0, asof=date(2026, 6, 17))
    assert graded == ["old"]
    rows = {p.id: p for p in log.load()}
    assert rows["old"].status == "graded" and rows["old"].correct is True
    assert rows["new"].status == "open"


# --- reliability ---

def _graded(direction, entry, exit_, conv):
    correct, ret = grade(direction, entry, exit_)
    return Prediction(id="x", date="2026-06-10", symbol="S", direction=direction,
                      horizon_days=5, entry_ref=entry, conviction=conv,
                      status="graded", exit_ref=exit_, correct=correct, return_pct=ret)


def test_reliability_metrics():
    preds = [
        _graded("up", 100, 110, 0.8),   # correct +10
        _graded("up", 100, 95, 0.7),    # wrong -5
        _graded("down", 100, 90, 0.6),  # correct +10
    ]
    assert abs(hit_rate(preds) - 2 / 3) < 1e-9
    assert abs(expectancy(preds) - (10 - 5 + 10) / 3) < 1e-9
    assert brier(preds) is not None
    assert summary(preds)["n_graded"] == 3


def test_calibration_buckets():
    preds = [_graded("up", 100, 110, 0.85), _graded("up", 100, 120, 0.82)]
    buckets = calibration_buckets(preds)
    assert buckets and buckets[0]["n"] == 2 and buckets[0]["hit_rate"] == 1.0


# --- judge ---

def test_judge_parses_scores():
    raw = '{"faithfulness":0.9,"completeness":0.8,"calibration":0.7,"actionability":0.6,"overall":0.78,"rationale":"ok"}'
    js = Judge(lambda prompt: raw, provider="ollama").score("analysis", "data")
    assert js.overall == 0.78 and js.rubric["faithfulness"] == 0.9


def test_judge_unparseable_is_zero():
    assert parse_judge("no json here").overall == 0.0
