"""Persistent registry of custom agent definitions.

Each agent has a personality (system prompt), allowed tools, optional
LLM model override, and can be assigned to multiple workspaces.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


DEFAULT_AGENT = {
    "id": "agt_default",
    "name": "CapOS",
    "emoji": "\U0001f916",
    "description": "Default assistant — general purpose with all tools",
    "system_prompt": "",
    "tool_ids": [],
    "llm_provider": None,
    "llm_model": None,
    "security_level": "standard",
    "language": "auto",
    "max_iterations": 10,
    "enabled": True,
    "created_at": "2026-01-01T00:00:00Z",
}


class AgentRegistry:
    """CRUD for custom agent definitions. Persisted to agents.json."""

    def __init__(self, data_path: str | Path) -> None:
        self._path = Path(data_path).resolve()
        self._lock = RLock()
        self._agents: dict[str, dict[str, Any]] = {}
        self._load()
        # Ensure default agent exists
        if "agt_default" not in self._agents:
            self._agents["agt_default"] = deepcopy(DEFAULT_AGENT)
            self._save()

    def add(
        self,
        name: str,
        emoji: str = "\U0001f916",
        description: str = "",
        system_prompt: str = "",
        tool_ids: list[str] | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        security_level: str = "standard",
        language: str = "auto",
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Agent name must be non-empty.")
        with self._lock:
            agent_id = f"agt_{uuid4().hex[:8]}"
            record: dict[str, Any] = {
                "id": agent_id,
                "name": name.strip(),
                "emoji": emoji or "\U0001f916",
                "description": description,
                "system_prompt": system_prompt,
                "tool_ids": tool_ids or [],
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "security_level": security_level,
                "language": language,
                "max_iterations": max(1, min(50, max_iterations)),
                "enabled": True,
                "created_at": _now(),
            }
            self._agents[agent_id] = record
            self._save()
            return deepcopy(record)

    def update(self, agent_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                raise KeyError(f"Agent '{agent_id}' not found.")
            allowed = {
                "name", "emoji", "description", "system_prompt", "tool_ids",
                "llm_provider", "llm_model", "security_level", "language",
                "max_iterations", "enabled",
            }
            for k, v in fields.items():
                if k in allowed:
                    agent[k] = v
            if "max_iterations" in fields:
                agent["max_iterations"] = max(1, min(50, agent["max_iterations"]))
            self._save()
            return deepcopy(agent)

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id == "agt_default":
                raise ValueError("Cannot remove the default agent.")
            if agent_id not in self._agents:
                return False
            del self._agents[agent_id]
            self._save()
            return True

    def get(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            a = self._agents.get(agent_id)
            return deepcopy(a) if a else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(a) for a in self._agents.values()]

    def get_for_workspace(self, agent_ids: list[str]) -> list[dict[str, Any]]:
        """Return agents matching the given IDs."""
        with self._lock:
            result = []
            for aid in agent_ids:
                a = self._agents.get(aid)
                if a:
                    result.append(deepcopy(a))
            return result

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._agents = {}
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for item in raw.get("agents", []):
                        if isinstance(item, dict) and "id" in item:
                            self._agents[item["id"]] = item
            except (json.JSONDecodeError, OSError):
                self._agents = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"agents": list(self._agents.values())}
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
