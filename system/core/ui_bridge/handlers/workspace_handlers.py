"""Workspace route handlers: CRUD, browse, set-default."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, error_code, msg, **kw):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, error_code, msg, **kw)


def list_workspaces(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {
        "workspaces": service.workspace_registry.list(),
        "default_id": (service.workspace_registry.get_default() or {}).get("id"),
    })


def add_workspace(service: Any, payload: Any, **kw: Any):
    p = payload or {}
    ws_path = p.get("path", "")
    if not ws_path or not isinstance(ws_path, str):
        _err(HTTPStatus.BAD_REQUEST, "workspace_error", "A non-empty 'path' is required.")
    resolved = Path(ws_path).resolve()
    if not resolved.exists():
        _err(HTTPStatus.BAD_REQUEST, "workspace_error", f"Path '{ws_path}' does not exist.")
    if not resolved.is_dir():
        _err(HTTPStatus.BAD_REQUEST, "workspace_error", f"Path '{ws_path}' is not a directory.")
    try:
        ws = service.workspace_registry.add(p.get("name", ""), ws_path, access=p.get("access", "write"), capabilities=p.get("capabilities", "*"), color=p.get("color", "#00ff88"))
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workspace_changed", {"action": "added", "workspace_id": ws.get("id", "")})
        except Exception:
            pass
        return _resp(HTTPStatus.OK, {"status": "success", "workspace": ws})
    except (ValueError, FileNotFoundError) as exc:
        _err(HTTPStatus.BAD_REQUEST, "workspace_error", str(exc))


def get_workspace(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    ws = service.workspace_registry.get(ws_id)
    if ws is None:
        _err(HTTPStatus.NOT_FOUND, "workspace_not_found", f"Workspace '{ws_id}' not found.")
    return _resp(HTTPStatus.OK, {"workspace": ws})


def update_workspace(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    try:
        ws = service.workspace_registry.update(ws_id, **(payload or {}))
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workspace_changed", {"action": "updated", "workspace_id": ws_id})
        except Exception:
            pass
        return _resp(HTTPStatus.OK, {"status": "success", "workspace": ws})
    except KeyError as exc:
        _err(HTTPStatus.NOT_FOUND, "workspace_not_found", str(exc))


def delete_workspace(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    try:
        service.workspace_registry.remove(ws_id)
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workspace_changed", {"action": "removed", "workspace_id": ws_id})
        except Exception:
            pass
        return _resp(HTTPStatus.OK, {"status": "success", "removed": ws_id})
    except ValueError as exc:
        _err(HTTPStatus.BAD_REQUEST, "workspace_error", str(exc))


def set_default(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    if not service.workspace_registry.set_default(ws_id):
        _err(HTTPStatus.NOT_FOUND, "workspace_not_found", f"Workspace '{ws_id}' not found.")
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("workspace_changed", {"action": "default_changed", "workspace_id": ws_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "default_id": ws_id})


def update_status(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    status = (payload or {}).get("status")
    if not isinstance(status, dict) or "name" not in status:
        _err(HTTPStatus.BAD_REQUEST, "invalid_status", "Status must be {name, color, icon}.")
    try:
        ws = service.workspace_registry.update(ws_id, status=status)
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workspace_changed", {"action": "status_changed", "workspace_id": ws_id})
        except Exception:
            pass
        return _resp(HTTPStatus.OK, {"status": "success", "workspace": ws})
    except KeyError as exc:
        _err(HTTPStatus.NOT_FOUND, "workspace_not_found", str(exc))


def browse(service: Any, payload: Any, ws_id: str = "", _raw_path: str = "", **kw: Any):
    qs = parse_qs(urlparse(_raw_path).query) if _raw_path else {}
    rel_path = (qs.get("path") or ["."])[0]
    try:
        result = service.file_browser.list_directory(ws_id, rel_path)
        return _resp(HTTPStatus.OK, result)
    except (KeyError, FileNotFoundError, PermissionError) as exc:
        _err(HTTPStatus.BAD_REQUEST, "browse_error", str(exc))
