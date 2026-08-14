"""Missed-run detection in the vault mirror.

Context (2026-08-13): the 2026-08-06 daily-run never fired — most likely a
dropped GitHub `schedule:` trigger — and nothing noticed. The gap only surfaced
in a manual audit a week later, by which point that day's chain snapshots were
permanently lost (yfinance chains are snapshot-only and cannot be backfilled).
The mirror now flags weekdays with no run note in the day's vault note.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_mirror():
    path = os.path.join(REPO_ROOT, "scripts", "vault_mirror.py")
    spec = importlib.util.spec_from_file_location("atb_vault_mirror", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMissedWeekdays:
    def test_flags_the_one_missing_weekday(self):
        """The real Aug 6 case: Mon-Wed and Fri present, Thursday absent.
        Fri 7/31 is inside the default 7-day window, so it is present too."""
        m = _load_mirror()
        existing = {"2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05",
                    "2026-08-07"}
        assert m.missed_weekdays(existing, today=date(2026, 8, 7)) == ["2026-08-06"]

    def test_ignores_weekends(self):
        m = _load_mirror()
        existing = {"2026-08-07", "2026-08-10"}
        # Sat 8/8 and Sun 8/9 are not trading days and must not be flagged
        assert m.missed_weekdays(existing, today=date(2026, 8, 10), lookback=3) == []

    def test_excludes_today(self):
        """Today's note is written just after this check runs, so its absence
        must never be reported as a miss — even on a wide lookback."""
        m = _load_mirror()
        got = m.missed_weekdays(set(), today=date(2026, 8, 13), lookback=10)
        assert "2026-08-13" not in got
        assert got == ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                       "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12"]

    def test_clean_week_is_empty(self):
        m = _load_mirror()
        existing = {"2026-08-10", "2026-08-11", "2026-08-12"}
        assert m.missed_weekdays(existing, today=date(2026, 8, 13), lookback=3) == []

    def test_reports_oldest_first(self):
        """5-day window from Thu 8/13 covers Sat 8/8 - Wed 8/12; the weekend
        drops out, leaving Mon-Wed with 8/12 already mirrored."""
        m = _load_mirror()
        got = m.missed_weekdays({"2026-08-12"}, today=date(2026, 8, 13), lookback=5)
        assert got == ["2026-08-10", "2026-08-11"]


class TestGapCallout:
    def test_renders_nothing_when_clean(self):
        m = _load_mirror()
        assert m.gap_callout([]) == ""

    def test_names_each_missing_day(self):
        m = _load_mirror()
        out = m.gap_callout(["2026-08-06"])
        assert "2026-08-06" in out
        assert out.lstrip().startswith("> [!warning]")

    def test_mentions_the_holiday_caveat(self):
        """No holiday calendar here, so the callout must not assert failure."""
        m = _load_mirror()
        assert "holiday" in m.gap_callout(["2026-08-06"]).lower()
