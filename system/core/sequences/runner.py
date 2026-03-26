from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import (
    CapabilityEngine,
    CapabilityExecutionError,
    CapabilityInputError,
)
from system.core.observation import ObservationLogger
from system.core.state import StateManager, VariableResolutionError

from .model import SequenceDefinition, SequenceValidationError
from .registry import SequenceRegistry
from .storage import SequenceStorageError


class SequenceRunError(RuntimeError):
    """Raised when run_sequence execution fails."""

    def __init__(self, message: str, runtime_model: dict[str, Any], error_code: str):
        super().__init__(message)
        self.runtime_model = runtime_model
        self.error_code = error_code


class SequenceRunner:
    """Executes a sequence by chaining capabilities through CapabilityEngine."""

    def __init__(
        self,
        sequence_registry: SequenceRegistry,
        capability_registry: CapabilityRegistry,
        capability_engine: CapabilityEngine,
        capability_executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.sequence_registry = sequence_registry
        self.capability_registry = capability_registry
        self.capability_engine = capability_engine
        self.capability_executor = capability_executor

    def run(
        self,
        *,
        sequence_id: str | None = None,
        sequence_definition: dict[str, Any] | None = None,
        sequence_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if sequence_id is None and sequence_definition is None:
            raise SequenceValidationError("run_sequence requires 'sequence_id' or 'sequence_definition'.")
        if sequence_inputs is not None and not isinstance(sequence_inputs, dict):
            raise SequenceValidationError("'inputs' for run_sequence must be an object when provided.")

        definition = self._resolve_definition(sequence_id=sequence_id, sequence_definition=sequence_definition)

        logger = ObservationLogger()
        logger.initialize("run_sequence")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_manager = StateManager(sequence_inputs or {})
        state_manager.set_runtime_provider(logger.get_runtime_model)

        current_step: str | None = None
        aggregated_steps: dict[str, Any] = {}
        last_output: dict[str, Any] = {}

        try:
            for step in definition.steps:
                current_step = step.step_id
                resolved_inputs = state_manager.resolve_templates(step.inputs)
                logger.mark_step_started(
                    current_step,
                    {"capability": step.capability, "inputs": deepcopy(resolved_inputs)},
                )

                step_result = self._execute_step_capability(step.capability, resolved_inputs)
                step_output = deepcopy(step_result.get("final_output", {}))
                state_manager.record_step_output(current_step, step_output)
                if isinstance(step_output, dict):
                    state_manager.update_state(step_output)

                step_summary = {
                    "capability": step.capability,
                    "status": step_result.get("status"),
                    "execution_id": step_result.get("execution_id"),
                    "output": step_output,
                }
                aggregated_steps[current_step] = step_summary
                last_output = step_output if isinstance(step_output, dict) else {"result": step_output}
                logger.mark_step_succeeded(current_step, step_summary, state_manager.state)

            final_output = {
                "sequence_id": definition.sequence_id,
                "steps": aggregated_steps,
                "last_step": current_step,
                "last_output": last_output,
            }
            runtime = logger.finish(
                status="ready",
                final_output=final_output,
                state_snapshot=state_manager.state,
            )
            return {
                "status": "success",
                "execution_id": runtime["execution_id"],
                "runtime": runtime,
                "final_output": final_output,
                "error_code": None,
                "error_message": None,
            }
        except Exception as exc:
            error_code = _error_code_from_exception(exc)
            message = str(exc)
            if current_step is not None:
                logger.mark_step_failed(current_step, error_code, message, state_manager.state)

            runtime = logger.finish(
                status="error",
                final_output={},
                state_snapshot=state_manager.state,
                error_code=error_code,
                error_message=message,
                failed_step=current_step,
            )
            raise SequenceRunError(message, runtime, error_code) from exc

    def _resolve_definition(
        self,
        *,
        sequence_id: str | None,
        sequence_definition: dict[str, Any] | None,
    ) -> SequenceDefinition:
        if sequence_definition is not None:
            return self.sequence_registry.validate(sequence_definition)
        loaded = self.sequence_registry.load_sequence(sequence_id or "")
        return self.sequence_registry.validate(loaded)

    def _execute_step_capability(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        if self.capability_executor is not None:
            return self.capability_executor(capability_id, inputs)

        capability_contract = self.capability_registry.get(capability_id)
        if capability_contract is None:
            raise SequenceValidationError(f"Unknown capability '{capability_id}'.")
        return self.capability_engine.execute(capability_contract, inputs)


def _error_code_from_exception(exc: Exception) -> str:
    if isinstance(exc, VariableResolutionError):
        return "variable_resolution_error"
    if isinstance(exc, CapabilityExecutionError):
        return "capability_execution_error"
    if isinstance(exc, CapabilityInputError):
        return "capability_execution_error"
    if exc.__class__.__name__ == "Phase7CapabilityExecutionError":
        return "capability_execution_error"
    if isinstance(exc, SequenceValidationError):
        return "sequence_validation_error"
    if isinstance(exc, SequenceStorageError):
        return "sequence_storage_error"
    return "sequence_execution_error"
