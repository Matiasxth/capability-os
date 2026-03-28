"""Generates proposed contract improvements for capabilities with recurring failures.

Reads improvement suggestions from PerformanceMonitor, looks up the current
capability contract, and produces a **proposed** modified contract with an
improved strategy (retry_policy or fallback) targeting the problematic step.

Spec section 14 rule: proposals are **never applied** automatically.
The user must explicitly approve each one via the Approval API.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from system.capabilities.registry import CapabilityRegistry
from system.core.self_improvement.performance_monitor import PerformanceMonitor


class StrategyOptimizer:
    """Generates optimization proposals from PerformanceMonitor suggestions."""

    def __init__(
        self,
        performance_monitor: PerformanceMonitor,
        capability_registry: CapabilityRegistry,
    ):
        self._monitor = performance_monitor
        self._registry = capability_registry

    def get_optimization_proposals(self) -> list[dict[str, Any]]:
        """Return proposals for each capability with an active improvement suggestion.

        Each proposal contains:
          - id:                 unique proposal identifier
          - capability_id:      target capability
          - current_contract:   the live contract (read-only snapshot)
          - proposed_contract:  the improved contract (not yet applied)
          - reason:             human-readable explanation
          - suggestion_type:    retry_policy | fallback | increase_timeout
        """
        suggestions = self._monitor.get_improvement_suggestions()
        proposals: list[dict[str, Any]] = []

        for suggestion in suggestions:
            capability_id = suggestion["capability_id"]
            contract = self._registry.get(capability_id)
            if contract is None:
                continue

            proposed = self._build_proposed_contract(contract, suggestion)
            if proposed is None:
                continue

            proposals.append({
                "id": f"opt_{uuid4().hex[:8]}",
                "capability_id": capability_id,
                "suggestion_type": suggestion["suggestion_type"],
                "reason": suggestion["reason"],
                "error_rate": suggestion["error_rate"],
                "current_contract": deepcopy(contract),
                "proposed_contract": proposed,
            })

        return proposals

    # ------------------------------------------------------------------
    # Proposal builders
    # ------------------------------------------------------------------

    def _build_proposed_contract(
        self,
        contract: dict[str, Any],
        suggestion: dict[str, Any],
    ) -> dict[str, Any] | None:
        suggestion_type = suggestion["suggestion_type"]
        if suggestion_type == "retry_policy":
            return self._propose_retry_policy(contract, suggestion)
        if suggestion_type == "fallback":
            return self._propose_fallback(contract, suggestion)
        if suggestion_type == "increase_timeout":
            return self._propose_increased_timeout(contract, suggestion)
        return None

    @staticmethod
    def _propose_retry_policy(
        contract: dict[str, Any],
        suggestion: dict[str, Any],
    ) -> dict[str, Any]:
        proposed = deepcopy(contract)
        strategy = proposed["strategy"]

        # If already retry_policy, just bump max_attempts
        if strategy.get("mode") == "retry_policy":
            existing = strategy.get("retry_policy", {})
            existing["max_attempts"] = min(
                (existing.get("max_attempts", 1) + 1), 5,
            )
            strategy["retry_policy"] = existing
            return proposed

        # Convert sequential/conditional → retry_policy with original steps
        strategy["mode"] = "retry_policy"
        strategy["retry_policy"] = {
            "max_attempts": 3,
            "backoff_ms": 1000,
        }
        return proposed

    @staticmethod
    def _propose_fallback(
        contract: dict[str, Any],
        suggestion: dict[str, Any],
    ) -> dict[str, Any]:
        proposed = deepcopy(contract)
        strategy = proposed["strategy"]

        if strategy.get("mode") == "fallback" and strategy.get("fallback_steps"):
            return proposed  # already has fallback

        # Keep primary steps, add minimal fallback
        primary_steps = strategy.get("steps", [])
        if not primary_steps:
            return proposed

        # Fallback: re-run the last step only (a lightweight retry of the final action)
        last_step = deepcopy(primary_steps[-1])
        last_step["step_id"] = f"{last_step['step_id']}_fallback"

        strategy["mode"] = "fallback"
        strategy["fallback_steps"] = [last_step]
        return proposed

    @staticmethod
    def _propose_increased_timeout(
        contract: dict[str, Any],
        suggestion: dict[str, Any],
    ) -> dict[str, Any]:
        proposed = deepcopy(contract)
        steps = proposed["strategy"].get("steps", [])

        # Find the step that fails most and double its timeout (via params)
        top_step_id = None
        failed_steps = suggestion.get("failed_steps", {})
        if failed_steps:
            top_step_id = max(failed_steps, key=failed_steps.get)

        for step in steps:
            if top_step_id and step.get("step_id") != top_step_id:
                continue
            params = step.get("params", {})
            current_timeout = params.get("timeout_ms")
            if isinstance(current_timeout, int) and current_timeout > 0:
                params["timeout_ms"] = min(current_timeout * 2, 120000)
            else:
                params["timeout_ms"] = 60000
            step["params"] = params
            break  # only the top failing step

        return proposed
