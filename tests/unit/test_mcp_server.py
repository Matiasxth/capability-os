"""
Tests for Componente 4 — MCP Server.

Validates:
  1. capability_to_mcp_tool: conversion from contract to MCP descriptor.
  2. list_tools: only "ready" capabilities exposed.
  3. call_tool: executes via engine, returns MCP content.
  4. call_tool error: missing capability, engine failure.
  5. handle_request: initialize, ping, tools/list, tools/call, unknown method.
  6. run_stdio: end-to-end JSON-RPC over simulated stdio.
  7. No engine configured: call_tool returns error content.
"""
from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.core.mcp.mcp_server import MCPServer, capability_to_mcp_tool

ROOT = Path(__file__).resolve().parents[2]


def _ready_contract(cap_id: str, inputs: dict | None = None) -> dict[str, Any]:
    return {
        "id": cap_id,
        "name": cap_id.replace("_", " ").title(),
        "domain": "ejecucion",
        "type": "base",
        "description": f"Capability {cap_id}",
        "inputs": inputs or {"value": {"type": "string", "required": True, "description": "Input value"}},
        "outputs": {"status": {"type": "string"}},
        "requirements": {"tools": ["execution_run_command"], "capabilities": [], "integrations": []},
        "strategy": {
            "mode": "sequential",
            "steps": [{"step_id": "run", "action": "execution_run_command", "params": {"command": "echo {{inputs.value}}"}}],
        },
        "exposure": {"visible_to_user": True, "trigger_phrases": [cap_id]},
        "lifecycle": {"version": "1.0.0", "status": "ready"},
    }


def _experimental_contract(cap_id: str) -> dict[str, Any]:
    c = _ready_contract(cap_id)
    c["lifecycle"]["status"] = "experimental"
    return c


def _registry(*contracts: dict[str, Any]) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for c in contracts:
        reg.register(c, source="test")
    return reg


# ===========================================================================
# 1. capability_to_mcp_tool
# ===========================================================================

class TestCapabilityToMCPTool(unittest.TestCase):

    def test_basic_conversion(self):
        contract = _ready_contract("read_file", {"path": {"type": "string", "required": True, "description": "File path"}})
        tool = capability_to_mcp_tool(contract)
        self.assertEqual(tool["name"], "read_file")
        self.assertEqual(tool["description"], "Capability read_file")
        schema = tool["inputSchema"]
        self.assertEqual(schema["type"], "object")
        self.assertIn("path", schema["properties"])
        self.assertEqual(schema["properties"]["path"]["type"], "string")
        self.assertEqual(schema["required"], ["path"])

    def test_optional_field_not_in_required(self):
        contract = _ready_contract("test_cap", {
            "a": {"type": "string", "required": True},
            "b": {"type": "string", "required": False},
        })
        tool = capability_to_mcp_tool(contract)
        self.assertEqual(tool["inputSchema"]["required"], ["a"])

    def test_no_inputs(self):
        contract = _ready_contract("list_processes")
        contract["inputs"] = {}
        tool = capability_to_mcp_tool(contract)
        self.assertEqual(tool["inputSchema"]["properties"], {})
        self.assertNotIn("required", tool["inputSchema"])

    def test_description_passthrough(self):
        contract = _ready_contract("test_cap")
        contract["description"] = "Custom description"
        tool = capability_to_mcp_tool(contract)
        self.assertEqual(tool["description"], "Custom description")


# ===========================================================================
# 2. list_tools — only "ready" exposed
# ===========================================================================

class TestListTools(unittest.TestCase):

    def test_only_ready(self):
        reg = _registry(
            _ready_contract("cap_ready"),
            _experimental_contract("cap_exp"),
        )
        server = MCPServer(reg)
        tools = server.list_tools()
        names = {t["name"] for t in tools}
        self.assertIn("cap_ready", names)
        self.assertNotIn("cap_exp", names)

    def test_empty_registry(self):
        reg = CapabilityRegistry()
        server = MCPServer(reg)
        self.assertEqual(server.list_tools(), [])

    def test_multiple_ready(self):
        reg = _registry(_ready_contract("cap_a"), _ready_contract("cap_b"))
        server = MCPServer(reg)
        self.assertEqual(len(server.list_tools()), 2)


# ===========================================================================
# 3. call_tool
# ===========================================================================

class TestCallTool(unittest.TestCase):

    def test_success(self):
        reg = _registry(_ready_contract("my_cap"))
        engine = MagicMock(spec=CapabilityEngine)
        engine.execute.return_value = {
            "status": "success",
            "final_output": {"stdout": "hello", "exit_code": 0},
        }
        server = MCPServer(reg, engine)
        result = server.call_tool("my_cap", {"value": "world"})
        self.assertIn("content", result)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertIn("hello", result["content"][0]["text"])

    def test_missing_capability(self):
        reg = CapabilityRegistry()
        server = MCPServer(reg, MagicMock(spec=CapabilityEngine))
        result = server.call_tool("nonexistent", {})
        self.assertTrue(result.get("isError"))
        self.assertIn("not found", result["content"][0]["text"])

    def test_engine_error(self):
        reg = _registry(_ready_contract("fail_cap"))
        engine = MagicMock(spec=CapabilityEngine)
        engine.execute.side_effect = CapabilityExecutionError("boom", {}, "tool_execution_error")
        server = MCPServer(reg, engine)
        result = server.call_tool("fail_cap", {"value": "x"})
        self.assertTrue(result.get("isError"))
        self.assertIn("boom", result["content"][0]["text"])

    def test_no_engine(self):
        reg = _registry(_ready_contract("test_cap"))
        server = MCPServer(reg, capability_engine=None)
        result = server.call_tool("test_cap", {})
        self.assertTrue(result.get("isError"))
        self.assertIn("No engine", result["content"][0]["text"])


# ===========================================================================
# 4. handle_request — JSON-RPC routing
# ===========================================================================

class TestHandleRequest(unittest.TestCase):

    def _server(self):
        reg = _registry(_ready_contract("test_cap"))
        engine = MagicMock(spec=CapabilityEngine)
        engine.execute.return_value = {"status": "success", "final_output": {"result": "ok"}}
        return MCPServer(reg, engine)

    def test_initialize(self):
        resp = self._server().handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(resp["id"], 1)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertEqual(result["serverInfo"]["name"], "capability-os")

    def test_ping(self):
        resp = self._server().handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(resp["result"], {})

    def test_tools_list(self):
        resp = self._server().handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        self.assertTrue(len(tools) >= 1)
        self.assertEqual(tools[0]["name"], "test_cap")

    def test_tools_call(self):
        resp = self._server().handle_request({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "test_cap", "arguments": {"value": "hello"}},
        })
        self.assertIn("content", resp["result"])

    def test_unknown_method(self):
        resp = self._server().handle_request({"jsonrpc": "2.0", "id": 5, "method": "unknown/method"})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)


# ===========================================================================
# 5. run_stdio — end-to-end
# ===========================================================================

class TestRunStdio(unittest.TestCase):

    def test_stdio_round_trip(self):
        reg = _registry(_ready_contract("echo_cap"))
        engine = MagicMock(spec=CapabilityEngine)
        engine.execute.return_value = {"status": "success", "final_output": {"text": "echoed"}}
        server = MCPServer(reg, engine)

        init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        call_req = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo_cap", "arguments": {"value": "hi"}}})

        stdin = io.StringIO(f"{init_req}\n{list_req}\n{call_req}\n")
        stdout = io.StringIO()

        server.run_stdio(stdin=stdin, stdout=stdout)

        stdout.seek(0)
        lines = [json.loads(line) for line in stdout if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["id"], 1)  # initialize
        self.assertIn("tools", lines[1]["result"])  # tools/list
        self.assertIn("content", lines[2]["result"])  # tools/call

    def test_stdio_invalid_json(self):
        server = MCPServer(CapabilityRegistry())
        stdin = io.StringIO("this is not json\n")
        stdout = io.StringIO()
        server.run_stdio(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        resp = json.loads(stdout.getvalue())
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32700)

    def test_stdio_empty_lines_skipped(self):
        server = MCPServer(CapabilityRegistry())
        ping_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        stdin = io.StringIO(f"\n\n{ping_req}\n\n")
        stdout = io.StringIO()
        server.run_stdio(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        lines = [line for line in stdout if line.strip()]
        self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
