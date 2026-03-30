"""ServiceContainer — replaces the god object.

Manages plugin registration, service resolution, dependency ordering,
and lifecycle (initialize -> start -> stop).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.lifecycle import PluginState
from system.sdk.manifest import PluginManifest

logger = logging.getLogger("capos.container")


class ServiceContainer:
    """Central orchestrator for plugin lifecycle and service resolution."""

    def __init__(
        self,
        workspace_root: Path,
        project_root: Path,
        settings: dict[str, Any],
        event_bus: Any,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._project_root = Path(project_root).resolve()
        self._settings = settings
        self._event_bus = event_bus

        self._plugins: dict[str, Any] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._states: dict[str, PluginState] = {}
        self._services: dict[type, Any] = {}
        self._init_errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_plugin(self, plugin: Any, manifest: PluginManifest | None = None) -> None:
        pid = plugin.plugin_id
        self._plugins[pid] = plugin
        if manifest:
            self._manifests[pid] = manifest
        self._states[pid] = PluginState.REGISTERED
        logger.debug(f"Registered plugin: {pid}")

    def register_service(self, contract_type: type, implementation: Any) -> None:
        # Validate that the implementation actually satisfies the Protocol
        if hasattr(contract_type, '__protocol_attrs__') or hasattr(contract_type, '__abstractmethods__'):
            if not isinstance(implementation, contract_type):
                logger.warning(
                    f"Contract violation: {type(implementation).__name__} "
                    f"does not fully implement {contract_type.__name__} — registering anyway"
                )
        self._services[contract_type] = implementation

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def get_service(self, contract_type: type) -> Any:
        if contract_type not in self._services:
            raise KeyError(
                f"No service for {contract_type.__name__}. "
                f"Available: {[t.__name__ for t in self._services]}"
            )
        return self._services[contract_type]

    def get_optional(self, contract_type: type) -> Any | None:
        return self._services.get(contract_type)

    def get_plugin(self, plugin_id: str) -> Any | None:
        return self._plugins.get(plugin_id)

    @property
    def plugins(self) -> dict[str, Any]:
        return dict(self._plugins)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def settings(self) -> dict[str, Any]:
        return self._settings

    @property
    def event_bus(self) -> Any:
        return self._event_bus

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize_all(self) -> list[str]:
        """Initialize all plugins in dependency order. Returns list of errors."""
        errors: list[str] = []
        for pid in self._resolve_order():
            err = self._initialize_one(pid)
            if err:
                errors.append(err)
        return errors

    def start_all(self) -> list[str]:
        errors: list[str] = []
        for pid in self._resolve_order():
            if self._states.get(pid) == PluginState.INITIALIZED:
                err = self._start_one(pid)
                if err:
                    errors.append(err)
        return errors

    def stop_all(self) -> None:
        for pid in reversed(self._resolve_order()):
            if self._states.get(pid) == PluginState.RUNNING:
                self._stop_one(pid)

    def _initialize_one(self, pid: str) -> str | None:
        plugin = self._plugins[pid]
        self._states[pid] = PluginState.INITIALIZING
        try:
            ctx = PluginContext(
                workspace_root=self._workspace_root,
                project_root=self._project_root,
                settings=self._settings,
                service_getter=self.get_service,
                service_registrar=self.register_service,
                event_bus=self._event_bus,
            )
            plugin.initialize(ctx)
            self._states[pid] = PluginState.INITIALIZED
            logger.info(f"  Plugin [{pid}]: initialized")
            return None
        except Exception as exc:
            self._states[pid] = PluginState.ERROR
            self._init_errors[pid] = str(exc)
            logger.error(f"  Plugin [{pid}]: FAILED ({exc})")
            return f"{pid}: {exc}"

    def _start_one(self, pid: str) -> str | None:
        plugin = self._plugins[pid]
        self._states[pid] = PluginState.STARTING
        try:
            plugin.start()
            self._states[pid] = PluginState.RUNNING
            logger.info(f"  Plugin [{pid}]: running")
            return None
        except Exception as exc:
            self._states[pid] = PluginState.ERROR
            logger.error(f"  Plugin [{pid}]: start FAILED ({exc})")
            return f"{pid}: {exc}"

    def _stop_one(self, pid: str) -> None:
        plugin = self._plugins[pid]
        self._states[pid] = PluginState.STOPPING
        try:
            plugin.stop()
            self._states[pid] = PluginState.STOPPED
        except Exception as exc:
            self._states[pid] = PluginState.ERROR
            logger.error(f"  Plugin [{pid}]: stop FAILED ({exc})")

    # ------------------------------------------------------------------
    # Dependency resolution (Kahn's topological sort)
    # ------------------------------------------------------------------

    def _resolve_order(self) -> list[str]:
        graph: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {pid: 0 for pid in self._plugins}

        for pid, plugin in self._plugins.items():
            deps = getattr(plugin, "dependencies", []) or []
            for dep in deps:
                if dep in self._plugins:
                    graph[dep].append(pid)
                    in_degree[pid] = in_degree.get(pid, 0) + 1

        queue = [pid for pid, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Append any unresolved (missing deps) at the end
        for pid in self._plugins:
            if pid not in order:
                order.append(pid)

        return order

    # ------------------------------------------------------------------
    # Status / Debug
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        return {
            pid: {
                "state": self._states.get(pid, PluginState.REGISTERED).value,
                "name": getattr(p, "plugin_name", pid),
                "version": getattr(p, "version", "?"),
                "error": self._init_errors.get(pid),
            }
            for pid, p in self._plugins.items()
        }
