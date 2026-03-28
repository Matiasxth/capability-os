"""
Tests for Componente 3 — StrategyOptimizer.

Validates:
  1. No proposals when no suggestions exist.
  2. retry_policy proposal: sequential → retry_policy with max_attempts=3.
  3. retry_policy proposal: already retry_policy → bumps max_attempts.
  4. fallback proposal: adds fallback_steps with last-step retry.
  5. fallback proposal: already has fallback → returned unchanged.
  6. increase_timeout proposal: doubles timeout on the top failing step.
  7. increase_timeout proposal: adds timeout when none exists.
  8. Proposal includes both current and proposed contracts.
  9. Unknown capability in suggestion is skipped (no crash).
  10. Proposed contract is a deep copy (doesn't mutate registry).
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.self_improvement.performance_monitor import PerformanceMonitor
from system.core.self_improvement.strategy_optimizer import StrategyOptimizer

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "strategy_opt"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _mock_monitor(suggestions: list[dict[str, Any]]) -> PerformanceMonitor:
    monitor = MagicMock(spec=PerformanceMonitor)
    monitor.get_improvement_suggestions.return_value = suggestions
    return monitor


def _registry_with_contract(contract: dict[str, Any]) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(contract, source="test")
    return reg


def _minimal_contract(
    capability_id: str = "test_cap",
    mode: str = "sequential",
    steps: list | None = None,
    extra_strategy: dict | None = None,
) -> dict[str, Any]:
    strategy: dict[str, Any] = {
        "mode": mode,
        "steps": steps or [
            {"step_id": "step_a", "action": "filesystem_read_file", "params": {"path": "{{inputs.path}}"}},
        ],
    }
    if extra_strategy:
        strategy.update(extra_strategy)
    return {
        "id": capability_id,
        "name": "Test Cap",
        "domain": "archivos",
        "type": "base",
        "description": "test",
        "inputs": {"path": {"type": "string", "required": True}},
        "outputs": {"content": {"type": "string"}},
        "requirements": {"tools": ["filesystem_read_file"], "capabilities": [], "integrations": []},
        "strategy": strategy,
        "exposure": {"visible_to_user": True, "trigger_phrases": ["test"]},
        "lifecycle": {"version": "1.1.0", "status": "ready"},
    }


def _suggestion(
    capability_id: str = "test_cap",
    suggestion_type: str = "retry_policy",
    failed_steps: dict | None = None,
    error_codes: dict | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "suggestion_type": suggestion_type,
        "reason": "Test reason.",
        "error_rate": 30.0,
        "total_in_window": 10,
        "errors_in_window": 3,
        "failed_steps": failed_steps or {"step_a": 3},
        "error_codes": error_codes or {"tool_execution_error": 3},
    }


# ===========================================================================
# 1. No proposals when healthy
# ===========================================================================

class TestNoProposals(unittest.TestCase):

    def test_no_suggestions_no_proposals(self):
        reg = _registry_with_contract(_minimal_contract())
        optimizer = StrategyOptimizer(_mock_monitor([]), reg)
        self.assertEqual(optimizer.get_optimization_proposals(), [])

    def test_unknown_capability_skipped(self):
        reg = _registry_with_contract(_minimal_contract())
        monitor = _mock_monitor([_suggestion(capability_id="nonexistent_cap")])
        optimizer = StrategyOptimizer(monitor, reg)
        self.assertEqual(optimizer.get_optimization_proposals(), [])


# ===========================================================================
# 2. retry_policy proposals
# ===========================================================================

class TestRetryPolicyProposal(unittest.TestCase):

    def test_sequential_to_retry_policy(self):
        contract = _minimal_contract(mode="sequential")
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="retry_policy")]),
            reg,
        )
        proposals = optimizer.get_optimization_proposals()
        self.assertEqual(len(proposals), 1)
        p = proposals[0]
        self.assertEqual(p["suggestion_type"], "retry_policy")
        proposed = p["proposed_contract"]
        self.assertEqual(proposed["strategy"]["mode"], "retry_policy")
        self.assertEqual(proposed["strategy"]["retry_policy"]["max_attempts"], 3)
        self.assertEqual(proposed["strategy"]["retry_policy"]["backoff_ms"], 1000)

    def test_existing_retry_policy_bumps_attempts(self):
        contract = _minimal_contract(
            mode="retry_policy",
            extra_strategy={"retry_policy": {"max_attempts": 2, "backoff_ms": 500}},
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="retry_policy")]),
            reg,
        )
        proposals = optimizer.get_optimization_proposals()
        proposed = proposals[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["retry_policy"]["max_attempts"], 3)

    def test_retry_policy_caps_at_5(self):
        contract = _minimal_contract(
            mode="retry_policy",
            extra_strategy={"retry_policy": {"max_attempts": 5, "backoff_ms": 500}},
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="retry_policy")]),
            reg,
        )
        proposed = optimizer.get_optimization_proposals()[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["retry_policy"]["max_attempts"], 5)


# ===========================================================================
# 3. fallback proposals
# ===========================================================================

class TestFallbackProposal(unittest.TestCase):

    def test_sequential_to_fallback(self):
        contract = _minimal_contract(
            steps=[
                {"step_id": "step_a", "action": "filesystem_read_file", "params": {"path": "{{inputs.path}}"}},
                {"step_id": "step_b", "action": "filesystem_read_file", "params": {"path": "{{inputs.path}}"}},
            ],
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="fallback")]),
            reg,
        )
        proposals = optimizer.get_optimization_proposals()
        proposed = proposals[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["mode"], "fallback")
        self.assertIn("fallback_steps", proposed["strategy"])
        fallback = proposed["strategy"]["fallback_steps"]
        self.assertEqual(len(fallback), 1)
        self.assertEqual(fallback[0]["step_id"], "step_b_fallback")

    def test_existing_fallback_returned_unchanged(self):
        contract = _minimal_contract(
            mode="fallback",
            extra_strategy={"fallback_steps": [
                {"step_id": "fb", "action": "filesystem_read_file", "params": {"path": "{{inputs.path}}"}},
            ]},
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="fallback")]),
            reg,
        )
        proposed = optimizer.get_optimization_proposals()[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["fallback_steps"][0]["step_id"], "fb")


# ===========================================================================
# 4. increase_timeout proposals
# ===========================================================================

class TestIncreaseTimeoutProposal(unittest.TestCase):

    def test_doubles_existing_timeout(self):
        contract = _minimal_contract(
            steps=[
                {"step_id": "step_a", "action": "filesystem_read_file",
                 "params": {"path": "{{inputs.path}}", "timeout_ms": 15000}},
            ],
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(
                suggestion_type="increase_timeout",
                failed_steps={"step_a": 3},
            )]),
            reg,
        )
        proposed = optimizer.get_optimization_proposals()[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["steps"][0]["params"]["timeout_ms"], 30000)

    def test_adds_timeout_when_missing(self):
        contract = _minimal_contract()
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(
                suggestion_type="increase_timeout",
                failed_steps={"step_a": 3},
            )]),
            reg,
        )
        proposed = optimizer.get_optimization_proposals()[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["steps"][0]["params"]["timeout_ms"], 60000)

    def test_caps_at_120000(self):
        contract = _minimal_contract(
            steps=[
                {"step_id": "step_a", "action": "filesystem_read_file",
                 "params": {"path": "{{inputs.path}}", "timeout_ms": 100000}},
            ],
        )
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(
                suggestion_type="increase_timeout",
                failed_steps={"step_a": 3},
            )]),
            reg,
        )
        proposed = optimizer.get_optimization_proposals()[0]["proposed_contract"]
        self.assertEqual(proposed["strategy"]["steps"][0]["params"]["timeout_ms"], 120000)


# ===========================================================================
# 5. Proposal metadata
# ===========================================================================

class TestProposalMetadata(unittest.TestCase):

    def test_includes_all_fields(self):
        contract = _minimal_contract()
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion()]),
            reg,
        )
        p = optimizer.get_optimization_proposals()[0]
        for key in ("id", "capability_id", "suggestion_type", "reason",
                     "error_rate", "current_contract", "proposed_contract"):
            self.assertIn(key, p, f"Missing key: {key}")

    def test_current_contract_is_deep_copy(self):
        contract = _minimal_contract()
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion()]),
            reg,
        )
        p = optimizer.get_optimization_proposals()[0]
        # Mutating the proposal's current_contract must not affect the registry
        p["current_contract"]["id"] = "mutated"
        self.assertEqual(reg.get("test_cap")["id"], "test_cap")

    def test_proposed_contract_differs_from_current(self):
        contract = _minimal_contract()
        reg = _registry_with_contract(contract)
        optimizer = StrategyOptimizer(
            _mock_monitor([_suggestion(suggestion_type="retry_policy")]),
            reg,
        )
        p = optimizer.get_optimization_proposals()[0]
        self.assertNotEqual(
            p["current_contract"]["strategy"]["mode"],
            p["proposed_contract"]["strategy"]["mode"],
        )


if __name__ == "__main__":
    unittest.main()
