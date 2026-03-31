# Plugin Development Guide

This is the complete guide for building plugins for Capability OS. Plugins are the primary extension mechanism -- every feature from memory to messaging channels is implemented as a plugin.

---

## Table of Contents

- [Plugin Structure](#plugin-structure)
- [Manifest v2 Format](#manifest-v2-format)
- [Plugin Types](#plugin-types)
- [PluginContext API](#plugincontext-api)
- [Protocol Contracts](#protocol-contracts)
- [Registering Routes](#registering-routes)
- [Registering Tools](#registering-tools)
- [Emitting Events](#emitting-events)
- [Hot-Reload Lifecycle](#hot-reload-lifecycle)
- [Health Checks](#health-checks)
- [Policy Engine](#policy-engine)
- [Complete Example](#complete-example)
- [Testing Plugins](#testing-plugins)

---

## Plugin Structure

Every plugin lives in its own directory under `system/plugins/` and consists of two required files:

```
system/plugins/my_plugin/
    capos-plugin.json    # Declarative manifest (metadata, permissions, deps)
    plugin.py            # Implementation (classes, factory function)
    __init__.py           # (optional) package marker
```

The manifest is loaded first for discovery. The entry point in the manifest points to the factory function that creates the plugin instance.

---

## Manifest v2 Format

The `capos-plugin.json` file describes your plugin declaratively. The plugin loader reads it before importing any Python code.

```json
{
  "id": "capos.my.plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "A description of what this plugin does",
  "author": "YourName",
  "plugin_types": ["BasePlugin", "ToolPlugin"],
  "dependencies": [
    "capos.core.settings",
    "capos.core.agent>=1.0.0"
  ],
  "optional_dependencies": [
    "capos.core.browser"
  ],
  "entry_point": "plugin:create_plugin",
  "settings_key": "my_plugin",
  "auto_start": true,
  "sdk_min_version": "2.0.0",

  "permissions": [
    "filesystem.read",
    "filesystem.write",
    "network.http",
    "event_bus.emit"
  ],
  "required_services": [
    "ToolRegistryContract",
    "ToolRuntimeContract"
  ],
  "provided_services": [
    "MyCustomContract"
  ],
  "events_emitted": [
    "my_plugin_update"
  ],
  "events_consumed": [
    "settings_updated"
  ],
  "config_schema": {
    "api_key": {"type": "string", "required": true},
    "timeout_ms": {"type": "integer", "default": 5000}
  },

  "license": "MIT",
  "homepage": "https://github.com/you/my-plugin",
  "tags": ["external", "tool"]
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique plugin identifier (dotted notation: `namespace.name`) |
| `name` | `string` | Human-readable display name |
| `version` | `string` | Semver version string |
| `description` | `string` | Short description |
| `author` | `string` | Plugin author |
| `plugin_types` | `string[]` | Which plugin types it implements: `BasePlugin`, `ToolPlugin`, `ChannelPlugin`, `MemoryPlugin`, `AgentPlugin`, `UIPlugin` |
| `dependencies` | `string[]` | Required plugins, with optional semver constraints (e.g. `"capos.core.agent>=1.0.0"`) |
| `optional_dependencies` | `string[]` | Plugins that enhance functionality but are not required |
| `entry_point` | `string` | Module and factory function (`"plugin:create_plugin"`) |
| `settings_key` | `string` | Key in `settings.json` for this plugin's config section |
| `auto_start` | `boolean` | Whether to call `start()` automatically on boot |
| `sdk_min_version` | `string` | Minimum SDK version required |
| `permissions` | `string[]` | Permission scopes this plugin needs (see [Policy Engine](#policy-engine)) |
| `required_services` | `string[]` | Contract names this plugin will request via `get_service()` |
| `provided_services` | `string[]` | Contract names this plugin publishes via `publish_service()` |
| `events_emitted` | `string[]` | Event types this plugin will emit |
| `events_consumed` | `string[]` | Event types this plugin subscribes to |
| `config_schema` | `object` | JSON schema for plugin-specific settings |
| `license` | `string` | License identifier |
| `homepage` | `string` | URL to project homepage or repository |
| `tags` | `string[]` | Categorization tags (e.g. `"builtin"`, `"channel"`, `"external"`) |

### Dependency Constraints

Dependencies support semver operators:

```json
"dependencies": [
  "capos.core.settings",
  "capos.core.agent>=1.0.0",
  "capos.core.memory>=1.0.0,<2.0.0"
]
```

The manifest's `parsed_dependencies()` method returns `(plugin_id, version_constraint)` tuples for programmatic access.

---

## Plugin Types

All plugin types are defined as `@runtime_checkable` Protocol classes in `system/sdk/plugin_types.py`.

### BasePlugin

The foundational protocol every plugin must implement:

```python
class BasePlugin(Protocol):
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
```

### ToolPlugin

Extends BasePlugin to register tools:

```python
class ToolPlugin(BasePlugin, Protocol):
    def register_tools(self, tool_registry: Any, tool_runtime: Any) -> list[str]: ...
```

### ChannelPlugin

Extends BasePlugin for messaging channel integrations:

```python
class ChannelPlugin(BasePlugin, Protocol):
    @property
    def channel_id(self) -> str: ...
    def get_status(self) -> dict[str, Any]: ...
    def configure(self, settings: dict[str, Any]) -> None: ...
    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]: ...
    def register_routes(self, router: Any) -> None: ...
```

### MemoryPlugin

Provides a memory storage backend:

```python
class MemoryPlugin(BasePlugin, Protocol):
    def store(self, key: str, value: Any, **kw: Any) -> None: ...
    def retrieve(self, key: str) -> Any: ...
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
```

### AgentPlugin

Registers agent types or behaviors:

```python
class AgentPlugin(BasePlugin, Protocol):
    def get_agent_types(self) -> list[dict[str, Any]]: ...
```

### UIPlugin

Registers Control Center UI sections:

```python
class UIPlugin(BasePlugin, Protocol):
    def get_ui_sections(self) -> list[dict[str, Any]]: ...
    def register_routes(self, router: Any) -> None: ...
```

### PluginLifecycleHooks (Mixin)

Inherit from this to get no-op defaults for optional lifecycle hooks:

```python
from system.sdk.plugin_types import PluginLifecycleHooks

class MyPlugin(PluginLifecycleHooks):
    plugin_id = "my.plugin"

    def health_check(self):
        return {"healthy": self._db.connected, "message": "DB check"}

    def get_state(self):
        return {"counter": self._counter}

    def restore_state(self, state):
        self._counter = state.get("counter", 0)

    def on_config_changed(self, new_config):
        self._timeout = new_config.get("timeout_ms", 5000)
```

---

## PluginContext API

Every plugin receives a `PluginContext` instance during `initialize()`. This is the **only** way to access cross-plugin dependencies.

### Available Methods

```python
class PluginContext:
    # Attributes
    workspace_root: Path        # Root workspace directory
    project_root: Path          # CapOS project root
    settings: dict[str, Any]    # Full settings.json content
    event_bus: EventBus         # For emitting events

    # Service resolution
    def get_service(self, contract_type: type) -> Any:
        """Get a service by its Protocol type. Raises ServiceNotFoundError."""

    def get_optional(self, contract_type: type) -> Any | None:
        """Get a service or None if not registered."""

    def publish_service(self, contract_type: type, implementation: Any) -> None:
        """Publish a service implementation for other plugins."""

    def plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        """Get settings section for a plugin.
        Convention: 'capos.channels.telegram' -> settings['telegram']
        """
```

### Usage Example

```python
from system.sdk.contracts import ToolRegistryContract, ToolRuntimeContract, MemoryManagerContract

class MyPlugin:
    def initialize(self, ctx):
        self._ctx = ctx

        # Get required services
        self.tool_registry = ctx.get_service(ToolRegistryContract)

        # Get optional services (returns None if unavailable)
        self.memory = ctx.get_optional(MemoryManagerContract)

        # Read plugin-specific settings
        self._settings = ctx.plugin_settings(self.plugin_id)

        # Publish a service for other plugins
        ctx.publish_service(MyCustomContract, MyImplementation())
```

### Policy Enforcement

When a `PolicyEngine` is active, `get_service()` checks `service.<ContractName>` permissions before resolving. Plugins tagged `"builtin"` bypass policy checks. External plugins get their manifest `permissions` verified at load time.

---

## Protocol Contracts

Contracts are defined in `system/sdk/contracts.py` as `@runtime_checkable` Protocol classes. Plugins never import each other -- they depend on these interfaces. The `ServiceContainer` resolves concrete implementations at runtime.

### Event Bus

| Contract | Methods |
|---|---|
| `EventBusContract` | `emit(event_type, data)`, `subscribe(callback)` |

### Settings

| Contract | Methods |
|---|---|
| `SettingsProvider` | `load_settings()`, `get_settings(mask_secrets)`, `save_settings(payload)` |

### Tool Registry & Runtime

| Contract | Methods |
|---|---|
| `ToolRegistryReader` | `get(tool_id)`, `list_all()`, `ids()` |
| `ToolRegistryWriter` | `register(contract, source)` |
| `ToolRegistryContract` | All of the above (combined) |
| `ToolRuntimeContract` | `execute(action, params)`, `register_handler(tool_id, handler)` |

### Capability Registry & Engine

| Contract | Methods |
|---|---|
| `CapabilityRegistryReader` | `get(capability_id)`, `list_all()`, `ids()` |
| `CapabilityRegistryWriter` | `register(contract, source)` |
| `CapabilityRegistryContract` | All of the above (combined) |
| `CapabilityEngineContract` | `execute(contract, inputs, event_callback)` |

### Interpretation & LLM

| Contract | Methods |
|---|---|
| `IntentInterpreterContract` | `interpret(text, history)`, `classify_message(text)`, `chat_response(text, user_name)` |
| `LLMClientContract` | `complete(system_prompt, user_prompt)` |

### Security

| Contract | Methods |
|---|---|
| `SecurityServiceContract` | `classify(capability_id, tool_id, inputs)`, `classify_description(level)` |

### Memory

| Contract | Methods |
|---|---|
| `MemoryReader` | `recall(key)`, `recall_all(memory_type)`, `count()` |
| `MemoryWriter` | `remember(key, value, memory_type, capability_id, ttl_days)`, `forget(memory_id)` |
| `MemoryManagerContract` | All of the above (combined) |
| `ExecutionHistoryContract` | `upsert_chat(session_id, intent, ...)`, `get_recent(n)`, `get_by_workspace(ws_id)`, `get_session(exec_id)`, `get_stats()`, `count()` |
| `SemanticMemoryContract` | `remember_semantic(text, metadata, ...)`, `recall_semantic(query, top_k)`, `forget_semantic(memory_id)`, `count()` |
| `MarkdownMemoryContract` | `load_memory_md()`, `save_memory_md(content)`, `load_memory_sections()`, `add_fact(section, fact)`, `remove_fact(section, fact_substring)`, `append_daily(entry, section)`, `build_context(max_tokens)` |

### Agent

| Contract | Methods |
|---|---|
| `AgentLoopContract` | `run(user_message, session_id, ...)`, `get_session(session_id)` |
| `AgentRegistryReader` | `list()`, `get(agent_id)` |
| `AgentRegistryWriter` | `create(data)`, `update(agent_id, data)`, `delete(agent_id)` |
| `AgentRegistryContract` | All of the above (combined) |

### Workspace

| Contract | Methods |
|---|---|
| `WorkspaceReader` | `list()`, `get(ws_id)`, `get_default()` |
| `WorkspaceWriter` | `add(name, path, ...)`, `remove(ws_id)`, `set_default(ws_id)`, `update(ws_id, **fields)` |
| `WorkspaceRegistryContract` | All of the above (combined) |

### Health & Metrics

| Contract | Methods |
|---|---|
| `HealthServiceContract` | `get_system_health()` |
| `MetricsCollectorContract` | `get_metrics()`, `record_execution(runtime_model)` |

### Integrations

| Contract | Methods |
|---|---|
| `IntegrationRegistryContract` | `list_all()`, `get(integration_id)`, `enable(integration_id)`, `disable(integration_id)` |

### Skills

| Contract | Methods |
|---|---|
| `SkillRegistryContract` | `list_installed()`, `get_skill(skill_id)`, `install_from_path(source_path)`, `uninstall(skill_id)` |

### Workflows

| Contract | Methods |
|---|---|
| `WorkflowRegistryContract` | `list()`, `get(wf_id)`, `create(name, description, nodes, edges)`, `update(wf_id, **fields)`, `delete(wf_id)`, `save_layout(wf_id, nodes, edges)` |
| `WorkflowExecutorContract` | `execute(workflow)` |

### Scheduler

| Contract | Methods |
|---|---|
| `TaskQueueContract` | `list()`, `add(description, schedule, ...)`, `update(task_id, **fields)`, `remove(task_id)`, `get(task_id)`, `get_ready()` |
| `SchedulerContract` | `get_status()`, `run_task_now(task_id)`, `execution_log` (property) |

### MCP

| Contract | Methods |
|---|---|
| `MCPClientManagerContract` | `list_servers()`, `add_server(config)`, `remove_server(server_id)` |

### Supervisor

| Contract | Methods |
|---|---|
| `SupervisorDaemonContract` | `get_status()`, `get_full_log()` |

---

## Registering Routes

Plugins that expose HTTP endpoints implement a `register_routes(router)` method. The router provides an `add(method, path, handler)` method:

```python
class MyPlugin:
    def register_routes(self, router):
        router.add("GET", "/my-plugin/status", self.handle_status)
        router.add("POST", "/my-plugin/action", self.handle_action)

    def handle_status(self, request):
        return {"status": "ok", "version": self.version}

    def handle_action(self, request):
        body = request.get("body", {})
        result = self.do_something(body)
        return {"result": result}
```

All routes are automatically prefixed and available through the main API server.

---

## Registering Tools

Plugins implementing `ToolPlugin` register tools through the `register_tools()` method:

```python
from system.sdk.models import ToolContract

class MyToolPlugin:
    plugin_id = "my.tools"
    # ...

    def register_tools(self, tool_registry, tool_runtime):
        tool = ToolContract(
            id="my_calculator",
            name="Calculator",
            category="utilities",
            description="Performs basic math operations",
            inputs={
                "expression": {"type": "string", "description": "Math expression to evaluate"}
            },
            outputs={
                "result": {"type": "number", "description": "Calculation result"}
            },
        )
        tool_registry.register(tool, source=self.plugin_id)
        tool_runtime.register_handler("my_calculator", self._handle_calculate)
        return ["my_calculator"]

    def _handle_calculate(self, params):
        import ast
        expr = params.get("expression", "0")
        # Safe evaluation
        result = ast.literal_eval(expr)
        return {"result": result}
```

---

## Emitting Events

Use the event bus from the plugin context to emit events:

```python
class MyPlugin:
    def initialize(self, ctx):
        self._event_bus = ctx.event_bus

    def do_something(self):
        # ... perform work ...
        self._event_bus.emit("my_plugin_update", {
            "action": "task_completed",
            "task_id": "abc123",
        })
```

Events are broadcast to all WebSocket-connected frontends in real time. See the [Event Catalog](Event-Catalog) for all standard event types.

---

## Hot-Reload Lifecycle

Plugins can persist state across hot-reloads by implementing `get_state()` and `restore_state()`:

```python
class MyPlugin(PluginLifecycleHooks):
    def initialize(self, ctx):
        self._counter = 0
        self._cache = {}

    def get_state(self):
        """Called before the plugin is unloaded during hot-reload."""
        return {
            "counter": self._counter,
            "cache": self._cache,
        }

    def restore_state(self, state):
        """Called after initialize() during hot-reload."""
        self._counter = state.get("counter", 0)
        self._cache = state.get("cache", {})
```

The reload sequence is:

1. `get_state()` on the old instance
2. `stop()` on the old instance
3. New instance created via factory
4. `initialize(ctx)` on the new instance
5. `restore_state(state)` on the new instance
6. `start()` on the new instance

### Configuration Changes

To react to settings changes at runtime, implement `on_config_changed()`:

```python
def on_config_changed(self, new_config):
    self._api_key = new_config.get("api_key", "")
    self._timeout = new_config.get("timeout_ms", 5000)
```

---

## Health Checks

Plugins can report health status by implementing `health_check()`:

```python
def health_check(self):
    """Called periodically by the supervisor."""
    db_ok = self._check_database()
    api_ok = self._check_api_connection()
    return {
        "healthy": db_ok and api_ok,
        "message": "All systems operational" if (db_ok and api_ok) else "Degraded",
        "checks": {
            "database": db_ok,
            "api": api_ok,
        }
    }
```

The return type follows `PluginHealthStatus`:

```python
class PluginHealthStatus(TypedDict):
    healthy: bool
    message: str
    checks: NotRequired[dict[str, bool]]
```

---

## Policy Engine

The `PolicyEngine` controls what permissions plugins have. When a plugin is loaded, the engine verifies that all its declared `permissions` are allowed by the active policy rules.

### Permission Scopes

Permissions are hierarchical. A wildcard like `"filesystem.*"` grants all filesystem sub-permissions:

| Category | Scopes |
|---|---|
| `filesystem` | `read`, `write`, `delete`, `create_directory` |
| `network` | `http`, `websocket`, `dns` |
| `execution` | `subprocess`, `docker`, `script` |
| `browser` | `navigate`, `screenshot`, `interact`, `read_text` |
| `memory` | `read`, `write`, `semantic`, `markdown` |
| `event_bus` | `emit`, `subscribe` |
| `settings` | `read`, `write` |
| `users` | `read`, `manage` |
| `plugins` | `install`, `reload`, `configure` |
| `workspaces` | `read`, `write`, `delete` |
| `agents` | `read`, `write`, `execute` |
| `capabilities` | `read`, `register`, `execute` |
| `tools` | `read`, `register`, `execute` |
| `scheduler` | `read`, `create`, `delete`, `run` |
| `workflows` | `read`, `create`, `execute` |
| `mcp` | `servers`, `tools` |
| `a2a` | `agents`, `delegate` |
| `supervisor` | `invoke`, `health`, `approve` |
| `voice` | `transcribe`, `synthesize` |

### Policy Rules

Policy rules are defined in a JSON file and target specific plugins, tags, roles, or workspaces:

```json
{
  "default_effect": "deny",
  "rules": [
    {
      "id": "builtin-allow-all",
      "description": "Builtin plugins can do anything",
      "target": { "tags": ["builtin"] },
      "permissions": ["*"],
      "effect": "allow",
      "priority": 100
    },
    {
      "id": "external-basic",
      "description": "External plugins get basic access",
      "target": { "tags": ["external"] },
      "permissions": ["filesystem.read", "network.http", "event_bus.emit"],
      "effect": "allow",
      "priority": 50
    }
  ]
}
```

Rules are evaluated in priority order (highest first). The first matching rule determines the outcome. If no rule matches, `default_effect` applies.

### Enforcement Points

- **Service resolution**: `ctx.get_service()` checks `service.<ContractName>` permission
- **Plugin load**: All declared permissions are verified before the plugin starts
- **Audit trail**: Every decision is logged to the `AuditLogger`

---

## Complete Example

Here is a complete working plugin that registers a tool and a route:

### `capos-plugin.json`

```json
{
  "id": "capos.example.weather",
  "name": "Weather Plugin",
  "version": "1.0.0",
  "description": "Provides weather lookup tool and status endpoint",
  "author": "CapOS Community",
  "plugin_types": ["ToolPlugin"],
  "dependencies": ["capos.core.settings"],
  "entry_point": "plugin:create_plugin",
  "settings_key": "weather",
  "permissions": [
    "network.http",
    "tools.register",
    "event_bus.emit"
  ],
  "provided_services": [],
  "events_emitted": ["weather_update"],
  "tags": ["external", "tool"],
  "config_schema": {
    "api_key": {"type": "string", "required": true},
    "default_city": {"type": "string", "default": "Buenos Aires"}
  }
}
```

### `plugin.py`

```python
"""Weather plugin — example of a ToolPlugin with routes and events."""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.plugin_types import PluginLifecycleHooks
from system.sdk.context import PluginContext
from system.sdk.contracts import ToolRegistryContract, ToolRuntimeContract
from system.sdk.models import ToolContract

logger = logging.getLogger(__name__)


class WeatherPlugin(PluginLifecycleHooks):
    plugin_id = "capos.example.weather"
    plugin_name = "Weather Plugin"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self._api_key: str = ""
        self._default_city: str = "Buenos Aires"
        self._last_result: dict[str, Any] = {}

    # ── Lifecycle ──────────────────────────────────────────────

    def initialize(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        settings = ctx.plugin_settings(self.plugin_id)
        self._api_key = settings.get("api_key", "")
        self._default_city = settings.get("default_city", "Buenos Aires")
        logger.info("Weather plugin initialized (city=%s)", self._default_city)

    def start(self) -> None:
        logger.info("Weather plugin started")

    def stop(self) -> None:
        logger.info("Weather plugin stopped")

    # ── Tool Registration ─────────────────────────────────────

    def register_tools(self, tool_registry, tool_runtime) -> list[str]:
        tool = ToolContract(
            id="weather_lookup",
            name="Weather Lookup",
            category="information",
            description="Get current weather for a city",
            inputs={
                "city": {
                    "type": "string",
                    "description": "City name",
                    "default": self._default_city,
                }
            },
            outputs={
                "temperature": {"type": "number"},
                "condition": {"type": "string"},
            },
        )
        tool_registry.register(tool, source=self.plugin_id)
        tool_runtime.register_handler("weather_lookup", self._handle_weather)
        return ["weather_lookup"]

    def _handle_weather(self, params: dict[str, Any]) -> dict[str, Any]:
        city = params.get("city", self._default_city)
        # In production, call a real weather API here
        result = {
            "city": city,
            "temperature": 22,
            "condition": "sunny",
        }
        self._last_result = result

        # Emit event for real-time UI updates
        if self._ctx:
            self._ctx.event_bus.emit("weather_update", result)

        return result

    # ── Routes ────────────────────────────────────────────────

    def register_routes(self, router) -> None:
        router.add("GET", "/weather/status", self._handle_status)
        router.add("POST", "/weather/lookup", self._handle_lookup_route)

    def _handle_status(self, request: Any) -> dict[str, Any]:
        return {
            "plugin": self.plugin_id,
            "version": self.version,
            "configured": bool(self._api_key),
            "default_city": self._default_city,
            "last_result": self._last_result,
        }

    def _handle_lookup_route(self, request: Any) -> dict[str, Any]:
        body = request.get("body", {})
        return self._handle_weather(body)

    # ── Hot-Reload ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {"last_result": self._last_result}

    def restore_state(self, state: dict[str, Any]) -> None:
        self._last_result = state.get("last_result", {})

    # ── Health Check ──────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        return {
            "healthy": bool(self._api_key),
            "message": "OK" if self._api_key else "Missing API key",
            "checks": {"api_key": bool(self._api_key)},
        }

    # ── Config Change ─────────────────────────────────────────

    def on_config_changed(self, new_config: dict[str, Any]) -> None:
        self._api_key = new_config.get("api_key", self._api_key)
        self._default_city = new_config.get("default_city", self._default_city)


# ── Factory ────────────────────────────────────────────────────

def create_plugin() -> WeatherPlugin:
    return WeatherPlugin()
```

---

## Testing Plugins

### Unit Testing

Test plugins by mocking the `PluginContext`:

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from system.plugins.my_plugin.plugin import create_plugin


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.workspace_root = Path("/tmp/test-workspace")
    ctx.project_root = Path("/tmp/test-project")
    ctx.settings = {"my_plugin": {"api_key": "test-key"}}
    ctx.plugin_settings.return_value = {"api_key": "test-key"}
    ctx.event_bus = MagicMock()
    return ctx


def test_plugin_lifecycle(mock_context):
    plugin = create_plugin()

    assert plugin.plugin_id == "capos.example.weather"
    assert plugin.version == "1.0.0"

    plugin.initialize(mock_context)
    plugin.start()
    plugin.stop()


def test_health_check(mock_context):
    plugin = create_plugin()
    plugin.initialize(mock_context)

    health = plugin.health_check()
    assert health["healthy"] is True


def test_hot_reload(mock_context):
    plugin = create_plugin()
    plugin.initialize(mock_context)

    # Simulate state
    state = plugin.get_state()

    # Create new instance and restore
    new_plugin = create_plugin()
    new_plugin.initialize(mock_context)
    new_plugin.restore_state(state)
```

### Contract Validation

Use the SDK's built-in validator to verify your plugin satisfies its contracts:

```python
from system.sdk.validation import validate_plugin, validate_contract
from system.sdk.contracts import ToolRegistryContract

# Validate BasePlugin interface
violations = validate_plugin(my_plugin_instance)
assert violations == [], f"Plugin violations: {violations}"

# Validate a contract implementation
violations = validate_contract(ToolRegistryContract, my_registry_impl)
assert violations == [], f"Contract violations: {violations}"
```

### Plugin Lifecycle States

During loading, plugins transition through these states:

```
REGISTERED -> INITIALIZING -> INITIALIZED -> STARTING -> RUNNING
                                                    |
                                              STOPPING -> STOPPED
                                                    |
                                                  ERROR
```

States are defined in `system/sdk/lifecycle.py` as `PluginState` enum values.
