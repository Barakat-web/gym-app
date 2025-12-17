"""
db.py
SQLite helpers + initialization (creates DB/tables, inserts default admin, etc.)
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

DB_FILE = Path(__file__).with_name("gym.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def executemany(sql: str, seq_of_params: list[tuple]) -> None:
    with get_conn() as conn:
        conn.executemany(sql, seq_of_params)


def fetch_one(sql: str, params: tuple = ()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def _create_tables() -> None:
    # Required tables (per spec)
    execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            national_id TEXT,
            join_date TEXT NOT NULL,
            plan_type TEXT NOT NULL,
            plan_price REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','expired'))
        )
        """
    )

    execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            method TEXT NOT NULL CHECK(method IN ('cash','card','transfer')),
            notes TEXT,
            FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
        )
        """
    )

    # Small settings table (used to force password change on first login)
    execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


def _get_setting(key: str, default: str | None = None) -> str | None:
    row = fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    if row:
        return str(row["value"])
    return default


def _set_setting(key: str, value: str) -> None:
    execute(
        """
        INSERT INTO app_settings(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )


def init_db(default_admin_hash: str) -> None:
    """
    Initialize the database.
    - Create tables
    - Insert default admin (admin/admin123) if no admin exists
    - Force password change on first login
    """
    _create_tables()

    admin = fetch_one("SELECT id FROM admin_users LIMIT 1")
    if not admin:
        now = datetime.utcnow().isoformat(timespec="seconds")
        execute(
            "INSERT INTO admin_users(username, password_hash, created_at) VALUES(?,?,?)",
            ("admin", default_admin_hash, now),
        )
        _set_setting("force_password_change", "1")
    else:
        # ensure setting exists
        if _get_setting("force_password_change") is None:
            _set_setting("force_password_change", "0")


def is_force_password_change() -> bool:
    val = fetch_one("SELECT value FROM app_settings WHERE key = ?", ("force_password_change",))
    return bool(val and str(val["value"]) == "1")


def clear_force_password_change() -> None:
    _set_setting("force_password_change", "0")
