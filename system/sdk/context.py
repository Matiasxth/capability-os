"""PluginContext — the dependency injection surface passed to each plugin."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class PluginContext:
    """Immutable context provided to plugins during ``initialize()``.

    Plugins request shared services through ``get_service(ContractType)``
    which is the **only** way to access cross-plugin dependencies.
    """

    def __init__(
        self,
        workspace_root: Path,
        project_root: Path,
        settings: dict[str, Any],
        service_getter: Callable[[type], Any],
        service_registrar: Callable[[type, Any], None],
        event_bus: Any,
        policy_engine: Any = None,
        plugin_id: str = "",
        plugin_tags: list[str] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.settings = settings
        self._get_service = service_getter
        self._register_service = service_registrar
        self.event_bus = event_bus
        self._policy = policy_engine
        self._plugin_id = plugin_id
        self._plugin_tags = plugin_tags or []

    def get_service(self, contract_type: type) -> Any:
        """Resolve a service by its Protocol type.

        If a PolicyEngine is active and the plugin is not builtin, checks
        ``service.<ContractName>`` permission before resolving.

        Raises ``ServiceNotFoundError`` if no provider is registered.
        Raises ``PermissionDeniedError`` if policy denies access.
        """
        self._check_service_permission(contract_type)
        try:
            return self._get_service(contract_type)
        except KeyError:
            from system.sdk.errors import ServiceNotFoundError
            raise ServiceNotFoundError(contract_type.__name__)

    def get_optional(self, contract_type: type) -> Any | None:
        """Like ``get_service`` but returns ``None`` instead of raising."""
        try:
            return self._get_service(contract_type)
        except KeyError:
            return None

    def publish_service(self, contract_type: type, implementation: Any) -> None:
        """Publish an implementation for a contract so other plugins can use it."""
        self._register_service(contract_type, implementation)

    def _check_service_permission(self, contract_type: type) -> None:
        """Check if the current plugin has permission to access a service."""
        if self._policy is None:
            return  # No policy engine = no enforcement
        if "builtin" in self._plugin_tags:
            return  # Builtin plugins bypass policy checks

        service_name = contract_type.__name__
        decision = self._policy.evaluate(
            f"service.{service_name}",
            plugin_id=self._plugin_id,
            plugin_tags=self._plugin_tags,
        )
        if not decision["allowed"]:
            from system.sdk.errors import PermissionDeniedError
            raise PermissionDeniedError(
                self._plugin_id,
                f"service.{service_name}",
                decision.get("reason", ""),
            )

    def plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        """Get the settings section for a specific plugin.

        Convention: ``capos.channels.telegram`` -> ``settings["telegram"]``.
        """
        key = plugin_id.rsplit(".", 1)[-1] if "." in plugin_id else plugin_id
        section = self.settings.get(key, {})
        return section if isinstance(section, dict) else {}
