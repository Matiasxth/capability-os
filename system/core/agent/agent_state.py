"""Agent session state management."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingConfirmation:
    confirmation_id: str
    tool_id: str
    params: dict[str, Any]
    security_level: int
    description: str
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 120.0

    @property
    def expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds


class AgentSession:
    """Tracks state for an active agent loop session."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or f"agent_{uuid.uuid4().hex[:12]}"
        self.messages: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pending: dict[str, PendingConfirmation] = {}
        self.iteration = 0
        self.status = "idle"  # idle | running | awaiting_confirmation | complete | error
        self.created_at = time.time()
        self.final_text: str | None = None

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str, tool_calls: list[dict] | None = None) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_id: str, call_id: str, result: Any, success: bool = True) -> None:
        self.messages.append({
            "role": "tool_result",
            "tool_id": tool_id,
            "tool_call_id": call_id,
            "content": result,
            "success": success,
        })

    def add_event(self, event: dict[str, Any]) -> None:
        event.setdefault("timestamp", time.time())
        event.setdefault("iteration", self.iteration)
        self.events.append(event)

    def set_pending(self, confirmation: PendingConfirmation) -> None:
        self.pending[confirmation.confirmation_id] = confirmation
        self.status = "awaiting_confirmation"

    def resolve_confirmation(self, confirmation_id: str, approved: bool) -> PendingConfirmation | None:
        conf = self.pending.pop(confirmation_id, None)
        if conf is None:
            return None
        if not approved or conf.expired:
            self.status = "running"
            return conf
        self.status = "running"
        return conf

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "iteration": self.iteration,
            "message_count": len(self.messages),
            "event_count": len(self.events),
            "pending_confirmations": [
                {"confirmation_id": c.confirmation_id, "tool_id": c.tool_id, "security_level": c.security_level, "description": c.description, "expired": c.expired}
                for c in self.pending.values()
            ],
            "final_text": self.final_text,
        }
