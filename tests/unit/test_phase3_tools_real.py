from __future__ import annotations

import json
import shutil
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolExecutionError, ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase3_tools"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _prepare_case_dir(case_name: str) -> Path:
    case_dir = TMP_ROOT / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def _build_runtime(workspace_root: Path, timeout_ms: int | None = None) -> ToolRuntime:
    tool_registry = ToolRegistry()
    contracts_dir = ROOT / "system" / "tools" / "contracts" / "v1"
    for contract_path in sorted(contracts_dir.glob("*.json")):
        contract = _load_json(contract_path)
        if timeout_ms is not None and contract["id"] == "execution_run_command":
            contract["constraints"]["timeout_ms"] = timeout_ms
        tool_registry.register(contract, source=str(contract_path))

    runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
    register_phase3_real_tools(runtime, workspace_root)
    return runtime


class _SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Test", "phase3")
        self.end_headers()
        self.wfile.write(b"hello from local server")

    def log_message(self, format, *args):  # noqa: A003
        return


class Phase3RealToolsTests(unittest.TestCase):
    def test_filesystem_write_file_success(self) -> None:
        case_dir = _prepare_case_dir("write_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        result = runtime.execute(
            "filesystem_write_file",
            {"path": "nested/demo.txt", "content": "hello"},
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue((workspace / "nested" / "demo.txt").exists())

    def test_filesystem_read_file_success(self) -> None:
        case_dir = _prepare_case_dir("read_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        target = workspace / "demo.txt"
        target.write_text("hello read", encoding="utf-8-sig")

        runtime = _build_runtime(workspace)
        result = runtime.execute("filesystem_read_file", {"path": "demo.txt"})

        self.assertEqual(result["content"], "hello read")
        self.assertEqual(result["path"], str(target.resolve()))

    def test_filesystem_list_directory_success(self) -> None:
        case_dir = _prepare_case_dir("list_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "a.txt").write_text("A", encoding="utf-8-sig")
        (workspace / "sub").mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace)
        result = runtime.execute("filesystem_list_directory", {"path": "."})

        names = {item["name"] for item in result["items"]}
        self.assertIn("a.txt", names)
        self.assertIn("sub", names)

    def test_execution_run_command_success(self) -> None:
        case_dir = _prepare_case_dir("exec_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace)
        result = runtime.execute("execution_run_command", {"command": 'py -c "print(123)"'})

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("123", result["stdout"])

    def test_network_http_get_success(self) -> None:
        case_dir = _prepare_case_dir("http_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace)
        server = HTTPServer(("127.0.0.1", 0), _SimpleHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            result = runtime.execute("network_http_get", {"url": url})
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(result["status_code"], 200)
        self.assertIn("hello from local server", result["body"])
        self.assertEqual(result["headers"].get("X-Test"), "phase3")

    def test_rejects_path_outside_workspace_for_read(self) -> None:
        case_dir = _prepare_case_dir("read_outside")
        workspace = case_dir / "workspace"
        outside = case_dir / "outside.txt"
        workspace.mkdir(parents=True, exist_ok=True)
        outside.write_text("outside", encoding="utf-8-sig")

        runtime = _build_runtime(workspace)
        with self.assertRaises(ToolExecutionError):
            runtime.execute("filesystem_read_file", {"path": str(outside)})

    def test_rejects_path_outside_workspace_for_write(self) -> None:
        case_dir = _prepare_case_dir("write_outside")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        outside = case_dir.parent / "blocked.txt"

        runtime = _build_runtime(workspace)
        with self.assertRaises(ToolExecutionError):
            runtime.execute("filesystem_write_file", {"path": str(outside), "content": "x"})

    def test_rejects_path_outside_workspace_for_list(self) -> None:
        case_dir = _prepare_case_dir("list_outside")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace)
        with self.assertRaises(ToolExecutionError):
            runtime.execute("filesystem_list_directory", {"path": str(case_dir.parent)})

    def test_rejects_non_allowlisted_command(self) -> None:
        case_dir = _prepare_case_dir("reject_command")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace)
        with self.assertRaises(ToolExecutionError):
            runtime.execute("execution_run_command", {"command": "cmd /c echo hi"})

    def test_execution_command_timeout(self) -> None:
        case_dir = _prepare_case_dir("timeout_command")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _build_runtime(workspace, timeout_ms=200)
        with self.assertRaises(ToolExecutionError):
            runtime.execute("execution_run_command", {"command": 'py -c "import time; time.sleep(2)"'})


if __name__ == "__main__":
    unittest.main()

