# WebSocket — Pending Items for Future Plan

Items identified during the WebSocket event-emission audit (2026-03-28).
These require deeper work beyond handler-level changes.

---

## 1. `telegram_message` event — emit from polling worker

**Status:** Frontend listens for `telegram_message` but no backend emits it.

**What's needed:** The Telegram polling worker (`system/integrations/installed/telegram_bot_connector/`)
should emit `event_bus.emit("telegram_message", {...})` each time it receives
an incoming message from the Telegram Bot API.

**Why it matters:** Without this, the Workspace UI only learns about new Telegram
messages via polling interval (5–30 s), not real-time push.

---

## 2. `whatsapp_message` event — emit from WhatsApp connector

**Status:** No `whatsapp_message` event exists yet.

**What's needed:** The WhatsApp connector/worker (`system/whatsapp_worker/`,
`system/integrations/installed/whatsapp_web_connector/connector.py`) should emit
`event_bus.emit("whatsapp_message", {...})` when a new incoming message arrives.

**Why it matters:** Same real-time gap as Telegram — the frontend can react
instantly if the backend pushes the event.

---

## 3. ControlCenter.jsx — WebSocket integration

**Status:** Only `Workspace.jsx` consumes WebSocket events.
`ControlCenter.jsx` still relies purely on manual refresh / polling.

**What's needed:** Add `useWebSocket` hook to ControlCenter so that
`settings_updated`, `integration_changed`, `mcp_changed`, `growth_update`,
`workspace_changed`, and `browser_changed` events auto-refresh the relevant
panels in real time.

---

## 4. Event catalog documentation

**Status:** Event types are scattered across handler files with no central reference.

**What's needed:** A single `docs/events.md` or a JSON schema listing all event
types, their payloads, and which handler emits each one. This helps frontend
devs know what to subscribe to.

---

## 5. `error` event — emit on unhandled handler errors

**Status:** Frontend handles `error` events with toast, but no handler emits them.

**What's needed:** The API server's top-level error handler should emit
`event_bus.emit("error", {"message": str(exc)})` for 500-level errors so the
frontend can show real-time error toasts without waiting for a polling cycle.

---

## Priority order

1. Telegram message event (high — most requested integration)
2. ControlCenter WS integration (high — immediate UX improvement)
3. Error event emission (medium — improves debugging experience)
4. WhatsApp message event (medium — depends on connector maturity)
5. Event catalog docs (low — nice-to-have for maintainability)
