"""Task queue repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class QueueRepository:
    """CRUD for scheduled task queue entries."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, task: dict[str, Any]) -> None:
        extra = {k: v for k, v in task.items() if k not in (
            "id", "description", "schedule", "enabled",
            "action_message", "agent_id", "channel", "last_run", "created_at",
        )}
        action = task.get("action")
        action_msg = task.get("action_message")
        if action_msg is None and isinstance(action, dict):
            action_msg = action.get("message")
        self._db.upsert("task_queue", {
            "id": task["id"],
            "description": task.get("description"),
            "schedule": task.get("schedule"),
            "enabled": 1 if task.get("enabled", True) else 0,
            "action_message": action_msg,
            "agent_id": task.get("agent_id"),
            "channel": task.get("channel"),
            "last_run": task.get("last_run"),
            "created_at": task.get("created_at"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM task_queue WHERE id=%s", (task_id,))
        return self._to_task(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM task_queue ORDER BY created_at")
        return [self._to_task(r) for r in rows]

    def delete(self, task_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM task_queue WHERE id=%s", (task_id,))
        self._db.execute("DELETE FROM task_queue WHERE id=%s", (task_id,))
        return (before or {}).get("c", 0) > 0

    @staticmethod
    def _to_task(row: dict) -> dict[str, Any]:
        task = {
            "id": row["id"],
            "description": row.get("description"),
            "schedule": row.get("schedule"),
            "enabled": bool(row.get("enabled", 1)),
            "action_message": row.get("action_message"),
            "agent_id": row.get("agent_id"),
            "channel": row.get("channel"),
            "last_run": row.get("last_run"),
            "created_at": row.get("created_at"),
        }
        data_str = row.get("data")
        if data_str:
            try:
                task.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return task
