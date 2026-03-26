# Capability OS - Phase 9 Technical README

## Scope
Phase 9 introduces a reusable and secure Browser Control Layer integrated with current contracts, registries, runtime, and capability execution.

Implemented in this phase:
- Browser tools:
  - `browser_open_session`
  - `browser_close_session`
  - `browser_navigate`
  - `browser_click_element`
  - `browser_type_text`
  - `browser_read_text`
  - `browser_wait_for_selector`
  - `browser_take_screenshot`
  - `browser_list_tabs`
  - `browser_switch_tab`
- Browser capabilities:
  - `open_browser`
  - `navigate_web`
  - `read_web_page`
  - `interact_with_page`

Out of scope (kept as requested):
- No WhatsApp connector or specific external integrations
- No advanced browser automation flows beyond base layer
- No LLM usage inside browser runtime
- No changes to `capability_engine`, `state_manager`, or `observation_logger` logic

## Playwright Encapsulation
- Playwright is isolated inside `PlaywrightBrowserEngineSession`.
- Tools call `BrowserSessionManager`, not Playwright directly.
- Sessions are managed by `session_id` in memory with `active_session_id` fallback.
- Tabs and active tab state are managed per session.
- Errors are raised as structured `BrowserToolError` payloads.

### Backward compatibility aliases
- Legacy aliases remain available and resolve internally to canonical tool IDs:
  - `browser_click` -> `browser_click_element`
  - `browser_type` -> `browser_type_text`
  - `browser_wait_for` -> `browser_wait_for_selector`
  - `browser_screenshot` -> `browser_take_screenshot`
- Deprecation note: new contracts and strategies should use canonical IDs.

## Security Model
- Screenshot paths are always resolved inside workspace.
- URL validation enforces `http/https`.
- Timeout handling is explicit per tool.
- Session validation is strict (`session_not_found` for invalid sessions).

## Session Policy
- Every browser tool accepts optional `session_id`.
- Resolution order:
  1. use explicit `session_id` when provided
  2. otherwise use `active_session_id`
  3. if no session is available, return structured `session_not_available` error
- Multiple sessions remain supported concurrently.

## Capability Behavior
- `open_browser` -> `browser_open_session`
- `navigate_web` -> `browser_navigate`
- `read_web_page` -> `browser_read_text`
- `interact_with_page` -> sequential `browser_wait_for_selector -> browser_type_text -> browser_click_element`

## Tests
- `tests/unit/test_phase9_browser_tools.py`
  - session lifecycle
  - navigation/read
  - screenshot workspace isolation
  - selector errors
  - tab list/switch
- `tests/unit/test_phase9_browser_capabilities.py`
  - contract validation
  - capability execution via `CapabilityEngine`
  - success/error observation logs

Notes:
- Tests use a fake browser engine abstraction to avoid fragile UI/browser dependencies.
- Runtime keeps compatibility with existing phases and contracts.
