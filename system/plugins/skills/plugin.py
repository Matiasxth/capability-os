"""Skills plugin — provides dynamic skill discovery and registration.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityRegistryContract,
    ToolRegistryContract,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class SkillsPlugin:
    """Bootstraps SkillRegistry and loads installed skills."""

    plugin_id: str = "capos.core.skills"
    plugin_name: str = "Skills"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.skill_registry: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        try:
            from system.core.skills import SkillRegistry

            capability_registry = ctx.get_optional(CapabilityRegistryContract)
            tool_registry = ctx.get_optional(ToolRegistryContract)
            tool_runtime = ctx.get_optional(ToolRuntimeContract)

            self.skill_registry = SkillRegistry(
                skills_dir=workspace_root / "skills",
                capability_registry=capability_registry,
                tool_registry=tool_registry,
                tool_runtime=tool_runtime,
            )

            # Load all installed skills from disk
            try:
                self.skill_registry.load_installed()
                logger.info("SkillRegistry loaded installed skills")
            except Exception:
                logger.exception("Failed to load installed skills")

            logger.info("Created SkillRegistry")
            from system.sdk.contracts import SkillRegistryContract
            ctx.publish_service(SkillRegistryContract, self.skill_registry)
        except Exception:
            logger.exception("Failed to create SkillRegistry")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import skill_handlers
        router.add("GET", "/skills", skill_handlers.list_skills)
        router.add("POST", "/skills/install", skill_handlers.install_skill)
        router.add("GET", "/skills/{skill_id}", skill_handlers.get_skill)
        router.add("DELETE", "/skills/{skill_id}", skill_handlers.uninstall_skill)
        router.add("POST", "/skills/hot-load", skill_handlers.hot_load)
        router.add("GET", "/skills/auto-generated", skill_handlers.list_created_skills)

    def start(self) -> None:
        """Skills are passive — nothing to start."""

    def stop(self) -> None:
        """Skills are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> SkillsPlugin:
    """Entry-point factory used by the plugin loader."""
    return SkillsPlugin()
