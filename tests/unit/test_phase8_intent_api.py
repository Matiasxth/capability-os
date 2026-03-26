from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.interpretation import LLMClient
from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase8_api"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _StubAdapter:
    def __init__(self, text: str):
        self.text = text

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        return self.text


class Phase8IntentAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _service(self, llm_output: str) -> CapabilityOSUIBridgeService:
        llm_client = LLMClient(adapter=_StubAdapter(llm_output))
        return CapabilityOSUIBridgeService(workspace_root=self.workspace, llm_client=llm_client)

    def test_interpret_endpoint_valid(self) -> None:
        service = self._service(
            '{"type":"capability","capability":"read_file","inputs":{"path":"demo.txt"}}'
        )
        response = service.handle("POST", "/interpret", {"text": "lee demo.txt"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.payload["suggest_only"])
        self.assertEqual(response.payload["suggestion"]["capability"], "read_file")

    def test_interpret_endpoint_unknown(self) -> None:
        service = self._service("garbage response")
        response = service.handle("POST", "/interpret", {"text": "algo ambiguo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["suggestion"]["type"], "unknown")

    def test_interpret_endpoint_invalid_capability(self) -> None:
        service = self._service(
            '{"type":"capability","capability":"non_existing_capability","inputs":{}}'
        )
        response = service.handle("POST", "/interpret", {"text": "haz algo"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.payload["error_code"], "interpretation_error")

    def test_interpret_endpoint_sequence_valid_inputs(self) -> None:
        service = self._service(
            (
                '{"type":"sequence","steps":['
                '{"step_id":"s1","capability":"read_file","inputs":{"path":"demo.txt"}},'
                '{"step_id":"s2","capability":"write_file","inputs":{"path":"copy.txt","content":"ok"}}'
                "]}"
            )
        )
        response = service.handle("POST", "/interpret", {"text": "secuencia valida"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["suggestion"]["type"], "sequence")
        self.assertEqual(len(response.payload["suggestion"]["steps"]), 2)

    def test_interpret_endpoint_sequence_rejects_extra_inputs(self) -> None:
        service = self._service(
            (
                '{"type":"sequence","steps":['
                '{"step_id":"s1","capability":"read_file","inputs":{"path":"demo.txt","extra":"bad"}}'
                "]}"
            )
        )
        response = service.handle("POST", "/interpret", {"text": "secuencia invalida"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.payload["error_code"], "interpretation_error")
        self.assertIn("unknown input fields", response.payload["error_message"])

    def test_plan_endpoint_builds_valid_plan(self) -> None:
        service = self._service(
            '{"type":"capability","capability":"read_file","inputs":{"path":"demo.txt"}}'
        )
        response = service.handle("POST", "/plan", {"intent": "lee demo.txt"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["type"], "capability")
        self.assertTrue(response.payload["suggest_only"])
        self.assertTrue(response.payload["valid"])
        self.assertEqual(len(response.payload["steps"]), 1)
        self.assertEqual(response.payload["steps"][0]["capability"], "read_file")

    def test_plan_endpoint_reports_validation_errors(self) -> None:
        service = self._service(
            '{"type":"capability","capability":"read_file","inputs":{}}'
        )
        response = service.handle("POST", "/plan", {"intent": "lee archivo"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.payload["valid"])
        self.assertTrue(any(err["code"] == "missing_required_inputs" for err in response.payload["errors"]))


if __name__ == "__main__":
    unittest.main()
