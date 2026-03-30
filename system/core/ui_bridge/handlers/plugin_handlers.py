"""Plugin management handlers — list, reload, install plugins at runtime."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, error_code, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, error_code, msg)


def list_plugins(service: Any, payload: Any, **kw: Any):
    """Return all plugins and their status."""
    if not hasattr(service, "container"):
        return _resp(HTTPStatus.OK, {"plugins": {}})
    status = service.container.get_status()
    return _resp(HTTPStatus.OK, {"plugins": status})


def get_plugin(service: Any, payload: Any, plugin_id: str = "", **kw: Any):
    """Get details of a specific plugin."""
    if not hasattr(service, "container"):
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "no_container", "Container not available")
    plugin = service.container.get_plugin(plugin_id)
    if plugin is None:
        _err(HTTPStatus.NOT_FOUND, "plugin_not_found", f"Plugin '{plugin_id}' not found")
    state = service.container._states.get(plugin_id)
    return _resp(HTTPStatus.OK, {
        "plugin_id": plugin_id,
        "name": getattr(plugin, "plugin_name", "?"),
        "version": getattr(plugin, "version", "?"),
        "dependencies": getattr(plugin, "dependencies", []),
        "state": state.value if state else "unknown",
    })


def reload_plugin(service: Any, payload: Any, plugin_id: str = "", **kw: Any):
    """Hot-reload a plugin without restarting the server."""
    if not hasattr(service, "container"):
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "no_container", "Container not available")

    from system.container.hot_reload import reload_plugin as do_reload
    err = do_reload(service.container, plugin_id)
    if err:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error": err})

    # Refresh aliases on service
    plugin = service.container.get_plugin(plugin_id)
    _refresh_aliases(service, plugin_id, plugin)

    return _resp(HTTPStatus.OK, {"status": "success", "plugin_id": plugin_id})


def install_plugin(service: Any, payload: Any, **kw: Any):
    """Install a plugin from a directory path."""
    body = payload or {}
    path = body.get("path", "")
    if not path:
        _err(HTTPStatus.BAD_REQUEST, "missing_path", "Field 'path' is required")

    if not hasattr(service, "container"):
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "no_container", "Container not available")

    from system.container.hot_reload import install_plugin_from_path
    pid, err = install_plugin_from_path(service.container, path)
    if err:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error": err, "plugin_id": pid})

    return _resp(HTTPStatus.OK, {"status": "success", "plugin_id": pid})


def _refresh_aliases(service: Any, plugin_id: str, plugin: Any) -> None:
    """Update backward-compatible aliases on the service after reload."""
    if plugin is None:
        return
    # Map known plugin IDs to their service attribute names
    ATTR_MAP = {
        "capos.channels.telegram": [("connector", "telegram_connector"), ("executor", "telegram_executor"), ("polling_worker", "telegram_polling_worker")],
        "capos.channels.slack": [("connector", "slack_connector"), ("executor", "slack_executor"), ("polling_worker", "slack_polling_worker")],
        "capos.channels.discord": [("connector", "discord_connector"), ("executor", "discord_executor"), ("polling_worker", "discord_polling_worker")],
        "capos.channels.whatsapp": [("backend_manager", "whatsapp_manager"), ("reply_worker", "whatsapp_reply_worker")],
        "capos.core.supervisor": [("supervisor", "supervisor"), ("skill_creator", "skill_creator")],
        "capos.core.scheduler": [("task_queue", "task_queue"), ("scheduler", "scheduler")],
    }
    for plugin_attr, service_attr in ATTR_MAP.get(plugin_id, []):
        val = getattr(plugin, plugin_attr, None)
        if val is not None:
            setattr(service, service_attr, val)
