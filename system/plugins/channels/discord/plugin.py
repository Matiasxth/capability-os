"""Discord channel plugin — wraps DiscordConnector into the plugin SDK pattern."""
from __future__ import annotations

from typing import Any

from system.sdk.contracts import (
    CapabilityEngineContract,
    ExecutionHistoryContract,
    IntentInterpreterContract,
)


class DiscordChannelPlugin:
    plugin_id = "capos.channels.discord"
    plugin_name = "Discord Channel"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self) -> None:
        self.connector = None
        self.executor = None
        self.polling_worker = None
        self._worker_process = None
        self._settings: dict[str, Any] = {}
        self._ctx: Any = None

    def initialize(self, ctx: Any) -> None:
        from system.integrations.installed.discord_bot_connector import (
            DiscordConnector,
            DiscordPollingWorker,
        )
        from system.capabilities.implementations.discord_executor import (
            DiscordCapabilityExecutor,
        )

        self._ctx = ctx
        self._settings = ctx.plugin_settings(self.plugin_id)

        # Create connector from settings
        self.connector = DiscordConnector(
            bot_token=self._settings.get("bot_token", ""),
            channel_id=self._settings.get("channel_id", ""),
            guild_id=self._settings.get("guild_id", ""),
            allowed_user_ids=self._settings.get("allowed_user_ids", []),
        )

        # Create executor
        self.executor = DiscordCapabilityExecutor(connector=self.connector)

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import integration_handlers
        router.add("GET", "/integrations/discord/status", integration_handlers.discord_status)
        router.add("POST", "/integrations/discord/configure", integration_handlers.discord_configure)
        router.add("POST", "/integrations/discord/test", integration_handlers.discord_test)
        router.add("POST", "/integrations/discord/polling/start", integration_handlers.discord_polling_start)
        router.add("POST", "/integrations/discord/polling/stop", integration_handlers.discord_polling_stop)
        router.add("GET", "/integrations/discord/polling/status", integration_handlers.discord_polling_status)

    def start(self) -> None:
        if not self._settings.get("polling_enabled", False):
            return

        # Try Redis worker first
        try:
            from system.infrastructure.message_queue import create_queue
            queue = create_queue(self._ctx.plugin_settings("capos.core.settings") if self._ctx else {})
            if queue.is_redis:
                from system.infrastructure.worker_process import WorkerProcess
                self._worker_process = WorkerProcess(
                    name="discord_worker", queue=queue, script="system/workers/discord_worker.py",
                )
                self._worker_process.start()
                return
        except Exception:
            pass

        # Fallback: in-process thread
        from system.integrations.installed.discord_bot_connector import DiscordPollingWorker

        interpreter = self._ctx.get_optional(IntentInterpreterContract)
        engine = self._ctx.get_optional(CapabilityEngineContract)
        execution_history = self._ctx.get_optional(ExecutionHistoryContract)

        executor_fn = None
        if engine is not None:
            executor_fn = lambda cap, inputs: engine.execute({"id": cap}, inputs)

        self.polling_worker = DiscordPollingWorker(
            adapter=self.connector, interpreter=interpreter,
            executor=executor_fn, execution_history=execution_history,
        )
        self.polling_worker.start()

    def stop(self) -> None:
        if self._worker_process is not None:
            self._worker_process.stop()
            self._worker_process = None
        if self.polling_worker is not None:
            self.polling_worker.stop()

    @property
    def channel_id(self) -> str:
        return "discord"

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
                guild_id=settings.get("guild_id", self.connector._guild_id),
                allowed_user_ids=settings.get("allowed_user_ids"),
            )

    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]:
        if self.connector is None:
            return {"status": "error", "error": "Connector not initialized"}
        return self.connector.send_message(target, text, **kw)


def create_plugin():
    return DiscordChannelPlugin()
