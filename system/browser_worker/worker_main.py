from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path when this file is executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.browser_worker.action_executor import BrowserActionExecutor
from system.browser_worker.protocol_handler import (
    build_error_response,
    build_event,
    build_protocol_error_response,
    build_success_response,
    parse_incoming_line,
    BrowserWorkerProtocolError,
)
from system.browser_worker.session_manager import BrowserWorkerActionError, BrowserWorkerSessionManager


def run_worker(workspace_root: Path) -> int:
    session_manager = BrowserWorkerSessionManager(workspace_root=workspace_root)
    action_executor = BrowserActionExecutor(session_manager=session_manager)

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue

            started = time.perf_counter()
            try:
                request_message = parse_incoming_line(line)
            except BrowserWorkerProtocolError as exc:
                fallback = _extract_request_fields(line)
                response = build_protocol_error_response(
                    request_id=fallback["request_id"],
                    source="browser_worker",
                    target=fallback["source"],
                    action=fallback["action"],
                    error_code=exc.error_code,
                    error_message=exc.error_message,
                    details=exc.details,
                )
                _write_message(response)
                continue

            message_type = request_message["message_type"]
            if message_type == "health":
                duration_ms = _duration_ms(started)
                result = {
                    "status": "ready",
                    "playwright_available": session_manager.playwright_available,
                    "session_count": session_manager.session_count,
                    "active_session_id": session_manager.active_session_id,
                    "session_ids": session_manager.list_session_ids(),
                }
                response = build_success_response(
                    request_message,
                    result=result,
                    duration_ms=duration_ms,
                )
                _write_message(response)
                continue

            if message_type == "control":
                if request_message["action"] == "shutdown":
                    duration_ms = _duration_ms(started)
                    response = build_success_response(
                        request_message,
                        result={"status": "shutting_down"},
                        duration_ms=duration_ms,
                    )
                    _write_message(response)
                    break

                duration_ms = _duration_ms(started)
                response = build_error_response(
                    request_message,
                    error_code="browser_action_not_supported",
                    error_message=f"Unsupported control action '{request_message['action']}'.",
                    details={"action": request_message["action"]},
                    duration_ms=duration_ms,
                )
                _write_message(response)
                continue

            _write_message(
                build_event(
                    request_message=request_message,
                    action="browser_command_started",
                    payload={
                        "action": request_message["action"],
                        "element_id": _extract_element_id(request_message),
                    },
                    session_id=request_message.get("session_id"),
                )
            )

            try:
                result = action_executor.execute(
                    action=request_message["action"],
                    session_id=request_message.get("session_id"),
                    payload=request_message.get("payload", {}),
                    metadata=request_message.get("metadata", {}),
                )
                duration_ms = _duration_ms(started)
                response = build_success_response(
                    request_message,
                    result=result,
                    duration_ms=duration_ms,
                )
                _write_message(response)
                _write_message(
                    build_event(
                        request_message=request_message,
                        action="browser_command_succeeded",
                        payload={
                            "action": request_message["action"],
                            "status": "success",
                            "element_id": result.get("element_id") or _extract_element_id(request_message),
                        },
                        session_id=result.get("session_id"),
                        duration_ms=duration_ms,
                    )
                )
            except BrowserWorkerActionError as exc:
                duration_ms = _duration_ms(started)
                response = build_error_response(
                    request_message,
                    error_code=exc.error_code,
                    error_message=exc.error_message,
                    details=exc.details,
                    duration_ms=duration_ms,
                )
                _write_message(response)
                _write_message(
                    build_event(
                        request_message=request_message,
                        action="browser_command_failed",
                        payload={
                            "action": request_message["action"],
                            "status": "error",
                            "error_code": exc.error_code,
                            "element_id": _extract_element_id(request_message),
                        },
                        session_id=request_message.get("session_id"),
                        duration_ms=duration_ms,
                    )
                )
            except Exception as exc:  # pragma: no cover - fallback safety
                duration_ms = _duration_ms(started)
                response = build_error_response(
                    request_message,
                    error_code="browser_worker_internal_error",
                    error_message=f"Unexpected browser worker error: {exc}",
                    details={},
                    duration_ms=duration_ms,
                )
                _write_message(response)
                _write_message(
                    build_event(
                        request_message=request_message,
                        action="browser_command_failed",
                        payload={
                            "action": request_message["action"],
                            "status": "error",
                            "error_code": "browser_worker_internal_error",
                            "element_id": _extract_element_id(request_message),
                        },
                        session_id=request_message.get("session_id"),
                        duration_ms=duration_ms,
                    )
                )
    finally:
        session_manager.shutdown()

    return 0


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _extract_request_fields(raw_line: str) -> dict[str, str]:
    request_id = f"invalid_{uuid.uuid4().hex}"
    source = "backend"
    action = "invalid_message"
    try:
        maybe = json.loads(raw_line)
    except Exception:
        return {"request_id": request_id, "source": source, "action": action}
    if not isinstance(maybe, dict):
        return {"request_id": request_id, "source": source, "action": action}
    if isinstance(maybe.get("request_id"), str) and maybe["request_id"]:
        request_id = maybe["request_id"]
    if isinstance(maybe.get("source"), str) and maybe["source"]:
        source = maybe["source"]
    if isinstance(maybe.get("action"), str) and maybe["action"]:
        action = maybe["action"]
    return {"request_id": request_id, "source": source, "action": action}


def _extract_element_id(request_message: dict[str, Any]) -> str | None:
    payload = request_message.get("payload")
    if not isinstance(payload, dict):
        return None
    element_id = payload.get("element_id")
    if not isinstance(element_id, str) or not element_id:
        return None
    return element_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capability OS Browser Worker")
    parser.add_argument(
        "--workspace-root",
        required=True,
        help="Workspace root used by the browser worker for path safety checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    return run_worker(workspace_root)


if __name__ == "__main__":
    raise SystemExit(main())
