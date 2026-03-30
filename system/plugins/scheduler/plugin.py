"""Scheduler plugin — provides task queue and proactive scheduling.

Dependencies: capos.core.settings, capos.core.agent
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    AgentLoopContract,
    AgentRegistryContract,
)

logger = logging.getLogger(__name__)


class SchedulerPlugin:
    """Bootstraps TaskQueue and ProactiveScheduler."""

    plugin_id: str = "capos.core.scheduler"
    plugin_name: str = "Scheduler"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings", "capos.core.agent"]

    def __init__(self) -> None:
        self.task_queue: Any = None
        self.scheduler: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        # --- TaskQueue ---
        try:
            from system.core.scheduler import TaskQueue

            self.task_queue = TaskQueue(
                data_path=workspace_root / "queue.json",
            )
            logger.info("Created TaskQueue")
        except Exception:
            logger.exception("Failed to create TaskQueue")

        # --- ProactiveScheduler ---
        try:
            from system.core.scheduler import ProactiveScheduler

            agent_loop = ctx.get_optional(AgentLoopContract)
            agent_registry = ctx.get_optional(AgentRegistryContract)

            self.scheduler = ProactiveScheduler(
                task_queue=self.task_queue,
                agent_loop=agent_loop,
                agent_registry=agent_registry,
                whatsapp_manager=None,
            )
            logger.info("Created ProactiveScheduler")
        except Exception:
            logger.exception("Failed to create ProactiveScheduler")

    def start(self) -> None:
        """Start the proactive scheduler."""
        if self.scheduler is not None:
            try:
                self.scheduler.start()
                logger.info("ProactiveScheduler started")
            except Exception:
                logger.exception("Failed to start ProactiveScheduler")

    def stop(self) -> None:
        """Stop the proactive scheduler."""
        if self.scheduler is not None:
            try:
                self.scheduler.stop()
                logger.info("ProactiveScheduler stopped")
            except Exception:
                logger.exception("Failed to stop ProactiveScheduler")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> SchedulerPlugin:
    """Entry-point factory used by the plugin loader."""
    return SchedulerPlugin()
