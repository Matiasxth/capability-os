# Capability OS - Phase 11 Technical README

## Scope
Phase 11 introduces a real Integration System to discover, validate, enable and manage existing integrations.

Implemented:
- Persistent `integration_registry`
- `integration_loader` for manifest discovery
- `integration_validator` for manifest/capability linkage checks
- Backend API endpoints for integration lifecycle
- Minimal frontend integration panel

No new integrations were created; WhatsApp Web Connector is the first managed case.

## Manifest vs Registry
- Static source (manifest): each integration declares `id`, `name`, `type`, `capabilities` (plus existing schema fields).
- Dynamic source (registry): persisted lifecycle state in JSON.

Registry fields:
- `id`
- `status`: `discovered | installed | validated | enabled | disabled | error`
- `validated` (boolean)
- `last_validated_at`
- `error`
- `metadata`

Persistence path:
- default: `<workspace_root>/system/integrations/registry_data.json`

## Lifecycle Rules
- Discovery registers integrations as `discovered/installed`.
- `validate` moves to `validated` on success, or `error` on failure.
- `enable` is allowed only when `validated == true`.
- `disable` is always allowed.
- Only integrations in `enabled` can run capabilities that require them.

## Validation Rules
`validate_integration` checks:
- manifest schema validity
- each manifest capability exists in `capability_registry`
- each capability contract declares that integration in `requirements.integrations`
- capability contracts remain valid

## API Endpoints
- `GET /integrations`
- `GET /integrations/{id}`
- `POST /integrations/{id}/validate`
- `POST /integrations/{id}/enable`
- `POST /integrations/{id}/disable`

All responses keep structured errors.

## Frontend
Added minimal integrations panel:
- list integrations (`id`, `name`, `type`, `status`)
- inspect detail (`capabilities`, `validated`, `error`)
- actions: `Validar`, `Habilitar`, `Deshabilitar`

## Tests
- Backend lifecycle and validation tests:
  - `tests/unit/test_phase11_integration_system.py`
- Existing schema validation extended for manifest changes:
  - `tests/unit/test_schema_validation.py`
- Frontend integration panel coverage:
  - `system/frontend/app/src/App.test.jsx`

