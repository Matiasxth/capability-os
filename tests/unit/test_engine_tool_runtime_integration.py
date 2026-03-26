from __future__ import annotations

import json
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class EngineToolRuntimeIntegrationTests(unittest.TestCase):
    def test_engine_fails_when_tool_has_no_stub_handler(self) -> None:
        capability_contract = _load_json(
            ROOT / "tests/unit/fixtures/phase2/capabilities/valid_sequential_capability.json"
        )
        tool_contracts = _load_json(ROOT / "tests/unit/fixtures/phase2/tools/valid_stub_tools.json")

        capability_registry = CapabilityRegistry()
        tool_registry = ToolRegistry()
        for tool in tool_contracts:
            tool_registry.register(tool, source="phase2_tool_fixture")

        tool_runtime = ToolRuntime(tool_registry)
        engine = CapabilityEngine(capability_registry, tool_runtime)

        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(capability_contract, {"project_name": "demo", "target_dir": "/workspace"})

        self.assertEqual(ctx.exception.error_code, "tool_execution_error")
        self.assertEqual(ctx.exception.runtime_model["status"], "error")


if __name__ == "__main__":
    unittest.main()
