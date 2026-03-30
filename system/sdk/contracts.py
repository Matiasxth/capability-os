"""Core typed contracts for cross-plugin communication.

Plugins never import each other directly — they depend on these Protocol
interfaces.  The ServiceContainer resolves concrete implementations at runtime.

SDK v2: Contracts now use typed models from ``system.sdk.models`` instead of
raw ``dict[str, Any]``. TypedDict is fully compatible with plain dicts so
existing code continues to work.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from system.sdk.models import (
    AgentConfig,
    CapabilityContract,
    ExecutionEntry,
    ExecutionResult,
    HealthSnapshot,
    IntegrationInfo,
    MCPServerConfig,
    MemoryEntry,
    PluginStatus,
    ScheduledTask,
    SchedulerStatus,
    SemanticHit,
    SupervisorStatus,
    ToolContract,
    WorkflowData,
    WorkspaceData,
)


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

@runtime_checkable
class EventBusContract(Protocol):
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None: ...
    def subscribe(self, callback: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@runtime_checkable
class SettingsProvider(Protocol):
    def load_settings(self) -> dict[str, Any]: ...
    def get_settings(self, *, mask_secrets: bool = True) -> dict[str, Any]: ...
    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Tool Registry & Runtime
# ---------------------------------------------------------------------------

@runtime_checkable
class ToolRegistryReader(Protocol):
    """Read-only access to registered tools."""
    def get(self, tool_id: str) -> ToolContract | None: ...
    def list_all(self) -> list[ToolContract]: ...
    def ids(self) -> list[str]: ...


@runtime_checkable
class ToolRegistryWriter(Protocol):
    """Write access to register new tools."""
    def register(self, contract: ToolContract, *, source: str = "<memory>") -> None: ...


@runtime_checkable
class ToolRegistryContract(ToolRegistryReader, ToolRegistryWriter, Protocol):
    """Full tool registry access (backward compatible)."""
    ...


@runtime_checkable
class ToolRuntimeContract(Protocol):
    def execute(self, action: str, params: dict[str, Any]) -> Any: ...
    def register_handler(self, tool_id: str, handler: Any) -> None: ...


# ---------------------------------------------------------------------------
# Capability Registry & Engine
# ---------------------------------------------------------------------------

@runtime_checkable
class CapabilityRegistryReader(Protocol):
    """Read-only access to registered capabilities."""
    def get(self, capability_id: str) -> CapabilityContract | None: ...
    def list_all(self) -> list[CapabilityContract]: ...
    def ids(self) -> list[str]: ...


@runtime_checkable
class CapabilityRegistryWriter(Protocol):
    """Write access to register new capabilities."""
    def register(self, contract: CapabilityContract, *, source: str = "<memory>") -> None: ...


@runtime_checkable
class CapabilityRegistryContract(CapabilityRegistryReader, CapabilityRegistryWriter, Protocol):
    """Full capability registry access (backward compatible)."""
    ...


@runtime_checkable
class CapabilityEngineContract(Protocol):
    def execute(
        self,
        contract: CapabilityContract,
        inputs: dict[str, Any],
        event_callback: Any = None,
    ) -> ExecutionResult: ...


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

@runtime_checkable
class IntentInterpreterContract(Protocol):
    def interpret(self, text: str, history: Any = None) -> dict[str, Any]: ...
    def classify_message(self, text: str) -> str: ...
    def chat_response(self, text: str, user_name: str = "") -> str: ...


@runtime_checkable
class LLMClientContract(Protocol):
    def complete(self, system_prompt: str = "", user_prompt: str = "") -> str: ...


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

@runtime_checkable
class SecurityServiceContract(Protocol):
    def classify(
        self,
        capability_id: str = "",
        tool_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> Any: ...

    def classify_description(self, level: Any) -> str: ...


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@runtime_checkable
class MemoryReader(Protocol):
    """Read-only memory access."""
    def recall(self, key: str) -> Any: ...
    def recall_all(self, memory_type: str | None = None) -> list[MemoryEntry]: ...
    def count(self) -> int: ...


@runtime_checkable
class MemoryWriter(Protocol):
    """Write access to memory."""
    def remember(self, key: str, value: Any, **kw: Any) -> Any: ...
    def forget(self, memory_id: str) -> bool: ...


@runtime_checkable
class MemoryManagerContract(MemoryReader, MemoryWriter, Protocol):
    """Full memory manager access (backward compatible)."""
    ...


@runtime_checkable
class ExecutionHistoryContract(Protocol):
    def upsert_chat(self, session_id: str, intent: str, messages: list | None = None, duration_ms: int = 0, workspace_id: str | None = None) -> str | None: ...
    def get_recent(self, n: int = 20) -> list[ExecutionEntry]: ...
    def get_by_workspace(self, workspace_id: str, limit: int = 50) -> list[ExecutionEntry]: ...
    def get_session(self, execution_id: str) -> ExecutionEntry | None: ...
    def get_stats(self) -> dict[str, Any]: ...
    def count(self) -> int: ...


@runtime_checkable
class SemanticMemoryContract(Protocol):
    def remember_semantic(self, text: str, **kw: Any) -> dict[str, Any] | None: ...
    def recall_semantic(self, query: str, top_k: int = 5) -> list[SemanticHit]: ...
    def forget_semantic(self, memory_id: str) -> bool: ...
    def count(self) -> int: ...


@runtime_checkable
class MarkdownMemoryContract(Protocol):
    def load_memory_md(self) -> str: ...
    def save_memory_md(self, content: str) -> None: ...
    def load_memory_sections(self) -> dict[str, list[str]]: ...
    def add_fact(self, section: str, fact: str) -> None: ...
    def remove_fact(self, section: str, fact_substring: str) -> bool: ...
    def append_daily(self, entry: str, section: str = "Sessions") -> None: ...
    def build_context(self, max_tokens: int = 500) -> str: ...


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@runtime_checkable
class AgentLoopContract(Protocol):
    def run(self, user_message: str, session_id: str | None = None, conversation_history: list | None = None, agent_config: AgentConfig | None = None, workspace_id: str | None = None, workspace_path: str | None = None) -> Any: ...
    def get_session(self, session_id: str) -> Any: ...


@runtime_checkable
class AgentRegistryReader(Protocol):
    """Read-only agent registry access."""
    def list(self) -> list[AgentConfig]: ...
    def get(self, agent_id: str) -> AgentConfig | None: ...


@runtime_checkable
class AgentRegistryWriter(Protocol):
    """Write access to agent registry."""
    def create(self, data: AgentConfig) -> AgentConfig: ...
    def update(self, agent_id: str, data: AgentConfig) -> AgentConfig | None: ...
    def delete(self, agent_id: str) -> bool: ...


@runtime_checkable
class AgentRegistryContract(AgentRegistryReader, AgentRegistryWriter, Protocol):
    """Full agent registry access (backward compatible)."""
    ...


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@runtime_checkable
class WorkspaceReader(Protocol):
    """Read-only workspace access."""
    def list(self) -> list[WorkspaceData]: ...
    def get(self, ws_id: str) -> WorkspaceData | None: ...
    def get_default(self) -> WorkspaceData | None: ...


@runtime_checkable
class WorkspaceWriter(Protocol):
    """Write access to workspace registry."""
    def add(self, name: str, path: str, **kw: Any) -> WorkspaceData: ...
    def remove(self, ws_id: str) -> bool: ...
    def set_default(self, ws_id: str) -> bool: ...
    def update(self, ws_id: str, **kw: Any) -> WorkspaceData | None: ...


@runtime_checkable
class WorkspaceRegistryContract(WorkspaceReader, WorkspaceWriter, Protocol):
    """Full workspace registry access (backward compatible)."""
    ...


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------

@runtime_checkable
class HealthServiceContract(Protocol):
    def get_system_health(self) -> HealthSnapshot: ...


@runtime_checkable
class MetricsCollectorContract(Protocol):
    def get_metrics(self) -> dict[str, Any]: ...
    def record_execution(self, **kw: Any) -> None: ...


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@runtime_checkable
class IntegrationRegistryContract(Protocol):
    def list_all(self) -> list[IntegrationInfo]: ...
    def get(self, integration_id: str) -> IntegrationInfo | None: ...
    def enable(self, integration_id: str) -> None: ...
    def disable(self, integration_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@runtime_checkable
class SkillRegistryContract(Protocol):
    def list_installed(self) -> list[dict[str, Any]]: ...
    def get_skill(self, skill_id: str) -> dict[str, Any] | None: ...
    def install_from_path(self, source_path: Any) -> dict[str, Any]: ...
    def uninstall(self, skill_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

@runtime_checkable
class WorkflowRegistryContract(Protocol):
    def list(self) -> list[WorkflowData]: ...
    def get(self, wf_id: str) -> WorkflowData | None: ...
    def create(self, **kw: Any) -> WorkflowData: ...
    def update(self, wf_id: str, **kw: Any) -> WorkflowData | None: ...
    def delete(self, wf_id: str) -> bool: ...
    def save_layout(self, wf_id: str, nodes: list, edges: list) -> WorkflowData | None: ...


@runtime_checkable
class WorkflowExecutorContract(Protocol):
    def execute(self, workflow: WorkflowData) -> ExecutionResult: ...


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

@runtime_checkable
class TaskQueueContract(Protocol):
    def list(self) -> list[ScheduledTask]: ...
    def add(self, **kw: Any) -> ScheduledTask: ...
    def update(self, task_id: str, **kw: Any) -> ScheduledTask: ...
    def remove(self, task_id: str) -> bool: ...
    def get(self, task_id: str) -> ScheduledTask | None: ...
    def get_ready(self) -> list[ScheduledTask]: ...


@runtime_checkable
class SchedulerContract(Protocol):
    def get_status(self) -> SchedulerStatus: ...
    def run_task_now(self, task_id: str) -> dict[str, Any]: ...
    @property
    def execution_log(self) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------

@runtime_checkable
class MCPClientManagerContract(Protocol):
    def list_servers(self) -> list[MCPServerConfig]: ...
    def add_server(self, config: MCPServerConfig) -> Any: ...
    def remove_server(self, server_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

@runtime_checkable
class SupervisorDaemonContract(Protocol):
    def get_status(self) -> SupervisorStatus: ...
    def get_full_log(self) -> list[dict[str, Any]]: ...
