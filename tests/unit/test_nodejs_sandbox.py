"""Tests for Node.js Sandbox (Componente 4)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from system.core.self_improvement.nodejs_sandbox import NodejsSandbox, _find_node

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "node_sandbox"

_NODE_AVAILABLE = _find_node() is not None


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


@unittest.skipUnless(_NODE_AVAILABLE, "Node.js not installed")
class TestNodejsSandbox(unittest.TestCase):

    def test_valid_code_executes(self):
        sb = NodejsSandbox(_ws("valid"))
        code = '''async function execute(inputs) {
  const name = inputs.name || "world";
  return { status: "success", greeting: "Hello " + name + "!" };
}
module.exports = { execute };
'''
        result = sb.execute(code, {"name": "Bob"})
        self.assertTrue(result["success"])
        self.assertEqual(result["output"]["greeting"], "Hello Bob!")

    def test_timeout_respected(self):
        sb = NodejsSandbox(_ws("timeout"), timeout_sec=2)
        code = '''async function execute(inputs) {
  await new Promise(r => setTimeout(r, 15000));
  return { status: "success" };
}
module.exports = { execute };
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("Timeout", result["error"])

    def test_forbidden_require_blocked(self):
        sb = NodejsSandbox(_ws("forbidden"))
        code = '''const { exec } = require("child_process");
async function execute(inputs) { return { status: "success" }; }
module.exports = { execute };
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("Blocked", result["error"])

    def test_runtime_error_returns_failure(self):
        sb = NodejsSandbox(_ws("error"))
        code = '''async function execute(inputs) {
  throw new Error("intentional error");
}
module.exports = { execute };
'''
        result = sb.execute(code, {})
        self.assertFalse(result["success"])
        self.assertIn("intentional error", result["error"])


class TestNodeNotAvailable(unittest.TestCase):

    @patch("system.core.self_improvement.nodejs_sandbox._find_node", return_value=None)
    def test_no_node_returns_clear_error(self, _mock):
        sb = NodejsSandbox(_ws("no_node"))
        result = sb.execute('module.exports = { execute: async () => ({}) };', {})
        self.assertFalse(result["success"])
        self.assertIn("not installed", result["error"])


class TestCleanup(unittest.TestCase):

    @unittest.skipUnless(_NODE_AVAILABLE, "Node.js not installed")
    def test_temp_files_removed(self):
        ws = _ws("cleanup")
        sb = NodejsSandbox(ws)
        code = '''async function execute(inputs) { return { status: "success" }; }
module.exports = { execute };
'''
        sb.execute(code, {})
        remaining = list(ws.glob("temp_*.js")) + list(ws.glob("runner_*.js"))
        self.assertEqual(len(remaining), 0)


if __name__ == "__main__":
    unittest.main()
