# Capability OS - Phase 8 Technical README

## Scope
Phase 8 adds a natural-language interpretation layer on top of existing deterministic execution.

Implemented components:
- `intent_interpreter`
- `input_extractor`
- `capability_matcher`
- `llm_client` (OpenAI-compatible API + Ollama local)
- base prompts for restricted intent parsing

Out of scope (kept as requested):
- no direct LLM execution
- no LLM inside capability runtime/engine
- no variable resolution by LLM
- no new capabilities/tools/domains
- no changes to `capability_engine`, `tool_runtime`, `state_manager`, `observation_logger`

## Architecture

### New interpretation layer
- `system/core/interpretation/prompts.py`
- `system/core/interpretation/llm_client.py`
- `system/core/interpretation/input_extractor.py`
- `system/core/interpretation/capability_matcher.py`
- `system/core/interpretation/intent_interpreter.py`

### Behavior
- `intent_interpreter` receives user text and calls `llm_client`.
- LLM response is parsed as JSON only.
- `input_extractor` normalizes/cleans values and checks structure.
- `capability_matcher` validates capability/sequence targets against registry.
- Final output is always suggestion-only:
  - `suggest_only: true`

Output format:
- capability suggestion:
  - `type: "capability"`
  - `capability`
  - `inputs`
- sequence suggestion:
  - `type: "sequence"`
  - `steps[]`
- unknown:
  - `type: "unknown"`

## LLM providers
- External API (`LLM_PROVIDER=openai`) via OpenAI-compatible `/chat/completions`
- Local model (`LLM_PROVIDER=ollama`) via `/api/generate`
- Tests use injected mock adapter (no real network dependency).

## Backend integration
- `system/core/ui_bridge/api_server.py`
- New endpoint:
  - `POST /interpret`
  - Request: `{ "text": "..." }`
  - Response includes:
    - `suggest_only`
    - `suggestion`
    - `error`

No automatic execution is triggered from `/interpret`.

## UI integration
- Existing React UI now includes:
  - free-text input
  - "Interpretar" action
  - suggestion panel
  - explicit suggestion type indicator (`capability | sequence | unknown`)
  - sequence summary (`step count` + detected capabilities list)
  - explicit confirmation button
- Execution only happens when user confirms suggestion.

## Hardening update
- Sequence suggestions now validate each step against capability contracts:
  - capability must exist in registry
  - unknown step input fields are rejected
  - required inputs declared in contracts must be present
- `suggest_only` behavior remains unchanged (`true` by default).

## Tests
- Backend/unit:
  - `tests/unit/test_phase8_intent_interpreter.py`
  - `tests/unit/test_phase8_intent_api.py`
- Frontend (mocked integration):
  - `system/frontend/app/src/App.phase8.test.jsx`

Run tests:
```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
cd system/frontend/app
npm test
```
