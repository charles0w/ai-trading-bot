#!/bin/bash
# Daily ai-trading-bot run (launchd). Loads .env, checks the CEO delegation
# queue, grades matured predictions, scans + runs the brain, then pushes a
# snapshot to the ceos-enterprise dashboard. DRY RUN by default; export
# ATB_EXECUTE=1 (or set it in the plist) to place paper orders.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate
set -a; [ -f .env ] && . ./.env; set +a   # export keys for all child scripts

mkdir -p logs
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  echo "--- CEO delegation queue ---"
  python fleet_tasks.py list || true
  echo "--- grade ---"
  python scripts/grade.py
  echo "--- scan ---"
  python scripts/scan.py
  echo "--- run_once ---"
  if [ "${ATB_EXECUTE:-0}" = "1" ]; then
    python scripts/run_once.py --execute
  else
    python scripts/run_once.py
  fi
  echo "--- report to dashboard ---"
  python scripts/report.py || true
  echo
} >> logs/daily.log 2>&1
