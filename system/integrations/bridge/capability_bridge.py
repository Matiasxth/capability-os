"""Publishes integration capabilities into the CapabilityRegistry (spec section 13.4 step 9).

After an integration is installed and validated, the Capability Bridge:
  1. Reads the manifest's capabilities list.
  2. Looks for matching contracts in `<integration>/capabilities/` or in the
     global v1 contracts directory.
  3. Registers any that are not yet in the CapabilityRegistry.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.shared.schema_validation import SchemaValidationError


class CapabilityBridgeError(RuntimeError):
    """Raised when capability bridge publishing fails."""


class CapabilityBridge:
    """Bridges integration capabilities into the global CapabilityRegistry."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        integrations_root: str | Path,
        global_contracts_dir: str | Path | None = None,
    ):
        self.capability_registry = capability_registry
        self.integrations_root = Path(integrations_root).resolve()
        self.global_contracts_dir = (
            Path(global_contracts_dir).resolve() if global_contracts_dir else None
        )

    def publish(self, integration_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Register all capabilities listed in the manifest.

        Returns a summary of published / already-registered / failed capabilities.
        """
        capabilities = manifest.get("capabilities", [])
        if not isinstance(capabilities, list):
            raise CapabilityBridgeError(
                f"Integration '{integration_id}' manifest has invalid capabilities."
            )

        published: list[str] = []
        already_registered: list[str] = []
        failed: list[dict[str, str]] = []

        for cap_id in capabilities:
            if not isinstance(cap_id, str) or not cap_id:
                failed.append({"id": str(cap_id), "error": "invalid capability id"})
                continue

            # Already in registry — skip
            if self.capability_registry.get(cap_id) is not None:
                already_registered.append(cap_id)
                continue

            contract = self._find_contract(integration_id, cap_id)
            if contract is None:
                failed.append({"id": cap_id, "error": "contract not found"})
                continue

            try:
                self.capability_registry.register(
                    contract,
                    source=f"capability_bridge:{integration_id}:{cap_id}",
                )
                published.append(cap_id)
            except (SchemaValidationError, Exception) as exc:
                failed.append({"id": cap_id, "error": str(exc)})

        return {
            "integration_id": integration_id,
            "published": published,
            "already_registered": already_registered,
            "failed": failed,
            "total_published": len(published),
        }

    def _find_contract(self, integration_id: str, cap_id: str) -> dict[str, Any] | None:
        """Search for a capability contract JSON in integration-local or global dirs."""
        # 1. Check integration-local capabilities/ dir
        local_path = self.integrations_root / integration_id / "capabilities" / f"{cap_id}.json"
        contract = self._load_json(local_path)
        if contract is not None:
            return contract

        # 2. Check global v1 contracts dir
        if self.global_contracts_dir is not None:
            global_path = self.global_contracts_dir / f"{cap_id}.json"
            contract = self._load_json(global_path)
            if contract is not None:
                return contract

        return None

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return None
