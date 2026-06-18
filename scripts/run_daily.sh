#!/bin/bash
# Daily ai-trading-bot run (for launchd). Grades matured predictions, then runs
# the brain over the universe. DRY RUN by default; export ATB_EXECUTE=1 to place
# paper orders. Logs to logs/daily.log.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate

mkdir -p logs
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
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
  echo
} >> logs/daily.log 2>&1
