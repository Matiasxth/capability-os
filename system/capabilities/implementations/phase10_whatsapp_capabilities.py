from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityExecutionError, CapabilityInputError
from system.core.observation import ObservationLogger
from system.integrations.installed.whatsapp_web_connector import (
    WhatsAppConnectorError,
    WhatsAppWebConnector,
)
from system.tools.runtime import ToolRuntime


class Phase10WhatsAppCapabilityExecutor:
    """Executes WhatsApp connector capabilities without changing core engine behavior."""

    _CAPABILITY_HANDLERS: dict[str, tuple[str, str]] = {
        "open_whatsapp_web": ("open_whatsapp_web", "open_whatsapp_web"),
        "wait_for_whatsapp_login": ("wait_for_whatsapp_login", "wait_for_whatsapp_login"),
        "search_whatsapp_chat": ("search_whatsapp_chat", "search_whatsapp_chat"),
        "read_whatsapp_messages": ("read_whatsapp_messages", "read_whatsapp_messages"),
        "send_whatsapp_message": ("send_whatsapp_message", "send_whatsapp_message"),
        "list_whatsapp_visible_chats": ("list_whatsapp_visible_chats", "list_whatsapp_visible_chats")
    }

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        tool_runtime: ToolRuntime,
        selectors_config_path: str | Path,
    ):
        self.capability_registry = capability_registry
        self.connector = WhatsAppWebConnector(tool_runtime, selectors_config_path)

    def execute(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        handler_info = self._CAPABILITY_HANDLERS.get(capability_id)
        if handler_info is None:
            return None
        if not isinstance(inputs, dict):
            raise CapabilityInputError("Capability inputs must be an object.")

        capability_contract = self._require_contract(capability_id)
        _validate_required_inputs(capability_contract, inputs)

        handler_name, step_id = handler_info
        handler: Callable[[dict[str, Any]], dict[str, Any]] = getattr(self.connector, handler_name)

        logger = ObservationLogger()
        logger.initialize(capability_id)
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        state_snapshot: dict[str, Any] = {}
        try:
            logger.mark_step_started(step_id, deepcopy(inputs))
            output = handler(inputs)
            if not isinstance(output, dict):
                raise WhatsAppConnectorError(
                    "invalid_connector_output",
                    f"Connector handler '{handler_name}' returned a non-object output.",
                )
            state_snapshot.update(deepcopy(output))
            logger.mark_step_succeeded(step_id, output, state_snapshot)
            runtime = logger.finish(status="ready", final_output=output, state_snapshot=state_snapshot)
            return {
                "execution_id": runtime["execution_id"],
                "capability_id": capability_id,
                "status": "success",
                "final_output": deepcopy(output),
                "runtime": runtime,
                "step_outputs": {step_id: deepcopy(output)},
            }
        except Exception as exc:
            if isinstance(exc, CapabilityInputError):
                raise
            if isinstance(exc, WhatsAppConnectorError) and exc.error_code == "invalid_input":
                raise CapabilityInputError(exc.error_message) from exc

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
            raise CapabilityExecutionError(message, runtime, error_code) from exc

    def _require_contract(self, capability_id: str) -> dict[str, Any]:
        contract = self.capability_registry.get(capability_id)
        if contract is None:
            raise CapabilityInputError(f"Capability '{capability_id}' is not registered.")
        return contract


def _validate_required_inputs(capability_contract: dict[str, Any], inputs: dict[str, Any]) -> None:
    required_fields: list[str] = []
    for field_name, field_contract in capability_contract.get("inputs", {}).items():
        if isinstance(field_contract, dict) and field_contract.get("required") is True:
            required_fields.append(field_name)

    missing = [field for field in required_fields if field not in inputs or inputs[field] is None]
    if missing:
        raise CapabilityInputError(f"Missing required inputs: {', '.join(sorted(missing))}")


def _error_code_from_exception(exc: Exception) -> str:
    if isinstance(exc, WhatsAppConnectorError):
        return exc.error_code
    if isinstance(exc, CapabilityExecutionError):
        return exc.error_code
    if isinstance(exc, CapabilityInputError):
        return "input_validation_error"
    return "execution_error"

