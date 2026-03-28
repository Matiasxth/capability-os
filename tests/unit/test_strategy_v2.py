"""
Tests for Bloque 3 — Strategy v2: conditional, retry_policy, fallback.

Validates:
  1. condition_evaluator: truthy, ==, !=, >, <, >=, <=, error cases.
  2. conditional mode: steps skipped when condition is false.
  3. retry_policy mode: retries on failure, respects max_attempts, updates retry_count.
  4. fallback mode: runs fallback_steps when primary fails.
  5. Schema validation: new fields accepted; invalid variables in conditions rejected.
  6. Backward-compatibility: sequential mode still works identically.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import (
    CapabilityEngine,
    CapabilityExecutionError,
    CapabilityInputError,
)
from system.core.state import StateManager
from system.core.strategy.condition_evaluator import ConditionError, evaluate_condition
from system.shared.schema_validation import SchemaValidationError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------------------
# Helpers: build engine with stub tools
# ---------------------------------------------------------------------------

_STUB_TOOL = {
    "id": "execution_run_command",
    "name": "stub",
    "category": "execution",
    "description": "stub",
    "inputs": {"command": {"type": "string", "required": True}},
    "outputs": {"stdout": {"type": "string"}, "exit_code": {"type": "integer"}},
    "constraints": {"timeout_ms": 5000, "allowlist": [], "workspace_only": False},
    "safety": {"level": "low", "requires_confirmation": False},
    "lifecycle": {"version": "1.1.0", "status": "ready"},
}


def _base_contract(mode: str, steps: list, **extra) -> dict:
    """Build a minimal valid capability contract with the given strategy."""
    c = {
        "id": "test_capability",
        "name": "Test",
        "domain": "ejecucion",
        "type": "base",
        "description": "Test",
        "inputs": {
            "command": {"type": "string", "required": True},
        },
        "outputs": {"stdout": {"type": "string"}},
        "requirements": {"tools": ["execution_run_command"], "capabilities": [], "integrations": []},
        "strategy": {"mode": mode, "steps": steps, **extra},
        "exposure": {"visible_to_user": True, "trigger_phrases": ["test"]},
        "lifecycle": {"version": "1.1.0", "status": "ready"},
    }
    return c


def _build_engine(handler_fn=None, fail_after: int = -1):
    """Build an engine with a single stub tool.

    If *fail_after* >= 0, the handler will succeed *fail_after* times then raise.
    """
    cap_reg = CapabilityRegistry()
    tool_reg = ToolRegistry()
    tool_reg.register(_STUB_TOOL, source="stub")

    call_counter = {"n": 0}

    def _default_handler(params):
        call_counter["n"] += 1
        if 0 <= fail_after < call_counter["n"]:
            raise RuntimeError(f"Intentional failure on call #{call_counter['n']}")
        cmd = params.get("command", "")
        return {"stdout": f"ran: {cmd}", "exit_code": 0}

    handler = handler_fn or _default_handler
    runtime = ToolRuntime(tool_reg)
    runtime.register_stub("execution_run_command", handler)
    engine = CapabilityEngine(cap_reg, runtime)
    return engine, cap_reg, call_counter


# ===========================================================================
# 1. condition_evaluator unit tests
# ===========================================================================

class TestConditionEvaluator(unittest.TestCase):

    def _sm(self, inputs: dict | None = None, step_outputs: dict | None = None) -> StateManager:
        sm = StateManager(inputs or {})
        if step_outputs:
            for step_id, output in step_outputs.items():
                sm.record_step_output(step_id, output)
        return sm

    # --- truthy ---
    def test_truthy_string(self):
        self.assertTrue(evaluate_condition("{{inputs.name}}", self._sm({"name": "hello"})))

    def test_truthy_empty_string_false(self):
        self.assertFalse(evaluate_condition("{{inputs.name}}", self._sm({"name": ""})))

    def test_truthy_zero_false(self):
        self.assertFalse(evaluate_condition("{{inputs.val}}", self._sm({"val": 0})))

    def test_truthy_none_false(self):
        self.assertFalse(evaluate_condition("{{inputs.val}}", self._sm({"val": None})))

    def test_truthy_positive_int(self):
        self.assertTrue(evaluate_condition("{{inputs.val}}", self._sm({"val": 42})))

    # --- == / != ---
    def test_eq_int(self):
        sm = self._sm(step_outputs={"build": {"exit_code": 0}})
        self.assertTrue(evaluate_condition("{{steps.build.outputs.exit_code}} == 0", sm))

    def test_eq_int_false(self):
        sm = self._sm(step_outputs={"build": {"exit_code": 1}})
        self.assertFalse(evaluate_condition("{{steps.build.outputs.exit_code}} == 0", sm))

    def test_neq(self):
        sm = self._sm(step_outputs={"build": {"exit_code": 1}})
        self.assertTrue(evaluate_condition("{{steps.build.outputs.exit_code}} != 0", sm))

    def test_eq_string(self):
        sm = self._sm({"mode": "debug"})
        self.assertTrue(evaluate_condition('{{inputs.mode}} == "debug"', sm))

    def test_eq_bool_true(self):
        sm = self._sm({"flag": True})
        self.assertTrue(evaluate_condition("{{inputs.flag}} == true", sm))

    def test_eq_bool_false(self):
        sm = self._sm({"flag": False})
        self.assertTrue(evaluate_condition("{{inputs.flag}} == false", sm))

    def test_eq_null(self):
        sm = self._sm({"val": None})
        self.assertTrue(evaluate_condition("{{inputs.val}} == null", sm))

    # --- numeric comparisons ---
    def test_greater_than(self):
        sm = self._sm({"val": 10})
        self.assertTrue(evaluate_condition("{{inputs.val}} > 5", sm))
        self.assertFalse(evaluate_condition("{{inputs.val}} > 15", sm))

    def test_less_than(self):
        sm = self._sm({"val": 3})
        self.assertTrue(evaluate_condition("{{inputs.val}} < 5", sm))

    def test_gte(self):
        sm = self._sm({"val": 5})
        self.assertTrue(evaluate_condition("{{inputs.val}} >= 5", sm))

    def test_lte(self):
        sm = self._sm({"val": 5})
        self.assertTrue(evaluate_condition("{{inputs.val}} <= 5", sm))

    # --- error cases ---
    def test_empty_condition_raises(self):
        with self.assertRaises(ConditionError):
            evaluate_condition("", self._sm())

    def test_malformed_condition_raises(self):
        with self.assertRaises(ConditionError):
            evaluate_condition("this is not valid", self._sm())

    def test_non_numeric_comparison_raises(self):
        sm = self._sm({"val": "not_a_number"})
        with self.assertRaises(ConditionError):
            evaluate_condition("{{inputs.val}} > 5", sm)


# ===========================================================================
# 2. conditional mode — engine integration
# ===========================================================================

class TestConditionalStrategy(unittest.TestCase):

    def test_all_steps_when_conditions_true(self):
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_a",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
                "condition": "{{inputs.command}}",
            },
        ])
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "hello"})
        self.assertEqual(result["status"], "success")
        self.assertIn("step_a", result["step_outputs"])

    def test_step_skipped_when_condition_false(self):
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_a",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
                "condition": "{{inputs.command}}",  # empty => falsy
            },
        ])
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": ""})
        self.assertEqual(result["status"], "success")
        self.assertNotIn("step_a", result["step_outputs"])

    def test_mixed_conditions(self):
        """Step A always runs (no condition), Step B skipped (false condition)."""
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_always",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
            },
            {
                "step_id": "step_conditional",
                "action": "execution_run_command",
                "params": {"command": "second"},
                "condition": "{{steps.step_always.outputs.exit_code}} != 0",
            },
        ])
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertIn("step_always", result["step_outputs"])
        # exit_code is 0, so condition "!= 0" is false → skipped
        self.assertNotIn("step_conditional", result["step_outputs"])

    def test_condition_with_step_output_comparison(self):
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_a",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
            },
            {
                "step_id": "step_b",
                "action": "execution_run_command",
                "params": {"command": "follow-up"},
                "condition": "{{steps.step_a.outputs.exit_code}} == 0",
            },
        ])
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertIn("step_b", result["step_outputs"])


# ===========================================================================
# 3. retry_policy mode
# ===========================================================================

class TestRetryPolicyStrategy(unittest.TestCase):

    def test_succeeds_on_first_attempt(self):
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract(
            "retry_policy",
            [{"step_id": "step_a", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            retry_policy={"max_attempts": 3, "backoff_ms": 0},
        )
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(counter["n"], 1)
        self.assertEqual(result["runtime"]["retry_count"], 0)

    def test_retries_on_failure_and_succeeds(self):
        """Fails once, then succeeds on second attempt."""
        call_count = {"n": 0}

        def flaky_handler(params):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            return {"stdout": "ok", "exit_code": 0}

        engine, cap_reg, _ = _build_engine(handler_fn=flaky_handler)
        contract = _base_contract(
            "retry_policy",
            [{"step_id": "step_a", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            retry_policy={"max_attempts": 3, "backoff_ms": 0},
        )
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(call_count["n"], 2)
        self.assertEqual(result["runtime"]["retry_count"], 1)

    def test_exhausts_retries_and_fails(self):
        engine, cap_reg, counter = _build_engine(fail_after=0)
        contract = _base_contract(
            "retry_policy",
            [{"step_id": "step_a", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            retry_policy={"max_attempts": 2, "backoff_ms": 0},
        )
        cap_reg.register(contract, source="test")
        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(contract, {"command": "go"})
        self.assertEqual(ctx.exception.runtime_model["status"], "error")
        self.assertEqual(counter["n"], 2)

    def test_retry_count_in_runtime_model(self):
        """After exhausting attempts, retry_count reflects the last attempt index."""
        engine, cap_reg, _ = _build_engine(fail_after=0)
        contract = _base_contract(
            "retry_policy",
            [{"step_id": "step_a", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            retry_policy={"max_attempts": 3, "backoff_ms": 0},
        )
        cap_reg.register(contract, source="test")
        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(contract, {"command": "go"})
        self.assertEqual(ctx.exception.runtime_model["retry_count"], 2)


# ===========================================================================
# 4. fallback mode
# ===========================================================================

class TestFallbackStrategy(unittest.TestCase):

    def test_primary_succeeds_no_fallback(self):
        engine, cap_reg, counter = _build_engine()
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "fallback_cmd"}},
            ],
        )
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertIn("primary", result["step_outputs"])
        self.assertNotIn("fallback", result["step_outputs"])
        self.assertEqual(counter["n"], 1)

    def test_primary_fails_fallback_succeeds(self):
        call_count = {"n": 0}

        def primary_fail_handler(params):
            call_count["n"] += 1
            cmd = params.get("command", "")
            if cmd == "will_fail":
                raise RuntimeError("primary failure")
            return {"stdout": f"ran: {cmd}", "exit_code": 0}

        engine, cap_reg, _ = _build_engine(handler_fn=primary_fail_handler)
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "will_fail"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "safe_cmd"}},
            ],
        )
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "irrelevant"})
        self.assertEqual(result["status"], "success")
        self.assertIn("fallback", result["step_outputs"])
        self.assertNotIn("primary", result["step_outputs"])  # reset between

    def test_both_fail_raises(self):
        engine, cap_reg, _ = _build_engine(fail_after=0)
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "also_fails"}},
            ],
        )
        cap_reg.register(contract, source="test")
        with self.assertRaises(CapabilityExecutionError):
            engine.execute(contract, {"command": "go"})

    def test_no_fallback_steps_raises_on_failure(self):
        engine, cap_reg, _ = _build_engine(fail_after=0)
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
        )
        cap_reg.register(contract, source="test")
        with self.assertRaises(CapabilityExecutionError):
            engine.execute(contract, {"command": "go"})

    def test_fallback_logs_contain_primary_failure(self):
        """Ensure the observation log records the primary step failure."""
        call_count = {"n": 0}

        def primary_fail(params):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom")
            return {"stdout": "ok", "exit_code": 0}

        engine, cap_reg, _ = _build_engine(handler_fn=primary_fail)
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "safe"}},
            ],
        )
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        events = [e["event"] for e in result["runtime"]["logs"]]
        self.assertIn("step_failed", events)
        self.assertIn("step_succeeded", events)


# ===========================================================================
# 5. Schema validation — new fields
# ===========================================================================

class TestSchemaValidation(unittest.TestCase):

    def test_condition_field_accepted(self):
        registry = CapabilityRegistry()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_a",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
                "condition": "{{inputs.command}}",
            },
        ])
        registry.register(contract, source="test")

    def test_retry_policy_field_accepted(self):
        registry = CapabilityRegistry()
        contract = _base_contract(
            "retry_policy",
            [{"step_id": "step_a", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            retry_policy={"max_attempts": 3, "backoff_ms": 100},
        )
        registry.register(contract, source="test")

    def test_fallback_steps_field_accepted(self):
        registry = CapabilityRegistry()
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "safe"}},
            ],
        )
        registry.register(contract, source="test")

    def test_invalid_variable_in_condition_rejected(self):
        registry = CapabilityRegistry()
        contract = _base_contract("conditional", [
            {
                "step_id": "step_a",
                "action": "execution_run_command",
                "params": {"command": "{{inputs.command}}"},
                "condition": "{{implicit_var}} == 1",
            },
        ])
        with self.assertRaises(SchemaValidationError):
            registry.register(contract, source="test")

    def test_invalid_variable_in_fallback_steps_rejected(self):
        registry = CapabilityRegistry()
        contract = _base_contract(
            "fallback",
            [{"step_id": "primary", "action": "execution_run_command",
              "params": {"command": "{{inputs.command}}"}}],
            fallback_steps=[
                {"step_id": "fallback", "action": "execution_run_command",
                 "params": {"command": "{{implicit_var}}"}},
            ],
        )
        with self.assertRaises(SchemaValidationError):
            registry.register(contract, source="test")


# ===========================================================================
# 6. Backward-compatibility: sequential still works
# ===========================================================================

class TestSequentialBackwardCompat(unittest.TestCase):

    def test_sequential_unchanged(self):
        engine, cap_reg, _ = _build_engine()
        contract = _base_contract("sequential", [
            {"step_id": "step_a", "action": "execution_run_command",
             "params": {"command": "{{inputs.command}}"}},
        ])
        cap_reg.register(contract, source="test")
        result = engine.execute(contract, {"command": "go"})
        self.assertEqual(result["status"], "success")
        self.assertIn("step_a", result["step_outputs"])

    def test_unsupported_mode_raises(self):
        engine, cap_reg, _ = _build_engine()
        contract = _base_contract("unknown_mode", [
            {"step_id": "step_a", "action": "execution_run_command",
             "params": {"command": "x"}},
        ])
        # The schema rejects unknown modes, but if somehow bypassed:
        with self.assertRaises(SchemaValidationError):
            cap_reg.register(contract, source="test")


if __name__ == "__main__":
    unittest.main()
