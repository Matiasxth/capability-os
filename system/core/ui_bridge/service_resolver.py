"""Dynamic service resolver — replaces the ~80 static attribute aliases.

Instead of manually wiring ``self.telegram_connector = getattr(plugin, "connector", None)``,
handlers access ``service.telegram_connector`` which triggers ``__getattr__`` and resolves
dynamically via these declarative maps.

Results are cached on the instance (via ``object.__setattr__``) so subsequent accesses
are O(1) dict lookups — identical performance to the old static aliases.
"""
from __future__ import annotations

from system.sdk.contracts import (
    AgentLoopContract,
    AgentRegistryContract,
    CapabilityEngineContract,
    CapabilityRegistryContract,
    ExecutionHistoryContract,
    HealthServiceContract,
    IntegrationRegistryContract,
    IntentInterpreterContract,
    LLMClientContract,
    MarkdownMemoryContract,
    MCPClientManagerContract,
    MemoryManagerContract,
    MetricsCollectorContract,
    SchedulerContract,
    SemanticMemoryContract,
    SecurityServiceContract,
    SettingsProvider,
    SkillRegistryContract,
    SupervisorDaemonContract,
    TaskQueueContract,
    ToolRegistryContract,
    ToolRuntimeContract,
    WorkflowExecutorContract,
    WorkflowRegistryContract,
    WorkspaceRegistryContract,
)


# --------------------------------------------------------------------------
# Category A: Attributes resolved via Protocol contracts
# Key = attribute name on service, Value = Protocol type
# --------------------------------------------------------------------------

CONTRACT_MAP: dict[str, type] = {
    "settings_service": SettingsProvider,
    "capability_registry": CapabilityRegistryContract,
    "tool_registry": ToolRegistryContract,
    "tool_runtime": ToolRuntimeContract,
    "security_service": SecurityServiceContract,
    "health_service": HealthServiceContract,
    "metrics_collector": MetricsCollectorContract,
    "execution_history": ExecutionHistoryContract,
    "memory_manager": MemoryManagerContract,
    "semantic_memory": SemanticMemoryContract,
    "markdown_memory": MarkdownMemoryContract,
    "intent_interpreter": IntentInterpreterContract,
    "engine": CapabilityEngineContract,
    "agent_loop": AgentLoopContract,
    "agent_registry": AgentRegistryContract,
    "workspace_registry": WorkspaceRegistryContract,
    "llm_client": LLMClientContract,
    "integration_registry": IntegrationRegistryContract,
    "skill_registry": SkillRegistryContract,
    "workflow_registry": WorkflowRegistryContract,
    "workflow_executor": WorkflowExecutorContract,
    "task_queue": TaskQueueContract,
    "scheduler": SchedulerContract,
    "mcp_client_manager": MCPClientManagerContract,
    "supervisor": SupervisorDaemonContract,
}


# --------------------------------------------------------------------------
# Category B: Attributes resolved via plugin_id + attribute name
# Key = attribute name on service, Value = (plugin_id, attribute_on_plugin)
# --------------------------------------------------------------------------

PLUGIN_ATTR_MAP: dict[str, tuple[str, str]] = {
    # Auth
    "user_registry": ("capos.core.auth", "user_registry"),
    "jwt_service": ("capos.core.auth", "jwt_service"),
    "auth_middleware": ("capos.core.auth", "auth_middleware"),
    # Memory
    "user_context": ("capos.core.memory", "user_context"),
    "memory_compactor": ("capos.core.memory", "compactor"),
    "embeddings_engine": ("capos.core.memory", "embeddings_engine"),
    "vector_store": ("capos.core.memory", "vector_store"),
    # Capabilities
    "phase7_executor": ("capos.core.capabilities", "phase7_executor"),
    "plan_builder": ("capos.core.capabilities", "plan_builder"),
    "plan_validator": ("capos.core.capabilities", "plan_validator"),
    # Workspace
    "path_validator": ("capos.core.workspace", "path_validator"),
    "workspace_context": ("capos.core.workspace", "workspace_context"),
    "file_browser": ("capos.core.workspace", "file_browser"),
    # Browser
    "browser_session_manager": ("capos.core.browser", "browser_session_manager"),
    # Supervisor (skill_creator has no contract — stays as plugin attr)
    "skill_creator": ("capos.core.supervisor", "skill_creator"),
    # Voice
    "stt_service": ("capos.core.voice", "stt_service"),
    "tts_service": ("capos.core.voice", "tts_service"),
    # MCP (mcp_client_manager promoted to CONTRACT_MAP)
    "mcp_tool_bridge": ("capos.core.mcp", "mcp_tool_bridge"),
    "mcp_capability_generator": ("capos.core.mcp", "mcp_capability_generator"),
    # A2A
    "agent_card_builder": ("capos.core.a2a", "agent_card_builder"),
    "a2a_server": ("capos.core.a2a", "a2a_server"),
    # Telegram
    "telegram_connector": ("capos.channels.telegram", "connector"),
    "telegram_executor": ("capos.channels.telegram", "executor"),
    "telegram_polling_worker": ("capos.channels.telegram", "polling_worker"),
    # Slack
    "slack_connector": ("capos.channels.slack", "connector"),
    "slack_executor": ("capos.channels.slack", "executor"),
    "slack_polling_worker": ("capos.channels.slack", "polling_worker"),
    # Discord
    "discord_connector": ("capos.channels.discord", "connector"),
    "discord_executor": ("capos.channels.discord", "executor"),
    "discord_polling_worker": ("capos.channels.discord", "polling_worker"),
    # WhatsApp
    "whatsapp_manager": ("capos.channels.whatsapp", "backend_manager"),
    "whatsapp_reply_worker": ("capos.channels.whatsapp", "reply_worker"),
    "phase10_whatsapp_executor": ("capos.channels.whatsapp", "executor"),
    # Growth
    "capability_generator": ("capos.core.growth", "capability_generator"),
    "auto_install_pipeline": ("capos.core.growth", "auto_install_pipeline"),
    "gap_analyzer": ("capos.core.growth", "gap_analyzer"),
    "performance_monitor": ("capos.core.growth", "performance_monitor"),
    "strategy_optimizer": ("capos.core.growth", "strategy_optimizer"),
    "integration_detector": ("capos.core.growth", "integration_detector"),
    "capability_bridge": ("capos.core.growth", "capability_bridge"),
    # Sequences
    "sequence_storage": ("capos.core.sequences", "sequence_storage"),
    "sequence_registry": ("capos.core.sequences", "sequence_registry"),
    "sequence_runner": ("capos.core.sequences", "sequence_runner"),
    # Workflows (promoted to CONTRACT_MAP)
    # Sandbox
    "sandbox_manager": ("capos.core.sandbox", "sandbox_manager"),
    # Integrations (loader/validator via plugin)
    "integration_loader": ("capos.core.integrations", "integration_loader"),
    "integration_validator": ("capos.core.integrations", "integration_validator"),
}


def resolve_attribute(container: object, name: str) -> tuple[bool, object]:
    """Attempt to resolve an attribute name via the maps.

    Returns ``(found, value)`` where ``found`` is True if the name is
    in one of the maps (even if the resolved value is None).
    """
    # Contract-based resolution
    contract_type = CONTRACT_MAP.get(name)
    if contract_type is not None:
        return True, container.get_optional(contract_type)  # type: ignore[attr-defined]

    # Plugin-attribute resolution
    mapping = PLUGIN_ATTR_MAP.get(name)
    if mapping is not None:
        plugin_id, attr_name = mapping
        plugin = container.get_plugin(plugin_id)  # type: ignore[attr-defined]
        if plugin is not None:
            return True, getattr(plugin, attr_name, None)
        return True, None

    return False, None
