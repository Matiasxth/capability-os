"""
Tests for Bloque 1 tools:
  Filesystem: edit_file, copy_file, move_file, delete_file
  Execution:  run_script, list_processes, terminate_process, read_process_output
  Network:    http_post
  System:     get_os_info, get_env_var, get_workspace_info
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from system.tools.implementations.phase3_tools import (
    execution_list_processes,
    execution_read_process_output,
    execution_run_script,
    execution_terminate_process,
    filesystem_copy_file,
    filesystem_delete_file,
    filesystem_edit_file,
    filesystem_move_file,
    network_http_post,
    system_get_env_var,
    system_get_os_info,
    system_get_workspace_info,
    ToolSecurityError,
)

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "bloque1_tools"
TMP.mkdir(parents=True, exist_ok=True)


def _workspace() -> Path:
    ws = TMP / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _contract(tool_id: str, category: str = "filesystem", timeout_ms: int = 30000,
              allowlist: list | None = None, workspace_only: bool = True,
              requires_confirmation: bool = False) -> dict:
    return {
        "id": tool_id,
        "category": category,
        "constraints": {
            "timeout_ms": timeout_ms,
            "allowlist": allowlist or [],
            "workspace_only": workspace_only,
        },
        "safety": {"level": "medium", "requires_confirmation": requires_confirmation},
    }


# ---------------------------------------------------------------------------
# Filesystem — edit_file
# ---------------------------------------------------------------------------

class TestFilesystemEditFile(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("filesystem_edit_file")

    def test_replace_old_string(self):
        f = self.ws / "edit_test.txt"
        f.write_text("hello world", encoding="utf-8-sig")
        result = filesystem_edit_file(
            {"path": str(f), "old_string": "world", "new_string": "there"},
            self.contract, self.ws,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(f.read_text(encoding="utf-8-sig"), "hello there")

    def test_full_replacement_when_no_old_string(self):
        f = self.ws / "edit_full.txt"
        f.write_text("old content", encoding="utf-8-sig")
        result = filesystem_edit_file(
            {"path": str(f), "new_string": "brand new"},
            self.contract, self.ws,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(f.read_text(encoding="utf-8-sig"), "brand new")

    def test_old_string_not_found_raises(self):
        f = self.ws / "edit_notfound.txt"
        f.write_text("some text", encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            filesystem_edit_file(
                {"path": str(f), "old_string": "NOT_THERE", "new_string": "x"},
                self.contract, self.ws,
            )

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            filesystem_edit_file(
                {"path": str(self.ws / "ghost.txt"), "new_string": "x"},
                self.contract, self.ws,
            )

    def test_outside_workspace_raises(self):
        with self.assertRaises(ToolSecurityError):
            filesystem_edit_file(
                {"path": "/etc/passwd", "new_string": "x"},
                self.contract, self.ws,
            )


# ---------------------------------------------------------------------------
# Filesystem — copy_file
# ---------------------------------------------------------------------------

class TestFilesystemCopyFile(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("filesystem_copy_file")

    def test_copy_creates_destination(self):
        src = self.ws / "copy_src.txt"
        dst = self.ws / "copy_dst.txt"
        src.write_text("content", encoding="utf-8-sig")
        result = filesystem_copy_file(
            {"source_path": str(src), "destination_path": str(dst)},
            self.contract, self.ws,
        )
        self.assertEqual(result["status"], "success")
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8-sig"), "content")

    def test_source_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            filesystem_copy_file(
                {"source_path": str(self.ws / "ghost.txt"), "destination_path": str(self.ws / "out.txt")},
                self.contract, self.ws,
            )

    def test_destination_outside_workspace_raises(self):
        src = self.ws / "copy_src2.txt"
        src.write_text("x", encoding="utf-8-sig")
        with self.assertRaises(ToolSecurityError):
            filesystem_copy_file(
                {"source_path": str(src), "destination_path": "/tmp/outside.txt"},
                self.contract, self.ws,
            )


# ---------------------------------------------------------------------------
# Filesystem — move_file
# ---------------------------------------------------------------------------

class TestFilesystemMoveFile(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("filesystem_move_file")

    def test_move_renames_file(self):
        src = self.ws / "move_src.txt"
        dst = self.ws / "move_dst.txt"
        src.write_text("moveme", encoding="utf-8-sig")
        result = filesystem_move_file(
            {"source_path": str(src), "destination_path": str(dst)},
            self.contract, self.ws,
        )
        self.assertEqual(result["status"], "success")
        self.assertFalse(src.exists())
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8-sig"), "moveme")

    def test_source_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            filesystem_move_file(
                {"source_path": str(self.ws / "ghost.txt"), "destination_path": str(self.ws / "out.txt")},
                self.contract, self.ws,
            )


# ---------------------------------------------------------------------------
# Filesystem — delete_file
# ---------------------------------------------------------------------------

class TestFilesystemDeleteFile(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("filesystem_delete_file", requires_confirmation=True)

    def test_delete_removes_file(self):
        f = self.ws / "delete_me.txt"
        f.write_text("bye", encoding="utf-8-sig")
        result = filesystem_delete_file({"path": str(f)}, self.contract, self.ws)
        self.assertEqual(result["status"], "success")
        self.assertFalse(f.exists())

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            filesystem_delete_file(
                {"path": str(self.ws / "ghost.txt")}, self.contract, self.ws,
            )

    def test_directory_raises(self):
        d = self.ws / "subdir"
        d.mkdir(exist_ok=True)
        with self.assertRaises(ValueError):
            filesystem_delete_file({"path": str(d)}, self.contract, self.ws)

    def test_outside_workspace_raises(self):
        with self.assertRaises(ToolSecurityError):
            filesystem_delete_file({"path": "/etc/passwd"}, self.contract, self.ws)


# ---------------------------------------------------------------------------
# Execution — run_script
# ---------------------------------------------------------------------------

class TestExecutionRunScript(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract(
            "execution_run_script",
            category="execution",
            timeout_ms=30000,
            allowlist=["python", "python3", "py", Path(sys.executable).name, "bash", "sh"],
        )

    def test_run_python_script(self):
        script = self.ws / "hello.py"
        script.write_text('print("hello_from_script")', encoding="utf-8-sig")
        result = execution_run_script(
            {"script_path": str(script)},
            self.contract, self.ws,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hello_from_script", result["stdout"])

    def test_script_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            execution_run_script(
                {"script_path": str(self.ws / "ghost.py")},
                self.contract, self.ws,
            )

    def test_script_with_args(self):
        script = self.ws / "args_test.py"
        script.write_text(
            "import sys; print(sys.argv[1])", encoding="utf-8-sig"
        )
        result = execution_run_script(
            {"script_path": str(script), "args": ["hello_arg"]},
            self.contract, self.ws,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hello_arg", result["stdout"])


# ---------------------------------------------------------------------------
# Execution — list_processes
# ---------------------------------------------------------------------------

class TestExecutionListProcesses(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("execution_list_processes", category="execution", workspace_only=False)

    def test_returns_list(self):
        result = execution_list_processes({}, self.contract, self.ws)
        self.assertIn("processes", result)
        self.assertIsInstance(result["processes"], list)
        self.assertGreaterEqual(result["count"], 0)

    def test_filter_reduces_results(self):
        result_all = execution_list_processes({}, self.contract, self.ws)
        result_filtered = execution_list_processes(
            {"filter": "ZZZNOMATCHZZ"},
            self.contract, self.ws,
        )
        self.assertLessEqual(result_filtered["count"], result_all["count"])


# ---------------------------------------------------------------------------
# Execution — read_process_output
# ---------------------------------------------------------------------------

class TestExecutionReadProcessOutput(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("execution_read_process_output", category="execution", workspace_only=False)

    def test_own_pid_is_running(self):
        result = execution_read_process_output(
            {"process_id": os.getpid()}, self.contract, self.ws,
        )
        self.assertTrue(result["running"])

    def test_invalid_pid_not_running(self):
        result = execution_read_process_output(
            {"process_id": 99999999}, self.contract, self.ws,
        )
        self.assertFalse(result["running"])

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            execution_read_process_output(
                {"process_id": "not_an_int"}, self.contract, self.ws,
            )


# ---------------------------------------------------------------------------
# Network — http_post
# ---------------------------------------------------------------------------

class _PostEchoHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body or b'{"echo":"empty"}')

    def log_message(self, *args):  # silence test output
        pass


class TestNetworkHttpPost(unittest.TestCase):
    server: HTTPServer
    port: int

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _PostEchoHandler)
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("network_http_post", category="network", workspace_only=False)

    def test_post_json_body(self):
        result = network_http_post(
            {"url": f"http://127.0.0.1:{self.port}/echo", "body": {"key": "value"}},
            self.contract, self.ws,
        )
        self.assertEqual(result["status_code"], 200)
        data = json.loads(result["body"])
        self.assertEqual(data.get("key"), "value")

    def test_post_text_body(self):
        result = network_http_post(
            {"url": f"http://127.0.0.1:{self.port}/echo", "body_text": "hello"},
            self.contract, self.ws,
        )
        self.assertEqual(result["status_code"], 200)

    def test_invalid_scheme_raises(self):
        with self.assertRaises(ValueError):
            network_http_post(
                {"url": "ftp://example.com"},
                self.contract, self.ws,
            )

    def test_missing_url_raises(self):
        with self.assertRaises(ValueError):
            network_http_post({}, self.contract, self.ws)


# ---------------------------------------------------------------------------
# System — get_os_info
# ---------------------------------------------------------------------------

class TestSystemGetOsInfo(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("system_get_os_info", category="system", workspace_only=False)

    def test_returns_expected_keys(self):
        result = system_get_os_info({}, self.contract, self.ws)
        for key in ("platform", "platform_version", "architecture", "python_version", "hostname"):
            self.assertIn(key, result)
            self.assertIsInstance(result[key], str)

    def test_platform_matches_sys(self):
        import platform as pl
        result = system_get_os_info({}, self.contract, self.ws)
        self.assertEqual(result["platform"], pl.system())


# ---------------------------------------------------------------------------
# System — get_env_var
# ---------------------------------------------------------------------------

class TestSystemGetEnvVar(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("system_get_env_var", category="system", workspace_only=False)

    def test_existing_variable(self):
        os.environ["_TEST_BLOQUE1"] = "hello_bloque1"
        result = system_get_env_var({"name": "_TEST_BLOQUE1"}, self.contract, self.ws)
        self.assertTrue(result["found"])
        self.assertEqual(result["value"], "hello_bloque1")
        del os.environ["_TEST_BLOQUE1"]

    def test_missing_variable_with_default(self):
        result = system_get_env_var(
            {"name": "_NONEXISTENT_VAR_XYZ", "default": "fallback"},
            self.contract, self.ws,
        )
        self.assertFalse(result["found"])
        self.assertEqual(result["value"], "fallback")

    def test_missing_variable_no_default(self):
        result = system_get_env_var(
            {"name": "_NONEXISTENT_VAR_XYZ"},
            self.contract, self.ws,
        )
        self.assertFalse(result["found"])
        self.assertIsNone(result["value"])

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError):
            system_get_env_var({"name": ""}, self.contract, self.ws)


# ---------------------------------------------------------------------------
# System — get_workspace_info
# ---------------------------------------------------------------------------

class TestSystemGetWorkspaceInfo(unittest.TestCase):
    def setUp(self):
        self.ws = _workspace()
        self.contract = _contract("system_get_workspace_info", category="system", workspace_only=False)

    def test_returns_expected_keys(self):
        result = system_get_workspace_info({}, self.contract, self.ws)
        for key in ("workspace_root", "artifacts_path", "sequences_path",
                    "capabilities_count", "tools_count"):
            self.assertIn(key, result)

    def test_workspace_root_is_absolute(self):
        result = system_get_workspace_info({}, self.contract, self.ws)
        self.assertTrue(Path(result["workspace_root"]).is_absolute())

    def test_tool_count_positive(self):
        result = system_get_workspace_info({}, self.contract, self.ws)
        self.assertGreater(result["tools_count"], 0)


if __name__ == "__main__":
    unittest.main()
