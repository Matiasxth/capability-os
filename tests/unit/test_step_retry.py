"""Tests for per-step retry in CapabilityEngine."""

import pytest
from unittest.mock import MagicMock, patch
from system.core.capability_engine.capability_engine import CapabilityEngine, CapabilityExecutionError


def _make_engine(tool_results):
    """Create a CapabilityEngine with a mock ToolRuntime that returns sequential results."""
    registry = MagicMock()
    registry.validate_contract.return_value = "test_cap"

    runtime = MagicMock()
    call_count = [0]
    def execute(action, params):
        idx = call_count[0]
        call_count[0] += 1
        result = tool_results[idx] if idx < len(tool_results) else tool_results[-1]
        if isinstance(result, Exception):
            raise result
        return result
    runtime.execute.side_effect = execute

    return CapabilityEngine(capability_registry=registry, tool_runtime=runtime)


def _contract(steps):
    return {
        "id": "test_cap",
        "inputs": {"x": {"type": "string", "required": True}},
        "outputs": {},
        "strategy": {"mode": "sequential", "steps": steps},
    }


class TestStepRetry:
    def test_no_retry_by_default(self):
        engine = _make_engine([RuntimeError("fail")])
        contract = _contract([{"step_id": "s1", "action": "tool_a", "params": {}}])
        with pytest.raises(CapabilityExecutionError):
            engine.execute(contract, {"x": "test"})

    def test_retry_succeeds_on_second_attempt(self):
        engine = _make_engine([
            RuntimeError("transient"),  # attempt 1: fail
            {"status": "ok"},           # attempt 2: success
        ])
        contract = _contract([{
            "step_id": "s1",
            "action": "tool_a",
            "params": {},
            "retry": {"max_attempts": 3, "backoff_ms": 0},
        }])
        result = engine.execute(contract, {"x": "test"})
        assert result["status"] == "success"

    def test_retry_exhausts_all_attempts(self):
        engine = _make_engine([
            RuntimeError("fail1"),
            RuntimeError("fail2"),
            RuntimeError("fail3"),
        ])
        contract = _contract([{
            "step_id": "s1",
            "action": "tool_a",
            "params": {},
            "retry": {"max_attempts": 3, "backoff_ms": 0},
        }])
        with pytest.raises(CapabilityExecutionError) as exc_info:
            engine.execute(contract, {"x": "test"})
        assert "fail3" in str(exc_info.value)

    def test_retry_only_retries_failing_step(self):
        engine = _make_engine([
            {"status": "ok"},           # s1: success
            RuntimeError("transient"),  # s2 attempt 1: fail
            {"status": "ok"},           # s2 attempt 2: success
        ])
        contract = _contract([
            {"step_id": "s1", "action": "tool_a", "params": {}},
            {"step_id": "s2", "action": "tool_b", "params": {},
             "retry": {"max_attempts": 2, "backoff_ms": 0}},
        ])
        result = engine.execute(contract, {"x": "test"})
        assert result["status"] == "success"

    @patch("system.core.capability_engine.capability_engine.time.sleep")
    def test_retry_with_backoff(self, mock_sleep):
        engine = _make_engine([
            RuntimeError("fail"),
            {"status": "ok"},
        ])
        contract = _contract([{
            "step_id": "s1",
            "action": "tool_a",
            "params": {},
            "retry": {"max_attempts": 2, "backoff_ms": 100},
        }])
        result = engine.execute(contract, {"x": "test"})
        assert result["status"] == "success"
        # Should have called sleep for backoff
        assert mock_sleep.called

    def test_step_without_retry_fails_immediately(self):
        engine = _make_engine([
            {"status": "ok"},           # s1: success
            RuntimeError("fatal"),      # s2: fail (no retry)
        ])
        contract = _contract([
            {"step_id": "s1", "action": "tool_a", "params": {}},
            {"step_id": "s2", "action": "tool_b", "params": {}},
        ])
        with pytest.raises(CapabilityExecutionError):
            engine.execute(contract, {"x": "test"})
