from __future__ import annotations

from copy import deepcopy
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import (
    CapabilityEngine,
    CapabilityExecutionError,
    CapabilityInputError,
)
from system.core.observation import ObservationLogger


class Phase7CapabilityExecutionError(RuntimeError):
    """Raised when deterministic Phase 7 capability execution fails."""

    def __init__(self, message: str, runtime_model: dict[str, Any], error_code: str):
        super().__init__(message)
        self.runtime_model = runtime_model
        self.error_code = error_code


class Phase7CapabilityExecutor:
    """Executes Phase 7 deterministic capabilities without modifying core engine."""

    def __init__(self, capability_registry: CapabilityRegistry, capability_engine: CapabilityEngine):
        self.capability_registry = capability_registry
        self.capability_engine = capability_engine

    def execute(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        if capability_id == "modify_code":
            return self._execute_modify_code(inputs)
        if capability_id == "diagnose_error":
            return self._execute_diagnose_error(inputs)
        return None

    def _execute_modify_code(self, inputs: dict[str, Any]) -> dict[str, Any]:
        file_path = inputs.get("file_path")
        modification = inputs.get("modification")
        mode = inputs.get("mode")
        if not isinstance(file_path, str) or not file_path.strip():
            raise CapabilityInputError("modify_code requires non-empty 'file_path'.")
        if not isinstance(modification, str):
            raise CapabilityInputError("modify_code requires string 'modification'.")
        if mode not in {"replace", "append"}:
            raise CapabilityInputError("modify_code field 'mode' must be 'replace' or 'append'.")

        logger = ObservationLogger()
        logger.initialize("modify_code")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_snapshot: dict[str, Any] = {}
        try:
            # Step 1: read existing file to validate path and get current content for append mode.
            read_step_id = "read_file"
            logger.mark_step_started(read_step_id, {"path": file_path})
            read_contract = self._require_contract("read_file")
            read_result = self.capability_engine.execute(read_contract, {"path": file_path})
            read_output = deepcopy(read_result.get("final_output", {}))
            current_content = read_output.get("content")
            if not isinstance(current_content, str):
                raise Phase7CapabilityExecutionError(
                    "read_file did not return string content.",
                    logger.get_runtime_model(),
                    "capability_execution_error",
                )
            state_snapshot.update(read_output if isinstance(read_output, dict) else {})
            logger.mark_step_succeeded(read_step_id, read_output, state_snapshot)

            # Step 2: deterministic modification inside capability scope.
            modified_content = modification if mode == "replace" else f"{current_content}{modification}"

            write_step_id = "write_file"
            logger.mark_step_started(write_step_id, {"path": file_path, "mode": mode})
            write_contract = self._require_contract("write_file")
            write_result = self.capability_engine.execute(
                write_contract,
                {"path": file_path, "content": modified_content},
            )
            write_output = deepcopy(write_result.get("final_output", {}))
            if isinstance(write_output, dict):
                state_snapshot.update(write_output)
            logger.mark_step_succeeded(write_step_id, write_output, state_snapshot)

            final_output = {
                "status": "success",
                "path": write_output.get("path", file_path),
            }
            runtime = logger.finish(status="ready", final_output=final_output, state_snapshot=state_snapshot)
            return {
                "execution_id": runtime["execution_id"],
                "capability_id": "modify_code",
                "status": "success",
                "final_output": final_output,
                "runtime": runtime,
                "step_outputs": {
                    read_step_id: read_output,
                    write_step_id: write_output,
                },
            }
        except Exception as exc:
            error_code = _error_code_from_exception(exc)
            message = str(exc)
            failed_step = logger.get_runtime_model().get("current_step")
            if isinstance(failed_step, str):
                logger.mark_step_failed(failed_step, error_code, message, state_snapshot)
            runtime = logger.finish(
                status="error",
                final_output={},
                state_snapshot=state_snapshot,
                error_code=error_code,
                error_message=message,
                failed_step=failed_step if isinstance(failed_step, str) else None,
            )
            raise Phase7CapabilityExecutionError(message, runtime, error_code) from exc

    def _execute_diagnose_error(self, inputs: dict[str, Any]) -> dict[str, Any]:
        error_output = inputs.get("error_output")
        if not isinstance(error_output, str) or not error_output.strip():
            raise CapabilityInputError("diagnose_error requires non-empty 'error_output'.")

        logger = ObservationLogger()
        logger.initialize("diagnose_error")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_snapshot: dict[str, Any] = {}
        step_id = "diagnose_error"
        try:
            logger.mark_step_started(step_id, {"error_output": error_output})
            diagnosis = _diagnose_error(error_output)
            state_snapshot["diagnosis"] = diagnosis
            logger.mark_step_succeeded(step_id, diagnosis, state_snapshot)
            final_output = {"diagnosis": diagnosis}
            runtime = logger.finish(status="ready", final_output=final_output, state_snapshot=state_snapshot)
            return {
                "execution_id": runtime["execution_id"],
                "capability_id": "diagnose_error",
                "status": "success",
                "final_output": final_output,
                "runtime": runtime,
                "step_outputs": {step_id: diagnosis},
            }
        except Exception as exc:
            error_code = _error_code_from_exception(exc)
            message = str(exc)
            logger.mark_step_failed(step_id, error_code, message, state_snapshot)
            runtime = logger.finish(
                status="error",
                final_output={},
                state_snapshot=state_snapshot,
                error_code=error_code,
                error_message=message,
                failed_step=step_id,
            )
            raise Phase7CapabilityExecutionError(message, runtime, error_code) from exc

    def _require_contract(self, capability_id: str) -> dict[str, Any]:
        contract = self.capability_registry.get(capability_id)
        if contract is None:
            raise CapabilityInputError(f"Capability '{capability_id}' is not registered.")
        return contract


def _diagnose_error(error_output: str) -> dict[str, str]:
    trimmed = error_output.strip()
    first_line = next((line.strip() for line in trimmed.splitlines() if line.strip()), trimmed)
    lower = trimmed.lower()

    if "modulenotfounderror" in lower:
        return {
            "error_type": "ModuleNotFoundError",
            "message": first_line,
            "possible_cause": "A required dependency is missing in the current environment.",
            "suggested_action": "Install the missing package and verify the active interpreter/environment.",
        }

    if "syntaxerror" in lower:
        return {
            "error_type": "SyntaxError",
            "message": first_line,
            "possible_cause": "The source file contains invalid syntax.",
            "suggested_action": "Review the referenced file/line and correct syntax before re-running.",
        }

    if "command not found" in lower or "is not recognized as an internal or external command" in lower:
        return {
            "error_type": "command_not_found",
            "message": first_line,
            "possible_cause": "The command is not installed or is not present in PATH.",
            "suggested_action": "Install the command or update PATH, then execute again.",
        }

    if "permission denied" in lower or "acceso denegado" in lower:
        return {
            "error_type": "permission_denied",
            "message": first_line,
            "possible_cause": "Current user does not have permission to access the target resource.",
            "suggested_action": "Adjust file/system permissions or run with the required access level.",
        }

    return {
        "error_type": "unknown_error",
        "message": first_line,
        "possible_cause": "Error pattern is not recognized by deterministic rules.",
        "suggested_action": "Inspect full logs and reproduce with verbose output for deeper diagnosis.",
    }


def _error_code_from_exception(exc: Exception) -> str:
    if isinstance(exc, CapabilityExecutionError):
        return "capability_execution_error"
    if isinstance(exc, CapabilityInputError):
        return "input_validation_error"
    if isinstance(exc, Phase7CapabilityExecutionError):
        return exc.error_code
    return "execution_error"
