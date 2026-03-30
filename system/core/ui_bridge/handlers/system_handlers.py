"""System-related route handlers: status, health, settings, LLM test, config export/import."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def get_status(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, service._status_snapshot())


def get_health(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, service.health_service.get_system_health())


def get_settings(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, {"settings": service.settings_service.get_settings(mask_secrets=True)})


def save_settings(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    result = service._save_settings(payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("settings_updated", {"keys": list((payload or {}).keys())})
    except Exception:
        pass
    return APIResponse(HTTPStatus.OK, result)


def test_llm(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, service._test_llm_connection())


def export_config(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    from datetime import datetime, timezone
    settings = service.settings_service.get_settings(mask_secrets=True)
    workspaces_data = {
        "workspaces": service.workspace_registry.list(),
        "default_workspace_id": (service.workspace_registry.get_default() or {}).get("id"),
    }
    export = {
        "settings": settings,
        "workspaces": workspaces_data,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
    }
    return APIResponse(HTTPStatus.OK, export)


def import_config(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    body = payload or {}
    imported_settings = body.get("settings")
    if isinstance(imported_settings, dict):
        service.settings_service.save_settings(imported_settings)
        service._refresh_llm_client_settings()
    imported_ws = body.get("workspaces", {})
    if isinstance(imported_ws, dict):
        for ws in imported_ws.get("workspaces", []):
            if isinstance(ws, dict) and ws.get("name") and ws.get("path"):
                try:
                    service.workspace_registry.add(
                        ws["name"], ws["path"],
                        access=ws.get("access", "write"),
                        color=ws.get("color", "#00ff88"),
                    )
                except (ValueError, FileNotFoundError):
                    pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("config_imported", {})
    except Exception:
        pass
    return APIResponse(HTTPStatus.OK, {"status": "success", "message": "Configuration imported."})
