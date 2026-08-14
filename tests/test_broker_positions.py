"""Broker.list_positions() + the dashboard's position sourcing.

Context (2026-08-13): scripts/report.py sourced open positions from the local
SQLite store at data/atb.db. That path is gitignored, so on the ephemeral
GitHub Actions runner it never exists and the ceos-enterprise finance desk
always showed zero open positions regardless of the real paper account. Alpaca
is the actual position-keeper, so the broker gains a list_positions() and the
reporter prefers it, keeping SQLite only as a local fallback.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3

import pytest

from trader_core.broker.base import PositionSnapshot

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_report():
    """Import scripts/report.py by path — scripts/ is not a package."""
    path = os.path.join(REPO_ROOT, "scripts", "report.py")
    spec = importlib.util.spec_from_file_location("atb_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestListPositions:
    def test_defaults_to_empty(self, fake_broker_factory):
        assert fake_broker_factory().list_positions() == []

    def test_returns_scripted_positions(self, fake_broker_factory):
        broker = fake_broker_factory(positions=[
            PositionSnapshot(occ_symbol="COP260918C00130000", quantity=2,
                             entry_price=3.10, mark_price=3.55),
        ])
        out = broker.list_positions()
        assert [p.occ_symbol for p in out] == ["COP260918C00130000"]
        assert out[0].quantity == 2

    def test_get_position_agrees_with_list(self, fake_broker_factory):
        """A position in list_positions() must be findable by symbol — the two
        broker reads should not disagree about what is open."""
        snap = PositionSnapshot(occ_symbol="LLY260918C00900000", quantity=1,
                                entry_price=5.0, mark_price=6.0)
        broker = fake_broker_factory(positions=[snap])
        assert broker.get_position("LLY260918C00900000") == snap
        assert broker.get_position("NOPE260918C00001000") is None


class TestReporterPositionSourcing:
    def test_maps_broker_snapshots_to_payload(self, fake_broker_factory):
        report = _load_report()
        broker = fake_broker_factory(positions=[
            PositionSnapshot(occ_symbol="COP260918C00130000", quantity=2,
                             entry_price=3.10, mark_price=3.55),
        ])
        rows = report.positions_from_broker(broker)
        assert rows == [{
            "occ_symbol": "COP260918C00130000", "quantity": 2,
            "entry_price": 3.10, "mark": 3.55, "entry_at_utc": None,
        }]

    def test_broker_empty_is_distinct_from_broker_unavailable(self, fake_broker_factory):
        """An account with no open positions returns []; an unreachable broker
        returns None so the caller can fall back instead of reporting a
        confident (and wrong) zero."""
        report = _load_report()
        assert report.positions_from_broker(fake_broker_factory()) == []
        assert report.positions_from_broker(None) is None

    def test_unreachable_broker_falls_back_to_sqlite(self, tmp_path, monkeypatch):
        report = _load_report()
        db = tmp_path / "atb.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE positions (occ_symbol TEXT, quantity INT, "
                    "entry_price REAL, mark REAL, entry_at_utc TEXT, closed INT)")
        con.execute("INSERT INTO positions VALUES ('X260918C00100000', 1, 1.0, 1.2, "
                    "'2026-08-13T00:00:00Z', 0)")
        con.commit()
        con.close()
        monkeypatch.setattr(report, "DB", str(db))
        monkeypatch.setattr(report, "_broker", lambda: None)  # broker unreachable

        rows = report.collect_positions()
        assert [r["occ_symbol"] for r in rows] == ["X260918C00100000"]

    def test_broker_wins_over_stale_sqlite(self, tmp_path, monkeypatch,
                                           fake_broker_factory):
        """The runner may carry a stale/empty db; the live broker is truth."""
        report = _load_report()
        db = tmp_path / "atb.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE positions (occ_symbol TEXT, quantity INT, "
                    "entry_price REAL, mark REAL, entry_at_utc TEXT, closed INT)")
        con.execute("INSERT INTO positions VALUES ('STALE260918C00100000', 9, 1.0, "
                    "1.0, '2026-01-01T00:00:00Z', 0)")
        con.commit()
        con.close()
        broker = fake_broker_factory(positions=[
            PositionSnapshot(occ_symbol="LIVE260918C00130000", quantity=2,
                             entry_price=3.10, mark_price=3.55),
        ])
        monkeypatch.setattr(report, "DB", str(db))
        monkeypatch.setattr(report, "_broker", lambda: broker)

        assert [r["occ_symbol"] for r in report.collect_positions()] == [
            "LIVE260918C00130000"]

    def test_missing_db_and_no_broker_is_empty(self, tmp_path, monkeypatch):
        report = _load_report()
        monkeypatch.setattr(report, "DB", str(tmp_path / "absent.db"))
        monkeypatch.setattr(report, "_broker", lambda: None)
        assert report.collect_positions() == []


class TestRunRecord:
    """_run_record() previously parsed logs/daily.log, which the Actions
    workflow never creates (it calls the python scripts directly, not
    run_daily.sh) — so the dashboard activity detail was always empty."""

    def test_summarises_todays_predictions(self):
        report = _load_report()
        rec = report.run_record_from_predictions(
            [
                {"date": "2026-08-13", "meta": {"component": "ml"}},
                {"date": "2026-08-13", "meta": {"component": "llm"}},
                {"date": "2026-08-13", "meta": {"component": "combined",
                                                "stage": "placed"}},
                {"date": "2026-08-12", "meta": {"component": "ml"}},
            ],
            graded_today=4, today="2026-08-13",
        )
        assert rec["ok"] is True
        assert "3 new" in rec["summary"]
        assert "1 placed" in rec["summary"]
        assert "4 graded" in rec["summary"]

    def test_no_predictions_today_is_not_ok(self):
        """A trading day that produced nothing is the silent-failure mode that
        hid the Aug 6 miss — surface it rather than reporting a healthy run."""
        report = _load_report()
        rec = report.run_record_from_predictions([], graded_today=0,
                                                 today="2026-08-13")
        assert rec["ok"] is False
        assert "0 new" in rec["summary"]
