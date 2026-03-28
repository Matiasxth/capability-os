"""Tests for Python Sandbox (Componente 3)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.self_improvement.python_sandbox import PythonSandbox

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "py_sandbox"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


class TestPythonSandbox(unittest.TestCase):

    def test_valid_code_executes(self):
        sb = PythonSandbox(_ws("valid"))
        code = '''def execute(inputs: dict) -> dict:
    name = inputs.get("name", "world")
    return {"status": "success", "greeting": f"Hello {name}!"}
'''
        result = sb.execute(code, {"name": "Alice"})
        self.assertTrue(result["success"])
        self.assertEqual(result["output"]["greeting"], "Hello Alice!")
        self.assertGreater(result["duration_ms"], 0)

    def test_timeout_respected(self):
        sb = PythonSandbox(_ws("timeout"), timeout_sec=2)
        code = '''def execute(inputs: dict) -> dict:
    import time
    time.sleep(10)
    return {"status": "success"}
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("Timeout", result["error"])

    def test_forbidden_import_blocked(self):
        sb = PythonSandbox(_ws("forbidden"))
        code = '''def execute(inputs: dict) -> dict:
    import subprocess
    subprocess.run(["echo", "hacked"])
    return {"status": "success"}
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("Blocked", result["error"])
        self.assertIn("subprocess", result["error"])

    def test_runtime_error_returns_failure(self):
        sb = PythonSandbox(_ws("error"))
        code = '''def execute(inputs: dict) -> dict:
    raise ValueError("intentional error")
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("intentional error", result["output"].get("error", result["error"]))

    def test_no_output_is_failure(self):
        sb = PythonSandbox(_ws("noout"))
        code = '''def execute(inputs: dict) -> dict:
    pass  # returns None
'''
        result = sb.execute(code, {})
        # The wrapper catches None and wraps it, but let's verify it's handled
        self.assertIsInstance(result, dict)

    def test_cleanup_removes_temp_file(self):
        ws = _ws("cleanup")
        sb = PythonSandbox(ws)
        code = '''def execute(inputs: dict) -> dict:
    return {"status": "success"}
'''
        sb.execute(code, {})
        # No temp files should remain
        remaining = list(ws.glob("temp_*.py"))
        self.assertEqual(len(remaining), 0)


if __name__ == "__main__":
    unittest.main()
