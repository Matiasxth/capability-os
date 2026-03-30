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

from system.capabilities.implementations import (
    Phase10WhatsAppCapabilityExecutor,
    Phase7CapabilityExecutionError,
    Phase7CapabilityExecutor,
)
from system.capabilities.implementations.discord_executor import DiscordCapabilityExecutor
from system.capabilities.implementations.slack_executor import SlackCapabilityExecutor
from system.capabilities.implementations.telegram_executor import TelegramCapabilityExecutor
from system.integrations.installed.discord_bot_connector import DiscordConnector, DiscordPollingWorker
from system.integrations.installed.slack_bot_connector import SlackConnector, SlackPollingWorker
from system.integrations.installed.telegram_bot_connector import TelegramConnector, TelegramConnectorError
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
        # Register extended system tools
        from system.tools.implementations.system_tools_extended import (
            system_monitor_overview, system_monitor_processes,
            package_install, package_list,
            git_status, git_log, git_commit,
            backup_create, backup_list,
        )
        for tid, fn in [
            ("system_monitor_overview", system_monitor_overview),
            ("system_monitor_processes", system_monitor_processes),
            ("package_install", package_install),
            ("package_list", package_list),
            ("git_status", git_status),
            ("git_log", git_log),
            ("git_commit", git_commit),
            ("backup_create", backup_create),
            ("backup_list", backup_list),
        ]:
            self.tool_runtime.register_handler(tid, lambda p, c, ctx=None, f=fn: f(p, c))

        self.browser_session_manager = register_phase9_browser_tools(
            self.tool_runtime,
            self.workspace_root,
            artifacts_root=runtime_settings["workspace"]["artifacts_path"],
            auto_start=runtime_settings["browser"]["auto_start"],
            cdp_port=runtime_settings["browser"].get("cdp_port", 0),
            auto_restart_max_retries=runtime_settings["browser"].get("auto_restart_max_retries", 2),
            backend=runtime_settings["browser"].get("backend", "playwright"),
        )
        # Skill registry
        from system.core.skills import SkillRegistry
        self.skill_registry = SkillRegistry(
            skills_dir=self.workspace_root / "skills",
            capability_registry=self.capability_registry,
            tool_registry=self.tool_registry,
            tool_runtime=self.tool_runtime,
        )
        self.skill_registry.load_installed()

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
        # WhatsApp backend manager (3 switchable backends)
        try:
            from system.integrations.installed.whatsapp_web_connector.backends import WhatsAppBackendManager
            from system.integrations.installed.whatsapp_web_connector.backends.baileys_backend import BaileysBackend
            from system.integrations.installed.whatsapp_web_connector.backends.browser_backend import BrowserBackend
            from system.integrations.installed.whatsapp_web_connector.backends.official_backend import OfficialBackend

            self.whatsapp_manager = WhatsAppBackendManager()
            self.whatsapp_manager.register(BaileysBackend())
            self.whatsapp_manager.register(BrowserBackend())
            official = OfficialBackend()
            wsp_settings = runtime_settings.get("whatsapp", {})
            if isinstance(wsp_settings, dict):
                official_config = wsp_settings.get("official", {})
                if isinstance(official_config, dict):
                    official.configure(official_config)
            self.whatsapp_manager.register(official)
            wsp_backend = wsp_settings.get("backend", "browser") if isinstance(wsp_settings, dict) else "browser"
            self.whatsapp_manager.switch(wsp_backend)
            print(f"  WhatsApp backends: baileys, browser, official (active: {wsp_backend})")

            self._wsp_reply_settings = wsp_settings  # defer reply worker until after interpreter
        except Exception as exc:
            print(f"  WhatsApp backend manager: failed ({exc})")

        # Telegram connector — load bot_token from settings
        tg_settings = runtime_settings.get("telegram", {})
        tg_user_names: dict[str, str] = {}
        for uid in tg_settings.get("allowed_user_ids", []):
            tg_user_names[str(uid)] = tg_settings.get("display_name", "")
        self.telegram_connector = TelegramConnector(
            bot_token=tg_settings.get("bot_token", ""),
            default_chat_id=tg_settings.get("default_chat_id", ""),
            allowed_user_ids=tg_settings.get("allowed_user_ids", []),
            allowed_usernames=tg_settings.get("allowed_usernames", []),
            user_display_names=tg_user_names,
        )
        self.telegram_executor = TelegramCapabilityExecutor(self.telegram_connector)
        if llm_client is None:
            llm_client = LLMClient(
                settings_provider=lambda: self.settings_service.get_settings(mask_secrets=False).get("llm", {})
            )
        self.intent_interpreter = IntentInterpreter(self.capability_registry, llm_client=llm_client)

        # Telegram polling — must be after intent_interpreter
        from system.integrations.installed.telegram_bot_connector.connector import TelegramPollingWorker
        self.telegram_polling_worker = TelegramPollingWorker(
            connector=self.telegram_connector,
            interpreter=self.intent_interpreter,
            executor=lambda cap_id, inputs: self._execute_capability({"capability_id": cap_id, "inputs": inputs}),
            execution_history=self.execution_history,
        )
        if tg_settings.get("polling_enabled"):
            self.telegram_polling_worker.start()

        # WhatsApp auto-reply worker (must be after intent_interpreter)
        try:
            if hasattr(self, "whatsapp_manager"):
                from system.integrations.installed.whatsapp_web_connector.whatsapp_reply_worker import WhatsAppReplyWorker
                wsp_s = getattr(self, "_wsp_reply_settings", {}) or {}
                wsp_allowed = wsp_s.get("allowed_user_ids", []) if isinstance(wsp_s, dict) else []
                self.whatsapp_reply_worker = WhatsAppReplyWorker(
                    backend_manager=self.whatsapp_manager,
                    interpreter=self.intent_interpreter,
                    executor=lambda cap_id, inputs: self._execute_capability_sync(cap_id, inputs),
                    execution_history=self.execution_history,
                    allowed_user_ids=wsp_allowed,
                    agent_loop=getattr(self, "agent_loop", None),
                )
                self.whatsapp_reply_worker.start()
                print(f"  WhatsApp auto-reply: active")
        except Exception as exc:
            print(f"  WhatsApp auto-reply: failed ({exc})")

        # Voice services (STT + TTS)
        try:
            from system.core.voice import STTService, TTSService
            voice_settings = runtime_settings.get("voice", {})
            llm_key = runtime_settings.get("llm", {}).get("api_key", "")
            self.stt_service = STTService(
                provider=voice_settings.get("stt_provider", "whisper_api"),
                api_key=voice_settings.get("stt_api_key") or llm_key,
                language=voice_settings.get("language", "es"),
            )
            self.tts_service = TTSService(
                provider=voice_settings.get("tts_provider", "web_speech"),
                api_key=voice_settings.get("tts_api_key") or llm_key,
                voice=voice_settings.get("tts_voice", "nova"),
                speed=voice_settings.get("tts_speed", 1.0),
                output_dir=self.workspace_root / "artifacts" / "voice",
            )
            print(f"  Voice: STT={self.stt_service._provider}, TTS={self.tts_service._provider}", flush=True)
        except Exception as exc:
            print(f"  Voice: failed ({exc})", flush=True)

        # Agent registry (custom agent definitions)
        try:
            from system.core.agent.agent_registry import AgentRegistry
            self.agent_registry = AgentRegistry(data_path=self.workspace_root / "agents.json")
            print(f"  Agent Registry: {len(self.agent_registry.list())} agents", flush=True)
        except Exception as exc:
            print(f"  Agent Registry: failed ({exc})", flush=True)

        # Agent Loop (autonomous agent with tool use)
        try:
            from system.core.agent import AgentLoop
            from system.core.agent.tool_use_adapter import ToolUseAdapter
            from system.core.security import SecurityService

            security_svc = SecurityService(workspace_roots=[str(self.workspace_root)])
            tool_adapter = ToolUseAdapter(llm_client=self.intent_interpreter.llm_client)
            self.agent_loop = AgentLoop(
                tool_use_adapter=tool_adapter,
                tool_runtime=self.tool_runtime,
                security_service=security_svc,
                tool_registry=self.tool_registry,
                workspace_root=str(self.workspace_root),
                max_iterations=runtime_settings.get("agent", {}).get("max_iterations", 10) if isinstance(runtime_settings.get("agent"), dict) else 10,
                execution_history=self.execution_history,
            )
            self.security_service = security_svc

            # Skill Creator (hot-reload)
            from system.core.supervisor.skill_creator import SkillCreator
            self.skill_creator = SkillCreator(
                tool_registry=self.tool_registry,
                tool_runtime=self.tool_runtime,
                agent_loop=self.agent_loop,
                security_service=security_svc,
                project_root=self.project_root,
            )
            print(f"  Agent Loop: active (max_iterations={self.agent_loop._max_iterations})", flush=True)

            # Supervisor Daemon
            try:
                from system.core.supervisor.supervisor_daemon import SupervisorDaemon
                sv_cfg = runtime_settings.get("supervisor", {}) if isinstance(runtime_settings.get("supervisor"), dict) else {}
                self.supervisor = SupervisorDaemon(
                    project_root=self.project_root,
                    skill_creator=getattr(self, "skill_creator", None),
                    execution_history=self.execution_history,
                    max_claude_per_hour=sv_cfg.get("max_claude_per_hour", 10),
                    health_interval_s=sv_cfg.get("health_interval_s", 60),
                )
                from system.core.ui_bridge.event_bus import event_bus as _sv_eb
                self.supervisor.start(_sv_eb)
                print(f"  Supervisor: active (claude={'yes' if self.supervisor.claude_bridge.available else 'no'})", flush=True)
            except Exception as sv_exc:
                print(f"  Supervisor: failed ({sv_exc})", flush=True)

            # Proactive Scheduler
            try:
                from system.core.scheduler import TaskQueue, ProactiveScheduler
                self.task_queue = TaskQueue(data_path=self.workspace_root / "queue.json")
                self.scheduler = ProactiveScheduler(
                    task_queue=self.task_queue,
                    agent_loop=self.agent_loop,
                    agent_registry=getattr(self, "agent_registry", None),
                    whatsapp_manager=getattr(self, "whatsapp_manager", None),
                )
                self.scheduler.start()
                print(f"  Scheduler: active ({len(self.task_queue.list())} tasks)", flush=True)
            except Exception as sc_exc:
                print(f"  Scheduler: failed ({sc_exc})", flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"  Agent Loop: failed ({exc})", flush=True)

        # Slack connector
        slack_settings = runtime_settings.get("slack", {})
        self.slack_connector = SlackConnector(
            bot_token=slack_settings.get("bot_token", ""),
            channel_id=slack_settings.get("channel_id", ""),
            allowed_user_ids=[str(i) for i in slack_settings.get("allowed_user_ids", [])],
        )
        self.slack_executor = SlackCapabilityExecutor(self.slack_connector)
        self.slack_polling_worker = SlackPollingWorker(
            adapter=self.slack_connector,
            interpreter=self.intent_interpreter,
            executor=lambda cap_id, inputs: self._execute_capability({"capability_id": cap_id, "inputs": inputs}),
            execution_history=self.execution_history,
        )
        if slack_settings.get("polling_enabled"):
            self.slack_polling_worker.start()

        # Discord connector
        discord_settings = runtime_settings.get("discord", {})
        self.discord_connector = DiscordConnector(
            bot_token=discord_settings.get("bot_token", ""),
            channel_id=discord_settings.get("channel_id", ""),
            guild_id=discord_settings.get("guild_id", ""),
            allowed_user_ids=[str(i) for i in discord_settings.get("allowed_user_ids", [])],
        )
        self.discord_executor = DiscordCapabilityExecutor(self.discord_connector)
        self.discord_polling_worker = DiscordPollingWorker(
            adapter=self.discord_connector,
            interpreter=self.intent_interpreter,
            executor=lambda cap_id, inputs: self._execute_capability({"capability_id": cap_id, "inputs": inputs}),
            execution_history=self.execution_history,
        )
        if discord_settings.get("polling_enabled"):
            self.discord_polling_worker.start()

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
        # Auto-load saved MCP servers from settings
        for srv_cfg in mcp_settings.get("servers", []):
            if isinstance(srv_cfg, dict) and srv_cfg.get("id"):
                try:
                    client = self.mcp_client_manager.add_server(srv_cfg)
                    client.connect()
                except Exception as exc:
                    print(f"MCP auto-load '{srv_cfg.get('id')}' failed: {exc}", flush=True)

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
        self._router = self._build_router()

    def _build_router(self):
        from system.core.ui_bridge.router import Router
        from system.core.ui_bridge.handlers import (
            system_handlers, browser_handlers, workspace_handlers,
            memory_handlers, integration_handlers, capability_handlers,
            growth_handlers, mcp_handlers, a2a_handlers, skill_handlers,
        )
        r = Router()
        # System
        r.add("GET", "/status", system_handlers.get_status)
        r.add("GET", "/health", system_handlers.get_health)
        r.add("GET", "/settings", system_handlers.get_settings)
        r.add("POST", "/settings", system_handlers.save_settings)
        r.add("POST", "/llm/test", system_handlers.test_llm)
        r.add("GET", "/system/export-config", system_handlers.export_config)
        r.add("POST", "/system/import-config", system_handlers.import_config)
        # Browser
        r.add("POST", "/browser/restart", browser_handlers.restart_worker)
        r.add("GET", "/browser/cdp-status", browser_handlers.cdp_status)
        r.add("POST", "/browser/launch-chrome", browser_handlers.launch_chrome)
        r.add("POST", "/browser/open-whatsapp", browser_handlers.open_whatsapp)
        r.add("POST", "/browser/connect-cdp", browser_handlers.connect_cdp)
        # Workspaces
        r.add("GET", "/workspaces", workspace_handlers.list_workspaces)
        r.add("POST", "/workspaces", workspace_handlers.add_workspace)
        r.add("GET", "/workspaces/{ws_id}", workspace_handlers.get_workspace)
        r.add("POST", "/workspaces/{ws_id}", workspace_handlers.update_workspace)
        r.add("DELETE", "/workspaces/{ws_id}", workspace_handlers.delete_workspace)
        r.add("POST", "/workspaces/{ws_id}/set-default", workspace_handlers.set_default)
        r.add("POST", "/workspaces/{ws_id}/status", workspace_handlers.update_status)
        r.add("GET", "/workspaces/{ws_id}/browse", workspace_handlers.browse)
        # Memory + metrics
        r.add("GET", "/metrics", memory_handlers.get_metrics)
        r.add("GET", "/memory/context", memory_handlers.get_context)
        r.add("GET", "/memory/history", memory_handlers.get_history)
        r.add("POST", "/memory/history/chat", memory_handlers.save_chat)
        r.add("DELETE", "/memory/history/{exec_id}", memory_handlers.delete_history)
        r.add("POST", "/memory/sessions", memory_handlers.save_session)
        r.add("GET", "/memory/sessions/{exec_id}", memory_handlers.get_session)
        r.add("GET", "/memory/preferences", memory_handlers.get_preferences)
        r.add("POST", "/memory/preferences", memory_handlers.set_preferences)
        r.add("GET", "/memory/semantic/search", memory_handlers.search_semantic)
        r.add("POST", "/memory/semantic", memory_handlers.add_semantic)
        r.add("DELETE", "/memory/semantic/{mem_id}", memory_handlers.delete_semantic)
        r.add("DELETE", "/memory", memory_handlers.clear_all)
        r.add("POST", "/memory/compact", memory_handlers.compact_sessions)
        # Capabilities
        r.add("GET", "/capabilities", capability_handlers.list_capabilities)
        r.add("GET", "/capabilities/health", capability_handlers.capabilities_health)
        r.add("GET", "/capabilities/{capability_id}", capability_handlers.get_capability)
        r.add("POST", "/execute", capability_handlers.execute)
        r.add("POST", "/chat", capability_handlers.chat)
        r.add("POST", "/interpret", capability_handlers.interpret)
        r.add("POST", "/plan", capability_handlers.plan)
        # Agent endpoints
        from system.core.ui_bridge.handlers import agent_handlers
        r.add("POST", "/agent", agent_handlers.start_agent)
        r.add("POST", "/agent/confirm", agent_handlers.confirm_action)
        r.add("GET", "/agent/{session_id}", agent_handlers.get_session)
        # Agent registry CRUD
        r.add("GET", "/agents", agent_handlers.list_agents)
        r.add("POST", "/agents", agent_handlers.create_agent)
        r.add("GET", "/agents/{agent_id}", agent_handlers.get_agent_def)
        r.add("POST", "/agents/{agent_id}", agent_handlers.update_agent)
        r.add("DELETE", "/agents/{agent_id}", agent_handlers.delete_agent)
        r.add("POST", "/agents/design", agent_handlers.design_agent)
        # Logs
        r.add("GET", "/logs", system_handlers.get_logs)
        # Voice
        from system.core.ui_bridge.handlers import voice_handlers
        r.add("POST", "/voice/transcribe", voice_handlers.transcribe)
        r.add("POST", "/voice/synthesize", voice_handlers.synthesize)
        r.add("GET", "/voice/config", voice_handlers.voice_config)
        r.add("GET", "/executions/{execution_id}", capability_handlers.get_execution)
        r.add("GET", "/executions/{execution_id}/events", capability_handlers.get_execution_events)
        # Growth
        r.add("GET", "/gaps/pending", growth_handlers.pending_gaps)
        r.add("POST", "/gaps/{gap_id}/analyze", growth_handlers.analyze_gap)
        r.add("POST", "/gaps/{gap_id}/generate", growth_handlers.generate_gap)
        r.add("POST", "/gaps/{gap_id}/approve", growth_handlers.approve_gap)
        r.add("POST", "/gaps/{gap_id}/reject", growth_handlers.reject_gap)
        r.add("GET", "/proposals", growth_handlers.list_proposals)
        r.add("POST", "/proposals/{prop_id}/regenerate", growth_handlers.regenerate_proposal)
        r.add("POST", "/proposals/{cap_id}/approve", growth_handlers.approve_proposal)
        r.add("POST", "/proposals/{cap_id}/reject", growth_handlers.reject_proposal)
        r.add("GET", "/optimizations/pending", growth_handlers.pending_optimizations)
        r.add("POST", "/optimizations/{opt_id}/approve", growth_handlers.approve_optimization)
        r.add("POST", "/optimizations/{opt_id}/reject", growth_handlers.reject_optimization)
        # MCP
        r.add("GET", "/mcp/servers", mcp_handlers.list_servers)
        r.add("POST", "/mcp/servers", mcp_handlers.add_server)
        r.add("DELETE", "/mcp/servers/{server_id}", mcp_handlers.remove_server)
        r.add("POST", "/mcp/servers/{server_id}/discover", mcp_handlers.discover_tools)
        r.add("GET", "/mcp/tools", mcp_handlers.list_tools)
        r.add("POST", "/mcp/tools/{tool_id}/install", mcp_handlers.install_tool)
        r.add("DELETE", "/mcp/tools/{tool_id}/uninstall", mcp_handlers.uninstall_tool)
        # A2A
        r.add("GET", "/.well-known/agent.json", a2a_handlers.agent_card)
        r.add("POST", "/a2a", a2a_handlers.handle_task)
        r.add("GET", "/a2a/{task_id}/events", a2a_handlers.task_events)
        r.add("GET", "/a2a/agents", a2a_handlers.list_agents)
        r.add("POST", "/a2a/agents", a2a_handlers.add_agent)
        r.add("DELETE", "/a2a/agents/{agent_id}", a2a_handlers.remove_agent)
        r.add("POST", "/a2a/agents/{agent_id}/delegate", a2a_handlers.delegate_task)
        # Integrations
        r.add("GET", "/integrations", integration_handlers.list_integrations)
        r.add("GET", "/integrations/{integration_id}", integration_handlers.inspect_integration)
        r.add("POST", "/integrations/{integration_id}/validate", integration_handlers.validate_integration)
        r.add("POST", "/integrations/{integration_id}/enable", integration_handlers.enable_integration)
        r.add("POST", "/integrations/{integration_id}/disable", integration_handlers.disable_integration)
        r.add("GET", "/integrations/whatsapp/selectors/health", integration_handlers.whatsapp_selectors_health)
        r.add("POST", "/integrations/whatsapp/selectors", integration_handlers.whatsapp_selectors_override)
        r.add("POST", "/integrations/whatsapp/close-session", integration_handlers.whatsapp_close_session)
        r.add("GET", "/integrations/whatsapp/session-status", integration_handlers.whatsapp_session_status)
        r.add("POST", "/integrations/whatsapp/start", integration_handlers.whatsapp_start)
        r.add("GET", "/integrations/whatsapp/qr", integration_handlers.whatsapp_qr)
        r.add("POST", "/integrations/whatsapp/stop", integration_handlers.whatsapp_stop)
        r.add("POST", "/integrations/whatsapp/configure", integration_handlers.whatsapp_configure)
        r.add("POST", "/integrations/whatsapp/switch-backend", integration_handlers.whatsapp_switch_backend)
        r.add("GET", "/integrations/whatsapp/backends", integration_handlers.whatsapp_list_backends)
        r.add("GET", "/integrations/whatsapp/debug", integration_handlers.whatsapp_debug)
        r.add("GET", "/integrations/whatsapp/debug-chats", integration_handlers.whatsapp_debug_chats)
        r.add("GET", "/integrations/whatsapp/reply-status", integration_handlers.whatsapp_reply_status)
        r.add("GET", "/integrations/telegram/status", integration_handlers.telegram_status)
        r.add("POST", "/integrations/telegram/configure", integration_handlers.telegram_configure)
        r.add("POST", "/integrations/telegram/test", integration_handlers.telegram_test)
        r.add("POST", "/integrations/telegram/polling/start", integration_handlers.telegram_polling_start)
        r.add("POST", "/integrations/telegram/polling/stop", integration_handlers.telegram_polling_stop)
        r.add("GET", "/integrations/telegram/polling/status", integration_handlers.telegram_polling_status)
        # Slack
        r.add("GET", "/integrations/slack/status", integration_handlers.slack_status)
        r.add("POST", "/integrations/slack/configure", integration_handlers.slack_configure)
        r.add("POST", "/integrations/slack/test", integration_handlers.slack_test)
        r.add("POST", "/integrations/slack/polling/start", integration_handlers.slack_polling_start)
        r.add("POST", "/integrations/slack/polling/stop", integration_handlers.slack_polling_stop)
        r.add("GET", "/integrations/slack/polling/status", integration_handlers.slack_polling_status)
        # Discord
        r.add("GET", "/integrations/discord/status", integration_handlers.discord_status)
        r.add("POST", "/integrations/discord/configure", integration_handlers.discord_configure)
        r.add("POST", "/integrations/discord/test", integration_handlers.discord_test)
        r.add("POST", "/integrations/discord/polling/start", integration_handlers.discord_polling_start)
        r.add("POST", "/integrations/discord/polling/stop", integration_handlers.discord_polling_stop)
        r.add("GET", "/integrations/discord/polling/status", integration_handlers.discord_polling_status)
        # Skills
        r.add("GET", "/skills", skill_handlers.list_skills)
        r.add("POST", "/skills/install", skill_handlers.install_skill)
        r.add("GET", "/skills/{skill_id}", skill_handlers.get_skill)
        r.add("DELETE", "/skills/{skill_id}", skill_handlers.uninstall_skill)
        r.add("POST", "/skills/hot-load", skill_handlers.hot_load)
        r.add("GET", "/skills/auto-generated", skill_handlers.list_created_skills)
        # Supervisor
        from system.core.ui_bridge.handlers import supervisor_handlers
        r.add("GET", "/supervisor/status", supervisor_handlers.supervisor_status)
        r.add("GET", "/supervisor/log", supervisor_handlers.supervisor_log)
        r.add("POST", "/supervisor/claude", supervisor_handlers.supervisor_invoke_claude)
        r.add("POST", "/supervisor/health-check", supervisor_handlers.health_check_now)
        # Scheduler
        from system.core.ui_bridge.handlers import scheduler_handlers
        r.add("GET", "/scheduler/tasks", scheduler_handlers.list_tasks)
        r.add("POST", "/scheduler/tasks", scheduler_handlers.create_task)
        r.add("POST", "/scheduler/tasks/{task_id}", scheduler_handlers.update_task)
        r.add("DELETE", "/scheduler/tasks/{task_id}", scheduler_handlers.delete_task)
        r.add("POST", "/scheduler/tasks/{task_id}/run", scheduler_handlers.run_task_now)
        r.add("GET", "/scheduler/status", scheduler_handlers.scheduler_status)
        r.add("GET", "/scheduler/log", scheduler_handlers.scheduler_log)
        return r

    def _load_registries(self) -> None:
        capability_dir = self.project_root / "system" / "capabilities" / "contracts" / "v1"
        tool_dir = self.project_root / "system" / "tools" / "contracts" / "v1"
        self.capability_registry.load_from_directory(capability_dir)
        self.tool_registry.load_from_directory(tool_dir)

    def handle(self, method: str, path: str, payload: dict[str, Any] | None = None) -> APIResponse:
        clean_path = urlparse(path).path.rstrip("/") or "/"

        # Router-based dispatch (new system — migrated routes)
        match = self._router.dispatch(method, clean_path)
        if match is not None:
            try:
                return match.handler(self, payload, _raw_path=path, **match.params)
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
            wa_tabs = [t for t in tabs if isinstance(t, dict) and "web.whatsapp.com" in (t.get("url") or "")]
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

        agent_config = None
        if agent_id and hasattr(service, "agent_registry"):
            agent_config = service.agent_registry.get(agent_id)

        import queue as _queue
        event_queue: _queue.Queue[dict[str, Any] | None] = _queue.Queue()

        def _run() -> None:
            try:
                gen = service.agent_loop.run(message, session_id=session_id, conversation_history=history, agent_config=agent_config)
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
