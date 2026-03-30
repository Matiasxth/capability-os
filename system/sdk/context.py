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
    ) -> None:
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.settings = settings
        self._get_service = service_getter
        self._register_service = service_registrar
        self.event_bus = event_bus

    def get_service(self, contract_type: type) -> Any:
        """Resolve a service by its Protocol type.

        Raises ``KeyError`` if no provider is registered.
        """
        return self._get_service(contract_type)

    def get_optional(self, contract_type: type) -> Any | None:
        """Like ``get_service`` but returns ``None`` instead of raising."""
        try:
            return self._get_service(contract_type)
        except KeyError:
            return None

    def publish_service(self, contract_type: type, implementation: Any) -> None:
        """Publish an implementation for a contract so other plugins can use it."""
        self._register_service(contract_type, implementation)

    def plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        """Get the settings section for a specific plugin.

        Convention: ``capos.channels.telegram`` -> ``settings["telegram"]``.
        """
        key = plugin_id.rsplit(".", 1)[-1] if "." in plugin_id else plugin_id
        section = self.settings.get(key, {})
        return section if isinstance(section, dict) else {}
