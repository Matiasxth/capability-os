from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from system.integrations.registry.integration_registry import IntegrationRegistry
from system.shared.schema_validation import (
    SchemaValidationError,
    load_json_file,
    load_schema,
    validate_instance,
)


class IntegrationLoaderError(RuntimeError):
    """Raised when integration discovery cannot complete."""


class IntegrationLoader:
    """Discovers integration manifests and syncs dynamic registry state."""

    def __init__(
        self,
        integrations_root: str | Path,
        manifest_schema_path: str | Path,
        integration_registry: IntegrationRegistry,
    ):
        self.integrations_root = Path(integrations_root).resolve()
        self.manifest_schema_path = Path(manifest_schema_path).resolve()
        self.integration_registry = integration_registry
        self._manifest_schema = load_schema(self.manifest_schema_path)
        self._manifests: dict[str, dict[str, Any]] = {}
        self._manifest_paths: dict[str, str] = {}

    def discover(self) -> list[dict[str, Any]]:
        if not self.integrations_root.exists():
            self.integrations_root.mkdir(parents=True, exist_ok=True)
            self._manifests = {}
            self._manifest_paths = {}
            return []

        self._manifests = {}
        self._manifest_paths = {}
        discovered_ids: list[str] = []
        for folder in sorted(self.integrations_root.iterdir()):
            if not folder.is_dir():
                continue
            manifest_path = folder / "manifest.json"
            if not manifest_path.exists():
                continue

            fallback_id = folder.name
            self.integration_registry.ensure_discovered(
                fallback_id,
                metadata={
                    "name": fallback_id,
                    "type": "unknown",
                    "capabilities": [],
                    "manifest_path": str(manifest_path),
                },
            )

            try:
                manifest = load_json_file(manifest_path)
                if not isinstance(manifest, dict):
                    raise SchemaValidationError("Manifest root must be an object.")
                validate_instance(manifest, self._manifest_schema, context=str(manifest_path))
            except Exception as exc:
                self.integration_registry.mark_error(
                    fallback_id,
                    f"manifest_invalid: {exc}",
                )
                continue

            integration_id = manifest.get("id")
            if not isinstance(integration_id, str) or not integration_id:
                self.integration_registry.mark_error(
                    fallback_id,
                    "manifest_invalid: field 'id' must be a non-empty string.",
                )
                continue

            metadata = {
                "name": manifest.get("name", integration_id),
                "type": manifest.get("type"),
                "capabilities": deepcopy(manifest.get("capabilities", [])),
                "manifest_path": str(manifest_path),
            }
            self.integration_registry.ensure_discovered(integration_id, metadata=metadata)
            self.integration_registry.mark_installed(integration_id, metadata=metadata)

            if integration_id != fallback_id:
                self.integration_registry.update_metadata(
                    fallback_id,
                    {"alias_of": integration_id},
                )

            self._manifests[integration_id] = manifest
            self._manifest_paths[integration_id] = str(manifest_path)
            discovered_ids.append(integration_id)

        discovered_entries: list[dict[str, Any]] = []
        for item_id in discovered_ids:
            entry = self.integration_registry.get_integration(item_id)
            if entry is not None:
                discovered_entries.append(entry)
        return discovered_entries

    def get_manifest(self, integration_id: str) -> dict[str, Any] | None:
        manifest = self._manifests.get(integration_id)
        if manifest is None:
            return None
        return deepcopy(manifest)

    def get_manifest_path(self, integration_id: str) -> str | None:
        return self._manifest_paths.get(integration_id)
