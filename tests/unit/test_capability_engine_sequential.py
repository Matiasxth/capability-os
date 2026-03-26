from __future__ import annotations

import json
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError, CapabilityInputError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class CapabilityEngineSequentialTests(unittest.TestCase):
    def _build_engine(self):
        capability_contract = _load_json(
            ROOT / "tests/unit/fixtures/phase2/capabilities/valid_sequential_capability.json"
        )
        tool_contracts = _load_json(ROOT / "tests/unit/fixtures/phase2/tools/valid_stub_tools.json")

        capability_registry = CapabilityRegistry()
        tool_registry = ToolRegistry()

        for tool in tool_contracts:
            tool_registry.register(tool, source="phase2_tool_fixture")

        tool_runtime = ToolRuntime(tool_registry)

        def command_stub(params):
            command = params.get("command", "")
            if command.startswith("create "):
                project_name = command.split(" ", 1)[1]
                return {
                    "project_path": f"/workspace/{project_name}",
                    "stdout": "created",
                    "exit_code": 0,
                }
            if command.startswith("install "):
                return {"status": "success", "stdout": "installed", "exit_code": 0}
            return {"status": "success", "stdout": "ok", "exit_code": 0}

        tool_runtime.register_stub("execution_run_command", command_stub)
        engine = CapabilityEngine(capability_registry, tool_runtime)
        return engine, capability_contract

    def test_executes_sequential_strategy(self) -> None:
        engine, contract = self._build_engine()

        result = engine.execute(contract, {"project_name": "demo", "target_dir": "/workspace"})

        self.assertEqual(result["status"], "success")
        self.assertIn("execution_id", result)
        self.assertEqual(result["runtime"]["status"], "ready")
        self.assertIn("create_project", result["step_outputs"])
        self.assertIn("install_dependencies", result["step_outputs"])
        self.assertEqual(result["step_outputs"]["create_project"]["project_path"], "/workspace/demo")
        self.assertEqual(result["final_output"]["status"], "success")

        events = [entry["event"] for entry in result["runtime"]["logs"]]
        self.assertEqual(events[0], "execution_started")
        self.assertEqual(events[-1], "execution_finished")

    def test_fails_when_required_input_is_missing(self) -> None:
        engine, contract = self._build_engine()
        with self.assertRaises(CapabilityInputError):
            engine.execute(contract, {"target_dir": "/workspace"})

    def test_fails_on_nonexistent_variable_reference(self) -> None:
        engine, contract = self._build_engine()
        contract["strategy"]["steps"][0]["params"]["command"] = "create {{state.project_name}}"

        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(contract, {"project_name": "demo", "target_dir": "/workspace"})

        self.assertEqual(ctx.exception.error_code, "variable_resolution_error")
        runtime = ctx.exception.runtime_model
        self.assertEqual(runtime["status"], "error")
        self.assertEqual(runtime["failed_step"], "create_project")


if __name__ == "__main__":
    unittest.main()
