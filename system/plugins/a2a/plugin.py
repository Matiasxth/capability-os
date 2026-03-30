"""A2A plugin — provides Agent-to-Agent protocol client, server,
and agent card builder.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityEngineContract,
    CapabilityRegistryContract,
    SettingsProvider,
)

logger = logging.getLogger(__name__)


class A2APlugin:
    """Bootstraps A2AClient, A2AServer, and AgentCardBuilder."""

    plugin_id: str = "capos.core.a2a"
    plugin_name: str = "A2A"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.a2a_client: Any = None
        self.a2a_server: Any = None
        self.agent_card_builder: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        capability_registry = ctx.get_optional(CapabilityRegistryContract)
        capability_engine = ctx.get_optional(CapabilityEngineContract)
        settings = ctx.get_optional(SettingsProvider)

        server_url = "http://localhost:8000"
        if settings is not None:
            try:
                all_settings = settings.get_settings(mask_secrets=False)
                a2a_cfg = all_settings.get("a2a", {})
                if isinstance(a2a_cfg, dict):
                    server_url = a2a_cfg.get("server_url", server_url)
            except Exception:
                pass

        # --- A2AClient ---
        try:
            from system.core.a2a import A2AClient

            self.a2a_client = A2AClient(agent_url=server_url)
            logger.info("Created A2AClient")
        except Exception:
            logger.exception("Failed to create A2AClient")

        # --- A2AServer ---
        try:
            from system.core.a2a import A2AServer

            self.a2a_server = A2AServer(
                capability_registry=capability_registry,
                capability_engine=capability_engine,
            )
            logger.info("Created A2AServer")
        except Exception:
            logger.exception("Failed to create A2AServer")

        # --- AgentCardBuilder ---
        try:
            from system.core.a2a import AgentCardBuilder

            self.agent_card_builder = AgentCardBuilder(
                capability_registry=capability_registry,
                server_url=server_url,
            )
            logger.info("Created AgentCardBuilder")
        except Exception:
            logger.exception("Failed to create AgentCardBuilder")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import a2a_handlers
        router.add("GET", "/.well-known/agent.json", a2a_handlers.agent_card)
        router.add("POST", "/a2a", a2a_handlers.handle_task)
        router.add("GET", "/a2a/{task_id}/events", a2a_handlers.task_events)
        router.add("GET", "/a2a/agents", a2a_handlers.list_agents)
        router.add("POST", "/a2a/agents", a2a_handlers.add_agent)
        router.add("DELETE", "/a2a/agents/{agent_id}", a2a_handlers.remove_agent)
        router.add("POST", "/a2a/agents/{agent_id}/delegate", a2a_handlers.delegate_task)

    def start(self) -> None:
        """A2A subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """A2A subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> A2APlugin:
    """Entry-point factory used by the plugin loader."""
    return A2APlugin()
