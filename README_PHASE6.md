# Capability OS - Phase 6 Technical README

## Scope
Phase 6 adds automation v1 using reusable sequences of capabilities.

Implemented in this phase:
- `save_sequence`
- `load_sequence`
- `run_sequence`
- Sequence model
- JSON sequence storage inside workspace
- Sequence registry
- Sequence runner integrated with existing `CapabilityEngine`

Out of scope (kept as requested):
- no integration system
- no browser control
- no LLM
- no new domains/naming conventions
- no non-sequential strategy modes

## Architecture

### Core sequence components
- `system/core/sequences/model.py`
  - sequence definition + step validation
  - explicit variable validation for:
    - `inputs.*`
    - `steps.<step_id>.outputs.*`
    - `state.*`
- `system/core/sequences/storage.py`
  - persistence in `workspace/sequences/*.json`
- `system/core/sequences/registry.py`
  - sequence validation, save/load, registry facade
- `system/core/sequences/runner.py`
  - executes sequence steps via existing `CapabilityEngine`
  - carries shared state across steps
  - emits canonical runtime model via `ObservationLogger`

### API integration
- `system/core/ui_bridge/api_server.py`
  - `/execute` now supports:
    - `save_sequence`
    - `load_sequence`
    - `run_sequence`
  - execution responses keep:
    - `execution_id`
    - canonical `runtime`
    - `final_output`
    - structured errors (`error_code`, `error_message`)

## Capability contracts added
- `system/capabilities/contracts/v1/save_sequence.json`
- `system/capabilities/contracts/v1/load_sequence.json`
- `system/capabilities/contracts/v1/run_sequence.json`

These are visible from the existing UI list and executable through existing backend endpoints.

## Sequence model
- Required:
  - `id`
  - `name`
  - `steps[]`
- Each step requires:
  - `step_id`
  - `capability`
  - `inputs`

## Storage
- Location: `workspace/sequences/`
- Format: JSON
- Filename: `<sequence_id>.json`

## Runtime behavior (`run_sequence`)
- Input:
  - `sequence_id` or `sequence_definition`
  - optional `inputs` for `inputs.*` template root
- Execution:
  - resolves explicit variables per step
  - executes each step capability through `CapabilityEngine`
  - updates shared `state` with each step output
  - stops on first failing step
- Output:
  - aggregated `final_output` with per-step outputs
  - canonical runtime model and logs

## Tests
- `tests/unit/test_phase6_sequences.py`
  - save sequence
  - load sequence
  - run sequence success
  - run sequence failure on intermediate step
  - explicit variable resolution
  - integration with capability engine
  - observation/log events

Run full backend tests:
```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
