from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.shared.schema_validation import SchemaValidationError, load_schema, validate_instance


class IntegrationValidationError(RuntimeError):
    """Raised when integration validation fails."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class IntegrationValidator:
    """Validates integration manifests and links with capability contracts."""

    def __init__(self, capability_registry: CapabilityRegistry, manifest_schema_path: str | Path):
        self.capability_registry = capability_registry
        self.manifest_schema_path = Path(manifest_schema_path).resolve()
        self._manifest_schema = load_schema(self.manifest_schema_path)

    def validate(self, manifest: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_instance(manifest, self._manifest_schema, context="integration_manifest")
        except SchemaValidationError as exc:
            raise IntegrationValidationError(f"Manifest validation failed: {exc}") from exc

        integration_id = manifest.get("id")
        if not isinstance(integration_id, str) or not integration_id:
            raise IntegrationValidationError("Manifest must include non-empty 'id'.")

        capabilities = manifest.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise IntegrationValidationError("Manifest must define at least one capability.")

        errors: list[str] = []
        for capability_id in capabilities:
            if not isinstance(capability_id, str) or not capability_id:
                errors.append("Manifest contains an invalid capability id entry.")
                continue

            contract = self.capability_registry.get(capability_id)
            if contract is None:
                errors.append(f"Capability '{capability_id}' does not exist in capability_registry.")
                continue

            # Re-validate contract to satisfy explicit validation requirement.
            try:
                self.capability_registry.validate_contract(
                    deepcopy(contract),
                    source=f"integration_validator:{integration_id}:{capability_id}",
                )
            except Exception as exc:
                errors.append(f"Capability '{capability_id}' contract is invalid: {exc}")
                continue

            declared_integrations = contract.get("requirements", {}).get("integrations", [])
            if not isinstance(declared_integrations, list) or integration_id not in declared_integrations:
                errors.append(
                    f"Capability '{capability_id}' does not declare integration '{integration_id}'."
                )

        if errors:
            raise IntegrationValidationError(
                f"Integration '{integration_id}' failed validation.",
                details=errors,
            )

        return {
            "integration_id": integration_id,
            "validated": True,
            "capability_count": len(capabilities),
        }

