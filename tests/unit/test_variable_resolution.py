from __future__ import annotations

import unittest

from system.core.state import StateManager, VariableResolutionError


class VariableResolutionTests(unittest.TestCase):
    def test_resolves_nested_structures(self) -> None:
        manager = StateManager({"project_name": "demo"})
        manager.update_state({"meta": {"root": "/tmp"}})
        manager.record_step_output("create_project", {"project_path": "/tmp/demo", "result": ["ok"]})
        manager.set_runtime_provider(lambda: {"execution_id": "exec_abc", "status": "running"})

        payload = {
            "cmd": "run {{inputs.project_name}}",
            "cwd": "{{state.meta.root}}",
            "project": "{{steps.create_project.outputs.project_path}}",
            "runtime_status": "{{runtime.status}}",
            "list": ["{{inputs.project_name}}", "{{runtime.execution_id}}"],
        }
        resolved = manager.resolve_templates(payload)

        self.assertEqual(resolved["cmd"], "run demo")
        self.assertEqual(resolved["cwd"], "/tmp")
        self.assertEqual(resolved["project"], "/tmp/demo")
        self.assertEqual(resolved["runtime_status"], "running")
        self.assertEqual(resolved["list"], ["demo", "exec_abc"])

    def test_fails_when_step_output_does_not_exist(self) -> None:
        manager = StateManager({})
        with self.assertRaises(VariableResolutionError):
            manager.resolve_templates("{{steps.unknown.outputs.value}}")


if __name__ == "__main__":
    unittest.main()
