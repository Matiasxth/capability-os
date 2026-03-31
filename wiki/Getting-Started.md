# Getting Started

This guide walks you through installing Capability OS, configuring an LLM provider, creating your owner account, and connecting your first messaging channel.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required for the backend |
| Node.js | 18+ | Required for the WhatsApp worker and frontend build |
| npm | 9+ | Comes with Node.js |
| Git | 2.x | To clone the repository |
| Docker | 24+ | Optional -- only needed for Docker install or L3 sandbox |

---

## Installation

### Method 1: CLI (recommended)

```bash
git clone https://github.com/your-org/capability-os.git
cd capability-os

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd system/frontend/app
npm install
cd ../../..

# Start the system
python -m capabilityos serve
```

The CLI starts the ASGI backend on port **8000**, the WebSocket server on port **8001**, and opens the frontend in your default browser.

### Method 2: Windows Launcher

Double-click `start.bat` in the repository root. It performs the same steps as Method 1 automatically -- installs dependencies if missing, builds the frontend, and launches the server.

### Method 3: Docker

```bash
docker compose up --build
```

The `docker-compose.yml` maps:
- `8000` -> backend API
- `8001` -> WebSocket server
- `5173` -> Vite dev server (in dev profile)

Production builds use a multi-stage Dockerfile that compiles the frontend into static assets served by the ASGI server directly.

---

## LLM Configuration

Capability OS supports multiple LLM providers. Configure one (or more) via environment variables or through the **Control Center > LLM** section in the web UI.

### Supported Providers

| Provider | Env Variable | Free Tier? | Notes |
|----------|-------------|------------|-------|
| **Groq** | `GROQ_API_KEY` | Yes (generous) | Fastest inference, recommended for getting started |
| **OpenAI** | `OPENAI_API_KEY` | No | GPT-4o, GPT-4, GPT-3.5 |
| **Anthropic** | `ANTHROPIC_API_KEY` | No | Claude 3.5 Sonnet, Claude 3 Opus |
| **Google Gemini** | `GEMINI_API_KEY` | Yes (limited) | Gemini 1.5 Pro, Gemini 1.5 Flash |
| **DeepSeek** | `DEEPSEEK_API_KEY` | No | DeepSeek V2, DeepSeek Coder |
| **Ollama** | `OLLAMA_BASE_URL` | Yes (local) | Any local model; default URL `http://localhost:11434` |

### Setting environment variables

```bash
# Linux / macOS
export GROQ_API_KEY="gsk_..."

# Windows (PowerShell)
$env:GROQ_API_KEY = "gsk_..."

# Windows (cmd)
set GROQ_API_KEY=gsk_...
```

Alternatively, save them in the **Control Center > LLM** page. The values persist in `settings.json`.

### Selecting the model

In `settings.json` (or through the UI):

```json
{
  "llm_provider": "groq",
  "llm_model": "llama-3.3-70b-versatile"
}
```

The system auto-detects whichever API key is available if no explicit provider is set.

---

## First-Time Setup

When you open the web UI for the first time, you are redirected to the **Onboarding** page:

1. **Create the owner account** -- choose a username and password. This account has full admin privileges.
2. **Configure LLM** -- enter your API key or confirm the Ollama URL.
3. **Test connection** -- click "Test LLM" to verify the provider is reachable.
4. **Enter the workspace** -- you are redirected to the main chat interface.

> The owner account is stored in `users.json` with a bcrypt-hashed password. JWT tokens expire after 24 hours.

---

## Connecting Channels

Capability OS supports four messaging channels out of the box, with five more UI-ready for Sprint 9.

### Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the bot token.
2. Go to **Control Center > Integrations > Telegram**.
3. Paste the bot token and (optionally) set a default chat ID and allowed user IDs.
4. Click **Configure**, then **Start Polling**.
5. Messages sent to your bot now appear in CapOS and are processed by the agent.

### WhatsApp

1. Go to **Control Center > Integrations > WhatsApp**.
2. Click **Start Session** -- a QR code appears.
3. Scan the QR code with WhatsApp on your phone.
4. Once connected, incoming messages are forwarded to the agent.

WhatsApp supports multiple backends:
- **Baileys** (default) -- headless, no browser needed
- **Puppeteer** -- uses a browser session
- **Official API** -- requires a Meta Business account

Switch backends via **Control Center > Integrations > WhatsApp > Switch Backend**.

### Slack

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps).
2. Add the required OAuth scopes (`chat:write`, `channels:read`, `channels:history`).
3. Install the app to your workspace and copy the Bot Token.
4. Go to **Control Center > Integrations > Slack**, paste the token, and click **Configure**.

### Discord

1. Create a Discord Application at [discord.com/developers](https://discord.com/developers/applications).
2. Create a Bot, copy the token, and invite the bot to your server.
3. Go to **Control Center > Integrations > Discord**, paste the token, and click **Configure**.

---

## CLI Commands

The `capabilityos` CLI provides quick access to common operations:

| Command | Description |
|---------|-------------|
| `capabilityos serve` | Start the full system (backend + frontend) |
| `capabilityos chat` | Interactive REPL with agent switching and session management |
| `capabilityos status` | Show system status (plugins, LLM, channels) |
| `capabilityos plugins` | List all plugins and their states |
| `capabilityos version` | Print the current CapOS version |

### Chat REPL shortcuts

| Shortcut | Action |
|----------|--------|
| `/agent <name>` | Switch to a named agent |
| `/session new` | Start a new chat session |
| `/session list` | List recent sessions |
| `/tools` | List available tools |
| `/exit` | Quit the REPL |

---

## Troubleshooting

### Port 8000 already in use

Another process is using port 8000. Either stop it or change the port:

```bash
# Find what is using port 8000
# Linux/macOS:
lsof -i :8000
# Windows:
netstat -ano | findstr :8000

# Start on a different port
python -m capabilityos serve --port 8080
```

### LLM connection fails

1. Verify your API key is set: check `settings.json` or the environment variable.
2. Click **Test LLM** in the Control Center to see the exact error.
3. If using Ollama, confirm it is running (`ollama list`) and the `OLLAMA_BASE_URL` is correct.
4. Check your firewall or proxy settings -- the backend needs outbound HTTPS access.

### Browser does not open automatically

The `serve` command tries to open your default browser. If it fails:
- Navigate manually to `http://localhost:8000` (production) or `http://localhost:5173` (Vite dev).

### WebSocket disconnected (red indicator)

The frontend connects to the WebSocket server on port `API_PORT + 1` (default 8001). If the connection drops:
- Check that the backend is still running.
- If you changed the API port, the WS port changes too (it is always API port + 1).
- Behind a reverse proxy, ensure WebSocket upgrade headers are forwarded.

### "Failed to fetch" errors

This usually means the backend is not running or CORS is blocking the request.
- Confirm the backend process is alive.
- Set `CORS_ORIGIN` environment variable to your frontend URL if running on a different origin.

### Agent fails silently

- Check **Control Center > LLM** -- the API key may be expired or rate-limited.
- Look at the backend console for Python tracebacks.
- Verify the circuit breaker has not tripped: restart the server to reset it.

### Docker container exits immediately

- Run `docker compose logs` to see the error.
- Common cause: missing environment variables. Pass them via `.env` file or `docker compose` environment section.
- Ensure Docker has enough memory allocated (at least 2 GB recommended).
