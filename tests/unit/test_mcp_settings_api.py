"""
Tests for Componente 5 — MCP Settings + API integration.

Validates:
  1. Settings: mcp section in defaults, validation.
  2. MCPClientManager: add/remove/list via manager directly.
  3. MCPToolBridge + MCPCapabilityGenerator integration: discover → bridge → generate.
  4. Endpoint contract: the shape of responses from the MCP handlers.
  5. Error handling: missing server, missing tool.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.core.mcp import (
    MCPCapabilityGenerator,
    MCPClient,
    MCPClientError,
    MCPClientManager,
    MCPToolBridge,
)
from system.core.settings.settings_service import SettingsService, SettingsValidationError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "mcp_settings"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _mock_client(server_id: str, tools: list[dict[str, Any]]) -> MCPClient:
    client = MagicMock(spec=MCPClient)
    client.server_id = server_id
    client.discover_tools.return_value = tools
    client.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    client.connect.return_value = {"protocolVersion": "2024-11-05"}
    client.status.return_value = {
        "server_id": server_id, "connected": True,
        "server_info": None, "tools_discovered": len(tools),
    }
    return client


# ===========================================================================
# 1. Settings — mcp section
# ===========================================================================

class TestMCPSettings(unittest.TestCase):

    def test_defaults_include_mcp(self):
        ws = _workspace("settings_defaults")
        svc = SettingsService(ws)
        settings = svc.load_settings()
        self.assertIn("mcp", settings)
        self.assertEqual(settings["mcp"]["servers"], [])
        self.assertFalse(settings["mcp"]["auto_discover_capabilities"])
        self.assertEqual(settings["mcp"]["server_timeout_ms"], 10000)

    def test_valid_mcp_settings(self):
        ws = _workspace("settings_valid")
        svc = SettingsService(ws)
        settings = svc.load_settings()
        settings["mcp"]["server_timeout_ms"] = 5000
        settings["mcp"]["auto_discover_capabilities"] = True
        validated = svc.validate_settings(settings)
        self.assertEqual(validated["mcp"]["server_timeout_ms"], 5000)
        self.assertTrue(validated["mcp"]["auto_discover_capabilities"])

    def test_invalid_mcp_timeout_raises(self):
        ws = _workspace("settings_bad_timeout")
        svc = SettingsService(ws)
        settings = svc.load_settings()
        settings["mcp"]["server_timeout_ms"] = -1
        with self.assertRaises(SettingsValidationError):
            svc.validate_settings(settings)

    def test_invalid_mcp_servers_type_raises(self):
        ws = _workspace("settings_bad_servers")
        svc = SettingsService(ws)
        settings = svc.load_settings()
        settings["mcp"]["servers"] = "not_a_list"
        with self.assertRaises(SettingsValidationError):
            svc.validate_settings(settings)

    def test_invalid_auto_discover_raises(self):
        ws = _workspace("settings_bad_disc")
        svc = SettingsService(ws)
        settings = svc.load_settings()
        settings["mcp"]["auto_discover_capabilities"] = "yes"
        with self.assertRaises(SettingsValidationError):
            svc.validate_settings(settings)


# ===========================================================================
# 2. MCPClientManager integration
# ===========================================================================

class TestMCPClientManagerIntegration(unittest.TestCase):

    def test_add_list_remove(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "test", "transport": "http", "url": "http://localhost:1"})
        self.assertEqual(len(mgr.list_servers()), 1)
        self.assertTrue(mgr.remove_server("test"))
        self.assertEqual(len(mgr.list_servers()), 0)

    def test_remove_nonexistent(self):
        mgr = MCPClientManager()
        self.assertFalse(mgr.remove_server("ghost"))


# ===========================================================================
# 3. Full MCP pipeline: discover → bridge → generate
# ===========================================================================

class TestMCPFullPipeline(unittest.TestCase):

    def test_discover_bridge_generate(self):
        ws = _workspace("pipeline")
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("testserver", [
            {"name": "greet", "description": "Say hello", "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }},
        ])

        # Bridge
        registered = bridge.bridge_server(client)
        self.assertEqual(len(registered), 1)
        self.assertIsNotNone(reg.get("mcp_testserver_greet"))

        # Generate capability proposal
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        proposals = gen.generate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["capability_id"], "mcp_testserver_greet")

        # Proposal saved
        loaded = gen.get_proposal("mcp_testserver_greet")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["domain"], "integraciones")

    def test_execute_bridged_tool(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)

        client = _mock_client("srv", [{"name": "echo", "description": "Echo"}])
        client.call_tool.return_value = {"content": [{"type": "text", "text": "echoed"}]}
        bridge.bridge_server(client)

        result = runtime.execute("mcp_srv_echo", {"text": "hello"})
        self.assertEqual(result["text"], "echoed")
        client.call_tool.assert_called_once_with("echo", {"text": "hello"})


# ===========================================================================
# 4. Handler response shapes
# ===========================================================================

class TestMCPHandlerShapes(unittest.TestCase):

    def test_add_server_response(self):
        mgr = MCPClientManager()
        client = mgr.add_server({"id": "s", "transport": "http", "url": "http://localhost:1"})
        status = client.status()
        self.assertIn("server_id", status)
        self.assertIn("connected", status)

    def test_list_servers_shape(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "s", "transport": "http", "url": "http://localhost:1"})
        servers = mgr.list_servers()
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["server_id"], "s")

    def test_list_tools_shape(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("srv", [{"name": "t", "description": "d"}])
        bridge.bridge_server(client)
        tools = bridge.list_bridged_tools()
        self.assertEqual(tools[0]["tool_id"], "mcp_srv_t")
        self.assertEqual(tools[0]["server_id"], "srv")

    def test_install_tool_shape(self):
        ws = _workspace("install_shape")
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("srv", [{"name": "x", "description": "d"}])
        bridge.bridge_server(client)

        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        result = gen.generate_for_tool("mcp_srv_x")
        self.assertIn("capability_id", result)
        self.assertIn("proposal_path", result)
        self.assertIn("contract", result)


# ===========================================================================
# 5. Error handling
# ===========================================================================

class TestMCPErrors(unittest.TestCase):

    def test_missing_server_id_raises(self):
        mgr = MCPClientManager()
        with self.assertRaises(MCPClientError):
            mgr.add_server({"transport": "http", "url": "http://localhost:1"})

    def test_install_unknown_tool(self):
        ws = _workspace("install_unknown")
        reg = ToolRegistry()
        bridge = MCPToolBridge(reg, ToolRuntime(reg))
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        self.assertIsNone(gen.generate_for_tool("mcp_ghost_tool"))

    def test_bridge_discovery_failure(self):
        from system.core.mcp.mcp_tool_bridge import MCPToolBridgeError
        reg = ToolRegistry()
        bridge = MCPToolBridge(reg, ToolRuntime(reg))
        client = MagicMock(spec=MCPClient)
        client.server_id = "bad"
        client.discover_tools.side_effect = MCPClientError("mcp_transport_error", "fail")
        with self.assertRaises(MCPToolBridgeError):
            bridge.bridge_server(client)


if __name__ == "__main__":
    unittest.main()
