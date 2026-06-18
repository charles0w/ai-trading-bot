# Daily automation (launchd)

Runs the bot every market weekday at 07:30 PT: grade matured predictions → scan
recent reporters → run the brain over the universe. **Dry run by default.**

## Install

```bash
cp deploy/com.charles.atb-daily.plist ~/Library/LaunchAgents/
chmod +x scripts/run_daily.sh
launchctl load ~/Library/LaunchAgents/com.charles.atb-daily.plist
launchctl start com.charles.atb-daily          # run once now to test
tail -f logs/daily.log                          # watch output
```

To go live (place paper orders unattended), edit the plist's `ATB_EXECUTE` to
`1`, then `launchctl unload` + `launchctl load` it again. Keep it `0` until a few
days of dry-run output look right.

## Heads-up (same TCC gotcha as eod-recap)

launchd jobs can be blocked from a Desktop-resident repo by macOS privacy (TCC):
if `logs/daily.log` stays empty after a scheduled run, grant **Full Disk Access
to `/bin/bash`** (System Settings → Privacy & Security → Full Disk Access). The
Mac must also be awake at 07:30 (AC power / `caffeinate`) for the run to fire.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.charles.atb-daily.plist
rm ~/Library/LaunchAgents/com.charles.atb-daily.plist
```

## What it does (scripts/run_daily.sh)

1. `grade.py` — grade predictions whose horizon elapsed; update the scorecard.
2. `scan.py` — list liquid names that just reported (PEAD candidates).
3. `run_once.py` — features → signal → Claude analyst → intersection → resolve →
   risk → size → (paper) execute → log prediction, per symbol.

Everything appends to `logs/daily.log`; orders/positions go to `data/atb.db`,
predictions to `data/predictions.jsonl`.
