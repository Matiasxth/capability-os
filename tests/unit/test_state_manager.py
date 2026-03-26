from __future__ import annotations

import unittest

from system.core.state import StateManager, VariableResolutionError


class StateManagerTests(unittest.TestCase):
    def test_state_manager_stores_and_resolves_explicit_variables(self) -> None:
        manager = StateManager({"project_name": "demo", "target_dir": "/tmp"})
        manager.update_state({"project_path": "/tmp/demo"})
        manager.record_step_output("create_project", {"project_path": "/tmp/demo"})
        manager.set_runtime_provider(lambda: {"execution_id": "exec_123"})

        resolved = manager.resolve_templates(
            {
                "name": "{{inputs.project_name}}",
                "path": "{{state.project_path}}",
                "from_step": "{{steps.create_project.outputs.project_path}}",
                "runtime": "{{runtime.execution_id}}",
                "message": "build {{inputs.project_name}}",
            }
        )

        self.assertEqual(resolved["name"], "demo")
        self.assertEqual(resolved["path"], "/tmp/demo")
        self.assertEqual(resolved["from_step"], "/tmp/demo")
        self.assertEqual(resolved["runtime"], "exec_123")
        self.assertEqual(resolved["message"], "build demo")

    def test_state_manager_fails_on_missing_variable(self) -> None:
        manager = StateManager({"project_name": "demo"})
        with self.assertRaises(VariableResolutionError):
            manager.resolve_templates("{{state.project_path}}")

    def test_state_manager_fails_on_implicit_variable(self) -> None:
        manager = StateManager({"project_name": "demo"})
        with self.assertRaises(VariableResolutionError):
            manager.resolve_templates("{{project_name}}")


if __name__ == "__main__":
    unittest.main()
