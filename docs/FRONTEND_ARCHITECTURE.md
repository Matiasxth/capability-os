# Frontend Architecture — Capability OS

## Overview

React 18 SPA with SDK-first architecture. All backend communication flows through a centralized SDK layer.

```
                    App.jsx (routing, auth guard)
                         |
        +----------------+----------------+
        |                |                |
   Workspace.jsx  ControlCenter.jsx  WorkflowEditor.jsx
   (chat/agent)    (96-line shell)    (visual editor)
        |                |
        |         16 section components
        |          (independent state)
        |                |
        +--------+-------+
                 |
            src/sdk/index.js  ←── SINGLE GATEWAY
            /       |        \
      client.js  events.js  session.js
      (HTTP+SSE)  (WebSocket) (token+chat)
           |
     domains/ (13 files)
     agents, capabilities, integrations,
     memory, system, workspaces, mcp,
     a2a, workflows, skills, growth, auth
```

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `sdk/client.js` | 105 | HTTP client + SSE parser. ALL fetch calls. Auth injection. |
| `sdk/events.js` | 95 | WebSocket event bus. Dynamic URL. Auto-reconnect. |
| `sdk/session.js` | 56 | Token lifecycle. Chat persistence to sessionStorage. |
| `sdk/eventTypes.js` | 100 | Event enum, labels, section mapping. |
| `sdk/notifications.js` | 48 | SW registration, push permissions, local notifications. |
| `sdk/index.js` | 45 | Composes all domains into singleton `sdk` object. |
| `sdk/domains/*.js` | ~500 | 13 domain files mapping to 140+ backend endpoints. |

## Architecture Rules

1. **Components NEVER call `fetch()` directly.** All HTTP goes through `sdk`.
2. **Components NEVER access `localStorage` for auth tokens.** Only `sdk.session` does.
3. **Components NEVER parse SSE streams.** Only `sdk/client.streamSSE()` does.
4. **WebSocket events go through `sdk.events`**, not raw `useWebSocket`.
5. **New channels** = 1 object in `CHANNELS[]` array + 1 `channelDomain()` in SDK.

These rules are enforced by `.eslintrc.json` (`no-restricted-imports`, `no-restricted-syntax`).

## SDK Usage

```js
import sdk from "./sdk";  // or "../sdk", "../../sdk"

// HTTP
const caps = await sdk.capabilities.list();
await sdk.system.settings.save({ llm: { model: "gpt-4o" } });

// Streaming (with auth)
for await (const chunk of sdk.capabilities.streamChat("hello", "User")) {
  console.log(chunk);
}

// Events (replaces polling)
sdk.events.on("execution_complete", (e) => { ... });
sdk.events.on("*", (e) => { ... });  // wildcard
sdk.events.onConnectionChange((connected) => { ... });

// Session
sdk.session.getToken();
sdk.session.saveChatMessages(messages);
const restored = sdk.session.restoreChatMessages();

// Notifications
import { requestPermission, showLocalNotification } from "./sdk/notifications";
await requestPermission();
showLocalNotification("CapOS", "New message from Telegram");
```

## Component Hierarchy

```
App.jsx
├── AuthProvider (AuthContext.jsx → sdk.auth)
├── ThemeProvider
├── WebSocketProvider (→ sdk.events)
├── ToastProvider
├── NotificationCenter (events feed panel)
├── InstallPrompt (PWA install banner)
│
├── Login.jsx (sdk.auth.status, sdk.auth.setup)
├── Onboarding.jsx (sdk.memory, sdk.system.settings)
│
├── Workspace.jsx (chat/agent interface)
│   ├── ChatThread, ChatInput, AgentStepView
│   ├── ProjectSidebar, SessionSidebar
│   └── sdk.events.on("*") for real-time updates
│
├── ControlCenter.jsx (96-line shell)
│   ├── CCLayout + CCSidebar
│   ├── KPIBar
│   └── 16 section components:
│       SystemSection, WorkspacesSection, LLMSection,
│       MetricsSection, OptimizeSection, AutoGrowthSection,
│       MCPSection, A2ASection, MemorySection,
│       IntegrationsSection (→ ChannelCard),
│       BrowserSection, SkillsSection, SupervisorSection,
│       SchedulerSection, AgentsSection, ProjectStatesSection
│
├── WorkflowEditor.jsx (ReactFlow canvas)
└── EditorLayout.jsx (Monaco editor)
```

## Event Flow

```
Backend EventBus
    ↓ emit("telegram_message", {from, text})
WebSocket Server (port 8001)
    ↓ JSON frame
sdk/events.js (createEventBus)
    ↓ notify listeners
    ├── App.jsx → ncEvents (NotificationCenter)
    │            → push notification if document.hidden
    ├── Workspace.jsx → loadHistory() if HISTORY_EVENT
    │                 → toast if EVENT_LABELS match
    └── ControlCenter.jsx → refreshAll() if active section matches
```

## ControlCenter Section Pattern

Each section is a standalone React component:

```jsx
// sections/MetricsSection.jsx
import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function MetricsSection({ toast }) {
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    sdk.memory.metrics().then(r => setMetrics(r.metrics || null));
    const id = setInterval(() => sdk.memory.metrics().then(r => setMetrics(r.metrics || null)), 30000);
    return () => clearInterval(id);
  }, []);

  if (!metrics) return <div className="skeleton skeleton-block" />;
  return (<div>...</div>);
}
```

## Channel Integration Pattern

All channels use `ChannelCard` component with declarative config:

```jsx
// In IntegrationsSection.jsx
const CHANNELS = [
  {
    name: "Telegram",
    sdkKey: "telegram",
    fields: [
      { key: "token", label: "Token", placeholder: "123456:ABC-DEF...", type: "token" },
      { key: "chat_id", label: "Chat ID", placeholder: "-1234567890" },
    ],
    buildConfig: (v) => ({ bot_token: v.token, default_chat_id: v.chat_id }),
    guide: <ol>...</ol>,
  },
  // Adding a new channel = adding one object here + one channelDomain() in SDK
];
```

## Testing

- **Framework**: Vitest + @testing-library/react + jsdom
- **SDK tests**: Mock `fetch()` directly (unit tests for client.js)
- **Domain tests**: Mock `client.js` (verify endpoint mapping)
- **Component tests**: Mock `sdk` module (integration tests)
- **CI**: `.github/workflows/frontend-ci.yml` — runs on push/PR to `system/frontend/**`

## PWA

- `manifest.json`: standalone display, theme_color #00ff88, SVG icons
- `sw.js`: cache static assets, network-first HTML, push handler
- `InstallPrompt.jsx`: `beforeinstallprompt` banner
- `sdk/notifications.js`: permission, local notifications, SW registration
