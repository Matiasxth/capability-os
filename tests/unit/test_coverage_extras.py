"""
Extra coverage tests for modules close to the 80% threshold:
  - intent_interpreter.py (78% → target ≥80%)
  - sequences/runner.py (79% → target ≥80%)
  - input_extractor.py (73% → target ≥76%)
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.interpretation.input_extractor import InputExtractionError, InputExtractor
from system.core.interpretation.intent_interpreter import IntentInterpreter, IntentInterpreterError
from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.core.sequences.runner import SequenceRunner, SequenceRunError
from system.core.sequences.model import SequenceDefinition, SequenceStep, SequenceValidationError
from system.core.sequences.registry import SequenceRegistry
from system.core.sequences.storage import SequenceStorage

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "coverage_extras"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    return reg


# ===========================================================================
# IntentInterpreter — cover missing branches
# ===========================================================================

class TestIntentInterpreterBranches(unittest.TestCase):

    def test_empty_text_raises(self):
        reg = _registry()
        interpreter = IntentInterpreter(reg)
        with self.assertRaises(IntentInterpreterError):
            interpreter.interpret("")

    def test_non_string_text_raises(self):
        reg = _registry()
        interpreter = IntentInterpreter(reg)
        with self.assertRaises(IntentInterpreterError):
            interpreter.interpret(123)

    def test_llm_client_error_propagates(self):
        reg = _registry()
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.side_effect = LLMClientError("connection refused")
        interpreter = IntentInterpreter(reg, llm_client=mock_llm)
        with self.assertRaises(IntentInterpreterError) as ctx:
            interpreter.interpret("read a file")
        self.assertIn("connection refused", str(ctx.exception))

    def test_invalid_json_response_returns_unknown(self):
        reg = _registry()
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = "this is not json at all"
        interpreter = IntentInterpreter(reg, llm_client=mock_llm)
        result = interpreter.interpret("read a file")
        self.assertEqual(result["suggestion"]["type"], "unknown")
        self.assertIsNotNone(result.get("error"))

    def test_valid_capability_response(self):
        reg = _registry()
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = json.dumps({
            "type": "capability",
            "capability": "read_file",
            "inputs": {"path": "test.txt"},
        })
        interpreter = IntentInterpreter(reg, llm_client=mock_llm)
        result = interpreter.interpret("read test.txt")
        self.assertEqual(result["suggestion"]["type"], "capability")
        self.assertEqual(result["suggestion"]["capability"], "read_file")
        self.assertIsNone(result["error"])

    def test_json_embedded_in_text(self):
        reg = _registry()
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = 'Here is the result:\n{"type": "unknown"}\nDone.'
        interpreter = IntentInterpreter(reg, llm_client=mock_llm)
        result = interpreter.interpret("do something unknown")
        self.assertEqual(result["suggestion"]["type"], "unknown")

    def test_sequence_response(self):
        reg = _registry()
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = json.dumps({
            "type": "sequence",
            "steps": [
                {"step_id": "s1", "capability": "read_file", "inputs": {"path": "a.txt"}},
                {"step_id": "s2", "capability": "write_file", "inputs": {"path": "b.txt", "content": "x"}},
            ],
        })
        interpreter = IntentInterpreter(reg, llm_client=mock_llm)
        result = interpreter.interpret("read a.txt and write to b.txt")
        self.assertEqual(result["suggestion"]["type"], "sequence")


# ===========================================================================
# InputExtractor — cover missing branches
# ===========================================================================

class TestInputExtractorBranches(unittest.TestCase):

    def setUp(self):
        self.extractor = InputExtractor()

    def test_non_dict_raises(self):
        with self.assertRaises(InputExtractionError):
            self.extractor.extract("not_dict")

    def test_invalid_type_raises(self):
        with self.assertRaises(InputExtractionError):
            self.extractor.extract({"type": "invalid"})

    def test_unknown_type_returns_minimal(self):
        result = self.extractor.extract({"type": "unknown"})
        self.assertEqual(result, {"type": "unknown"})

    def test_capability_missing_id_raises(self):
        with self.assertRaises(InputExtractionError):
            self.extractor.extract({"type": "capability", "capability": ""})

    def test_capability_valid(self):
        result = self.extractor.extract({
            "type": "capability",
            "capability": "read_file",
            "inputs": {"path": "x"},
        })
        self.assertEqual(result["type"], "capability")
        self.assertEqual(result["capability"], "read_file")

    def test_sequence_valid(self):
        result = self.extractor.extract({
            "type": "sequence",
            "steps": [{"step_id": "s1", "capability": "read_file", "inputs": {"path": "x"}}],
        })
        self.assertEqual(result["type"], "sequence")
        self.assertIsInstance(result["steps"], list)

    def test_sequence_non_list_steps_raises(self):
        with self.assertRaises(InputExtractionError):
            self.extractor.extract({"type": "sequence", "steps": "bad"})

    def test_sequence_step_missing_capability_raises(self):
        with self.assertRaises(InputExtractionError):
            self.extractor.extract({"type": "sequence", "steps": [{"step_id": "s1", "inputs": {}}]})


# ===========================================================================
# SequenceRunner — cover edge cases
# ===========================================================================

class TestSequenceRunnerBranches(unittest.TestCase):

    def test_no_sequence_id_or_definition_raises(self):
        reg = _registry()
        storage = SequenceStorage(_workspace("runner_no_id"))
        seq_reg = SequenceRegistry(storage)
        runner = SequenceRunner(
            sequence_registry=seq_reg,
            capability_registry=reg,
            capability_engine=MagicMock(),
            capability_executor=lambda cap_id, inputs: {"status": "success", "final_output": {}},
        )
        with self.assertRaises(SequenceValidationError):
            runner.run()

    def test_non_dict_inputs_raises(self):
        reg = _registry()
        storage = SequenceStorage(_workspace("runner_bad_inputs"))
        seq_reg = SequenceRegistry(storage)
        runner = SequenceRunner(
            sequence_registry=seq_reg,
            capability_registry=reg,
            capability_engine=MagicMock(),
            capability_executor=lambda cap_id, inputs: {"status": "success", "final_output": {}},
        )
        with self.assertRaises(SequenceValidationError):
            runner.run(sequence_definition={"id": "test", "name": "test", "steps": []},
                       sequence_inputs="not_a_dict")

    def test_inline_definition_executes(self):
        reg = _registry()
        ws = _workspace("runner_inline")
        storage = SequenceStorage(ws)
        seq_reg = SequenceRegistry(storage)

        call_log = []

        def mock_executor(cap_id, inputs):
            call_log.append(cap_id)
            return {
                "status": "success",
                "execution_id": f"exec_{cap_id}",
                "final_output": {"stdout": "ok"},
            }

        runner = SequenceRunner(
            sequence_registry=seq_reg,
            capability_registry=reg,
            capability_engine=MagicMock(),
            capability_executor=mock_executor,
        )
        result = runner.run(
            sequence_definition={
                "id": "test_seq",
                "name": "Test Sequence",
                "steps": [
                    {"step_id": "step_a", "capability": "read_file", "inputs": {"path": "x"}},
                ],
            },
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("read_file", call_log)


if __name__ == "__main__":
    unittest.main()
