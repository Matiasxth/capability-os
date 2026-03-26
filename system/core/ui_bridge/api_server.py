from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from system.capabilities.implementations import (
    Phase10WhatsAppCapabilityExecutor,
    Phase7CapabilityExecutionError,
    Phase7CapabilityExecutor,
)
from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import (
    CapabilityEngine,
    CapabilityExecutionError,
    CapabilityInputError,
)
from system.core.health import HealthService
from system.core.interpretation import IntentInterpreter, IntentInterpreterError, LLMClient
from system.core.observation import ObservationLogger
from system.core.planning import PlanBuildError, PlanBuilder, PlanValidator
from system.core.sequences import (
    SequenceRegistry,
    SequenceRunError,
    SequenceRunner,
    SequenceStorage,
    SequenceStorageError,
    SequenceValidationError,
)
from system.core.settings import SettingsService, SettingsValidationError
from system.integrations.registry import (
    IntegrationLoader,
    IntegrationLoaderError,
    IntegrationNotFoundError,
    IntegrationRegistry,
    IntegrationRegistryError,
    IntegrationValidationError,
    IntegrationValidator,
)
from system.shared.schema_validation import SchemaValidationError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools, register_phase9_browser_tools


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
        self.settings_service = SettingsService(self.workspace_root)
        runtime_settings = self.settings_service.load_settings()

        self.capability_registry = CapabilityRegistry()
        self.tool_registry = ToolRegistry()
        self._load_registries()
        self.integration_registry = IntegrationRegistry(self.integration_registry_data_path)
        self.integration_loader = IntegrationLoader(
            self.integrations_root,
            self.integration_manifest_schema_path,
            self.integration_registry,
        )
        self.integration_validator = IntegrationValidator(
            self.capability_registry,
            self.integration_manifest_schema_path,
        )
        self._refresh_integrations()

        self.tool_runtime = ToolRuntime(self.tool_registry, workspace_root=self.workspace_root)
        register_phase3_real_tools(self.tool_runtime, self.workspace_root)
        self.browser_session_manager = register_phase9_browser_tools(
            self.tool_runtime,
            self.workspace_root,
            artifacts_root=runtime_settings["workspace"]["artifacts_path"],
            auto_start=runtime_settings["browser"]["auto_start"],
        )
        self.engine = CapabilityEngine(self.capability_registry, self.tool_runtime)
        self.phase7_executor = Phase7CapabilityExecutor(self.capability_registry, self.engine)
        whatsapp_selectors_config = (
            self.project_root
            / "system"
            / "integrations"
            / "installed"
            / "whatsapp_web_connector"
            / "config"
            / "selectors.json"
        )
        self.phase10_whatsapp_executor = Phase10WhatsAppCapabilityExecutor(
            self.capability_registry,
            self.tool_runtime,
            whatsapp_selectors_config,
        )
        if llm_client is None:
            llm_client = LLMClient(
                settings_provider=lambda: self.settings_service.get_settings(mask_secrets=False).get("llm", {})
            )
        self.intent_interpreter = IntentInterpreter(self.capability_registry, llm_client=llm_client)
        self.plan_builder = PlanBuilder()
        self.plan_validator = PlanValidator(
            self.capability_registry,
            integration_status_resolver=self._integration_status,
        )
        self.sequence_storage = SequenceStorage(
            self.workspace_root,
            sequences_path=runtime_settings["workspace"]["sequences_path"],
        )
        self.sequence_registry = SequenceRegistry(self.sequence_storage)
        self.sequence_runner = SequenceRunner(
            sequence_registry=self.sequence_registry,
            capability_registry=self.capability_registry,
            capability_engine=self.engine,
            capability_executor=self._execute_capability_for_sequence_steps,
        )
        self.health_service = HealthService(
            settings_service=self.settings_service,
            browser_status_provider=self.browser_session_manager.status_snapshot,
            integrations_provider=self._list_integrations,
        )
        self._apply_runtime_settings(runtime_settings)

        self._executions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def _load_registries(self) -> None:
        capability_dir = self.project_root / "system" / "capabilities" / "contracts" / "v1"
        tool_dir = self.project_root / "system" / "tools" / "contracts" / "v1"
        self.capability_registry.load_from_directory(capability_dir)
        self.tool_registry.load_from_directory(tool_dir)

    def handle(self, method: str, path: str, payload: dict[str, Any] | None = None) -> APIResponse:
        clean_path = urlparse(path).path.rstrip("/") or "/"
        try:
            if method == "GET" and clean_path == "/status":
                return APIResponse(HTTPStatus.OK, self._status_snapshot())

            if method == "GET" and clean_path == "/health":
                return APIResponse(HTTPStatus.OK, self.health_service.get_system_health())

            if method == "GET" and clean_path == "/settings":
                return APIResponse(HTTPStatus.OK, {"settings": self.settings_service.get_settings(mask_secrets=True)})

            if method == "POST" and clean_path == "/settings":
                request = payload or {}
                return APIResponse(HTTPStatus.OK, self._save_settings(request))

            if method == "POST" and clean_path == "/llm/test":
                return APIResponse(HTTPStatus.OK, self._test_llm_connection())

            if method == "POST" and clean_path == "/browser/restart":
                return APIResponse(HTTPStatus.OK, self._restart_browser_worker())

            if method == "GET" and clean_path == "/capabilities":
                return APIResponse(HTTPStatus.OK, {"capabilities": self._list_capabilities()})

            if method == "GET" and clean_path.startswith("/capabilities/"):
                capability_id = clean_path.split("/", 2)[2]
                return APIResponse(HTTPStatus.OK, {"capability": self._get_capability(capability_id)})

            if method == "POST" and clean_path == "/execute":
                request = payload or {}
                result = self._execute_capability(request)
                return APIResponse(HTTPStatus.OK, result)

            if method == "POST" and clean_path == "/interpret":
                request = payload or {}
                result = self._interpret_text(request)
                return APIResponse(HTTPStatus.OK, result)

            if method == "POST" and clean_path == "/plan":
                request = payload or {}
                result = self._plan_intent(request)
                return APIResponse(HTTPStatus.OK, result)

            if method == "GET" and clean_path == "/integrations":
                return APIResponse(HTTPStatus.OK, {"integrations": self._list_integrations()})

            if clean_path.startswith("/integrations/"):
                suffix = clean_path[len("/integrations/") :]
                if method == "GET" and suffix and "/" not in suffix:
                    return APIResponse(HTTPStatus.OK, {"integration": self._inspect_integration(suffix)})

                if method == "POST" and suffix.endswith("/validate"):
                    integration_id = suffix[: -len("/validate")].rstrip("/")
                    return APIResponse(HTTPStatus.OK, self._validate_integration(integration_id))

                if method == "POST" and suffix.endswith("/enable"):
                    integration_id = suffix[: -len("/enable")].rstrip("/")
                    return APIResponse(HTTPStatus.OK, self._enable_integration(integration_id))

                if method == "POST" and suffix.endswith("/disable"):
                    integration_id = suffix[: -len("/disable")].rstrip("/")
                    return APIResponse(HTTPStatus.OK, self._disable_integration(integration_id))

            if method == "GET" and clean_path.startswith("/executions/"):
                suffix = clean_path[len("/executions/") :]
                if suffix.endswith("/events"):
                    execution_id = suffix[: -len("/events")].rstrip("/")
                    execution = self._get_execution(execution_id)
                    return APIResponse(
                        HTTPStatus.OK,
                        {
                            "execution_id": execution_id,
                            "events": execution["runtime"].get("logs", []),
                        },
                    )

                execution_id = suffix
                execution = self._get_execution(execution_id)
                return APIResponse(HTTPStatus.OK, execution)

            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "endpoint_not_found",
                f"Endpoint '{clean_path}' does not exist.",
            )
        except APIRequestError as exc:
            return APIResponse(
                exc.status_code,
                {
                    "status": "error",
                    "error_code": exc.error_code,
                    "error_message": exc.error_message,
                    "details": exc.details,
                },
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

        self._refresh_llm_client_settings()
        try:
            interpretation = self.intent_interpreter.interpret(intent)
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

    def _execute_capability(self, request: dict[str, Any]) -> dict[str, Any]:
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
                result = self.phase7_executor.execute(capability_id, inputs)
            if result is None:
                result = self.engine.execute(contract, inputs)
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

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _dispatch(self, method: str) -> None:
        service: CapabilityOSUIBridgeService = self.server.service  # type: ignore[attr-defined]
        try:
            payload = self._read_json_payload() if method == "POST" else None
            response = service.handle(method, self.path, payload)
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

        self.send_response(response.status_code)
        self._send_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response.payload, ensure_ascii=False).encode("utf-8"))

    def _send_headers(self) -> None:
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

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


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    workspace_root: str | Path | None = None,
) -> ThreadingHTTPServer:
    service = CapabilityOSUIBridgeService(workspace_root=workspace_root)
    server = ThreadingHTTPServer((host, port), CapabilityOSRequestHandler)
    server.service = service  # type: ignore[attr-defined]
    return server


if __name__ == "__main__":
    http_server = create_http_server()
    bound_host, bound_port = http_server.server_address
    print(f"Capability OS UI Bridge listening on http://{bound_host}:{bound_port}")
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http_server.server_close()
