"""Shared typed models for cross-plugin data exchange.

These TypedDict definitions replace the pervasive ``dict[str, Any]`` pattern
in SDK contracts. TypedDict is fully compatible with plain dicts — existing
code that passes ``dict`` continues to work, but IDEs and mypy now validate
field names and types.

Usage::

    from system.sdk.models import AgentConfig, WorkspaceData

    def get(self, agent_id: str) -> AgentConfig | None: ...
"""
from __future__ import annotations

from typing import Any, TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired


# ---------------------------------------------------------------------------
# Plugin & System
# ---------------------------------------------------------------------------

class PluginStatus(TypedDict):
    """Status of a single plugin in the container."""
    state: str            # PluginState.value: "running", "error", etc.
    name: str
    version: str
    error: str | None


class LLMHealth(TypedDict):
    """Health info for the LLM provider."""
    status: str           # "ready" | "not_configured" | "error"
    provider: str
    model: str
    base_url: NotRequired[str]
    timeout_ms: NotRequired[int]
    issues: list[str]


class HealthSnapshot(TypedDict):
    """System-wide health snapshot returned by /health."""
    status: str           # "ready" | "error"
    started_at: NotRequired[str]
    uptime_ms: NotRequired[int]
    issues: list[str]
    llm: LLMHealth
    browser_worker: dict[str, Any]
    integrations: dict[str, Any]


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class WorkspaceStatus(TypedDict, total=False):
    """Custom project status (user-configurable)."""
    name: str
    color: str
    icon: str


class WorkspaceData(TypedDict):
    """A registered workspace / project."""
    id: str
    name: str
    path: str
    access: str           # "read" | "write" | "none"
    color: str
    active: bool
    allowed_capabilities: NotRequired[str]
    icon: NotRequired[str]
    status: NotRequired[WorkspaceStatus]
    description: NotRequired[str]
    agent_ids: NotRequired[list[str]]
    created_at: NotRequired[str]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentConfig(TypedDict):
    """Definition of a custom AI agent."""
    id: NotRequired[str]
    name: str
    emoji: str
    description: str
    system_prompt: NotRequired[str]
    tool_ids: NotRequired[list[str]]
    llm_model: NotRequired[str]
    language: NotRequired[str]
    max_iterations: NotRequired[int]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class ExecutionResult(TypedDict):
    """Result of a capability execution."""
    execution_id: str
    capability_id: str
    status: str           # "success" | "error"
    final_output: dict[str, Any]
    runtime: NotRequired[dict[str, Any]]
    step_outputs: NotRequired[dict[str, Any]]


class ExecutionEntry(TypedDict):
    """A single entry in execution history."""
    session_id: str
    intent: str
    status: str
    duration_ms: int
    workspace_id: NotRequired[str | None]
    messages: NotRequired[list[dict[str, Any]]]
    created_at: NotRequired[str]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryEntry(TypedDict):
    """A key-value memory record."""
    id: str
    key: str
    value: Any
    memory_type: NotRequired[str]
    created_at: NotRequired[str]
    ttl_days: NotRequired[int | None]


class SemanticHit(TypedDict):
    """A result from semantic memory search."""
    text: str
    score: float
    memory: NotRequired[MemoryEntry]


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ScheduledTask(TypedDict):
    """A scheduled task in the task queue."""
    id: str
    description: str
    schedule: str         # "every_30min", "daily_09:00", etc.
    enabled: bool
    channel: str | None
    agent_id: str | None
    last_run: str | None
    next_run: str | None
    run_count: int
    last_result: NotRequired[dict[str, Any] | None]
    created_at: NotRequired[str]
    action: NotRequired[dict[str, Any]]


class SchedulerStatus(TypedDict):
    """Scheduler runtime status."""
    running: bool
    queue_size: int
    ready_tasks: int
    total_executions: int


# ---------------------------------------------------------------------------
# Tool & Capability Contracts
# ---------------------------------------------------------------------------

class ToolContract(TypedDict):
    """A registered tool definition."""
    id: str
    name: str
    category: NotRequired[str]
    description: str
    inputs: dict[str, Any]
    outputs: NotRequired[dict[str, Any]]
    constraints: NotRequired[dict[str, Any]]
    safety: NotRequired[dict[str, Any]]
    lifecycle: NotRequired[dict[str, Any]]


class CapabilityContract(TypedDict):
    """A registered capability definition."""
    id: str
    name: str
    domain: str
    type: str
    description: str
    inputs: dict[str, Any]
    outputs: NotRequired[dict[str, Any]]
    strategy: NotRequired[dict[str, Any]]
    exposure: NotRequired[dict[str, Any]]
    lifecycle: NotRequired[dict[str, Any]]


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class WorkflowNode(TypedDict, total=False):
    """A node in a visual workflow."""
    id: str
    type: str             # "trigger", "tool", "agent", "condition", etc.
    data: dict[str, Any]
    position: dict[str, float]


class WorkflowEdge(TypedDict):
    """An edge connecting two workflow nodes."""
    source: str
    target: str
    animated: NotRequired[bool]


class WorkflowData(TypedDict):
    """A saved workflow definition."""
    id: str
    name: str
    description: NotRequired[str]
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    parallel: NotRequired[bool]
    created_at: NotRequired[str]


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class IntegrationInfo(TypedDict):
    """Summary of an installed integration."""
    id: str
    name: str
    type: str             # "web_app", "rest_api", "local_app", etc.
    status: str           # "enabled", "disabled", "error"
    capabilities: NotRequired[list[str]]


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------

class MCPServerConfig(TypedDict):
    """Configuration for an MCP server."""
    id: str
    transport: str        # "stdio" | "http"
    command: NotRequired[str]
    url: NotRequired[str]
    timeout_ms: NotRequired[int]


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class SupervisorStatus(TypedDict):
    """Supervisor daemon status."""
    health: dict[str, Any]
    claude: dict[str, Any]
    errors: NotRequired[dict[str, Any]]
    gap_detector: NotRequired[dict[str, Any]]
    security: NotRequired[dict[str, Any]]
