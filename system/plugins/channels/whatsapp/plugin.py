"""WhatsApp channel plugin — wraps WhatsAppBackendManager into the plugin SDK pattern.

Special: manages 3 backends (browser, baileys, official) via BackendManager,
uses WhatsAppReplyWorker for incoming messages, and Phase10 executor for
capability execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from system.sdk.contracts import (
    CapabilityEngineContract,
    CapabilityRegistryContract,
    ExecutionHistoryContract,
    IntentInterpreterContract,
    ToolRuntimeContract,
)


class WhatsAppChannelPlugin:
    plugin_id = "capos.channels.whatsapp"
    plugin_name = "WhatsApp Channel"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self) -> None:
        self.connector = None       # WhatsAppBackendManager
        self.executor = None        # Phase10WhatsAppCapabilityExecutor
        self.polling_worker = None  # WhatsAppReplyWorker
        self._worker_process = None
        self._settings: dict[str, Any] = {}
        self._ctx: Any = None

    def initialize(self, ctx: Any) -> None:
        from system.integrations.installed.whatsapp_web_connector.backends import (
            WhatsAppBackendManager,
        )
        from system.integrations.installed.whatsapp_web_connector.backends.baileys_backend import (
            BaileysBackend,
        )
        from system.integrations.installed.whatsapp_web_connector.backends.browser_backend import (
            BrowserBackend,
        )
        from system.integrations.installed.whatsapp_web_connector.backends.official_backend import (
            OfficialBackend,
        )

        self._ctx = ctx
        self._settings = ctx.plugin_settings(self.plugin_id)

        # Build the backend manager with all 3 backends registered
        manager = WhatsAppBackendManager()
        manager.register(BrowserBackend())
        manager.register(BaileysBackend())

        # Official backend needs configuration via configure()
        official = OfficialBackend()
        official_config = self._settings.get("official", {})
        if official_config:
            official.configure(official_config)
        manager.register(official)

        # Switch to the configured backend (default: browser)
        active_backend = self._settings.get("backend", "browser")
        manager.switch(active_backend)

        self.connector = manager

        # Create executor (Phase10) if registries are available
        cap_registry = ctx.get_optional(CapabilityRegistryContract)
        tool_runtime = ctx.get_optional(ToolRuntimeContract)

        if cap_registry is not None and tool_runtime is not None:
            from system.capabilities.implementations import (
                Phase10WhatsAppCapabilityExecutor,
            )

            selectors_config = (
                ctx.project_root
                / "system"
                / "integrations"
                / "installed"
                / "whatsapp_web_connector"
                / "config"
                / "selectors.json"
            )
            self.executor = Phase10WhatsAppCapabilityExecutor(
                capability_registry=cap_registry,
                tool_runtime=tool_runtime,
                selectors_config_path=selectors_config,
            )

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import integration_handlers
        router.add("GET", "/integrations/whatsapp/selectors/health", integration_handlers.whatsapp_selectors_health)
        router.add("POST", "/integrations/whatsapp/selectors", integration_handlers.whatsapp_selectors_override)
        router.add("POST", "/integrations/whatsapp/close-session", integration_handlers.whatsapp_close_session)
        router.add("GET", "/integrations/whatsapp/session-status", integration_handlers.whatsapp_session_status)
        router.add("POST", "/integrations/whatsapp/start", integration_handlers.whatsapp_start)
        router.add("GET", "/integrations/whatsapp/qr", integration_handlers.whatsapp_qr)
        router.add("POST", "/integrations/whatsapp/stop", integration_handlers.whatsapp_stop)
        router.add("POST", "/integrations/whatsapp/configure", integration_handlers.whatsapp_configure)
        router.add("POST", "/integrations/whatsapp/switch-backend", integration_handlers.whatsapp_switch_backend)
        router.add("GET", "/integrations/whatsapp/backends", integration_handlers.whatsapp_list_backends)
        router.add("GET", "/integrations/whatsapp/debug", integration_handlers.whatsapp_debug)
        router.add("GET", "/integrations/whatsapp/debug-chats", integration_handlers.whatsapp_debug_chats)
        router.add("GET", "/integrations/whatsapp/reply-status", integration_handlers.whatsapp_reply_status)

    def start(self) -> None:
        # Try Redis worker first (reply processing in separate process)
        try:
            from system.infrastructure.message_queue import create_queue
            queue = create_queue(self._ctx.plugin_settings("capos.core.settings") if self._ctx else {})
            if queue.is_redis:
                from system.infrastructure.worker_process import WorkerProcess
                self._worker_process = WorkerProcess(
                    name="whatsapp_worker", queue=queue, script="system/workers/whatsapp_worker.py",
                )
                self._worker_process.start()
                return
        except Exception:
            pass

        # Fallback: in-process reply worker (original behavior)
        from system.integrations.installed.whatsapp_web_connector.whatsapp_reply_worker import (
            WhatsAppReplyWorker,
        )

        interpreter = self._ctx.get_optional(IntentInterpreterContract)
        if interpreter is None:
            return

        engine = self._ctx.get_optional(CapabilityEngineContract)
        execution_history = self._ctx.get_optional(ExecutionHistoryContract)

        executor_fn = None
        if engine is not None:
            executor_fn = lambda cap, inputs: engine.execute(
                {"id": cap}, inputs
            )

        self.polling_worker = WhatsAppReplyWorker(
            backend_manager=self.connector,
            interpreter=interpreter,
            executor=executor_fn,
            execution_history=execution_history,
            allowed_user_ids=self._settings.get("allowed_user_ids", []),
        )
        self.polling_worker.start()

    def stop(self) -> None:
        if self._worker_process is not None:
            self._worker_process.stop()
            self._worker_process = None
        if self.polling_worker is not None:
            self.polling_worker.stop()
        if self.connector is not None:
            self.connector.stop()

    @property
    def channel_id(self) -> str:
        return "whatsapp"

    def get_status(self) -> dict[str, Any]:
        status = {"channel": self.channel_id, "configured": False, "connected": False}
        if self.connector is not None:
            manager_status = self.connector.get_status()
            status.update(manager_status)
            status["configured"] = True
            status["backends"] = self.connector.list_backends()
        if self.polling_worker is not None:
            status["reply_worker"] = self.polling_worker.get_status()
        return status

    def configure(self, settings: dict[str, Any]) -> None:
        self._settings.update(settings)

        # Switch backend if requested
        backend = settings.get("backend")
        if backend and self.connector is not None:
            self.connector.switch(backend)

        # Update allowed users on the reply worker
        allowed = settings.get("allowed_user_ids")
        if allowed is not None and self.polling_worker is not None:
            self.polling_worker.configure(allowed_user_ids=allowed)

    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]:
        if self.connector is None:
            return {"status": "error", "error": "Backend manager not initialized"}
        return self.connector.send_message(target, text)


def create_plugin():
    return WhatsAppChannelPlugin()
