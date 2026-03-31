# Architecture

This document describes the internal architecture of Capability OS -- how requests flow from the user to the AI agent, how plugins are loaded and wired together, and how data moves through the system.

---

## System Overview

```
+-------------------------------------------------------------------+
|                          Frontend                                  |
|  React 18 + Vite  |  ReactFlow  |  Monaco Editor  |  SDK layer    |
+-------------------------------------------------------------------+
         |  HTTP REST           |  SSE streams          |  WebSocket
         v                     v                       v
+-------------------------------------------------------------------+
|                       ASGI Server (uvicorn)                        |
|              Port 8000 (HTTP) + Port 8001 (WS)                    |
+-------------------------------------------------------------------+
         |
         v
+-------------------------------------------------------------------+
|  Router   -->   Auth Middleware (JWT)   -->   Handler (19 modules) |
+-------------------------------------------------------------------+
         |
         v
+-------------------------------------------------------------------+
|                     ServiceContainer                               |
|  Kahn's topological sort  |  Plugin lifecycle  |  DI registry     |
+-------------------------------------------------------------------+
         |
    +----+----+-----+-----+-----+-----+-----+-----+-----+
    |    |    |     |     |     |     |     |     |     |
    v    v    v     v     v     v     v     v     v     v
  Core  Auth Memory Agent Caps  Work  Sched Supvr Chanl ...
  Svc   Plug Plug   Plug  Plug  flow  Plug  Plug  Plug
                                Plug
+-------------------------------------------------------------------+
|  Tool Runtime  |  Capability Engine  |  LLM Client (multi-prov)   |
+-------------------------------------------------------------------+
         |                    |
         v                    v
+-------------------------------------------------------------------+
|  SQLite  |  sqlite-vec  |  MEMORY.md  |  settings.json  | users  |
+-------------------------------------------------------------------+
```

---

## Plugin Dependency Graph

The 21 plugins form a directed acyclic graph (DAG). The ServiceContainer uses **Kahn's topological sort** to compute the initialization order.

```
                    core_services
                    /    |     \
                  auth  memory  capabilities
                  /       |         \
               agent    workspace   skills
              / | \       |          |
         browser voice  workflows   mcp
            |              |          |
          sandbox       scheduler   a2a
            |              |
        supervisor      sequences
                           |
                        growth
                           |
        +--------+---------+--------+--------+
        |        |         |        |        |
     telegram  slack    discord  whatsapp  integrations
```

**Rule:** A plugin may only depend on plugins above it in the graph. Cross-plugin communication uses typed Protocol contracts from `system/sdk/contracts.py` -- never direct imports.

---

## Request Flow

Every HTTP request follows the same path:

```
1. Client sends HTTP request
       |
2. ASGI Server (asgi_server.py) receives the raw ASGI scope
       |
3. Router (router.py) performs O(1) dict lookup on method+path
   Falls back to regex pattern matching for parameterized routes
       |
4. Auth Middleware checks JWT token from Authorization header
   - No token: 401 Unauthorized (except public routes)
   - Expired: 401 Unauthorized
   - Invalid role: 403 Forbidden
       |
5. Handler function executes business logic
   - Calls ServiceContainer to get plugin services
   - Orchestrates one or more operations
       |
6. Response returned as JSON with appropriate HTTP status
       |
7. (Optional) EventBus emits event for real-time UI updates
   - Event broadcast via WebSocket to all connected clients
```

### Streaming Requests

Three endpoints support Server-Sent Events (SSE) for real-time streaming:

```
POST /agent/stream    -- Agent loop events (thinking, tool calls, responses)
POST /chat/stream     -- Chat completion chunks
POST /execute/stream  -- Capability execution events
```

SSE format:
```
data: {"type": "agent_thinking", "content": "Analyzing your request..."}\n\n
data: {"type": "tool_call", "tool": "read_file", "args": {"path": "..."}}\n\n
data: {"type": "agent_response", "content": "Here is the result..."}\n\n
data: {"done": true}\n\n
```

---

## Plugin Lifecycle

Every plugin goes through a well-defined state machine:

```
REGISTERED --> INITIALIZING --> INITIALIZED --> STARTING --> RUNNING --> STOPPING --> STOPPED
                                                                           |
                                                                        FAILED
```

### Lifecycle stages

| Stage | What happens |
|-------|-------------|
| **REGISTERED** | Plugin factory is registered with the container |
| **INITIALIZING** | `initialize(ctx)` is called with a `PluginContext` |
| **INITIALIZED** | Plugin has resolved its dependencies and published its services |
| **STARTING** | `start()` is called to activate background workers |
| **RUNNING** | Plugin is fully operational |
| **STOPPING** | `stop()` is called during shutdown |
| **STOPPED** | Plugin has released all resources |
| **FAILED** | An error occurred during any transition |

### Discovery and loading

1. `api_server.py` imports each plugin's `create_plugin()` factory.
2. Factories are registered with the `ServiceContainer`.
3. `container.initialize_all()` builds the dependency graph via Kahn's topological sort and calls `initialize(ctx)` in dependency order.
4. `container.start_all()` calls `start()` on each plugin.

### Hot reload

The `PluginLoader` supports hot-reloading a plugin without restarting the server:

1. `get_state()` saves the plugin's in-memory state.
2. `stop()` is called.
3. The plugin module is re-imported.
4. `initialize(ctx)` and `start()` are called on the new instance.
5. `restore_state(state)` restores the saved state.

---

## ServiceContainer Design

The `ServiceContainer` (`system/container/service_container.py`, 218 lines) is the heart of the dependency injection system.

### Key concepts

| Concept | Description |
|---------|-------------|
| **Plugin registration** | `register(factory)` stores a factory function keyed by `plugin_id` |
| **Dependency resolution** | Kahn's topological sort orders plugins so dependencies initialize first |
| **Service registry** | Plugins publish services keyed by Protocol type via `ctx.publish_service(protocol, impl)` |
| **Service lookup** | Consumers call `ctx.get_service(protocol)` to get the concrete implementation |
| **Policy enforcement** | External (non-builtin) plugins are checked against the `PolicyEngine` before accessing services |
| **Health checks** | `check_plugin_health()` and `check_all_health()` query each plugin's `health_check()` method |

### PluginContext

Each plugin receives a `PluginContext` during initialization. It provides:

```python
ctx.get_service(ProtocolType)      # Get a dependency by Protocol
ctx.get_optional(ProtocolType)     # Get or return None
ctx.publish_service(Protocol, impl) # Publish own service
ctx.plugin_settings(plugin_id)     # Read settings for this plugin
ctx.event_bus                      # Access the EventBus
```

---

## Frontend Architecture

The frontend follows an **SDK-first** pattern. No component makes raw `fetch()` calls or parses SSE manually -- everything goes through the SDK layer.

```
+-------------------------------------------------------------------+
|                       React Components                             |
|  Workspace | ControlCenter | WorkflowEditor | Login | Onboarding  |
+-------------------------------------------------------------------+
         |
         v
+-------------------------------------------------------------------+
|                        Frontend SDK                                |
|  client.js  |  events.js  |  session.js  |  notifications.js      |
|  domains/: auth, agents, capabilities, integrations, memory,       |
|           system, workspaces, mcp, a2a, workflows, skills, growth  |
+-------------------------------------------------------------------+
         |                    |                       |
    HTTP (fetch)         SSE (streamSSE)         WebSocket
         |                    |                       |
         v                    v                       v
+-------------------------------------------------------------------+
|                     Backend API (port 8000 / 8001)                 |
+-------------------------------------------------------------------+
```

### Key architectural rules

1. **No raw `fetch()`** -- all HTTP goes through `sdk/client.js`.
2. **No direct `localStorage`** -- token and session management goes through `sdk/session.js`.
3. **No SSE parsing in components** -- streaming is handled by `client.js:streamSSE()`.
4. **No hardcoded URLs** -- base URLs are derived from `VITE_API_BASE_URL` env var.
5. **Event-driven updates** -- `sdk/events.js` provides a pub/sub bus over WebSocket; components subscribe to specific event types.

### ControlCenter sections

The Control Center uses a section-based architecture. Each section is a standalone component in `components/control-center/sections/`:

```
sections/
  SystemSection.jsx         -- health, export/import config
  WorkspacesSection.jsx     -- workspace CRUD
  LLMSection.jsx            -- LLM provider configuration
  MetricsSection.jsx        -- execution metrics
  OptimizeSection.jsx       -- gap detection, optimization
  AutoGrowthSection.jsx     -- capability proposals
  MCPSection.jsx            -- MCP server management
  A2ASection.jsx            -- agent-to-agent
  MemorySection.jsx         -- semantic search, markdown, compact
  IntegrationsSection.jsx   -- channels (Telegram, WhatsApp, Slack, Discord)
  BrowserSection.jsx        -- Chrome/CDP management
  SkillsSection.jsx         -- skill packages
  SupervisorSection.jsx     -- supervisor daemon
  SchedulerSection.jsx      -- scheduled tasks
  AgentsSection.jsx         -- custom agent management
  ProjectStatesSection.jsx  -- workspace status labels
```

Sections are registered in `sectionRegistry.js` with searchable keywords for the command palette.

---

## Data Flow Patterns

### HTTP (request-response)

Standard REST calls for CRUD operations and one-shot actions. The SDK's `client.js` handles auth header injection, 401 auto-logout, and JSON parsing.

### SSE (streaming)

Used for long-running operations where the client needs incremental progress:

- **Agent streaming** (`/agent/stream`) -- yields `agent_thinking`, `tool_call`, `tool_result`, `agent_response` events.
- **Chat streaming** (`/chat/stream`) -- yields text chunks for progressive rendering.
- **Execution streaming** (`/execute/stream`) -- yields step-by-step execution events.

The SDK's `streamSSE()` is an async generator that handles the SSE protocol, auth, and error detection.

### WebSocket (push)

A single persistent WebSocket connection (port 8001) carries all server-pushed events. The backend's `EventBus` emits events; the `ws_server.py` broadcasts them to all connected clients.

The frontend's `sdk/events.js` provides:
- `on(type, fn)` -- subscribe to a specific event type
- `on("*", fn)` -- wildcard subscription for all events
- `off(type, fn)` -- unsubscribe
- `onConnectionChange(fn)` -- track connection status
- Automatic reconnection with exponential backoff (up to 30 seconds)

---

## Security Layers

### Authentication

- **JWT tokens** with 24-hour expiry.
- **4 roles:** `owner`, `admin`, `user`, `viewer` (hierarchical).
- Auth middleware validates every request (except public routes like `/auth/status`, `/auth/setup`, `/auth/login`).

### Progressive Security (3 levels)

| Level | Name | Behavior |
|-------|------|----------|
| **L1** | Free | Tool executes immediately -- no confirmation needed |
| **L2** | Confirm | User sees a confirmation dialog before execution |
| **L3** | Password | User must enter their password to authorize |

The `SecurityService` classifies each tool call based on pattern-based rules (e.g., file deletion = L2, shell commands = L3).

### Execution Sandboxes

| Sandbox | Isolation | Use case |
|---------|-----------|----------|
| **ProcessSandbox** | Separate subprocess with `shell=False` | L2 operations |
| **DockerSandbox** | Docker container with `no-new-privileges`, no host networking | L3 operations |

### Security hardening (applied)

- Command injection eliminated: `shell=True` replaced with `shlex.split()` + `shell=False`
- Path traversal prevention: `_validate_path()` with `relative_to()` + symlink protection
- Docker images pinned: `node:18.20-slim`, `python:3.12.7-slim`
- CORS configurable via `CORS_ORIGIN` environment variable
- File terminal restricted to 21 safe commands (allowlist)
- Prompt injection mitigated: agent name/description truncated in system prompts

---

## Memory Architecture

CapOS uses three complementary memory stores:

### 1. Execution History (SQLite)

`system/core/memory/execution_history.py` -- stores every execution session with timestamps, inputs, outputs, and duration. Used for the history feed in the Workspace and for metrics.

### 2. Semantic Vectors (sqlite-vec)

`system/core/memory/sqlite_vector_store.py` + `semantic_memory.py` -- stores text embeddings for semantic search. When a user asks "what did I do last week about the API?", semantic memory finds relevant past interactions.

The embeddings engine generates vectors via the configured LLM provider. The vector store performs cosine similarity search (currently O(n); ANN indexing planned for scale).

### 3. Markdown Memory (MEMORY.md)

`system/core/memory/markdown_memory.py` -- a persistent, human-readable markdown file that stores:
- **Facts**: key-value knowledge about the user and system
- **Daily notes**: auto-generated summaries of each day's activity
- **Context**: used to build the agent's system prompt

The compactor (`compactor.py`) automatically summarizes and prunes old entries when the context window approaches the token limit.

---

## Key Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `system/core/ui_bridge/api_server.py` | ~2,084 | Central entry point, plugin registration, route building |
| `system/container/service_container.py` | 218 | DI container with topological sort |
| `system/core/ui_bridge/router.py` | 81 | O(1) dict + regex route matching |
| `system/core/ui_bridge/event_bus.py` | 69 | Thread-safe singleton pub/sub |
| `system/core/ui_bridge/asgi_server.py` | 382 | ASGI application for uvicorn |
| `system/core/ui_bridge/ws_server.py` | 369 | WebSocket server |
| `system/core/agent/agent_loop.py` | 457 | Generator-based agent loop |
| `system/core/interpretation/llm_client.py` | 266 | Multi-provider LLM client |
| `system/core/security/security_service.py` | 165 | Progressive security classifier |
| `system/sdk/contracts.py` | ~200 | 20+ typed Protocol contracts |
| `system/sdk/models.py` | ~150 | TypedDict models for SDK v2 |
| `system/sdk/policy.py` | ~180 | PolicyEngine with priority rules |
