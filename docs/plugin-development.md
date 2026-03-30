# Plugin Development Guide

This guide covers how to create, install, and test plugins for CapabilityOS.

---

## Plugin Anatomy

A plugin is a directory containing at minimum:

```
my-plugin/
+-- capos-plugin.json   # manifest (metadata + entry point)
+-- plugin.py           # implementation + factory function
```

The `capos-plugin.json` manifest declares metadata. The `plugin.py` file exports a `create_plugin()` factory function that returns a plugin instance.

---

## Manifest (`capos-plugin.json`)

```json
{
  "id": "my-org.my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "Brief description of what the plugin does.",
  "author": "Your Name",
  "plugin_types": ["tool"],
  "dependencies": ["capos.core.settings"],
  "entry_point": "plugin:create_plugin",
  "settings_key": "my_plugin",
  "auto_start": true
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier (convention: `org.category.name`) |
| `name` | Yes | Human-readable display name |
| `version` | Yes | SemVer string |
| `description` | No | Short description |
| `author` | No | Author name (default: "CapabilityOS") |
| `plugin_types` | No | Categories: `tool`, `channel`, `memory`, `agent`, `ui` |
| `dependencies` | No | List of plugin IDs this plugin requires |
| `entry_point` | No | Module and factory function (default: `plugin:create_plugin`) |
| `settings_key` | No | Key in `settings.json` for this plugin's config |
| `auto_start` | No | Whether to start automatically (default: `true`) |

---

## BasePlugin Interface

Every plugin must implement the `BasePlugin` Protocol:

```python
class MyPlugin:
    plugin_id = "my-org.my-plugin"
    plugin_name = "My Plugin"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def initialize(self, ctx: PluginContext) -> None:
        """Called once during container initialization.

        This is where you:
        - Read settings via ctx.plugin_settings(self.plugin_id)
        - Resolve dependencies via ctx.get_service(ContractType)
        - Publish your own services via ctx.publish_service(ContractType, impl)
        - Create instances of your service classes
        """
        ...

    def start(self) -> None:
        """Called after all plugins are initialized.

        Start background threads, polling loops, or other active services.
        Passive plugins (no background work) can leave this empty.
        """
        ...

    def stop(self) -> None:
        """Called during shutdown (reverse dependency order).

        Clean up threads, close connections, release resources.
        """
        ...


def create_plugin():
    """Factory function — the entry point declared in the manifest."""
    return MyPlugin()
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `plugin_id` | `str` | Must match the manifest `id` |
| `plugin_name` | `str` | Display name |
| `version` | `str` | SemVer |
| `dependencies` | `list[str]` | Plugin IDs that must initialize before this one |

---

## PluginContext

The `PluginContext` is passed to `initialize()` and provides the dependency injection surface:

```python
def initialize(self, ctx: PluginContext) -> None:
    # Read this plugin's settings section
    settings = ctx.plugin_settings(self.plugin_id)

    # Resolve a required service (raises KeyError if missing)
    tool_runtime = ctx.get_service(ToolRuntimeContract)

    # Resolve an optional service (returns None if missing)
    agent_loop = ctx.get_optional(AgentLoopContract)

    # Publish a service for other plugins to consume
    ctx.publish_service(MyServiceContract, my_implementation)

    # Access shared resources
    workspace = ctx.workspace_root   # Path to user workspace
    project = ctx.project_root       # Path to CapabilityOS root
    bus = ctx.event_bus               # EventBus for pub/sub
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_service(contract_type)` | `Any` | Resolve a service by Protocol type. Raises `KeyError`. |
| `get_optional(contract_type)` | `Any or None` | Like `get_service` but returns `None` on miss. |
| `publish_service(contract_type, impl)` | `None` | Register an implementation for a Protocol contract. |
| `plugin_settings(plugin_id)` | `dict` | Get the settings section for a plugin. |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `workspace_root` | `Path` | User workspace directory |
| `project_root` | `Path` | CapabilityOS installation root |
| `settings` | `dict` | Full runtime settings |
| `event_bus` | `EventBus` | System event bus |

---

## Example: Channel Plugin

Channel plugins handle messaging for a specific platform.

```python
from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityEngineContract,
    IntentInterpreterContract,
)


class MyChannelPlugin:
    plugin_id = "my-org.channels.sms"
    plugin_name = "SMS Channel"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self):
        self.connector = None
        self._polling = False
        self._ctx = None

    def initialize(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        settings = ctx.plugin_settings(self.plugin_id)
        self.connector = SMSConnector(
            api_key=settings.get("api_key", ""),
            phone=settings.get("phone", ""),
        )

    def start(self) -> None:
        settings = self._ctx.plugin_settings(self.plugin_id)
        if not settings.get("polling_enabled"):
            return

        interpreter = self._ctx.get_optional(IntentInterpreterContract)
        engine = self._ctx.get_optional(CapabilityEngineContract)

        # Start polling in background thread
        self._polling = True
        self.connector.start_polling(interpreter, engine)

    def stop(self) -> None:
        if self._polling and self.connector:
            self.connector.stop_polling()

    # ChannelPlugin interface
    @property
    def channel_id(self) -> str:
        return "sms"

    def get_status(self) -> dict:
        return {"channel": "sms", "configured": bool(self.connector)}

    def configure(self, settings: dict) -> None:
        if self.connector:
            self.connector.configure(**settings)

    def send_message(self, target: str, text: str, **kw) -> dict:
        return self.connector.send(target, text)


def create_plugin():
    return MyChannelPlugin()
```

---

## Example: Tool Plugin

Tool plugins register handlers into the ToolRuntime.

```python
from system.sdk.context import PluginContext
from system.sdk.contracts import ToolRegistryContract, ToolRuntimeContract


class MyToolPlugin:
    plugin_id = "my-org.tools.calculator"
    plugin_name = "Calculator Tools"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def initialize(self, ctx: PluginContext) -> None:
        registry = ctx.get_service(ToolRegistryContract)
        runtime = ctx.get_service(ToolRuntimeContract)

        # Register tool contract
        registry.register({
            "id": "calculator_eval",
            "name": "Calculator",
            "description": "Evaluate a math expression",
            "inputs": {
                "expression": {"type": "string", "required": True}
            },
        })

        # Register handler
        runtime.register_handler("calculator_eval", self._handle_eval)

    def _handle_eval(self, action, params):
        expr = params.get("expression", "")
        # Safe eval (use ast.literal_eval or a parser in production)
        result = eval(expr)  # simplified for example
        return {"result": result}

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def create_plugin():
    return MyToolPlugin()
```

---

## Installing Plugins

### From CLI
```bash
python -m capabilityos plugins install /path/to/my-plugin
```

This copies the plugin directory into `system/plugins/` and prints instructions to restart.

### From API
```
POST /plugins/install
{"path": "/absolute/path/to/my-plugin"}
```

### Manual
Copy your plugin directory into `system/plugins/` and restart the server.

---

## Hot-Reloading

Reload a plugin without restarting the entire system:

```
POST /plugins/{plugin_id}/reload
```

The hot-reload process:
1. Stops the running plugin
2. Reimports the Python module
3. Calls `create_plugin()` to get a new instance
4. Replaces the old instance in the container
5. Re-initializes and starts the new instance

This is useful during development. Production changes should use a full restart.

---

## Testing Plugins

### Unit Test Pattern

```python
import pytest
from unittest.mock import MagicMock
from system.sdk.context import PluginContext


def make_test_context(**overrides):
    """Create a minimal PluginContext for testing."""
    services = overrides.get("services", {})

    def getter(ct):
        if ct in services:
            return services[ct]
        raise KeyError(ct.__name__)

    return PluginContext(
        workspace_root=overrides.get("workspace_root", "/tmp/test"),
        project_root=overrides.get("project_root", "/tmp/test"),
        settings=overrides.get("settings", {}),
        service_getter=getter,
        service_registrar=overrides.get("registrar", lambda ct, impl: None),
        event_bus=overrides.get("event_bus", MagicMock()),
    )


def test_my_plugin_initializes():
    from my_plugin.plugin import create_plugin

    plugin = create_plugin()
    ctx = make_test_context(settings={"my_plugin": {"key": "value"}})
    plugin.initialize(ctx)
    assert plugin.plugin_id == "my-org.my-plugin"


def test_my_plugin_start_stop():
    from my_plugin.plugin import create_plugin

    plugin = create_plugin()
    ctx = make_test_context()
    plugin.initialize(ctx)
    plugin.start()
    plugin.stop()
```

### Integration Test

Run the full server and check your plugin appears:

```bash
python -m capabilityos serve &
curl http://localhost:8000/plugins | python -m json.tool
```

### Validation

The SDK includes a validation utility:

```python
from system.sdk.validation import validate_plugin

plugin = create_plugin()
violations = validate_plugin(plugin)
if violations:
    print("Plugin validation failed:", violations)
```

---

## Lifecycle States

Plugins transition through these states:

```
REGISTERED -> INITIALIZING -> INITIALIZED -> STARTING -> RUNNING
                   |                             |
                   v                             v
                 ERROR                         ERROR
                                                 |
                                            STOPPING -> STOPPED
```

The ServiceContainer initializes and starts plugins in topological order (dependencies first) and stops them in reverse order.

---

## Best Practices

1. **Depend on contracts, not implementations.** Use `ctx.get_service(SomeContract)` instead of importing concrete classes.

2. **Declare dependencies explicitly.** If your plugin needs the agent loop, add `capos.core.agent` to `dependencies`.

3. **Keep `initialize()` fast.** Do heavy work (network calls, large file reads) in `start()` or lazily.

4. **Handle missing optionals gracefully.** Use `ctx.get_optional()` for services that may not be available.

5. **Publish services early.** Other plugins may depend on what you publish, so do it in `initialize()`.

6. **Use the event bus for loose coupling.** Emit events instead of calling other plugins directly when possible. See [Event Catalog](events.md) for all available event types.

7. **Settings convention.** Use `ctx.plugin_settings(self.plugin_id)` which maps `capos.channels.telegram` to `settings["telegram"]`.

---

## Emitting Events

Plugins can emit events to notify the frontend and other subscribers in real time.

### From initialize() or service methods

```python
def initialize(self, ctx: PluginContext) -> None:
    self._event_bus = ctx.event_bus

def some_action(self):
    # Emit an event — delivered via WebSocket to all connected clients
    self._event_bus.emit("my_plugin_event", {
        "action": "data_processed",
        "count": 42,
    })
```

### From handlers (API route functions)

```python
def my_handler(service, payload, **kw):
    from system.core.ui_bridge.event_bus import event_bus
    # ... do work ...
    event_bus.emit("integration_changed", {"action": "my_thing_happened"})
    return _resp(HTTPStatus.OK, {"status": "success"})
```

### Frontend auto-refresh

To make the ControlCenter auto-refresh when your event fires, add your event type to the `SECTION_FOR_EVENT` map in `ControlCenter.jsx`:

```javascript
const SECTION_FOR_EVENT = {
  // ... existing mappings ...
  my_plugin_event: "my-section",
};
```

For the full list of events, payloads, and consumers, see **[docs/events.md](events.md)**.

---

## Registering API Routes

Plugins don't register routes directly — routes are declared in `api_server.py._build_router()`. To add endpoints for your plugin:

1. Create a handler module: `system/core/ui_bridge/handlers/my_handlers.py`
2. Define handler functions following the signature: `def my_handler(service, payload, **kw) -> APIResponse`
3. Register routes in `_build_router()`:

```python
from system.core.ui_bridge.handlers import my_handlers
r.add("GET", "/my-plugin/status", my_handlers.get_status)
r.add("POST", "/my-plugin/action", my_handlers.do_action)
```

4. Access your plugin's services via `service.container.get_plugin("my-org.my-plugin")`
