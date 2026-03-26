from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = "1.0"
MESSAGE_TYPES = {"command", "response", "event", "health", "control"}


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_message(
    *,
    message_type: str,
    action: str,
    source: str,
    target: str,
    request_id: str | None = None,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"Unsupported message_type '{message_type}'.")
    if not isinstance(action, str) or not action:
        raise ValueError("Field 'action' must be a non-empty string.")
    if not isinstance(source, str) or not source:
        raise ValueError("Field 'source' must be a non-empty string.")
    if not isinstance(target, str) or not target:
        raise ValueError("Field 'target' must be a non-empty string.")

    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": message_type,
        "request_id": request_id or new_request_id(),
        "timestamp": utc_timestamp(),
        "source": source,
        "target": target,
        "action": action,
        "session_id": session_id,
        "payload": payload or {},
        "metadata": metadata or {},
    }


def build_command_message(
    *,
    action: str,
    payload: dict[str, Any] | None = None,
    session_id: str | None = None,
    timeout_ms: int | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    source: str = "backend",
    target: str = "browser_worker",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if timeout_ms is not None:
        metadata["timeout_ms"] = timeout_ms
    if trace_id:
        metadata["trace_id"] = trace_id

    return build_message(
        message_type="command",
        action=action,
        source=source,
        target=target,
        request_id=request_id,
        session_id=session_id,
        payload=payload or {},
        metadata=metadata,
    )


def build_health_message(
    *,
    request_id: str | None = None,
    source: str = "backend",
    target: str = "browser_worker",
) -> dict[str, Any]:
    return build_message(
        message_type="health",
        action="ping",
        source=source,
        target=target,
        request_id=request_id,
        payload={},
        metadata={},
    )


def build_control_message(
    *,
    action: str,
    request_id: str | None = None,
    source: str = "backend",
    target: str = "browser_worker",
) -> dict[str, Any]:
    return build_message(
        message_type="control",
        action=action,
        source=source,
        target=target,
        request_id=request_id,
        payload={},
        metadata={},
    )
