"""Sandbox plugin — provides process and Docker sandboxes for tool execution."""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext

logger = logging.getLogger(__name__)


class SandboxPlugin:
    plugin_id = "capos.core.sandbox"
    plugin_name = "Sandbox"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self) -> None:
        self.sandbox_manager = None

    def initialize(self, ctx: PluginContext) -> None:
        from system.core.sandbox import SandboxManager

        sandbox_settings = ctx.settings.get("sandbox", {})
        if not isinstance(sandbox_settings, dict):
            sandbox_settings = {}

        self.sandbox_manager = SandboxManager(
            workspace_root=str(ctx.workspace_root),
            process_timeout=sandbox_settings.get("process_timeout", 30),
            docker_timeout=sandbox_settings.get("docker_timeout", 60),
            docker_image=sandbox_settings.get("docker_image", "python:3.12-slim"),
            max_memory_mb=sandbox_settings.get("max_memory_mb", 512),
        )

        docker_status = "available" if self.sandbox_manager.docker_available else "not available"
        logger.info(f"Sandbox: process=ready, docker={docker_status}")

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def create_plugin() -> SandboxPlugin:
    return SandboxPlugin()
