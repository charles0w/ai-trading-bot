"""Mirror run results into the Obsidian vault (obi-secondbrain) — serverless.

Called by the GitHub Actions workflows after each run, with the vault cloned
to a working dir via the write-scoped deploy key:

    python scripts/vault_mirror.py /tmp/vault --mode daily    # every daily-run
    python scripts/vault_mirror.py /tmp/vault --mode weekly   # weekly-eval too

Writes (all under the vault):
    repos/ai-trading-bot/predictions.jsonl        canonical mirror
    repos/ai-trading-bot/chain_snapshots.jsonl    canonical mirror
    repos/ai-trading-bot/runs/<date>.md           per-run summary note
    repos/ai-trading-bot/evals/…                  weekly: eval doc copies
    ai-memory/fleet/AI Trading Bot Weekly Eval.md weekly: fleet scorecard note

Everything is regenerated from the data files (predictions/snapshots/evals),
so the mirror is idempotent — re-running a mode for the same day converges to
the same content. Numbers are computed, never narrated."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_eval import conviction_label, load_predictions, scorecard  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PROJ = "repos/ai-trading-bot"


def _copy_mirrors(vault: Path) -> None:
    dst = vault / PROJ
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("predictions.jsonl", "chain_snapshots.jsonl"):
        src = REPO / "data" / name
        if src.exists():
            shutil.copyfile(src, dst / name)


def _snapshot_count(day: str) -> int:
    path = REPO / "data" / "chain_snapshots.jsonl"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if f'"date": "{day}"' in line)


def missed_weekdays(existing: set[str], today: date, lookback: int = 7) -> list[str]:
    """Weekdays in the `lookback` days before `today` that have no run note.

    Today is excluded — its note is written moments after this check. Weekends
    are skipped, but US market holidays are not (no calendar here), so a hit is
    "suspicious", not "broken"; the callout says so.
    """
    out = []
    for back in range(lookback, 0, -1):
        day = date.fromordinal(today.toordinal() - back)
        if day.weekday() >= 5:            # Sat/Sun
            continue
        if day.isoformat() not in existing:
            out.append(day.isoformat())
    return out


def gap_callout(missing: list[str]) -> str:
    """Obsidian admonition naming days with no run note, or '' when clean."""
    if not missing:
        return ""
    days = " · ".join(f"`{d}`" for d in missing)
    return (
        "\n> [!warning] Missing run note(s): " + days + "\n"
        "> No daily-run mirrored for these weekdays. Most likely a dropped\n"
        "> GitHub `schedule:` trigger — or a market holiday, which is not\n"
        "> checked here. Predictions and chain snapshots for a missed day are\n"
        "> **not backfillable**; re-running the workflow later cannot recover\n"
        "> them.\n"
    )


def _existing_run_days(vault: Path) -> set[str]:
    runs = vault / PROJ / "runs"
    if not runs.exists():
        return set()
    return {p.stem for p in runs.glob("*.md")}


def _run_note(vault: Path, today: str) -> None:
    rows = load_predictions()
    new = [r for r in rows if r.get("date") == today]
    graded_today = [r for r in rows if r.get("graded_date") == today]
    card = scorecard(rows)
    gaps = gap_callout(missed_weekdays(_existing_run_days(vault),
                                       date.fromisoformat(today)))

    def fmt(r):
        comp = (r.get("meta") or {}).get("component", "combined")
        conv = r.get("conviction")
        conv = f"{conv:.2f}" if isinstance(conv, (int, float)) else conviction_label(r)
        stage = (r.get("meta") or {}).get("stage") or "—"
        return f"| {r['id']} | {comp} | {r['direction']} | {conv} | {stage} |"

    def fmt_grade(r):
        ret = r.get("return_pct")
        ret = f"{ret:+.2f}%" if isinstance(ret, (int, float)) else "—"
        return f"| {r['id']} | {'✅' if r.get('correct') else '❌'} | {ret} |"

    new_rows = "\n".join(fmt(r) for r in new) or "| — | — | — | — | — |"
    graded_rows = "\n".join(fmt_grade(r) for r in graded_today) or "| — | — | — |"
    hit = f"{card['hit_rate']:.1%}" if card["hit_rate"] is not None else "—"

    note = f"""---
type: run-log
parent: ai-trading-bot
date: {today}
tags: [ai-trading-bot, run-log]
---

# Daily run — {today}

Auto-mirrored from the serverless daily-run (GitHub Actions). Data source of
truth: `data/predictions.jsonl` + `data/chain_snapshots.jsonl` in the
[code repo](https://github.com/charles0w/ai-trading-bot).
{gaps}
## New predictions today ({len(new)})

| id | component | dir | conviction | stage |
|---|---|---|---|---|
{new_rows}

## Graded today ({len(graded_today)})

| id | correct | return |
|---|---|---|
{graded_rows}

## Running totals

Total {card['total']} · graded {card['graded']} · open {card['open']} · hit rate {hit} · chain snapshots today: {_snapshot_count(today)}
"""
    out = vault / PROJ / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{today}.md").write_text(note, encoding="utf-8")


def _weekly(vault: Path, today: str) -> None:
    evals_src = REPO / "evals"
    if not evals_src.exists():
        return
    dst = vault / PROJ / "evals"
    dst.mkdir(parents=True, exist_ok=True)
    for f in evals_src.glob("*.md"):
        shutil.copyfile(f, dst / f.name)

    latest = evals_src / "latest.md"
    verdict = ""
    if latest.exists():
        m = re.search(r"## Verdict\n\n(.+?)\n\n## Scorecard", latest.read_text(encoding="utf-8"),
                      re.DOTALL)
        verdict = (m.group(1).strip() if m else "").replace("\n", "\n> ")
    card = scorecard(load_predictions())
    hit = f"{card['hit_rate']:.1%}" if card["hit_rate"] is not None else "—"
    mean = f"{card['mean_return_pct']:+.2f}%" if card["mean_return_pct"] is not None else "—"
    comp_rows = "\n".join(
        f"| {c} | {b['graded']} | {b['hit_rate']:.0%} | "
        f"{(f'{b['mean_return_pct']:+.2f}%' if b['mean_return_pct'] is not None else '—')} |"
        for c, b in sorted(card["by_component"].items())
    ) or "| — | 0 | — | — |"

    note = f"""---
tags: [ai-memory, fleet, ai-trading-bot, weekly-eval]
updated: {today}
---

# AI Trading Bot Weekly Eval

> [!summary] Auto-mirrored {today} from the serverless weekly eval.
> {verdict}

| Metric | Value |
|---|---|
| Total predictions | {card['total']} |
| Graded | {card['graded']} |
| Open | {card['open']} |
| Hit rate | {hit} |
| Mean return (graded) | {mean} |

### By component

| Component | Graded | Hit rate | Mean return |
|---|---|---|---|
{comp_rows}

[[../../repos/ai-trading-bot/notes|Session notes]] · Full eval: https://github.com/charles0w/ai-trading-bot/blob/main/evals/latest.md
"""
    fleet = vault / "ai-memory" / "fleet"
    fleet.mkdir(parents=True, exist_ok=True)
    (fleet / "AI Trading Bot Weekly Eval.md").write_text(note, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", help="path to the cloned obi-secondbrain checkout")
    ap.add_argument("--mode", choices=("daily", "weekly"), default="daily")
    args = ap.parse_args()
    vault = Path(args.vault)
    today = date.today().isoformat()

    _copy_mirrors(vault)
    _run_note(vault, today)
    if args.mode == "weekly":
        _weekly(vault, today)
    print(f"vault mirror ({args.mode}) written for {today}")


if __name__ == "__main__":
    main()
