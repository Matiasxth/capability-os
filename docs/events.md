# Event Catalog

All events emitted via `event_bus.emit()` and broadcast to WebSocket clients and SSE streams.

## Event Format

Every event has the shape:
```json
{
  "type": "event_type",
  "timestamp": "2026-03-30T15:00:00Z",
  "data": { ... }
}
```

---

## Channel / Messaging Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `telegram_message` | `integrations/installed/telegram_bot_connector/connector.py:428` | `chat_id`, `user`, `text` | Workspace.jsx |
| `whatsapp_message` | `whatsapp_worker/whatsapp_client.py:225`, `backends/official_backend.py:226`, `backends/base.py:8` | `from`, `pushName`, `text`, `messageId` | Workspace.jsx |
| `whatsapp_message_processed` | `whatsapp_web_connector/whatsapp_reply_worker.py:153` | `contact`, `response_preview` | — |
| `slack_message` | `integrations/channel_adapter.py:242` | `user`, `text`, `channel` | Workspace.jsx |
| `discord_message` | `integrations/channel_adapter.py:242` | `user`, `text`, `channel` | Workspace.jsx |

## System Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `error` | `api_server.py:581,1836`, `channel_adapter.py:205`, `telegram connector:369` | `source`, `path`/`method`, `message` | ControlCenter.jsx (toast) |
| `settings_updated` | `handlers/system_handlers.py:28` | `keys` | ControlCenter.jsx |
| `config_imported` | `handlers/system_handlers.py:77` | `{}` | ControlCenter.jsx |
| `auth_setup_complete` | `handlers/auth_handlers.py:96` | `user_id` | — |

## Workspace Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `workspace_changed` | `handlers/workspace_handlers.py:41,61,74,87,101` | `action` (`added`/`updated`/`removed`/`default_changed`/`status_changed`), `workspace_id` | ControlCenter.jsx |

## Integration Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `integration_changed` | `handlers/integration_handlers.py` (12 sites), `handlers/skill_handlers.py:39,55` | `action` (`enabled`/`disabled`/`whatsapp_configured`/`whatsapp_backend_switched`/`telegram_configured`/`telegram_polling_started`/`telegram_polling_stopped`/`slack_*`/`discord_*`/`skill_installed`/`skill_uninstalled`), `integration_id`/`backend`/`skill_id` | ControlCenter.jsx |

## Memory Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `session_updated` | `handlers/memory_handlers.py:58,70,90,183`, `channel_adapter.py:394`, `whatsapp_reply_worker.py:390`, `telegram connector:605` | `session_id`, `action` (optional: `deleted`/`compacted`) | ControlCenter.jsx |
| `preferences_updated` | `handlers/memory_handlers.py:114` | `keys` | ControlCenter.jsx |
| `memory_cleared` | `handlers/memory_handlers.py:152` | `{}` | ControlCenter.jsx |

## MCP Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `mcp_changed` | `handlers/mcp_handlers.py:21,31,49,59` | `action` (`server_added`/`server_removed`/`tool_installed`/`tool_uninstalled`), `server_id`/`tool_id` | ControlCenter.jsx |

## A2A Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `a2a_changed` | `handlers/a2a_handlers.py:37,47,57` | `action` (`agent_added`/`agent_removed`/`task_delegated`), `agent_id` | ControlCenter.jsx |

## Growth / Self-Improvement Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `growth_update` | `handlers/growth_handlers.py:25,35,57,75` | `action` (`gap_generated`/`gap_approved`/`proposal_approved`/`optimization_approved`), `gap_id`/`capability_id`/`optimization_id` | ControlCenter.jsx |

## Browser Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `browser_changed` | `handlers/browser_handlers.py:13,29,45` | `action` (`worker_restarted`/`chrome_launched`/`cdp_connected`) | ControlCenter.jsx |

## Execution Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `execution_complete` | `api_server.py:1247,1267,1287` | `execution_id`, `capability_id`, `status` (`success`/`error`) | Workspace.jsx |

## Supervisor Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `supervisor_alert` | `supervisor_daemon.py:130`, `security_auditor.py:251`, `gap_detector.py:212`, `error_interceptor.py:112` | `severity` (`info`/`warning`/`high`/`critical`), `source`, `message`, `findings` (optional) | Future: Supervisor UI |
| `supervisor_action` | `handlers/supervisor_handlers.py:92` | `action`, `result` | — |
| `skill_created` | `supervisor/skill_creator.py:143` | `tool_id`, `auto` | Future: Skills UI |

## Scheduler Events

| Event | Source File | Data Fields | Frontend Consumer |
|-------|-----------|-------------|-------------------|
| `scheduler_cycle` | `scheduler/proactive_scheduler.py:154,188` | `cycle` (`quick`/`deep`), `ready_tasks`/`disabled_tasks` (quick), `summary` (deep) | Future: Scheduler UI |

---

## WebSocket Consumer Mapping (ControlCenter.jsx)

The frontend maps events to UI sections for auto-refresh:

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
};
```

When an event arrives whose type is in this map, the corresponding section auto-refreshes and a toast notification appears.

The `error` event type triggers an error toast regardless of section.

---

## How to Emit Events

### From Python (backend)

```python
from system.core.ui_bridge.event_bus import event_bus

event_bus.emit("my_event", {"key": "value"})
```

### From a Plugin

```python
def initialize(self, ctx: PluginContext) -> None:
    self._event_bus = ctx.event_bus

def some_method(self):
    self._event_bus.emit("my_event", {"action": "something_happened"})
```

### Subscribing (Python)

```python
unsub = event_bus.subscribe(lambda evt: print(evt["type"], evt["data"]))
# Later:
unsub()
```

### Subscribing (React)

```jsx
import { useWebSocket } from "../hooks/useWebSocket";

function MyComponent() {
  const handleEvent = useCallback((event) => {
    if (event.type === "my_event") {
      // react to event
    }
  }, []);
  const { connected } = useWebSocket(handleEvent);
}
```
