from __future__ import annotations

import random
import time
from copy import deepcopy
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.observation import ObservationLogger
from system.core.state import StateManager, VariableResolutionError
from system.core.strategy import ConditionError, evaluate_condition
from system.shared.schema_validation import SchemaValidationError
from system.tools.runtime import ToolExecutionError, ToolRuntime


class CapabilityEngineError(RuntimeError):
    """Base exception for capability engine failures."""


class CapabilityInputError(CapabilityEngineError):
    """Raised when required inputs are missing."""


class CapabilityExecutionError(CapabilityEngineError):
    """Raised when execution fails after runtime initialization."""

    def __init__(self, message: str, runtime_model: dict[str, Any], error_code: str):
        super().__init__(message)
        self.runtime_model = runtime_model
        self.error_code = error_code


class CapabilityEngine:
    """Capability engine supporting sequential, conditional, retry_policy and fallback strategies."""

    SUPPORTED_MODES = {"sequential", "conditional", "retry_policy", "fallback"}

    def __init__(self, capability_registry: CapabilityRegistry, tool_runtime: ToolRuntime, metrics_collector: Any = None, execution_history: Any = None, semantic_memory: Any = None):
        self.capability_registry = capability_registry
        self.tool_runtime = tool_runtime
        self.metrics_collector = metrics_collector
        self.execution_history = execution_history
        self.semantic_memory = semantic_memory

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, capability_contract: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        contract_id = self.capability_registry.validate_contract(capability_contract, source="capability_engine")
        self._validate_required_inputs(capability_contract, inputs)
        normalized_inputs = self._normalize_inputs(capability_contract, inputs)

        strategy = capability_contract.get("strategy", {})
        mode = strategy.get("mode")
        if mode not in self.SUPPORTED_MODES:
            raise CapabilityInputError(f"Unsupported strategy mode '{mode}'.")

        logger = ObservationLogger(metrics_collector=self.metrics_collector, execution_history=self.execution_history, semantic_memory=self.semantic_memory)
        logger.initialize(contract_id)
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_manager = StateManager(normalized_inputs)
        state_manager.set_runtime_provider(logger.get_runtime_model)

        # Inject relevant memories into state (Rule 5: never block)
        try:
            if self.semantic_memory is not None:
                intent_text = " ".join(str(v) for v in normalized_inputs.values() if v)
                if intent_text.strip():
                    hits = self.semantic_memory.recall_semantic(intent_text, top_k=3)
                    if hits:
                        state_manager.update_state({
                            "relevant_memories": [
                                {"text": h.get("text", ""), "score": h.get("score", 0), "type": h.get("memory", {}).get("memory_type", "")}
                                for h in hits
                            ]
                        })
        except Exception:
            pass

        # Mutable ref so strategy interpreters can update the "current step" for
        # the outer error handler.  Index 0 = current step id.
        step_ref: list[str | None] = [None]

        try:
            if mode == "sequential":
                final_output = self._run_steps_sequential(
                    strategy.get("steps", []), state_manager, logger, step_ref,
                )
            elif mode == "conditional":
                final_output = self._run_conditional(
                    strategy, state_manager, logger, step_ref,
                )
            elif mode == "retry_policy":
                final_output = self._run_retry_policy(
                    strategy, state_manager, logger, step_ref,
                )
            elif mode == "fallback":
                final_output = self._run_fallback(
                    strategy, state_manager, logger, step_ref,
                )
            else:
                raise CapabilityInputError(f"Unsupported strategy mode '{mode}'.")

            runtime_model = logger.finish(
                status="ready",
                final_output=final_output,
                state_snapshot=state_manager.state,
            )
            return {
                "execution_id": runtime_model["execution_id"],
                "capability_id": contract_id,
                "status": "success",
                "final_output": deepcopy(runtime_model["final_output"]),
                "runtime": runtime_model,
                "step_outputs": deepcopy(state_manager.step_outputs),
            }

        except Exception as exc:
            error_code = self._error_code_from_exception(exc)
            message = str(exc)

            if step_ref[0] is not None:
                logger.mark_step_failed(step_ref[0], error_code, message, state_manager.state)

            runtime_model = logger.finish(
                status="error",
                final_output={},
                state_snapshot=state_manager.state,
                error_code=error_code,
                error_message=message,
                failed_step=step_ref[0],
            )
            raise CapabilityExecutionError(message, runtime_model, error_code) from exc

    # ------------------------------------------------------------------
    # Shared step execution
    # ------------------------------------------------------------------

    def _run_single_step(
        self,
        step: dict[str, Any],
        state_manager: StateManager,
        logger: ObservationLogger,
        step_ref: list[str | None],
    ) -> dict[str, Any]:
        """Execute one strategy step with optional per-step retry.

        Steps can declare ``"retry": {"max_attempts": 3, "backoff_ms": 500}``
        for exponential backoff with jitter on failure.
        Does NOT log failures — caller is responsible.
        """
        step_id = step.get("step_id")
        if not step_id:
            raise SchemaValidationError("Strategy steps require 'step_id'.")

        action = step.get("action")
        if not isinstance(action, str) or not action:
            raise SchemaValidationError(f"Step '{step_id}' has invalid 'action'.")

        params = step.get("params", {})
        if not isinstance(params, dict):
            raise SchemaValidationError(f"Step '{step_id}' params must be an object.")

        retry_cfg = step.get("retry")
        max_attempts = 1
        backoff_ms = 0
        if isinstance(retry_cfg, dict):
            max_attempts = max(1, int(retry_cfg.get("max_attempts", 1)))
            backoff_ms = max(0, int(retry_cfg.get("backoff_ms", 0)))

        step_ref[0] = step_id
        resolved_params = state_manager.resolve_templates(params)

        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            if attempt > 0 and backoff_ms > 0:
                # Exponential backoff with jitter
                delay = (backoff_ms * (2 ** (attempt - 1)) + random.randint(0, 200)) / 1000.0
                time.sleep(delay)

            logger.mark_step_started(step_id, resolved_params)
            try:
                step_result = self.tool_runtime.execute(action, resolved_params)
                state_manager.record_step_output(step_id, step_result)
                if isinstance(step_result, dict):
                    state_manager.update_state(step_result)
                logger.mark_step_succeeded(step_id, step_result, state_manager.state)
                return self._normalize_output(step_result)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    logger.mark_step_failed(step_id, self._error_code_from_exception(exc), str(exc), state_manager.state)
                    continue
                raise

        raise last_exc  # pragma: no cover

    def _run_steps_sequential(
        self,
        steps: list[dict[str, Any]],
        state_manager: StateManager,
        logger: ObservationLogger,
        step_ref: list[str | None],
    ) -> dict[str, Any]:
        """Run steps in strict sequence. Returns the last step output."""
        final_output: dict[str, Any] = {}
        for step in steps:
            final_output = self._run_single_step(step, state_manager, logger, step_ref)
        return final_output

    # ------------------------------------------------------------------
    # Strategy v2: conditional
    # ------------------------------------------------------------------

    def _run_conditional(
        self,
        strategy: dict[str, Any],
        state_manager: StateManager,
        logger: ObservationLogger,
        step_ref: list[str | None],
    ) -> dict[str, Any]:
        """Sequential steps with optional per-step conditions. Skipped steps are not executed."""
        final_output: dict[str, Any] = {}
        for step in strategy.get("steps", []):
            condition = step.get("condition")
            if condition is not None:
                if not evaluate_condition(condition, state_manager):
                    continue
            final_output = self._run_single_step(step, state_manager, logger, step_ref)
        return final_output

    # ------------------------------------------------------------------
    # Strategy v2: retry_policy
    # ------------------------------------------------------------------

    def _run_retry_policy(
        self,
        strategy: dict[str, Any],
        state_manager: StateManager,
        logger: ObservationLogger,
        step_ref: list[str | None],
    ) -> dict[str, Any]:
        """Sequential execution wrapped in a retry loop."""
        retry_cfg = strategy.get("retry_policy", {})
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1)))
        backoff_ms = max(0, int(retry_cfg.get("backoff_ms", 0)))
        steps = strategy.get("steps", [])

        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            if attempt > 0:
                # Reset step state for a clean retry — inputs are preserved
                state_manager.step_outputs = {}
                state_manager.state = {}
                if logger.runtime is not None:
                    logger.runtime["retry_count"] = attempt
                if backoff_ms > 0:
                    time.sleep(backoff_ms / 1000.0)

            try:
                return self._run_steps_sequential(steps, state_manager, logger, step_ref)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    # Log failure for this attempt, then continue
                    if step_ref[0] is not None:
                        error_code = self._error_code_from_exception(exc)
                        logger.mark_step_failed(
                            step_ref[0], error_code, str(exc), state_manager.state,
                        )
                        step_ref[0] = None
                    continue
                raise

        raise last_exc  # pragma: no cover — unreachable

    # ------------------------------------------------------------------
    # Strategy v2: fallback
    # ------------------------------------------------------------------

    def _run_fallback(
        self,
        strategy: dict[str, Any],
        state_manager: StateManager,
        logger: ObservationLogger,
        step_ref: list[str | None],
    ) -> dict[str, Any]:
        """Run primary steps; on failure, run fallback_steps."""
        primary_steps = strategy.get("steps", [])
        fallback_steps = strategy.get("fallback_steps", [])

        try:
            return self._run_steps_sequential(primary_steps, state_manager, logger, step_ref)
        except Exception as primary_exc:
            if not fallback_steps:
                raise

            # Log primary failure then try fallback
            if step_ref[0] is not None:
                error_code = self._error_code_from_exception(primary_exc)
                logger.mark_step_failed(
                    step_ref[0], error_code, str(primary_exc), state_manager.state,
                )

            # Reset step state for fallback — inputs preserved
            state_manager.step_outputs = {}
            state_manager.state = {}
            step_ref[0] = None

            return self._run_steps_sequential(fallback_steps, state_manager, logger, step_ref)

    # ------------------------------------------------------------------
    # Helpers (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_required_inputs(capability_contract: dict[str, Any], inputs: dict[str, Any]) -> None:
        if not isinstance(inputs, dict):
            raise CapabilityInputError("Engine inputs must be an object.")

        required_fields: list[str] = []
        for field_name, field_contract in capability_contract.get("inputs", {}).items():
            if isinstance(field_contract, dict) and field_contract.get("required") is True:
                required_fields.append(field_name)

        missing = [field for field in required_fields if field not in inputs or inputs[field] is None]
        if missing:
            raise CapabilityInputError(f"Missing required inputs: {', '.join(sorted(missing))}")

    @staticmethod
    def _normalize_inputs(capability_contract: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(inputs)
        for field_name in capability_contract.get("inputs", {}).keys():
            normalized.setdefault(field_name, None)
        return normalized

    @staticmethod
    def _normalize_output(step_result: Any) -> dict[str, Any]:
        if isinstance(step_result, dict):
            return deepcopy(step_result)
        return {"result": deepcopy(step_result)}

    @staticmethod
    def _error_code_from_exception(exc: Exception) -> str:
        if isinstance(exc, VariableResolutionError):
            return "variable_resolution_error"
        if isinstance(exc, ToolExecutionError):
            return "tool_execution_error"
        if isinstance(exc, CapabilityInputError):
            return "input_validation_error"
        if isinstance(exc, SchemaValidationError):
            return "contract_validation_error"
        if isinstance(exc, ConditionError):
            return "condition_evaluation_error"
        return "execution_error"
