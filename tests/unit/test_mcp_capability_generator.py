"""
Tests for Componente 3 — MCP Capability Generator.

Validates:
  1. build_capability_contract: correct structure, inputs forwarded, naming.
  2. Contract passes CapabilityRegistry schema validation.
  3. MCPCapabilityGenerator.generate_proposals: generates for all bridged tools.
  4. generate_for_tool: single tool proposal.
  5. Proposal persistence: save, get, list, delete.
  6. No registry mutation (spec section 14).
  7. Strategy params use explicit variable origins.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.mcp.mcp_capability_generator import (
    MCPCapabilityGenerator,
    build_capability_contract,
)
from system.core.mcp.mcp_client import MCPClient
from system.core.mcp.mcp_tool_bridge import MCPToolBridge, build_tool_contract
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "mcp_capgen"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _sample_tool_contract() -> dict[str, Any]:
    return build_tool_contract("testserver", {
        "name": "greet",
        "description": "Greet someone",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Who to greet"},
                "lang": {"type": "string"},
            },
            "required": ["name"],
        },
    })


def _mock_client(server_id: str, tools: list[dict[str, Any]]) -> MCPClient:
    client = MagicMock(spec=MCPClient)
    client.server_id = server_id
    client.discover_tools.return_value = tools
    client.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    return client


# ===========================================================================
# 1. build_capability_contract
# ===========================================================================

class TestBuildCapabilityContract(unittest.TestCase):

    def test_structure(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        self.assertEqual(cap["id"], "mcp_testserver_greet")
        self.assertEqual(cap["domain"], "integraciones")
        self.assertEqual(cap["type"], "integration")
        self.assertEqual(cap["lifecycle"]["status"], "experimental")

    def test_inputs_forwarded(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        self.assertIn("name", cap["inputs"])
        self.assertTrue(cap["inputs"]["name"]["required"])
        self.assertFalse(cap["inputs"]["lang"]["required"])

    def test_strategy_uses_explicit_variable_origins(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        step = cap["strategy"]["steps"][0]
        self.assertEqual(step["action"], "mcp_testserver_greet")
        self.assertEqual(step["params"]["name"], "{{inputs.name}}")
        self.assertEqual(step["params"]["lang"], "{{inputs.lang}}")

    def test_single_step_sequential(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        self.assertEqual(cap["strategy"]["mode"], "sequential")
        self.assertEqual(len(cap["strategy"]["steps"]), 1)
        self.assertEqual(cap["strategy"]["steps"][0]["step_id"], "call_mcp")

    def test_requirements_reference_tool(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        self.assertEqual(cap["requirements"]["tools"], ["mcp_testserver_greet"])

    def test_passes_capability_schema(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        reg = CapabilityRegistry()
        reg.register(cap, source="test")  # raises if invalid

    def test_no_inputs_produces_empty_params(self):
        tool = build_tool_contract("srv", {"name": "noop", "description": "No-op"})
        cap = build_capability_contract(tool)
        self.assertEqual(cap["strategy"]["steps"][0]["params"], {})

    def test_exposure_trigger_phrases(self):
        tool = _sample_tool_contract()
        cap = build_capability_contract(tool)
        self.assertEqual(cap["exposure"]["trigger_phrases"], ["mcp testserver greet"])


# ===========================================================================
# 2. MCPCapabilityGenerator.generate_proposals
# ===========================================================================

class TestGenerateProposals(unittest.TestCase):

    def _bridge_with_tools(self, ws_name: str) -> tuple[MCPToolBridge, Path]:
        ws = _workspace(ws_name)
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("testserver", [
            {"name": "alpha", "description": "Tool A", "inputSchema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}},
            {"name": "beta", "description": "Tool B"},
        ])
        bridge.bridge_server(client)
        return bridge, ws

    def test_generates_for_all_bridged(self):
        bridge, ws = self._bridge_with_tools("gen_all")
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        results = gen.generate_proposals()
        self.assertEqual(len(results), 2)
        ids = {r["capability_id"] for r in results}
        self.assertEqual(ids, {"mcp_testserver_alpha", "mcp_testserver_beta"})

    def test_proposals_saved_to_disk(self):
        bridge, ws = self._bridge_with_tools("gen_disk")
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        gen.generate_proposals()
        self.assertTrue((ws / "proposals" / "mcp_testserver_alpha.json").exists())
        self.assertTrue((ws / "proposals" / "mcp_testserver_beta.json").exists())

    def test_proposals_are_valid_contracts(self):
        bridge, ws = self._bridge_with_tools("gen_valid")
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        results = gen.generate_proposals()
        cap_reg = CapabilityRegistry()
        for r in results:
            cap_reg.register(r["contract"], source="test")


# ===========================================================================
# 3. generate_for_tool
# ===========================================================================

class TestGenerateForTool(unittest.TestCase):

    def test_single_tool(self):
        ws = _workspace("single")
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("srv", [{"name": "one", "description": "Only one"}])
        bridge.bridge_server(client)

        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        result = gen.generate_for_tool("mcp_srv_one")
        self.assertIsNotNone(result)
        self.assertEqual(result["capability_id"], "mcp_srv_one")

    def test_unknown_tool_returns_none(self):
        ws = _workspace("unknown")
        reg = ToolRegistry()
        bridge = MCPToolBridge(reg, ToolRuntime(reg))
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        self.assertIsNone(gen.generate_for_tool("mcp_ghost_tool"))


# ===========================================================================
# 4. Proposal CRUD
# ===========================================================================

class TestProposalCRUD(unittest.TestCase):

    def _setup(self, name: str):
        ws = _workspace(name)
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("srv", [{"name": "tool", "description": "d"}])
        bridge.bridge_server(client)
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        gen.generate_for_tool("mcp_srv_tool")
        return gen

    def test_get_proposal(self):
        gen = self._setup("crud_get")
        prop = gen.get_proposal("mcp_srv_tool")
        self.assertIsNotNone(prop)
        self.assertEqual(prop["id"], "mcp_srv_tool")

    def test_get_nonexistent(self):
        gen = self._setup("crud_none")
        self.assertIsNone(gen.get_proposal("ghost"))

    def test_list_proposals(self):
        gen = self._setup("crud_list")
        self.assertIn("mcp_srv_tool", gen.list_proposals())

    def test_delete_proposal(self):
        gen = self._setup("crud_del")
        self.assertTrue(gen.delete_proposal("mcp_srv_tool"))
        self.assertIsNone(gen.get_proposal("mcp_srv_tool"))

    def test_delete_nonexistent(self):
        gen = self._setup("crud_del_none")
        self.assertFalse(gen.delete_proposal("ghost"))


# ===========================================================================
# 5. Spec section 14 — no registry mutation
# ===========================================================================

class TestNoRegistryMutation(unittest.TestCase):

    def test_generate_does_not_install(self):
        ws = _workspace("no_install")
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        bridge = MCPToolBridge(reg, runtime)
        client = _mock_client("srv", [{"name": "x", "description": "d"}])
        bridge.bridge_server(client)

        cap_reg = CapabilityRegistry()
        initial_ids = set(cap_reg.ids())
        gen = MCPCapabilityGenerator(bridge, ws / "proposals")
        gen.generate_proposals()
        self.assertEqual(set(cap_reg.ids()), initial_ids)


if __name__ == "__main__":
    unittest.main()
