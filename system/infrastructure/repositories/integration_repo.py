"""Integration registry repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class IntegrationRepository:
    """CRUD for integration state entries."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, entry: dict[str, Any]) -> None:
        extra = {k: v for k, v in entry.items() if k not in (
            "id", "status", "validated", "last_validated_at", "error",
        )}
        self._db.upsert("integrations", {
            "id": entry["id"],
            "status": entry.get("status", "discovered"),
            "validated": 1 if entry.get("validated") else 0,
            "last_validated_at": entry.get("last_validated_at"),
            "error": entry.get("error"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, integration_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM integrations WHERE id=%s", (integration_id,))
        return self._to_entry(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM integrations ORDER BY id")
        return [self._to_entry(r) for r in rows]

    def delete(self, integration_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM integrations WHERE id=%s", (integration_id,))
        self._db.execute("DELETE FROM integrations WHERE id=%s", (integration_id,))
        return (before or {}).get("c", 0) > 0

    @staticmethod
    def _to_entry(row: dict) -> dict[str, Any]:
        entry = {
            "id": row["id"],
            "status": row.get("status", "discovered"),
            "validated": bool(row.get("validated")),
            "last_validated_at": row.get("last_validated_at"),
            "error": row.get("error"),
        }
        data_str = row.get("data")
        if data_str:
            try:
                entry.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return entry
