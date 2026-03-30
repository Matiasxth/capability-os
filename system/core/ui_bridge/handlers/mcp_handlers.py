"""MCP route handlers: servers, tools, install/uninstall."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def list_servers(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"servers": service.mcp_client_manager.list_servers()})


def add_server(service: Any, payload: Any, **kw: Any):
    result = service._mcp_add_server(payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("mcp_changed", {"action": "server_added"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def remove_server(service: Any, payload: Any, server_id: str = "", **kw: Any):
    result = service._mcp_remove_server(server_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("mcp_changed", {"action": "server_removed", "server_id": server_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def discover_tools(service: Any, payload: Any, server_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._mcp_discover_tools(server_id))


def list_tools(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"tools": service.mcp_tool_bridge.list_bridged_tools()})


def install_tool(service: Any, payload: Any, tool_id: str = "", **kw: Any):
    result = service._mcp_install_tool(tool_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("mcp_changed", {"action": "tool_installed", "tool_id": tool_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def uninstall_tool(service: Any, payload: Any, tool_id: str = "", **kw: Any):
    result = service._mcp_uninstall_tool(tool_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("mcp_changed", {"action": "tool_uninstalled", "tool_id": tool_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)
