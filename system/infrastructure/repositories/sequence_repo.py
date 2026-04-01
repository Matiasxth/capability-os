"""Sequence repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class SequenceRepository:
    """CRUD for sequence definitions."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def save(self, sequence_id: str, definition: dict[str, Any]) -> None:
        name = definition.get("name") or definition.get("id") or sequence_id
        self._db.upsert("sequences", {
            "id": sequence_id,
            "name": name,
            "data": json.dumps(definition, default=str),
            "created_at": definition.get("created_at"),
        })

    def load(self, sequence_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM sequences WHERE id=%s", (sequence_id,))
        if row is None:
            return None
        data_str = row.get("data")
        if data_str:
            try:
                return json.loads(data_str) if isinstance(data_str, str) else data_str
            except (json.JSONDecodeError, TypeError):
                pass
        return {"id": row["id"], "name": row.get("name")}

    def list_ids(self) -> list[str]:
        rows = self._db.fetch_all("SELECT id FROM sequences ORDER BY created_at")
        return [r["id"] for r in rows]

    def delete(self, sequence_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM sequences WHERE id=%s", (sequence_id,))
        self._db.execute("DELETE FROM sequences WHERE id=%s", (sequence_id,))
        return (before or {}).get("c", 0) > 0
