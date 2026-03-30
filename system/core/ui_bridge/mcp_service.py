"""MCP service — moved from api_server.py god-object.

These functions handle MCP server management and tool discovery.
Called by mcp_handlers.py.
"""
from __future__ import annotations

from typing import Any


def mcp_add_server(service: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return service._mcp_add_server(payload)

def mcp_remove_server(service: Any, server_id: str) -> dict[str, Any]:
    return service._mcp_remove_server(server_id)

def mcp_discover_tools(service: Any, server_id: str) -> dict[str, Any]:
    return service._mcp_discover_tools(server_id)

def mcp_install_tool(service: Any, tool_id: str) -> dict[str, Any]:
    return service._mcp_install_tool(tool_id)

def mcp_uninstall_tool(service: Any, tool_id: str) -> dict[str, Any]:
    return service._mcp_uninstall_tool(tool_id)
