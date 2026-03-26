from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = "1.0"
MESSAGE_TYPES = {"command", "response", "event", "health", "control"}


class BrowserWorkerProtocolError(RuntimeError):
    def __init__(self, error_code: str, error_message: str, details: dict[str, Any] | None = None):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}


def parse_incoming_line(raw_line: str) -> dict[str, Any]:
    line = raw_line.strip()
    if not line:
        raise BrowserWorkerProtocolError("invalid_message", "Received empty message line.")

    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise BrowserWorkerProtocolError(
            "invalid_json",
            f"Incoming message is not valid JSON: {exc}",
        ) from exc

    if not isinstance(message, dict):
        raise BrowserWorkerProtocolError("invalid_message", "Incoming message must be a JSON object.")

    _validate_incoming_message(message)
    return message


def build_success_response(
    request_message: dict[str, Any],
    *,
    result: dict[str, Any],
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "response",
        "request_id": request_message["request_id"],
        "timestamp": _timestamp(),
        "source": "browser_worker",
        "target": request_message["source"],
        "action": request_message["action"],
        "session_id": result.get("session_id", request_message.get("session_id")),
        "payload": {},
        "metadata": _response_metadata(request_message, duration_ms),
        "status": "success",
        "result": result,
        "error": None,
    }


def build_error_response(
    request_message: dict[str, Any],
    *,
    error_code: str,
    error_message: str,
    details: dict[str, Any] | None,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "response",
        "request_id": request_message["request_id"],
        "timestamp": _timestamp(),
        "source": "browser_worker",
        "target": request_message["source"],
        "action": request_message["action"],
        "session_id": request_message.get("session_id"),
        "payload": {},
        "metadata": _response_metadata(request_message, duration_ms),
        "status": "error",
        "result": {},
        "error": {
            "error_code": error_code,
            "error_message": error_message,
            "details": details or {},
        },
    }


def build_event(
    *,
    request_message: dict[str, Any],
    action: str,
    payload: dict[str, Any] | None = None,
    session_id: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    event_metadata: dict[str, Any] = {}
    request_metadata = request_message.get("metadata")
    if isinstance(request_metadata, dict):
        trace_id = request_metadata.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            event_metadata["trace_id"] = trace_id
    if duration_ms is not None:
        event_metadata["duration_ms"] = duration_ms

    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "event",
        "request_id": request_message["request_id"],
        "timestamp": _timestamp(),
        "source": "browser_worker",
        "target": request_message["source"],
        "action": action,
        "session_id": session_id or request_message.get("session_id"),
        "payload": payload or {},
        "metadata": event_metadata,
    }


def build_protocol_error_response(
    *,
    request_id: str,
    source: str,
    target: str,
    action: str,
    error_code: str,
    error_message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "response",
        "request_id": request_id,
        "timestamp": _timestamp(),
        "source": source,
        "target": target,
        "action": action,
        "session_id": None,
        "payload": {},
        "metadata": {},
        "status": "error",
        "result": {},
        "error": {
            "error_code": error_code,
            "error_message": error_message,
            "details": details or {},
        },
    }


def _validate_incoming_message(message: dict[str, Any]) -> None:
    protocol_version = message.get("protocol_version")
    if protocol_version != PROTOCOL_VERSION:
        raise BrowserWorkerProtocolError(
            "protocol_version_mismatch",
            f"Unsupported protocol_version '{protocol_version}'. Expected '{PROTOCOL_VERSION}'.",
        )

    message_type = message.get("message_type")
    if message_type not in MESSAGE_TYPES:
        raise BrowserWorkerProtocolError(
            "invalid_message_type",
            f"Unsupported message_type '{message_type}'.",
        )
    if message_type not in {"command", "health", "control"}:
        raise BrowserWorkerProtocolError(
            "invalid_message_type",
            f"Worker accepts only command/health/control as incoming types, got '{message_type}'.",
        )

    request_id = message.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise BrowserWorkerProtocolError("invalid_request_id", "Field 'request_id' must be a non-empty string.")

    timestamp = message.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        raise BrowserWorkerProtocolError("invalid_timestamp", "Field 'timestamp' must be a non-empty string.")

    source = message.get("source")
    target = message.get("target")
    action = message.get("action")
    if not isinstance(source, str) or not source:
        raise BrowserWorkerProtocolError("invalid_source", "Field 'source' must be a non-empty string.")
    if not isinstance(target, str) or not target:
        raise BrowserWorkerProtocolError("invalid_target", "Field 'target' must be a non-empty string.")
    if not isinstance(action, str) or not action:
        raise BrowserWorkerProtocolError("invalid_action", "Field 'action' must be a non-empty string.")

    session_id = message.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        raise BrowserWorkerProtocolError("invalid_session_id", "Field 'session_id' must be a string or null.")

    payload = message.get("payload")
    if payload is None:
        message["payload"] = {}
    elif not isinstance(payload, dict):
        raise BrowserWorkerProtocolError("invalid_payload", "Field 'payload' must be an object.")

    metadata = message.get("metadata")
    if metadata is None:
        message["metadata"] = {}
    elif not isinstance(metadata, dict):
        raise BrowserWorkerProtocolError("invalid_metadata", "Field 'metadata' must be an object.")


def _response_metadata(request_message: dict[str, Any], duration_ms: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {"duration_ms": duration_ms}
    request_metadata = request_message.get("metadata")
    if isinstance(request_metadata, dict):
        trace_id = request_metadata.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            metadata["trace_id"] = trace_id
    return metadata


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

