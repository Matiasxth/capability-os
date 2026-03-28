"""
Tests for Componente 2 — MCP Tool Bridge.

Validates:
  1. Schema changes: "mcp" category accepted in tool + capability schemas.
  2. mcp_tool_id naming: sanitisation, spec-compliant format.
  3. build_tool_contract: full contract generation from MCP descriptor.
  4. Input schema conversion: properties, required, description.
  5. MCPToolBridge.bridge_server: registers in ToolRegistry + ToolRuntime.
  6. Handler delegates to MCPClient.call_tool correctly.
  7. unbridge_server removes tracked tools.
  8. list_bridged_tools returns metadata.
  9. Duplicate tool skipped (no DuplicateIdError).
  10. Invalid tool skipped gracefully.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.mcp.mcp_client import MCPClient, MCPClientError
from system.core.mcp.mcp_tool_bridge import (
    MCPToolBridge,
    MCPToolBridgeError,
    _convert_input_schema,
    _sanitize_token,
    build_tool_contract,
    mcp_tool_id,
)
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# 1. Schema acceptance — "mcp" category
# ===========================================================================

class TestSchemaAcceptsMCP(unittest.TestCase):

    def test_tool_contract_schema_accepts_mcp_category(self):
        registry = ToolRegistry()
        contract = {
            "id": "mcp_test_greet",
            "name": "Test greet",
            "category": "mcp",
            "description": "MCP test tool",
            "inputs": {"name": {"type": "string", "required": True}},
            "outputs": {"content": {"type": "array"}},
            "constraints": {"timeout_ms": 10000, "allowlist": [], "workspace_only": False},
            "safety": {"level": "medium", "requires_confirmation": False},
            "lifecycle": {"version": "1.0.0", "status": "experimental"},
        }
        registry.register(contract, source="test")
        self.assertIsNotNone(registry.get("mcp_test_greet"))

    def test_capability_contract_schema_accepts_mcp_tool(self):
        cap_reg = CapabilityRegistry()
        contract = {
            "id": "mcp_test_action",
            "name": "MCP test action",
            "domain": "integraciones",
            "type": "integration",
            "description": "Test MCP capability",
            "inputs": {"value": {"type": "string", "required": True}},
            "outputs": {"content": {"type": "array"}},
            "requirements": {"tools": ["mcp_test_greet"], "capabilities": [], "integrations": []},
            "strategy": {
                "mode": "sequential",
                "steps": [{"step_id": "call_mcp", "action": "mcp_test_greet", "params": {"name": "{{inputs.value}}"}}],
            },
            "exposure": {"visible_to_user": True, "trigger_phrases": ["mcp test"]},
            "lifecycle": {"version": "1.0.0", "status": "experimental"},
        }
        cap_reg.register(contract, source="test")
        self.assertIsNotNone(cap_reg.get("mcp_test_action"))


# ===========================================================================
# 2. ID sanitisation and naming
# ===========================================================================

class TestMCPToolId(unittest.TestCase):

    def test_simple_names(self):
        self.assertEqual(mcp_tool_id("myserver", "read_file"), "mcp_myserver_read_file")

    def test_sanitizes_special_chars(self):
        self.assertEqual(mcp_tool_id("My-Server!", "Do.Thing"), "mcp_my_server_do_thing")

    def test_sanitizes_spaces(self):
        self.assertEqual(mcp_tool_id("a b", "c d"), "mcp_a_b_c_d")

    def test_empty_fallback_to_unknown(self):
        self.assertEqual(mcp_tool_id("", ""), "mcp_unknown_unknown")

    def test_sanitize_token(self):
        self.assertEqual(_sanitize_token("Hello--World"), "hello_world")
        self.assertEqual(_sanitize_token("---"), "unknown")


# ===========================================================================
# 3. build_tool_contract
# ===========================================================================

class TestBuildToolContract(unittest.TestCase):

    def test_minimal_mcp_tool(self):
        mcp_tool = {"name": "greet", "description": "Say hello"}
        contract = build_tool_contract("alpha", mcp_tool)
        self.assertEqual(contract["id"], "mcp_alpha_greet")
        self.assertEqual(contract["category"], "mcp")
        self.assertEqual(contract["description"], "Say hello")
        self.assertEqual(contract["lifecycle"]["status"], "experimental")

    def test_with_input_schema(self):
        mcp_tool = {
            "name": "read",
            "description": "Read",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "encoding": {"type": "string"},
                },
                "required": ["path"],
            },
        }
        contract = build_tool_contract("srv", mcp_tool)
        self.assertTrue(contract["inputs"]["path"]["required"])
        self.assertFalse(contract["inputs"]["encoding"]["required"])
        self.assertEqual(contract["inputs"]["path"]["description"], "File path")

    def test_custom_timeout(self):
        contract = build_tool_contract("s", {"name": "t"}, timeout_ms=5000)
        self.assertEqual(contract["constraints"]["timeout_ms"], 5000)

    def test_missing_description_gets_default(self):
        contract = build_tool_contract("s", {"name": "t"})
        self.assertIn("MCP tool t from s", contract["description"])

    def test_passes_tool_schema_validation(self):
        """Generated contract must pass ToolRegistry validation."""
        mcp_tool = {
            "name": "action",
            "description": "Do something",
            "inputSchema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        }
        contract = build_tool_contract("testserver", mcp_tool)
        registry = ToolRegistry()
        registry.register(contract, source="test")


# ===========================================================================
# 4. Input schema conversion
# ===========================================================================

class TestInputSchemaConversion(unittest.TestCase):

    def test_empty_schema(self):
        self.assertEqual(_convert_input_schema({}), {})

    def test_array_type_field(self):
        schema = {"properties": {"val": {"type": ["string", "null"]}}, "required": []}
        result = _convert_input_schema(schema)
        self.assertEqual(result["val"]["type"], "string")

    def test_non_dict_field_skipped(self):
        schema = {"properties": {"bad": "not_a_dict"}, "required": []}
        result = _convert_input_schema(schema)
        self.assertEqual(result, {})


# ===========================================================================
# 5. MCPToolBridge.bridge_server
# ===========================================================================

def _mock_client(server_id: str, tools: list[dict[str, Any]]) -> MCPClient:
    client = MagicMock(spec=MCPClient)
    client.server_id = server_id
    client.discover_tools.return_value = tools
    client.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    return client


class TestMCPToolBridgeBridge(unittest.TestCase):

    def test_bridge_registers_tools(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("alpha", [
            {"name": "greet", "description": "Hello", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            {"name": "farewell", "description": "Bye"},
        ])
        registered = bridge.bridge_server(client)
        self.assertEqual(len(registered), 2)
        self.assertIsNotNone(reg.get("mcp_alpha_greet"))
        self.assertIsNotNone(reg.get("mcp_alpha_farewell"))

    def test_handler_calls_mcp_client(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("alpha", [{"name": "echo", "description": "Echo"}])
        bridge.bridge_server(client)

        result = runtime.execute("mcp_alpha_echo", {"text": "hello"})
        client.call_tool.assert_called_once_with("echo", {"text": "hello"})
        self.assertIn("content", result)

    def test_handler_flattens_single_text_content(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "t", "description": "d"}])
        client.call_tool.return_value = {"content": [{"type": "text", "text": "result_value"}]}
        bridge.bridge_server(client)

        result = runtime.execute("mcp_s_t", {})
        self.assertEqual(result["text"], "result_value")

    def test_duplicate_skipped(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "t", "description": "d"}])
        bridge.bridge_server(client)

        # Bridge again with same tools — should not raise
        registered = bridge.bridge_server(client)
        self.assertEqual(len(registered), 1)

    def test_discovery_failure_raises(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = MagicMock(spec=MCPClient)
        client.server_id = "bad"
        client.discover_tools.side_effect = MCPClientError("mcp_transport_error", "Connection refused")

        with self.assertRaises(MCPToolBridgeError):
            bridge.bridge_server(client)

    def test_tool_with_empty_name_skipped(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "", "description": "bad"}, {"name": "good", "description": "ok"}])
        registered = bridge.bridge_server(client)
        self.assertEqual(len(registered), 1)


# ===========================================================================
# 6. unbridge and list
# ===========================================================================

class TestMCPToolBridgeManagement(unittest.TestCase):

    def test_unbridge_removes_tracked(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "a", "description": "d"}, {"name": "b", "description": "d"}])
        bridge.bridge_server(client)
        removed = bridge.unbridge_server("s")
        self.assertEqual(set(removed), {"mcp_s_a", "mcp_s_b"})
        self.assertEqual(bridge.list_bridged_tools(), [])

    def test_unbridge_unknown_server(self):
        bridge = MCPToolBridge(ToolRegistry(), ToolRuntime(ToolRegistry()))
        self.assertEqual(bridge.unbridge_server("ghost"), [])

    def test_list_bridged_tools(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "x", "description": "d"}])
        bridge.bridge_server(client)
        tools = bridge.list_bridged_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["tool_id"], "mcp_s_x")
        self.assertEqual(tools[0]["server_id"], "s")

    def test_handler_error_propagates(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("s", [{"name": "fail", "description": "d"}])
        client.call_tool.side_effect = MCPClientError("mcp_server_error", "Boom")
        bridge.bridge_server(client)

        from system.tools.runtime import ToolExecutionError
        with self.assertRaises(ToolExecutionError):
            runtime.execute("mcp_s_fail", {})


if __name__ == "__main__":
    unittest.main()
