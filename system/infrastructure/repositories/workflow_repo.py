"""Workflow repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class WorkflowRepository:
    """CRUD for visual workflow definitions."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, wf: dict[str, Any]) -> None:
        extra = {k: v for k, v in wf.items() if k not in (
            "id", "name", "description", "created_at", "updated_at",
        )}
        self._db.upsert("workflows", {
            "id": wf["id"],
            "name": wf.get("name"),
            "description": wf.get("description"),
            "created_at": wf.get("created_at"),
            "updated_at": wf.get("updated_at"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, wf_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM workflows WHERE id=%s", (wf_id,))
        return self._to_wf(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM workflows ORDER BY updated_at DESC")
        return [self._to_wf(r) for r in rows]

    def delete(self, wf_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM workflows WHERE id=%s", (wf_id,))
        self._db.execute("DELETE FROM workflows WHERE id=%s", (wf_id,))
        return (before or {}).get("c", 0) > 0

    @staticmethod
    def _to_wf(row: dict) -> dict[str, Any]:
        wf = {
            "id": row["id"],
            "name": row.get("name"),
            "description": row.get("description"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        data_str = row.get("data")
        if data_str:
            try:
                wf.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return wf
