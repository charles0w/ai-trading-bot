"""SQLite implementation of trader_core's Store port.

Three tables: signals (the bot's calls, for grading/traceability), orders, and
positions. Satisfies trader_core.ports.Store so the executor/exit-manager can
persist against it. Used by scripts/paper_smoke.py and the eventual pipeline.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ORDER_COLS = [
    "signal_id", "parent_order_id", "broker", "broker_order_id", "client_order_id",
    "submitted_at_utc", "occ_symbol", "side", "quantity", "order_type",
    "limit_price", "status", "filled_qty", "avg_fill_price", "exit_reason",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id   TEXT PRIMARY KEY,
    created_utc TEXT,
    underlying  TEXT,
    direction   TEXT,
    conviction  REAL,
    status      TEXT DEFAULT 'open',
    reason      TEXT,
    meta_json   TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT,
    parent_order_id INTEGER,
    broker          TEXT,
    broker_order_id TEXT,
    client_order_id TEXT,
    submitted_at_utc TEXT,
    occ_symbol      TEXT,
    side            TEXT,
    quantity        INTEGER,
    order_type      TEXT,
    limit_price     REAL,
    status          TEXT,
    filled_qty      INTEGER DEFAULT 0,
    avg_fill_price  REAL,
    exit_reason     TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    open_order_id INTEGER,
    occ_symbol    TEXT,
    quantity      INTEGER,
    entry_price   REAL,
    entry_at_utc  TEXT,
    mark          REAL,
    closed        INTEGER DEFAULT 0
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path = "data/atb.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # --- signals --------------------------------------------------------
    def record_signal(self, *, signal_id: str, underlying: str, direction: str,
                      conviction: float | None = None, meta: dict | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO signals "
            "(signal_id, created_utc, underlying, direction, conviction, status, meta_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (signal_id, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             underlying, direction, conviction, "open", json.dumps(meta or {})),
        )
        self.conn.commit()

    def mark_signal_rejected(self, signal_id: str | None, reason: str) -> None:
        if signal_id is None:
            return
        self.conn.execute(
            "INSERT INTO signals (signal_id, status, reason) VALUES (?, 'rejected', ?) "
            "ON CONFLICT(signal_id) DO UPDATE SET status='rejected', reason=excluded.reason",
            (signal_id, reason),
        )
        self.conn.commit()

    # --- orders ---------------------------------------------------------
    def insert_order(self, **fields: Any) -> int:
        cols = [c for c in _ORDER_COLS if c in fields]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT INTO orders ({','.join(cols)}) VALUES ({placeholders})"
        cur = self.conn.execute(sql, [fields[c] for c in cols])
        self.conn.commit()
        return int(cur.lastrowid)

    def update_order(self, order_id: int, **fields: Any) -> None:
        cols = [c for c in _ORDER_COLS if c in fields]
        if not cols:
            return
        sets = ",".join(f"{c}=?" for c in cols)
        self.conn.execute(f"UPDATE orders SET {sets} WHERE id=?",
                          [fields[c] for c in cols] + [order_id])
        self.conn.commit()

    # --- positions ------------------------------------------------------
    def open_position(self, *, open_order_id: int, occ_symbol: str, quantity: int,
                      entry_price: float, entry_at_utc: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO positions (open_order_id, occ_symbol, quantity, entry_price, entry_at_utc) "
            "VALUES (?,?,?,?,?)",
            (open_order_id, occ_symbol, quantity, entry_price, entry_at_utc),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def open_positions(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM positions WHERE closed=0").fetchall()
        return [dict(r) for r in rows]

    def update_position_mark(self, position_id: int, mark: float) -> None:
        self.conn.execute("UPDATE positions SET mark=? WHERE id=?", (mark, position_id))
        self.conn.commit()

    def mark_position_closed(self, position_id: int) -> None:
        self.conn.execute("UPDATE positions SET closed=1 WHERE id=?", (position_id,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
