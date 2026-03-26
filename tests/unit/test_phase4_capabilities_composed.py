from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase4_capabilities"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _prepare_case_dir(case_name: str) -> Path:
    case_dir = TMP_ROOT / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def _build_engine(workspace_root: Path) -> tuple[CapabilityEngine, CapabilityRegistry]:
    capability_registry = CapabilityRegistry()
    for contract_path in sorted((ROOT / "system" / "capabilities" / "contracts" / "v1").glob("*.json")):
        capability_registry.register(_load_json(contract_path), source=str(contract_path))

    tool_registry = ToolRegistry()
    for contract_path in sorted((ROOT / "system" / "tools" / "contracts" / "v1").glob("*.json")):
        tool_registry.register(_load_json(contract_path), source=str(contract_path))

    tool_runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
    register_phase3_real_tools(tool_runtime, workspace_root)
    return CapabilityEngine(capability_registry, tool_runtime), capability_registry


class Phase4ComposedCapabilitiesTests(unittest.TestCase):
    def test_create_project_contract_unit(self) -> None:
        contract = _load_json(ROOT / "system/capabilities/contracts/v1/create_project.json")
        registry = CapabilityRegistry()
        contract_id = registry.validate_contract(contract, source="phase4_create_project")

        self.assertEqual(contract_id, "create_project")
        self.assertEqual(contract["requirements"]["tools"], ["execution_run_command", "filesystem_list_directory"])

    def test_analyze_project_contract_unit(self) -> None:
        contract = _load_json(ROOT / "system/capabilities/contracts/v1/analyze_project.json")
        registry = CapabilityRegistry()
        contract_id = registry.validate_contract(contract, source="phase4_analyze_project")

        self.assertEqual(contract_id, "analyze_project")
        self.assertEqual(contract["requirements"]["tools"], ["filesystem_list_directory", "filesystem_read_file"])

    def test_run_build_contract_unit(self) -> None:
        contract = _load_json(ROOT / "system/capabilities/contracts/v1/run_build.json")
        registry = CapabilityRegistry()
        contract_id = registry.validate_contract(contract, source="phase4_run_build")

        self.assertEqual(contract_id, "run_build")
        self.assertEqual(contract["requirements"]["tools"], ["execution_run_command"])

    def test_run_tests_contract_unit(self) -> None:
        contract = _load_json(ROOT / "system/capabilities/contracts/v1/run_tests.json")
        registry = CapabilityRegistry()
        contract_id = registry.validate_contract(contract, source="phase4_run_tests")

        self.assertEqual(contract_id, "run_tests")
        self.assertEqual(contract["requirements"]["tools"], ["execution_run_command"])

    def test_create_project_e2e(self) -> None:
        case_dir = _prepare_case_dir("create_project")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("create_project")
        self.assertIsNotNone(contract)

        result = engine.execute(contract, {"project_name": "demo_project"})

        self.assertEqual(result["status"], "success")
        project_path = Path(result["final_output"]["project_path"])
        self.assertTrue(project_path.exists())
        self.assertTrue((project_path / "README.md").exists())
        self.assertEqual(result["final_output"]["status"], "success")

    def test_create_project_e2e_with_target_dir(self) -> None:
        case_dir = _prepare_case_dir("create_project_target_dir")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        target_dir = workspace / "nested" / "apps"
        target_dir.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("create_project")
        self.assertIsNotNone(contract)

        result = engine.execute(
            contract,
            {"project_name": "demo_target", "target_dir": str(target_dir)},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_output"]["project_path"], str(target_dir / "demo_target"))
        self.assertTrue((target_dir / "demo_target" / "README.md").exists())

    def test_analyze_project_e2e(self) -> None:
        case_dir = _prepare_case_dir("analyze_project")
        workspace = case_dir / "workspace"
        project = workspace / "sample_project"
        project.mkdir(parents=True, exist_ok=True)
        (project / "README.md").write_text("# Sample\nLine 2", encoding="utf-8-sig")
        (project / "main.py").write_text("print('ok')\n", encoding="utf-8-sig")

        engine, caps = _build_engine(workspace)
        contract = caps.get("analyze_project")
        self.assertIsNotNone(contract)

        result = engine.execute(contract, {"project_path": str(project)})

        report = result["final_output"]["analysis_report"]
        self.assertEqual(result["status"], "success")
        self.assertEqual(report["project_path"], str(project))
        self.assertGreaterEqual(report["items_total"], 2)
        self.assertGreaterEqual(report["file_count"], 1)
        self.assertIn("read_file_lines", report)

    def test_run_build_e2e_default_and_custom_command(self) -> None:
        case_dir = _prepare_case_dir("run_build")
        workspace = case_dir / "workspace"
        project = workspace / "build_project"
        project.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("run_build")
        self.assertIsNotNone(contract)

        default_result = engine.execute(contract, {"project_path": str(project)})
        self.assertEqual(default_result["status"], "success")
        self.assertEqual(default_result["final_output"]["exit_code"], 0)
        self.assertIn("build_ok", default_result["final_output"]["stdout"])

        custom_result = engine.execute(
            contract,
            {"project_path": str(project), "build_command": 'py -c "print(\'custom_build\')"'},
        )
        self.assertEqual(custom_result["status"], "success")
        self.assertIn("custom_build", custom_result["final_output"]["stdout"])

    def test_run_tests_e2e_default_and_custom_command(self) -> None:
        case_dir = _prepare_case_dir("run_tests")
        workspace = case_dir / "workspace"
        project = workspace / "tests_project"
        project.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("run_tests")
        self.assertIsNotNone(contract)

        default_result = engine.execute(contract, {"project_path": str(project)})
        self.assertEqual(default_result["status"], "success")
        self.assertEqual(default_result["final_output"]["exit_code"], 0)
        self.assertIn("tests_ok", default_result["final_output"]["stdout"])

        custom_result = engine.execute(
            contract,
            {"project_path": str(project), "test_command": 'py -c "print(\'custom_tests\')"'},
        )
        self.assertEqual(custom_result["status"], "success")
        self.assertIn("custom_tests", custom_result["final_output"]["stdout"])

    def test_project_path_outside_workspace_is_rejected(self) -> None:
        case_dir = _prepare_case_dir("outside_workspace")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        outside = case_dir.parent / "outside_project"
        outside.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        run_build = caps.get("run_build")
        self.assertIsNotNone(run_build)

        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(run_build, {"project_path": str(outside)})

        self.assertEqual(ctx.exception.runtime_model["status"], "error")
        self.assertEqual(ctx.exception.error_code, "tool_execution_error")

    def test_observation_logs_success_and_error(self) -> None:
        case_dir = _prepare_case_dir("observation")
        workspace = case_dir / "workspace"
        project = workspace / "obs_project"
        project.mkdir(parents=True, exist_ok=True)
        (project / "README.md").write_text("# Obs", encoding="utf-8-sig")

        engine, caps = _build_engine(workspace)

        analyze = caps.get("analyze_project")
        self.assertIsNotNone(analyze)
        success = engine.execute(analyze, {"project_path": str(project)})
        success_events = [entry["event"] for entry in success["runtime"]["logs"]]
        self.assertEqual(success_events[0], "execution_started")
        self.assertIn("step_succeeded", success_events)
        self.assertEqual(success_events[-1], "execution_finished")

        run_tests = caps.get("run_tests")
        self.assertIsNotNone(run_tests)
        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(run_tests, {"project_path": str(project), "test_command": "cmd /c echo blocked"})

        runtime = ctx.exception.runtime_model
        error_events = [entry["event"] for entry in runtime["logs"]]
        self.assertIn("step_failed", error_events)
        self.assertEqual(error_events[-1], "execution_finished")
        self.assertEqual(runtime["status"], "error")
        self.assertIsNotNone(runtime["error_code"])
        self.assertIsNotNone(runtime["error_message"])


if __name__ == "__main__":
    unittest.main()
