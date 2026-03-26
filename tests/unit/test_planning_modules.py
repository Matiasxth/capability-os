from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.planning import PlanBuildError, PlanBuilder, PlanValidator

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "planning_modules"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class PlanningModulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)

        self.registry = CapabilityRegistry()
        self.registry.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")

    def test_plan_builder_converts_capability_suggestion_to_step(self) -> None:
        builder = PlanBuilder()
        plan = builder.build(
            {
                "suggest_only": True,
                "suggestion": {
                    "type": "capability",
                    "capability": "read_file",
                    "inputs": {"path": "demo.txt"},
                },
            }
        )
        self.assertEqual(plan["type"], "capability")
        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(plan["steps"][0]["step_id"], "step_1")
        self.assertEqual(plan["steps"][0]["capability"], "read_file")

    def test_plan_builder_rejects_invalid_suggestion(self) -> None:
        builder = PlanBuilder()
        with self.assertRaises(PlanBuildError):
            builder.build({"suggest_only": True, "suggestion": {"type": "capability"}})

    def test_plan_validator_detects_unknown_capability(self) -> None:
        validator = PlanValidator(self.registry, integration_status_resolver=lambda _: "enabled")
        result = validator.validate(
            {
                "type": "sequence",
                "suggest_only": True,
                "steps": [{"step_id": "step_1", "capability": "unknown_capability", "inputs": {}}],
            }
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any(err["code"] == "capability_not_found" for err in result["errors"]))

    def test_plan_validator_detects_missing_required_inputs(self) -> None:
        validator = PlanValidator(self.registry, integration_status_resolver=lambda _: "enabled")
        result = validator.validate(
            {
                "type": "capability",
                "suggest_only": True,
                "steps": [{"step_id": "step_1", "capability": "read_file", "inputs": {}}],
            }
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any(err["code"] == "missing_required_inputs" for err in result["errors"]))

    def test_plan_validator_checks_integration_enablement(self) -> None:
        def integration_status(integration_id: str) -> str | None:
            if integration_id == "whatsapp_web_connector":
                return "disabled"
            return "enabled"

        validator = PlanValidator(self.registry, integration_status_resolver=integration_status)
        result = validator.validate(
            {
                "type": "capability",
                "suggest_only": True,
                "steps": [
                    {
                        "step_id": "step_1",
                        "capability": "open_whatsapp_web",
                        "inputs": {},
                    }
                ],
            }
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any(err["code"] == "integration_not_enabled" for err in result["errors"]))


if __name__ == "__main__":
    unittest.main()
