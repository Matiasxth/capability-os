"""Tests for Tool Validator (Componente 5)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
from system.core.self_improvement.python_sandbox import PythonSandbox
from system.core.self_improvement.tool_validator import ToolValidator

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "tool_val"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _contract(**extra_outputs) -> dict:
    outputs = {"status": {"type": "string"}, "result": {"type": "string"}}
    outputs.update(extra_outputs)
    return {
        "inputs": {"value": {"type": "string", "required": True, "description": "Test input"}},
        "outputs": outputs,
    }


def _validator(name: str, llm: LLMClient | None = None) -> ToolValidator:
    ws = _ws(name)
    return ToolValidator(
        python_sandbox=PythonSandbox(ws / "py"),
        nodejs_sandbox=NodejsSandbox(ws / "js"),
        llm_client=llm,
    )


class TestValidCodeFirstAttempt(unittest.TestCase):

    def test_python_valid_first_try(self):
        v = _validator("py_ok")
        code = '''def execute(inputs: dict) -> dict:
    return {"status": "success", "result": inputs.get("value", "")}
'''
        result = v.validate(code, _contract(), runtime="python")
        self.assertTrue(result["validated"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["runtime"], "python")
        self.assertIn("result", result["test_output"])


class TestAutoCorrection(unittest.TestCase):

    def test_fix_on_second_attempt(self):
        """First code has a typo, LLM provides corrected version."""
        mock_llm = MagicMock(spec=LLMClient)
        # LLM returns corrected code on fix request
        mock_llm.complete.return_value = '''def execute(inputs: dict) -> dict:
    return {"status": "success", "result": str(inputs.get("value", ""))}
'''
        v = _validator("fix", llm=mock_llm)
        # Broken code: NameError on undefined var
        broken = '''def execute(inputs: dict) -> dict:
    return {"status": "success", "result": undefined_var}
'''
        result = v.validate(broken, _contract(), runtime="python")
        self.assertTrue(result["validated"])
        self.assertGreater(result["attempts"], 1)


class TestAllAttemptsFail(unittest.TestCase):

    def test_three_failures_returns_not_validated(self):
        mock_llm = MagicMock(spec=LLMClient)
        # LLM always returns broken code
        mock_llm.complete.return_value = '''def execute(inputs: dict) -> dict:
    return undefined_var
'''
        v = _validator("allfail", llm=mock_llm)
        broken = '''def execute(inputs: dict) -> dict:
    raise RuntimeError("always fails")
'''
        result = v.validate(broken, _contract(), runtime="python")
        self.assertFalse(result["validated"])
        self.assertEqual(result["attempts"], 3)
        self.assertTrue(len(result["error"]) > 0)


class TestOutputShapeValidation(unittest.TestCase):

    def test_missing_expected_key_triggers_retry(self):
        """Code runs fine but output misses a required key."""
        mock_llm = MagicMock(spec=LLMClient)
        # LLM returns code that includes the missing key
        mock_llm.complete.return_value = '''def execute(inputs: dict) -> dict:
    return {"status": "success", "result": "ok", "extra_field": 42}
'''
        v = _validator("shape", llm=mock_llm)
        # Code that returns status but not "result"
        code = '''def execute(inputs: dict) -> dict:
    return {"status": "success", "something_else": 1}
'''
        contract = _contract(extra_field={"type": "integer"})
        result = v.validate(code, contract, runtime="python")
        # After LLM fix it should include the missing key
        self.assertTrue(result["validated"])


if __name__ == "__main__":
    unittest.main()
