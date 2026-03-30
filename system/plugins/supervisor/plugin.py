"""Supervisor plugin — provides the background supervisor daemon
and skill creator for autonomous self-improvement.

Dependencies: capos.core.settings, capos.core.agent
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    AgentLoopContract,
    ExecutionHistoryContract,
    SecurityServiceContract,
    SettingsProvider,
    ToolRegistryContract,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class SupervisorPlugin:
    """Bootstraps SupervisorDaemon and SkillCreator."""

    plugin_id: str = "capos.core.supervisor"
    plugin_name: str = "Supervisor"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings", "capos.core.agent"]

    def __init__(self) -> None:
        self.supervisor: Any = None
        self.skill_creator: Any = None
        self._event_bus: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        project_root = ctx.project_root
        self._event_bus = ctx.event_bus

        execution_history = ctx.get_optional(ExecutionHistoryContract)

        # --- SkillCreator ---
        try:
            from system.core.supervisor.skill_creator import SkillCreator

            tool_registry = ctx.get_optional(ToolRegistryContract)
            tool_runtime = ctx.get_optional(ToolRuntimeContract)
            agent_loop = ctx.get_optional(AgentLoopContract)
            security_service = ctx.get_optional(SecurityServiceContract)

            self.skill_creator = SkillCreator(
                tool_registry=tool_registry,
                tool_runtime=tool_runtime,
                agent_loop=agent_loop,
                security_service=security_service,
                project_root=project_root,
            )
            logger.info("Created SkillCreator")
        except Exception:
            logger.exception("Failed to create SkillCreator")

        # --- SupervisorDaemon ---
        try:
            from system.core.supervisor.supervisor_daemon import SupervisorDaemon

            self.supervisor = SupervisorDaemon(
                project_root=project_root,
                skill_creator=self.skill_creator,
                execution_history=execution_history,
            )
            logger.info("Created SupervisorDaemon")
            from system.sdk.contracts import SupervisorDaemonContract
            ctx.publish_service(SupervisorDaemonContract, self.supervisor)
        except Exception:
            logger.exception("Failed to create SupervisorDaemon")

    def start(self) -> None:
        """Start the supervisor daemon."""
        if self.supervisor is not None:
            try:
                self.supervisor.start(self._event_bus)
                logger.info("SupervisorDaemon started")
            except Exception:
                logger.exception("Failed to start SupervisorDaemon")

    def stop(self) -> None:
        """Stop the supervisor daemon."""
        if self.supervisor is not None:
            try:
                self.supervisor.stop()
                logger.info("SupervisorDaemon stopped")
            except Exception:
                logger.exception("Failed to stop SupervisorDaemon")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> SupervisorPlugin:
    """Entry-point factory used by the plugin loader."""
    return SupervisorPlugin()
