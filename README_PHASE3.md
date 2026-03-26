# Capability OS - Phase 3 Technical README

## Scope
Phase 3 implements minimum real tools and base capabilities for v1, keeping the architecture constraints from the spec:

Implemented real tools:
- `filesystem_read_file`
- `filesystem_write_file`
- `filesystem_list_directory`
- `execution_run_command`
- `network_http_get`

Implemented base capabilities:
- `read_file`
- `write_file`
- `list_directory`
- `execute_command`
- `fetch_url`

Out of scope in this phase:
- frontend
- integration system/pipeline
- browser control
- non-sequential strategies

## Contracts
Tool contracts are in:
- `system/tools/contracts/v1/*.json`

Capability contracts are in:
- `system/capabilities/contracts/v1/*.json`

All contracts are validated through existing Phase 1 schemas/registries.

## Runtime integration
- Real tool implementations are in `system/tools/implementations/phase3_tools.py`.
- Registration helper: `register_phase3_real_tools(...)` in `system/tools/runtime/phase3_registration.py`.
- Execution still flows through existing Phase 2 components:
  - `CapabilityEngine`
  - `ToolRuntime`
  - `StateManager`
  - `ObservationLogger`

## Security behavior
- Strict workspace isolation for filesystem and execution tools.
- `execution_run_command` enforces allowlist and timeout from tool contract.
- `cwd` is forced inside workspace.
- Clear errors are raised and captured by observation logger in runtime model.

## Tests
Added:
- `tests/unit/test_phase3_tools_real.py`
- `tests/unit/test_phase3_capabilities_e2e.py`

Run full suite:

```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```
