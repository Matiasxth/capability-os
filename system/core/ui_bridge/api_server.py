from __future__ import annotations

import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

# Only imports still used by methods remaining in this file.
# All other classes are resolved via plugins + ServiceContainer.
from system.core.interpretation import IntentInterpreterError, LLMClient
from system.core.a2a import A2AClient, A2AClientError, register_a2a_delegate_tool
from system.core.observation import ObservationLogger
from system.core.mcp import MCPClientError
from system.core.planning import PlanBuildError
from system.core.settings import SettingsService, SettingsValidationError
from system.shared.schema_validation import SchemaValidationError

# Imports for private methods still in this file (to be fully extracted in Phase 5 completion).
# These will be removed once the methods move to their service modules.
from system.capabilities.implementations import Phase7CapabilityExecutionError, Phase7CapabilityExecutor
from system.core.capability_engine import CapabilityExecutionError, CapabilityInputError
from system.integrations.registry import (
    IntegrationLoader, IntegrationLoaderError, IntegrationNotFoundError,
    IntegrationRegistry, IntegrationRegistryError, IntegrationValidationError, IntegrationValidator,
)
from system.core.self_improvement import CapabilityGeneratorError
from system.core.sequences import SequenceRunError, SequenceStorageError, SequenceValidationError


@dataclass
class APIResponse:
    status_code: int
    payload: dict[str, Any]


class APIRequestError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(error_message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}


class CapabilityOSUIBridgeService:
    """Local API bridge that exposes capabilities and execution runtime."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        llm_client: LLMClient | None = None,
        integrations_root: str | Path | None = None,
        integration_registry_data_path: str | Path | None = None,
    ):
        self.project_root = Path(__file__).resolve().parents[3]
        self.workspace_root = Path(workspace_root or self.project_root).resolve()
        self.integrations_root = Path(
            integrations_root
            or self.project_root / "system" / "integrations" / "installed"
        ).resolve()
        self.integration_registry_data_path = Path(
            integration_registry_data_path
            or self.workspace_root / "system" / "integrations" / "registry_data.json"
        ).resolve()
        self.integration_manifest_schema_path = (
            self.project_root / "system" / "integrations" / "contracts" / "integration_manifest.schema.json"
        )

        # ── ServiceContainer (replaces god-object wiring) ──
        self.settings_service = SettingsService(self.workspace_root)
        runtime_settings = self.settings_service.load_settings()

        # ── Load audit logger + policy engine ──
        from system.sdk.audit import AuditLogger
        from system.sdk.policy import PolicyEngine
        self.audit_logger = AuditLogger()
        policies_path = self.project_root / "system" / "core" / "security" / "policies.json"
        policy_engine = PolicyEngine.from_file(policies_path)
        policy_engine._audit_logger = self.audit_logger

        # ── Initialize ServiceContainer with all plugins ──
        from system.container import ServiceContainer
        from system.core.ui_bridge.event_bus import event_bus

        self.container = ServiceContainer(
            workspace_root=self.workspace_root,
            project_root=self.project_root,
            settings=runtime_settings,
            event_bus=event_bus,
            policy_engine=policy_engine,
        )
        self.policy_engine = policy_engine

        # Auto-discover and register all plugins from system/plugins/
        from system.container.plugin_loader import PluginLoader
        plugins_dir = self.project_root / "system" / "plugins"
        discovered = PluginLoader.load_from_directory(plugins_dir)
        for plugin, manifest in discovered:
            try:
                self.container.register_plugin(plugin, manifest)
            except Exception as exc:
                print(f"  Plugin registration failed ({manifest.id}): {exc}", flush=True)

        # If an external LLMClient was passed, publish it before initialization
        if llm_client is not None:
            from system.sdk.contracts import LLMClientContract
            self.container.register_service(LLMClientContract, llm_client)

        # ── Message Queue (Redis or in-memory fallback) ──
        from system.infrastructure.message_queue import create_queue
        self.message_queue = create_queue(runtime_settings)
        # EventBridge: bidirectional EventBus ↔ Redis (outbound + inbound)
        from system.infrastructure.event_bridge import EventBridge
        self._event_bridge = EventBridge(event_bus, self.message_queue)
        self._event_bridge.start()
        # Job Queue for async task execution
        from system.infrastructure.job_queue import JobQueue
        self.job_queue = JobQueue(self.message_queue)
        # Redis cache layer for storage acceleration
        from system.infrastructure.redis_cache import RedisCache
        self.redis_cache = RedisCache(self.message_queue)

        # ── Database (PostgreSQL or SQLite fallback) ──
        from system.infrastructure.database import create_database
        from system.sdk.contracts import DatabaseContract
        self.database = create_database(runtime_settings, self.workspace_root)
        self.container.register_service(DatabaseContract, self.database)
        if self.message_queue.is_redis:
            print("  Redis: connected (cache + events + workers)", flush=True)
        else:
            print("  Redis: not available (in-memory fallback)", flush=True)

        # Initialize all plugins (dependency-ordered)
        print("-- Initializing plugins --", flush=True)
        init_errors = self.container.initialize_all()
        for err in init_errors:
            print(f"  INIT ERROR: {err}", flush=True)

        # Start plugins with background services
        print("-- Starting plugins --", flush=True)
        start_errors = self.container.start_all()
        for err in start_errors:
            print(f"  START ERROR: {err}", flush=True)

        # ── Dynamic service resolution via __getattr__ ──
        # Handlers access service.xxx which resolves dynamically via
        # system/core/ui_bridge/service_resolver.py maps (CONTRACT_MAP + PLUGIN_ATTR_MAP).
        # Results are cached on the instance for O(1) subsequent access.
        # The settings_service is eagerly set since it was created before the container.
        from system.sdk.contracts import SettingsProvider
        self.settings_service = self.container.get_optional(SettingsProvider) or self.settings_service

        self._refresh_integrations()
        self._apply_late_bindings(runtime_settings)

        self._executions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._router = self._build_router()

    # ------------------------------------------------------------------
    # Dynamic attribute resolution (replaces ~80 static aliases)
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails (not in __dict__)
        from system.core.ui_bridge.service_resolver import resolve_attribute
        found, value = resolve_attribute(self.container, name)
        if found:
            # Cache on instance so __getattr__ won't fire again for this name
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def invalidate_alias_cache(self, plugin_id: str) -> None:
        """Clear cached attributes for a plugin after hot-reload."""
        from system.core.ui_bridge.service_resolver import PLUGIN_ATTR_MAP, CONTRACT_MAP
        for attr_name, (pid, _) in PLUGIN_ATTR_MAP.items():
            if pid == plugin_id and attr_name in self.__dict__:
                del self.__dict__[attr_name]
        # Also invalidate contract-based attrs since the impl may have changed
        for attr_name in CONTRACT_MAP:
            if attr_name in self.__dict__:
                del self.__dict__[attr_name]

    def _apply_late_bindings(self, runtime_settings: dict[str, Any]) -> None:
        """Wire cross-plugin dependencies that can't be resolved via DI."""
        # Scheduler multi-channel delivery
        if self.scheduler:
            if self.telegram_connector:
                self.scheduler._telegram = self.telegram_connector
            if self.slack_connector:
                self.scheduler._slack = self.slack_connector
            if self.discord_connector:
                self.scheduler._discord = self.discord_connector
            if self.whatsapp_manager:
                self.scheduler._whatsapp = self.whatsapp_manager

        # Interpreter needs workspace registry for context
        if self.intent_interpreter and self.workspace_registry:
            self.intent_interpreter._workspace_registry = self.workspace_registry

        # Path validator for filesystem tools
        try:
            from system.tools.implementations.phase3_tools import set_path_validator
            if self.path_validator:
                set_path_validator(self.path_validator)
        except Exception:
            pass

        # A2A known agents + delegate tool
        self._a2a_known_agents: list[dict[str, Any]] = list(
            runtime_settings.get("a2a", {}).get("known_agents", [])
        )
        try:
            register_a2a_delegate_tool(self.tool_registry, self.tool_runtime)
        except Exception:
            pass

    def _build_router(self):
        """Build HTTP router — plugins declare their own routes via register_routes()."""
        from system.core.ui_bridge.router import Router
        r = Router()
        self.container.register_all_routes(r)
        return r

    def _load_registries(self) -> None:
        capability_dir = self.project_root / "system" / "capabilities" / "contracts" / "v1"
        tool_dir = self.project_root / "system" / "tools" / "contracts" / "v1"
        self.capability_registry.load_from_directory(capability_dir)
        self.tool_registry.load_from_directory(tool_dir)

    def handle(self, method: str, path: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> APIResponse:
        clean_path = urlparse(path).path.rstrip("/") or "/"

        # Router-based dispatch (new system — migrated routes)
        match = self._router.dispatch(method, clean_path)
        if match is not None:
            try:
                return match.handler(self, payload, _raw_path=path, _headers=headers or {}, **match.params)
            except APIRequestError as exc:
                return APIResponse(exc.status_code, {"status": "error", "error_code": exc.error_code, "error_message": str(exc), "details": exc.details})
            except Exception as exc:
                try:
                    from system.core.ui_bridge.event_bus import event_bus
                    event_bus.emit("error", {"source": "handler", "path": clean_path, "message": str(exc)[:300]})
                except Exception:
                    pass
                return APIResponse(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error_code": "internal_error", "error_message": "An unexpected error occurred.", "details": {}})

        # All routes migrated to handler modules — only 404 fallback remains
        return APIResponse(
            HTTPStatus.NOT_FOUND,
            {"status": "error", "error_code": "endpoint_not_found", "error_message": f"Endpoint '{clean_path}' does not exist."},
        )

    def _list_capabilities(self) -> list[dict[str, Any]]:
        capabilities: list[dict[str, Any]] = []
        for contract in self.capability_registry.list_all():
            capabilities.append(
                {
                    "id": contract["id"],
                    "name": contract["name"],
                    "description": contract["description"],
                    "domain": contract["domain"],
                    "type": contract["type"],
                    "status": contract.get("lifecycle", {}).get("status"),
                }
            )
        return capabilities

    def _get_capability(self, capability_id: str) -> dict[str, Any]:
        contract = self.capability_registry.get(capability_id)
        if contract is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "capability_not_found",
                f"Capability '{capability_id}' is not registered.",
            )
        return contract

    def _refresh_integrations(self) -> None:
        try:
            self.integration_loader.discover()
        except IntegrationLoaderError as exc:
            raise APIRequestError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "integration_loader_error",
                str(exc),
            ) from exc

    def _list_integrations(self) -> list[dict[str, Any]]:
        self._refresh_integrations()
        items: list[dict[str, Any]] = []
        for entry in self.integration_registry.list_integrations():
            metadata = entry.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            items.append(
                {
                    "id": entry["id"],
                    "name": metadata.get("name", entry["id"]),
                    "type": metadata.get("type", "unknown"),
                    "status": entry["status"],
                    "capabilities": metadata.get("capabilities", []),
                }
            )
        return items

    def _inspect_integration(self, integration_id: str) -> dict[str, Any]:
        self._refresh_integrations()
        entry = self.integration_registry.get_integration(integration_id)
        if entry is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "integration_not_found",
                f"Integration '{integration_id}' is not registered.",
            )

        manifest = self.integration_loader.get_manifest(integration_id)
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "id": integration_id,
            "manifest": manifest,
            "status": entry["status"],
            "validated": entry.get("validated", False),
            "last_validated_at": entry.get("last_validated_at"),
            "error": entry.get("error"),
            "capabilities": metadata.get("capabilities", []),
            "metadata": metadata,
        }

    def _validate_integration(self, integration_id: str) -> dict[str, Any]:
        self._refresh_integrations()
        entry = self.integration_registry.get_integration(integration_id)
        if entry is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "integration_not_found",
                f"Integration '{integration_id}' is not registered.",
            )

        manifest = self.integration_loader.get_manifest(integration_id)
        if manifest is None:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "manifest_not_found",
                f"Integration '{integration_id}' has no discoverable manifest.",
            )

        try:
            result = self.integration_validator.validate(manifest)
            state = self.integration_registry.mark_validated(integration_id)
            return {
                "status": "success",
                "integration_id": integration_id,
                "validated": True,
                "result": result,
                "integration": self._format_integration_state(state),
                "error_code": None,
                "error_message": None,
            }
        except IntegrationValidationError as exc:
            state = self.integration_registry.mark_error(
                integration_id,
                str(exc),
            )
            return {
                "status": "error",
                "integration_id": integration_id,
                "validated": False,
                "integration": self._format_integration_state(state),
                "error_code": "integration_validation_error",
                "error_message": str(exc),
                "details": {"errors": exc.details},
            }

    def _enable_integration(self, integration_id: str) -> dict[str, Any]:
        self._refresh_integrations()
        try:
            state = self.integration_registry.enable(integration_id)
        except IntegrationNotFoundError as exc:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "integration_not_found",
                str(exc),
            ) from exc
        except IntegrationRegistryError as exc:
            raise APIRequestError(
                HTTPStatus.CONFLICT,
                "integration_not_validated",
                str(exc),
            ) from exc

        return {
            "status": "success",
            "integration_id": integration_id,
            "integration": self._format_integration_state(state),
            "error_code": None,
            "error_message": None,
        }

    def _disable_integration(self, integration_id: str) -> dict[str, Any]:
        self._refresh_integrations()
        try:
            state = self.integration_registry.disable(integration_id)
        except IntegrationNotFoundError as exc:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "integration_not_found",
                str(exc),
            ) from exc
        return {
            "status": "success",
            "integration_id": integration_id,
            "integration": self._format_integration_state(state),
            "error_code": None,
            "error_message": None,
        }

    @staticmethod
    def _format_integration_state(entry: dict[str, Any]) -> dict[str, Any]:
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "id": entry.get("id"),
            "name": metadata.get("name", entry.get("id")),
            "type": metadata.get("type", "unknown"),
            "status": entry.get("status"),
            "validated": entry.get("validated"),
            "last_validated_at": entry.get("last_validated_at"),
            "error": entry.get("error"),
            "capabilities": metadata.get("capabilities", []),
            "metadata": metadata,
        }

    def _ensure_integrations_enabled(self, capability_contract: dict[str, Any]) -> None:
        required_integrations = capability_contract.get("requirements", {}).get("integrations", [])
        if not isinstance(required_integrations, list):
            return
        if not required_integrations:
            return

        self._refresh_integrations()
        for integration_id in required_integrations:
            if not isinstance(integration_id, str) or not integration_id:
                continue
            state = self.integration_registry.get_integration(integration_id)
            if state is None:
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "integration_not_available",
                    f"Required integration '{integration_id}' is not discovered.",
                )
            status = state.get("status")
            if status != "enabled":
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "integration_not_enabled",
                    f"Required integration '{integration_id}' is not enabled (status='{status}').",
                    details={"integration_id": integration_id, "status": status},
                )

    def _interpret_text(self, request: dict[str, Any]) -> dict[str, Any]:
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Field 'text' is required and must be a non-empty string.",
            )
        self._refresh_llm_client_settings()
        try:
            return self.intent_interpreter.interpret(text)
        except IntentInterpreterError as exc:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "interpretation_error", str(exc)) from exc

    def _plan_intent(self, request: dict[str, Any]) -> dict[str, Any]:
        intent = request.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Field 'intent' is required and must be a non-empty string.",
            )
        history = request.get("conversation_history") or None

        self._refresh_llm_client_settings()
        try:
            interpretation = self.intent_interpreter.interpret(intent, history=history)
            plan = self.plan_builder.build(interpretation)
            validation = self.plan_validator.validate(plan)
        except (IntentInterpreterError, PlanBuildError) as exc:
            return {
                "type": "unknown",
                "suggest_only": True,
                "steps": [],
                "valid": False,
                "errors": [{"code": "planning_error", "message": str(exc)}],
                "intent": intent.strip(),
            }

        return {
            "type": plan["type"],
            "suggest_only": True,
            "steps": plan.get("steps", []),
            "valid": validation["valid"],
            "errors": validation["errors"],
            "intent": intent.strip(),
        }

    def _status_snapshot(self) -> dict[str, Any]:
        health = self.health_service.get_system_health()
        return {
            "llm": health["llm"],
            "browser_worker": health["browser_worker"],
            "integrations": health["integrations"],
        }

    def _save_settings(self, request: dict[str, Any]) -> dict[str, Any]:
        settings_payload = request.get("settings")
        if not isinstance(settings_payload, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Field 'settings' must be an object.",
            )
        try:
            saved = self.settings_service.save_settings(settings_payload)
        except SettingsValidationError as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "settings_validation_error",
                str(exc),
                details={"errors": exc.details},
            ) from exc

        self._apply_runtime_settings(saved)
        return {
            "status": "success",
            "settings": self.settings_service.get_settings(mask_secrets=True),
            "error_code": None,
            "error_message": None,
        }

    def _apply_runtime_settings(self, settings: dict[str, Any]) -> None:
        workspace_settings = settings.get("workspace", {})
        if isinstance(workspace_settings, dict):
            artifacts_path = workspace_settings.get("artifacts_path")
            sequences_path = workspace_settings.get("sequences_path")
            if isinstance(artifacts_path, str) and artifacts_path:
                self.browser_session_manager.set_artifacts_root(artifacts_path)
            if isinstance(sequences_path, str) and sequences_path:
                self.sequence_storage.configure_sequences_path(sequences_path)

        browser_settings = settings.get("browser", {})
        if isinstance(browser_settings, dict):
            auto_start = browser_settings.get("auto_start")
            if isinstance(auto_start, bool):
                self.browser_session_manager.set_auto_start(auto_start)
            backend = browser_settings.get("backend")
            if isinstance(backend, str) and backend in ("playwright", "cdp"):
                self.browser_session_manager.set_backend(backend)

        llm_settings = settings.get("llm")
        self._refresh_llm_client_settings(llm_settings if isinstance(llm_settings, dict) else None)

    def _refresh_llm_client_settings(self, llm_settings: dict[str, Any] | None = None) -> None:
        client = self.intent_interpreter.llm_client
        explicit_adapter = getattr(client, "_explicit_adapter", None)
        if explicit_adapter is not None:
            return
        configure = getattr(client, "configure_from_settings", None)
        if not callable(configure):
            return
        payload = llm_settings
        if payload is None:
            settings = self.settings_service.get_settings(mask_secrets=False)
            maybe_llm = settings.get("llm")
            payload = maybe_llm if isinstance(maybe_llm, dict) else {}
        configure(payload)

    def _test_llm_connection(self) -> dict[str, Any]:
        self._refresh_llm_client_settings()
        llm_settings = self.settings_service.get_settings(mask_secrets=False).get("llm", {})
        provider = llm_settings.get("provider", "unknown")
        model = llm_settings.get("model", "")
        try:
            response = self.intent_interpreter.llm_client.complete(
                system_prompt="You are a health check endpoint.",
                user_prompt="Respond with exactly: ok",
            )
        except Exception as exc:
            return {
                "status": "error",
                "provider": provider,
                "model": model,
                "error_code": "llm_connection_error",
                "error_message": str(exc),
            }

        return {
            "status": "success",
            "provider": provider,
            "model": model,
            "sample": response[:120],
            "error_code": None,
            "error_message": None,
        }

    def _restart_browser_worker(self) -> dict[str, Any]:
        status_snapshot = self.browser_session_manager.restart_worker()
        return {
            "status": "success",
            "browser_worker": status_snapshot,
            "error_code": None,
            "error_message": None,
        }

    def _cdp_status(self) -> dict[str, Any]:
        """Check if Chrome is running with CDP on the configured port."""
        cdp_port = self._get_cdp_port()
        try:
            from urllib.request import urlopen as _urlopen
            resp = _urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
            info = json.loads(resp.read().decode("utf-8"))
            tabs_resp = _urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=2)
            tabs = json.loads(tabs_resp.read().decode("utf-8"))
            wa_tabs = [t for t in tabs if isinstance(t, dict) and urlparse(t.get("url") or "").hostname == "web.whatsapp.com"]
            return {"connected": True, "tabs": len(tabs), "browser": info.get("Browser", ""), "port": cdp_port, "whatsapp_open": len(wa_tabs) > 0}
        except Exception:
            return {"connected": False, "tabs": 0, "browser": "", "port": cdp_port}

    def _connect_worker_to_cdp(self) -> dict[str, Any]:
        """Connect the browser worker to an already-running Chrome via CDP."""
        cdp_port = self._get_cdp_port()
        # Verify Chrome is running
        try:
            from urllib.request import urlopen as _urlopen
            _urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
        except Exception:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "chrome_not_running", f"Chrome is not running on port {cdp_port}.")
        # Update worker's CDP port and open a session
        self.browser_session_manager.set_cdp_port(cdp_port)
        try:
            session = self.browser_session_manager.open_session(
                {"headless": False},
                {"constraints": {"timeout_ms": 10000}},
            )
            return {"status": "success", "connected": True, "port": cdp_port, "session_id": session.get("session_id")}
        except Exception as exc:
            return {"status": "success", "connected": False, "port": cdp_port, "error": str(exc)}

    def _launch_chrome(self) -> dict[str, Any]:
        """Launch Chrome with remote debugging enabled."""
        import subprocess as _sp
        import sys as _sys
        import time as _time

        cdp_port = self._get_cdp_port()

        # Check if already running
        already_running = False
        try:
            from urllib.request import urlopen as _urlopen
            _urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=1)
            already_running = True
        except Exception:
            pass

        if not already_running:
            # Find Chrome executable
            chrome = self._find_chrome()
            if not chrome:
                raise APIRequestError(HTTPStatus.NOT_FOUND, "chrome_not_found", "Chrome executable not found. Install Google Chrome.")

            profile_dir = self.workspace_root / "workspace" / "chrome-profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            cmd = [chrome, f"--remote-debugging-port={cdp_port}", f"--user-data-dir={str(profile_dir)}", "--no-first-run", "--no-default-browser-check"]
            try:
                proc = _sp.Popen(cmd, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            except Exception as exc:
                raise APIRequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "chrome_launch_failed", str(exc)) from exc
            # Wait briefly for Chrome to start accepting CDP connections
            _time.sleep(1.5)

        # Restart worker so it picks up the CDP port, then connect
        worker_connected = False
        session_id = None
        result_error = ""
        try:
            self.browser_session_manager.set_cdp_port(cdp_port)
            self.browser_session_manager.restart_worker()
            import time as _time2
            _time2.sleep(1)
            session = self.browser_session_manager.open_session(
                {"headless": False},
                {"constraints": {"timeout_ms": 10000}},
            )
            worker_connected = True
            session_id = session.get("session_id")
        except Exception as _conn_exc:
            result_error = str(_conn_exc)

        result: dict[str, Any] = {"status": "success", "port": cdp_port, "worker_connected": worker_connected}
        if not worker_connected and result_error:
            result["worker_error"] = result_error
        if already_running:
            result["already_running"] = True
        else:
            result["launched"] = True
            result["pid"] = proc.pid
        if session_id:
            result["session_id"] = session_id
        return result

    def _open_whatsapp(self) -> dict[str, Any]:
        """Open WhatsApp Web in the CDP-connected Chrome."""
        cdp_port = self._get_cdp_port()
        try:
            from urllib.request import urlopen as _urlopen, Request as _Request
            body = json.dumps({"url": "https://web.whatsapp.com"}).encode("utf-8")
            req = _Request(f"http://127.0.0.1:{cdp_port}/json/new?https://web.whatsapp.com", method="PUT")
            resp = _urlopen(req, timeout=5)
            tab = json.loads(resp.read().decode("utf-8"))
            return {"status": "success", "tab_id": tab.get("id", ""), "url": "https://web.whatsapp.com"}
        except Exception as exc:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "whatsapp_open_failed", f"Failed to open WhatsApp: {exc}. Is Chrome running with debugging?") from exc

    def _start_whatsapp_worker(self) -> dict[str, Any]:
        """Start WhatsApp — tries Baileys first, falls back to browser bridge."""
        # Try Baileys first (fast, no browser)
        connector = self.phase10_whatsapp_executor.connector
        baileys = connector._get_baileys()
        if baileys is not None:
            try:
                result = baileys.ensure_connected(timeout_s=10.0)
                status = result.get("status", "unknown")
                # If Baileys works (QR or connected), use it
                if status in ("qr_required", "connected"):
                    response: dict[str, Any] = {"status": status, "backend": "baileys"}
                    if result.get("qr"):
                        response["qr"] = result["qr"]
                        response["qr_image"] = self._qr_to_data_url(result["qr"])
                    if result.get("user"):
                        response["user"] = result["user"]
                    response["connected"] = status == "connected"
                    return response
                # Baileys blocked/failed — fall through to browser bridge
            except Exception:
                pass

        # Fallback: browser bridge (Playwright headless)
        return self._start_whatsapp_browser_bridge()

    def _start_whatsapp_browser_bridge(self) -> dict[str, Any]:
        """Open WhatsApp Web in headless Playwright and capture QR."""
        if not hasattr(self, "_wsp_bridge"):
            try:
                from system.integrations.installed.whatsapp_web_connector.browser_bridge import BrowserBridge
                self._wsp_bridge = BrowserBridge()
            except ImportError:
                return {"status": "error", "error": "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"}

        bridge = self._wsp_bridge
        if not bridge.available:
            return {"status": "error", "error": "Playwright not available. Run: pip install playwright && python -m playwright install chromium"}

        result = bridge.start(timeout_s=25.0)
        result["backend"] = "browser"
        return result

    def _whatsapp_bridge_check(self) -> dict[str, Any]:
        """Poll the browser bridge for QR refresh or login detection."""
        if not hasattr(self, "_wsp_bridge"):
            return {"status": "idle", "connected": False}
        return self._wsp_bridge.check_login()

    def _whatsapp_bridge_close(self) -> dict[str, Any]:
        """Close the browser bridge session."""
        if not hasattr(self, "_wsp_bridge"):
            return {"status": "idle"}
        result = self._wsp_bridge.close()
        del self._wsp_bridge
        return result

    def _whatsapp_bridge_debug(self) -> dict[str, Any]:
        """Screenshot the bridge page for debugging."""
        if not hasattr(self, "_wsp_bridge"):
            return {"status": "idle"}
        return self._wsp_bridge.debug_screenshot()

    @staticmethod
    def _qr_to_data_url(qr_data: str) -> str | None:
        """Convert QR string to a data:image/png;base64 URL. Returns None if qrcode lib unavailable."""
        try:
            import base64
            import io
            import qrcode  # type: ignore
            img = qrcode.make(qr_data)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except ImportError:
            return None
        except Exception:
            return None

    def _get_cdp_port(self) -> int:
        try:
            return int(self.settings_service.load_settings().get("browser", {}).get("cdp_port", 0)) or 9222
        except Exception:
            return 9222

    @staticmethod
    def _find_chrome() -> str | None:
        """Find Chrome executable on Windows/Mac/Linux."""
        import sys as _sys
        candidates: list[str] = []
        if _sys.platform == "win32":
            for base in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("LOCALAPPDATA", "")]:
                if base:
                    candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
        elif _sys.platform == "darwin":
            candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        else:
            candidates.extend(["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"])
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Try PATH on Linux
        if _sys.platform != "win32":
            import shutil as _shutil
            for name in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]:
                found = _shutil.which(name)
                if found:
                    return found
        return None

    def _integration_status(self, integration_id: str) -> str | None:
        if not isinstance(integration_id, str) or not integration_id:
            return None
        self._refresh_integrations()
        state = self.integration_registry.get_integration(integration_id)
        if state is None:
            return None
        status = state.get("status")
        if isinstance(status, str):
            return status
        return None

    def _execute_capability(self, request: dict[str, Any], event_callback: Any = None) -> dict[str, Any]:
        capability_id = request.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Field 'capability_id' is required and must be a non-empty string.",
            )

        inputs = request.get("inputs", {})
        if not isinstance(inputs, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Field 'inputs' must be an object.",
            )

        contract = self.capability_registry.get(capability_id)
        if contract is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "capability_not_found",
                f"Capability '{capability_id}' is not registered.",
            )

        if capability_id in {"save_sequence", "load_sequence", "run_sequence"}:
            response = self._execute_sequence_capability(capability_id, inputs)
            self._store_execution(response)
            return response

        self._ensure_integrations_enabled(contract)

        try:
            result = self.phase10_whatsapp_executor.execute(capability_id, inputs)
            if result is None:
                result = self.telegram_executor.execute(capability_id, inputs)
            if result is None:
                result = self.slack_executor.execute(capability_id, inputs)
            if result is None:
                result = self.discord_executor.execute(capability_id, inputs)
            if result is None:
                result = self.phase7_executor.execute(capability_id, inputs)
            if result is None:
                result = self.engine.execute(contract, inputs, event_callback=event_callback)
            response = {
                "status": result["status"],
                "execution_id": result["execution_id"],
                "capability_id": result["capability_id"],
                "runtime": result["runtime"],
                "final_output": result["final_output"],
                "error_code": None,
                "error_message": None,
            }
            self._store_execution(response)
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("execution_complete", {"execution_id": response.get("execution_id"), "capability_id": capability_id, "status": "success"})
            except Exception:
                pass
            return response
        except Phase7CapabilityExecutionError as exc:
            runtime = exc.runtime_model
            execution_id = runtime.get("execution_id")
            response = {
                "status": "error",
                "execution_id": execution_id,
                "capability_id": capability_id,
                "runtime": runtime,
                "final_output": runtime.get("final_output", {}),
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
            if isinstance(execution_id, str) and execution_id:
                self._store_execution(response)
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("execution_complete", {"execution_id": execution_id, "capability_id": capability_id, "status": "error"})
            except Exception:
                pass
            return response
        except CapabilityExecutionError as exc:
            runtime = exc.runtime_model
            execution_id = runtime.get("execution_id")
            response = {
                "status": "error",
                "execution_id": execution_id,
                "capability_id": capability_id,
                "runtime": runtime,
                "final_output": runtime.get("final_output", {}),
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
            if isinstance(execution_id, str) and execution_id:
                self._store_execution(response)
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("execution_complete", {"execution_id": execution_id, "capability_id": capability_id, "status": "error"})
            except Exception:
                pass
            return response
        except (CapabilityInputError, SchemaValidationError) as exc:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "validation_error", str(exc)) from exc

    def _execute_sequence_capability(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        if capability_id == "save_sequence":
            return self._execute_save_sequence(inputs)
        if capability_id == "load_sequence":
            return self._execute_load_sequence(inputs)
        if capability_id == "run_sequence":
            try:
                run_result = self.sequence_runner.run(
                    sequence_id=inputs.get("sequence_id"),
                    sequence_definition=inputs.get("sequence_definition"),
                    sequence_inputs=inputs.get("inputs"),
                )
                return {
                    "status": run_result["status"],
                    "execution_id": run_result["execution_id"],
                    "capability_id": "run_sequence",
                    "runtime": run_result["runtime"],
                    "final_output": run_result["final_output"],
                    "error_code": None,
                    "error_message": None,
                }
            except SequenceRunError as exc:
                runtime = exc.runtime_model
                return {
                    "status": "error",
                    "execution_id": runtime.get("execution_id"),
                    "capability_id": "run_sequence",
                    "runtime": runtime,
                    "final_output": runtime.get("final_output", {}),
                    "error_code": exc.error_code,
                    "error_message": str(exc),
                }
            except (SequenceValidationError, SequenceStorageError) as exc:
                raise APIRequestError(HTTPStatus.BAD_REQUEST, "validation_error", str(exc)) from exc

        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            f"Unsupported sequence capability '{capability_id}'.",
        )

    def _execute_save_sequence(self, inputs: dict[str, Any]) -> dict[str, Any]:
        sequence_definition = inputs.get("sequence_definition")
        if not isinstance(sequence_definition, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "validation_error",
                "save_sequence requires 'sequence_definition' as an object.",
            )

        logger = ObservationLogger()
        logger.initialize("save_sequence")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        step_id = "save_sequence"
        try:
            logger.mark_step_started(step_id, {"sequence_definition": sequence_definition})
            sequence_id = self.sequence_registry.save_sequence(sequence_definition)
            output = {"status": "success", "sequence_id": sequence_id}
            logger.mark_step_succeeded(step_id, output, {"sequence_id": sequence_id})
            runtime = logger.finish(status="ready", final_output=output, state_snapshot={"sequence_id": sequence_id})
            return {
                "status": "success",
                "execution_id": runtime["execution_id"],
                "capability_id": "save_sequence",
                "runtime": runtime,
                "final_output": output,
                "error_code": None,
                "error_message": None,
            }
        except Exception as exc:
            error_code = "sequence_storage_error"
            logger.mark_step_failed(step_id, error_code, str(exc), {})
            runtime = logger.finish(
                status="error",
                final_output={},
                state_snapshot={},
                error_code=error_code,
                error_message=str(exc),
                failed_step=step_id,
            )
            return {
                "status": "error",
                "execution_id": runtime["execution_id"],
                "capability_id": "save_sequence",
                "runtime": runtime,
                "final_output": {},
                "error_code": error_code,
                "error_message": str(exc),
            }

    def _execute_load_sequence(self, inputs: dict[str, Any]) -> dict[str, Any]:
        sequence_id = inputs.get("sequence_id")
        if not isinstance(sequence_id, str) or not sequence_id:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "validation_error",
                "load_sequence requires 'sequence_id' as a non-empty string.",
            )

        logger = ObservationLogger()
        logger.initialize("load_sequence")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()

        step_id = "load_sequence"
        try:
            logger.mark_step_started(step_id, {"sequence_id": sequence_id})
            definition = self.sequence_registry.load_sequence(sequence_id)
            output = {"sequence_definition": definition}
            logger.mark_step_succeeded(step_id, output, {"sequence_id": sequence_id})
            runtime = logger.finish(status="ready", final_output=output, state_snapshot={"sequence_id": sequence_id})
            return {
                "status": "success",
                "execution_id": runtime["execution_id"],
                "capability_id": "load_sequence",
                "runtime": runtime,
                "final_output": output,
                "error_code": None,
                "error_message": None,
            }
        except Exception as exc:
            error_code = "sequence_storage_error"
            logger.mark_step_failed(step_id, error_code, str(exc), {"sequence_id": sequence_id})
            runtime = logger.finish(
                status="error",
                final_output={},
                state_snapshot={"sequence_id": sequence_id},
                error_code=error_code,
                error_message=str(exc),
                failed_step=step_id,
            )
            return {
                "status": "error",
                "execution_id": runtime["execution_id"],
                "capability_id": "load_sequence",
                "runtime": runtime,
                "final_output": {},
                "error_code": error_code,
                "error_message": str(exc),
            }

    def _execute_capability_sync(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a capability synchronously. Used by channel reply workers."""
        try:
            result = self._execute_capability({"capability_id": capability_id, "inputs": inputs})
            return result
        except Exception as exc:
            return {"status": "error", "error_message": str(exc)}

    def _store_execution(self, execution_response: dict[str, Any]) -> None:
        execution_id = execution_response.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            return
        with self._lock:
            self._executions[execution_id] = execution_response

    def _get_execution(self, execution_id: str) -> dict[str, Any]:
        with self._lock:
            execution = self._executions.get(execution_id)
        if execution is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "execution_not_found",
                f"Execution '{execution_id}' does not exist.",
            )
        return execution

    # ------------------------------------------------------------------
    # Auto-growth handlers
    # ------------------------------------------------------------------

    def _analyze_gap(self, gap_id: str) -> dict[str, Any]:
        gap = self.integration_detector.get_gap(gap_id)
        if gap is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "gap_not_found", f"Gap '{gap_id}' not found.")
        gap_input = {"capability_id": gap.get("suggested_capability"), "intent": gap.get("intent"), "description": gap.get("intent")}
        try:
            analysis = self.auto_install_pipeline._analyzer.analyze(gap_input)
            return {"status": "success", "gap_id": gap_id, "analysis": analysis}
        except Exception as exc:
            raise APIRequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "analysis_failed", str(exc)) from exc

    def _auto_generate_for_gap(self, gap_id: str) -> dict[str, Any]:
        gap = self.integration_detector.get_gap(gap_id)
        if gap is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "gap_not_found", f"Gap '{gap_id}' not found.")
        gap_input = {"id": gap_id, "capability_id": gap.get("suggested_capability"), "intent": gap.get("intent"), "description": gap.get("intent")}
        try:
            proposal = self.auto_install_pipeline.process_gap(gap_input)
            return {"status": "success", "proposal": proposal}
        except Exception as exc:
            raise APIRequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "generation_failed", str(exc)) from exc

    def _regenerate_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.auto_install_pipeline.get_proposal(proposal_id)
        if proposal is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "proposal_not_found", f"Proposal '{proposal_id}' not found.")
        gap_input = {"id": proposal.get("gap_id"), "capability_id": proposal.get("contract", {}).get("id"), "intent": proposal.get("suggestion", ""), "description": proposal.get("reason", "")}
        try:
            new_proposal = self.auto_install_pipeline.process_gap(gap_input)
            return {"status": "success", "proposal": new_proposal}
        except Exception as exc:
            raise APIRequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "regeneration_failed", str(exc)) from exc

    def _generate_capability_for_gap(self, gap_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        gap = self.integration_detector.get_gap(gap_id)
        if gap is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "gap_not_found",
                f"Gap '{gap_id}' does not exist.",
            )
        # Merge gap data with any overrides from the request body
        gen_input: dict[str, Any] = {
            "capability_id": gap.get("suggested_capability"),
            "intent": gap.get("intent"),
            "sample_intent": gap.get("intent"),
        }
        gen_input.update({k: v for k, v in payload.items() if v is not None})

        try:
            result = self.capability_generator.generate_proposal(gen_input)
        except CapabilityGeneratorError as exc:
            raise APIRequestError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "capability_generation_failed",
                str(exc),
                details=exc.details,
            ) from exc
        return {"status": "success", "proposal": result}

    # ------------------------------------------------------------------
    # Approval handlers (spec section 14: user confirms)
    # ------------------------------------------------------------------

    def _approve_gap(self, gap_id: str) -> dict[str, Any]:
        gap = self.integration_detector.get_gap(gap_id)
        if gap is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "gap_not_found", f"Gap '{gap_id}' not found.")
        resolved = self.integration_detector.resolve_gap(gap_id, "user_approved")
        return {"status": "success", "gap_id": gap_id, "gap": resolved}

    def _reject_gap(self, gap_id: str) -> dict[str, Any]:
        gap = self.integration_detector.get_gap(gap_id)
        if gap is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "gap_not_found", f"Gap '{gap_id}' not found.")
        closed = self.integration_detector.close_gap(gap_id, "user_rejected")
        return {"status": "success", "gap_id": gap_id, "gap": closed}

    def _approve_optimization(self, opt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        proposed_contract = payload.get("proposed_contract")
        if not isinstance(proposed_contract, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST, "missing_proposed_contract",
                "Field 'proposed_contract' is required in request body.",
            )
        capability_id = proposed_contract.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST, "invalid_contract",
                "Proposed contract must include a valid 'id'.",
            )
        # Write the approved contract to the v1 directory
        import json as _json
        contract_path = self.project_root / "system" / "capabilities" / "contracts" / "v1" / f"{capability_id}.json"
        contract_path.write_text(
            _json.dumps(proposed_contract, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Re-register in the live registry
        self.capability_registry.load_from_directory(
            self.project_root / "system" / "capabilities" / "contracts" / "v1"
        )
        return {"status": "success", "optimization_id": opt_id, "capability_id": capability_id, "applied": True}

    def _reject_optimization(self, opt_id: str) -> dict[str, Any]:
        return {"status": "success", "optimization_id": opt_id, "discarded": True}

    def _approve_proposal(self, capability_id: str) -> dict[str, Any]:
        contract = self.capability_generator.get_proposal(capability_id)
        if contract is None:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND, "proposal_not_found",
                f"Proposal '{capability_id}' does not exist.",
            )
        try:
            self.capability_registry.register(contract, source=f"proposal:{capability_id}")
        except Exception as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST, "proposal_invalid",
                f"Proposal contract failed validation: {exc}",
            ) from exc
        self.capability_generator.delete_proposal(capability_id)
        return {"status": "success", "capability_id": capability_id, "installed": True}

    def _reject_proposal(self, capability_id: str) -> dict[str, Any]:
        deleted = self.capability_generator.delete_proposal(capability_id)
        if not deleted:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND, "proposal_not_found",
                f"Proposal '{capability_id}' does not exist.",
            )
        return {"status": "success", "capability_id": capability_id, "deleted": True}

    # ------------------------------------------------------------------
    # MCP handlers
    # ------------------------------------------------------------------

    def _mcp_add_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = payload.get("server") or payload
        if not isinstance(config, dict) or not config.get("id"):
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "invalid_mcp_server", "Server config must include 'id'.")
        try:
            client = self.mcp_client_manager.add_server(config)
            client.connect()
            self._persist_mcp_server(config)
            return {"status": "success", "server": client.status()}
        except MCPClientError as exc:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=exc.details) from exc

    def _mcp_remove_server(self, server_id: str) -> dict[str, Any]:
        self.mcp_tool_bridge.unbridge_server(server_id)
        removed = self.mcp_client_manager.remove_server(server_id)
        if not removed:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "mcp_server_not_found", f"MCP server '{server_id}' not found.")
        self._unpersist_mcp_server(server_id)
        return {"status": "success", "server_id": server_id, "removed": True}

    def _persist_mcp_server(self, config: dict[str, Any]) -> None:
        """Save MCP server config to settings.json."""
        try:
            current = self.settings_service.load_settings()
            mcp = current.get("mcp", {})
            servers = mcp.get("servers", [])
            # Replace if same id exists, otherwise append
            servers = [s for s in servers if s.get("id") != config.get("id")]
            servers.append(config)
            mcp["servers"] = servers
            current["mcp"] = mcp
            self.settings_service.save_settings(current)
        except Exception:
            pass  # Don't break the add flow

    def _unpersist_mcp_server(self, server_id: str) -> None:
        """Remove MCP server config from settings.json."""
        try:
            current = self.settings_service.load_settings()
            mcp = current.get("mcp", {})
            servers = mcp.get("servers", [])
            mcp["servers"] = [s for s in servers if s.get("id") != server_id]
            current["mcp"] = mcp
            self.settings_service.save_settings(current)
        except Exception:
            pass

    def _mcp_discover_tools(self, server_id: str) -> dict[str, Any]:
        client = self.mcp_client_manager.get_client(server_id)
        if client is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "mcp_server_not_found", f"MCP server '{server_id}' not found.")
        try:
            registered = self.mcp_tool_bridge.bridge_server(client)
        except Exception as exc:
            raise APIRequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "mcp_discovery_failed", str(exc)) from exc
        return {"status": "success", "server_id": server_id, "tools_registered": len(registered), "tools": [t["id"] for t in registered]}

    def _mcp_install_tool(self, tool_id: str) -> dict[str, Any]:
        result = self.mcp_capability_generator.generate_for_tool(tool_id)
        if result is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "mcp_tool_not_found", f"MCP tool '{tool_id}' not found.")
        # Auto-register the capability so it's immediately usable
        contract = result.get("contract")
        if contract and isinstance(contract, dict):
            try:
                self.capability_registry.register(contract)
            except Exception:
                pass  # Already registered or validation error — don't block
        return {"status": "success", "proposal": result, "capability_id": result.get("capability_id")}

    def _mcp_uninstall_tool(self, tool_id: str) -> dict[str, Any]:
        removed = self.capability_registry.remove(tool_id)
        # Also try with mcp_ prefix in case the capability_id differs
        if not removed:
            removed = self.capability_registry.remove("mcp_" + tool_id)
        # Remove proposal file if it exists
        try:
            proposal_path = self.mcp_capability_generator._proposals_dir / f"{tool_id}.json"
            if proposal_path.exists():
                proposal_path.unlink()
        except Exception:
            pass
        if not removed:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "mcp_tool_not_found", f"Capability for tool '{tool_id}' not found.")
        return {"status": "success", "tool_id": tool_id, "uninstalled": True}

    # ------------------------------------------------------------------
    # A2A agent management handlers
    # ------------------------------------------------------------------

    def _a2a_list_agents(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for agent in self._a2a_known_agents:
            url = agent.get("url", "")
            entry: dict[str, Any] = {"id": agent.get("id", url), "url": url, "status": "unknown", "skills": agent.get("skills", [])}
            try:
                client = A2AClient(url, timeout_ms=3000)
                card = client.discover()
                entry["status"] = "reachable"
                entry["name"] = card.get("name")
                entry["skills"] = card.get("skills", [])
                # Update cached skills
                agent["skills"] = entry["skills"]
                agent["name"] = entry["name"]
            except Exception:
                entry["status"] = "error"
                entry["name"] = agent.get("name")
            results.append(entry)
        return results

    def _a2a_add_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = payload.get("url", "")
        agent_id = payload.get("id") or url
        if not url:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "invalid_a2a_agent", "Field 'url' is required.")
        entry: dict[str, Any] = {"id": agent_id, "url": url}
        # Discover agent card to get name and skills
        try:
            client = A2AClient(url, timeout_ms=5000)
            card = client.discover()
            entry["name"] = card.get("name")
            entry["skills"] = card.get("skills", [])
        except Exception:
            entry["skills"] = []
        self._a2a_known_agents = [a for a in self._a2a_known_agents if a.get("id") != agent_id]
        self._a2a_known_agents.append(entry)
        return {"status": "success", "agent": entry}

    def _a2a_remove_agent(self, agent_id: str) -> dict[str, Any]:
        before = len(self._a2a_known_agents)
        self._a2a_known_agents = [a for a in self._a2a_known_agents if a.get("id") != agent_id]
        if len(self._a2a_known_agents) == before:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "a2a_agent_not_found", f"Agent '{agent_id}' not found.")
        return {"status": "success", "removed": agent_id}

    def _a2a_delegate(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        agent = next((a for a in self._a2a_known_agents if a.get("id") == agent_id), None)
        if agent is None:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "a2a_agent_not_found", f"Agent '{agent_id}' not found.")
        skill_id = payload.get("skill_id", "")
        message = payload.get("message", "")
        if not skill_id:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "missing_skill_id", "Field 'skill_id' is required.")
        try:
            client = A2AClient(agent["url"])
            result = client.send_task(skill_id, message)
            return {"status": "success", "task": result}
        except A2AClientError as exc:
            raise APIRequestError(HTTPStatus.BAD_GATEWAY, exc.code, str(exc)) from exc

    def _execute_capability_for_sequence_steps(
        self, capability_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        contract = self.capability_registry.get(capability_id)
        if contract is None:
            raise SequenceValidationError(f"Unknown capability '{capability_id}'.")
        self._ensure_integrations_enabled(contract)

        result = self.phase10_whatsapp_executor.execute(capability_id, inputs)
        if result is None:
            result = self.phase7_executor.execute(capability_id, inputs)
        if result is not None:
            return result

        return self.engine.execute(contract, inputs)


class CapabilityOSRequestHandler(BaseHTTPRequestHandler):
    server_version = "CapabilityOSUIBridge/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _dispatch(self, method: str) -> None:
        # Rate limiting
        rate_limiter = getattr(self.server, "rate_limiter", None)
        if rate_limiter is not None:
            client_ip = self.client_address[0]
            if not rate_limiter.allow(client_ip):
                self.send_response(HTTPStatus.TOO_MANY_REQUESTS)
                self._send_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "error_code": "rate_limited", "error_message": "Too many requests. Try again later."}).encode("utf-8"))
                return

        # SSE streaming endpoint — handled directly, not through service.handle()
        if method == "POST" and self.path.split("?")[0] == "/chat/stream":
            self._handle_chat_stream()
            return
        if method == "POST" and self.path.split("?")[0] == "/execute/stream":
            self._handle_execute_stream()
            return
        if method == "POST" and self.path.split("?")[0] == "/agent/stream":
            self._handle_agent_stream()
            return

        service: CapabilityOSUIBridgeService = self.server.service  # type: ignore[attr-defined]
        try:
            payload = self._read_json_payload() if method in ("POST", "PUT") else None
            # Forward request headers so auth handlers can extract tokens
            req_headers = {k: v for k, v in self.headers.items()}
            response = service.handle(method, self.path, payload, headers=req_headers)
        except APIRequestError as exc:
            response = APIResponse(
                exc.status_code,
                {
                    "status": "error",
                    "error_code": exc.error_code,
                    "error_message": exc.error_message,
                    "details": exc.details,
                },
            )
        except Exception as exc:
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("error", {"source": "api_dispatch", "method": method, "path": self.path, "message": str(exc)[:300]})
            except Exception:
                pass
            response = APIResponse(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"status": "error", "error_code": "internal_error", "error_message": "An unexpected error occurred.", "details": {}},
            )

        self.send_response(response.status_code)
        self._send_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response.payload, ensure_ascii=False).encode("utf-8"))

    def _send_headers(self) -> None:
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")

    def _read_json_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        if not raw_body.strip():
            return {}
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body must be valid JSON.",
            ) from exc
        if not isinstance(payload, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body root must be an object.",
            )
        return payload

    def _handle_chat_stream(self) -> None:
        """SSE endpoint for streaming LLM chat responses."""
        service: CapabilityOSUIBridgeService = self.server.service  # type: ignore[attr-defined]
        try:
            body = self._read_json_payload() or {}
        except Exception:
            body = {}
        message = body.get("message", "")
        user_name = body.get("user_name", "User")
        history = body.get("conversation_history") or []

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            service._refresh_llm_client_settings()
            workspaces = service.intent_interpreter._get_workspace_context()
            from system.core.interpretation.prompts import build_chat_prompt
            system_prompt, user_prompt = build_chat_prompt(
                message, user_name, workspaces, history,
                capability_ids=service.capability_registry.ids(),
            )
            for chunk in service.intent_interpreter.llm_client.stream_complete(
                system_prompt=system_prompt, user_prompt=user_prompt,
            ):
                sse_line = f"data: {json.dumps({'chunk': chunk})}\n\n"
                self.wfile.write(sse_line.encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: {\"done\":true}\n\n")
            self.wfile.flush()
        except Exception as exc:
            self.wfile.write(f"data: {json.dumps({'error': str(exc)[:200]})}\n\n".encode("utf-8"))
            self.wfile.flush()


    def _handle_execute_stream(self) -> None:
        """SSE endpoint for streaming capability execution events."""
        import queue as _queue

        service: CapabilityOSUIBridgeService = self.server.service  # type: ignore[attr-defined]
        try:
            body = self._read_json_payload() or {}
        except Exception:
            body = {}

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        event_queue: _queue.Queue[dict[str, Any] | None] = _queue.Queue()

        def on_event(entry: dict[str, Any]) -> None:
            event_queue.put(entry)

        def run_execution() -> dict[str, Any] | None:
            try:
                return service._execute_capability(body, event_callback=on_event)
            except Exception as exc:
                event_queue.put({"event": "error", "timestamp": "", "payload": {"message": str(exc)[:300]}})
                return None
            finally:
                event_queue.put(None)  # sentinel

        import threading
        t = threading.Thread(target=lambda: event_queue.put(("__result__", run_execution())), daemon=True)

        # Simpler approach: run in same thread, callback writes to queue, drain after
        # Actually we need to stream events AS they happen. Use a thread:
        result_holder: list[Any] = [None]

        def _run() -> None:
            try:
                result_holder[0] = service._execute_capability(body, event_callback=on_event)
            except Exception as exc:
                event_queue.put({"event": "error", "timestamp": "", "payload": {"message": str(exc)[:300]}})
            finally:
                event_queue.put(None)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()

        try:
            while True:
                entry = event_queue.get(timeout=120)
                if entry is None:
                    break
                sse_line = f"data: {json.dumps(entry, default=str)}\n\n"
                self.wfile.write(sse_line.encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass

        # Send final result
        result = result_holder[0]
        if result is not None:
            done_payload = {"done": True, "result": {
                "status": result.get("status", "error"),
                "execution_id": result.get("execution_id", ""),
                "capability_id": result.get("capability_id", ""),
                "final_output": result.get("final_output", {}),
                "error_code": result.get("error_code"),
                "error_message": result.get("error_message"),
            }}
        else:
            done_payload = {"done": True, "result": {"status": "error", "error_message": "Execution failed"}}
        self.wfile.write(f"data: {json.dumps(done_payload, default=str)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _handle_agent_stream(self) -> None:
        """SSE endpoint for streaming agent loop events in real-time."""
        import threading

        service: CapabilityOSUIBridgeService = self.server.service  # type: ignore[attr-defined]
        try:
            body = self._read_json_payload() or {}
        except Exception:
            body = {}

        if not hasattr(service, "agent_loop"):
            self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Agent not available"}).encode())
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        message = body.get("message", "")
        session_id = body.get("session_id")
        history = body.get("history", [])
        agent_id = body.get("agent_id")
        workspace_id = body.get("workspace_id")

        agent_config = None
        if agent_id and hasattr(service, "agent_registry"):
            agent_config = service.agent_registry.get(agent_id)

        # Resolve workspace path for agent context
        ws_root = str(service.workspace_root)
        if workspace_id and hasattr(service, "workspace_registry"):
            ws = service.workspace_registry.get(workspace_id)
            if ws and ws.get("path"):
                ws_root = ws["path"]

        import queue as _queue
        event_queue: _queue.Queue[dict[str, Any] | None] = _queue.Queue()

        def _run() -> None:
            try:
                gen = service.agent_loop.run(message, session_id=session_id, conversation_history=history, agent_config=agent_config, workspace_id=workspace_id, workspace_path=ws_root)
                for event in gen:
                    event_queue.put(event)
            except StopIteration:
                pass
            except Exception as exc:
                event_queue.put({"event": "agent_error", "error": str(exc)[:300]})
            finally:
                event_queue.put(None)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()

        try:
            while True:
                event = event_queue.get(timeout=120)
                if event is None:
                    break
                sse_line = f"data: {json.dumps(event, default=str)}\n\n"
                self.wfile.write(sse_line.encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass

        self.wfile.write(b"data: {\"done\": true}\n\n")
        self.wfile.flush()


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    workspace_root: str | Path | None = None,
    ws_port: int | None = None,
) -> ThreadingHTTPServer:
    service = CapabilityOSUIBridgeService(workspace_root=workspace_root)
    from system.core.ui_bridge.rate_limiter import RateLimiter
    server = ThreadingHTTPServer((host, port), CapabilityOSRequestHandler)
    server.service = service  # type: ignore[attr-defined]
    server.rate_limiter = RateLimiter()  # type: ignore[attr-defined]
    server.ws_server = None  # type: ignore[attr-defined]
    if ws_port is not None:
        try:
            from system.core.ui_bridge.ws_server import start_ws_server
            from system.core.ui_bridge.event_bus import event_bus
            server.ws_server = start_ws_server(host, ws_port, event_bus)
        except Exception as exc:
            print(f"[WS] Failed to start WebSocket server: {exc}", flush=True)
    return server


if __name__ == "__main__":
    _http_port = int(os.environ.get("PORT", 8000))
    _ws_port = int(os.environ.get("WS_PORT", _http_port + 1))
    http_server = create_http_server(port=_http_port, ws_port=_ws_port)
    bound_host, bound_port = http_server.server_address
    print(f"Capability OS UI Bridge listening on http://{bound_host}:{bound_port}")
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if http_server.ws_server:
            http_server.ws_server.shutdown()
        http_server.server_close()
