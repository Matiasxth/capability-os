"""Agent plugin — provides the agentic execution loop, agent registry,
and tool-use LLM adapter.

Publishes:
  - AgentLoopContract
  - AgentRegistryContract

Dependencies: capos.core.settings, capos.core.memory
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    AgentLoopContract,
    AgentRegistryContract,
    ExecutionHistoryContract,
    LLMClientContract,
    MarkdownMemoryContract,
    SecurityServiceContract,
    SettingsProvider,
    ToolRegistryContract,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class AgentPlugin:
    """Bootstraps AgentRegistry, ToolUseAdapter, and AgentLoop."""

    plugin_id: str = "capos.core.agent"
    plugin_name: str = "Agent"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings", "capos.core.memory"]

    def __init__(self) -> None:
        self.agent_registry: Any = None
        self.tool_use_adapter: Any = None
        self.agent_loop: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        # --- AgentRegistry ---
        try:
            from system.core.agent.agent_registry import AgentRegistry
            from system.sdk.contracts import DatabaseContract

            db = ctx.get_optional(DatabaseContract)
            self.agent_registry = AgentRegistry(
                data_path=workspace_root / "agents.json",
                db=db,
            )
            ctx.publish_service(AgentRegistryContract, self.agent_registry)
            logger.info("Published AgentRegistryContract")
        except Exception:
            logger.exception("Failed to create AgentRegistry")

        # --- ToolUseAdapter ---
        try:
            from system.core.agent.tool_use_adapter import ToolUseAdapter

            llm_client = ctx.get_optional(LLMClientContract)
            self.tool_use_adapter = ToolUseAdapter(llm_client=llm_client)
            logger.info("Created ToolUseAdapter")
        except Exception:
            logger.exception("Failed to create ToolUseAdapter")

        # --- AgentLoop ---
        try:
            from system.core.agent import AgentLoop

            tool_runtime = ctx.get_optional(ToolRuntimeContract)
            security_service = ctx.get_optional(SecurityServiceContract)
            tool_registry = ctx.get_optional(ToolRegistryContract)
            settings = ctx.get_optional(SettingsProvider)
            execution_history = ctx.get_optional(ExecutionHistoryContract)
            markdown_memory = ctx.get_optional(MarkdownMemoryContract)

            # max_iterations from settings
            max_iterations = 10
            if settings is not None:
                try:
                    all_settings = settings.get_settings(mask_secrets=False)
                    agent_cfg = all_settings.get("agent", {})
                    if isinstance(agent_cfg, dict):
                        max_iterations = int(agent_cfg.get("max_iterations", 10))
                except Exception:
                    pass

            # MemoryCompactor is an internal detail of the memory plugin
            memory_compactor = None
            try:
                from system.core.memory import MemoryCompactor  # noqa: F811

                if markdown_memory is not None:
                    memory_compactor = MemoryCompactor(
                        markdown_memory=markdown_memory,
                        max_context_tokens=4000,
                    )
            except Exception:
                pass

            self.agent_loop = AgentLoop(
                tool_use_adapter=self.tool_use_adapter,
                tool_runtime=tool_runtime,
                security_service=security_service,
                tool_registry=tool_registry,
                workspace_root=str(workspace_root),
                max_iterations=max_iterations,
                execution_history=execution_history,
                markdown_memory=markdown_memory,
                memory_compactor=memory_compactor,
            )
            ctx.publish_service(AgentLoopContract, self.agent_loop)
            logger.info("Published AgentLoopContract")
        except Exception:
            logger.exception("Failed to create AgentLoop")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import agent_handlers
        router.add("POST", "/agent", agent_handlers.start_agent)
        router.add("POST", "/agent/confirm", agent_handlers.confirm_action)
        router.add("GET", "/agent/{session_id}", agent_handlers.get_session)
        router.add("GET", "/agents", agent_handlers.list_agents)
        router.add("POST", "/agents", agent_handlers.create_agent)
        router.add("GET", "/agents/{agent_id}", agent_handlers.get_agent_def)
        router.add("POST", "/agents/{agent_id}", agent_handlers.update_agent)
        router.add("DELETE", "/agents/{agent_id}", agent_handlers.delete_agent)
        router.add("POST", "/agents/design", agent_handlers.design_agent)

    def start(self) -> None:
        """Agent subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """Agent subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> AgentPlugin:
    """Entry-point factory used by the plugin loader."""
    return AgentPlugin()
