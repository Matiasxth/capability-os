"""User repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class UserRepository:
    """CRUD for user accounts (passwords stored as bcrypt hashes)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, user: dict[str, Any]) -> None:
        extra = {k: v for k, v in user.items() if k not in (
            "id", "username", "display_name", "password_hash", "role", "created_at",
        )}
        self._db.upsert("users", {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name"),
            "password_hash": user["password_hash"],
            "role": user.get("role", "user"),
            "created_at": user.get("created_at"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, user_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))
        return self._to_user(row) if row else None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM users WHERE username=%s", (username,))
        return self._to_user(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM users ORDER BY created_at")
        return [self._to_user(r) for r in rows]

    def delete(self, user_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM users WHERE id=%s", (user_id,))
        self._db.execute("DELETE FROM users WHERE id=%s", (user_id,))
        return (before or {}).get("c", 0) > 0

    @staticmethod
    def _to_user(row: dict) -> dict[str, Any]:
        user = {
            "id": row["id"],
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "password_hash": row.get("password_hash"),
            "role": row.get("role", "user"),
            "created_at": row.get("created_at"),
        }
        data_str = row.get("data")
        if data_str:
            try:
                user.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return user
