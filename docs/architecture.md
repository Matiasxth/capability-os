# Architecture Overview

CapabilityOS is a plugin-based system where all functionality is provided by 21 plugins managed by a central ServiceContainer. Plugins communicate through typed Protocol contracts and a pub/sub event bus.

---

## High-Level Architecture

```
+---------------------------------------------------------------------+
|                          Client Layer                                |
|  +-------------------+  +-------------------+  +-----------------+  |
|  | React 18 + Vite   |  | CLI (capabilityos)|  | Ext. Channels   |  |
|  | ReactFlow, Monaco |  | chat/serve/status |  | WA/TG/Slack/DC  |  |
|  +--------+----------+  +--------+----------+  +--------+--------+  |
|           |                      |                       |          |
+-----------+----------------------+-----------------------+----------+
            |                      |                       |
            v                      v                       v
+---------------------------------------------------------------------+
|                        Transport Layer                               |
|  +-------------------+  +-------------------+  +-----------------+  |
|  | HTTP / ASGI       |  | WebSocket (WS)    |  | SSE Streaming   |  |
|  | uvicorn + sync fb |  | RFC 6455          |  | Agent steps     |  |
|  +--------+----------+  +--------+----------+  +--------+--------+  |
+-----------+----------------------+-----------------------+----------+
            |                      |                       |
            v                      v                       v
+---------------------------------------------------------------------+
|                         Router Layer                                 |
|  +-----------------------------------------------------------+      |
|  |  Router (180+ endpoints)                                  |      |
|  |  Auth Middleware (JWT validation, role checks)             |      |
|  +-----------------------------------------------------------+      |
|  +-----------------------------------------------------------+      |
|  |  19 Handler Modules                                       |      |
|  |  system | agent | capability | workspace | memory         |      |
|  |  workflow | plugin | scheduler | supervisor | voice        |      |
|  |  browser | integration | growth | mcp | a2a | skill       |      |
|  |  file | auth | scheduler                                  |      |
|  +-----------------------------------------------------------+      |
+---------------------------------------------------------------------+
            |
            v
+---------------------------------------------------------------------+
|                       Plugin Layer                                   |
|  +-----------------------------------------------------------+      |
|  |  ServiceContainer                                         |      |
|  |  - Kahn's topological sort for init order                 |      |
|  |  - Typed service registry (Protocol -> impl)              |      |
|  |  - Hot-reload support                                     |      |
|  +-----------------------------------------------------------+      |
|  +-----------------------------------------------------------+      |
|  |  21 Plugins (see Plugin Dependency Graph below)           |      |
|  +-----------------------------------------------------------+      |
+---------------------------------------------------------------------+
            |
            v
+---------------------------------------------------------------------+
|                       Service Layer                                  |
|  +-----------+  +----------+  +--------+  +----------+  +--------+  |
|  | Agent     |  | Security |  | Memory |  | Workflow |  | Sandbox|  |
|  | Loop      |  | Service  |  | Manager|  | Executor |  | Manager|  |
|  +-----------+  +----------+  +--------+  +----------+  +--------+  |
|  +-----------+  +----------+  +--------+  +----------+  +--------+  |
|  | Tool      |  | Capability| | LLM    |  | Scheduler|  | Health |  |
|  | Runtime   |  | Engine    | | Client |  |          |  | Service|  |
|  +-----------+  +----------+  +--------+  +----------+  +--------+  |
+---------------------------------------------------------------------+
            |
            v
+---------------------------------------------------------------------+
|                       Storage Layer                                  |
|  +-------------+  +-------------+  +-------------+  +------------+  |
|  | settings.json|  | sqlite-vec  |  | MEMORY.md   |  | users.json |  |
|  | (config)     |  | (vectors)   |  | (notes)     |  | (auth)     |  |
|  +-------------+  +-------------+  +-------------+  +------------+  |
|  +-------------+  +-------------+  +-------------+                  |
|  | history.db   |  | workflows/  |  | agents.json |                  |
|  | (sessions)   |  | (graphs)    |  | (defs)      |                  |
|  +-------------+  +-------------+  +-------------+                  |
+---------------------------------------------------------------------+
```

---

## Plugin Dependency Graph

Plugins are initialized in topological order. An arrow means "depends on".

```
core_services
    |
    +----> auth
    |
    +----> memory
    |         |
    |         +----> capabilities
    |         |         |
    |         |         +----> workspace
    |         |         +----> growth
    |         |
    |         +----> agent
    |                   |
    |                   +----> supervisor
    |                   +----> scheduler
    |                   +----> skills
    |
    +----> browser
    +----> voice
    +----> mcp
    +----> a2a
    +----> sequences
    +----> workflows
    +----> sandbox
    +----> channels/telegram
    +----> channels/slack
    +----> channels/discord
    +----> channels/whatsapp
```

The ServiceContainer uses Kahn's algorithm to flatten this DAG into an initialization order. Shutdown happens in reverse order.

---

## Request Flow

### HTTP Request

```
Client
  |
  v
UnifiedHandler.do_GET / do_POST / do_DELETE
  |
  +-- Is API path? (matches API_PREFIXES)
  |     |
  |     v
  |   service.handle(method, path, payload, headers)
  |     |
  |     v
  |   Router.dispatch(method, path)
  |     |
  |     +-- Exact match: O(1) dict lookup
  |     +-- Pattern match: regex with {param} capture
  |     |
  |     v
  |   Auth Middleware (if protected route)
  |     |
  |     +-- Extract JWT from Authorization header
  |     +-- Validate token, check role
  |     +-- Reject with 401/403 if unauthorized
  |     |
  |     v
  |   Handler function (service, payload, **path_params)
  |     |
  |     +-- Reads from ServiceContainer services
  |     +-- May call ToolRuntime, AgentLoop, etc.
  |     +-- Returns APIResponse(status_code, payload)
  |     |
  |     v
  |   JSON response with CORS headers
  |
  +-- Not API path?
        |
        v
      Serve static file from frontend dist/
      (SPA fallback to index.html)
```

### Agent Session

```
POST /agent  {message, session_id?, agent_id?, workspace_id?}
  |
  v
agent_handlers.start_agent()
  |
  v
AgentLoop.run(message, session_id, agent_config, workspace_id)
  |
  +-- Build system prompt (agent config + workspace context + memory)
  |
  +-- LOOP (max_iterations):
  |     |
  |     v
  |   LLMClient.complete(system_prompt, conversation)
  |     |
  |     v
  |   Parse tool calls from LLM response
  |     |
  |     +-- No tool calls? -> Return final response
  |     |
  |     v
  |   SecurityService.classify(tool_id, inputs)
  |     |
  |     +-- Level 1: execute immediately
  |     +-- Level 2: emit "approval_needed" event, wait for /agent/confirm
  |     +-- Level 3: require password
  |     |
  |     v
  |   ToolRuntime.execute(action, params)
  |     |
  |     v
  |   Append tool result to conversation
  |     |
  |     v
  |   EventBus.emit("agent_step", {tool, result, ...})
  |     |
  |     +-- SSE pushes step to frontend in real-time
  |     |
  |     v
  |   Continue loop
  |
  v
Return {session_id, messages, steps}
```

---

## Event Bus Flow

The EventBus is a thread-safe synchronous pub/sub singleton. It connects the backend to the frontend via SSE/WebSocket.

```
Backend (any plugin/handler)
  |
  v
event_bus.emit("event_type", {data})
  |
  v
EventBus broadcasts to all subscribers
  |
  +----> SSE handler (pushes to /executions/{id}/events)
  +----> WebSocket server (pushes to connected clients)
  +----> Logging subscriber
  +----> Any plugin subscriber
```

### Common Event Types

| Event | Source | Data |
|-------|--------|------|
| `agent_step` | Agent Loop | `{tool, result, iteration}` |
| `agent_complete` | Agent Loop | `{session_id, final_response}` |
| `approval_needed` | Security Service | `{tool, inputs, level}` |
| `error` | Any handler | `{source, path, message}` |
| `telegram_message` | Telegram Plugin | `{chat_id, text}` |
| `whatsapp_message` | WhatsApp Plugin | `{contact, text}` |
| `execution_progress` | Capability Engine | `{execution_id, step, total}` |
| `memory_updated` | Memory Plugin | `{type, key}` |
| `workflow_step` | Workflow Executor | `{workflow_id, node_id, status}` |
| `plugin_state_change` | ServiceContainer | `{plugin_id, old_state, new_state}` |

---

## SSE Streaming Flow

Long-running operations (agent sessions, workflow execution) stream progress via Server-Sent Events.

```
Frontend                                   Backend
   |                                          |
   |  POST /agent {message}                   |
   |  <<<  {session_id, status: "running"}    |
   |                                          |
   |  GET /executions/{id}/events             |
   |  <<<  SSE stream opens                   |
   |                                          |
   |  <<<  event: agent_step                  |
   |  <<<  data: {tool: "read_file", ...}     |
   |                                          |
   |  <<<  event: agent_step                  |
   |  <<<  data: {tool: "write_file", ...}    |
   |                                          |
   |  <<<  event: agent_complete              |
   |  <<<  data: {response: "Done!"}          |
   |                                          |
   |  SSE stream closes                       |
```

The frontend's `ChatThread` component subscribes to the SSE stream and renders each step in real-time with the `AgentStepView` component.

---

## Memory Subsystem

Three complementary memory systems work together:

```
+-----------------------------------------------------------+
|                    Memory Subsystem                        |
|                                                           |
|  +-------------------+  +--------------------------+      |
|  | Execution History |  | Semantic Memory          |      |
|  | (SQLite / JSON)   |  | (sqlite-vec vectors)     |      |
|  |                   |  |                          |      |
|  | - Session replay  |  | - Embeddings engine      |      |
|  | - Per-workspace   |  | - Similarity search      |      |
|  | - Duration/stats  |  | - 100x faster than JSON  |      |
|  +-------------------+  +--------------------------+      |
|                                                           |
|  +-------------------+  +--------------------------+      |
|  | Markdown Memory   |  | User Context             |      |
|  | (MEMORY.md)       |  | (preferences.json)       |      |
|  |                   |  |                          |      |
|  | - Sections/facts  |  | - Display names          |      |
|  | - Daily notes     |  | - Per-workspace prefs    |      |
|  | - Auto-compaction |  | - UI preferences         |      |
|  +-------------------+  +--------------------------+      |
+-----------------------------------------------------------+
```

### Memory Flow for Agent Conversations

```
1. User sends message
2. Agent builds context:
   a. markdown_memory.build_context(500 tokens)
   b. semantic_memory.recall_semantic(query, top_k=5)
   c. execution_history.get_recent(5)
3. Context injected into system prompt
4. Agent conversation proceeds
5. After completion:
   a. execution_history.upsert_chat(session_id, messages)
   b. semantic_memory.remember_semantic(summary)
   c. markdown_memory.append_daily(summary)
```

---

## Security Architecture

### Three Levels

```
Level 1 (Free)        Level 2 (Confirm)       Level 3 (Password)
+--------------+      +----------------+       +------------------+
| Read file    |      | Write file     |       | Delete system    |
| List dir     |      | Run command    |       | Modify OS        |
| Send message |      | Create dir     |       | Admin actions    |
| Search       |      | Install plugin |       | User management  |
+--------------+      +----------------+       +------------------+
     |                      |                         |
     v                      v                         v
  Execute                Emit event               Emit event
  immediately            "approval_needed"        "approval_needed"
                              |                    + password check
                              v                         |
                         Frontend shows                 v
                         confirmation dialog       Frontend shows
                              |                    password dialog
                              v                         |
                         POST /agent/confirm            v
                              |                    POST /agent/confirm
                              v                    + password field
                         Execute or deny                |
                                                        v
                                                   Verify + execute
```

### Auth Middleware

Protected routes check the JWT token:

```
Request with Authorization: Bearer <token>
  |
  v
AuthMiddleware.check_auth(headers, required_role)
  |
  +-- No token? -> 401 Unauthorized
  +-- Invalid token? -> 401 Unauthorized
  +-- Wrong role? -> 403 Forbidden
  +-- Valid? -> Continue to handler
```

### Execution Sandbox

```
Tool Execution Request
  |
  v
SecurityService.classify(tool_id)
  |
  +-- Trusted tool? -> Direct execution (no sandbox)
  |
  +-- Untrusted? -> SandboxManager
                      |
                      +-- L2 (Process sandbox)
                      |     subprocess with:
                      |     - timeout (30s default)
                      |     - memory limit
                      |     - restricted PATH
                      |
                      +-- L3 (Docker sandbox)
                            docker run with:
                            - timeout (60s default)
                            - memory cap (512MB)
                            - no network (optional)
                            - read-only filesystem
                            - workspace mounted as volume
```

---

## Workflow Execution

Visual workflows are stored as directed acyclic graphs (DAGs) and executed via topological sort.

```
WorkflowCanvas (ReactFlow)
  |
  v
POST /workflows  (save graph: nodes + edges)
  |
  v
POST /workflows/{id}/run
  |
  v
WorkflowExecutor.run(workflow)
  |
  +-- Topological sort of nodes
  |
  +-- For each node in order:
        |
        +-- Trigger: start conditions
        +-- Tool: ToolRuntime.execute(tool_id, params)
        +-- Agent: AgentLoop.run(prompt)
        +-- Condition: evaluate expression, choose branch
        +-- Loop: repeat sub-graph N times
        +-- Delay: asyncio.sleep / time.sleep
        +-- Webhook: HTTP call to external URL
        +-- End: collect outputs
        |
        v
      EventBus.emit("workflow_step", {node_id, status})
        |
        v
      Next node (with outputs from previous)
```

### Node Types

| Type | Icon | Description |
|------|------|-------------|
| Trigger | Lightning | Workflow start condition |
| Tool | Wrench | Execute a registered tool |
| Agent | Brain | Run an agent conversation |
| Condition | Diamond | Branch based on expression |
| Loop | Arrows | Repeat a subgraph |
| Delay | Clock | Wait for a duration |
| Webhook | Globe | HTTP request to external service |
| End | Flag | Workflow completion |
