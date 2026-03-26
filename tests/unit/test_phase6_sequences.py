from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase6_sequences"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _build_sequence(sequence_id: str) -> dict:
    return {
        "id": sequence_id,
        "name": "Copy Source File",
        "steps": [
            {
                "step_id": "read_source",
                "capability": "read_file",
                "inputs": {"path": "source.txt"},
            },
            {
                "step_id": "write_copy",
                "capability": "write_file",
                "inputs": {
                    "path": "copy.txt",
                    "content": "{{steps.read_source.outputs.content}}",
                },
            },
            {
                "step_id": "read_copy",
                "capability": "read_file",
                "inputs": {"path": "{{state.path}}"},
            },
        ],
    }


class Phase6SequencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "source.txt").write_text("hello from sequence", encoding="utf-8-sig")
        self.service = CapabilityOSUIBridgeService(workspace_root=self.workspace)

    def test_save_sequence(self) -> None:
        sequence = _build_sequence("copy_source_sequence")
        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "save_sequence", "inputs": {"sequence_definition": sequence}},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["status"], "success")
        self.assertEqual(payload["final_output"]["sequence_id"], "copy_source_sequence")

        stored = self.workspace / "sequences" / "copy_source_sequence.json"
        self.assertTrue(stored.exists())

    def test_load_sequence(self) -> None:
        sequence = _build_sequence("loadable_sequence")
        save = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "save_sequence", "inputs": {"sequence_definition": sequence}},
        )
        self.assertEqual(save.payload["status"], "success")

        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "load_sequence", "inputs": {"sequence_id": "loadable_sequence"}},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "success")
        loaded = payload["final_output"]["sequence_definition"]
        self.assertEqual(loaded["id"], "loadable_sequence")
        self.assertEqual(len(loaded["steps"]), 3)

    def test_run_sequence_successful(self) -> None:
        sequence = _build_sequence("run_success_sequence")
        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "run_sequence", "inputs": {"sequence_definition": sequence}},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "success")
        final_output = payload["final_output"]
        self.assertEqual(final_output["sequence_id"], "run_success_sequence")
        self.assertEqual(final_output["last_step"], "read_copy")
        self.assertEqual(final_output["last_output"]["content"], "hello from sequence")
        self.assertTrue((self.workspace / "copy.txt").exists())

    def test_run_sequence_failure_on_intermediate_step(self) -> None:
        failing_sequence = {
            "id": "failing_sequence",
            "name": "Failing sequence",
            "steps": [
                {
                    "step_id": "read_source",
                    "capability": "read_file",
                    "inputs": {"path": "source.txt"},
                },
                {
                    "step_id": "fail_step",
                    "capability": "read_file",
                    "inputs": {"path": "missing.txt"},
                },
                {
                    "step_id": "never_runs",
                    "capability": "write_file",
                    "inputs": {"path": "x.txt", "content": "nope"},
                },
            ],
        }
        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "run_sequence", "inputs": {"sequence_definition": failing_sequence}},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["runtime"]["status"], "error")
        self.assertEqual(payload["runtime"]["failed_step"], "fail_step")

    def test_run_sequence_explicit_variables_inputs_steps_state(self) -> None:
        sequence = {
            "id": "vars_sequence",
            "name": "Variables sequence",
            "steps": [
                {
                    "step_id": "write_seed",
                    "capability": "write_file",
                    "inputs": {
                        "path": "{{inputs.target_path}}",
                        "content": "{{inputs.seed_content}}",
                    },
                },
                {
                    "step_id": "read_seed",
                    "capability": "read_file",
                    "inputs": {"path": "{{steps.write_seed.outputs.path}}"},
                },
                {
                    "step_id": "write_state_copy",
                    "capability": "write_file",
                    "inputs": {
                        "path": "state_copy.txt",
                        "content": "{{state.content}}",
                    },
                },
            ],
        }
        response = self.service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "run_sequence",
                "inputs": {
                    "sequence_definition": sequence,
                    "inputs": {"target_path": "seed.txt", "seed_content": "abc"},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "success")
        self.assertTrue((self.workspace / "seed.txt").exists())
        self.assertTrue((self.workspace / "state_copy.txt").exists())
        self.assertEqual((self.workspace / "state_copy.txt").read_text(encoding="utf-8-sig"), "abc")

    def test_run_sequence_integration_with_capability_engine(self) -> None:
        sequence = _build_sequence("engine_integration_sequence")
        called_capabilities: list[str] = []

        original_execute = self.service.engine.execute

        def wrapped_execute(contract, inputs):
            called_capabilities.append(contract["id"])
            return original_execute(contract, inputs)

        self.service.engine.execute = wrapped_execute  # type: ignore[assignment]
        response = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "run_sequence", "inputs": {"sequence_definition": sequence}},
        )
        self.service.engine.execute = original_execute  # type: ignore[assignment]

        self.assertEqual(response.payload["status"], "success")
        self.assertEqual(called_capabilities, ["read_file", "write_file", "read_file"])

    def test_run_sequence_observation_logs(self) -> None:
        sequence = _build_sequence("logs_sequence")
        success = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "run_sequence", "inputs": {"sequence_definition": sequence}},
        )
        success_events = [entry["event"] for entry in success.payload["runtime"]["logs"]]
        self.assertEqual(success_events[0], "execution_started")
        self.assertIn("step_started", success_events)
        self.assertIn("step_succeeded", success_events)
        self.assertEqual(success_events[-1], "execution_finished")

        failing = {
            "id": "logs_fail_sequence",
            "name": "Logs fail",
            "steps": [
                {"step_id": "x", "capability": "read_file", "inputs": {"path": "missing.txt"}},
            ],
        }
        error = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "run_sequence", "inputs": {"sequence_definition": failing}},
        )
        error_events = [entry["event"] for entry in error.payload["runtime"]["logs"]]
        self.assertIn("step_failed", error_events)
        self.assertEqual(error_events[-1], "execution_finished")


if __name__ == "__main__":
    unittest.main()
