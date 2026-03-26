from __future__ import annotations

import unittest

from system.capabilities.registry import CapabilityRegistry
from system.core.interpretation import (
    CapabilityMatcher,
    InputExtractor,
    IntentInterpreter,
    IntentInterpreterError,
    LLMClient,
)


class _StubAdapter:
    def __init__(self, text: str):
        self.text = text

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        return self.text


class Phase8IntentInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry()
        self.registry.load_from_directory("system/capabilities/contracts/v1")

    def _build_interpreter(self, llm_output: str) -> IntentInterpreter:
        llm_client = LLMClient(adapter=_StubAdapter(llm_output))
        return IntentInterpreter(
            self.registry,
            llm_client=llm_client,
            input_extractor=InputExtractor(),
            capability_matcher=CapabilityMatcher(self.registry),
        )

    def test_valid_capability_suggestion(self) -> None:
        interpreter = self._build_interpreter(
            '{"type":"capability","capability":"read_file","inputs":{"path":" main.py "}}'
        )
        result = interpreter.interpret("lee main.py")
        self.assertTrue(result["suggest_only"])
        self.assertEqual(result["suggestion"]["type"], "capability")
        self.assertEqual(result["suggestion"]["capability"], "read_file")
        self.assertEqual(result["suggestion"]["inputs"]["path"], "main.py")

    def test_unknown_type(self) -> None:
        interpreter = self._build_interpreter('{"type":"unknown"}')
        result = interpreter.interpret("haz magia")
        self.assertEqual(result["suggestion"]["type"], "unknown")

    def test_invalid_json_response_becomes_unknown(self) -> None:
        interpreter = self._build_interpreter("not-json-at-all")
        result = interpreter.interpret("lee un archivo")
        self.assertEqual(result["suggestion"]["type"], "unknown")
        self.assertIsNotNone(result["error"])

    def test_rejects_non_existing_capability(self) -> None:
        interpreter = self._build_interpreter(
            '{"type":"capability","capability":"non_existing_capability","inputs":{}}'
        )
        with self.assertRaises(IntentInterpreterError):
            interpreter.interpret("haz algo raro")

    def test_sequence_validation_against_registry(self) -> None:
        interpreter = self._build_interpreter(
            '{"type":"sequence","steps":[{"step_id":"s1","capability":"read_file","inputs":{"path":"x.txt"}}]}'
        )
        result = interpreter.interpret("secuencia")
        self.assertEqual(result["suggestion"]["type"], "sequence")
        self.assertEqual(result["suggestion"]["steps"][0]["capability"], "read_file")

        bad = self._build_interpreter(
            '{"type":"sequence","steps":[{"step_id":"s1","capability":"nope","inputs":{}}]}'
        )
        with self.assertRaises(IntentInterpreterError):
            bad.interpret("bad sequence")

    def test_sequence_rejects_unknown_step_input_fields(self) -> None:
        interpreter = self._build_interpreter(
            (
                '{"type":"sequence","steps":['
                '{"step_id":"s1","capability":"read_file","inputs":{"path":"x.txt","extra":"nope"}}'
                "]}"
            )
        )
        with self.assertRaises(IntentInterpreterError) as ctx:
            interpreter.interpret("lee archivo")
        self.assertIn("unknown input fields", str(ctx.exception))

    def test_sequence_valid_with_contract_inputs(self) -> None:
        interpreter = self._build_interpreter(
            (
                '{"type":"sequence","steps":['
                '{"step_id":"s1","capability":"read_file","inputs":{"path":"main.py"}},'
                '{"step_id":"s2","capability":"write_file","inputs":{"path":"copy.py","content":"ok"}}'
                "]}"
            )
        )
        result = interpreter.interpret("leer y escribir archivo")
        self.assertTrue(result["suggest_only"])
        self.assertEqual(result["suggestion"]["type"], "sequence")
        self.assertEqual(len(result["suggestion"]["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
