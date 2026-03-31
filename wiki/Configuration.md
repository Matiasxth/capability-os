# Configuration Reference

Complete reference for configuring Capability OS. Configuration is managed through `settings.json`, environment variables, and Docker compose files.

---

## Table of Contents

- [settings.json](#settingsjson)
- [Environment Variables](#environment-variables)
- [Docker Configuration](#docker-configuration)
- [LLM Providers](#llm-providers)
- [Browser Configuration](#browser-configuration)
- [Sandbox Configuration](#sandbox-configuration)
- [Auth Settings](#auth-settings)
- [Channel Configuration](#channel-configuration)
- [MCP Server Configuration](#mcp-server-configuration)
- [A2A Configuration](#a2a-configuration)
- [Workspace Configuration](#workspace-configuration)
- [Agent Configuration](#agent-configuration)

---

## settings.json

The primary configuration file located at `system/settings.json`. A template with safe defaults is provided at `system/settings.example.json`.

> **SECURITY WARNING**: Never commit `settings.json` with real API keys. If a key was committed, rotate it immediately at your provider's console.

### Complete Structure

```json
{
  "_security_note": "NEVER commit settings.json with real API keys.",

  "llm": {
    "provider": "openai",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.3-70b-versatile",
    "api_key": "YOUR_API_KEY_HERE",
    "timeout_ms": 30000
  },

  "browser": {
    "backend": "playwright",
    "auto_start": false,
    "cdp_port": 0,
    "auto_restart_max_retries": 2
  },

  "agent": {
    "enabled": true,
    "max_iterations": 10
  },

  "workspace": {
    "artifacts_path": "/path/to/artifacts",
    "sequences_path": "/path/to/sequences"
  },

  "sandbox": {
    "process_timeout": 30,
    "docker_timeout": 60,
    "docker_image": "python:3.12-slim",
    "max_memory_mb": 512
  },

  "mcp": {
    "servers": [],
    "auto_discover_capabilities": false,
    "server_timeout_ms": 10000
  },

  "a2a": {
    "enabled": true,
    "server_url": "http://localhost:8000",
    "known_agents": []
  },

  "telegram": {
    "bot_token": "",
    "default_chat_id": "",
    "allowed_user_ids": [],
    "allowed_usernames": [],
    "polling_enabled": false,
    "display_name": ""
  },

  "slack": {
    "bot_token": "",
    "channel_id": "",
    "allowed_user_ids": [],
    "polling_enabled": false
  },

  "discord": {
    "bot_token": "",
    "channel_id": "",
    "guild_id": "",
    "allowed_user_ids": [],
    "polling_enabled": false
  },

  "whatsapp": {
    "backend": "browser",
    "allowed_user_ids": [],
    "official": {
      "phone_number_id": "",
      "access_token": "",
      "verify_token": ""
    }
  }
}
```

### Field Reference

#### `llm` -- LLM Provider Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | `string` | `"openai"` | LLM provider identifier. All providers use the OpenAI-compatible API format |
| `base_url` | `string` | `"https://api.openai.com/v1"` | API endpoint URL |
| `model` | `string` | `"gpt-4o-mini"` | Model identifier |
| `api_key` | `string` | `""` | API key (masked in API responses) |
| `timeout_ms` | `integer` | `30000` | Request timeout in milliseconds |

#### `browser` -- Browser Worker Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `backend` | `string` | `"playwright"` | Browser backend: `"playwright"` or `"cdp"` |
| `auto_start` | `boolean` | `false` | Auto-launch browser on startup |
| `cdp_port` | `integer` | `0` | Chrome DevTools Protocol port (0 = disabled) |
| `auto_restart_max_retries` | `integer` | `2` | Max auto-restart attempts on crash |

#### `agent` -- Agent Loop Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `boolean` | `true` | Enable the agent loop |
| `max_iterations` | `integer` | `10` | Maximum tool-use iterations per request |

#### `workspace` -- Workspace Paths

| Field | Type | Default | Description |
|---|---|---|---|
| `artifacts_path` | `string` | `"<project>/artifacts"` | Where generated artifacts are stored |
| `sequences_path` | `string` | `"<project>/sequences"` | Where automation sequences are stored |

#### `sandbox` -- Execution Sandbox

| Field | Type | Default | Description |
|---|---|---|---|
| `process_timeout` | `integer` | `30` | L2 process sandbox timeout (seconds) |
| `docker_timeout` | `integer` | `60` | L3 Docker sandbox timeout (seconds) |
| `docker_image` | `string` | `"python:3.12-slim"` | Docker image for L3 sandboxed execution |
| `max_memory_mb` | `integer` | `512` | Memory limit for Docker containers |

---

## Environment Variables

Environment variables override `settings.json` values when running in Docker. They are defined in `docker-compose.yml` and `.env` files.

### LLM Variables

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | LLM provider name | `ollama` |
| `LLM_BASE_URL` | API base URL | Varies by provider |
| `LLM_MODEL` | Model name | Varies by provider |
| `OPENAI_API_KEY` | OpenAI API key | (empty) |
| `OPENAI_BASE_URL` | OpenAI API URL | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o-mini` |
| `ANTHROPIC_API_KEY` | Anthropic API key | (empty) |
| `ANTHROPIC_MODEL` | Anthropic model | `claude-sonnet-4-20250514` |
| `GEMINI_API_KEY` | Google Gemini API key | (empty) |
| `GEMINI_MODEL` | Gemini model | `gemini-2.0-flash` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (empty) |
| `DEEPSEEK_MODEL` | DeepSeek model | `deepseek-chat` |

### Infrastructure Variables

| Variable | Description | Default |
|---|---|---|
| `WS_PORT` | WebSocket server port | `8001` |
| `BROWSER_CDP_URL` | Chrome DevTools Protocol URL | `ws://chrome:3000` |
| `BROWSER_TOKEN` | Browserless authentication token | `capos_browser_secret` |

---

## Docker Configuration

### docker-compose.yml

The production Docker setup includes two services:

```yaml
version: "3.8"

services:
  chrome:
    image: browserless/chrome:1-chrome-stable
    container_name: capos-chrome
    expose:
      - "3000"
    environment:
      - MAX_CONCURRENT_SESSIONS=2
      - CONNECTION_TIMEOUT=120000
      - TOKEN=${BROWSER_TOKEN:-capos_browser_secret}
    restart: unless-stopped

  capability-os:
    build: .
    container_name: capability-os
    ports:
      - "127.0.0.1:8000:8000"    # API server
      - "127.0.0.1:8001:8001"    # WebSocket server
    security_opt:
      - no-new-privileges:true
    volumes:
      - workspace:/data/workspace
      - artifacts:/data/workspace/artifacts
    environment:
      # (see Environment Variables section above)
    depends_on:
      - chrome
    restart: unless-stopped

volumes:
  workspace:
  artifacts:
```

### Key Docker Features

- **`no-new-privileges`**: Security option preventing privilege escalation inside the container
- **Loopback binding**: Ports bound to `127.0.0.1` only (not exposed to network)
- **Chrome isolation**: The `chrome` service is not exposed to the host -- only accessible from the `capability-os` container via internal Docker networking
- **Named volumes**: `workspace` and `artifacts` persist data across container restarts

### Starting Docker

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f capability-os

# Stop
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

---

## LLM Providers

Capability OS supports multiple LLM providers through an OpenAI-compatible API interface. All providers are configured through the `llm` section in `settings.json`.

### Groq (Default for Development)

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.3-70b-versatile",
    "api_key": "gsk_YOUR_GROQ_KEY",
    "timeout_ms": 30000
  }
}
```

Available Groq models: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, `gemma2-9b-it`

### OpenAI

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "sk-YOUR_OPENAI_KEY",
    "timeout_ms": 30000
  }
}
```

Available models: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1-mini`, `o3-mini`

### Anthropic

```json
{
  "llm": {
    "provider": "anthropic",
    "base_url": "https://api.anthropic.com/v1",
    "model": "claude-sonnet-4-20250514",
    "api_key": "sk-ant-YOUR_ANTHROPIC_KEY",
    "timeout_ms": 60000
  }
}
```

Available models: `claude-sonnet-4-20250514`, `claude-haiku-4-20250414`, `claude-3-5-sonnet-20241022`

### Ollama (Local)

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.1:8b",
    "api_key": "ollama",
    "timeout_ms": 60000
  }
}
```

Available models: Any model installed via `ollama pull <model>`. Common choices: `llama3.1:8b`, `llama3.1:70b`, `mistral`, `codellama`, `phi3`

### Google Gemini

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "gemini-2.0-flash",
    "api_key": "YOUR_GEMINI_KEY",
    "timeout_ms": 30000
  }
}
```

Available models: `gemini-2.0-flash`, `gemini-2.0-pro`, `gemini-1.5-flash`

### DeepSeek

```json
{
  "llm": {
    "provider": "openai",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "YOUR_DEEPSEEK_KEY",
    "timeout_ms": 30000
  }
}
```

Available models: `deepseek-chat`, `deepseek-coder`, `deepseek-reasoner`

---

## Browser Configuration

The browser worker supports two backends for web automation:

### Playwright (Default)

Playwright manages its own browser instance. Best for local development.

```json
{
  "browser": {
    "backend": "playwright",
    "auto_start": true,
    "auto_restart_max_retries": 2
  }
}
```

### CDP (Chrome DevTools Protocol)

Connects to an external Chrome instance. Used in Docker setups where Chrome runs in a separate container.

```json
{
  "browser": {
    "backend": "cdp",
    "cdp_port": 9222,
    "auto_start": true
  }
}
```

In Docker, the CDP URL is set via the `BROWSER_CDP_URL` environment variable pointing to the `chrome` service (`ws://chrome:3000`).

---

## Sandbox Configuration

The execution sandbox provides two isolation levels:

### L2 -- Process Sandbox

Runs code in a subprocess with timeout and resource limits. Always available.

```json
{
  "sandbox": {
    "process_timeout": 30
  }
}
```

### L3 -- Docker Sandbox

Runs code in an isolated Docker container. Requires Docker to be installed and running.

```json
{
  "sandbox": {
    "docker_timeout": 60,
    "docker_image": "python:3.12-slim",
    "max_memory_mb": 512
  }
}
```

---

## Auth Settings

Authentication is configured through `users.json` and `jwt_secret.key` files in the workspace root. These are created automatically on first setup.

### Roles

| Role | Workspaces | Agents | Max Security Level | Supervisor | Create Skills |
|---|---|---|---|---|---|
| `owner` | All (`*`) | All (`*`) | 10 | Yes | Yes |
| `admin` | All (`*`) | All (`*`) | 7 | Yes | Yes |
| `user` | Assigned only | Assigned only | 3 | No | No |
| `viewer` | Assigned only | Assigned only | 0 | No | No |

### JWT Configuration

- **Algorithm**: HS256
- **Secret**: Auto-generated 128-character hex string, stored in `workspace/jwt_secret.key`
- **Token lifetime**: 24 hours (default)
- **Token payload**: `user_id`, `role`, `iat`, `exp`

---

## Channel Configuration

### WhatsApp (3 Backends)

WhatsApp supports three backends, switchable at runtime:

#### Browser/Puppeteer Backend

```json
{
  "whatsapp": {
    "backend": "browser",
    "allowed_user_ids": ["5491155551234@c.us"]
  }
}
```

Uses a headless browser to connect to WhatsApp Web. Requires QR code scanning.

#### Baileys/Node.js Backend

```json
{
  "whatsapp": {
    "backend": "baileys",
    "allowed_user_ids": ["5491155551234@c.us"]
  }
}
```

Uses the Baileys library (Node.js) for a lighter-weight connection. Also requires QR code scanning.

#### Official Cloud API

```json
{
  "whatsapp": {
    "backend": "official",
    "allowed_user_ids": [],
    "official": {
      "phone_number_id": "YOUR_PHONE_NUMBER_ID",
      "access_token": "YOUR_ACCESS_TOKEN",
      "verify_token": "YOUR_VERIFY_TOKEN"
    }
  }
}
```

Uses the official WhatsApp Cloud API via Meta Business Suite. Requires a Meta developer account and approved business phone number.

### Telegram

```json
{
  "telegram": {
    "bot_token": "123456:ABC-DEF1234...",
    "default_chat_id": "your_chat_id",
    "allowed_user_ids": ["1234567890"],
    "allowed_usernames": ["your_username"],
    "polling_enabled": true,
    "display_name": "Your Name"
  }
}
```

| Field | Description |
|---|---|
| `bot_token` | Token from BotFather (`/newbot` command) |
| `default_chat_id` | Default chat to send proactive messages |
| `allowed_user_ids` | Telegram user IDs allowed to interact (array of strings) |
| `allowed_usernames` | Telegram usernames allowed (alternative to IDs) |
| `polling_enabled` | Start polling automatically on boot |
| `display_name` | Display name for user messages in history |

### Slack

```json
{
  "slack": {
    "bot_token": "xoxb-YOUR-BOT-TOKEN",
    "channel_id": "C0123456789",
    "allowed_user_ids": ["U0123456789"],
    "polling_enabled": true
  }
}
```

| Field | Description |
|---|---|
| `bot_token` | Bot User OAuth Token from Slack App settings |
| `channel_id` | Channel ID to monitor (starts with `C`) |
| `allowed_user_ids` | Slack user IDs allowed to interact (starts with `U`) |
| `polling_enabled` | Start polling automatically on boot |

**Required OAuth Scopes**: `channels:history`, `channels:read`, `chat:write`, `users:read`

### Discord

```json
{
  "discord": {
    "bot_token": "YOUR_BOT_TOKEN",
    "channel_id": "1234567890123456789",
    "guild_id": "9876543210987654321",
    "allowed_user_ids": ["1234567890123456789"],
    "polling_enabled": true
  }
}
```

| Field | Description |
|---|---|
| `bot_token` | Bot token from Discord Developer Portal |
| `channel_id` | Channel snowflake ID to monitor |
| `guild_id` | Server (guild) snowflake ID |
| `allowed_user_ids` | Discord user IDs allowed to interact |
| `polling_enabled` | Start polling automatically on boot |

**Required Bot Intents**: `MESSAGE_CONTENT`, `GUILDS`, `GUILD_MESSAGES`

---

## MCP Server Configuration

Model Context Protocol servers extend CapOS with external tool providers.

```json
{
  "mcp": {
    "servers": [
      {
        "id": "filesystem",
        "transport": "stdio",
        "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
      },
      {
        "id": "web-search",
        "transport": "http",
        "url": "http://localhost:3001/mcp",
        "timeout_ms": 15000
      }
    ],
    "auto_discover_capabilities": false,
    "server_timeout_ms": 10000
  }
}
```

### Server Config Fields

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique server identifier |
| `transport` | `string` | `"stdio"` (subprocess) or `"http"` (network) |
| `command` | `string[]` | Command to start a stdio server |
| `url` | `string` | URL for an HTTP server |
| `timeout_ms` | `integer` | Per-request timeout (overrides global) |

### Global MCP Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `auto_discover_capabilities` | `boolean` | `false` | Auto-register MCP tools as capabilities |
| `server_timeout_ms` | `integer` | `10000` | Default timeout for MCP servers |

---

## A2A Configuration

Agent-to-Agent protocol for delegating tasks to remote AI agents.

```json
{
  "a2a": {
    "enabled": true,
    "server_url": "http://localhost:8000",
    "known_agents": [
      {
        "id": "remote-coder",
        "url": "http://192.168.1.50:8000",
        "name": "Remote Coding Agent",
        "capabilities": ["code_generation", "code_review"]
      }
    ]
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `boolean` | `true` | Enable A2A protocol |
| `server_url` | `string` | `"http://localhost:8000"` | This agent's public URL for incoming A2A requests |
| `known_agents` | `array` | `[]` | List of known remote agents for delegation |

---

## Workspace Configuration

```json
{
  "workspace": {
    "artifacts_path": "C:/Projects/capability-os/artifacts",
    "sequences_path": "C:/Projects/capability-os/sequences"
  }
}
```

Additional workspaces are managed through the API and stored in the workspace registry, not in `settings.json`. Each workspace has:

| Field | Description |
|---|---|
| `id` | Auto-generated unique ID |
| `name` | Human-readable name |
| `path` | Filesystem path |
| `access` | `"read"`, `"write"`, or `"none"` |
| `color` | Hex color for UI display |
| `icon` | Icon identifier |
| `allowed_capabilities` | Which capabilities can operate on this workspace (`"*"` = all) |

---

## Agent Configuration

Custom agents are managed through the API, not `settings.json`. The global agent settings control the default agent loop behavior:

```json
{
  "agent": {
    "enabled": true,
    "max_iterations": 10
  }
}
```

Each custom agent (`AgentConfig`) can override:

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Agent display name |
| `emoji` | `string` | Agent avatar emoji |
| `description` | `string` | What this agent specializes in |
| `system_prompt` | `string` | Custom system prompt |
| `tool_ids` | `string[]` | Restricted tool access |
| `llm_model` | `string` | Override LLM model |
| `language` | `string` | Preferred response language |
| `max_iterations` | `integer` | Override max iterations |
