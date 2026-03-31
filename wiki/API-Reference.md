# API Reference

Complete reference for all REST endpoints in Capability OS, organized by module. All endpoints return JSON. Unless noted otherwise, every endpoint requires a valid JWT token in the `Authorization: Bearer <token>` header.

---

## Auth

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/auth/status` | Check if owner account exists | No |
| `POST` | `/auth/setup` | Create the owner account (first-time only) | No |
| `POST` | `/auth/login` | Authenticate and receive a JWT token | No |
| `GET` | `/auth/me` | Get the current user's profile | Yes |
| `GET` | `/auth/users` | List all users (admin+) | Yes |
| `POST` | `/auth/users` | Create a new user (admin+) | Yes |
| `PUT` | `/auth/users/{userId}` | Update a user (admin+) | Yes |
| `DELETE` | `/auth/users/{userId}` | Delete a user (admin+) | Yes |

### POST /auth/setup

```json
// Request
{ "username": "admin", "password": "secretpassword" }

// Response
{ "status": "ok", "token": "eyJ...", "user": { "id": "...", "username": "admin", "role": "owner" } }
```

### POST /auth/login

```json
// Request
{ "username": "admin", "password": "secretpassword" }

// Response
{ "status": "ok", "token": "eyJ...", "user": { "id": "...", "username": "admin", "role": "owner" } }
```

---

## System

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/status` | System status overview | Yes |
| `GET` | `/health` | Detailed health check (plugins, LLM, channels, browser) | Yes |
| `GET` | `/logs` | Recent system logs | Yes |
| `GET` | `/settings` | Get current settings (secrets masked) | Yes |
| `POST` | `/settings` | Save settings | Yes |
| `POST` | `/llm/test` | Test LLM connection with current config | Yes |
| `GET` | `/system/export-config` | Export full system configuration | Yes |
| `POST` | `/system/import-config` | Import system configuration | Yes |

### POST /settings

```json
// Request
{
  "settings": {
    "llm_provider": "groq",
    "llm_model": "llama-3.3-70b-versatile",
    "groq_api_key": "gsk_..."
  }
}

// Response
{ "status": "ok", "settings": { ... } }
```

---

## Agent

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/agent` | Run agent (one-shot, returns full response) | Yes |
| `POST` | `/agent/stream` | Run agent with SSE streaming | Yes |
| `POST` | `/agent/confirm` | Confirm or reject a pending L2/L3 action | Yes |
| `GET` | `/agent/{sessionId}` | Get agent session state | Yes |
| `GET` | `/agents` | List custom agent definitions | Yes |
| `POST` | `/agents` | Create a custom agent | Yes |
| `GET` | `/agents/{id}` | Get a specific agent definition | Yes |
| `POST` | `/agents/{id}` | Update an agent definition | Yes |
| `DELETE` | `/agents/{id}` | Delete an agent definition | Yes |
| `POST` | `/agents/design` | AI-assisted agent design from description | Yes |

### POST /agent

```json
// Request
{
  "message": "Create a Python script that sorts a list",
  "session_id": "optional-session-id",
  "history": [],
  "agent_id": "optional-custom-agent-id"
}

// Response
{
  "status": "ok",
  "session_id": "abc123",
  "events": [
    { "type": "agent_thinking", "content": "..." },
    { "type": "tool_call", "tool": "write_file", "args": { "path": "sort.py", "content": "..." } },
    { "type": "agent_response", "content": "I created sort.py with..." }
  ]
}
```

### POST /agent/confirm

```json
// Request
{
  "session_id": "abc123",
  "confirmation_id": "conf-456",
  "approved": true,
  "password": "required-for-L3-only"
}

// Response
{ "status": "ok", "events": [ ... ] }
```

---

## Capabilities

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/capabilities` | List all registered capabilities | Yes |
| `GET` | `/capabilities/{id}` | Get capability details and contract | Yes |
| `GET` | `/capabilities/health` | Capability health summary | Yes |
| `POST` | `/interpret` | Interpret natural language into intent | Yes |
| `POST` | `/plan` | Generate execution plan from intent | Yes |
| `POST` | `/chat` | One-shot chat completion | Yes |
| `POST` | `/chat/stream` | Streaming chat completion (SSE) | Yes |
| `POST` | `/execute` | Execute a capability by ID | Yes |
| `POST` | `/execute/stream` | Execute a capability with streaming events (SSE) | Yes |
| `GET` | `/executions/{id}` | Get execution result | Yes |
| `GET` | `/executions/{id}/events` | Get execution event log | Yes |

### POST /chat

```json
// Request
{
  "message": "What is the capital of France?",
  "user_name": "User",
  "conversation_history": []
}

// Response
{ "response": "The capital of France is Paris.", "model": "llama-3.3-70b-versatile" }
```

### POST /execute

```json
// Request
{
  "capability_id": "file_read",
  "inputs": { "path": "/home/user/notes.txt" }
}

// Response
{
  "execution_id": "exec-789",
  "status": "completed",
  "result": { "content": "..." },
  "duration_ms": 142
}
```

---

## Workspaces

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/workspaces` | List all workspaces | Yes |
| `POST` | `/workspaces` | Create a workspace | Yes |
| `GET` | `/workspaces/{id}` | Get workspace details | Yes |
| `POST` | `/workspaces/{id}` | Update workspace fields | Yes |
| `DELETE` | `/workspaces/{id}` | Remove a workspace | Yes |
| `POST` | `/workspaces/{id}/set-default` | Set workspace as default | Yes |
| `POST` | `/workspaces/{id}/status` | Update workspace status label | Yes |
| `GET` | `/workspaces/{id}/browse` | Browse workspace file tree | Yes |

### POST /workspaces

```json
// Request
{
  "name": "My Project",
  "path": "/home/user/projects/my-project",
  "access": "write",
  "capabilities": "*",
  "color": "#00ff88"
}

// Response
{ "status": "ok", "workspace": { "id": "ws-001", "name": "My Project", ... } }
```

---

## Memory

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/memory/context` | Get current memory context for agent prompt | Yes |
| `GET` | `/memory/history` | Get execution history (optional filters) | Yes |
| `DELETE` | `/memory/history/{executionId}` | Delete a history entry | Yes |
| `POST` | `/memory/history/chat` | Save a chat session to history | Yes |
| `POST` | `/memory/sessions` | Save a session object | Yes |
| `GET` | `/memory/sessions/{executionId}` | Get a saved session | Yes |
| `GET` | `/memory/preferences` | Get user preferences | Yes |
| `POST` | `/memory/preferences` | Set user preferences | Yes |
| `DELETE` | `/memory` | Clear all memory stores | Yes |
| `POST` | `/memory/compact` | Compact old history entries | Yes |
| `GET` | `/metrics` | Get execution metrics and statistics | Yes |
| `GET` | `/memory/daily` | Get daily notes (optional date filter) | Yes |
| `GET` | `/memory/summaries` | Get memory summaries | Yes |
| `GET` | `/memory/agent-context` | Get full agent context (memory + workspace) | Yes |

### Semantic Memory

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/memory/semantic/search?q={query}&top_k={n}` | Semantic search over stored memories | Yes |
| `POST` | `/memory/semantic` | Add a semantic memory entry | Yes |
| `DELETE` | `/memory/semantic/{memId}` | Delete a semantic memory entry | Yes |

### Markdown Memory

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/memory/markdown` | Get MEMORY.md contents | Yes |
| `POST` | `/memory/markdown` | Overwrite MEMORY.md | Yes |
| `POST` | `/memory/markdown/fact` | Add a fact to a section | Yes |
| `DELETE` | `/memory/markdown/fact` | Remove a fact by substring match | Yes |

---

## Workflows

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/workflows` | List all workflows | Yes |
| `POST` | `/workflows` | Create a new workflow | Yes |
| `GET` | `/workflows/{id}` | Get workflow definition (nodes + edges) | Yes |
| `PUT` | `/workflows/{id}` | Update workflow (nodes, edges, metadata) | Yes |
| `DELETE` | `/workflows/{id}` | Delete a workflow | Yes |
| `POST` | `/workflows/{id}/run` | Execute a workflow | Yes |

### PUT /workflows/{id}

```json
// Request
{
  "name": "Deploy Pipeline",
  "description": "Build, test, and deploy",
  "nodes": [
    { "id": "n1", "type": "action", "data": { "capability_id": "shell_exec", "inputs": { "command": "npm test" } } },
    { "id": "n2", "type": "action", "data": { "capability_id": "shell_exec", "inputs": { "command": "npm run build" } } }
  ],
  "edges": [
    { "source": "n1", "target": "n2" }
  ]
}
```

---

## Plugins

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/plugins` | List all plugins with status, version, dependencies | Yes |
| `GET` | `/plugins/{id}` | Get plugin details | Yes |
| `POST` | `/plugins/{id}/reload` | Hot-reload a plugin | Yes |
| `POST` | `/plugins/install` | Install a plugin from a path | Yes |

### GET /plugins response

```json
{
  "plugins": [
    {
      "id": "capos.core.auth",
      "name": "Authentication",
      "version": "1.0.0",
      "state": "RUNNING",
      "dependencies": ["capos.core.settings"],
      "permissions": ["auth:manage", "auth:read"]
    }
  ]
}
```

---

## Scheduler

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/scheduler/status` | Scheduler daemon status and cycle info | Yes |
| `GET` | `/scheduler/log` | Scheduler execution log | Yes |
| `GET` | `/scheduler/tasks` | List scheduled tasks | Yes |
| `POST` | `/scheduler/tasks` | Create a scheduled task | Yes |
| `POST` | `/scheduler/tasks/{taskId}` | Update a task | Yes |
| `DELETE` | `/scheduler/tasks/{taskId}` | Delete a task | Yes |
| `POST` | `/scheduler/tasks/{taskId}/run` | Run a task immediately | Yes |

### POST /scheduler/tasks

```json
// Request
{
  "name": "Daily Report",
  "capability_id": "generate_report",
  "inputs": { "format": "markdown" },
  "schedule": "0 9 * * *",
  "enabled": true,
  "channel": "telegram"
}

// Response
{ "status": "ok", "task": { "id": "task-001", ... } }
```

---

## Supervisor

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/supervisor/status` | Supervisor daemon status | Yes |
| `GET` | `/supervisor/log` | Supervisor action log | Yes |
| `POST` | `/supervisor/claude` | Invoke Claude bridge with a prompt | Yes |
| `POST` | `/supervisor/health-check` | Trigger a system health check | Yes |
| `POST` | `/supervisor/approve` | Approve a supervisor preview | Yes |
| `POST` | `/supervisor/discard` | Discard a supervisor preview | Yes |

---

## Files & IDE

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/files/tree` | Get file tree for current workspace | Yes |
| `GET` | `/files/tree/{wsId}` | Get file tree for a specific workspace | Yes |
| `GET` | `/files/read?path={path}&ws={wsId}` | Read file contents | Yes |
| `POST` | `/files/write` | Write content to a file | Yes |
| `POST` | `/files/create` | Create a new file | Yes |
| `DELETE` | `/files/delete?path={path}&ws={wsId}` | Delete a file | Yes |
| `POST` | `/files/terminal` | Execute a terminal command (allowlisted) | Yes |
| `GET` | `/files/analyze/{wsId}` | Analyze workspace health (issues, stats) | Yes |
| `POST` | `/files/auto-clean/{wsId}` | Auto-clean workspace (dry_run supported) | Yes |
| `POST` | `/files/generate-readme/{wsId}` | Generate README for workspace | Yes |

### POST /files/terminal

Only 21 allowlisted commands are permitted (e.g., `ls`, `cat`, `grep`, `git`, `npm`, `python`). Shell metacharacters are blocked.

```json
// Request
{ "command": "git status", "ws": "ws-001" }

// Response
{ "output": "On branch main\nnothing to commit", "exit_code": 0 }
```

---

## Channels: Telegram

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/integrations/telegram/status` | Telegram bot connection status | Yes |
| `POST` | `/integrations/telegram/configure` | Set bot token and chat config | Yes |
| `POST` | `/integrations/telegram/test` | Send a test message | Yes |
| `POST` | `/integrations/telegram/polling/start` | Start polling for messages | Yes |
| `POST` | `/integrations/telegram/polling/stop` | Stop polling | Yes |
| `GET` | `/integrations/telegram/polling/status` | Polling worker status | Yes |

### POST /integrations/telegram/configure

```json
{
  "bot_token": "123456:ABC-DEF...",
  "default_chat_id": "987654321",
  "allowed_user_ids": [123456789]
}
```

---

## Channels: WhatsApp

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/integrations/whatsapp/session-status` | WhatsApp session status | Yes |
| `POST` | `/integrations/whatsapp/start` | Start WhatsApp session | Yes |
| `POST` | `/integrations/whatsapp/stop` | Stop WhatsApp session | Yes |
| `POST` | `/integrations/whatsapp/close-session` | Close and clean session | Yes |
| `GET` | `/integrations/whatsapp/qr` | Get QR code for pairing | Yes |
| `POST` | `/integrations/whatsapp/configure` | Update WhatsApp config | Yes |
| `POST` | `/integrations/whatsapp/switch-backend` | Switch backend (baileys/puppeteer/official) | Yes |
| `GET` | `/integrations/whatsapp/backends` | List available backends | Yes |

---

## Channels: Slack

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/integrations/slack/status` | Slack integration status | Yes |
| `POST` | `/integrations/slack/configure` | Set Slack bot token | Yes |
| `POST` | `/integrations/slack/test` | Send a test message | Yes |
| `POST` | `/integrations/slack/polling/start` | Start Slack event polling | Yes |
| `POST` | `/integrations/slack/polling/stop` | Stop polling | Yes |
| `GET` | `/integrations/slack/polling/status` | Polling status | Yes |

---

## Channels: Discord

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/integrations/discord/status` | Discord bot status | Yes |
| `POST` | `/integrations/discord/configure` | Set Discord bot token | Yes |
| `POST` | `/integrations/discord/test` | Send a test message | Yes |
| `POST` | `/integrations/discord/polling/start` | Start Discord gateway | Yes |
| `POST` | `/integrations/discord/polling/stop` | Stop gateway | Yes |
| `GET` | `/integrations/discord/polling/status` | Gateway status | Yes |

---

## Channels: Generic Integrations

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/integrations` | List all integrations with status | Yes |
| `GET` | `/integrations/{id}` | Get integration details | Yes |
| `POST` | `/integrations/{id}/validate` | Validate integration configuration | Yes |
| `POST` | `/integrations/{id}/enable` | Enable an integration | Yes |
| `POST` | `/integrations/{id}/disable` | Disable an integration | Yes |

---

## MCP (Model Context Protocol)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/mcp/servers` | List registered MCP servers | Yes |
| `POST` | `/mcp/servers` | Add an MCP server | Yes |
| `DELETE` | `/mcp/servers/{id}` | Remove an MCP server | Yes |
| `POST` | `/mcp/servers/{id}/discover` | Discover tools from an MCP server | Yes |
| `GET` | `/mcp/tools` | List all MCP tools | Yes |
| `POST` | `/mcp/tools/{id}/install` | Install an MCP tool | Yes |
| `DELETE` | `/mcp/tools/{id}/uninstall` | Uninstall an MCP tool | Yes |

### POST /mcp/servers

```json
// Request
{
  "server": {
    "name": "filesystem",
    "url": "http://localhost:3000/mcp",
    "transport": "stdio"
  }
}
```

---

## A2A (Agent-to-Agent)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/.well-known/agent.json` | This agent's A2A card (public) | No |
| `GET` | `/a2a/agents` | List registered remote agents | Yes |
| `POST` | `/a2a/agents` | Register a remote agent | Yes |
| `DELETE` | `/a2a/agents/{id}` | Remove a remote agent | Yes |
| `POST` | `/a2a/agents/{agentId}/delegate` | Delegate a task to a remote agent | Yes |

### POST /a2a/agents/{agentId}/delegate

```json
// Request
{ "skill_id": "code_review", "message": "Review my PR #42" }

// Response
{ "status": "ok", "task_id": "a2a-task-001", "result": "..." }
```

---

## Skills

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/skills` | List installed skills | Yes |
| `GET` | `/skills/{id}` | Get skill details | Yes |
| `POST` | `/skills/install` | Install a skill from source | Yes |
| `DELETE` | `/skills/{id}` | Uninstall a skill | Yes |
| `GET` | `/skills/auto-generated` | List supervisor-generated skill domains | Yes |

---

## Growth (Self-Improvement)

### Gaps

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/gaps/pending` | List pending capability gaps | Yes |
| `POST` | `/gaps/{id}/analyze` | Analyze a gap in detail | Yes |
| `POST` | `/gaps/{id}/generate` | Generate a capability to fill a gap | Yes |
| `POST` | `/gaps/{id}/approve` | Approve a generated capability | Yes |
| `POST` | `/gaps/{id}/reject` | Reject a generated capability | Yes |

### Optimizations

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/optimizations/pending` | List pending optimization suggestions | Yes |
| `POST` | `/optimizations/{id}/approve` | Approve an optimization | Yes |
| `POST` | `/optimizations/{id}/reject` | Reject an optimization | Yes |

### Proposals

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/proposals` | List auto-generated capability proposals | Yes |
| `POST` | `/proposals/{id}/regenerate` | Regenerate a proposal | Yes |
| `POST` | `/proposals/{capabilityId}/approve` | Approve a proposal | Yes |
| `POST` | `/proposals/{capabilityId}/reject` | Reject a proposal | Yes |

---

## Voice

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/voice/stt` | Speech-to-text (audio upload) | Yes |
| `POST` | `/voice/tts` | Text-to-speech (returns audio) | Yes |

---

## Browser

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/browser/cdp-status` | Chrome DevTools Protocol status | Yes |
| `POST` | `/browser/launch-chrome` | Launch a Chrome instance | Yes |
| `POST` | `/browser/connect-cdp` | Connect to running Chrome via CDP | Yes |
| `POST` | `/browser/restart` | Restart the browser worker | Yes |
| `POST` | `/browser/open-whatsapp` | Open WhatsApp Web in the browser | Yes |

---

## Streaming Endpoints (SSE)

Three endpoints return Server-Sent Events instead of standard JSON responses. They accept POST with a JSON body and return a stream of `data:` frames.

### POST /agent/stream

Streams the full agent loop execution. Each frame is a JSON object with a `type` field.

**Event types:**

| Type | Description | Key fields |
|------|-------------|------------|
| `agent_start` | Agent loop started | `session_id` |
| `agent_thinking` | Agent is reasoning | `content` |
| `tool_call` | Agent wants to call a tool | `tool`, `args` |
| `tool_result` | Tool execution result | `tool`, `result`, `duration_ms` |
| `awaiting_confirmation` | L2/L3 action needs approval | `confirmation_id`, `tool`, `level` |
| `agent_response` | Final agent response | `content` |

**SSE wire format:**

```
data: {"type": "agent_start", "session_id": "abc123"}\n\n
data: {"type": "agent_thinking", "content": "Let me analyze..."}\n\n
data: {"type": "tool_call", "tool": "read_file", "args": {"path": "main.py"}}\n\n
data: {"type": "tool_result", "tool": "read_file", "result": "...", "duration_ms": 45}\n\n
data: {"type": "agent_response", "content": "The file contains..."}\n\n
data: {"done": true}\n\n
```

### POST /chat/stream

Streams text chunks from a chat completion. Each frame contains a `chunk` field with a text fragment.

```
data: {"chunk": "The "}\n\n
data: {"chunk": "capital "}\n\n
data: {"chunk": "of France is Paris."}\n\n
data: {"done": true}\n\n
```

### POST /execute/stream

Streams capability execution events. Same format as agent stream but scoped to a single capability.

```
data: {"type": "step_start", "step": "read_file", "index": 0}\n\n
data: {"type": "step_complete", "step": "read_file", "result": "...", "duration_ms": 34}\n\n
data: {"type": "execution_complete", "result": { ... }}\n\n
data: {"done": true}\n\n
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "error_code": "not_found",
  "error_message": "Workspace ws-999 not found."
}
```

Common HTTP status codes:

| Code | Meaning |
|------|---------|
| `400` | Bad request (missing/invalid parameters) |
| `401` | Unauthorized (missing or expired JWT) |
| `403` | Forbidden (insufficient role) |
| `404` | Resource not found |
| `409` | Conflict (duplicate resource) |
| `500` | Internal server error |
| `503` | Service unavailable (plugin not loaded) |
