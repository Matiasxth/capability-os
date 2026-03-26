from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase7_capabilities"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class Phase7CapabilitiesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.target_file = self.workspace / "main.py"
        self.target_file.write_text("print('old')\n", encoding="utf-8-sig")
        self.service = CapabilityOSUIBridgeService(workspace_root=self.workspace)

    def _execute(self, capability_id: str, inputs: dict):
        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": capability_id, "inputs": inputs},
        )
        self.assertEqual(response.status_code, 200)
        return response.payload

    def test_modify_code_replace_mode(self) -> None:
        payload = self._execute(
            "modify_code",
            {"file_path": "main.py", "modification": "print('new')\n", "mode": "replace"},
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["status"], "success")
        self.assertTrue(payload["final_output"]["path"].endswith("main.py"))
        self.assertEqual(self.target_file.read_text(encoding="utf-8-sig"), "print('new')\n")

    def test_modify_code_append_mode(self) -> None:
        payload = self._execute(
            "modify_code",
            {"file_path": "main.py", "modification": "print('append')\n", "mode": "append"},
        )
        self.assertEqual(payload["status"], "success")
        content = self.target_file.read_text(encoding="utf-8-sig")
        self.assertIn("print('old')", content)
        self.assertIn("print('append')", content)

    def test_modify_code_errors(self) -> None:
        outside = self.case_dir / "outside.py"
        outside.write_text("x", encoding="utf-8-sig")
        outside_payload = self._execute(
            "modify_code",
            {"file_path": str(outside), "modification": "y", "mode": "replace"},
        )
        self.assertEqual(outside_payload["status"], "error")
        self.assertEqual(outside_payload["runtime"]["status"], "error")

        bad_mode = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "modify_code", "inputs": {"file_path": "main.py", "modification": "x", "mode": "invalid"}},
        )
        self.assertEqual(bad_mode.status_code, 400)
        self.assertEqual(bad_mode.payload["error_code"], "validation_error")

    def test_diagnose_error_detection_and_fallback(self) -> None:
        cases = [
            ("ModuleNotFoundError: No module named 'requests'", "ModuleNotFoundError"),
            ("SyntaxError: invalid syntax", "SyntaxError"),
            ("bash: foo: command not found", "command_not_found"),
            ("Permission denied: /root/file", "permission_denied"),
            ("Unhandled exception happened", "unknown_error"),
        ]
        for error_output, expected in cases:
            payload = self._execute("diagnose_error", {"error_output": error_output})
            self.assertEqual(payload["status"], "success")
            diagnosis = payload["final_output"]["diagnosis"]
            self.assertEqual(diagnosis["error_type"], expected)
            self.assertIn("possible_cause", diagnosis)
            self.assertIn("suggested_action", diagnosis)

    def test_integration_with_capability_engine(self) -> None:
        calls: list[str] = []
        original = self.service.engine.execute

        def wrapped(contract, inputs):
            calls.append(contract["id"])
            return original(contract, inputs)

        self.service.engine.execute = wrapped  # type: ignore[assignment]
        payload = self._execute(
            "modify_code",
            {"file_path": "main.py", "modification": "print('z')\n", "mode": "replace"},
        )
        self.service.engine.execute = original  # type: ignore[assignment]

        self.assertEqual(payload["status"], "success")
        self.assertEqual(calls, ["read_file", "write_file"])

    def test_sequence_integration_with_phase7_capabilities(self) -> None:
        sequence = {
            "id": "phase_seven_sequence",
            "name": "Phase7 sequence",
            "steps": [
                {
                    "step_id": "modify",
                    "capability": "modify_code",
                    "inputs": {
                        "file_path": "main.py",
                        "modification": "print('seq')\n",
                        "mode": "append",
                    },
                },
                {
                    "step_id": "diagnose",
                    "capability": "diagnose_error",
                    "inputs": {"error_output": "{{inputs.error_output}}"},
                },
            ],
        }
        payload = self._execute(
            "run_sequence",
            {"sequence_definition": sequence, "inputs": {"error_output": "SyntaxError: invalid syntax"}},
        )
        self.assertEqual(payload["status"], "success")
        steps = payload["final_output"]["steps"]
        self.assertEqual(steps["modify"]["output"]["status"], "success")
        self.assertEqual(steps["diagnose"]["output"]["diagnosis"]["error_type"], "SyntaxError")
        self.assertIn("print('seq')", self.target_file.read_text(encoding="utf-8-sig"))

    def test_observation_logs_success_and_error(self) -> None:
        success = self._execute(
            "modify_code",
            {"file_path": "main.py", "modification": "print('ok')\n", "mode": "replace"},
        )
        success_events = [entry["event"] for entry in success["runtime"]["logs"]]
        self.assertEqual(success_events[0], "execution_started")
        self.assertIn("step_succeeded", success_events)
        self.assertEqual(success_events[-1], "execution_finished")

        error = self._execute(
            "modify_code",
            {"file_path": str(self.case_dir / "outside.py"), "modification": "x", "mode": "replace"},
        )
        error_events = [entry["event"] for entry in error["runtime"]["logs"]]
        self.assertEqual(error["status"], "error")
        self.assertIn("step_failed", error_events)
        self.assertEqual(error_events[-1], "execution_finished")


if __name__ == "__main__":
    unittest.main()
