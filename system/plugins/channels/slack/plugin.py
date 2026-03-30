"""Slack channel plugin — wraps SlackConnector into the plugin SDK pattern."""
from __future__ import annotations

from typing import Any

from system.sdk.contracts import (
    CapabilityEngineContract,
    ExecutionHistoryContract,
    IntentInterpreterContract,
)


class SlackChannelPlugin:
    plugin_id = "capos.channels.slack"
    plugin_name = "Slack Channel"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self) -> None:
        self.connector = None
        self.executor = None
        self.polling_worker = None
        self._settings: dict[str, Any] = {}
        self._ctx: Any = None

    def initialize(self, ctx: Any) -> None:
        from system.integrations.installed.slack_bot_connector import (
            SlackConnector,
            SlackPollingWorker,
        )
        from system.capabilities.implementations.slack_executor import (
            SlackCapabilityExecutor,
        )

        self._ctx = ctx
        self._settings = ctx.plugin_settings(self.plugin_id)

        # Create connector from settings
        self.connector = SlackConnector(
            bot_token=self._settings.get("bot_token", ""),
            channel_id=self._settings.get("channel_id", ""),
            allowed_user_ids=self._settings.get("allowed_user_ids", []),
        )

        # Create executor
        self.executor = SlackCapabilityExecutor(connector=self.connector)

    def start(self) -> None:
        from system.integrations.installed.slack_bot_connector import (
            SlackPollingWorker,
        )

        if not self._settings.get("polling_enabled", False):
            return

        interpreter = self._ctx.get_optional(IntentInterpreterContract)
        engine = self._ctx.get_optional(CapabilityEngineContract)
        execution_history = self._ctx.get_optional(ExecutionHistoryContract)

        executor_fn = None
        if engine is not None:
            executor_fn = lambda cap, inputs: engine.execute(
                {"id": cap}, inputs
            )

        self.polling_worker = SlackPollingWorker(
            adapter=self.connector,
            interpreter=interpreter,
            executor=executor_fn,
            execution_history=execution_history,
        )
        self.polling_worker.start()

    def stop(self) -> None:
        if self.polling_worker is not None:
            self.polling_worker.stop()

    @property
    def channel_id(self) -> str:
        return "slack"

    def get_status(self) -> dict[str, Any]:
        status = {"channel": self.channel_id, "configured": False, "connected": False}
        if self.connector is not None:
            status.update(self.connector.get_status())
        if self.polling_worker is not None:
            status["polling"] = self.polling_worker.get_status()
        return status

    def configure(self, settings: dict[str, Any]) -> None:
        self._settings.update(settings)
        if self.connector is not None:
            self.connector.configure(
                bot_token=settings.get("bot_token", self.connector._bot_token),
                channel_id=settings.get("channel_id", self.connector._channel_id),
                allowed_user_ids=settings.get("allowed_user_ids"),
            )

    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]:
        if self.connector is None:
            return {"status": "error", "error": "Connector not initialized"}
        return self.connector.send_message(target, text, **kw)


def create_plugin():
    return SlackChannelPlugin()
