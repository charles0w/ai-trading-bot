"""LLM-as-judge for recap / thesis quality.

Critical design rule (from the eval system work): judge with a DIFFERENT model
family than the writer to avoid self-preference bias. The writer is Claude, so
the judge should be e.g. local Ollama (llama3.1 / qwen2.5) or an OpenAI model.
Injectable `complete` keeps it testable and provider-agnostic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

_RUBRIC = ["faithfulness", "completeness", "calibration", "actionability"]


@dataclass
class JudgeScore:
    overall: float
    rubric: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    raw: str = ""


def build_judge_prompt(text: str, context: str = "") -> str:
    return (
        "You are a strict evaluator of a market analysis. Score it 0.0-1.0 on: "
        + ", ".join(_RUBRIC) + ". Faithfulness = claims supported by the data; "
        "completeness = covers the key drivers; calibration = confidence matches "
        "evidence; actionability = a clear, usable call.\n\n"
        f"CONTEXT (ground-truth data):\n{context}\n\nANALYSIS:\n{text}\n\n"
        'Respond with ONLY JSON: {"faithfulness":0-1,"completeness":0-1,'
        '"calibration":0-1,"actionability":0-1,"overall":0-1,"rationale":"..."}'
    )


def parse_judge(raw: str) -> JudgeScore:
    try:
        obj = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
    except (json.JSONDecodeError, AttributeError):
        return JudgeScore(overall=0.0, rationale="unparseable", raw=raw)
    rubric = {}
    for k in _RUBRIC:
        try:
            rubric[k] = max(0.0, min(1.0, float(obj[k])))
        except (KeyError, TypeError, ValueError):
            pass
    try:
        overall = float(obj.get("overall"))
    except (TypeError, ValueError):
        overall = sum(rubric.values()) / len(rubric) if rubric else 0.0
    return JudgeScore(overall=max(0.0, min(1.0, overall)), rubric=rubric,
                      rationale=str(obj.get("rationale", "")), raw=raw)


class Judge:
    def __init__(self, complete: Callable[[str], str], *,
                 provider: str = "ollama", model: str = "llama3.1"):
        self._complete = complete
        self.provider = provider
        self.model = model

    def score(self, text: str, context: str = "") -> JudgeScore:
        return parse_judge(self._complete(build_judge_prompt(text, context)))
