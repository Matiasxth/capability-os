# Capability OS - Phase 1 Technical README

## Scope
Phase 1 implements only the foundational layer defined in the spec:

- Contract schemas:
  - capability_contract.schema.json
  - tool_contract.schema.json
  - integration_manifest.schema.json
- Registries:
  - capability_registry
  - tool_registry
- Unit tests for schema validation, valid load, invalid rejection, and duplicate ID detection.

Out of scope for this phase:

- capability_engine
- tool_runtime
- frontend
- integration pipeline/runtime

## Implemented structure

- system/capabilities/contracts/capability_contract.schema.json
- system/tools/contracts/tool_contract.schema.json
- system/integrations/contracts/integration_manifest.schema.json
- system/shared/schema_validation.py
- system/shared/base_registry.py
- system/capabilities/registry/capability_registry.py
- system/tools/registry/tool_registry.py
- tests/unit/test_schema_validation.py
- tests/unit/test_capability_registry.py
- tests/unit/test_tool_registry.py

## Registry behavior
Both registries reuse `system/shared/base_registry.py` and provide:

- JSON loading from disk
- Validation against schema
- ID-based indexing
- Full listing
- Duplicate ID detection

`CapabilityRegistry` adds one extra validation aligned with strategy rules:

- Strategy template variables must use explicit sources:
  - `inputs.*`
  - `state.*`
  - `steps.<step_id>.outputs.*`
  - `runtime.*`

## Running tests

From project root:

```bash
py -m unittest discover -s tests/unit -p "test_*.py" -v
```

