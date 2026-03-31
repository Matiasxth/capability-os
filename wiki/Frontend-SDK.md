# Frontend SDK

The Frontend SDK is the single gateway between React components and the CapOS backend. Every HTTP call, SSE stream, WebSocket event, token operation, and notification goes through the SDK -- no exceptions.

---

## Why SDK-First

Before the SDK existed, the frontend had three overlapping problems:

1. **3 duplicated HTTP wrappers** -- `api.js` had 70+ functions, several components had inline `fetch()` calls, and streaming endpoints each had their own SSE parser. A single auth bug had to be fixed in multiple places.

2. **Unauthenticated streaming** -- The `/agent/stream`, `/chat/stream`, and `/execute/stream` endpoints were called without JWT tokens because each SSE consumer had its own fetch logic and some forgot to add the auth header.

3. **Fragmented state** -- Token management was spread across `AuthContext`, `localStorage` calls inside components, and hardcoded keys. Chat history was lost on page refresh because no one owned persistence.

The SDK solved all three by providing:
- **One HTTP client** (`client.js`) with centralized auth injection
- **One SSE parser** (`streamSSE`) that handles auth, errors, and framing
- **One event bus** (`events.js`) over a single WebSocket connection
- **One session manager** (`session.js`) for tokens and chat persistence
- **12 domain modules** that mirror the backend API structure

---

## Installation

The SDK ships as part of the frontend source. No npm package to install.

```js
import sdk from "../sdk";

// Use any domain
const caps = await sdk.capabilities.list();
const users = await sdk.auth.listUsers();

// Stream agent events
for await (const event of sdk.agents.stream("Build me a CLI tool")) {
  console.log(event.type, event.content);
}

// Subscribe to real-time events
sdk.events.on("execution_complete", (e) => {
  console.log("Execution finished:", e.data);
});
```

---

## SDK Structure

```
src/sdk/
  index.js              -- SDK entry point, assembles all domains
  client.js             -- Core HTTP + SSE client (fetch, streamSSE)
  events.js             -- WebSocket event bus (on/off/wildcard)
  session.js            -- Token + chat session persistence
  notifications.js      -- Push notifications + local fallback
  eventTypes.js         -- Canonical event type constants
  domains/
    auth.js             -- Authentication (login, setup, user CRUD)
    agents.js           -- Agent execution, streaming, custom agents
    capabilities.js     -- Capability CRUD, chat, execute, streaming
    integrations.js     -- Channel management (Telegram, WhatsApp, Slack, Discord + new)
    memory.js           -- History, semantic, markdown, preferences
    system.js           -- Status, settings, LLM, browser, plugins, supervisor, scheduler, files
    workspaces.js       -- Workspace CRUD, file analysis, auto-clean
    mcp.js              -- MCP servers and tools
    a2a.js              -- Agent-to-Agent protocol
    workflows.js        -- Workflow CRUD and execution
    skills.js           -- Skill install/uninstall/list
    growth.js           -- Gaps, optimizations, proposals
  __tests__/
    client.test.js      -- HTTP client tests
    events.test.js      -- Event bus tests
    session.test.js     -- Session management tests
```

---

## Core Modules

### client.js -- HTTP + SSE

All backend communication goes through two functions:

#### `request(method, path, body, options)`

Every non-streaming HTTP call. Handles:
- JWT injection from `session.getToken()`
- Auto-logout on 401 (clears token, redirects to `/login`)
- JSON parsing and error extraction

```js
import { get, post, put, del } from "../sdk/client.js";

const data = await get("/capabilities");
const result = await post("/execute", { capability_id: "file_read", inputs: { path: "readme.md" } });
await put("/workflows/wf-001", { name: "Updated Name" });
await del("/workspaces/ws-003");
```

#### `streamSSE(path, body)`

Async generator that sends an authenticated POST and yields parsed SSE frames:

```js
import { streamSSE } from "../sdk/client.js";

for await (const frame of streamSSE("/agent/stream", { message: "Hello" })) {
  // frame = { type: "agent_thinking", content: "..." }
  if (frame.error) throw new Error(frame.error);
  console.log(frame);
}
// Generator returns when it receives { done: true }
```

Features:
- Auth header injection (fixes the unauthenticated streaming bug)
- 401 detection with auto-logout
- Buffer-based SSE parsing (handles partial frames)
- Error frame detection (`{ error: "..." }`)
- Clean termination on `{ done: true }`

---

### events.js -- WebSocket Event Bus

A single WebSocket connection to port `API_PORT + 1` that provides pub/sub:

```js
import sdk from "../sdk";

// Subscribe to a specific event
sdk.events.on("execution_complete", (event) => {
  console.log(event.type, event.data);
});

// Wildcard -- receive ALL events
sdk.events.on("*", (event) => {
  console.log("Any event:", event.type);
});

// Unsubscribe
sdk.events.off("execution_complete", myHandler);

// Connection tracking
console.log(sdk.events.isConnected()); // true/false
const unsub = sdk.events.onConnectionChange((connected) => {
  console.log("WS connected:", connected);
});
unsub(); // cleanup

// Teardown
sdk.events.destroy();
```

**WebSocket URL resolution** (in priority order):
1. `VITE_WS_URL` env var (explicit)
2. Derived from `VITE_API_BASE_URL` (protocol + hostname, port + 1)
3. Derived from `window.location` (protocol + hostname, port + 1)

**Reconnection:** Automatic with exponential backoff (1s, 2s, 4s, ... up to 30s max).

---

### session.js -- Token and Chat Persistence

Single source of truth for auth tokens and chat state:

```js
import * as session from "../sdk/session.js";

// Token lifecycle (localStorage)
session.setToken("eyJ...");
const token = session.getToken();  // or null
session.clearToken();

// Username (localStorage)
session.setUsername("matias");
const name = session.getUsername(); // defaults to "User"

// Chat messages (sessionStorage -- survives refresh, cleared on tab close)
session.saveChatMessages([{ role: "user", content: "hello" }]);
const messages = session.restoreChatMessages(); // [] if empty
session.clearChatMessages();
```

Storage keys:
- `capos_token` -- JWT token (localStorage)
- `capos_username` -- display name (localStorage)
- `capos_chat_session` -- chat messages (sessionStorage)

---

### notifications.js -- Push and Local Notifications

```js
import * as notifications from "../sdk/notifications.js";

// Register service worker (call once on app init)
await notifications.registerSW();

// Request permission
const permission = await notifications.requestPermission(); // "granted" | "denied" | "default"

// Show a local notification
notifications.showLocalNotification("Task Complete", "Your deployment finished successfully.");

// Check if running as installed PWA
notifications.isInstalled(); // true/false
```

Graceful fallback chain:
1. Service Worker notification (if registered)
2. Native `Notification` API
3. Silent no-op (if permission denied)

---

### eventTypes.js -- Typed Event Constants

Use these instead of raw strings to avoid typos:

```js
import { EVENTS, HISTORY_EVENTS, EVENT_LABELS, SECTION_FOR_EVENT } from "../sdk/eventTypes.js";

sdk.events.on(EVENTS.EXECUTION_COMPLETE, handler);
sdk.events.on(EVENTS.TELEGRAM_MESSAGE, handler);
```

**All 24 event types:**

| Constant | Value | Category |
|----------|-------|----------|
| `TELEGRAM_MESSAGE` | `telegram_message` | Message Reception |
| `WHATSAPP_MESSAGE` | `whatsapp_message` | Message Reception |
| `SLACK_MESSAGE` | `slack_message` | Message Reception |
| `DISCORD_MESSAGE` | `discord_message` | Message Reception |
| `SESSION_UPDATED` | `session_updated` | Session |
| `EXECUTION_COMPLETE` | `execution_complete` | Session |
| `SETTINGS_UPDATED` | `settings_updated` | Configuration |
| `CONFIG_IMPORTED` | `config_imported` | Configuration |
| `PREFERENCES_UPDATED` | `preferences_updated` | Configuration |
| `WORKSPACE_CHANGED` | `workspace_changed` | Workspace |
| `MEMORY_CLEARED` | `memory_cleared` | Memory |
| `INTEGRATION_CHANGED` | `integration_changed` | Integrations |
| `GROWTH_UPDATE` | `growth_update` | Growth |
| `MCP_CHANGED` | `mcp_changed` | MCP |
| `A2A_CHANGED` | `a2a_changed` | A2A |
| `BROWSER_CHANGED` | `browser_changed` | Browser |
| `SUPERVISOR_ALERT` | `supervisor_alert` | Supervisor |
| `SUPERVISOR_ACTION` | `supervisor_action` | Supervisor |
| `SKILL_CREATED` | `skill_created` | Supervisor |
| `SCHEDULER_CYCLE` | `scheduler_cycle` | Scheduler |
| `AUTH_SETUP_COMPLETE` | `auth_setup_complete` | Auth |
| `ERROR` | `error` | Errors |
| `WHATSAPP_MESSAGE_PROCESSED` | `whatsapp_message_processed` | Processed |

**Helper exports:**

- `HISTORY_EVENTS` -- array of events that should trigger a history reload
- `EVENT_LABELS` -- maps event types to user-friendly toast labels
- `SECTION_FOR_EVENT` -- maps event types to ControlCenter section IDs

---

## Domain Reference

### sdk.auth

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `status()` | `GET /auth/status` | Check if owner exists |
| `setup(username, password)` | `POST /auth/setup` | Create owner account |
| `login(username, password)` | `POST /auth/login` | Login, returns JWT |
| `me()` | `GET /auth/me` | Current user profile |
| `listUsers()` | `GET /auth/users` | List all users |
| `createUser(user)` | `POST /auth/users` | Create a user |
| `updateUser(userId, fields)` | `PUT /auth/users/{id}` | Update a user |
| `deleteUser(userId)` | `DELETE /auth/users/{id}` | Delete a user |

### sdk.agents

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /agents` | List custom agents |
| `create(config)` | `POST /agents` | Create agent |
| `get(id)` | `GET /agents/{id}` | Get agent definition |
| `update(id, fields)` | `POST /agents/{id}` | Update agent |
| `delete(id)` | `DELETE /agents/{id}` | Delete agent |
| `design(description)` | `POST /agents/design` | AI-assisted design |
| `run(message, sessionId, history, agentId)` | `POST /agent` | One-shot agent call |
| `confirm(sessionId, confirmationId, approved, password)` | `POST /agent/confirm` | Confirm/reject L2/L3 |
| `getSession(sessionId)` | `GET /agent/{sessionId}` | Get session state |
| `stream(message, sessionId, history, agentId, workspaceId)` | `POST /agent/stream` | SSE agent stream |

### sdk.capabilities

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /capabilities` | List capabilities |
| `get(id)` | `GET /capabilities/{id}` | Get capability |
| `health()` | `GET /capabilities/health` | Health summary |
| `execute(capabilityId, inputs)` | `POST /execute` | Execute capability |
| `getExecution(id)` | `GET /executions/{id}` | Get result |
| `getExecutionEvents(id)` | `GET /executions/{id}/events` | Get event log |
| `interpret(text)` | `POST /interpret` | NLU intent |
| `plan(intent, history)` | `POST /plan` | Generate plan |
| `chat(message, userName, history)` | `POST /chat` | One-shot chat |
| `streamChat(message, userName, history)` | `POST /chat/stream` | SSE chat chunks |
| `streamExecution(capabilityId, inputs)` | `POST /execute/stream` | SSE execution |

### sdk.integrations

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /integrations` | List all integrations |
| `get(id)` | `GET /integrations/{id}` | Get integration |
| `validate(id)` | `POST /integrations/{id}/validate` | Validate config |
| `enable(id)` | `POST /integrations/{id}/enable` | Enable |
| `disable(id)` | `POST /integrations/{id}/disable` | Disable |

**Channel sub-objects:** `sdk.integrations.telegram`, `.slack`, `.discord`, `.whatsapp`, `.signal`, `.matrix`, `.teams`, `.email`, `.webhook`

Each channel (except WhatsApp) exposes: `status()`, `configure(config)`, `test()`, `startPolling()`, `stopPolling()`, `pollingStatus()`.

WhatsApp has: `status()`, `start()`, `stop()`, `closeSession()`, `qr()`, `configure(config)`, `switchBackend(backend)`, `listBackends()`.

### sdk.memory

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `context()` | `GET /memory/context` | Agent context |
| `history(capabilityId, workspaceId)` | `GET /memory/history` | Execution history |
| `deleteHistory(executionId)` | `DELETE /memory/history/{id}` | Delete entry |
| `saveChatSession(...)` | `POST /memory/history/chat` | Save chat |
| `saveSession(session)` | `POST /memory/sessions` | Save session |
| `getSession(executionId)` | `GET /memory/sessions/{id}` | Get session |
| `preferences()` | `GET /memory/preferences` | Get prefs |
| `setPreferences(prefs)` | `POST /memory/preferences` | Set prefs |
| `clearAll()` | `DELETE /memory` | Clear all |
| `compact(maxAgeHours)` | `POST /memory/compact` | Compact history |
| `metrics()` | `GET /metrics` | Execution metrics |
| `daily(date)` | `GET /memory/daily` | Daily notes |
| `summaries()` | `GET /memory/summaries` | Summaries |
| `agentContext()` | `GET /memory/agent-context` | Full context |

**Sub-objects:**

`sdk.memory.semantic`: `search(query, topK)`, `add(text, memoryType, metadata)`, `delete(memId)`

`sdk.memory.markdown`: `get()`, `save(content)`, `addFact(section, fact)`, `removeFact(section, factSubstring)`

### sdk.system

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `status()` | `GET /status` | System status |
| `health()` | `GET /health` | Health check |
| `logs()` | `GET /logs` | System logs |
| `exportConfig()` | `GET /system/export-config` | Export config |
| `importConfig(data)` | `POST /system/import-config` | Import config |

**Sub-objects:**

`sdk.system.settings`: `get()`, `save(settings)`

`sdk.system.llm`: `test()`

`sdk.system.browser`: `cdpStatus()`, `launchChrome()`, `connectCDP()`, `restart()`, `openWhatsApp()`

`sdk.system.plugins`: `list()`, `get(id)`, `reload(id)`, `install(path)`

`sdk.system.supervisor`: `status()`, `log()`, `invoke(prompt)`, `healthCheck()`, `approve(previewId)`, `discard(previewId)`

`sdk.system.scheduler`: `status()`, `log()`, `listTasks()`, `createTask(task)`, `updateTask(taskId, fields)`, `deleteTask(taskId)`, `runNow(taskId)`

`sdk.system.files`: `tree(wsId)`, `read(path, wsId)`, `write(path, content, wsId)`, `create(path, content, wsId)`, `delete(path, wsId)`, `terminal(command, wsId)`

### sdk.workspaces

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /workspaces` | List workspaces |
| `add(name, path, access, capabilities, color)` | `POST /workspaces` | Create |
| `get(id)` | `GET /workspaces/{id}` | Get details |
| `update(id, fields)` | `POST /workspaces/{id}` | Update |
| `remove(id)` | `DELETE /workspaces/{id}` | Remove |
| `setDefault(id)` | `POST /workspaces/{id}/set-default` | Set default |
| `updateStatus(id, status)` | `POST /workspaces/{id}/status` | Set status label |
| `browse(id, relativePath)` | `GET /workspaces/{id}/browse` | Browse files |
| `analyze(wsId)` | `GET /files/analyze/{id}` | Analyze health |
| `autoClean(wsId, dryRun)` | `POST /files/auto-clean/{id}` | Auto-clean |
| `generateReadme(wsId)` | `POST /files/generate-readme/{id}` | Generate README |

### sdk.mcp

`sdk.mcp.servers`: `list()`, `add(serverConfig)`, `remove(id)`, `discover(id)`

`sdk.mcp.tools`: `list()`, `install(id)`, `uninstall(id)`

### sdk.a2a

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `agentCard()` | `GET /.well-known/agent.json` | This agent's card |
| `agents.list()` | `GET /a2a/agents` | List remote agents |
| `agents.add(url, id)` | `POST /a2a/agents` | Register agent |
| `agents.remove(id)` | `DELETE /a2a/agents/{id}` | Remove agent |
| `delegate(agentId, skillId, message)` | `POST /a2a/agents/{id}/delegate` | Delegate task |

### sdk.workflows

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /workflows` | List workflows |
| `create(name, description)` | `POST /workflows` | Create workflow |
| `get(id)` | `GET /workflows/{id}` | Get definition |
| `update(id, data)` | `PUT /workflows/{id}` | Update workflow |
| `delete(id)` | `DELETE /workflows/{id}` | Delete workflow |
| `run(id)` | `POST /workflows/{id}/run` | Run workflow |

### sdk.skills

| Method | Backend Endpoint | Description |
|--------|-----------------|-------------|
| `list()` | `GET /skills` | List skills |
| `get(id)` | `GET /skills/{id}` | Get skill |
| `install(source)` | `POST /skills/install` | Install |
| `uninstall(id)` | `DELETE /skills/{id}` | Uninstall |
| `autoGenerated()` | `GET /skills/auto-generated` | List auto-generated |

### sdk.growth

`sdk.growth.gaps`: `pending()`, `analyze(id)`, `generate(id, overrides)`, `approve(id)`, `reject(id)`

`sdk.growth.optimizations`: `pending()`, `approve(id, proposedContract)`, `reject(id)`

`sdk.growth.proposals`: `list()`, `regenerate(id)`, `approve(capabilityId)`, `reject(capabilityId)`

### sdk.session

| Function | Description |
|----------|-------------|
| `getToken()` | Get JWT from localStorage |
| `setToken(token)` | Store JWT |
| `clearToken()` | Remove JWT |
| `getUsername()` | Get display name (default: "User") |
| `setUsername(name)` | Store display name |
| `saveChatMessages(messages)` | Persist chat to sessionStorage |
| `restoreChatMessages()` | Restore chat (returns []) |
| `clearChatMessages()` | Clear chat state |

### sdk.events

| Method | Description |
|--------|-------------|
| `on(type, fn)` | Subscribe to event type (or "*" for all) |
| `off(type, fn)` | Unsubscribe |
| `isConnected()` | WebSocket connection state |
| `onConnectionChange(fn)` | Track connection changes, returns unsub function |
| `destroy()` | Close WebSocket and clear all listeners |

---

## ControlCenter Section Pattern

To add a new section to the Control Center:

### Step 1: Create the section component

```jsx
// src/components/control-center/sections/MySection.jsx
import React from "react";
import sdk from "../../../sdk";

export default function MySection({ settings, health, integrations, act, toast }) {
  const [data, setData] = React.useState(null);

  React.useEffect(() => {
    sdk.myDomain.list().then(setData).catch(() => toast("Failed to load", "error"));
  }, []);

  return (
    <div className="cc-section">
      <h2>My Section</h2>
      {/* Section UI here */}
    </div>
  );
}
```

### Step 2: Export from sections/index.js

```js
// sections/index.js
export { default as MySection } from "./MySection.jsx";
```

### Step 3: Register in sectionRegistry.js

```js
// Add to the SECTION_REGISTRY array
{ id: "my-section", label: "My Section", keywords: ["my", "custom", "feature"] },
```

### Step 4: Map events (optional)

If your section should react to WebSocket events, add mappings in `eventTypes.js`:

```js
// In SECTION_FOR_EVENT
[EVENTS.MY_EVENT]: "my-section",

// In EVENT_LABELS
[EVENTS.MY_EVENT]: "My event occurred",
```

The ControlCenter's wildcard event handler will automatically:
- Show a toast notification
- Highlight the section in the sidebar
- Refresh data if the section is active

**Props received by every section:**

| Prop | Type | Description |
|------|------|-------------|
| `settings` | `object` | Current system settings |
| `health` | `object` | System health snapshot |
| `integrations` | `array` | Integration status list |
| `act(fn, msg)` | `function` | Execute an async action with loading/error handling |
| `toast(text, type)` | `function` | Show a toast notification |
| `saving` | `boolean` | Whether a save is in progress |
| `error` | `string` | Current error message |

---

## Channel Integration Pattern

To add a new messaging channel to the Integrations section, use the `ChannelCard` component:

### In the SDK (domains/integrations.js)

Use the `channelDomain()` helper to generate standard endpoints:

```js
function channelDomain(prefix) {
  return {
    status: () => get(`${prefix}/status`),
    configure: (config) => post(`${prefix}/configure`, typeof config === "object" ? config : {}),
    test: () => post(`${prefix}/test`, {}),
    startPolling: () => post(`${prefix}/polling/start`, {}),
    stopPolling: () => post(`${prefix}/polling/stop`, {}),
    pollingStatus: () => get(`${prefix}/polling/status`),
  };
}

// Usage
export const integrations = {
  myChannel: channelDomain("/integrations/my-channel"),
};
```

### In the UI (IntegrationsSection.jsx)

Import `ChannelCard` and add it to the section:

```jsx
import ChannelCard from "./integrations/ChannelCard";

<ChannelCard
  name="My Channel"
  icon="icon-emoji-or-svg"
  channelSdk={sdk.integrations.myChannel}
  onAction={(action) => act(() => sdk.integrations.myChannel[action](), `${action} done`)}
/>
```

The `ChannelCard` component handles the standard UI for status display, configure button, test button, and polling start/stop.

---

## Testing Pattern

SDK tests use Vitest with mock isolation:

```js
// __tests__/client.test.js
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock session BEFORE importing client
vi.mock("../session.js", () => ({
  getToken: vi.fn(() => "test-jwt-token"),
  clearToken: vi.fn(),
}));

const { request, get, post } = await import("../client.js");
const { getToken, clearToken } = await import("../session.js");

describe("client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    getToken.mockReturnValue("test-jwt-token");
    global.fetch = vi.fn();
  });

  it("sends GET with auth header", async () => {
    global.fetch.mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ data: 1 }),
    });

    const result = await get("/test");

    expect(global.fetch).toHaveBeenCalledWith("/test", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({
        Authorization: "Bearer test-jwt-token",
      }),
    }));
    expect(result).toEqual({ data: 1 });
  });
});
```

**Key patterns:**
- Mock `session.js` before importing the module under test
- Mock `global.fetch` to control HTTP responses
- Use `vi.restoreAllMocks()` in `beforeEach` for isolation
- Test both success and error paths (401, 500, network errors)

### Testing components that use the SDK

```js
// Mock the entire SDK
vi.mock("../sdk", () => ({
  default: {
    capabilities: { list: vi.fn(() => Promise.resolve({ capabilities: [] })) },
    events: { on: vi.fn(), off: vi.fn(), isConnected: vi.fn(() => true), onConnectionChange: vi.fn(() => () => {}) },
    session: { getToken: vi.fn(() => "token"), getUsername: vi.fn(() => "User") },
  },
}));
```

---

## Architecture Rules

These rules are enforced by convention and code review. Violations introduce the same bugs the SDK was built to eliminate.

### 1. No raw `fetch()`

Every HTTP call must go through `sdk/client.js`. This ensures auth headers, 401 handling, and error extraction are consistent.

```js
// WRONG
const resp = await fetch("/capabilities");

// RIGHT
const data = await sdk.capabilities.list();
```

### 2. No direct `localStorage` / `sessionStorage`

Token and session state must go through `sdk/session.js`. This keeps storage keys centralized and makes token lifecycle testable.

```js
// WRONG
const token = localStorage.getItem("capos_token");

// RIGHT
import { getToken } from "../sdk/session.js";
const token = getToken();
```

### 3. No SSE parsing outside the SDK

All streaming goes through `client.js:streamSSE()`. Components consume async generators, never raw `ReadableStream`.

```js
// WRONG
const resp = await fetch("/chat/stream", { method: "POST", body: JSON.stringify({ message }) });
const reader = resp.body.getReader();

// RIGHT
for await (const chunk of sdk.capabilities.streamChat(message, userName)) {
  appendText(chunk);
}
```

### 4. No hardcoded URLs

Base URLs are resolved from environment variables (`VITE_API_BASE_URL`, `VITE_WS_URL`). Components never construct URLs manually.

### 5. Events go through `sdk.events`

Never create a standalone WebSocket. The SDK manages a single connection with automatic reconnection.

```js
// WRONG
const ws = new WebSocket("ws://localhost:8001");

// RIGHT
sdk.events.on("execution_complete", handler);
```
