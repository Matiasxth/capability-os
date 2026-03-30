"""Browser plugin — registers Phase 9 browser automation tools
and manages the browser session.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    SettingsProvider,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class BrowserPlugin:
    """Registers browser tools into the ToolRuntime."""

    plugin_id: str = "capos.core.browser"
    plugin_name: str = "Browser"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.browser_session_manager: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root

        try:
            from system.tools.runtime import register_phase9_browser_tools

            tool_runtime = ctx.get_optional(ToolRuntimeContract)
            if tool_runtime is None:
                logger.warning("ToolRuntime not available — skipping browser tools")
                return

            settings = ctx.get_optional(SettingsProvider)
            browser_cfg: dict[str, Any] = {}
            if settings is not None:
                try:
                    all_settings = settings.get_settings(mask_secrets=False)
                    browser_cfg = all_settings.get("browser", {})
                    if not isinstance(browser_cfg, dict):
                        browser_cfg = {}
                except Exception:
                    pass

            self.browser_session_manager = register_phase9_browser_tools(
                tool_runtime=tool_runtime,
                workspace_root=workspace_root,
                auto_start=browser_cfg.get("auto_start", True),
                cdp_port=browser_cfg.get("cdp_port", 0),
                backend=browser_cfg.get("backend", "playwright"),
            )
            logger.info("Registered Phase 9 browser tools")
        except Exception:
            logger.exception("Failed to register browser tools")

    def start(self) -> None:
        """Browser tools are registered at init — nothing to start."""

    def stop(self) -> None:
        """Stop browser session if active."""
        if self.browser_session_manager is not None:
            try:
                if hasattr(self.browser_session_manager, "stop"):
                    self.browser_session_manager.stop()
                    logger.info("Browser session manager stopped")
            except Exception:
                logger.exception("Failed to stop browser session manager")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> BrowserPlugin:
    """Entry-point factory used by the plugin loader."""
    return BrowserPlugin()
