"""
ceo_report.py — a tiny, dependency-free eval toolkit.

Three things, usable independently:
  judge(output, criteria)        -> LLM-as-a-judge score (0..1) + one-line rationale
  track_reliability(id, passed)  -> rolling pass-rate (pass^k-style consistency proxy)
  report(agent_id, ...)          -> POST a status (+ optional eval fields) to a dashboard

Standard library only. Bring your own model key.

JUDGE PROVIDER — pick ONE (auto-selected; override with EVAL_JUDGE_PROVIDER):
  Anthropic (native):
    ANTHROPIC_API_KEY=<key>
    EVAL_JUDGE_MODEL=<optional, default claude-haiku-4-5-20251001>
  OpenAI-compatible (OpenAI, Gemini OpenAI endpoint, Groq, ...):
    EVAL_JUDGE_URL=https://api.openai.com/v1/chat/completions
    EVAL_JUDGE_KEY=<key>
    EVAL_JUDGE_MODEL=gpt-4o-mini

REPORTING (optional — only if you POST to a dashboard):
    REPORT_URL=<your endpoint>     # e.g. https://your-app/api/report
    REPORT_SECRET=<shared secret>  # sent as the x-report-secret header

RIGOR NOTE: an unvalidated judge is a confident guess. Hand-grade a sample and confirm
agreement before trusting these scores, and judge with a DIFFERENT model family than the
one that produced the output (self-preference bias).
"""
import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPORT_URL = os.environ.get("REPORT_URL", "")
REPORT_SECRET = os.environ.get("REPORT_SECRET", "")

JUDGE_PROVIDER = os.environ.get("EVAL_JUDGE_PROVIDER", "").lower()
JUDGE_URL = os.environ.get("EVAL_JUDGE_URL", "")
JUDGE_KEY = os.environ.get("EVAL_JUDGE_KEY", "")
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_REL_STORE = Path(os.environ.get("EVAL_STORE", str(Path.home() / ".eval_reliability.json")))


def _clamp01(x):
    return max(0.0, min(1.0, float(x)))


def _judge_prompt(output, criteria):
    return (
        "You are a strict evaluation judge. Score the AGENT OUTPUT from 0.0 to 1.0 "
        "against the CRITERIA. Penalize unsupported claims and missing requirements. "
        "Do not reward length. Respond ONLY with compact JSON: "
        '{"score": <float 0..1>, "summary": "<one sentence>"}.\n\n'
        f"CRITERIA:\n{criteria}\n\nAGENT OUTPUT:\n{output}\n"
    )


def _parse_judge(content):
    m = re.search(r"\{.*\}", content, re.DOTALL)
    parsed = json.loads(m.group(0) if m else content)
    return {"score": _clamp01(float(parsed["score"])), "summary": str(parsed.get("summary", "")).strip()}


def judge(output, criteria, *, model=None):
    """Score `output` (0..1) against `criteria`. Returns {"score": float|None, "summary": str}."""
    provider = JUDGE_PROVIDER or ("anthropic" if ANTHROPIC_KEY else ("openai" if (JUDGE_URL and JUDGE_KEY) else ""))
    if provider == "anthropic":
        return _judge_anthropic(output, criteria, model)
    if provider == "openai":
        return _judge_openai(output, criteria, model)
    return {"score": None, "summary": "judge not configured (set ANTHROPIC_API_KEY or EVAL_JUDGE_URL/KEY)"}


def _judge_anthropic(output, criteria, model):
    if not ANTHROPIC_KEY:
        return {"score": None, "summary": "ANTHROPIC_API_KEY not set"}
    body = json.dumps({
        "model": model or JUDGE_MODEL or "claude-haiku-4-5-20251001",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": _judge_prompt(output, criteria)}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": ANTHROPIC_KEY,
                 "anthropic-version": "2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return _parse_judge(data["content"][0]["text"])
    except Exception as e:
        print(f"[ceo_report] anthropic judge failed: {e}")
        return {"score": None, "summary": f"judge error: {e}"}


def _judge_openai(output, criteria, model):
    if not (JUDGE_URL and JUDGE_KEY):
        return {"score": None, "summary": "EVAL_JUDGE_URL/KEY not set"}
    body = json.dumps({
        "model": model or JUDGE_MODEL or "gpt-4o-mini",
        "messages": [{"role": "user", "content": _judge_prompt(output, criteria)}],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        JUDGE_URL, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {JUDGE_KEY}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        return _parse_judge(content)
    except Exception as e:
        print(f"[ceo_report] openai judge failed: {e}")
        return {"score": None, "summary": f"judge error: {e}"}


def track_reliability(agent_id, *, passed, window=8):
    """Record this run's pass/fail; return recent pass-rate over the last `window` runs.

    pass^k in its strict form asks 'did ALL k runs pass' (0/1). This returns the smoother
    fraction-passed, which reads better on a dashboard while still surfacing inconsistency.
    """
    try:
        history = json.loads(_REL_STORE.read_text()) if _REL_STORE.exists() else {}
    except Exception:
        history = {}
    runs = (history.get(agent_id, []) + [bool(passed)])[-window:]
    history[agent_id] = runs
    try:
        _REL_STORE.write_text(json.dumps(history))
    except Exception as e:
        print(f"[ceo_report] could not persist reliability: {e}")
    return sum(runs) / len(runs) if runs else 0.0


def report(agent_id, *, ok, summary, state=None,
           eval_score=None, eval_reliability=None, eval_summary=None):
    """POST a status (+ optional eval fields) to REPORT_URL. Returns True on success."""
    if not (REPORT_URL and REPORT_SECRET):
        print("[ceo_report] REPORT_URL/REPORT_SECRET not set — skipping report")
        return False
    status = {"state": state or ("ok" if ok else "error"),
              "lastRun": datetime.now(timezone.utc).isoformat(), "summary": summary, "ok": ok}
    if eval_score is not None:
        status["evalScore"] = round(_clamp01(eval_score), 4)
    if eval_reliability is not None:
        status["evalReliability"] = round(_clamp01(eval_reliability), 4)
    if eval_summary is not None:
        status["evalSummary"] = eval_summary
    req = urllib.request.Request(
        REPORT_URL, data=json.dumps({"agentId": agent_id, "status": status}).encode(),
        headers={"Content-Type": "application/json", "x-report-secret": REPORT_SECRET},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ceo_report] report failed: {e}")
        return False
