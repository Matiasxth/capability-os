# Capability OS - Phase 5 Technical README

## Scope
Phase 5 adds a minimal operational UI layer over the existing Phase 1-4 foundation:

- Local backend UI bridge API (Python)
- Minimal React frontend to browse and execute capabilities
- Execution status, events/logs, final output and error visualization

Out of scope (kept as requested):
- no integration system runtime/pipeline
- no browser control
- no LLM features
- no new capability/tool/domain/state naming
- sequential strategy only

## Backend UI Bridge

### Module
- `system/core/ui_bridge/api_server.py`

### Design
- Uses existing registries and contracts from disk:
  - `CapabilityRegistry`
  - `ToolRegistry`
- Uses existing runtime stack:
  - `CapabilityEngine`
  - `ToolRuntime`
  - Phase 3 real tool registration (`register_phase3_real_tools`)
- Keeps in-memory execution records for querying runtime and events by `execution_id`.
- Returns canonical runtime model from `ObservationLogger`.

### Endpoints
- `GET /capabilities`
- `GET /capabilities/{capability_id}`
- `POST /execute`
- `GET /executions/{execution_id}`
- `GET /executions/{execution_id}/events`

### Error handling
- Structured API errors:
  - `status`
  - `error_code`
  - `error_message`
  - `details`
- Execution failures from engine keep runtime model consistency and are stored/queryable.

## Frontend UI (React)

### App location
- `system/frontend/app`

### Main features
- Capabilities list grouped by `domain`
- Capability detail:
  - `name`, `id`, `description`, `domain`, `type`
  - dynamic inputs (required/optional) from contract
- Execute action via backend API
- Execution panel shows:
  - `execution_id`
  - `status`
  - `current_step`
  - `started_at`
  - `ended_at`
  - `duration_ms`
  - `failed_step`
  - `final_output`
  - `error_code`, `error_message`
- Events panel shows:
  - `execution_started`
  - `capability_resolved`
  - `validation_passed`
  - `step_started`
  - `step_succeeded`
  - `step_failed`
  - `execution_finished`

### Status visibility mapping
UI maps internal states to visible domain states according to spec section 26.3:
- `available | ready -> listo`
- `not_configured -> no configurado`
- `preparing -> limitado`
- `running -> ejecutando`
- `error -> error`
- `experimental -> experimental`
- `disabled -> deshabilitado`

## Tests

### Backend tests
- `tests/unit/test_phase5_ui_bridge_api.py`
- Covers endpoint behavior, execution retrieval, events retrieval and structured errors.

### Frontend tests
- `system/frontend/app/src/App.test.jsx`
- Covers:
  - capabilities rendering
  - dynamic form rendering
  - execution flow with mocked API
  - visible UI error handling

## Run

### Start backend API
```bash
py -m system.core.ui_bridge.api_server
```

### Start frontend
```bash
cd system/frontend/app
npm install
npm run dev
```

### Run frontend tests
```bash
cd system/frontend/app
npm test
```

### Run backend/unit tests
```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
