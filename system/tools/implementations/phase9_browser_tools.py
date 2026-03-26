from __future__ import annotations

import json
import os
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from system.tools.browser_ipc import BrowserIPCClient, BrowserIPCError


class BrowserToolError(RuntimeError):
    """Structured browser tool error for stable reporting in runtime."""

    def __init__(self, error_code: str, error_message: str, details: dict[str, Any] | None = None):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __str__(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True)


class BrowserSessionManager:
    """Session-aware manager for browser tools with isolated worker IPC backend."""

    def __init__(
        self,
        workspace_root: str | Path,
        ipc_client: BrowserIPCClient | None = None,
        artifacts_root: str | Path | None = None,
        auto_start: bool = True,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self._ipc_client = ipc_client or BrowserIPCClient(workspace_root=self.workspace_root)
        self._artifacts_root = _resolve_artifacts_root(self.workspace_root, artifacts_root)
        self._sessions: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.RLock()
        self._active_session_id: str | None = None
        self._auto_start = bool(auto_start)

    def set_auto_start(self, auto_start: bool) -> None:
        if not isinstance(auto_start, bool):
            raise BrowserToolError("invalid_input", "Field 'auto_start' must be boolean.")
        with self._lock:
            self._auto_start = auto_start

    def set_artifacts_root(self, artifacts_root: str | Path) -> None:
        self._artifacts_root = _resolve_artifacts_root(self.workspace_root, artifacts_root)
        self._artifacts_root.mkdir(parents=True, exist_ok=True)

    def restart_worker(self) -> dict[str, Any]:
        self._ipc_client.restart()
        with self._lock:
            self._sessions.clear()
            self._active_session_id = None

        if self._auto_start:
            try:
                self._ipc_client.health_check(timeout_ms=2000)
            except BrowserIPCError:
                pass
        return self.status_snapshot()

    def open_session(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        headless = params.get("headless", True)
        if not isinstance(headless, bool):
            raise BrowserToolError("invalid_input", "Field 'headless' must be a boolean when provided.")

        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        payload: dict[str, Any] = {"headless": headless}
        start_url = params.get("start_url")
        if start_url not in (None, ""):
            _validate_url(start_url)
            payload["start_url"] = start_url

        result = self._execute_command(
            action="browser_open_session",
            payload=payload,
            session_id=None,
            timeout_ms=timeout_ms,
        )
        session_id = _require_non_empty_string(result.get("session_id"), "session_id")
        self._remember_session(session_id)

        response: dict[str, Any] = {"status": "success", "session_id": session_id}
        if isinstance(result.get("url"), str) and result["url"]:
            response["url"] = result["url"]
        if isinstance(result.get("status_code"), int):
            response["status_code"] = result["status_code"]
        return response

    def close_session(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        self._execute_command(
            action="browser_close_session",
            payload={},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._forget_session(session_id)
        return {"status": "success", "session_id": session_id}

    def navigate(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        url = params.get("url")
        _validate_url(url)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_navigate",
            payload={"url": url},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def click(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = _require_selector(params.get("selector"))
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_click_element",
            payload={"selector": selector},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def type_text(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = _require_selector(params.get("selector"))
        text = _require_string(params.get("text"), "text")
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_type_text",
            payload={"selector": selector, "text": text},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def read_text(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector_raw = params.get("selector")
        selector = None if selector_raw in (None, "") else _require_selector(selector_raw)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        payload: dict[str, Any] = {}
        if selector is not None:
            payload["selector"] = selector
        result = self._execute_command(
            action="browser_read_text",
            payload=payload,
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def wait_for(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = _require_selector(params.get("selector"))
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_wait_for_selector",
            payload={"selector": selector},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def screenshot(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        full_page = params.get("full_page", False)
        if not isinstance(full_page, bool):
            raise BrowserToolError("invalid_input", "Field 'full_page' must be a boolean when provided.")

        raw_path = params.get("path")
        if raw_path in (None, ""):
            destination = self._default_screenshot_path(session_id)
        else:
            destination = _resolve_workspace_path(self.workspace_root, raw_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        result = self._execute_command(
            action="browser_take_screenshot",
            payload={"path": str(destination), "full_page": full_page},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        result["path"] = str(destination)
        return result

    def list_tabs(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_list_tabs",
            payload={},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def switch_tab(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        tab_index = params.get("tab_index")
        if not isinstance(tab_index, int):
            raise BrowserToolError("invalid_input", "Field 'tab_index' must be an integer.")
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_switch_tab",
            payload={"tab_index": tab_index},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def list_interactive_elements(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        filters_payload = params.get("filters", {})
        if filters_payload is None:
            filters_payload = {}
        if not isinstance(filters_payload, dict):
            raise BrowserToolError("invalid_input", "Field 'filters' must be an object when provided.")

        payload = {
            "filters": {
                "visible_only": _read_bool(
                    filters_payload.get("visible_only", params.get("visible_only", True)),
                    "visible_only",
                ),
                "in_viewport_only": _read_bool(
                    filters_payload.get("in_viewport_only", params.get("in_viewport_only", False)),
                    "in_viewport_only",
                ),
                "text_contains": _read_optional_string(
                    filters_payload.get("text_contains", params.get("text_contains")),
                    "text_contains",
                ),
            },
            "limit": _read_positive_int(params.get("limit"), "limit", 300),
        }
        result = self._execute_command(
            action="browser_list_interactive_elements",
            payload=payload,
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def click_element_by_id(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        element_id = _require_non_empty_string(params.get("element_id"), "element_id")
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_click_element_by_id",
            payload={"element_id": element_id},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def type_into_element(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        element_id = _require_non_empty_string(params.get("element_id"), "element_id")
        text = _require_string(params.get("text"), "text")
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        result = self._execute_command(
            action="browser_type_into_element",
            payload={"element_id": element_id, "text": text},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def highlight_element(self, params: dict[str, Any], tool_contract: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        element_id = _require_non_empty_string(params.get("element_id"), "element_id")
        timeout_ms = _resolve_timeout_ms(params, tool_contract)
        duration_ms = _read_positive_int(params.get("duration_ms"), "duration_ms", 1200)
        result = self._execute_command(
            action="browser_highlight_element",
            payload={"element_id": element_id, "duration_ms": duration_ms},
            session_id=session_id,
            timeout_ms=timeout_ms,
        )
        self._remember_session(session_id)
        result["session_id"] = session_id
        return result

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_session_id = self._active_session_id
            known_sessions = list(self._sessions.keys())
            auto_start = self._auto_start

        transport = self._ipc_client.get_status()
        health: dict[str, Any] | None = None
        health_error: dict[str, Any] | None = None
        if transport.get("alive"):
            try:
                health = self._ipc_client.health_check(timeout_ms=1200)
            except BrowserIPCError as exc:
                health_error = {
                    "error_code": exc.error_code,
                    "error_message": exc.error_message,
                    "details": exc.details,
                }

        return {
            "active_session_id": active_session_id,
            "known_sessions": known_sessions,
            "auto_start": auto_start,
            "artifacts_path": str(self._artifacts_root),
            "transport": transport,
            "health": health,
            "health_error": health_error,
        }

    def _execute_command(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        session_id: str | None,
        timeout_ms: int,
    ) -> dict[str, Any]:
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        transport_timeout_ms = _resolve_transport_timeout_ms(timeout_ms)
        try:
            result = self._ipc_client.execute(
                action=action,
                payload=payload,
                session_id=session_id,
                timeout_ms=timeout_ms,
                transport_timeout_ms=transport_timeout_ms,
                trace_id=trace_id,
            )
        except BrowserIPCError as exc:
            details = dict(exc.details) if isinstance(exc.details, dict) else {}
            if "trace_id" not in details:
                details["trace_id"] = trace_id
            details.setdefault("action_timeout_ms", timeout_ms)
            details.setdefault("transport_timeout_ms", transport_timeout_ms)
            raise BrowserToolError(exc.error_code, exc.error_message, details) from exc

        if not isinstance(result, dict):
            raise BrowserToolError(
                "browser_worker_protocol_error",
                f"Worker result for action '{action}' must be an object.",
                {"trace_id": trace_id},
            )
        return result

    def _remember_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions.pop(session_id)
            self._sessions[session_id] = None
            self._active_session_id = session_id

    def _forget_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            if self._active_session_id == session_id:
                self._active_session_id = self._fallback_active_session_id_locked()

    def _resolve_session_id(self, params: dict[str, Any]) -> str:
        raw_session_id = params.get("session_id")
        if raw_session_id not in (None, ""):
            session_id = _require_non_empty_string(raw_session_id, "session_id")
            self._remember_session(session_id)
            return session_id

        with self._lock:
            active_session_id = self._active_session_id
        if active_session_id is None:
            raise BrowserToolError(
                "session_not_available",
                "No browser session available. Provide 'session_id' or open a session first.",
            )
        return active_session_id

    def _default_screenshot_path(self, session_id: str) -> Path:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return (
            self._artifacts_root
            / "screenshots"
            / session_id
            / f"screenshot_{now}.png"
        ).resolve()

    def _fallback_active_session_id_locked(self) -> str | None:
        if not self._sessions:
            return None
        return next(reversed(self._sessions))


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserToolError("invalid_input", f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _require_selector(value: Any) -> str:
    selector = _require_non_empty_string(value, "selector")
    lowered = selector.lower()
    if lowered in {"click", "type", "wait", "wait_for_selector", "navigate", "open", "close"}:
        raise BrowserToolError(
            "invalid_input",
            (
                f"Field 'selector' has invalid value '{selector}'. "
                "Provide a real CSS selector like '#id', '.class', 'button', or '[aria-label=\"...\"]'."
            ),
        )
    return selector


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise BrowserToolError("invalid_input", f"Field '{field_name}' must be a string.")
    return value


def _validate_url(url: Any) -> None:
    if not isinstance(url, str) or not url.strip():
        raise BrowserToolError("invalid_input", "Field 'url' must be a non-empty string.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserToolError("invalid_url", f"URL '{url}' must start with http:// or https://.")


def _resolve_timeout_ms(params: dict[str, Any], tool_contract: dict[str, Any]) -> int:
    configured = int(tool_contract.get("constraints", {}).get("timeout_ms", 15000))
    timeout_ms = params.get("timeout_ms", configured)
    if timeout_ms is None:
        return configured
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise BrowserToolError("invalid_input", "Field 'timeout_ms' must be a positive integer when provided.")
    return timeout_ms


def _resolve_transport_timeout_ms(action_timeout_ms: int) -> int:
    buffer_ms = max(1000, min(5000, action_timeout_ms // 3))
    return action_timeout_ms + buffer_ms


def _read_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BrowserToolError("invalid_input", f"Field '{field_name}' must be boolean.")
    return value


def _read_optional_string(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise BrowserToolError("invalid_input", f"Field '{field_name}' must be a string when provided.")
    return value


def _read_positive_int(value: Any, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        raise BrowserToolError("invalid_input", f"Field '{field_name}' must be a positive integer.")
    return value


def _resolve_workspace_path(workspace_root: Path, path_value: Any) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise BrowserToolError("invalid_input", "Field 'path' must be a non-empty string when provided.")

    root = workspace_root.resolve()
    raw = Path(path_value.strip())
    candidate = raw if raw.is_absolute() else (root / raw)
    resolved = candidate.resolve()

    try:
        common = os.path.commonpath([str(root), str(resolved)])
    except ValueError as exc:
        raise BrowserToolError("workspace_violation", f"Path '{path_value}' is outside workspace.") from exc
    if Path(common) != root:
        raise BrowserToolError("workspace_violation", f"Path '{path_value}' is outside workspace.")
    return resolved


def _resolve_artifacts_root(workspace_root: Path, value: str | Path | None) -> Path:
    root = workspace_root.resolve()
    raw = Path(value) if value is not None else (root / "artifacts")
    candidate = raw if raw.is_absolute() else (root / raw)
    resolved = candidate.resolve()
    try:
        common = os.path.commonpath([str(root), str(resolved)])
    except ValueError as exc:
        raise BrowserToolError("workspace_violation", "Artifacts path must be inside workspace.") from exc
    if Path(common) != root:
        raise BrowserToolError("workspace_violation", "Artifacts path must be inside workspace.")
    return resolved
