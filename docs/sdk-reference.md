# SDK Reference

Complete reference for the CapabilityOS Plugin SDK.

Location: `system/sdk/`

---

## Plugin Types

All plugin types are `@runtime_checkable` Protocol classes defined in `system/sdk/plugin_types.py`.

### BasePlugin

Every plugin must satisfy this interface.

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

Registers tools into the ToolRuntime.

```python
class ToolPlugin(BasePlugin, Protocol):
    def register_tools(self, tool_registry: Any, tool_runtime: Any) -> list[str]: ...
```

### ChannelPlugin

Provides a messaging channel (Telegram, Slack, etc.).

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

Provides a memory backend.

```python
class MemoryPlugin(BasePlugin, Protocol):
    def store(self, key: str, value: Any, **kw: Any) -> None: ...
    def retrieve(self, key: str) -> Any: ...
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
```

### AgentPlugin

Registers agent types or behaviors.

```python
class AgentPlugin(BasePlugin, Protocol):
    def get_agent_types(self) -> list[dict[str, Any]]: ...
```

### UIPlugin

Registers Control Center UI sections and routes.

```python
class UIPlugin(BasePlugin, Protocol):
    def get_ui_sections(self) -> list[dict[str, Any]]: ...
    def register_routes(self, router: Any) -> None: ...
```

---

## Service Contracts

Typed Protocol interfaces for cross-plugin communication. Defined in `system/sdk/contracts.py`. Plugins resolve these through `PluginContext.get_service()`.

### EventBusContract

```python
class EventBusContract(Protocol):
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None: ...
    def subscribe(self, callback: Any) -> Any: ...
```

### SettingsProvider

```python
class SettingsProvider(Protocol):
    def load_settings(self) -> dict[str, Any]: ...
    def get_settings(self, *, mask_secrets: bool = True) -> dict[str, Any]: ...
    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]: ...
```

### ToolRegistryContract

```python
class ToolRegistryContract(Protocol):
    def get(self, tool_id: str) -> dict[str, Any] | None: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def ids(self) -> list[str]: ...
    def register(self, contract: dict[str, Any], *, source: str = "<memory>") -> None: ...
```

### ToolRuntimeContract

```python
class ToolRuntimeContract(Protocol):
    def execute(self, action: str, params: dict[str, Any]) -> Any: ...
    def register_handler(self, tool_id: str, handler: Any) -> None: ...
```

### CapabilityRegistryContract

```python
class CapabilityRegistryContract(Protocol):
    def get(self, capability_id: str) -> dict[str, Any] | None: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def ids(self) -> list[str]: ...
    def register(self, contract: dict[str, Any], *, source: str = "<memory>") -> None: ...
```

### CapabilityEngineContract

```python
class CapabilityEngineContract(Protocol):
    def execute(
        self,
        contract: dict[str, Any],
        inputs: dict[str, Any],
        event_callback: Any = None,
    ) -> dict[str, Any]: ...
```

### IntentInterpreterContract

```python
class IntentInterpreterContract(Protocol):
    def interpret(self, text: str, history: Any = None) -> dict[str, Any]: ...
    def classify_message(self, text: str) -> str: ...
    def chat_response(self, text: str, user_name: str = "") -> str: ...
```

### LLMClientContract

```python
class LLMClientContract(Protocol):
    def complete(self, system_prompt: str = "", user_prompt: str = "") -> str: ...
```

### SecurityServiceContract

```python
class SecurityServiceContract(Protocol):
    def classify(
        self,
        capability_id: str = "",
        tool_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> Any: ...
    def classify_description(self, level: Any) -> str: ...
```

### MemoryManagerContract

```python
class MemoryManagerContract(Protocol):
    def recall(self, key: str) -> Any: ...
    def remember(self, key: str, value: Any, **kw: Any) -> Any: ...
    def recall_all(self, memory_type: str | None = None) -> list[dict[str, Any]]: ...
    def forget(self, memory_id: str) -> bool: ...
    def count(self) -> int: ...
```

### ExecutionHistoryContract

```python
class ExecutionHistoryContract(Protocol):
    def upsert_chat(
        self, session_id: str, intent: str,
        messages: list | None = None,
        duration_ms: int = 0,
        workspace_id: str | None = None,
    ) -> str | None: ...
    def get_recent(self, n: int = 20) -> list[dict[str, Any]]: ...
    def get_by_workspace(self, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_session(self, execution_id: str) -> dict[str, Any] | None: ...
    def get_stats(self) -> dict[str, Any]: ...
    def count(self) -> int: ...
```

### SemanticMemoryContract

```python
class SemanticMemoryContract(Protocol):
    def remember_semantic(self, text: str, **kw: Any) -> dict[str, Any] | None: ...
    def recall_semantic(self, query: str, top_k: int = 5) -> list[dict[str, Any]]: ...
    def forget_semantic(self, memory_id: str) -> bool: ...
    def count(self) -> int: ...
```

### MarkdownMemoryContract

```python
class MarkdownMemoryContract(Protocol):
    def load_memory_md(self) -> str: ...
    def save_memory_md(self, content: str) -> None: ...
    def load_memory_sections(self) -> dict[str, list[str]]: ...
    def add_fact(self, section: str, fact: str) -> None: ...
    def remove_fact(self, section: str, fact_substring: str) -> bool: ...
    def append_daily(self, entry: str, section: str = "Sessions") -> None: ...
    def build_context(self, max_tokens: int = 500) -> str: ...
```

### AgentLoopContract

```python
class AgentLoopContract(Protocol):
    def run(
        self, user_message: str,
        session_id: str | None = None,
        conversation_history: list | None = None,
        agent_config: dict[str, Any] | None = None,
        workspace_id: str | None = None,
        workspace_path: str | None = None,
    ) -> Any: ...
    def get_session(self, session_id: str) -> Any: ...
```

### AgentRegistryContract

```python
class AgentRegistryContract(Protocol):
    def list(self) -> list[dict[str, Any]]: ...
    def get(self, agent_id: str) -> dict[str, Any] | None: ...
    def create(self, data: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, agent_id: str, data: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete(self, agent_id: str) -> bool: ...
```

### WorkspaceRegistryContract

```python
class WorkspaceRegistryContract(Protocol):
    def list(self) -> list[dict[str, Any]]: ...
    def get(self, ws_id: str) -> dict[str, Any] | None: ...
    def get_default(self) -> dict[str, Any] | None: ...
    def add(self, name: str, path: str, **kw: Any) -> dict[str, Any]: ...
    def remove(self, ws_id: str) -> bool: ...
    def set_default(self, ws_id: str) -> bool: ...
    def update(self, ws_id: str, **kw: Any) -> dict[str, Any] | None: ...
```

### HealthServiceContract

```python
class HealthServiceContract(Protocol):
    def get_system_health(self) -> dict[str, Any]: ...
```

### MetricsCollectorContract

```python
class MetricsCollectorContract(Protocol):
    def get_metrics(self) -> dict[str, Any]: ...
    def record_execution(self, **kw: Any) -> None: ...
```

---

## PluginContext API

Defined in `system/sdk/context.py`.

```python
class PluginContext:
    workspace_root: Path          # User workspace directory
    project_root: Path            # CapabilityOS installation root
    settings: dict[str, Any]      # Full runtime settings
    event_bus: Any                # EventBus singleton

    def get_service(self, contract_type: type) -> Any
    def get_optional(self, contract_type: type) -> Any | None
    def publish_service(self, contract_type: type, implementation: Any) -> None
    def plugin_settings(self, plugin_id: str) -> dict[str, Any]
```

### Settings Resolution

`plugin_settings("capos.channels.telegram")` extracts the last segment (`telegram`) and returns `settings["telegram"]`. If the key doesn't exist or isn't a dict, returns `{}`.

---

## PluginManifest

Defined in `system/sdk/manifest.py`. Loaded from `capos-plugin.json` by the PluginLoader.

```python
@dataclass
class PluginManifest:
    id: str                              # "my-org.my-plugin"
    name: str                            # "My Plugin"
    version: str                         # "1.0.0"
    description: str = ""                # Short description
    author: str = "CapabilityOS"         # Author
    plugin_types: list[str] = []         # ["tool", "channel", ...]
    dependencies: list[str] = []         # ["capos.core.settings"]
    entry_point: str = "plugin:create_plugin"  # module:factory
    settings_key: str = ""               # Key in settings.json
    auto_start: bool = True              # Auto-start on boot
```

### Factory Methods

| Method | Description |
|--------|-------------|
| `PluginManifest.from_dict(data)` | Create from a dictionary |
| `PluginManifest.from_file(path)` | Load from a JSON file |
| `manifest.to_dict()` | Serialize to dictionary |

---

## ServiceContainer API

Defined in `system/container/service_container.py`. The central orchestrator.

```python
class ServiceContainer:
    def __init__(self, workspace_root, project_root, settings, event_bus)

    # Registration
    def register_plugin(self, plugin: Any, manifest: PluginManifest | None = None) -> None
    def register_service(self, contract_type: type, implementation: Any) -> None

    # Resolution
    def get_service(self, contract_type: type) -> Any          # raises KeyError
    def get_optional(self, contract_type: type) -> Any | None
    def get_plugin(self, plugin_id: str) -> Any | None

    # Lifecycle
    def initialize_all(self) -> list[str]    # returns error messages
    def start_all(self) -> list[str]         # returns error messages
    def stop_all(self) -> None

    # Inspection
    def get_status(self) -> dict[str, Any]

    # Properties
    @property plugins: dict[str, Any]
    @property workspace_root: Path
    @property project_root: Path
    @property settings: dict[str, Any]
    @property event_bus: Any
```

### Dependency Resolution

The container uses Kahn's algorithm (topological sort) to determine initialization order based on each plugin's `dependencies` list. Plugins with unmet dependencies are initialized last.

### Service Registration Flow

1. Plugin A calls `ctx.publish_service(FooContract, foo_impl)` during `initialize()`
2. The container stores `FooContract -> foo_impl` in its service registry
3. Plugin B calls `ctx.get_service(FooContract)` during its own `initialize()`
4. The container returns `foo_impl`

This works because Plugin B declares Plugin A in its `dependencies`, ensuring A initializes first.

---

## Lifecycle States

Defined in `system/sdk/lifecycle.py`.

```python
class PluginState(Enum):
    REGISTERED   = "registered"    # Plugin registered, not yet initialized
    INITIALIZING = "initializing"  # initialize() in progress
    INITIALIZED  = "initialized"   # initialize() completed
    STARTING     = "starting"      # start() in progress
    RUNNING      = "running"       # start() completed, fully operational
    STOPPING     = "stopping"      # stop() in progress
    STOPPED      = "stopped"       # stop() completed
    ERROR        = "error"         # Failed during any transition
```

### State Transitions

```
REGISTERED
    |
    v
INITIALIZING --[error]--> ERROR
    |
    v
INITIALIZED
    |
    v
STARTING -----[error]--> ERROR
    |
    v
RUNNING
    |
    v
STOPPING -----[error]--> ERROR
    |
    v
STOPPED
```

---

## Contract Validation

Defined in `system/sdk/validation.py`.

```python
def validate_contract(contract_type: type, implementation: Any) -> list[str]
```

Checks if an implementation satisfies a Protocol by verifying all non-private members exist and are callable where expected. Returns a list of violation messages (empty means valid).

```python
def validate_plugin(plugin: Any) -> list[str]
```

Validates that a plugin implements the BasePlugin interface: checks for `plugin_id`, `plugin_name`, `version`, `dependencies` attributes and `initialize()`, `start()`, `stop()` methods.

---

## Hot-Reload API

Defined in `system/container/hot_reload.py`.

```python
def reload_plugin(container: ServiceContainer, plugin_id: str) -> str | None
```

Stops the plugin, reimports its module, creates a new instance via `create_plugin()`, replaces it in the container, and re-initializes + starts it. Returns an error string or `None` on success.

```python
def install_plugin_from_path(container, plugin_path: str) -> tuple[str | None, str | None]
```

Loads a plugin from a filesystem path, registers it in the container, and starts it. Returns `(plugin_id, error)`.

---

## EventBus

Defined in `system/core/ui_bridge/event_bus.py`. Thread-safe synchronous pub/sub.

```python
class EventBus:
    def subscribe(self, callback) -> Callable[[], None]  # returns unsubscribe fn
    def emit(self, event_type: str, data: dict | None = None) -> None
    @property subscriber_count: int
```

Events are dicts with `type`, `timestamp`, and `data` fields. Subscriber errors are silently caught so emitters are never blocked.

Usage:
```python
from system.core.ui_bridge.event_bus import event_bus

unsub = event_bus.subscribe(lambda evt: print(evt["type"]))
event_bus.emit("my_event", {"key": "value"})
unsub()
```
