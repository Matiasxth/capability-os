# Capability OS - Phase 7 Technical README

## Scope
Phase 7 adds deterministic operational capabilities for code modification and error diagnosis:

- `modify_code`
- `diagnose_error`

Out of scope (kept as requested):
- no LLM
- no integration system
- no browser control
- no changes to `capability_engine`, `tool_runtime`, `state_manager`, `observation_logger`
- sequential strategy only

## Implemented Components

### Capability contracts
- `system/capabilities/contracts/v1/modify_code.json`
- `system/capabilities/contracts/v1/diagnose_error.json`

### Deterministic capability executor (Phase 7)
- `system/capabilities/implementations/phase7_capabilities.py`

This executor keeps logic deterministic and outside the generic engine, while still reusing existing capabilities via `CapabilityEngine` when needed.

### Sequence integration
- `system/core/sequences/runner.py` now supports an optional capability execution callback.
- API bridge wires `run_sequence` to execute Phase 7 capabilities inside sequences.

### API integration
- `system/core/ui_bridge/api_server.py`
  - `/execute` now supports direct execution for:
    - `modify_code`
    - `diagnose_error`
  - `run_sequence` can invoke them in sequence steps.

## Functional Behavior

### modify_code
- Uses `filesystem_read_file` and `filesystem_write_file` through existing `read_file`/`write_file` capabilities.
- Modes:
  - `replace`: full replacement with `modification`
  - `append`: `current_content + modification`
- Validates `file_path` via workspace-safe read/write path checks.
- Returns:
  - `status`
  - `path`
- Emits canonical runtime events/logs.

### diagnose_error
- Deterministically parses `error_output`.
- Detects:
  - `ModuleNotFoundError`
  - `SyntaxError`
  - `command not found` (including Windows wording)
  - `permission denied` (including Spanish wording)
- Fallback for unrecognized patterns.
- Returns:
  - `diagnosis.error_type`
  - `diagnosis.message`
  - `diagnosis.possible_cause`
  - `diagnosis.suggested_action`
- Emits canonical runtime events/logs.

## Tests
- `tests/unit/test_phase7_modify_code_and_diagnose_error.py`
  - modify_code replace/append/errors
  - diagnose_error detections and fallback
  - integration with `CapabilityEngine`
  - integration with `run_sequence`
  - observation/log checks

Run full backend tests:
```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
