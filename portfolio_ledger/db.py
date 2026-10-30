"""SQLite ledger (portfolio_ledger/portfolio.db): 1-share positions, paper and live."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from common.config import ROOT

DB = ROOT / "portfolio_ledger" / "portfolio.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  horizon INTEGER NOT NULL,             -- 5 weekly, 21 monthly, 63 quarterly (trading days)
  mode TEXT NOT NULL,                   -- PAPER (signal, edge not proven) | LIVE (signal) | MANUAL (user trade)
  source TEXT NOT NULL,                 -- signal | user
  entry_date TEXT NOT NULL,
  entry_price REAL NOT NULL,
  atr14 REAL,
  tp REAL, sl REAL,                     -- triple-barrier prices
  expiry_date TEXT,                     -- vertical (time) barrier
  status TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | CLOSED_TP | CLOSED_SL | CLOSED_TIME | CLOSED_EXIT | CLOSED_MANUAL
  exit_date TEXT, exit_price REAL, pnl REAL, ret_pct REAL,
  ml_prob REAL, cluster TEXT, notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pos_status ON positions(status);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id INTEGER, ts TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT
);
"""


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def open_positions(con=None) -> list[dict]:
    if con is None:
        with connect() as c:
            return open_positions(c)
    return [dict(r) for r in con.execute("SELECT * FROM positions WHERE status='OPEN' ORDER BY entry_date")]


def all_positions(con=None) -> list[dict]:
    if con is None:
        with connect() as c:
            return all_positions(c)
    return [dict(r) for r in con.execute("SELECT * FROM positions ORDER BY entry_date, id")]


def log_event(con, position_id: int | None, kind: str, detail: str = "") -> None:
    con.execute("INSERT INTO events(position_id, ts, kind, detail) VALUES (?,?,?,?)", (position_id, now(), kind, detail))
