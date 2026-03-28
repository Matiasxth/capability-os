# Contributing to Capability OS

## Reporting bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (from `GET /executions/{id}/events` or `GET /metrics`)
- Python version and OS

## Proposing a new capability

Every capability must have a formal contract before implementation. Use this template:

```json
{
  "id": "verb_object",
  "name": "Human Readable Name",
  "domain": "one of: desarrollo|archivos|ejecucion|web|integraciones|automatizacion|observacion",
  "type": "base|composed|integration|generated",
  "description": "What this capability does.",
  "inputs": {
    "field_name": {"type": "string", "required": true, "description": "What this field is."}
  },
  "outputs": {
    "result_field": {"type": "string"}
  },
  "requirements": {
    "tools": ["category_verb_object"],
    "capabilities": [],
    "integrations": []
  },
  "strategy": {
    "mode": "sequential",
    "steps": [
      {
        "step_id": "step_name",
        "action": "category_verb_object",
        "params": {"field": "{{inputs.field_name}}"}
      }
    ]
  },
  "exposure": {
    "visible_to_user": true,
    "trigger_phrases": ["natural language trigger"]
  },
  "lifecycle": {
    "version": "1.0.0",
    "status": "experimental"
  }
}
```

Place the contract in `system/capabilities/contracts/v1/` and include tests.

## Adding a new integration

Follow the formal pipeline (spec section 13):

1. Create a directory under `system/integrations/installed/your_connector/`
2. Include `manifest.json` following the integration manifest schema
3. Add capability contracts under `your_connector/capabilities/`
4. Add tool contracts if needed under `your_connector/tools/`
5. Include a `connector.py` with the implementation
6. Add tests under `tests/unit/`

The manifest must match:
```json
{
  "id": "provider_type_connector",
  "name": "Human Name",
  "type": "web_app|rest_api|local_app|file_based",
  "status": "ready",
  "capabilities": ["capability_id_1"],
  "requirements": {},
  "lifecycle": {"version": "1.0.0"}
}
```

## Running tests

```bash
# Full backend suite
python -m pytest tests/unit/ -q

# With coverage enforcement
python -m pytest --cov=system.core --cov-fail-under=80 --cov-report=term-missing:skip-covered

# Frontend
cd system/frontend/app && npm test -- --run
```

## Naming conventions (spec section 27)

| Layer | Pattern | Example |
|---|---|---|
| Capabilities | `verb_object` | `read_file`, `create_project` |
| Tools | `category_verb_object` | `filesystem_read_file`, `mcp_server_tool` |
| Integrations | `provider_type_connector` | `whatsapp_web_connector` |

Rules:
- IDs are **snake_case**, lowercase, immutable once published
- Human-readable `name` can change; `id` cannot
- No mixing prefixes between layers

## Variables in strategies

Only explicit origins are allowed:
- `{{inputs.field_name}}`
- `{{state.field_name}}`
- `{{steps.step_id.outputs.field_name}}`
- `{{runtime.field_name}}`

Implicit variables like `{{project_name}}` are rejected by schema validation.

## Pull request process

1. **Branch** from `main`
2. **Write tests** for every new component (target: core coverage >=82%)
3. **Validate contracts** against their JSON schemas
4. **Run the full test suite** before opening the PR
5. **Include** in your PR description:
   - What spec section this implements
   - Files created/modified
   - Tests added

PRs without tests will not be merged. PRs that drop coverage below 82% will be flagged.

## Architecture decisions

- The system **proposes, the user confirms** (spec section 14). Never auto-install capabilities, integrations, or optimizations.
- Memory operations **never block execution** (Rule 5). All disk writes are wrapped in try/except.
- Every tool contract must include `constraints` (timeout, allowlist, workspace_only) and `safety` (level, requires_confirmation).
- The `CapabilityEngine` does not contain business logic. It only interprets contracts.
