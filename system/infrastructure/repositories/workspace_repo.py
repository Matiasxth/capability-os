"""Workspace repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class WorkspaceRepository:
    """CRUD for workspace entries."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, ws: dict[str, Any]) -> None:
        extra = {k: v for k, v in ws.items() if k not in ("id", "name", "path", "access", "color", "is_default", "created_at")}
        self._db.upsert("workspaces", {
            "id": ws["id"],
            "name": ws.get("name"),
            "path": ws.get("path"),
            "access": ws.get("access", "write"),
            "color": ws.get("color", "#00ff88"),
            "is_default": 1 if ws.get("is_default") else 0,
            "created_at": ws.get("created_at"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, ws_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM workspaces WHERE id=%s", (ws_id,))
        return self._to_ws(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM workspaces ORDER BY created_at")
        return [self._to_ws(r) for r in rows]

    def update(self, ws_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(ws_id)
        if not existing:
            return None
        existing.update(fields)
        self.add(existing)
        return existing

    def delete(self, ws_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM workspaces WHERE id=%s", (ws_id,))
        self._db.execute("DELETE FROM workspaces WHERE id=%s", (ws_id,))
        return (before or {}).get("c", 0) > 0

    def set_default(self, ws_id: str) -> None:
        self._db.execute("UPDATE workspaces SET is_default=0")
        self._db.execute("UPDATE workspaces SET is_default=1 WHERE id=%s", (ws_id,))

    def get_default_id(self) -> str | None:
        row = self._db.fetch_one("SELECT id FROM workspaces WHERE is_default=1")
        return row["id"] if row else None

    @staticmethod
    def _to_ws(row: dict) -> dict[str, Any]:
        ws = {"id": row["id"], "name": row.get("name"), "path": row.get("path"),
              "access": row.get("access", "write"), "color": row.get("color", "#00ff88"),
              "is_default": bool(row.get("is_default")), "created_at": row.get("created_at")}
        data_str = row.get("data")
        if data_str:
            try:
                ws.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return ws
