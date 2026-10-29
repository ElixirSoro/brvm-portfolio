"""Base SQLite locale : schéma et accès."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from . import config, universe

SCHEMA = """
CREATE TABLE IF NOT EXISTS securities (
    ticker TEXT PRIMARY KEY, name TEXT, country TEXT, sector TEXT, sika TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS corporate_actions (
    ticker TEXT, date TEXT, ratio REAL, PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS dividends (
    ticker TEXT, ex_date TEXT, pay_date TEXT, amount REAL, is_gross INTEGER,
    PRIMARY KEY (ticker, ex_date)
);
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created TEXT DEFAULT CURRENT_TIMESTAMP,
    note TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER, date TEXT, type TEXT,
    ticker TEXT, quantity REAL, price REAL, gross REAL, fees REAL, net REAL, note TEXT,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, fingerprint TEXT, title TEXT,
    source TEXT, query TEXT, published TEXT, collected TEXT DEFAULT CURRENT_TIMESTAMP,
    content TEXT, summary TEXT, category TEXT, scope TEXT, theme TEXT, analyzed INTEGER DEFAULT 0,
    method TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_fp ON news(fingerprint);
CREATE TABLE IF NOT EXISTS impacts (
    news_id INTEGER, ticker TEXT, score REAL, horizon TEXT, confidence REAL, rationale TEXT,
    PRIMARY KEY (news_id, ticker)
);
CREATE TABLE IF NOT EXISTS factors (
    code TEXT, date TEXT, value REAL, PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS updates (what TEXT PRIMARY KEY, at TEXT);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or config.DB_PATH), check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def session(path: Path | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init(path: Path | None = None) -> None:
    with session(path) as con:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT OR REPLACE INTO securities VALUES (?,?,?,?,?)",
            [(t, n, c, s, universe.sika_ticker(t, c)) for t, n, c, s in universe.SECURITIES],
        )
        con.executemany("INSERT OR IGNORE INTO corporate_actions VALUES (?,?,?)", universe.CORPORATE_ACTIONS)


def df(sql: str, params: tuple = (), path: Path | None = None) -> pd.DataFrame:
    with session(path) as con:
        return pd.read_sql_query(sql, con, params=params)


def execute(sql: str, params: tuple = (), path: Path | None = None) -> int:
    with session(path) as con:
        cur = con.execute(sql, params)
        return cur.lastrowid


def executemany(sql: str, rows: list[tuple], path: Path | None = None) -> None:
    with session(path) as con:
        con.executemany(sql, rows)


def get_setting(key: str, default=None, path: Path | None = None):
    with session(path) as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value, path: Path | None = None) -> None:
    execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)), path)


def mark_update(what: str, path: Path | None = None) -> None:
    execute("INSERT OR REPLACE INTO updates VALUES (?, datetime('now'))", (what,), path)


def last_update(what: str, path: Path | None = None) -> str | None:
    with session(path) as con:
        row = con.execute("SELECT at FROM updates WHERE what=?", (what,)).fetchone()
    return row["at"] if row else None
