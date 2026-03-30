"""MCP plugin — provides Model Context Protocol client, tool bridge,
and capability generator for MCP-connected servers.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    ToolRegistryContract,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class MCPPlugin:
    """Bootstraps MCPClientManager, MCPToolBridge, and MCPCapabilityGenerator."""

    plugin_id: str = "capos.core.mcp"
    plugin_name: str = "MCP"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.mcp_client_manager: Any = None
        self.mcp_tool_bridge: Any = None
        self.mcp_capability_generator: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        # --- MCPClientManager ---
        try:
            from system.core.mcp import MCPClientManager

            self.mcp_client_manager = MCPClientManager()
            logger.info("Created MCPClientManager")
            from system.sdk.contracts import MCPClientManagerContract
            ctx.publish_service(MCPClientManagerContract, self.mcp_client_manager)
        except Exception:
            logger.exception("Failed to create MCPClientManager")

        # --- MCPToolBridge ---
        try:
            from system.core.mcp import MCPToolBridge

            tool_registry = ctx.get_optional(ToolRegistryContract)
            tool_runtime = ctx.get_optional(ToolRuntimeContract)

            if tool_registry is not None and tool_runtime is not None:
                self.mcp_tool_bridge = MCPToolBridge(
                    tool_registry=tool_registry,
                    tool_runtime=tool_runtime,
                )
                logger.info("Created MCPToolBridge")
            else:
                logger.warning(
                    "ToolRegistry or ToolRuntime not available — skipping MCPToolBridge"
                )
        except Exception:
            logger.exception("Failed to create MCPToolBridge")

        # --- MCPCapabilityGenerator ---
        try:
            from system.core.mcp import MCPCapabilityGenerator

            if self.mcp_tool_bridge is not None:
                proposals_dir = workspace_root / "proposals"
                self.mcp_capability_generator = MCPCapabilityGenerator(
                    tool_bridge=self.mcp_tool_bridge,
                    proposals_dir=proposals_dir,
                )
                logger.info("Created MCPCapabilityGenerator")
        except Exception:
            logger.exception("Failed to create MCPCapabilityGenerator")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import mcp_handlers
        router.add("GET", "/mcp/servers", mcp_handlers.list_servers)
        router.add("POST", "/mcp/servers", mcp_handlers.add_server)
        router.add("DELETE", "/mcp/servers/{server_id}", mcp_handlers.remove_server)
        router.add("POST", "/mcp/servers/{server_id}/discover", mcp_handlers.discover_tools)
        router.add("GET", "/mcp/tools", mcp_handlers.list_tools)
        router.add("POST", "/mcp/tools/{tool_id}/install", mcp_handlers.install_tool)
        router.add("DELETE", "/mcp/tools/{tool_id}/uninstall", mcp_handlers.uninstall_tool)

    def start(self) -> None:
        """MCP subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """MCP subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> MCPPlugin:
    """Entry-point factory used by the plugin loader."""
    return MCPPlugin()
