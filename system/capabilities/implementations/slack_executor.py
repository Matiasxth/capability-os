"""Executor for Slack Bot API capabilities."""
from __future__ import annotations

from typing import Any

from system.integrations.channel_adapter import ChannelError


_CAPABILITY_HANDLERS = {
    "send_slack_message": "send_slack_message",
}


class SlackCapabilityExecutor:
    """Executes Slack capabilities by delegating to the connector."""

    def __init__(self, connector: Any = None):
        self.connector = connector

    def execute(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        handler_name = _CAPABILITY_HANDLERS.get(capability_id)
        if handler_name is None:
            return None
        if self.connector is None:
            return None
        handler = getattr(self.connector, handler_name, None)
        if handler is None:
            return None
        try:
            output = handler(inputs)
        except ChannelError as exc:
            return {
                "status": "error",
                "execution_id": f"slack_{capability_id}",
                "capability_id": capability_id,
                "runtime": {},
                "final_output": {},
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
        except Exception as exc:
            return {
                "status": "error",
                "execution_id": f"slack_{capability_id}",
                "capability_id": capability_id,
                "runtime": {},
                "final_output": {},
                "error_code": "slack_error",
                "error_message": str(exc),
            }
        return {
            "status": output.get("status", "success") if isinstance(output, dict) else "success",
            "execution_id": f"slack_{capability_id}",
            "capability_id": capability_id,
            "runtime": {},
            "final_output": output if isinstance(output, dict) else {},
            "error_code": None,
            "error_message": None,
        }
