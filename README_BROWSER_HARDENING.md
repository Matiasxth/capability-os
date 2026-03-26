# Capability OS - Browser Hardening (Worker IPC Isolation)

## Scope
This hardening phase isolates the Browser Control Layer in an external worker process.
The backend process no longer creates or stores Playwright objects directly.

## What Changed
- Added browser worker process under `system/browser_worker/`.
- Added formal IPC client/protocol under `system/tools/browser_ipc/`.
- Updated browser tool implementation (`phase9_browser_tools.py`) to use IPC calls only.
- Kept browser tool contracts and browser capability contracts unchanged.
- Kept `capability_engine`, `tool_runtime`, `state_manager`, and `observation_logger` untouched.

## IPC Protocol
Every message includes:
- `protocol_version`
- `message_type` (`command`, `response`, `event`, `health`, `control`)
- `request_id`
- `timestamp`
- `source`
- `target`
- `action`
- `session_id`
- `payload`
- `metadata` (`timeout_ms`, `trace_id`, response `duration_ms`)

Transport:
- subprocess + stdin/stdout
- newline-delimited JSON
- structured response correlation by `request_id`

## Worker Responsibilities
- Initialize Playwright runtime (inside worker process only)
- Maintain browser sessions in worker memory
- Execute browser actions
- Return structured success/error responses
- Emit worker events

## Error Handling
Structured error codes include:
- `browser_worker_unavailable`
- `browser_worker_timeout`
- `session_not_available`
- `browser_action_not_supported`
- `playwright_not_installed`
- `navigation_failed`

## Lifecycle
- Worker starts on demand when first browser tool call arrives.
- Worker failure is detected and surfaced.
- Automatic restart is intentionally not implemented in this phase.
- Health/control message types are supported (`ping`, `shutdown`).

## Compatibility
Still works with existing contracts and capabilities:
- `open_browser`
- `navigate_web`
- `read_web_page`
- `interact_with_page`
- WhatsApp connector capabilities (through same browser tools)

## Tests
Added/updated tests:
- `tests/unit/test_phase9_browser_tools.py`
- `tests/unit/test_phase9_browser_capabilities.py`
- `tests/unit/test_browser_hardening_backend.py`
- `tests/unit/test_browser_ipc_client.py`
- `tests/unit/test_browser_worker_protocol.py`
- `tests/unit/test_browser_worker_session_manager.py`
- `tests/unit/test_browser_dom_introspection.py`
- `tests/unit/test_browser_element_registry.py`

## DOM Introspection And Interaction Layer
Implemented inside worker only:
- `dom_introspection.py` extracts interactive DOM candidates.
- `element_mapper.py` normalizes candidates to the standard element model.
- `element_registry.py` keeps per-session `element_id` mappings.

New worker/browser actions:
- `browser_list_interactive_elements`
- `browser_click_element_by_id`
- `browser_type_into_element`
- `browser_highlight_element`

Element IDs:
- Format `el_001`, `el_002`, ...
- Unique per session
- Stable for unchanged snapshot
- Invalidated on navigation/switch tab/session close

Structured element interaction errors:
- `element_not_found`
- `element_not_visible`
- `element_not_interactable`
- `element_stale`
- `element_out_of_view`
