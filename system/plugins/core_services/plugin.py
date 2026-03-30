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
        settings_service = SettingsService(workspace_root=workspace_root)
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

        # --- ToolRuntime ---
        tool_runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
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
