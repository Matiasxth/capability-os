from __future__ import annotations

import json
import shutil
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase3_capabilities"
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


class _FetchHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"phase3 fetch ok")

    def log_message(self, format, *args):  # noqa: A003
        return


class Phase3CapabilitiesE2ETests(unittest.TestCase):
    def test_write_file_capability_e2e(self) -> None:
        case_dir = _prepare_case_dir("write_file")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        engine, caps = _build_engine(workspace)

        contract = caps.get("write_file")
        self.assertIsNotNone(contract)
        result = engine.execute(contract, {"path": "notes/a.txt", "content": "hello"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_output"]["status"], "success")
        self.assertTrue((workspace / "notes" / "a.txt").exists())

    def test_read_file_capability_e2e(self) -> None:
        case_dir = _prepare_case_dir("read_file")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        target = workspace / "demo.txt"
        target.write_text("read me", encoding="utf-8-sig")

        engine, caps = _build_engine(workspace)
        contract = caps.get("read_file")
        self.assertIsNotNone(contract)

        result = engine.execute(contract, {"path": "demo.txt"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_output"]["content"], "read me")

    def test_list_directory_capability_e2e(self) -> None:
        case_dir = _prepare_case_dir("list_directory")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "a.txt").write_text("A", encoding="utf-8-sig")
        (workspace / "b").mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("list_directory")
        self.assertIsNotNone(contract)

        result = engine.execute(contract, {"path": "."})
        names = {item["name"] for item in result["final_output"]["items"]}
        self.assertIn("a.txt", names)
        self.assertIn("b", names)

    def test_execute_command_capability_e2e(self) -> None:
        case_dir = _prepare_case_dir("execute_command")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)
        contract = caps.get("execute_command")
        self.assertIsNotNone(contract)

        result = engine.execute(contract, {"command": 'py -c "print(456)"'})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_output"]["exit_code"], 0)
        self.assertIn("456", result["final_output"]["stdout"])

    def test_fetch_url_capability_e2e(self) -> None:
        case_dir = _prepare_case_dir("fetch_url")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        server = HTTPServer(("127.0.0.1", 0), _FetchHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            engine, caps = _build_engine(workspace)
            contract = caps.get("fetch_url")
            self.assertIsNotNone(contract)

            url = f"http://127.0.0.1:{server.server_port}/"
            result = engine.execute(contract, {"url": url})
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_output"]["status_code"], 200)
        self.assertIn("phase3 fetch ok", result["final_output"]["body"])

    def test_observation_logs_success_and_error(self) -> None:
        case_dir = _prepare_case_dir("observation")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        engine, caps = _build_engine(workspace)

        success_contract = caps.get("write_file")
        self.assertIsNotNone(success_contract)
        success = engine.execute(success_contract, {"path": "ok.txt", "content": "ok"})
        success_events = [entry["event"] for entry in success["runtime"]["logs"]]
        self.assertEqual(success_events[0], "execution_started")
        self.assertIn("step_succeeded", success_events)
        self.assertEqual(success_events[-1], "execution_finished")

        error_contract = caps.get("execute_command")
        self.assertIsNotNone(error_contract)
        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(error_contract, {"command": "cmd /c echo not_allowed"})

        runtime = ctx.exception.runtime_model
        error_events = [entry["event"] for entry in runtime["logs"]]
        self.assertIn("step_failed", error_events)
        self.assertEqual(error_events[-1], "execution_finished")
        self.assertEqual(runtime["status"], "error")
        self.assertIsNotNone(runtime["error_code"])
        self.assertIsNotNone(runtime["error_message"])


if __name__ == "__main__":
    unittest.main()

