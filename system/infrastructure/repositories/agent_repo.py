"""Agent registry repository — PostgreSQL/SQLite backed."""
from __future__ import annotations

import json
from typing import Any


class AgentRepository:
    """CRUD for agent definitions."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def add(self, agent: dict[str, Any]) -> None:
        extra = {k: v for k, v in agent.items() if k not in ("id", "name", "emoji", "description", "system_prompt", "enabled", "created_at")}
        self._db.upsert("agents", {
            "id": agent["id"],
            "name": agent.get("name"),
            "emoji": agent.get("emoji", "🤖"),
            "description": agent.get("description"),
            "system_prompt": agent.get("system_prompt"),
            "enabled": 1 if agent.get("enabled", True) else 0,
            "created_at": agent.get("created_at"),
            "data": json.dumps(extra, default=str),
        })

    def get(self, agent_id: str) -> dict[str, Any] | None:
        row = self._db.fetch_one("SELECT * FROM agents WHERE id=%s", (agent_id,))
        return self._to_agent(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.fetch_all("SELECT * FROM agents ORDER BY created_at")
        return [self._to_agent(r) for r in rows]

    def update(self, agent_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(agent_id)
        if not existing:
            return None
        existing.update(fields)
        self.add(existing)
        return existing

    def delete(self, agent_id: str) -> bool:
        before = self._db.fetch_one("SELECT COUNT(*) as c FROM agents WHERE id=%s", (agent_id,))
        self._db.execute("DELETE FROM agents WHERE id=%s", (agent_id,))
        return (before or {}).get("c", 0) > 0

    @staticmethod
    def _to_agent(row: dict) -> dict[str, Any]:
        agent = {"id": row["id"], "name": row.get("name"), "emoji": row.get("emoji", "🤖"),
                 "description": row.get("description"), "system_prompt": row.get("system_prompt"),
                 "enabled": bool(row.get("enabled", 1)), "created_at": row.get("created_at")}
        data_str = row.get("data")
        if data_str:
            try:
                agent.update(json.loads(data_str) if isinstance(data_str, str) else data_str)
            except Exception:
                pass
        return agent
