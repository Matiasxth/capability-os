"""Tests for Runtime Analyzer (Componente 1)."""
from __future__ import annotations

import unittest
from pathlib import Path

from system.core.self_improvement.runtime_analyzer import RuntimeAnalyzer
from system.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.load_from_directory(ROOT / "system" / "tools" / "contracts" / "v1")
    return reg


class TestRuntimeAnalyzer(unittest.TestCase):

    def test_existing_tool_detected(self):
        ra = RuntimeAnalyzer(tool_registry=_registry())
        result = ra.analyze({"capability_id": "filesystem_read_file", "intent": "read a file"})
        self.assertEqual(result["strategy"], "existing_tool")
        self.assertGreater(result["confidence"], 0.9)

    def test_browser_keyword(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "open the web page and scrape data"})
        self.assertEqual(result["strategy"], "browser")

    def test_cli_keyword(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "run git clone on the repository"})
        self.assertEqual(result["strategy"], "cli")
        self.assertIn("git", result["suggestion"])

    def test_generic_defaults_to_python(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "calculate the fibonacci sequence"})
        self.assertEqual(result["strategy"], "python")

    def test_not_implementable(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "make a phone call to the office"})
        self.assertEqual(result["strategy"], "not_implementable")

    def test_nodejs_keyword(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "create a websocket server with socket.io"})
        self.assertEqual(result["strategy"], "nodejs")

    def test_result_has_all_fields(self):
        ra = RuntimeAnalyzer()
        result = ra.analyze({"intent": "do something"})
        for key in ("strategy", "reason", "suggestion", "confidence"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
