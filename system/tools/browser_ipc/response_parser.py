from __future__ import annotations

import json
from typing import Any

from .message_builder import MESSAGE_TYPES, PROTOCOL_VERSION


class IPCProtocolError(RuntimeError):
    """Raised when an IPC message does not follow the protocol contract."""


def parse_message_line(raw_line: str) -> dict[str, Any]:
    line = raw_line.strip()
    if not line:
        raise IPCProtocolError("Received empty IPC message line.")

    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise IPCProtocolError(f"Worker emitted invalid JSON: {exc}") from exc

    if not isinstance(message, dict):
        raise IPCProtocolError("Worker message must be a JSON object.")

    _validate_base_fields(message)
    return message


def parse_response_for_request(message: dict[str, Any], request_id: str) -> dict[str, Any]:
    _validate_base_fields(message)

    if message["message_type"] != "response":
        raise IPCProtocolError(
            f"Expected response for request '{request_id}', got '{message['message_type']}'."
        )
    if message["request_id"] != request_id:
        raise IPCProtocolError(
            f"Response request_id mismatch: expected '{request_id}', got '{message['request_id']}'."
        )

    status = message.get("status")
    if status not in {"success", "error"}:
        raise IPCProtocolError("Response field 'status' must be 'success' or 'error'.")

    metadata = message.get("metadata")
    if not isinstance(metadata, dict):
        raise IPCProtocolError("Response field 'metadata' must be an object.")

    if status == "success":
        result = message.get("result")
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise IPCProtocolError("Successful response field 'result' must be an object.")
        return {
            "status": "success",
            "result": result,
            "metadata": metadata,
        }

    error = message.get("error")
    if not isinstance(error, dict):
        raise IPCProtocolError("Error response field 'error' must be an object.")

    error_code = error.get("error_code")
    error_message = error.get("error_message")
    if not isinstance(error_code, str) or not error_code:
        raise IPCProtocolError("Error response field 'error.error_code' must be a non-empty string.")
    if not isinstance(error_message, str) or not error_message:
        raise IPCProtocolError("Error response field 'error.error_message' must be a non-empty string.")

    details = error.get("details")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise IPCProtocolError("Error response field 'error.details' must be an object when present.")

    return {
        "status": "error",
        "error": {
            "error_code": error_code,
            "error_message": error_message,
            "details": details,
        },
        "metadata": metadata,
    }


def _validate_base_fields(message: dict[str, Any]) -> None:
    protocol_version = message.get("protocol_version")
    if protocol_version != PROTOCOL_VERSION:
        raise IPCProtocolError(
            f"Unsupported protocol_version '{protocol_version}', expected '{PROTOCOL_VERSION}'."
        )

    message_type = message.get("message_type")
    if message_type not in MESSAGE_TYPES:
        raise IPCProtocolError(f"Unsupported message_type '{message_type}'.")

    request_id = message.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise IPCProtocolError("Field 'request_id' must be a non-empty string.")

    timestamp = message.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        raise IPCProtocolError("Field 'timestamp' must be a non-empty string.")

    source = message.get("source")
    target = message.get("target")
    action = message.get("action")
    if not isinstance(source, str) or not source:
        raise IPCProtocolError("Field 'source' must be a non-empty string.")
    if not isinstance(target, str) or not target:
        raise IPCProtocolError("Field 'target' must be a non-empty string.")
    if not isinstance(action, str) or not action:
        raise IPCProtocolError("Field 'action' must be a non-empty string.")

    metadata = message.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise IPCProtocolError("Field 'metadata' must be an object.")

    payload = message.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise IPCProtocolError("Field 'payload' must be an object.")

