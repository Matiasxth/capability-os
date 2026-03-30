"""Workspace plugin — provides workspace management, path validation,
file browsing, and workspace context.

Publishes:
  - WorkspaceRegistryContract

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import WorkspaceRegistryContract

logger = logging.getLogger(__name__)


class WorkspacePlugin:
    """Bootstraps WorkspaceRegistry and supporting utilities."""

    plugin_id: str = "capos.core.workspace"
    plugin_name: str = "Workspace"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.workspace_registry: Any = None
        self.path_validator: Any = None
        self.file_browser: Any = None
        self.workspace_context: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        # --- WorkspaceRegistry ---
        try:
            from system.core.workspace import WorkspaceRegistry

            self.workspace_registry = WorkspaceRegistry(
                data_path=workspace_root / "workspaces.json",
            )
            ctx.publish_service(WorkspaceRegistryContract, self.workspace_registry)
            logger.info("Published WorkspaceRegistryContract")
        except Exception:
            logger.exception("Failed to create WorkspaceRegistry")

        # --- PathValidator ---
        try:
            from system.core.workspace import PathValidator

            self.path_validator = PathValidator(self.workspace_registry)
            logger.info("Created PathValidator")
        except Exception:
            logger.exception("Failed to create PathValidator")

        # --- FileBrowser ---
        try:
            from system.core.workspace import FileBrowser

            self.file_browser = FileBrowser(self.workspace_registry)
            logger.info("Created FileBrowser")
        except Exception:
            logger.exception("Failed to create FileBrowser")

        # --- WorkspaceContext ---
        try:
            from system.core.workspace import WorkspaceContext

            self.workspace_context = WorkspaceContext(self.workspace_registry)
            logger.info("Created WorkspaceContext")
        except Exception:
            logger.exception("Failed to create WorkspaceContext")

    def start(self) -> None:
        """Workspace subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """Workspace subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> WorkspacePlugin:
    """Entry-point factory used by the plugin loader."""
    return WorkspacePlugin()
