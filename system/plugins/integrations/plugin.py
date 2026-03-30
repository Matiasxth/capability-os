"""Integrations plugin — manages IntegrationRegistry, Loader, and Validator.

Migrated from direct instantiation in api_server.py to the plugin pattern.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import CapabilityRegistryContract

logger = logging.getLogger(__name__)


class IntegrationsPlugin:
    """Bootstraps the integration registry, loader, and validator."""

    plugin_id: str = "capos.core.integrations"
    plugin_name: str = "Integrations"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.integration_registry: Any = None
        self.integration_loader: Any = None
        self.integration_validator: Any = None

    def initialize(self, ctx: PluginContext) -> None:
        project_root = ctx.project_root
        workspace_root = ctx.workspace_root

        integrations_root = project_root / "system" / "integrations" / "installed"
        manifest_schema = project_root / "system" / "integrations" / "contracts" / "integration_manifest.schema.json"
        registry_data_path = workspace_root / "system" / "integrations" / "registry_data.json"

        try:
            from system.integrations.registry import (
                IntegrationRegistry,
                IntegrationLoader,
                IntegrationValidator,
            )

            self.integration_registry = IntegrationRegistry(registry_data_path)

            self.integration_loader = IntegrationLoader(
                integrations_root, manifest_schema, self.integration_registry,
            )

            cap_registry = ctx.get_optional(CapabilityRegistryContract)
            self.integration_validator = IntegrationValidator(
                cap_registry, manifest_schema,
            )

            # Publish contract so other plugins/handlers can resolve it
            from system.sdk.contracts import IntegrationRegistryContract
            ctx.publish_service(IntegrationRegistryContract, self.integration_registry)

            logger.info("IntegrationRegistry initialized (%d integrations)", len(self.integration_registry.list_all() if hasattr(self.integration_registry, 'list_all') else []))
        except Exception:
            logger.exception("Failed to initialize IntegrationRegistry")

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def create_plugin() -> IntegrationsPlugin:
    return IntegrationsPlugin()
