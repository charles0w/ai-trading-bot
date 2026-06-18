from __future__ import annotations

from datetime import date

from atb.features import FeatureVector
from atb.signal.base import SignalOutput
from atb.signal.intersection import combine
from atb.signal.llm_analyst import LLMAnalyst, Thesis, parse_thesis
from atb.signal.pead_model import PeadHeuristicModel
from trader_core.execution.intent import LONG_CALL, LONG_PUT


def _fv(**kw):
    base = dict(symbol="NVDA", asof=date(2026, 6, 17), spot=200.0,
                days_since_earnings=2, post_earnings_return=0.06, sue=2.5, mom_12_1=0.2)
    base.update(kw)
    return FeatureVector(**base)


# --- heuristic model ---

def test_model_up_on_positive_surprise_and_drift():
    out = PeadHeuristicModel().score(_fv())
    assert out.direction == "up" and out.probability > 0.5


def test_model_down_on_negative_surprise_and_drift():
    out = PeadHeuristicModel().score(_fv(sue=-2.5, post_earnings_return=-0.06, mom_12_1=-0.2))
    assert out.direction == "down" and out.probability > 0.5


def test_model_flat_outside_window():
    out = PeadHeuristicModel().score(_fv(days_since_earnings=30))
    assert out.direction == "flat" and out.probability == 0.5


# --- LLM analyst parsing ---

def test_parse_thesis_good_json():
    th = parse_thesis('Here: {"direction":"up","conviction":0.7,"rationale":"strong SUE"}')
    assert th.direction == "up" and th.conviction == 0.7


def test_parse_thesis_malformed_falls_back_flat():
    th = parse_thesis("the model rambled with no json")
    assert th.direction == "flat" and th.conviction == 0.0


def test_analyst_uses_injected_completion():
    analyst = LLMAnalyst(lambda prompt: '{"direction":"up","conviction":0.8,"rationale":"x"}')
    th = analyst.analyze(_fv())
    assert th.direction == "up" and th.conviction == 0.8


# --- intersection ---

def _sig(direction="up", probability=0.7):
    return SignalOutput(direction, probability, 0.05, "r", "v0")


def test_combine_agreement_makes_intent():
    intent = combine(_sig("up", 0.7), Thesis("up", 0.8, "r"), _fv())
    assert intent is not None and intent.direction == LONG_CALL
    assert 0.5 < intent.conviction <= 1.0


def test_combine_disagreement_blocks():
    assert combine(_sig("up", 0.7), Thesis("down", 0.9, "r"), _fv()) is None


def test_combine_low_probability_blocks():
    assert combine(_sig("up", 0.52), Thesis("up", 0.9, "r"), _fv()) is None


def test_combine_low_conviction_blocks():
    assert combine(_sig("up", 0.7), Thesis("up", 0.3, "r"), _fv()) is None


def test_combine_flat_blocks():
    assert combine(_sig("flat", 0.5), Thesis("up", 0.9, "r"), _fv()) is None


def test_combine_down_makes_put():
    intent = combine(_sig("down", 0.7), Thesis("down", 0.8, "r"), _fv())
    assert intent.direction == LONG_PUT
