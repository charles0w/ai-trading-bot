"""Service the CEO's delegation queue from an agent repo.

The CEO (ceos-enterprise /ceo) delegates work into a queue (fleet_tasks).
This client closes the loop: the agent working in a repo — a Claude session
or Charles — picks tasks up and reports their fate, which the dashboard's
Delegations panel reflects live.

At the START of a working session in an agent repo:

    python fleet_tasks.py list           # anything the CEO queued for this agent?
    python fleet_tasks.py start <id>     # claim it (dashboard shows in progress)
    ... do the work ...
    python fleet_tasks.py done <id>      # close it
    python fleet_tasks.py drop <id>      # won't do (obsolete / wrong agent)

Programmatic:
    from fleet_tasks import fetch_tasks, update_task, queued_count
    fetch_tasks(status="queued")  ·  update_task(7, "done")  ·  queued_count()

Vendoring: copy this file into the agent repo and set AGENT_ID below.
This canonical copy reads FLEET_AGENT_ID from the environment instead.

Env:
    CEOS_REPORT_SECRET (or REPORT_SECRET) — required; same secret as ceo_report.
    CEOS_DASHBOARD_URL — optional, defaults to https://ceos-enterprise.vercel.app
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

AGENT_ID = os.environ.get("FLEET_AGENT_ID", "")  # vendored copies hardcode this
DEFAULT_URL = "https://ceos-enterprise.vercel.app"
STATUSES = ("queued", "in_progress", "done", "dropped")


def _base() -> str:
    return os.environ.get("CEOS_DASHBOARD_URL", DEFAULT_URL).strip().rstrip("/")


def _secret() -> str:
    return (os.environ.get("CEOS_REPORT_SECRET") or os.environ.get("REPORT_SECRET") or "").strip()


def _request(path: str, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{_base()}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"x-report-secret": _secret(), "content-type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode() or "{}")


def fetch_tasks(status: str | None = "queued", agent_id: str | None = None) -> list[dict]:
    """Tasks for this agent, newest first. status=None returns recent of any status."""
    if not _secret():
        raise RuntimeError("CEOS_REPORT_SECRET is not set")
    q = {"agentId": agent_id or AGENT_ID}
    if status:
        q["status"] = status
    return _request(f"/api/tasks?{urllib.parse.urlencode(q)}").get("tasks", [])


def update_task(task_id: int, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    try:
        out = _request("/api/tasks", method="PATCH", body={"id": int(task_id), "status": status})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    return bool(out.get("ok"))


def queued_count(agent_id: str | None = None) -> int:
    """Queue depth for run summaries. Never raises — returns 0 when unreachable."""
    try:
        return len(fetch_tasks("queued", agent_id))
    except Exception:
        return 0


def _age(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    except Exception:
        return "?"
    if mins < 60:
        return f"{mins}m"
    if mins < 60 * 24:
        return f"{mins // 60}h"
    return f"{mins // (60 * 24)}d"


def _cli() -> None:
    args = sys.argv[1:]
    if not AGENT_ID:
        print("set FLEET_AGENT_ID (or hardcode AGENT_ID in your vendored copy)")
        sys.exit(2)
    if not args or args[0] == "list":
        open_tasks = [t for s in ("queued", "in_progress") for t in fetch_tasks(s)]
        if not open_tasks:
            print(f"no open tasks for '{AGENT_ID}' — the CEO's queue is clear")
            return
        for t in open_tasks:
            print(f"#{t['id']:<4} [{t['status']:<11}] {_age(t['createdAt']):>3} ago  {t['title']}")
            print(f"      {t['spec'][:160]}")
        return
    cmd, rest = args[0], args[1:]
    if cmd in ("start", "done", "drop") and rest:
        status = {"start": "in_progress", "done": "done", "drop": "dropped"}[cmd]
        ok = update_task(int(rest[0]), status)
        print(f"task #{rest[0]} → {status}" if ok else f"task #{rest[0]} not found")
        sys.exit(0 if ok else 1)
    print(__doc__.split("Env:")[0])
    sys.exit(2)


if __name__ == "__main__":
    _cli()
