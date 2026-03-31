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
        strict_contracts: bool = False,
        policy_engine: Any = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._project_root = Path(project_root).resolve()
        self._settings = settings
        self._event_bus = event_bus
        self._strict = strict_contracts
        self._policy_engine = policy_engine

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
        """Register a service implementation for a Protocol contract.

        In strict mode, raises ContractViolationError if validation fails.
        In default mode, logs warnings and registers anyway.
        """
        from system.sdk.validation import validate_contract
        violations = validate_contract(contract_type, implementation)
        if violations:
            if self._strict:
                from system.sdk.errors import ContractViolationError
                raise ContractViolationError(
                    contract_type.__name__,
                    type(implementation).__name__,
                    violations,
                )
            else:
                logger.warning(
                    f"Contract violations for {contract_type.__name__} "
                    f"({type(implementation).__name__}): {violations}"
                )
        self._services[contract_type] = implementation

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def get_service(self, contract_type: type) -> Any:
        if contract_type not in self._services:
            from system.sdk.errors import ServiceNotFoundError
            raise ServiceNotFoundError(contract_type.__name__)
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
            # Resolve plugin tags from manifest for policy enforcement
            manifest = self._manifests.get(pid)
            plugin_tags = manifest.tags if manifest and hasattr(manifest, "tags") else []

            ctx = PluginContext(
                workspace_root=self._workspace_root,
                project_root=self._project_root,
                settings=self._settings,
                service_getter=self.get_service,
                service_registrar=self.register_service,
                event_bus=self._event_bus,
                policy_engine=self._policy_engine,
                plugin_id=pid,
                plugin_tags=plugin_tags,
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
    # Route registration
    # ------------------------------------------------------------------

    def register_all_routes(self, router: Any) -> None:
        """Let every plugin with a register_routes() method declare its HTTP routes."""
        for pid in self._resolve_order():
            plugin = self._plugins.get(pid)
            if plugin is not None and hasattr(plugin, "register_routes"):
                try:
                    plugin.register_routes(router)
                    logger.debug(f"  Plugin [{pid}]: registered routes")
                except Exception as exc:
                    logger.error(f"  Plugin [{pid}]: route registration FAILED ({exc})")

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def check_plugin_health(self, plugin_id: str) -> dict[str, Any]:
        """Run health check on a single plugin."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"healthy": False, "message": f"Plugin '{plugin_id}' not found"}
        if self._states.get(plugin_id) != PluginState.RUNNING:
            return {"healthy": False, "message": f"Plugin not running (state: {self._states.get(plugin_id, '?')})"}
        if hasattr(plugin, "health_check") and callable(plugin.health_check):
            try:
                return plugin.health_check()
            except Exception as exc:
                return {"healthy": False, "message": f"Health check failed: {exc}"}
        return {"healthy": True, "message": "No health check declared"}

    def check_all_health(self) -> dict[str, dict[str, Any]]:
        """Run health checks on all running plugins."""
        return {pid: self.check_plugin_health(pid) for pid in self._plugins}

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
