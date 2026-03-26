from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


INTEGRATION_STATUSES = {
    "discovered",
    "installed",
    "validated",
    "enabled",
    "disabled",
    "error",
}


class IntegrationRegistryError(RuntimeError):
    """Raised when integration registry operations are invalid."""


class IntegrationNotFoundError(IntegrationRegistryError):
    """Raised when integration id does not exist in registry."""


class IntegrationRegistry:
    """Persistent dynamic state for discovered integrations."""

    def __init__(self, data_path: str | Path):
        self.data_path = Path(data_path).resolve()
        self._lock = RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def list_integrations(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(self._entries[key]) for key in sorted(self._entries)]

    def get_integration(self, integration_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(integration_id)
            if entry is None:
                return None
            return deepcopy(entry)

    def ensure_discovered(self, integration_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if integration_id in self._entries:
                entry = self._entries[integration_id]
                if metadata:
                    entry["metadata"].update(deepcopy(metadata))
                self._save_locked()
                return deepcopy(entry)

            entry = {
                "id": integration_id,
                "status": "discovered",
                "validated": False,
                "last_validated_at": None,
                "error": None,
                "metadata": deepcopy(metadata or {}),
            }
            self._entries[integration_id] = entry
            self._save_locked()
            return deepcopy(entry)

    def mark_installed(self, integration_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            entry = self._entries.get(integration_id)
            if entry is None:
                entry = {
                    "id": integration_id,
                    "status": "discovered",
                    "validated": False,
                    "last_validated_at": None,
                    "error": None,
                    "metadata": deepcopy(metadata or {}),
                }
                self._entries[integration_id] = entry

            if metadata:
                entry["metadata"].update(deepcopy(metadata))

            if entry["status"] in {"discovered", "installed"}:
                entry["status"] = "installed"

            if entry["status"] != "error":
                entry["error"] = None
            self._save_locked()
            return deepcopy(entry)

    def mark_validated(self, integration_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._require_entry_locked(integration_id)
            entry["validated"] = True
            entry["status"] = "validated"
            entry["last_validated_at"] = _utc_now_iso()
            entry["error"] = None
            self._save_locked()
            return deepcopy(entry)

    def mark_error(self, integration_id: str, error_message: str) -> dict[str, Any]:
        with self._lock:
            entry = self._entries.get(integration_id)
            if entry is None:
                entry = self.ensure_discovered(integration_id, {})
                self._entries[integration_id] = entry
                entry = self._entries[integration_id]

            entry["status"] = "error"
            entry["validated"] = False
            entry["last_validated_at"] = _utc_now_iso()
            entry["error"] = error_message
            self._save_locked()
            return deepcopy(entry)

    def enable(self, integration_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._require_entry_locked(integration_id)
            if entry.get("validated") is not True:
                raise IntegrationRegistryError(
                    f"Integration '{integration_id}' cannot be enabled because it is not validated."
                )
            entry["status"] = "enabled"
            entry["error"] = None
            self._save_locked()
            return deepcopy(entry)

    def disable(self, integration_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._require_entry_locked(integration_id)
            entry["status"] = "disabled"
            self._save_locked()
            return deepcopy(entry)

    def update_metadata(self, integration_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = self._require_entry_locked(integration_id)
            entry["metadata"].update(deepcopy(metadata))
            self._save_locked()
            return deepcopy(entry)

    def _load(self) -> None:
        with self._lock:
            if not self.data_path.exists():
                self.data_path.parent.mkdir(parents=True, exist_ok=True)
                self._entries = {}
                self._save_locked()
                return

            with self.data_path.open("r", encoding="utf-8-sig") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise IntegrationRegistryError(
                    f"Integration registry data '{self.data_path}' must be an object."
                )
            entries = raw.get("integrations", [])
            if not isinstance(entries, list):
                raise IntegrationRegistryError(
                    f"Integration registry data '{self.data_path}' has invalid 'integrations'."
                )

            loaded: dict[str, dict[str, Any]] = {}
            for item in entries:
                if not isinstance(item, dict):
                    continue
                integration_id = item.get("id")
                if not isinstance(integration_id, str) or not integration_id:
                    continue
                status = item.get("status")
                if status not in INTEGRATION_STATUSES:
                    status = "discovered"
                loaded[integration_id] = {
                    "id": integration_id,
                    "status": status,
                    "validated": bool(item.get("validated", False)),
                    "last_validated_at": item.get("last_validated_at"),
                    "error": item.get("error"),
                    "metadata": deepcopy(item.get("metadata", {}))
                    if isinstance(item.get("metadata"), dict)
                    else {},
                }
            self._entries = loaded

    def _save_locked(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "integrations": [
                self._entries[key]
                for key in sorted(self._entries)
            ]
        }
        with self.data_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _require_entry_locked(self, integration_id: str) -> dict[str, Any]:
        entry = self._entries.get(integration_id)
        if entry is None:
            raise IntegrationNotFoundError(f"Integration '{integration_id}' is not registered.")
        return entry


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
