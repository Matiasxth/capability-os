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
from system.core.a2a import A2AClient, A2AClientError, A2AServer, AgentCardBuilder, register_a2a_delegate_tool
from system.core.memory import EmbeddingsEngine, ExecutionHistory, MemoryManager, SemanticMemory, UserContext, VectorStore
from system.core.workspace import FileBrowser, PathValidator, WorkspaceContext, WorkspaceRegistry
from system.core.metrics import MetricsCollector
from system.core.observation import ObservationLogger
from system.core.self_improvement import (
    AutoInstallPipeline,
    CapabilityGenerator,
    CapabilityGeneratorError,
    GapAnalyzer,
    PerformanceMonitor,
    RuntimeAnalyzer,
    StrategyOptimizer,
    ToolCodeGenerator,
    ToolValidator,
)
from system.core.mcp import MCPClientManager, MCPToolBridge, MCPCapabilityGenerator, MCPClientError
from system.integrations.bridge import CapabilityBridge
from system.integrations.classifier import IntegrationClassifier
from system.integrations.detector import IntegrationDetector
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

        self.metrics_collector = MetricsCollector(
            data_path=self.workspace_root / "artifacts" / "metrics.json",
            traces_dir=self.workspace_root / "artifacts" / "traces",
        )

        self.tool_runtime = ToolRuntime(self.tool_registry, workspace_root=self.workspace_root)
        register_phase3_real_tools(self.tool_runtime, self.workspace_root)
        self.browser_session_manager = register_phase9_browser_tools(
            self.tool_runtime,
            self.workspace_root,
            artifacts_root=runtime_settings["workspace"]["artifacts_path"],
            auto_start=runtime_settings["browser"]["auto_start"],
            cdp_port=runtime_settings["browser"].get("cdp_port", 0),
            auto_restart_max_retries=runtime_settings["browser"].get("auto_restart_max_retries", 2),
        )
        self.execution_history = ExecutionHistory(
            data_path=self.workspace_root / "memory" / "history.json",
        )
        self.memory_manager = MemoryManager(
            data_path=self.workspace_root / "memory" / "memories.json",
        )
        self.user_context = UserContext(
            memory=self.memory_manager,
            metrics=self.metrics_collector,
        )
        self.embeddings_engine = EmbeddingsEngine(
            vocab_path=self.workspace_root / "memory" / "tfidf_vocab.json",
        )
        self.vector_store = VectorStore(
            data_path=self.workspace_root / "memory" / "vectors.json",
        )
        self.semantic_memory = SemanticMemory(
            memory_manager=self.memory_manager,
            vector_store=self.vector_store,
            embeddings_engine=self.embeddings_engine,
        )
        self.engine = CapabilityEngine(
            self.capability_registry, self.tool_runtime,
            metrics_collector=self.metrics_collector,
            execution_history=self.execution_history,
            semantic_memory=self.semantic_memory,
        )
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

        self.integration_detector = IntegrationDetector()
        self.gap_analyzer = GapAnalyzer(
            detector=self.integration_detector,
            classifier=IntegrationClassifier(),
        )
        self.performance_monitor = PerformanceMonitor(
            metrics_collector=self.metrics_collector,
        )
        self.strategy_optimizer = StrategyOptimizer(
            performance_monitor=self.performance_monitor,
            capability_registry=self.capability_registry,
        )
        self.capability_generator = CapabilityGenerator(
            llm_client=self.intent_interpreter.llm_client,
            capability_registry=self.capability_registry,
            proposals_dir=self.workspace_root / "proposals",
        )
        from system.core.self_improvement.python_sandbox import PythonSandbox
        from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
        self.auto_install_pipeline = AutoInstallPipeline(
            runtime_analyzer=RuntimeAnalyzer(tool_registry=self.tool_registry),
            capability_generator=self.capability_generator,
            tool_code_generator=ToolCodeGenerator(llm_client=self.intent_interpreter.llm_client),
            tool_validator=ToolValidator(
                python_sandbox=PythonSandbox(self.workspace_root / "sandbox" / "py"),
                nodejs_sandbox=NodejsSandbox(self.workspace_root / "sandbox" / "js"),
                llm_client=self.intent_interpreter.llm_client,
            ),
            tool_registry=self.tool_registry,
            tool_runtime=self.tool_runtime,
            capability_registry=self.capability_registry,
            proposals_dir=self.workspace_root / "proposals" / "auto",
        )
        self.capability_bridge = CapabilityBridge(
            capability_registry=self.capability_registry,
            integrations_root=self.integrations_root,
            global_contracts_dir=self.project_root / "system" / "capabilities" / "contracts" / "v1",
        )

        self.workspace_registry = WorkspaceRegistry(
            data_path=self.workspace_root / "workspaces.json",
        )
        self.path_validator = PathValidator(self.workspace_registry)
        self.workspace_context = WorkspaceContext(self.workspace_registry)
        self.file_browser = FileBrowser(self.workspace_registry)
        # Wire workspace context into intent interpreter (late binding)
        self.intent_interpreter._workspace_registry = self.workspace_registry
        # Wire path validator into filesystem tools (late binding)
        try:
            from system.tools.implementations.phase3_tools import set_path_validator
            set_path_validator(self.path_validator)
        except Exception:
            pass

        mcp_settings = runtime_settings.get("mcp", {})
        self.mcp_client_manager = MCPClientManager(
            default_timeout_ms=mcp_settings.get("server_timeout_ms", 10000),
        )
        self.mcp_tool_bridge = MCPToolBridge(
            tool_registry=self.tool_registry,
            tool_runtime=self.tool_runtime,
        )
        self.mcp_capability_generator = MCPCapabilityGenerator(
            tool_bridge=self.mcp_tool_bridge,
            proposals_dir=self.workspace_root / "proposals" / "mcp",
        )
        self.agent_card_builder = AgentCardBuilder(
            capability_registry=self.capability_registry,
            server_url=runtime_settings.get("a2a", {}).get("server_url", "http://localhost:8000"),
        )
        self.a2a_server = A2AServer(
            capability_registry=self.capability_registry,
            capability_engine=self.engine,
        )
        self._a2a_known_agents: list[dict[str, Any]] = list(
            runtime_settings.get("a2a", {}).get("known_agents", [])
        )
        try:
            register_a2a_delegate_tool(self.tool_registry, self.tool_runtime)
        except Exception:
            pass

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
            if method == "GET" and clean_path == "/.well-known/agent.json":
                return APIResponse(HTTPStatus.OK, self.agent_card_builder.build())

            if method == "POST" and clean_path == "/a2a":
                result = self.a2a_server.handle_task(payload or {})
                return APIResponse(HTTPStatus.OK, result)

            if method == "GET" and clean_path.startswith("/a2a/") and clean_path.endswith("/events"):
                task_id = clean_path[len("/a2a/"):-len("/events")]
                events = self.a2a_server.list_events(task_id)
                if events is None:
                    raise APIRequestError(HTTPStatus.NOT_FOUND, "task_not_found", f"Task '{task_id}' not found.")
                return APIResponse(HTTPStatus.OK, {"task_id": task_id, "events": events})

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

            if method == "GET" and clean_path == "/metrics":
                return APIResponse(HTTPStatus.OK, {"metrics": self.metrics_collector.get_metrics()})

            if method == "GET" and clean_path == "/gaps/pending":
                return APIResponse(HTTPStatus.OK, {"gaps": self.gap_analyzer.get_actionable_gaps()})

            if clean_path.startswith("/gaps/") and clean_path.endswith("/analyze") and method == "POST":
                gap_id = clean_path[len("/gaps/"):-len("/analyze")]
                return APIResponse(HTTPStatus.OK, self._analyze_gap(gap_id))

            if clean_path.startswith("/gaps/") and clean_path.endswith("/generate") and method == "POST":
                gap_id = clean_path[len("/gaps/"):-len("/generate")]
                return APIResponse(HTTPStatus.OK, self._auto_generate_for_gap(gap_id))

            if method == "GET" and clean_path == "/proposals":
                return APIResponse(HTTPStatus.OK, {"proposals": self.auto_install_pipeline.list_proposals()})

            if clean_path.startswith("/proposals/") and clean_path.endswith("/regenerate") and method == "POST":
                prop_id = clean_path[len("/proposals/"):-len("/regenerate")]
                return APIResponse(HTTPStatus.OK, self._regenerate_proposal(prop_id))

            if method == "GET" and clean_path == "/capabilities/health":
                return APIResponse(HTTPStatus.OK, {"suggestions": self.performance_monitor.get_improvement_suggestions()})

            if method == "GET" and clean_path == "/optimizations/pending":
                return APIResponse(HTTPStatus.OK, {"proposals": self.strategy_optimizer.get_optimization_proposals()})

            # --- Approval endpoints (spec section 14: user confirms) ---

            if clean_path.startswith("/gaps/") and clean_path.endswith("/approve") and method == "POST":
                gap_id = clean_path[len("/gaps/"):-len("/approve")]
                return APIResponse(HTTPStatus.OK, self._approve_gap(gap_id))

            if clean_path.startswith("/gaps/") and clean_path.endswith("/reject") and method == "POST":
                gap_id = clean_path[len("/gaps/"):-len("/reject")]
                return APIResponse(HTTPStatus.OK, self._reject_gap(gap_id))

            if clean_path.startswith("/optimizations/") and clean_path.endswith("/approve") and method == "POST":
                opt_id = clean_path[len("/optimizations/"):-len("/approve")]
                return APIResponse(HTTPStatus.OK, self._approve_optimization(opt_id, payload or {}))

            if clean_path.startswith("/optimizations/") and clean_path.endswith("/reject") and method == "POST":
                opt_id = clean_path[len("/optimizations/"):-len("/reject")]
                return APIResponse(HTTPStatus.OK, self._reject_optimization(opt_id))

            if clean_path.startswith("/proposals/") and clean_path.endswith("/approve") and method == "POST":
                cap_id = clean_path[len("/proposals/"):-len("/approve")]
                return APIResponse(HTTPStatus.OK, self._approve_proposal(cap_id))

            if clean_path.startswith("/proposals/") and clean_path.endswith("/reject") and method == "POST":
                cap_id = clean_path[len("/proposals/"):-len("/reject")]
                return APIResponse(HTTPStatus.OK, self._reject_proposal(cap_id))

            if method == "GET" and clean_path == "/capabilities":
                return APIResponse(HTTPStatus.OK, {"capabilities": self._list_capabilities()})

            if method == "GET" and clean_path.startswith("/capabilities/"):
                capability_id = clean_path.split("/", 2)[2]
                return APIResponse(HTTPStatus.OK, {"capability": self._get_capability(capability_id)})

            if method == "POST" and clean_path == "/execute":
                request = payload or {}
                result = self._execute_capability(request)
                return APIResponse(HTTPStatus.OK, result)

            if method == "POST" and clean_path == "/chat":
                body = payload or {}
                message = body.get("message", "")
                user_name = body.get("user_name", "User")
                history = body.get("conversation_history") or []
                if not isinstance(message, str) or not message.strip():
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "invalid_input", "A non-empty 'message' is required.")
                self._refresh_llm_client_settings()
                msg_type = self.intent_interpreter.classify_message(message, history)
                if msg_type == "conversational":
                    response_text = self.intent_interpreter.chat_response(message, user_name, history)
                    return APIResponse(HTTPStatus.OK, {"type": "chat", "response": response_text})
                # For confirmations with a suggested_action, pass it back
                suggested = None
                for msg in reversed(history):
                    if msg.get("role") in ("assistant", "system") and msg.get("suggested_action"):
                        suggested = msg["suggested_action"]
                        break
                return APIResponse(HTTPStatus.OK, {"type": "action", "suggested_action": suggested})

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

            # --- MCP endpoints ---

            if method == "GET" and clean_path == "/mcp/servers":
                return APIResponse(HTTPStatus.OK, {"servers": self.mcp_client_manager.list_servers()})

            if method == "POST" and clean_path == "/mcp/servers":
                return APIResponse(HTTPStatus.OK, self._mcp_add_server(payload or {}))

            if clean_path.startswith("/mcp/servers/") and method == "DELETE":
                server_id = clean_path[len("/mcp/servers/"):]
                return APIResponse(HTTPStatus.OK, self._mcp_remove_server(server_id))

            if clean_path.startswith("/mcp/servers/") and clean_path.endswith("/discover") and method == "POST":
                server_id = clean_path[len("/mcp/servers/"):-len("/discover")]
                return APIResponse(HTTPStatus.OK, self._mcp_discover_tools(server_id))

            if method == "GET" and clean_path == "/mcp/tools":
                return APIResponse(HTTPStatus.OK, {"tools": self.mcp_tool_bridge.list_bridged_tools()})

            if clean_path.startswith("/mcp/tools/") and clean_path.endswith("/install") and method == "POST":
                tool_id = clean_path[len("/mcp/tools/"):-len("/install")]
                return APIResponse(HTTPStatus.OK, self._mcp_install_tool(tool_id))

            # --- Memory endpoints ---

            if method == "GET" and clean_path == "/memory/context":
                return APIResponse(HTTPStatus.OK, {"context": self.user_context.get_context()})

            if method == "GET" and clean_path == "/memory/history":
                cap_filter = None
                if "?" in path:
                    from urllib.parse import parse_qs
                    qs = parse_qs(urlparse(path).query)
                    cap_filter = qs.get("capability_id", [None])[0]
                if cap_filter:
                    entries = self.execution_history.get_by_capability(cap_filter)
                else:
                    entries = self.execution_history.get_recent(20)
                return APIResponse(HTTPStatus.OK, {"history": entries})

            if method == "POST" and clean_path == "/memory/history/chat":
                body = payload or {}
                session_id = body.get("session_id", "")
                if not session_id:
                    from datetime import datetime, timezone
                    session_id = f"chat_{datetime.now(timezone.utc).isoformat().replace(':', '-')}"
                exec_id = self.execution_history.upsert_chat(
                    session_id=session_id,
                    intent=body.get("intent", ""),
                    messages=body.get("messages"),
                    duration_ms=body.get("duration_ms", 0),
                )
                return APIResponse(HTTPStatus.OK, {"status": "success", "id": exec_id})

            if clean_path.startswith("/memory/history/") and method == "DELETE":
                exec_id = clean_path[len("/memory/history/"):]
                deleted = self.execution_history.delete(exec_id)
                if not deleted:
                    raise APIRequestError(HTTPStatus.NOT_FOUND, "entry_not_found", f"History entry '{exec_id}' not found.")
                return APIResponse(HTTPStatus.OK, {"status": "success", "deleted": exec_id})

            if method == "POST" and clean_path == "/memory/sessions":
                body = payload or {}
                exec_id = self.execution_history.record_session(
                    intent=body.get("intent", ""),
                    plan_steps=body.get("plan_steps", []),
                    step_runs=body.get("step_runs", []),
                    status=body.get("status", "unknown"),
                    duration_ms=body.get("duration_ms", 0),
                    error_message=body.get("error_message"),
                    failed_step=body.get("failed_step"),
                    final_output=body.get("final_output", {}),
                )
                return APIResponse(HTTPStatus.OK, {"status": "success", "id": exec_id})

            if clean_path.startswith("/memory/sessions/") and method == "GET":
                exec_id = clean_path[len("/memory/sessions/"):]
                entry = self.execution_history.get_session(exec_id)
                if entry is None:
                    raise APIRequestError(HTTPStatus.NOT_FOUND, "session_not_found", f"Session '{exec_id}' not found.")
                return APIResponse(HTTPStatus.OK, {"session": entry})

            if method == "GET" and clean_path == "/memory/preferences":
                return APIResponse(HTTPStatus.OK, {"preferences": self.user_context.get_context().get("custom_preferences", {})})

            if method == "POST" and clean_path == "/memory/preferences":
                prefs = (payload or {}).get("preferences", payload or {})
                if isinstance(prefs, dict):
                    for k, v in prefs.items():
                        self.user_context.set_preference(k, v)
                return APIResponse(HTTPStatus.OK, {"status": "success", "preferences": self.user_context.get_context().get("custom_preferences", {})})

            # --- Semantic memory ---

            if method == "GET" and clean_path == "/memory/semantic/search":
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(path).query)
                q = (qs.get("q") or qs.get("query") or [""])[0]
                top_k = int((qs.get("top_k") or ["5"])[0])
                results = self.semantic_memory.recall_semantic(q, top_k=top_k) if q else []
                return APIResponse(HTTPStatus.OK, {"results": results, "query": q, "count": len(results)})

            if method == "POST" and clean_path == "/memory/semantic":
                text = (payload or {}).get("text", "")
                if not isinstance(text, str) or not text.strip():
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "missing_text", "Field 'text' is required.")
                mem_type = (payload or {}).get("memory_type", "capability_context")
                meta = (payload or {}).get("metadata", {})
                rec = self.semantic_memory.remember_semantic(text, metadata=meta, memory_type=mem_type)
                return APIResponse(HTTPStatus.OK, {"status": "success", "memory": rec})

            if clean_path.startswith("/memory/semantic/") and method == "DELETE":
                mem_id = clean_path[len("/memory/semantic/"):]
                deleted = self.semantic_memory.forget_semantic(mem_id)
                if not deleted:
                    raise APIRequestError(HTTPStatus.NOT_FOUND, "memory_not_found", f"Semantic memory '{mem_id}' not found.")
                return APIResponse(HTTPStatus.OK, {"status": "success", "deleted": mem_id})

            if method == "DELETE" and clean_path == "/memory":
                self.execution_history.clear()
                self.vector_store.clear()
                for rec in self.memory_manager.recall_all():
                    self.memory_manager.forget(rec["id"])
                return APIResponse(HTTPStatus.OK, {"status": "success", "message": "All memory cleared."})

            # --- A2A agent management ---

            if method == "GET" and clean_path == "/a2a/agents":
                return APIResponse(HTTPStatus.OK, {"agents": self._a2a_list_agents()})

            if method == "POST" and clean_path == "/a2a/agents":
                return APIResponse(HTTPStatus.OK, self._a2a_add_agent(payload or {}))

            if clean_path.startswith("/a2a/agents/") and method == "DELETE":
                agent_id = clean_path[len("/a2a/agents/"):]
                return APIResponse(HTTPStatus.OK, self._a2a_remove_agent(agent_id))

            if clean_path.startswith("/a2a/agents/") and clean_path.endswith("/delegate") and method == "POST":
                agent_id = clean_path[len("/a2a/agents/"):-len("/delegate")]
                return APIResponse(HTTPStatus.OK, self._a2a_delegate(agent_id, payload or {}))

            # --- Workspace management ---

            if method == "GET" and clean_path == "/workspaces":
                return APIResponse(HTTPStatus.OK, {"workspaces": self.workspace_registry.list(), "default_id": (self.workspace_registry.get_default() or {}).get("id")})

            if method == "POST" and clean_path == "/workspaces":
                p = payload or {}
                ws_path = p.get("path", "")
                if not ws_path or not isinstance(ws_path, str):
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "workspace_error", "A non-empty 'path' is required.")
                from pathlib import Path as _P
                resolved_ws = _P(ws_path).resolve()
                if not resolved_ws.exists():
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "workspace_error", f"Path '{ws_path}' does not exist.")
                if not resolved_ws.is_dir():
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "workspace_error", f"Path '{ws_path}' is not a directory.")
                try:
                    ws = self.workspace_registry.add(p.get("name", ""), ws_path, access=p.get("access", "write"), capabilities=p.get("capabilities", "*"), color=p.get("color", "#00ff88"))
                    return APIResponse(HTTPStatus.OK, {"status": "success", "workspace": ws})
                except (ValueError, FileNotFoundError) as exc:
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "workspace_error", str(exc)) from exc

            if clean_path.startswith("/workspaces/") and not clean_path.endswith("/browse") and not clean_path.endswith("/set-default"):
                ws_id = clean_path[len("/workspaces/"):]
                if method == "GET":
                    ws = self.workspace_registry.get(ws_id)
                    if ws is None:
                        raise APIRequestError(HTTPStatus.NOT_FOUND, "workspace_not_found", f"Workspace '{ws_id}' not found.")
                    return APIResponse(HTTPStatus.OK, {"workspace": ws})
                if method == "POST":
                    try:
                        ws = self.workspace_registry.update(ws_id, **(payload or {}))
                        return APIResponse(HTTPStatus.OK, {"status": "success", "workspace": ws})
                    except KeyError as exc:
                        raise APIRequestError(HTTPStatus.NOT_FOUND, "workspace_not_found", str(exc)) from exc
                if method == "DELETE":
                    try:
                        self.workspace_registry.remove(ws_id)
                        return APIResponse(HTTPStatus.OK, {"status": "success", "removed": ws_id})
                    except ValueError as exc:
                        raise APIRequestError(HTTPStatus.BAD_REQUEST, "workspace_error", str(exc)) from exc

            if clean_path.startswith("/workspaces/") and clean_path.endswith("/set-default") and method == "POST":
                ws_id = clean_path[len("/workspaces/"):-len("/set-default")]
                if not self.workspace_registry.set_default(ws_id):
                    raise APIRequestError(HTTPStatus.NOT_FOUND, "workspace_not_found", f"Workspace '{ws_id}' not found.")
                return APIResponse(HTTPStatus.OK, {"status": "success", "default_id": ws_id})

            if clean_path.startswith("/workspaces/") and clean_path.endswith("/browse") and method == "GET":
                ws_id = clean_path[len("/workspaces/"):-len("/browse")]
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(path).query)
                rel_path = (qs.get("path") or ["."])[0]
                try:
                    result = self.file_browser.list_directory(ws_id, rel_path)
                    return APIResponse(HTTPStatus.OK, result)
                except (KeyError, FileNotFoundError, PermissionError) as exc:
                    raise APIRequestError(HTTPStatus.BAD_REQUEST, "browse_error", str(exc)) from exc

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
            return {"status": "success", "server": client.status()}
        except MCPClientError as exc:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=exc.details) from exc

    def _mcp_remove_server(self, server_id: str) -> dict[str, Any]:
        self.mcp_tool_bridge.unbridge_server(server_id)
        removed = self.mcp_client_manager.remove_server(server_id)
        if not removed:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "mcp_server_not_found", f"MCP server '{server_id}' not found.")
        return {"status": "success", "server_id": server_id, "removed": True}

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
        return {"status": "success", "proposal": result}

    # ------------------------------------------------------------------
    # A2A agent management handlers
    # ------------------------------------------------------------------

    def _a2a_list_agents(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for agent in self._a2a_known_agents:
            url = agent.get("url", "")
            entry: dict[str, Any] = {"id": agent.get("id", url), "url": url, "status": "unknown"}
            try:
                client = A2AClient(url, timeout_ms=3000)
                card = client.discover()
                entry["status"] = "reachable"
                entry["name"] = card.get("name")
                entry["skills"] = len(card.get("skills", []))
            except Exception:
                entry["status"] = "error"
            results.append(entry)
        return results

    def _a2a_add_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = payload.get("url", "")
        agent_id = payload.get("id") or url
        if not url:
            raise APIRequestError(HTTPStatus.BAD_REQUEST, "invalid_a2a_agent", "Field 'url' is required.")
        entry = {"id": agent_id, "url": url}
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

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

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
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")

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
