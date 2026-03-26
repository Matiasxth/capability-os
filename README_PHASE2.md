# Capability OS - Phase 2 Technical README

## Scope
Phase 2 implements the minimum runtime layer defined by the spec, on top of Phase 1 contracts/registries.

Implemented components:

- `capability_engine`
- `tool_runtime`
- `state_manager`
- `observation_logger`

Out of scope in this phase:

- frontend
- integration pipeline/runtime
- browser control
- adaptive/conditional execution

## Behavior implemented

### Capability Engine
- Receives `capability_contract + inputs`.
- Validates contract via existing registry/schema layer.
- Validates required inputs (`required=true`).
- Supports only `strategy.mode = sequential`.
- Executes step-by-step with mandatory `step_id`.
- Resolves params via explicit templates only (`inputs`, `state`, `steps.<id>.outputs`, `runtime`).
- Persists outputs by step.
- Updates state and canonical runtime model.
- Returns structured `final_output` and runtime snapshot.

### Tool Runtime
- Validates tool existence via `ToolRegistry`.
- Dispatches to stub handlers by `tool_id`.
- No real system command execution in this phase.

### State Manager
- Stores inputs, mutable state, and step outputs.
- Resolves explicit template variables.
- Fails clearly on implicit/non-existent variables.

### Observation Logger
- Emits and stores spec events:
  - `execution_started`
  - `capability_resolved`
  - `validation_passed`
  - `step_started`
  - `step_succeeded`
  - `step_failed`
  - `execution_finished`
- Maintains canonical runtime model fields, including:
  - `started_at`, `ended_at`, `duration_ms`
  - `status`, `failed_step`
  - `error_code`, `error_message`
  - `final_output`

## Tests
Unit and integration-minimum tests are under `tests/unit/`.

Run:

```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
