# Capability OS - Phase 4 Technical README

## Scope
Phase 4 adds only composed v1 capabilities on top of Phase 1-3 foundations.

Implemented composed capabilities:
- `create_project`
- `analyze_project`
- `run_build`
- `run_tests`

No additions beyond scope:
- no frontend
- no integration system runtime/pipeline
- no browser control
- no LLM
- sequential strategy only

## Contracts added
Capability contracts:
- `system/capabilities/contracts/v1/create_project.json`
- `system/capabilities/contracts/v1/analyze_project.json`
- `system/capabilities/contracts/v1/run_build.json`
- `system/capabilities/contracts/v1/run_tests.json`

These contracts run through existing:
- `CapabilityRegistry`
- `CapabilityEngine`
- `StateManager`
- `ObservationLogger`

## Runtime behavior
- `create_project` uses `execution_run_command` + `filesystem_list_directory`.
- `analyze_project` uses `filesystem_list_directory` + `filesystem_read_file` and returns deterministic `analysis_report`.
- `run_build` uses `execution_run_command` with optional `build_command` and fallback safe command.
- `run_tests` uses `execution_run_command` with optional `test_command` and fallback safe command.

## Security
- Workspace isolation remains enforced by existing real tools.
- `execution_run_command` keeps allowlist/timeout/cwd restrictions.
- Outside-workspace paths fail with structured runtime errors.

## Tests
Added:
- `tests/unit/test_phase4_capabilities_composed.py`

Includes:
- unit checks per composed capability contract
- end-to-end execution via `CapabilityEngine`
- outside-workspace rejection tests
- observation/log checks on success and error
- structured output assertions

Run all tests:

```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
