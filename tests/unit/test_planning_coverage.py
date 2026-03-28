"""
Additional tests for PlanBuilder and PlanValidator to push core coverage ≥80%.

Covers all uncovered branches identified in coverage report.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.planning import PlanBuildError, PlanBuilder, PlanValidator

ROOT = Path(__file__).resolve().parents[2]


def _registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    return reg


# ===========================================================================
# PlanBuilder — cover all missing branches
# ===========================================================================

class TestPlanBuilderFull(unittest.TestCase):

    def setUp(self):
        self.builder = PlanBuilder()

    # --- error branches ---

    def test_non_dict_interpretation_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build("not_a_dict")

    def test_non_dict_suggestion_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": "not_a_dict"})

    def test_invalid_suggestion_type_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "invalid_type"}})

    def test_missing_capability_in_capability_suggestion_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "capability", "capability": ""}})

    def test_non_dict_inputs_in_capability_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "capability", "capability": "read_file", "inputs": "bad"}})

    def test_non_list_steps_in_sequence_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "sequence", "steps": "not_list"}})

    def test_non_dict_step_in_sequence_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "sequence", "steps": ["not_dict"]}})

    def test_missing_capability_in_sequence_step_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "sequence", "steps": [{"capability": ""}]}})

    def test_non_dict_inputs_in_sequence_step_raises(self):
        with self.assertRaises(PlanBuildError):
            self.builder.build({"suggestion": {"type": "sequence", "steps": [
                {"capability": "read_file", "inputs": 123}
            ]}})

    # --- success branches ---

    def test_unknown_type_returns_empty_steps(self):
        plan = self.builder.build({"suggestion": {"type": "unknown"}})
        self.assertEqual(plan["type"], "unknown")
        self.assertEqual(plan["steps"], [])

    def test_non_bool_suggest_only_defaults_to_true(self):
        plan = self.builder.build({
            "suggest_only": "not_bool",
            "suggestion": {"type": "unknown"},
        })
        self.assertTrue(plan["suggest_only"])

    def test_none_inputs_normalized_to_empty_dict(self):
        plan = self.builder.build({
            "suggestion": {"type": "capability", "capability": "read_file", "inputs": None},
        })
        self.assertEqual(plan["steps"][0]["inputs"], {})

    def test_capability_with_suggest_only_false(self):
        plan = self.builder.build({
            "suggest_only": False,
            "suggestion": {"type": "capability", "capability": "read_file", "inputs": {"path": "x"}},
        })
        self.assertFalse(plan["suggest_only"])

    def test_sequence_with_multiple_steps(self):
        plan = self.builder.build({
            "suggestion": {
                "type": "sequence",
                "steps": [
                    {"capability": "read_file", "inputs": {"path": "a.txt"}},
                    {"step_id": "custom_id", "capability": "write_file", "inputs": {"path": "b.txt", "content": "x"}},
                ],
            },
        })
        self.assertEqual(plan["type"], "sequence")
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][0]["step_id"], "step_1")
        self.assertEqual(plan["steps"][1]["step_id"], "custom_id")

    def test_sequence_step_with_none_inputs(self):
        plan = self.builder.build({
            "suggestion": {
                "type": "sequence",
                "steps": [
                    {"capability": "list_processes", "inputs": None},
                ],
            },
        })
        self.assertEqual(plan["steps"][0]["inputs"], {})

    def test_sequence_step_auto_generates_step_id(self):
        plan = self.builder.build({
            "suggestion": {
                "type": "sequence",
                "steps": [{"capability": "read_file", "inputs": {"path": "x"}}],
            },
        })
        self.assertEqual(plan["steps"][0]["step_id"], "step_1")


# ===========================================================================
# PlanValidator — cover all missing branches
# ===========================================================================

class TestPlanValidatorFull(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def _validator(self, int_resolver=None):
        return PlanValidator(self.registry, integration_status_resolver=int_resolver)

    # --- structural errors ---

    def test_non_dict_plan_returns_invalid(self):
        result = self._validator().validate("not_dict")
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "invalid_plan")

    def test_invalid_plan_type_returns_invalid(self):
        result = self._validator().validate({"type": "bad_type", "steps": []})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "invalid_plan_type")

    def test_unknown_type_returns_error(self):
        result = self._validator().validate({"type": "unknown", "steps": []})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "unknown_intent")

    def test_empty_steps_returns_error(self):
        result = self._validator().validate({"type": "capability", "steps": []})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "missing_steps")

    def test_non_list_steps_returns_error(self):
        result = self._validator().validate({"type": "capability", "steps": "bad"})
        self.assertFalse(result["valid"])

    def test_non_dict_step_returns_error(self):
        result = self._validator().validate({"type": "capability", "steps": ["not_dict"]})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "invalid_step")

    def test_missing_step_id_returns_error(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"capability": "read_file", "inputs": {"path": "x"}}],
        })
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "missing_step_id")

    def test_duplicate_step_id_returns_error(self):
        result = self._validator().validate({
            "type": "sequence",
            "steps": [
                {"step_id": "step_1", "capability": "read_file", "inputs": {"path": "a"}},
                {"step_id": "step_1", "capability": "read_file", "inputs": {"path": "b"}},
            ],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "duplicate_step_id" for e in result["errors"]))

    def test_invalid_step_id_pattern_returns_error(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "123_bad", "capability": "read_file", "inputs": {"path": "x"}}],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "invalid_step_id" for e in result["errors"]))

    def test_missing_capability_in_step_returns_error(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "", "inputs": {}}],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "missing_capability" for e in result["errors"]))

    def test_none_inputs_coerced_to_dict(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "list_processes", "inputs": None}],
        })
        # list_processes has no required inputs, so should pass
        self.assertTrue(result["valid"])

    def test_non_dict_inputs_returns_error(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "read_file", "inputs": "bad"}],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "invalid_inputs" for e in result["errors"]))

    def test_unknown_input_fields_reported(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "read_file",
                       "inputs": {"path": "x", "nonexistent_field": "y"}}],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "unknown_input_fields" for e in result["errors"]))

    def test_valid_plan_passes(self):
        result = self._validator().validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "read_file",
                       "inputs": {"path": "demo.txt"}}],
        })
        self.assertTrue(result["valid"])

    def test_no_integration_resolver_skips_integration_check(self):
        # No integration_status_resolver → integrations not checked
        result = self._validator(int_resolver=None).validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "open_whatsapp_web", "inputs": {}}],
        })
        # Valid because integration check is skipped
        self.assertTrue(result["valid"])

    def test_integration_resolver_returns_none_for_unknown(self):
        result = self._validator(int_resolver=lambda _: None).validate({
            "type": "capability",
            "steps": [{"step_id": "step_a", "capability": "open_whatsapp_web", "inputs": {}}],
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "integration_not_enabled" for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
