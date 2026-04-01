"""Core services plugin for Capability OS.

Wraps the foundational services that every other plugin depends on:
SettingsService, CapabilityRegistry, ToolRegistry, ToolRuntime,
SecurityService, HealthService, and MetricsCollector.
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityRegistryContract,
    HealthServiceContract,
    MetricsCollectorContract,
    SecurityServiceContract,
    SettingsProvider,
    ToolRegistryContract,
    ToolRuntimeContract,
)

from system.core.settings import SettingsService
from system.capabilities.registry import CapabilityRegistry
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools
from system.core.security import SecurityService
from system.core.health import HealthService
from system.core.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class CoreServicesPlugin:
    """Bootstraps all core passive services and publishes them to the container."""

    plugin_id: str = "capos.core.settings"
    plugin_name: str = "Core Services"
    version: str = "1.0.0"
    dependencies: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root
        project_root = ctx.project_root

        # --- SettingsService ---
        from system.sdk.contracts import DatabaseContract
        db = ctx.get_optional(DatabaseContract)
        settings_service = SettingsService(workspace_root=workspace_root, db=db)
        ctx.publish_service(SettingsProvider, settings_service)
        logger.info("Published SettingsProvider")

        # --- CapabilityRegistry ---
        capability_registry = CapabilityRegistry()
        cap_contracts_dir = project_root / "system" / "capabilities" / "contracts"
        _load_contracts(capability_registry, cap_contracts_dir, "capability")
        ctx.publish_service(CapabilityRegistryContract, capability_registry)
        logger.info(
            "Published CapabilityRegistryContract (%d contracts)",
            len(capability_registry),
        )

        # --- ToolRegistry ---
        tool_registry = ToolRegistry()
        tool_contracts_dir = project_root / "system" / "tools" / "contracts"
        _load_contracts(tool_registry, tool_contracts_dir, "tool")
        ctx.publish_service(ToolRegistryContract, tool_registry)
        logger.info(
            "Published ToolRegistryContract (%d contracts)", len(tool_registry)
        )

        # --- ToolRuntime (with dedicated execution pool) ---
        from system.infrastructure.tool_pool import ToolExecutionPool
        tool_pool = ToolExecutionPool()
        tool_runtime = ToolRuntime(tool_registry, workspace_root=workspace_root, tool_pool=tool_pool)
        register_phase3_real_tools(tool_runtime, workspace_root)
        ctx.publish_service(ToolRuntimeContract, tool_runtime)
        logger.info("Published ToolRuntimeContract")

        # --- SecurityService ---
        security_service = SecurityService(
            workspace_roots=[str(workspace_root)],
        )
        ctx.publish_service(SecurityServiceContract, security_service)
        logger.info("Published SecurityServiceContract")

        # --- HealthService ---
        health_service = HealthService(
            settings_service=settings_service,
            browser_status_provider=_null_browser_status,
            integrations_provider=_null_integrations,
        )
        ctx.publish_service(HealthServiceContract, health_service)
        logger.info("Published HealthServiceContract")

        # --- MetricsCollector ---
        data_dir = project_root / "memory"
        metrics_collector = MetricsCollector(
            data_path=data_dir / "metrics.json",
            traces_dir=data_dir / "traces",
        )
        ctx.publish_service(MetricsCollectorContract, metrics_collector)
        logger.info("Published MetricsCollectorContract")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import system_handlers, file_handlers, plugin_handlers
        # System
        router.add("GET", "/status", system_handlers.get_status)
        router.add("GET", "/health", system_handlers.get_health)
        router.add("GET", "/settings", system_handlers.get_settings)
        router.add("POST", "/settings", system_handlers.save_settings)
        router.add("POST", "/llm/test", system_handlers.test_llm)
        router.add("GET", "/system/export-config", system_handlers.export_config)
        router.add("POST", "/system/import-config", system_handlers.import_config)
        router.add("GET", "/logs", system_handlers.get_logs)
        # Files / Editor
        router.add("GET", "/files/tree", file_handlers.file_tree)
        router.add("GET", "/files/tree/{ws_id}", file_handlers.file_tree)
        router.add("GET", "/files/read", file_handlers.file_read)
        router.add("POST", "/files/write", file_handlers.file_write)
        router.add("POST", "/files/create", file_handlers.file_create)
        router.add("DELETE", "/files/delete", file_handlers.file_delete)
        router.add("POST", "/files/terminal", file_handlers.file_terminal)
        router.add("GET", "/files/analyze/{ws_id}", file_handlers.workspace_analyze)
        router.add("POST", "/files/auto-clean/{ws_id}", file_handlers.workspace_auto_clean)
        router.add("POST", "/files/generate-readme/{ws_id}", file_handlers.workspace_generate_readme)
        router.add("POST", "/files/suggest-structure", file_handlers.workspace_suggest_structure)
        # Plugin management
        router.add("GET", "/plugins", plugin_handlers.list_plugins)
        router.add("GET", "/plugins/{plugin_id}", plugin_handlers.get_plugin)
        router.add("POST", "/plugins/{plugin_id}/reload", plugin_handlers.reload_plugin)
        router.add("POST", "/plugins/install", plugin_handlers.install_plugin)

    def start(self) -> None:
        """Core services are passive — nothing to start."""

    def stop(self) -> None:
        """Core services are passive — nothing to stop."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _load_contracts(
    registry: CapabilityRegistry | ToolRegistry,
    contracts_dir: Any,
    label: str,
) -> None:
    """Load versioned contract directories (v1/, v2/, ...) into a registry."""
    from pathlib import Path

    contracts_path = Path(contracts_dir)
    if not contracts_path.exists():
        logger.warning("Contracts directory not found: %s", contracts_path)
        return

    # Load each versioned sub-directory (v1, v2, ...)
    version_dirs = sorted(
        d for d in contracts_path.iterdir() if d.is_dir() and d.name.startswith("v")
    )
    if version_dirs:
        for vdir in version_dirs:
            try:
                registry.load_from_directory(vdir)
                logger.debug("Loaded %s contracts from %s", label, vdir.name)
            except Exception:
                logger.exception("Failed to load %s contracts from %s", label, vdir)
    else:
        # Fallback: load JSON files directly from contracts_dir
        try:
            registry.load_from_directory(contracts_path)
        except Exception:
            logger.exception("Failed to load %s contracts from %s", label, contracts_path)


def _null_browser_status() -> dict[str, Any]:
    """Placeholder browser status until the browser plugin replaces it."""
    return {"transport": {"alive": False}, "backend": "playwright"}


def _null_integrations() -> list[dict[str, Any]]:
    """Placeholder integrations list until the integrations plugin replaces it."""
    return []


def create_plugin() -> CoreServicesPlugin:
    return CoreServicesPlugin()
