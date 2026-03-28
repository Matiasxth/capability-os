"""A2A Server — receives tasks from external agents and executes them.

Task lifecycle: submitted → working → completed | failed.

An incoming A2A task is mapped to a capability execution:
  - ``task.skill_id``  → ``capability_id``
  - ``task.message``   → capability ``inputs``

The result is returned as an A2A artifact with text content.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import (
    CapabilityEngine,
    CapabilityExecutionError,
    CapabilityInputError,
)


class A2AServer:
    """Processes A2A tasks by delegating to the CapabilityEngine."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        capability_engine: CapabilityEngine | None = None,
    ):
        self._registry = capability_registry
        self._engine = capability_engine
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Public: handle an incoming task request
    # ------------------------------------------------------------------

    def handle_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process a ``tasks/send`` request and return the task result."""
        params = payload.get("params", payload)
        skill_id = params.get("skill_id") or params.get("skillId") or ""
        message_text = _extract_message_text(params)
        task_id = params.get("id") or f"task_{uuid4().hex[:8]}"

        # Create task record
        task = self._create_task(task_id, skill_id, message_text)

        # Resolve capability
        contract = self._registry.get(skill_id)
        if contract is None:
            return self._fail_task(task, "skill_not_found", f"Skill '{skill_id}' not found.")

        if self._engine is None:
            return self._fail_task(task, "no_engine", "No engine configured.")

        # Mark working
        task["status"] = {"state": "working", "timestamp": _now_iso()}
        self._store(task)

        # Execute
        try:
            inputs = _parse_inputs(message_text, contract)
            result = self._engine.execute(contract, inputs)
        except (CapabilityExecutionError, CapabilityInputError) as exc:
            return self._fail_task(task, "execution_error", str(exc))
        except Exception as exc:
            return self._fail_task(task, "internal_error", str(exc))

        # Build artifact
        final_output = result.get("final_output", {})
        text = json.dumps(final_output, ensure_ascii=False, default=str) if isinstance(final_output, dict) else str(final_output)

        task["status"] = {"state": "completed", "timestamp": _now_iso()}
        task["artifacts"] = [
            {
                "parts": [{"type": "text", "text": text}],
                "index": 0,
            }
        ]
        self._store(task)
        return deepcopy(task)

    # ------------------------------------------------------------------
    # Public: query tasks
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return deepcopy(task) if task else None

    def list_events(self, task_id: str) -> list[dict[str, Any]] | None:
        """Return status history for a task (for SSE streaming)."""
        task = self.get_task(task_id)
        if task is None:
            return None
        events: list[dict[str, Any]] = []
        status = task.get("status", {})
        events.append({"type": "status", "data": status})
        if task.get("artifacts"):
            events.append({"type": "artifact", "data": task["artifacts"]})
        return events

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_task(self, task_id: str, skill_id: str, message: str) -> dict[str, Any]:
        task: dict[str, Any] = {
            "id": task_id,
            "skill_id": skill_id,
            "status": {"state": "submitted", "timestamp": _now_iso()},
            "message": message,
            "artifacts": [],
        }
        self._store(task)
        return task

    def _fail_task(self, task: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        task["status"] = {
            "state": "failed",
            "timestamp": _now_iso(),
            "error": {"code": code, "message": message},
        }
        self._store(task)
        return deepcopy(task)

    def _store(self, task: dict[str, Any]) -> None:
        with self._lock:
            self._tasks[task["id"]] = task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_message_text(params: dict[str, Any]) -> str:
    """Extract text content from A2A message format."""
    message = params.get("message", {})
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        parts = message.get("parts", [])
        if isinstance(parts, list):
            texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
            if texts:
                return " ".join(texts)
        # Fallback: check for role/content style
        content = message.get("content", "")
        if isinstance(content, str):
            return content
    return str(message) if message else ""


def _parse_inputs(message_text: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Try to parse message as JSON inputs; fallback to first required field."""
    # Try JSON parse
    text = message_text.strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: assign to first required input field
    inputs_spec = contract.get("inputs", {})
    for field_name, field_def in inputs_spec.items():
        if isinstance(field_def, dict) and field_def.get("required"):
            return {field_name: message_text}

    # Last resort: if there's any input, use the first one
    if inputs_spec:
        first_key = next(iter(inputs_spec))
        return {first_key: message_text}

    return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
