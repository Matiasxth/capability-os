# Capability OS - Phase 10 Technical README

## Scope
Phase 10 introduces the first real connector: **WhatsApp Web Connector v1** in **assisted mode** over the existing Browser Control Layer.

Implemented in this phase:
- Integration manifest: `whatsapp_web_connector` (`web_app`)
- Connector-specific selectors/config in external JSON
- Connector logic isolated from generic browser tools
- WhatsApp capabilities:
  - `open_whatsapp_web`
  - `wait_for_whatsapp_login`
  - `search_whatsapp_chat`
  - `read_whatsapp_messages`
  - `send_whatsapp_message`
  - `list_whatsapp_visible_chats`
- Backend execution integration through a dedicated Phase 10 capability executor
- Minimal UI visibility improvement for `login_state` values

## Assisted Login Policy
- Login remains **manual via QR**.
- The system only detects and reports:
  - `qr_visible`
  - `authenticated`
  - `timeout`
- No QR automation, no API-based auth, and no bypass logic.

## Architecture Separation
- Generic browser behavior remains in Phase 9 browser tools/runtime.
- WhatsApp-specific behavior lives in:
  - `system/integrations/installed/whatsapp_web_connector/config/selectors.json`
  - `system/integrations/installed/whatsapp_web_connector/connector.py`
- Capability execution orchestration is implemented in:
  - `system/capabilities/implementations/phase10_whatsapp_capabilities.py`

## Safety and Limits
- Uses existing browser session model (`session_id` / active session fallback).
- Explicit error handling for missing selectors and send failures.
- Message reading is intentionally limited to **visible messages only** (`scope=visible_only`).
- No full-history extraction in v1.

## Tests
- Connector/capability unit tests with mocked browser layer:
  - `tests/unit/test_phase10_whatsapp_connector.py`
- Schema coverage updated for manifest validation:
  - `tests/unit/test_schema_validation.py`
- Frontend basic visibility check for `login_state`:
  - `system/frontend/app/src/App.test.jsx`

## Out of Scope (kept)
- No WhatsApp/Meta official API integration.
- No automatic QR scanning.
- No advanced browser hacks.
- No LLM inside connector runtime.

