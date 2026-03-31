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
        self._worker_process: Any = None

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

            # Resolve channel connectors for multi-channel delivery
            tg_plugin = None
            slack_plugin = None
            discord_plugin = None
            try:
                from system.container.service_container import ServiceContainer
                # Channel plugins expose send_message via their plugin instances
                # We pass them as connectors to the scheduler
                container = getattr(ctx, "_get_service", None)
                if container:
                    # Plugins are resolved after init, so we use lazy access via event_bus context
                    pass
            except Exception:
                pass

            self.scheduler = ProactiveScheduler(
                task_queue=self.task_queue,
                agent_loop=agent_loop,
                agent_registry=agent_registry,
                whatsapp_manager=None,
                telegram_connector=tg_plugin,
                slack_connector=slack_plugin,
                discord_connector=discord_plugin,
                event_bus=ctx.event_bus,
            )
            logger.info("Created ProactiveScheduler")
        except Exception:
            logger.exception("Failed to create ProactiveScheduler")

        from system.sdk.contracts import TaskQueueContract, SchedulerContract
        if self.task_queue:
            ctx.publish_service(TaskQueueContract, self.task_queue)
        if self.scheduler:
            ctx.publish_service(SchedulerContract, self.scheduler)

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import scheduler_handlers
        router.add("GET", "/scheduler/tasks", scheduler_handlers.list_tasks)
        router.add("POST", "/scheduler/tasks", scheduler_handlers.create_task)
        router.add("POST", "/scheduler/tasks/{task_id}", scheduler_handlers.update_task)
        router.add("DELETE", "/scheduler/tasks/{task_id}", scheduler_handlers.delete_task)
        router.add("POST", "/scheduler/tasks/{task_id}/run", scheduler_handlers.run_task_now)
        router.add("GET", "/scheduler/status", scheduler_handlers.scheduler_status)
        router.add("GET", "/scheduler/log", scheduler_handlers.scheduler_log)

    def start(self) -> None:
        """Start the proactive scheduler."""
        # Try Redis worker first
        try:
            from system.infrastructure.message_queue import create_queue
            queue = create_queue({})
            if queue.is_redis:
                from system.infrastructure.worker_process import WorkerProcess
                self._worker_process = WorkerProcess(
                    name="scheduler_worker", queue=queue, script="system/workers/scheduler_worker.py",
                )
                self._worker_process.start()
                logger.info("Scheduler started as Redis worker")
                return
        except Exception:
            pass

        # Fallback: in-process threads (original behavior)
        if self.scheduler is not None:
            try:
                self.scheduler.start()
                logger.info("ProactiveScheduler started (in-process)")
            except Exception:
                logger.exception("Failed to start ProactiveScheduler")

    def stop(self) -> None:
        """Stop the proactive scheduler."""
        if self._worker_process is not None:
            self._worker_process.stop()
            self._worker_process = None
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
