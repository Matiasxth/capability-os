# Event Catalog

Complete reference for all events in Capability OS. Events flow from the backend `EventBus` through WebSocket connections to the frontend `sdk.events` system in real time.

---

## Table of Contents

- [Event Format](#event-format)
- [Event Types by Category](#event-types-by-category)
  - [Messages](#messages)
  - [Sessions and Execution](#sessions-and-execution)
  - [Settings and Configuration](#settings-and-configuration)
  - [Workspace](#workspace)
  - [Memory](#memory)
  - [Integrations](#integrations)
  - [Growth and Optimization](#growth-and-optimization)
  - [MCP](#mcp)
  - [A2A](#a2a)
  - [Browser](#browser)
  - [Supervisor](#supervisor)
  - [Scheduler](#scheduler)
  - [Auth](#auth)
  - [Errors](#errors)
- [Frontend Usage](#frontend-usage)
- [Backend Usage](#backend-usage)

---

## Event Format

Every event emitted through the `EventBus` follows this structure:

```json
{
  "type": "event_type_string",
  "timestamp": "2026-03-30T14:22:33Z",
  "data": {
    "key": "value"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `string` | Event type identifier (see catalog below) |
| `timestamp` | `string` | ISO 8601 UTC timestamp |
| `data` | `object` | Event-specific payload (always an object, never null) |

The `EventBus` adds `type` and `timestamp` automatically. Emitters only provide the event type string and the `data` payload.

---

## Event Types by Category

### Messages

Incoming messages from external messaging channels. These events trigger history reloads in the frontend.

#### `telegram_message`

| | |
|---|---|
| **Type string** | `telegram_message` |
| **Payload** | `chat_id`, `text`, `from_user`, `message_id` |
| **Emitter** | `system/integrations/installed/telegram_bot_connector/connector.py` (TelegramPollingWorker) |
| **When** | A new message is received from a Telegram chat |

#### `whatsapp_message`

| | |
|---|---|
| **Type string** | `whatsapp_message` |
| **Payload** | `chat_id`, `text`, `from_user`, `timestamp` |
| **Emitter** | `system/whatsapp_worker/whatsapp_client.py` |
| **When** | A new WhatsApp message is detected by the polling worker |

#### `whatsapp_message_processed`

| | |
|---|---|
| **Type string** | `whatsapp_message_processed` |
| **Payload** | `chat_id`, `response`, `status` |
| **Emitter** | WhatsApp reply worker |
| **When** | A WhatsApp message has been processed and replied to |

#### `slack_message`

| | |
|---|---|
| **Type string** | `slack_message` |
| **Payload** | `channel_id`, `text`, `user_id`, `ts` |
| **Emitter** | `system/integrations/installed/slack_bot_connector/` (SlackPollingWorker) |
| **When** | A new message is received from a Slack channel |

#### `discord_message`

| | |
|---|---|
| **Type string** | `discord_message` |
| **Payload** | `channel_id`, `text`, `user_id`, `message_id` |
| **Emitter** | `system/integrations/installed/discord_bot_connector/` (DiscordPollingWorker) |
| **When** | A new message is received from a Discord channel |

---

### Sessions and Execution

Events related to agent sessions and capability execution.

#### `session_updated`

| | |
|---|---|
| **Type string** | `session_updated` |
| **Payload** | `session_id`, optionally `action` (`"deleted"`, `"compacted"`) and `count` |
| **Emitter** | `system/core/ui_bridge/handlers/memory_handlers.py` |
| **When** | A chat session is created, updated, deleted, or compacted |

#### `execution_complete`

| | |
|---|---|
| **Type string** | `execution_complete` |
| **Payload** | `execution_id`, `capability_id`, `status` (`"success"` or `"error"`) |
| **Emitter** | `system/core/ui_bridge/api_server.py` (execution endpoints) |
| **When** | A capability execution finishes (success or error) |

---

### Settings and Configuration

Events triggered by settings changes.

#### `settings_updated`

| | |
|---|---|
| **Type string** | `settings_updated` |
| **Payload** | `keys` (list of changed setting keys) |
| **Emitter** | `system/core/ui_bridge/handlers/system_handlers.py` |
| **When** | Settings are saved via the API |

#### `config_imported`

| | |
|---|---|
| **Type string** | `config_imported` |
| **Payload** | `{}` (empty) |
| **Emitter** | `system/core/ui_bridge/handlers/system_handlers.py` |
| **When** | A full configuration export is imported |

#### `preferences_updated`

| | |
|---|---|
| **Type string** | `preferences_updated` |
| **Payload** | `keys` (list of changed preference keys) |
| **Emitter** | `system/core/ui_bridge/handlers/memory_handlers.py` |
| **When** | User preferences (UI theme, language, etc.) are updated |

---

### Workspace

Events related to workspace management.

#### `workspace_changed`

| | |
|---|---|
| **Type string** | `workspace_changed` |
| **Payload** | `action` (`"added"`, `"updated"`, `"removed"`, `"default_changed"`, `"status_changed"`), `workspace_id` |
| **Emitter** | `system/core/ui_bridge/handlers/workspace_handlers.py` |
| **When** | A workspace is added, modified, removed, or its status/default changes |

---

### Memory

Events related to memory management.

#### `memory_cleared`

| | |
|---|---|
| **Type string** | `memory_cleared` |
| **Payload** | `{}` (empty) |
| **Emitter** | `system/core/ui_bridge/handlers/memory_handlers.py` |
| **When** | All memory entries are cleared |

---

### Integrations

Events for integration and skill changes.

#### `integration_changed`

| | |
|---|---|
| **Type string** | `integration_changed` |
| **Payload** | `action` and context-specific fields |
| **Emitter** | `system/core/ui_bridge/handlers/integration_handlers.py`, `system/core/ui_bridge/handlers/skill_handlers.py` |
| **When** | An integration is enabled/disabled/configured, or a skill is installed/uninstalled |

**Possible `action` values:**
- `"enabled"`, `"disabled"` (integration toggle)
- `"whatsapp_configured"`, `"whatsapp_backend_switched"` (WhatsApp setup)
- `"telegram_configured"`, `"telegram_polling_started"`, `"telegram_polling_stopped"`
- `"slack_configured"`, `"slack_polling_started"`, `"slack_polling_stopped"`
- `"discord_configured"`, `"discord_polling_started"`, `"discord_polling_stopped"`
- `"skill_installed"`, `"skill_uninstalled"` (skill lifecycle)

---

### Growth and Optimization

Events from the self-improvement engine.

#### `growth_update`

| | |
|---|---|
| **Type string** | `growth_update` |
| **Payload** | `action`, plus `gap_id`, `capability_id`, or `optimization_id` depending on the action |
| **Emitter** | `system/core/ui_bridge/handlers/growth_handlers.py` |
| **When** | A capability gap is detected, a proposal is approved, or an optimization is applied |

**Possible `action` values:**
- `"gap_generated"` -- new capability gap identified
- `"gap_approved"` -- gap approved for development
- `"proposal_approved"` -- capability proposal approved
- `"optimization_approved"` -- optimization applied

---

### MCP

Events for Model Context Protocol server changes.

#### `mcp_changed`

| | |
|---|---|
| **Type string** | `mcp_changed` |
| **Payload** | `action`, optionally `server_id` or `tool_id` |
| **Emitter** | `system/core/ui_bridge/handlers/mcp_handlers.py` |
| **When** | An MCP server is added/removed, or an MCP tool is installed/uninstalled |

**Possible `action` values:**
- `"server_added"`, `"server_removed"`
- `"tool_installed"`, `"tool_uninstalled"`

---

### A2A

Events for Agent-to-Agent protocol changes.

#### `a2a_changed`

| | |
|---|---|
| **Type string** | `a2a_changed` |
| **Payload** | `action`, optionally `agent_id` |
| **Emitter** | `system/core/ui_bridge/handlers/a2a_handlers.py` |
| **When** | An A2A remote agent is added, removed, or a task is delegated |

**Possible `action` values:**
- `"agent_added"`, `"agent_removed"`, `"task_delegated"`

---

### Browser

Events from the browser worker subsystem.

#### `browser_changed`

| | |
|---|---|
| **Type string** | `browser_changed` |
| **Payload** | `action` |
| **Emitter** | `system/core/ui_bridge/handlers/browser_handlers.py` |
| **When** | The browser worker is restarted, Chrome is launched, or a CDP connection is established |

**Possible `action` values:**
- `"worker_restarted"`, `"chrome_launched"`, `"cdp_connected"`

---

### Supervisor

Events from the autonomous supervisor system.

#### `supervisor_alert`

| | |
|---|---|
| **Type string** | `supervisor_alert` |
| **Payload** | Varies by source -- includes `type`, `message`, and source-specific fields |
| **Emitter** | `system/core/supervisor/error_interceptor.py`, `system/core/supervisor/gap_detector.py`, `system/core/supervisor/security_auditor.py`, `system/core/supervisor/supervisor_daemon.py` |
| **When** | The supervisor detects an error pattern, capability gap, security issue, or health problem |

#### `supervisor_action`

| | |
|---|---|
| **Type string** | `supervisor_action` |
| **Payload** | `action` (action type), `result` (status) |
| **Emitter** | `system/core/ui_bridge/handlers/supervisor_handlers.py` |
| **When** | A supervisor action (fix, approve, reject) is executed by the user |

#### `skill_created`

| | |
|---|---|
| **Type string** | `skill_created` |
| **Payload** | `tool_id`, `auto` (boolean) |
| **Emitter** | `system/core/supervisor/skill_creator.py` |
| **When** | The supervisor auto-creates a new skill from a repeated tool pattern |

---

### Scheduler

Events from the task scheduler.

#### `scheduler_cycle`

| | |
|---|---|
| **Type string** | `scheduler_cycle` |
| **Payload** | `task_id`, `description`, `status`, `result` or error details |
| **Emitter** | `system/core/scheduler/proactive_scheduler.py` |
| **When** | A scheduled task completes a cycle (success or failure) |

---

### Auth

Events from the authentication system.

#### `auth_setup_complete`

| | |
|---|---|
| **Type string** | `auth_setup_complete` |
| **Payload** | `user_id` |
| **Emitter** | `system/core/ui_bridge/handlers/auth_handlers.py` |
| **When** | The initial owner account setup is completed |

---

### Errors

System-level error events.

#### `error`

| | |
|---|---|
| **Type string** | `error` |
| **Payload** | `source`, `message`, optionally `path`, `method` |
| **Emitter** | `system/core/ui_bridge/api_server.py`, `system/integrations/channel_adapter.py` |
| **When** | An unhandled error occurs in an API handler or channel polling worker |

**Possible `source` values:**
- `"handler"` -- API route handler error
- `"api_dispatch"` -- API dispatch error
- `"telegram_polling"` -- Telegram polling error
- `"<channel>_polling"` -- Any channel polling error

---

## Frontend Usage

### Importing Event Types

```javascript
import { EVENTS, HISTORY_EVENTS, EVENT_LABELS, SECTION_FOR_EVENT } from "../sdk/eventTypes";
```

### Subscribing to Events

```javascript
import sdk from "../sdk";

// Subscribe to a specific event
sdk.events.on(EVENTS.EXECUTION_COMPLETE, (event) => {
  console.log("Execution done:", event.data.execution_id);
});

// Subscribe to all events (wildcard)
sdk.events.on("*", (event) => {
  console.log("Event:", event.type, event.data);
});

// Unsubscribe
const unsub = sdk.events.on(EVENTS.SETTINGS_UPDATED, handler);
unsub(); // later
```

### Connection Status

```javascript
sdk.events.onConnectionChange((connected) => {
  console.log("WebSocket connected:", connected);
});
```

### History Events

`HISTORY_EVENTS` lists events that should trigger a history reload:

```javascript
const HISTORY_EVENTS = [
  "telegram_message",
  "whatsapp_message",
  "slack_message",
  "discord_message",
  "session_updated",
  "execution_complete",
  "memory_cleared",
];
```

### Event Labels

`EVENT_LABELS` maps events to user-friendly toast messages:

```javascript
const EVENT_LABELS = {
  settings_updated:    "Settings updated",
  config_imported:     "Config imported",
  workspace_changed:   "Workspace updated",
  growth_update:       "Growth updated",
  integration_changed: "Integration updated",
  mcp_changed:         "MCP updated",
  a2a_changed:         "A2A updated",
  browser_changed:     "Browser updated",
  preferences_updated: "Preferences saved",
  memory_cleared:      "Memory cleared",
  supervisor_alert:    "Supervisor alert",
  skill_created:       "Skill created",
  scheduler_cycle:     "Scheduler cycle",
};
```

### Section Mapping

`SECTION_FOR_EVENT` maps events to Control Center sections for auto-navigation:

```javascript
const SECTION_FOR_EVENT = {
  settings_updated:    "llm",
  config_imported:     "system",
  workspace_changed:   "workspaces",
  growth_update:       "self-improvement",
  integration_changed: "integrations",
  mcp_changed:         "mcp",
  a2a_changed:         "a2a",
  browser_changed:     "browser",
  memory_cleared:      "memory",
  preferences_updated: "memory",
  supervisor_alert:    "supervisor",
  skill_created:       "skills",
  scheduler_cycle:     "scheduler",
};
```

---

## Backend Usage

### Emitting Events

```python
from system.core.ui_bridge.event_bus import event_bus

# Simple event
event_bus.emit("my_event", {"key": "value"})

# Channel message event
event_bus.emit("telegram_message", {
    "chat_id": "123456",
    "text": "Hello from the bot",
    "from_user": "user123",
})

# Error event
event_bus.emit("error", {
    "source": "my_plugin",
    "message": "Something went wrong",
})
```

### Subscribing (Backend)

```python
from system.core.ui_bridge.event_bus import event_bus

def my_handler(event):
    if event["type"] == "settings_updated":
        # Reload configuration
        pass

unsubscribe = event_bus.subscribe(my_handler)

# Later, to unsubscribe:
unsubscribe()
```

### Event Bus Properties

- **Thread-safe**: All operations use an internal `threading.Lock`
- **Fire-and-forget**: Subscriber errors are silently caught -- a bad subscriber never blocks the emitter
- **Synchronous**: Events are delivered synchronously to all subscribers
- **Singleton**: `event_bus` is a module-level singleton shared across the entire system

### From Plugin Context

Plugins should use the event bus from their context:

```python
class MyPlugin:
    def initialize(self, ctx):
        self._event_bus = ctx.event_bus

    def do_work(self):
        self._event_bus.emit("my_plugin_event", {"result": "done"})
```

---

## Quick Reference Table

| Event Type | Category | Trigger |
|---|---|---|
| `telegram_message` | Messages | Incoming Telegram message |
| `whatsapp_message` | Messages | Incoming WhatsApp message |
| `whatsapp_message_processed` | Messages | WhatsApp message processed |
| `slack_message` | Messages | Incoming Slack message |
| `discord_message` | Messages | Incoming Discord message |
| `session_updated` | Sessions | Chat session CRUD |
| `execution_complete` | Sessions | Capability execution done |
| `settings_updated` | Settings | Settings saved |
| `config_imported` | Settings | Config import |
| `preferences_updated` | Settings | Preferences saved |
| `workspace_changed` | Workspace | Workspace CRUD |
| `memory_cleared` | Memory | Memory wiped |
| `integration_changed` | Integrations | Integration or skill changed |
| `growth_update` | Growth | Gap/proposal/optimization |
| `mcp_changed` | MCP | MCP server or tool changed |
| `a2a_changed` | A2A | A2A agent or task changed |
| `browser_changed` | Browser | Browser worker state changed |
| `supervisor_alert` | Supervisor | Supervisor detection |
| `supervisor_action` | Supervisor | User action on supervisor item |
| `skill_created` | Supervisor | Auto-skill creation |
| `scheduler_cycle` | Scheduler | Scheduled task completed |
| `auth_setup_complete` | Auth | Owner account created |
| `error` | Errors | Unhandled system error |
