# Channels and Integrations

Complete guide for integrating Capability OS with external messaging platforms. Channels allow users to interact with their AI agent from WhatsApp, Telegram, Slack, Discord, and more.

---

## Table of Contents

- [Architecture](#architecture)
- [WhatsApp](#whatsapp)
  - [Browser/Puppeteer Backend](#browserpuppeteer-backend)
  - [Baileys/Node.js Backend](#baileysnodejs-backend)
  - [Official Cloud API Backend](#official-cloud-api-backend)
  - [Switching Backends](#switching-backends)
- [Telegram](#telegram)
- [Slack](#slack)
- [Discord](#discord)
- [Planned Channels](#planned-channels)
- [Adding a Custom Channel](#adding-a-custom-channel)

---

## Architecture

### ChannelPlugin Base

Every channel implements the `ChannelPlugin` protocol from `system/sdk/plugin_types.py`:

```python
class ChannelPlugin(BasePlugin, Protocol):
    @property
    def channel_id(self) -> str: ...
    def get_status(self) -> dict[str, Any]: ...
    def configure(self, settings: dict[str, Any]) -> None: ...
    def send_message(self, target: str, text: str, **kw: Any) -> dict[str, Any]: ...
    def register_routes(self, router: Any) -> None: ...
```

### Polling Pattern

All channels use a polling-based architecture for incoming messages:

```
External Service  -->  PollingWorker (background thread)
                            |
                       IntentInterpreter (classify intent)
                            |
                       CapabilityEngine (execute capability)
                            |
                       EventBus.emit("<channel>_message")
                            |
                       WebSocket --> Frontend UI
```

1. **PollingWorker** runs in a background thread, periodically checking for new messages
2. Incoming messages are classified by the **IntentInterpreter**
3. If a capability is identified, the **CapabilityEngine** executes it
4. Events are emitted through the **EventBus** for real-time UI updates
5. Responses are sent back through the channel connector

### Auto-Reply Flow

When `polling_enabled` is `true`:

1. New message detected by the polling worker
2. Message filtered by `allowed_user_ids` / `allowed_usernames`
3. Intent interpreted via LLM
4. Capability executed (if applicable) or chat response generated
5. Response sent back to the channel
6. Execution logged to history

### Plugin Lifecycle

Each channel plugin follows the standard lifecycle:

```
initialize(ctx)     # Create connector, load settings
    |
register_routes()   # Register HTTP endpoints for status/configuration
    |
start()             # Start polling worker (if polling_enabled)
    |
stop()              # Stop polling worker, close connections
```

---

## WhatsApp

**Plugin ID**: `capos.channels.whatsapp`
**File**: `system/plugins/channels/whatsapp/plugin.py`

WhatsApp is the most feature-rich channel with three interchangeable backends. The `WhatsAppBackendManager` allows switching between backends at runtime.

### Browser/Puppeteer Backend

The original backend. Uses a headless browser to interact with WhatsApp Web.

#### Setup

1. Start CapOS normally
2. Navigate to **Control Center > Integrations > WhatsApp**
3. Click **Start WhatsApp** (this launches the browser backend)
4. Scan the QR code displayed in the UI with your phone's WhatsApp app
5. Once connected, the status will show "connected"

#### Configuration

```json
{
  "whatsapp": {
    "backend": "browser",
    "allowed_user_ids": ["5491155551234@c.us"]
  }
}
```

#### How it Works

- Launches a Puppeteer/Playwright-controlled Chrome instance
- Navigates to `web.whatsapp.com`
- Generates a QR code for phone linking
- Polls the DOM for incoming messages using CSS selectors
- Sends messages by typing into the WhatsApp Web interface
- Selectors are configurable via `system/integrations/installed/whatsapp_web_connector/config/selectors.json`

#### Pros and Cons

- **Pros**: No API key needed, free, works with personal WhatsApp
- **Cons**: Requires QR scan, browser resource usage, may break if WhatsApp Web updates selectors

---

### Baileys/Node.js Backend

A lighter-weight alternative using the Baileys library (reverse-engineered WhatsApp Web protocol).

#### Setup

1. Ensure Node.js is installed
2. Configure backend in settings:

```json
{
  "whatsapp": {
    "backend": "baileys",
    "allowed_user_ids": ["5491155551234@c.us"]
  }
}
```

3. Start WhatsApp from the Control Center
4. Scan the QR code with your phone

#### How it Works

- Runs a Node.js subprocess using the Baileys library
- Communicates with the Python backend via IPC
- Handles WhatsApp protocol natively (no browser needed)
- Persists session data for reconnection

#### Pros and Cons

- **Pros**: Lower resource usage than browser, faster message delivery
- **Cons**: Requires Node.js, uses unofficial protocol

---

### Official Cloud API Backend

Uses the official WhatsApp Business Cloud API from Meta.

#### Setup

1. Create a Meta Business account at [business.facebook.com](https://business.facebook.com)
2. Create an app in the [Meta Developer Portal](https://developers.facebook.com)
3. Add the WhatsApp product to your app
4. Get your Phone Number ID and Access Token from the WhatsApp section
5. Set a Verify Token for webhook validation

```json
{
  "whatsapp": {
    "backend": "official",
    "official": {
      "phone_number_id": "123456789012345",
      "access_token": "EAAxxxxxxxxxxxxxxxx",
      "verify_token": "my_custom_verify_token"
    }
  }
}
```

#### How it Works

- Sends messages via the official Graph API (`POST https://graph.facebook.com/v18.0/<phone_number_id>/messages`)
- Receives messages via webhooks (requires a public URL)
- Supports templates, interactive messages, and media

#### Pros and Cons

- **Pros**: Official, reliable, supports business features, no QR scanning
- **Cons**: Requires Meta Business account, costs per conversation, approval process for templates

---

### Switching Backends

Switch backends at runtime via the API:

```bash
# Via API
curl -X POST http://localhost:8000/integrations/whatsapp/switch-backend \
  -H "Content-Type: application/json" \
  -d '{"backend": "baileys"}'
```

Or through the Control Center UI:

1. Go to **Integrations > WhatsApp**
2. Click **Backends** dropdown
3. Select the desired backend
4. The system will stop the current backend and start the new one

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/whatsapp/session-status` | Get connection status |
| `GET` | `/integrations/whatsapp/qr` | Get QR code for scanning |
| `GET` | `/integrations/whatsapp/backends` | List available backends |
| `GET` | `/integrations/whatsapp/reply-status` | Reply worker status |
| `GET` | `/integrations/whatsapp/debug` | Debug information |
| `GET` | `/integrations/whatsapp/debug-chats` | List active chats |
| `POST` | `/integrations/whatsapp/start` | Start WhatsApp connection |
| `POST` | `/integrations/whatsapp/stop` | Stop WhatsApp connection |
| `POST` | `/integrations/whatsapp/configure` | Update configuration |
| `POST` | `/integrations/whatsapp/switch-backend` | Switch active backend |
| `POST` | `/integrations/whatsapp/close-session` | Close current session |
| `GET` | `/integrations/whatsapp/selectors/health` | Check selector health |
| `POST` | `/integrations/whatsapp/selectors` | Override CSS selectors |

---

## Telegram

**Plugin ID**: `capos.channels.telegram`
**File**: `system/plugins/channels/telegram/plugin.py`

### Setup

1. **Create a bot** with [BotFather](https://t.me/BotFather):
   - Send `/newbot` to BotFather
   - Choose a name and username
   - Copy the bot token

2. **Get your Chat ID**:
   - Send a message to your bot
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Find your `chat.id` in the response

3. **Get your User ID**:
   - Send a message to [@userinfobot](https://t.me/userinfobot)
   - It will reply with your user ID

4. **Configure** in `settings.json`:

```json
{
  "telegram": {
    "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    "default_chat_id": "1234567890",
    "allowed_user_ids": ["1234567890"],
    "allowed_usernames": [],
    "polling_enabled": true,
    "display_name": "Your Name"
  }
}
```

5. **Start polling** from Control Center or set `polling_enabled: true` for auto-start.

### Security

- Only messages from users in `allowed_user_ids` or `allowed_usernames` are processed
- All other messages are silently ignored
- The `display_name` is used in execution history for attribution

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/telegram/status` | Connection and config status |
| `POST` | `/integrations/telegram/configure` | Update Telegram settings |
| `POST` | `/integrations/telegram/test` | Send a test message |
| `POST` | `/integrations/telegram/polling/start` | Start polling worker |
| `POST` | `/integrations/telegram/polling/stop` | Stop polling worker |
| `GET` | `/integrations/telegram/polling/status` | Polling worker status |

---

## Slack

**Plugin ID**: `capos.channels.slack`
**File**: `system/plugins/channels/slack/plugin.py`

### Setup

1. **Create a Slack App**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps)
   - Click **Create New App** > **From scratch**
   - Choose a name and workspace

2. **Configure OAuth Scopes**:
   - Navigate to **OAuth & Permissions**
   - Add Bot Token Scopes:
     - `channels:history` -- Read message history
     - `channels:read` -- View channel info
     - `chat:write` -- Send messages
     - `users:read` -- View user info

3. **Install to Workspace**:
   - Click **Install to Workspace** and authorize
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`)

4. **Get Channel ID**:
   - Right-click the channel in Slack > **View channel details**
   - The Channel ID is at the bottom (starts with `C`)

5. **Get User IDs**:
   - Click a user's profile in Slack
   - The User ID is in the **More** menu (starts with `U`)

6. **Configure** in `settings.json`:

```json
{
  "slack": {
    "bot_token": "xoxb-YOUR-SLACK-BOT-TOKEN",
    "channel_id": "C0123456789",
    "allowed_user_ids": ["U0123456789"],
    "polling_enabled": true
  }
}
```

7. **Invite the bot** to the channel: `/invite @YourBotName`

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/slack/status` | Connection and config status |
| `POST` | `/integrations/slack/configure` | Update Slack settings |
| `POST` | `/integrations/slack/test` | Send a test message |
| `POST` | `/integrations/slack/polling/start` | Start polling worker |
| `POST` | `/integrations/slack/polling/stop` | Stop polling worker |
| `GET` | `/integrations/slack/polling/status` | Polling worker status |

---

## Discord

**Plugin ID**: `capos.channels.discord`
**File**: `system/plugins/channels/discord/plugin.py`

### Setup

1. **Create a Discord Application**:
   - Go to [discord.com/developers/applications](https://discord.com/developers/applications)
   - Click **New Application** and give it a name

2. **Create a Bot**:
   - Navigate to the **Bot** section
   - Click **Add Bot**
   - Enable **Message Content Intent** under Privileged Gateway Intents
   - Copy the bot **Token**

3. **Enable Required Intents**:
   - **MESSAGE_CONTENT** -- Read message content
   - **GUILDS** -- Access server info
   - **GUILD_MESSAGES** -- Receive message events

4. **Invite Bot to Server**:
   - Go to **OAuth2 > URL Generator**
   - Select scopes: `bot`
   - Select permissions: `Send Messages`, `Read Message History`, `View Channels`
   - Open the generated URL and add the bot to your server

5. **Get IDs** (enable Developer Mode in Discord Settings > Advanced):
   - **Guild ID**: Right-click server name > Copy Server ID
   - **Channel ID**: Right-click channel > Copy Channel ID
   - **User ID**: Right-click user > Copy User ID

6. **Configure** in `settings.json`:

```json
{
  "discord": {
    "bot_token": "YOUR-DISCORD-BOT-TOKEN",
    "channel_id": "1234567890123456789",
    "guild_id": "9876543210987654321",
    "allowed_user_ids": ["1234567890123456789"],
    "polling_enabled": true
  }
}
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/discord/status` | Connection and config status |
| `POST` | `/integrations/discord/configure` | Update Discord settings |
| `POST` | `/integrations/discord/test` | Send a test message |
| `POST` | `/integrations/discord/polling/start` | Start polling worker |
| `POST` | `/integrations/discord/polling/stop` | Stop polling worker |
| `GET` | `/integrations/discord/polling/status` | Polling worker status |

---

## Planned Channels

The following channels have UI cards ready in the Control Center but backend plugins are planned for future sprints:

| Channel | Status | Notes |
|---|---|---|
| **Signal** | UI ready, backend planned | Signal Protocol integration via signal-cli |
| **Matrix** | UI ready, backend planned | Matrix.org protocol via matrix-nio |
| **Microsoft Teams** | UI ready, backend planned | Microsoft Graph API integration |
| **Email** | UI ready, backend planned | IMAP/SMTP polling and sending |
| **Webhook** | UI ready, backend planned | Generic HTTP webhook endpoint for custom integrations |

These channels follow the same `ChannelPlugin` architecture. Once the backend plugin is built, the existing UI card will connect automatically.

---

## Adding a Custom Channel

To add a new channel to Capability OS, you need three pieces:

### 1. Backend Plugin

Create a new plugin directory under `system/plugins/channels/`:

```
system/plugins/channels/my_channel/
    __init__.py
    capos-plugin.json
    plugin.py
```

#### `capos-plugin.json`

```json
{
  "id": "capos.channels.my_channel",
  "name": "My Channel",
  "version": "1.0.0",
  "dependencies": ["capos.core.settings"],
  "entry_point": "plugin:create_plugin",
  "permissions": [
    "network.http",
    "event_bus.emit",
    "agents.execute",
    "capabilities.execute"
  ],
  "events_emitted": ["my_channel_message"],
  "tags": ["builtin", "channel"]
}
```

#### `plugin.py`

```python
from __future__ import annotations
from typing import Any
from system.sdk.contracts import (
    CapabilityEngineContract,
    ExecutionHistoryContract,
    IntentInterpreterContract,
)


class MyChannelPlugin:
    plugin_id = "capos.channels.my_channel"
    plugin_name = "My Channel"
    version = "1.0.0"
    dependencies = ["capos.core.settings"]

    def __init__(self):
        self._ctx = None
        self._settings = {}
        self._connector = None
        self._polling_worker = None

    def initialize(self, ctx):
        self._ctx = ctx
        self._settings = ctx.plugin_settings(self.plugin_id)
        # Initialize your connector here

    def register_routes(self, router):
        router.add("GET", "/integrations/my-channel/status", self._handle_status)
        router.add("POST", "/integrations/my-channel/configure", self._handle_configure)

    def start(self):
        if not self._settings.get("polling_enabled", False):
            return
        # Start polling worker here

    def stop(self):
        if self._polling_worker:
            self._polling_worker.stop()

    @property
    def channel_id(self):
        return "my_channel"

    def get_status(self):
        return {"channel": self.channel_id, "configured": True, "connected": True}

    def configure(self, settings):
        self._settings.update(settings)

    def send_message(self, target, text, **kw):
        # Send message through your channel
        return {"status": "ok"}

    def _handle_status(self, request):
        return self.get_status()

    def _handle_configure(self, request):
        body = request.get("body", {})
        self.configure(body)
        return {"status": "ok"}


def create_plugin():
    return MyChannelPlugin()
```

### 2. Frontend Channel Card

Add a channel card in the Control Center integrations section. The frontend uses a `channelDomain` mapping in the SDK to route events:

```javascript
// In the channel card component
import sdk from "../../sdk";
import { EVENTS } from "../../sdk/eventTypes";

// Listen for messages from your channel
sdk.events.on("my_channel_message", (event) => {
  console.log("New message:", event.data);
});
```

### 3. Event Type Registration

Add your event type to `src/sdk/eventTypes.js`:

```javascript
export const EVENTS = {
  // ... existing events ...
  MY_CHANNEL_MESSAGE: "my_channel_message",
};
```

And add it to `HISTORY_EVENTS` if incoming messages should trigger history reloads:

```javascript
export const HISTORY_EVENTS = [
  // ... existing events ...
  EVENTS.MY_CHANNEL_MESSAGE,
];
```
