"""Executor for Telegram Bot API capabilities.

Routes capability execution to the TelegramConnector methods.
Same pattern as Phase10WhatsAppCapabilityExecutor.
"""
from __future__ import annotations

from typing import Any

from system.integrations.installed.telegram_bot_connector import TelegramConnector, TelegramConnectorError


_CAPABILITY_HANDLERS = {
    "send_telegram_message": "send_telegram_message",
    "send_telegram_photo": "send_telegram_photo",
    "get_telegram_updates": "get_telegram_updates",
}


class TelegramCapabilityExecutor:
    """Executes Telegram capabilities by delegating to the connector."""

    def __init__(self, connector: TelegramConnector | None = None):
        self.connector = connector or TelegramConnector()

    def execute(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        handler_name = _CAPABILITY_HANDLERS.get(capability_id)
        if handler_name is None:
            return None
        handler = getattr(self.connector, handler_name)
        try:
            output = handler(inputs)
        except TelegramConnectorError as exc:
            return {
                "status": "error",
                "execution_id": f"telegram_{capability_id}",
                "capability_id": capability_id,
                "runtime": {},
                "final_output": {},
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
        except Exception as exc:
            return {
                "status": "error",
                "execution_id": f"telegram_{capability_id}",
                "capability_id": capability_id,
                "runtime": {},
                "final_output": {},
                "error_code": "telegram_error",
                "error_message": str(exc),
            }
        return {
            "status": output.get("status", "success") if isinstance(output, dict) else "success",
            "execution_id": f"telegram_{capability_id}",
            "capability_id": capability_id,
            "runtime": {},
            "final_output": output if isinstance(output, dict) else {},
            "error_code": None,
            "error_message": None,
        }
