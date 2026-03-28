"""MCP Server — exposes Capability OS capabilities as MCP tools.

Reads all capabilities with ``lifecycle.status == "ready"`` from the
CapabilityRegistry, converts them to MCP tool descriptors, and serves
them over the MCP protocol (JSON-RPC 2.0 over stdio).

This makes Capability OS interoperable with any MCP-compatible agent.

Protocol methods handled:
  - ``initialize``   — handshake
  - ``tools/list``   — returns the converted tool list
  - ``tools/call``   — executes a capability via the CapabilityEngine
  - ``ping``         — health check
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError, CapabilityInputError


# ---------------------------------------------------------------------------
# Capability → MCP tool conversion
# ---------------------------------------------------------------------------

def capability_to_mcp_tool(contract: dict[str, Any]) -> dict[str, Any]:
    """Convert a capability contract into an MCP tool descriptor."""
    inputs = contract.get("inputs", {})
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field_name, field_def in inputs.items():
        if not isinstance(field_def, dict):
            continue
        prop: dict[str, Any] = {"type": field_def.get("type", "string")}
        desc = field_def.get("description")
        if isinstance(desc, str) and desc:
            prop["description"] = desc
        properties[field_name] = prop
        if field_def.get("required") is True:
            required.append(field_name)

    input_schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        input_schema["required"] = required

    return {
        "name": contract["id"],
        "description": contract.get("description", contract["id"]),
        "inputSchema": input_schema,
    }


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 response helpers
# ---------------------------------------------------------------------------

def _success_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error_response(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


# ---------------------------------------------------------------------------
# MCPServer
# ---------------------------------------------------------------------------

class MCPServer:
    """Serves Capability OS capabilities as MCP tools over JSON-RPC 2.0."""

    SERVER_INFO = {
        "name": "capability-os",
        "version": "1.0.0",
    }
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        capability_engine: CapabilityEngine | None = None,
    ):
        self._registry = capability_registry
        self._engine = capability_engine

    # ------------------------------------------------------------------
    # Public: list available tools
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors for all ready capabilities."""
        tools: list[dict[str, Any]] = []
        for contract in self._registry.list_all():
            status = contract.get("lifecycle", {}).get("status")
            if status != "ready":
                continue
            tools.append(capability_to_mcp_tool(contract))
        return tools

    # ------------------------------------------------------------------
    # Public: call a tool (execute capability)
    # ------------------------------------------------------------------

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute the capability identified by *tool_name* and return MCP content."""
        if self._engine is None:
            return _error_content(f"No engine configured — cannot execute '{tool_name}'.")

        contract = self._registry.get(tool_name)
        if contract is None:
            return _error_content(f"Tool '{tool_name}' not found.")

        try:
            result = self._engine.execute(contract, arguments or {})
        except (CapabilityExecutionError, CapabilityInputError) as exc:
            return _error_content(str(exc))

        final_output = result.get("final_output", {})
        if isinstance(final_output, dict):
            text = json.dumps(final_output, ensure_ascii=False, default=str)
        else:
            text = str(final_output)

        return {"content": [{"type": "text", "text": text}]}

    # ------------------------------------------------------------------
    # Public: handle a single JSON-RPC request
    # ------------------------------------------------------------------

    def handle_request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Route a JSON-RPC 2.0 request and return a response."""
        req_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params") or {}

        if method == "initialize":
            return _success_response(req_id, {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": self.SERVER_INFO,
            })

        if method == "ping":
            return _success_response(req_id, {})

        if method == "tools/list":
            return _success_response(req_id, {"tools": self.list_tools()})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self.call_tool(tool_name, arguments)
            return _success_response(req_id, result)

        return _error_response(req_id, -32601, f"Method '{method}' not found.")

    # ------------------------------------------------------------------
    # Public: stdio event loop
    # ------------------------------------------------------------------

    def run_stdio(self, stdin=None, stdout=None) -> None:
        """Read JSON-RPC lines from stdin, write responses to stdout."""
        _in = stdin or sys.stdin
        _out = stdout or sys.stdout

        for raw_line in _in:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = _error_response(None, -32700, "Parse error.")
                _out.write(json.dumps(response, ensure_ascii=True) + "\n")
                _out.flush()
                continue

            response = self.handle_request(message)
            _out.write(json.dumps(response, ensure_ascii=True) + "\n")
            _out.flush()


def _error_content(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {message}"}], "isError": True}
