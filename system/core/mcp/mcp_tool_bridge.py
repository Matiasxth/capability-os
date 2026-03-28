"""Bridges MCP tools into the Capability OS Tool Registry and Runtime.

For each tool discovered via an MCPClient:
  1. Generates a tool contract (category ``"mcp"``, id ``mcp_<server>_<tool>``).
  2. Registers the contract in the ToolRegistry.
  3. Registers a handler in the ToolRuntime that delegates to ``MCPClient.call_tool``.

Naming canon (spec section 27.2): ``category_verb_object`` → ``mcp_<server>_<tool>``.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from system.core.mcp.mcp_client import MCPClient, MCPClientError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime


class MCPToolBridgeError(RuntimeError):
    """Raised when MCP tool bridging fails."""


# ---------------------------------------------------------------------------
# ID sanitisation
# ---------------------------------------------------------------------------

_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _sanitize_token(raw: str) -> str:
    """Lowercase, replace non-alnum runs with ``_``, strip edges."""
    return _SANITIZE_RE.sub("_", raw.lower()).strip("_") or "unknown"


def mcp_tool_id(server_id: str, tool_name: str) -> str:
    """Build a spec-compliant tool id: ``mcp_<server>_<tool>``."""
    return f"mcp_{_sanitize_token(server_id)}_{_sanitize_token(tool_name)}"


# ---------------------------------------------------------------------------
# Contract generation
# ---------------------------------------------------------------------------

def build_tool_contract(
    server_id: str,
    mcp_tool: dict[str, Any],
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Convert an MCP tool descriptor into a Capability OS tool contract.

    Args:
        server_id: MCP server identifier.
        mcp_tool: Tool descriptor from ``tools/list`` (name, description, inputSchema).
        timeout_ms: Default timeout for the tool.
    """
    tool_name = mcp_tool.get("name", "unknown")
    tool_id = mcp_tool_id(server_id, tool_name)
    description = mcp_tool.get("description") or f"MCP tool {tool_name} from {server_id}"
    input_schema = mcp_tool.get("inputSchema") or {}

    inputs = _convert_input_schema(input_schema)
    outputs: dict[str, Any] = {
        "content": {"type": "array", "description": "MCP response content blocks."},
    }

    return {
        "id": tool_id,
        "name": f"{server_id}: {tool_name}",
        "category": "mcp",
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
        "constraints": {
            "timeout_ms": timeout_ms,
            "allowlist": [],
            "workspace_only": False,
        },
        "safety": {
            "level": "medium",
            "requires_confirmation": False,
        },
        "lifecycle": {
            "version": "1.0.0",
            "status": "experimental",
        },
    }


def _convert_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a JSON-Schema ``properties`` block into Capability OS input fields."""
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    inputs: dict[str, Any] = {}
    for field_name, field_def in properties.items():
        if not isinstance(field_def, dict):
            continue
        field_type = field_def.get("type", "string")
        if isinstance(field_type, list):
            field_type = field_type[0] if field_type else "string"
        entry: dict[str, Any] = {
            "type": str(field_type),
            "required": field_name in required_fields,
        }
        desc = field_def.get("description")
        if isinstance(desc, str) and desc:
            entry["description"] = desc
        inputs[field_name] = entry
    return inputs


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class MCPToolBridge:
    """Registers MCP tools into the Capability OS tool system."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_runtime: ToolRuntime,
        default_timeout_ms: int = 30000,
    ):
        self._tool_registry = tool_registry
        self._tool_runtime = tool_runtime
        self._default_timeout_ms = default_timeout_ms
        self._registered_ids: dict[str, str] = {}  # tool_id → server_id

    def bridge_server(self, client: MCPClient) -> list[dict[str, Any]]:
        """Discover tools from *client* and register them.

        Returns the list of tool contracts that were registered.
        """
        try:
            mcp_tools = client.discover_tools()
        except MCPClientError as exc:
            raise MCPToolBridgeError(f"Discovery failed for '{client.server_id}': {exc}") from exc

        registered: list[dict[str, Any]] = []
        for mcp_tool in mcp_tools:
            tool_name = mcp_tool.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                continue

            contract = build_tool_contract(
                client.server_id, mcp_tool, timeout_ms=self._default_timeout_ms,
            )
            tool_id = contract["id"]

            # Skip if already registered
            if self._tool_registry.get(tool_id) is not None:
                registered.append(contract)
                continue

            try:
                self._tool_registry.register(contract, source=f"mcp:{client.server_id}")
            except Exception:
                continue  # skip tools that fail validation

            # Register a handler that delegates to MCPClient.call_tool
            self._register_handler(tool_id, client, tool_name)
            self._registered_ids[tool_id] = client.server_id
            registered.append(contract)

        return registered

    def unbridge_server(self, server_id: str) -> list[str]:
        """Remove all tools from a server. Returns list of removed tool_ids."""
        removed: list[str] = []
        for tool_id, sid in list(self._registered_ids.items()):
            if sid == server_id:
                del self._registered_ids[tool_id]
                removed.append(tool_id)
        return removed

    def list_bridged_tools(self) -> list[dict[str, Any]]:
        """Return metadata about currently bridged MCP tools."""
        result: list[dict[str, Any]] = []
        for tool_id, server_id in sorted(self._registered_ids.items()):
            contract = self._tool_registry.get(tool_id)
            result.append({
                "tool_id": tool_id,
                "server_id": server_id,
                "name": contract.get("name") if contract else tool_id,
                "status": contract.get("lifecycle", {}).get("status") if contract else "unknown",
            })
        return result

    def _register_handler(self, tool_id: str, client: MCPClient, mcp_tool_name: str) -> None:
        """Register a ToolRuntime handler that calls the MCP server."""
        def _handler(params: dict[str, Any]) -> dict[str, Any]:
            try:
                result = client.call_tool(mcp_tool_name, params)
            except MCPClientError as exc:
                raise RuntimeError(
                    f"MCP tool '{mcp_tool_name}' on '{client.server_id}' failed: {exc}"
                ) from exc
            # Flatten MCP content to a dict the engine can use
            content = result.get("content", [])
            if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
                text = content[0].get("text")
                if isinstance(text, str):
                    return {"content": content, "text": text}
            return {"content": content}

        self._tool_runtime.register_handler(tool_id, _handler)
