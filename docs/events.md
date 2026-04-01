# Event Catalog

All events emitted via `event_bus.emit()` and broadcast to WebSocket clients.

## Event Format

```json
{
  "type": "event_type",
  "timestamp": "2026-03-30T14:22:01.123Z",
  "data": { ... }
}
```

## Message Reception

| Event | Payload | Source |
|-------|---------|--------|
| `telegram_message` | `{chat_id, user, text}` | `connector.py` |
| `whatsapp_message` | `{from, pushName, text}` | `official_backend.py`, `whatsapp_client.py` |
| `slack_message` | `{channel_id, user, text}` | `channel_adapter.py` |
| `discord_message` | `{channel_id, user, text}` | `channel_adapter.py` |

## Session & Execution

| Event | Payload | Source |
|-------|---------|--------|
| `session_updated` | `{session_id, action?}` | `memory_handlers.py` — chat saved, deleted, compacted |
| `execution_complete` | `{execution_id, capability_id, status}` | `api_server.py` — capability execution finished |
| `whatsapp_message_processed` | `{from, pushName, text}` | `whatsapp_reply_worker.py` |

## Settings & Configuration

| Event | Payload | Source |
|-------|---------|--------|
| `settings_updated` | `{keys: [...]}` | `system_handlers.py` — settings saved |
| `config_imported` | `{}` | `system_handlers.py` — full config imported |
| `preferences_updated` | `{keys: [...]}` | `memory_handlers.py` — user prefs changed |

## Workspace

| Event | Payload | Source |
|-------|---------|--------|
| `workspace_changed` | `{action, workspace_id}` | `workspace_handlers.py` |

Actions: `added`, `updated`, `removed`, `default_changed`, `status_changed`

## Memory

| Event | Payload | Source |
|-------|---------|--------|
| `memory_cleared` | `{}` | `memory_handlers.py` — all history deleted |

## Integrations

| Event | Payload | Source |
|-------|---------|--------|
| `integration_changed` | `{action, integration_id?}` | `integration_handlers.py`, `skill_handlers.py` |

Actions: `enabled`, `disabled`, `whatsapp_configured`, `whatsapp_backend_switched`, `telegram_configured`, `telegram_polling_started`, `telegram_polling_stopped`, `slack_configured`, `slack_polling_started`, `slack_polling_stopped`, `discord_configured`, `discord_polling_started`, `discord_polling_stopped`, `skill_installed`, `skill_uninstalled`

## Growth & Optimization

| Event | Payload | Source |
|-------|---------|--------|
| `growth_update` | `{action, gap_id?/capability_id?/optimization_id?}` | `growth_handlers.py` |

Actions: `gap_generated`, `gap_approved`, `proposal_approved`, `optimization_approved`

## MCP

| Event | Payload | Source |
|-------|---------|--------|
| `mcp_changed` | `{action, server_id?/tool_id?}` | `mcp_handlers.py` |

Actions: `server_added`, `server_removed`, `tool_installed`, `tool_uninstalled`

## A2A

| Event | Payload | Source |
|-------|---------|--------|
| `a2a_changed` | `{action, agent_id?}` | `a2a_handlers.py` |

Actions: `agent_added`, `agent_removed`, `task_delegated`

## Browser

| Event | Payload | Source |
|-------|---------|--------|
| `browser_changed` | `{action}` | `browser_handlers.py` |

Actions: `worker_restarted`, `chrome_launched`, `cdp_connected`

## Supervisor

| Event | Payload | Source |
|-------|---------|--------|
| `supervisor_alert` | `{severity, source, message, ...}` | `supervisor_daemon.py`, `error_interceptor.py`, `gap_detector.py`, `security_auditor.py` |
| `supervisor_action` | `{action, result}` | `supervisor_handlers.py` |
| `skill_created` | `{tool_id, auto: bool}` | `skill_creator.py` — new skill hot-loaded |

## Workflows

| Event | Payload | Source |
|-------|---------|--------|
| `notification` | `{channel, message, recipient?}` | `workflow_executor.py` — notification node sends to channel |
| `workflow_completed` | `{workflow_id, status, node_count, duration_ms}` | `workflow_executor.py` — workflow finished successfully |

## Agents

| Event | Payload | Source |
|-------|---------|--------|
| `agent_changed` | `{action, agent_id}` | `agent_handlers.py` |

Actions: `created`, `updated`, `deleted`

## Scheduler

| Event | Payload | Source |
|-------|---------|--------|
| `scheduler_cycle` | `{cycle, ready_tasks?, summary?}` | `proactive_scheduler.py` |

Cycles: `quick` (30min), `deep` (4h)

## Auth

| Event | Payload | Source |
|-------|---------|--------|
| `auth_setup_complete` | `{user_id}` | `auth_handlers.py` — owner account created |

## Errors

| Event | Payload | Source |
|-------|---------|--------|
| `error` | `{source, path?, method?, message}` | `api_server.py`, `channel_adapter.py` |

Sources: `handler`, `api_dispatch`, `{channel}_polling`

## Frontend Usage

```js
import sdk from "./sdk";
import { EVENTS, HISTORY_EVENTS, EVENT_LABELS } from "./sdk/eventTypes";

// Subscribe to specific event
sdk.events.on(EVENTS.EXECUTION_COMPLETE, (e) => {
  console.log("Execution done:", e.data.execution_id);
});

// Subscribe to all events
sdk.events.on("*", (e) => { ... });

// Check connection
sdk.events.isConnected(); // boolean
sdk.events.onConnectionChange((connected) => { ... });
```

## Summary

- **26 event types** across 16 categories
- **60+ emission points** in the backend
- All events broadcast to all connected WebSocket clients
- Frontend SDK provides `sdk.events.on/off` for subscription
