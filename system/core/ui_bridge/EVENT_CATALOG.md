# Event Catalog

All events emitted via `event_bus.emit()` and broadcast over WebSocket (port 8001).

## Event Envelope

```json
{
  "type": "<event_type>",
  "timestamp": "2026-03-28T12:00:00Z",
  "data": { ... }
}
```

## Events

### telegram_message
- **Emitter:** `telegram_bot_connector/connector.py` (polling worker, line ~427)
- **Data:** `{ chat_id, user, text }`
- **Consumers:** Workspace (history refresh)

### whatsapp_message
- **Emitter:** `whatsapp_worker/whatsapp_client.py` (_read_loop, incoming_message)
- **Data:** `{ from, pushName, text, messageId }`
- **Consumers:** Workspace (history refresh)

### execution_complete
- **Emitter:** `api_server.py` (_execute_capability)
- **Data:** `{ execution_id, capability_id, status }`
- **Consumers:** Workspace (history refresh)

### session_updated
- **Emitter:** `handlers/memory_handlers.py` (save_chat, save_session, delete_history)
- **Data:** `{ session_id, action? }`
- **Consumers:** Workspace (history refresh)

### settings_updated
- **Emitter:** `handlers/system_handlers.py` (save_settings)
- **Data:** `{ keys }`
- **Consumers:** Workspace (toast), ControlCenter (refresh + toast)

### config_imported
- **Emitter:** `handlers/system_handlers.py` (import_config)
- **Data:** `{}`
- **Consumers:** Workspace (toast), ControlCenter (refresh)

### workspace_changed
- **Emitter:** `handlers/workspace_handlers.py` (add, update, delete, set_default)
- **Data:** `{ action, workspace_id }`
- **Actions:** `added`, `updated`, `removed`, `default_changed`
- **Consumers:** Workspace (toast), ControlCenter (refresh workspaces)

### growth_update
- **Emitter:** `handlers/growth_handlers.py` (generate_gap, approve_gap, approve_proposal, approve_optimization)
- **Data:** `{ action, gap_id?, capability_id?, optimization_id? }`
- **Actions:** `gap_generated`, `gap_approved`, `proposal_approved`, `optimization_approved`
- **Consumers:** Workspace (toast), ControlCenter (refresh self-improvement/auto-growth)

### integration_changed
- **Emitter:** `handlers/integration_handlers.py` (enable, disable, telegram_configure, polling start/stop)
- **Data:** `{ action, integration_id? }`
- **Actions:** `enabled`, `disabled`, `telegram_configured`, `telegram_polling_started`, `telegram_polling_stopped`
- **Consumers:** Workspace (toast), ControlCenter (refresh integrations)

### mcp_changed
- **Emitter:** `handlers/mcp_handlers.py` (add_server, remove_server, install_tool, uninstall_tool)
- **Data:** `{ action, server_id?, tool_id? }`
- **Actions:** `server_added`, `server_removed`, `tool_installed`, `tool_uninstalled`
- **Consumers:** Workspace (toast), ControlCenter (refresh MCP)

### a2a_changed
- **Emitter:** `handlers/a2a_handlers.py` (add_agent, remove_agent, delegate_task)
- **Data:** `{ action, agent_id? }`
- **Actions:** `agent_added`, `agent_removed`, `task_delegated`
- **Consumers:** Workspace (toast), ControlCenter (refresh A2A)

### browser_changed
- **Emitter:** `handlers/browser_handlers.py` (restart_worker, launch_chrome, connect_cdp)
- **Data:** `{ action }`
- **Actions:** `worker_restarted`, `chrome_launched`, `cdp_connected`
- **Consumers:** Workspace (toast), ControlCenter (refresh browser)

### preferences_updated
- **Emitter:** `handlers/memory_handlers.py` (set_preferences)
- **Data:** `{ keys }`
- **Consumers:** Workspace (toast), ControlCenter (refresh memory)

### memory_cleared
- **Emitter:** `handlers/memory_handlers.py` (clear_all)
- **Data:** `{}`
- **Consumers:** Workspace (history refresh), ControlCenter (refresh memory)

### error
- **Emitter:** `api_server.py` (catch-all in handle + _dispatch)
- **Data:** `{ source, path, message, method? }`
- **Sources:** `handler`, `api_dispatch`
- **Consumers:** Workspace (error toast), ControlCenter (error toast), App (activity feed)
