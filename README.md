# Capability OS

**AI-powered personal operating system with autonomous agents, progressive security, and multi-channel messaging.**

<p align="center">
  <img src=".github/preview.png" alt="Capability OS" width="800"/>
</p>

An intelligent system that understands natural language, executes real actions through tools, manages projects, and communicates via WhatsApp, Telegram, Slack, and Discord — all from a cyberpunk-styled web interface.

```
CapabilityOS.bat          # double-click to launch (Windows)
python launcher.py        # or run directly
open http://localhost:8000
```

---

## Features

### Autonomous Agent
The LLM doesn't just suggest — it **executes**. The agent loop calls tools iteratively, observes results, retries on errors, and explains everything in natural language.

```
You: "list the files in my workspace"
Agent: [calls filesystem_list_directory] → artifacts, memory, pagina, skills, system
       "Your workspace has 7 directories: artifacts, memory, pagina..."
```

### Progressive Security (3 Levels)
| Level | Action | Example |
|-------|--------|---------|
| **1 — Free** | Read-only ops, no confirmation | Read files, list dirs, send messages |
| **2 — Confirm** | User clicks "Allow" | Write files, run commands, create dirs |
| **3 — Password** | Password/2FA required | Delete system files, modify OS settings |

### Custom Agents
Create AI team members with unique personalities, tools, and behaviors:
- **System prompt** — define personality and expertise
- **Tool selection** — choose which tools each agent can use
- **LLM model override** — each agent can use a different model
- **Assign to projects** — agents understand project context
- **AI Designer** — describe what you want and the AI creates the agent config

### Project Workspaces
- Create projects with custom status and icons
- Assign agents to projects
- Track session history per project
- Customizable states: Idea, In Progress, Completed, Paused, Archived (or create your own)

### Multi-Channel Messaging
| Channel | Status | Features |
|---------|--------|----------|
| **WhatsApp** | 3 backends | Browser (Puppeteer), Baileys, Official Cloud API |
| **Telegram** | Ready | Polling + auto-reply via agent |
| **Slack** | Ready | Polling + auto-reply |
| **Discord** | Ready | Polling + auto-reply |

### 54 Capabilities + 40 Tools
Filesystem, execution, network, browser automation, messaging, system info, sequences, MCP, A2A, and more.

---

## Quick Start

### Option 1: Launcher (recommended for Windows)

Double-click **`CapabilityOS.bat`** — opens a cyberpunk dashboard at `http://localhost:9000` where you can start/stop/restart the system.

### Option 2: Direct run

```bash
pip install -r requirements.txt
cd system/frontend/app && npm install && npm run build && cd ../../..
python docker-entrypoint.py
```

Open `http://localhost:8000`

### Option 3: Docker

```bash
docker compose up --build
```

### Configure LLM

The system supports multiple providers. Configure in Settings or via environment variables:

```bash
# Groq (free, recommended)
LLM_PROVIDER=openai LLM_BASE_URL=https://api.groq.com/openai/v1 OPENAI_API_KEY=gsk_...

# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=sk-...

# Anthropic
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-...

# Ollama (local, no key needed)
LLM_PROVIDER=ollama

# Gemini
LLM_PROVIDER=gemini GEMINI_API_KEY=...

# DeepSeek
LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=...
```

---

## Architecture

```
User Message
  → Agent Loop (iterative)
    ├── LLM decides which tool(s) to call
    ├── Security Service classifies: Level 1/2/3
    ├── Tool Runtime executes
    ├── Result fed back to LLM
    ├── If error → LLM retries or explains
    └── Loop until complete or needs user input
```

### System Components

| Component | Description | Location |
|-----------|-------------|----------|
| **Agent Loop** | Autonomous tool-use loop with multi-turn reasoning | `system/core/agent/` |
| **Agent Registry** | CRUD for custom agent definitions | `system/core/agent/agent_registry.py` |
| **Security Service** | 3-level classification (free/confirm/password) | `system/core/security/` |
| **Intent Interpreter** | Classic mode: classify → plan → execute | `system/core/interpretation/` |
| **Capability Engine** | Strategy executor (sequential/conditional/retry/fallback) | `system/core/capability_engine/` |
| **Tool Runtime** | 40+ tool handlers (filesystem, browser, network, etc.) | `system/tools/` |
| **Workspace Registry** | Project management with status, agents, paths | `system/core/workspace/` |
| **Error Notifier** | Detects errors, triggers Claude Code for auto-review | `system/core/observation/` |
| **WhatsApp Backends** | Browser (Puppeteer), Baileys, Official API | `system/integrations/installed/whatsapp_web_connector/` |
| **Channel Adapters** | Telegram, Slack, Discord polling + auto-reply | `system/integrations/` |
| **Event Bus** | Real-time pub/sub for WebSocket push | `system/core/ui_bridge/event_bus.py` |
| **WebSocket Server** | RFC 6455 compliant, real-time UI updates | `system/core/ui_bridge/ws_server.py` |
| **Frontend** | React 18 + Vite, cyberpunk theme | `system/frontend/app/` |
| **Launcher** | Web dashboard for start/stop/restart | `launcher.py` |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agent` | POST | Start autonomous agent session |
| `/agent/confirm` | POST | Confirm/deny Level 2/3 action |
| `/agents` | GET/POST | List/create custom agents |
| `/agents/{id}` | GET/POST/DELETE | Get/update/delete agent |
| `/agents/design` | POST | AI designs an agent from description |
| `/chat` | POST | Classify message (conversational vs action) |
| `/execute` | POST | Execute single capability |
| `/plan` | POST | Generate execution plan |
| `/health` | GET | System health check |
| `/settings` | GET/POST | System configuration |
| `/workspaces` | GET/POST | List/create workspaces |
| `/workspaces/{id}/status` | POST | Update project status |
| `/integrations` | GET | List all integrations |
| `/integrations/whatsapp/start` | POST | Connect WhatsApp |
| `/integrations/whatsapp/backends` | GET | List WhatsApp backends |
| `/capabilities` | GET | List all capabilities |

---

## Configuration

### Settings File

`system/settings.json` (copy from `system/settings.example.json`):

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.1-8b-instant",
    "api_key": "YOUR_KEY",
    "timeout_ms": 30000
  },
  "browser": {
    "backend": "playwright",
    "auto_start": true,
    "cdp_port": 0
  },
  "agent": {
    "enabled": true,
    "max_iterations": 10
  },
  "whatsapp": {
    "backend": "browser",
    "allowed_user_ids": []
  },
  "project_states": [
    {"name": "Idea", "color": "#a855f7", "icon": "💡"},
    {"name": "In Progress", "color": "#3b82f6", "icon": "🚀"},
    {"name": "Completed", "color": "#22c55e", "icon": "✅"}
  ]
}
```

### Browser Backend

| Backend | Setup | Use Case |
|---------|-------|----------|
| **Playwright** (default) | Zero config — works out of the box | General browsing, WhatsApp |
| **CDP** | Launch Chrome with `--remote-debugging-port=9222` | Reuse existing Chrome session |

### WhatsApp Backend

| Backend | Setup | Reliability |
|---------|-------|-------------|
| **Browser** | QR scan in UI, Puppeteer headless | Good for sending |
| **Baileys** | QR scan, Node.js protocol | May be blocked (405) |
| **Official** | Meta Business account + tokens | Best for production |

---

## Development

### Requirements
- Python 3.12+
- Node.js 18+
- Optional: `pip install playwright && python -m playwright install chromium`

### Run Tests
```bash
python -m pytest tests/ -v
cd system/frontend/app && npm test -- --run
```

### Verification Agent
```bash
python scripts/verify.py
```
Runs 16 checks: health, frontend bundle, API endpoints, WhatsApp backends, cache headers, etc.

### Project Structure
```
capability-os/
├── CapabilityOS.bat              # Windows launcher
├── launcher.py                   # Web dashboard launcher
├── docker-entrypoint.py          # Main server (API + frontend)
├── scripts/verify.py             # Post-deploy verification
├── system/
│   ├── core/
│   │   ├── agent/                # Autonomous agent loop + registry
│   │   ├── security/             # Progressive security (3 levels)
│   │   ├── interpretation/       # Intent classification + LLM client
│   │   ├── capability_engine/    # Strategy execution engine
│   │   ├── observation/          # Logging + error notifier
│   │   ├── workspace/            # Project workspace registry
│   │   ├── health/               # System health checks
│   │   ├── settings/             # Configuration management
│   │   ├── memory/               # Semantic memory + execution history
│   │   └── ui_bridge/            # API server + WebSocket + handlers
│   ├── tools/                    # 40+ tool implementations + contracts
│   ├── capabilities/             # 54 capability contracts
│   ├── integrations/             # WhatsApp, Telegram, Slack, Discord
│   ├── whatsapp_worker/          # Node.js workers (Baileys + Puppeteer)
│   └── frontend/app/             # React 18 + Vite frontend
└── tests/                        # Unit tests
```

---

## Changelog

### v2.0 (Current)
- **Autonomous Agent Loop** — LLM calls tools iteratively with error recovery
- **Progressive Security** — 3-level classification (free/confirm/password)
- **Custom Agents** — create, edit, assign to projects, AI designer
- **3 WhatsApp Backends** — Browser (Puppeteer), Baileys, Official Cloud API
- **Project Workspaces** — states, icons, agent assignment
- **Cyberpunk UI** — dark theme with neon accents
- **Launcher** — web dashboard for system management
- **Error Notifier** — auto-triggers Claude Code on errors
- **Verification Agent** — 16 automated post-deploy checks

### v1.0
- Conversational UI, session management
- MCP + A2A integration
- Semantic memory
- Self-improvement system
- Browser worker (CDP)

---

## License

MIT
