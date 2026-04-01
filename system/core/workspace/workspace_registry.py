"""Persistent registry of workspaces with access control.

Stores workspace definitions in ``workspaces.json``.  Each workspace has
an id, a filesystem path, an access level (``write``/``read``/``none``),
and an optional set of allowed capabilities.

Thread-safe.  Persists on every write.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


VALID_ACCESS = {"write", "read", "none"}


class WorkspaceRegistry:
    """Manages the set of registered workspaces."""

    def __init__(self, data_path: str | Path, db: Any = None):
        self._path = Path(data_path).resolve()
        self._lock = RLock()
        self._workspaces: dict[str, dict[str, Any]] = {}
        self._default_id: str | None = None
        self._repo: Any = None
        if db is not None:
            try:
                from system.infrastructure.repositories import WorkspaceRepository
                self._repo = WorkspaceRepository(db)
            except Exception:
                pass
        self._load()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        name: str,
        path: str,
        access: str = "write",
        capabilities: str | list[str] = "*",
        color: str = "#00ff88",
        icon: str = "folder",
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Workspace name must be non-empty.")
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path '{path}' does not exist.")
        if not resolved.is_dir():
            raise ValueError(f"Path '{path}' is not a directory.")
        if access not in VALID_ACCESS:
            raise ValueError(f"Access must be one of {VALID_ACCESS}.")

        with self._lock:
            for ws in self._workspaces.values():
                if Path(ws["path"]).resolve() == resolved:
                    raise ValueError(f"Path '{resolved}' is already registered.")

            ws_id = f"ws_{uuid4().hex[:6]}"
            record: dict[str, Any] = {
                "id": ws_id,
                "name": name.strip(),
                "path": str(resolved),
                "access": access,
                "allowed_capabilities": capabilities,
                "color": color,
                "icon": icon,
                "active": True,
                "status": {"name": "En construccion", "color": "#ffaa00", "icon": "\U0001f3d7\ufe0f"},
                "description": "",
                "agent_ids": [],
                "created_at": _now(),
            }
            self._workspaces[ws_id] = record
            if self._default_id is None:
                self._default_id = ws_id
            self._save()
            return deepcopy(record)

    def remove(self, ws_id: str) -> bool:
        with self._lock:
            if ws_id not in self._workspaces:
                return False
            if self._default_id == ws_id and len(self._workspaces) == 1:
                raise ValueError("Cannot remove the only workspace.")
            del self._workspaces[ws_id]
            if self._default_id == ws_id:
                self._default_id = next(iter(self._workspaces), None)
            self._save()
            return True

    def update(self, ws_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            ws = self._workspaces.get(ws_id)
            if ws is None:
                raise KeyError(f"Workspace '{ws_id}' not found.")
            for k, v in fields.items():
                if k in ("name", "access", "allowed_capabilities", "color", "icon", "active", "status", "description", "agent_ids"):
                    ws[k] = v
                elif k == "path":
                    ws["path"] = str(Path(v).resolve())
            self._save()
            return deepcopy(ws)

    def get(self, ws_id: str) -> dict[str, Any] | None:
        with self._lock:
            ws = self._workspaces.get(ws_id)
            return deepcopy(ws) if ws else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(ws) for ws in self._workspaces.values()]

    # ------------------------------------------------------------------
    # Default workspace
    # ------------------------------------------------------------------

    def get_default(self) -> dict[str, Any] | None:
        with self._lock:
            if self._default_id and self._default_id in self._workspaces:
                return deepcopy(self._workspaces[self._default_id])
            return None

    def set_default(self, ws_id: str) -> bool:
        with self._lock:
            if ws_id not in self._workspaces:
                return False
            self._default_id = ws_id
            self._save()
            return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_by_path(self, path: str) -> dict[str, Any] | None:
        """Find the workspace whose root contains *path*."""
        norm = _normalize(path)
        with self._lock:
            for ws in self._workspaces.values():
                ws_norm = _normalize(ws["path"])
                if norm == ws_norm or norm.startswith(ws_norm + os.sep):
                    return deepcopy(ws)
        return None

    def validate_path_exists(self, path: str) -> bool:
        return Path(path).resolve().exists()

    def count(self) -> int:
        with self._lock:
            return len(self._workspaces)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            # Try DB first
            if self._repo is not None:
                try:
                    rows = self._repo.list_all()
                    if rows:
                        for item in rows:
                            if isinstance(item, dict) and "id" in item:
                                self._workspaces[item["id"]] = item
                        self._default_id = self._repo.get_default_id()
                        return
                except Exception:
                    pass
            # Fallback: JSON file
            if not self._path.exists():
                self._workspaces = {}
                self._default_id = None
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for item in raw.get("workspaces", []):
                        if isinstance(item, dict) and "id" in item:
                            self._workspaces[item["id"]] = item
                    self._default_id = raw.get("default_workspace_id")
                # Migrate JSON data into DB
                if self._repo is not None and self._workspaces:
                    for ws in self._workspaces.values():
                        try:
                            self._repo.add(ws)
                        except Exception:
                            pass
                    if self._default_id:
                        try:
                            self._repo.set_default(self._default_id)
                        except Exception:
                            pass
            except (json.JSONDecodeError, OSError):
                self._workspaces = {}
                self._default_id = None

    def _save(self) -> None:
        # Write to DB if available
        if self._repo is not None:
            try:
                for ws in self._workspaces.values():
                    self._repo.add(ws)
                if self._default_id:
                    self._repo.set_default(self._default_id)
            except Exception:
                pass
        # Always write JSON as backup
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "workspaces": list(self._workspaces.values()),
                "default_workspace_id": self._default_id,
            }
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass


def _normalize(path: str) -> str:
    """Normalize path for cross-platform comparison (case-insensitive on Windows)."""
    n = str(Path(path).resolve())
    if os.name == "nt":
        n = n.lower()
    return n


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
