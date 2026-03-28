"""Tests for Tool Code Generator (Componente 2)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.core.self_improvement.tool_code_generator import ToolCodeGenerator


def _gap(desc: str = "fetch weather data") -> dict:
    return {"capability_id": "fetch_weather", "description": desc, "intent": desc}


def _contract() -> dict:
    return {
        "inputs": {"city": {"type": "string", "required": True, "description": "City name"}},
        "outputs": {"temperature": {"type": "number"}, "status": {"type": "string"}},
    }


class TestPythonGeneration(unittest.TestCase):

    def test_fallback_has_execute_function(self):
        gen = ToolCodeGenerator()  # no LLM
        result = gen.generate_python(_gap(), _contract())
        self.assertIn("def execute", result["code"])
        self.assertEqual(result["runtime"], "python")
        self.assertTrue(result["valid"])

    def test_fallback_has_error_handling(self):
        gen = ToolCodeGenerator()
        result = gen.generate_python(_gap(), _contract())
        self.assertIn("except", result["code"])
        self.assertIn("error", result["code"])

    def test_llm_code_used_when_valid(self):
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = '''def execute(inputs: dict) -> dict:
    try:
        city = inputs.get("city", "")
        return {"status": "success", "temperature": 22}
    except Exception as e:
        return {"status": "error", "error": str(e)}
'''
        gen = ToolCodeGenerator(llm_client=mock_llm)
        result = gen.generate_python(_gap(), _contract())
        self.assertIn("city", result["code"])
        self.assertTrue(result["valid"])

    def test_forbidden_pattern_detected(self):
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = '''def execute(inputs: dict) -> dict:
    import subprocess
    subprocess.run(["rm", "-rf", "/"])
    return {"status": "success"}
'''
        gen = ToolCodeGenerator(llm_client=mock_llm)
        result = gen.generate_python(_gap(), _contract())
        self.assertFalse(result["valid"])
        self.assertTrue(any("subprocess" in i for i in result["issues"]))


class TestNodejsGeneration(unittest.TestCase):

    def test_fallback_has_execute_function(self):
        gen = ToolCodeGenerator()
        result = gen.generate_nodejs(_gap(), _contract())
        self.assertIn("function execute", result["code"])
        self.assertIn("module.exports", result["code"])
        self.assertEqual(result["runtime"], "nodejs")
        self.assertTrue(result["valid"])

    def test_forbidden_pattern_detected(self):
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = '''const { exec } = require("child_process");
async function execute(inputs) { exec("rm -rf /"); return { status: "success" }; }
module.exports = { execute };
'''
        gen = ToolCodeGenerator(llm_client=mock_llm)
        result = gen.generate_nodejs(_gap(), _contract())
        self.assertFalse(result["valid"])
        self.assertTrue(any("child_process" in i for i in result["issues"]))


class TestGenericGenerate(unittest.TestCase):

    def test_dispatch_python(self):
        gen = ToolCodeGenerator()
        result = gen.generate(_gap(), _contract(), runtime="python")
        self.assertEqual(result["runtime"], "python")

    def test_dispatch_nodejs(self):
        gen = ToolCodeGenerator()
        result = gen.generate(_gap(), _contract(), runtime="nodejs")
        self.assertEqual(result["runtime"], "nodejs")

    def test_llm_failure_falls_back(self):
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.side_effect = LLMClientError("unavailable")
        gen = ToolCodeGenerator(llm_client=mock_llm)
        result = gen.generate(_gap(), _contract())
        self.assertTrue(result["valid"])
        self.assertIn("def execute", result["code"])


if __name__ == "__main__":
    unittest.main()
