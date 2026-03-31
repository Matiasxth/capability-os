"""Plugin type Protocols — each plugin implements one or more of these."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .context import PluginContext


@runtime_checkable
class BasePlugin(Protocol):
    """Every plugin must implement this base interface.

    Required: plugin_id, plugin_name, version, dependencies,
    initialize(), start(), stop().

    Optional lifecycle hooks (implement if needed):
    - health_check() — periodic health monitoring
    - get_state() / restore_state() — state persistence across hot-reloads
    - on_config_changed() — react to settings changes at runtime
    """

    @property
    def plugin_id(self) -> str: ...
    @property
    def plugin_name(self) -> str: ...
    @property
    def version(self) -> str: ...
    @property
    def dependencies(self) -> list[str]: ...

    def initialize(self, ctx: PluginContext) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...

    # Optional hooks — default implementations provided below
    # Plugins override these only if they need the functionality.


class PluginLifecycleHooks:
    """Mixin with default no-op implementations for optional lifecycle hooks.

    Plugins can inherit from this to get no-op defaults::

        class MyPlugin(PluginLifecycleHooks):
            plugin_id = "my.plugin"
            ...

            def health_check(self):
                return {"healthy": self._db.connected, "message": "DB check"}
    """

    def health_check(self) -> dict[str, Any]:
        """Return health status. Override to add custom checks."""
        return {"healthy": True, "message": "ok"}

    def get_state(self) -> dict[str, Any]:
        """Return serializable state for persistence across hot-reloads."""
        return {}

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state after a hot-reload. Called after initialize()."""
        pass

    def on_config_changed(self, new_config: dict[str, Any]) -> None:
        """Called when plugin settings change at runtime."""
        pass


@runtime_checkable
class ToolPlugin(BasePlugin, Protocol):
    """Registers tools into the ToolRuntime."""
    def register_tools(self, tool_registry: Any, tool_runtime: Any) -> list[str]: ...


@runtime_checkable
class ChannelPlugin(BasePlugin, Protocol):
    """Registers a messaging channel."""
    @property
    def channel_id(self) -> str: ...
    def get_status(self) -> dict[str, Any]: ...
    def configure(self, settings: dict[str, Any]) -> None: ...
    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]: ...
    def register_routes(self, router: Any) -> None: ...


@runtime_checkable
class MemoryPlugin(BasePlugin, Protocol):
    """Provides a memory backend."""
    def store(self, key: str, value: Any, **kw: Any) -> None: ...
    def retrieve(self, key: str) -> Any: ...
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...


@runtime_checkable
class AgentPlugin(BasePlugin, Protocol):
    """Registers agent types or behaviors."""
    def get_agent_types(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class UIPlugin(BasePlugin, Protocol):
    """Registers Control Center UI sections."""
    def get_ui_sections(self) -> list[dict[str, Any]]: ...
    def register_routes(self, router: Any) -> None: ...
