from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.observation import ObservationLogger
from system.core.state import StateManager, VariableResolutionError
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
    """Generic sequential capability engine for Phase 2."""

    def __init__(self, capability_registry: CapabilityRegistry, tool_runtime: ToolRuntime):
        self.capability_registry = capability_registry
        self.tool_runtime = tool_runtime

    def execute(self, capability_contract: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        contract_id = self.capability_registry.validate_contract(capability_contract, source="capability_engine")
        self._validate_required_inputs(capability_contract, inputs)
        normalized_inputs = self._normalize_inputs(capability_contract, inputs)

        strategy = capability_contract.get("strategy", {})
        mode = strategy.get("mode")
        if mode != "sequential":
            raise CapabilityInputError(
                f"Unsupported strategy mode '{mode}'. Phase 2 only supports 'sequential'."
            )

        logger = ObservationLogger()
        logger.initialize(contract_id)
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_manager = StateManager(normalized_inputs)
        state_manager.set_runtime_provider(logger.get_runtime_model)

        final_output: dict[str, Any] = {}
        current_step: str | None = None

        try:
            for step in strategy.get("steps", []):
                current_step = step.get("step_id")
                if not current_step:
                    raise SchemaValidationError("Sequential strategy steps require 'step_id'.")

                action = step.get("action")
                if not isinstance(action, str) or not action:
                    raise SchemaValidationError(f"Step '{current_step}' has invalid 'action'.")

                params = step.get("params", {})
                if not isinstance(params, dict):
                    raise SchemaValidationError(f"Step '{current_step}' params must be an object.")

                resolved_params = state_manager.resolve_templates(params)
                logger.mark_step_started(current_step, resolved_params)

                step_result = self.tool_runtime.execute(action, resolved_params)
                state_manager.record_step_output(current_step, step_result)
                if isinstance(step_result, dict):
                    state_manager.update_state(step_result)

                logger.mark_step_succeeded(current_step, step_result, state_manager.state)
                final_output = self._normalize_output(step_result)

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

            if current_step is not None:
                logger.mark_step_failed(
                    current_step,
                    error_code,
                    message,
                    state_manager.state,
                )

            runtime_model = logger.finish(
                status="error",
                final_output={},
                state_snapshot=state_manager.state,
                error_code=error_code,
                error_message=message,
                failed_step=current_step,
            )
            raise CapabilityExecutionError(message, runtime_model, error_code) from exc

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
        return "execution_error"
