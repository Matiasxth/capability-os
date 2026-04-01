"""Execution history repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class ExecutionRepository:
    """CRUD for execution history entries."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def insert(self, entry: dict[str, Any]) -> None:
        extra = {k: v for k, v in entry.items() if k not in (
            "id", "execution_id", "capability_id", "intent", "status",
            "duration_ms", "timestamp", "error_code", "error_message",
            "failed_step", "workspace_id",
        )}
        self._db.upsert("executions", {
            "id": entry.get("execution_id") or entry.get("id"),
            "capability_id": entry.get("capability_id"),
            "intent": entry.get("intent"),
            "status": entry.get("status", "success"),
            "duration_ms": entry.get("duration_ms", 0),
            "timestamp": entry.get("timestamp"),
            "error_code": entry.get("error_code"),
            "error_message": entry.get("error_message"),
            "failed_step": entry.get("failed_step"),
            "workspace_id": entry.get("workspace_id"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, execution_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM executions WHERE id=%s", (execution_id,))
        return self._to_entry(row) if row else None

    def get_recent(self, n: int = 20, workspace_id: str | None = None) -> list[dict[str, Any]]:
        if workspace_id:
            rows = self._db.fetch_all(
                "SELECT * FROM executions WHERE workspace_id=%s ORDER BY timestamp DESC LIMIT %s",
                (workspace_id, n),
            )
        else:
            rows = self._db.fetch_all(
                "SELECT * FROM executions ORDER BY timestamp DESC LIMIT %s", (n,),
            )
        return [self._to_entry(r) for r in rows]

    def search(self, query: str, n: int = 10) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        rows = self._db.fetch_all(
            "SELECT * FROM executions WHERE intent LIKE %s OR capability_id LIKE %s ORDER BY timestamp DESC LIMIT %s",
            (pattern, pattern, n),
        )
        return [self._to_entry(r) for r in rows]

    def delete(self, execution_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM executions WHERE id=%s", (execution_id,))
        self._db.execute("DELETE FROM executions WHERE id=%s", (execution_id,))
        return (before or {}).get("c", 0) > 0

    def clear(self) -> None:
        self._db.execute("DELETE FROM executions")

    def count(self) -> int:
        row = self._db.fetch_one("SELECT COUNT(*) as c FROM executions")
        return (row or {}).get("c", 0)

    @staticmethod
    def _to_entry(row: dict) -> dict[str, Any]:
        entry = {
            "execution_id": row.get("id"),
            "capability_id": row.get("capability_id"),
            "intent": row.get("intent"),
            "status": row.get("status"),
            "duration_ms": row.get("duration_ms"),
            "timestamp": row.get("timestamp"),
            "error_code": row.get("error_code"),
            "error_message": row.get("error_message"),
            "failed_step": row.get("failed_step"),
            "workspace_id": row.get("workspace_id"),
        }
        data_str = row.get("data")
        if data_str:
            try:
                extra = json.loads(data_str) if isinstance(data_str, str) else data_str
                entry.update(extra)
            except Exception:
                pass
        return entry
