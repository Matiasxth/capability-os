"""Database abstraction — PostgreSQL with SQLite fallback.

Usage:
    from system.infrastructure.database import create_database
    db = create_database(settings)  # auto-detects PostgreSQL
    db.execute("INSERT INTO executions ...", params)
    rows = db.fetch_all("SELECT * FROM executions WHERE ...")
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Database:
    """Unified database interface — PostgreSQL or SQLite."""

    def __init__(self, backend: str, conn: Any, lock: threading.RLock | None = None) -> None:
        self.backend = backend  # "postgresql" or "sqlite"
        self._conn = conn
        self._lock = lock or threading.RLock()
        self._placeholder = "%s" if backend == "postgresql" else "?"

    def ph(self, sql: str) -> str:
        """Convert %s placeholders to ? for SQLite."""
        if self.backend == "sqlite":
            return sql.replace("%s", "?")
        return sql

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(self.ph(sql), params)
            self._conn.commit()

    def execute_many(self, sql: str, param_list: list[tuple]) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executemany(self.ph(sql), param_list)
            self._conn.commit()

    def fetch_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(self.ph(sql), params)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def fetch_all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(self.ph(sql), params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    def table_exists(self, table_name: str) -> bool:
        if self.backend == "postgresql":
            row = self.fetch_one(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                (table_name,),
            )
            return row.get("exists", False) if row else False
        row = self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return row is not None

    def upsert(self, table: str, data: dict[str, Any], pk: str = "id") -> None:
        """Insert or update a row — works on both PostgreSQL and SQLite."""
        cols = list(data.keys())
        vals = [data[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)

        if self.backend == "postgresql":
            update_cols = [c for c in cols if c != pk]
            if update_cols:
                update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({pk}) DO UPDATE SET {update_set}"
            else:
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({pk}) DO NOTHING"
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"

        self.execute(sql, tuple(vals))

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


def create_database(settings: dict | None = None, workspace_root: str | Path = ".") -> Database:
    """Factory: returns PostgreSQL if configured, else SQLite.

    Settings:
        {"database": {"url": "postgresql://...", "type": "postgresql"}}
    Or env:
        DATABASE_URL=postgresql://user:pass@host:5432/capos
    """
    settings = settings or {}
    db_config = settings.get("database", {})

    # Try PostgreSQL
    pg_url = db_config.get("url") or os.environ.get("DATABASE_URL", "")
    if pg_url and pg_url.startswith("postgresql"):
        try:
            import psycopg
            conn = psycopg.connect(pg_url, autocommit=True)
            db = Database("postgresql", conn)
            _init_schema(db)
            logger.info("Database: PostgreSQL connected")
            return db
        except ImportError:
            logger.info("psycopg not installed — falling back to SQLite")
        except Exception as exc:
            logger.warning("PostgreSQL connection failed (%s) — falling back to SQLite", exc)

    # Fallback: SQLite
    db_path = Path(workspace_root) / "memory" / "capos.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    db = Database("sqlite", conn)
    _init_schema(db)
    logger.info("Database: SQLite (%s)", db_path)
    return db


def _init_schema(db: Database) -> None:
    """Create tables if they don't exist."""

    jsonb = "JSONB" if db.backend == "postgresql" else "TEXT"
    ts_default = "CURRENT_TIMESTAMP" if db.backend == "sqlite" else "NOW()"

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            capability_id TEXT,
            intent TEXT,
            status TEXT DEFAULT 'success',
            duration_ms INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT {ts_default},
            error_code TEXT,
            error_message TEXT,
            failed_step TEXT,
            workspace_id TEXT,
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT,
            access TEXT DEFAULT 'write',
            color TEXT DEFAULT '#00ff88',
            is_default INTEGER DEFAULT 0,
            created_at TEXT DEFAULT {ts_default},
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '🤖',
            description TEXT,
            system_prompt TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT {ts_default},
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value {jsonb},
            updated_at TEXT DEFAULT {ts_default}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS task_queue (
            id TEXT PRIMARY KEY,
            description TEXT,
            schedule TEXT,
            enabled INTEGER DEFAULT 1,
            action_message TEXT,
            agent_id TEXT,
            channel TEXT,
            last_run TEXT,
            created_at TEXT DEFAULT {ts_default},
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS sequences (
            id TEXT PRIMARY KEY,
            name TEXT,
            data {jsonb},
            created_at TEXT DEFAULT {ts_default}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT {ts_default},
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT {ts_default},
            updated_at TEXT DEFAULT {ts_default},
            data {jsonb}
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS integrations (
            id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'discovered',
            validated INTEGER DEFAULT 0,
            last_validated_at TEXT,
            error TEXT,
            data {jsonb}
        )
    """)

    # Indexes
    if not db.table_exists("idx_executions_ts"):
        try:
            db.execute("CREATE INDEX IF NOT EXISTS idx_executions_ts ON executions(timestamp DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_executions_cap ON executions(capability_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_executions_ws ON executions(workspace_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        except Exception:
            pass
