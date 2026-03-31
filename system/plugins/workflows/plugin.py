"""Workflows plugin — visual workflow builder backend.

Provides WorkflowRegistry (CRUD + persistence) and WorkflowExecutor
(topological execution of workflow graphs).

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import ToolRuntimeContract, AgentLoopContract, LLMClientContract

logger = logging.getLogger(__name__)


class WorkflowsPlugin:
    """Bootstraps WorkflowRegistry and WorkflowExecutor."""

    plugin_id: str = "capos.core.workflows"
    plugin_name: str = "Workflows"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.workflow_registry: Any = None
        self.workflow_executor: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:
        workspace_root = ctx.workspace_root
        tool_runtime = ctx.get_optional(ToolRuntimeContract)
        agent_loop = ctx.get_optional(AgentLoopContract)
        llm = ctx.get_optional(LLMClientContract)

        # --- WorkflowRegistry ---
        try:
            from system.core.workflow import WorkflowRegistry

            self.workflow_registry = WorkflowRegistry(
                workspace_root=workspace_root,
            )
            logger.info("Created WorkflowRegistry")
        except Exception:
            logger.exception("Failed to create WorkflowRegistry")

        # --- WorkflowExecutor ---
        try:
            from system.core.workflow import WorkflowExecutor

            self.workflow_executor = WorkflowExecutor(
                tool_runtime=tool_runtime,
                agent_loop=agent_loop,
                llm=llm,
            )
            logger.info("Created WorkflowExecutor")
        except Exception:
            logger.exception("Failed to create WorkflowExecutor")

        from system.sdk.contracts import WorkflowRegistryContract, WorkflowExecutorContract
        if self.workflow_registry:
            ctx.publish_service(WorkflowRegistryContract, self.workflow_registry)
        if self.workflow_executor:
            ctx.publish_service(WorkflowExecutorContract, self.workflow_executor)

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import workflow_handlers
        router.add("GET", "/workflows", workflow_handlers.list_workflows)
        router.add("POST", "/workflows", workflow_handlers.create_workflow)
        router.add("GET", "/workflows/{wf_id}", workflow_handlers.get_workflow)
        router.add("PUT", "/workflows/{wf_id}", workflow_handlers.update_workflow)
        router.add("DELETE", "/workflows/{wf_id}", workflow_handlers.delete_workflow)
        router.add("POST", "/workflows/{wf_id}/run", workflow_handlers.run_workflow)
        router.add("POST", "/workflows/{wf_id}/layout", workflow_handlers.save_layout)

    def start(self) -> None:
        """Workflows are passive — nothing to start."""

    def stop(self) -> None:
        """Workflows are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> WorkflowsPlugin:
    """Entry-point factory used by the plugin loader."""
    return WorkflowsPlugin()
