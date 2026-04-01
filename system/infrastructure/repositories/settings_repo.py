"""Settings repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class SettingsRepository:
    """Key-value settings store."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get(self, key: str) -> Any | None:
        row = self._db.fetch_one("SELECT value FROM settings WHERE key=%s", (key,))
        if row is None:
            return None
        raw = row.get("value")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        return raw

    def set(self, key: str, value: Any) -> None:
        self._db.upsert("settings", {
            "key": key,
            "value": json.dumps(value, default=str),
        }, pk="key")

    def get_all(self) -> dict[str, Any]:
        rows = self._db.fetch_all("SELECT key, value FROM settings")
        result: dict[str, Any] = {}
        for row in rows:
            raw = row.get("value")
            try:
                result[row["key"]] = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = raw
        return result

    def delete(self, key: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM settings WHERE key=%s", (key,))
        self._db.execute("DELETE FROM settings WHERE key=%s", (key,))
        return (before or {}).get("c", 0) > 0
