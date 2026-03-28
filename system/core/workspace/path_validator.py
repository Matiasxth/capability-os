"""Validates filesystem operations against the workspace registry.

Every filesystem tool must call ``validate()`` before executing.
If the path falls outside all registered workspaces, or the workspace
access level forbids the operation, the call is rejected.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from system.core.workspace.workspace_registry import WorkspaceRegistry


class PathValidator:
    """Checks paths against workspace access rules."""

    def __init__(self, registry: WorkspaceRegistry):
        self._registry = registry

    def validate(
        self,
        path: str,
        operation: str = "read",
        capability_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate a filesystem operation.

        Args:
            path: Absolute or relative filesystem path.
            operation: ``"read"`` or ``"write"``.
            capability_id: The capability requesting access (optional).

        Returns:
            ``{allowed, workspace, reason}``
        """
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError):
            return _deny("Invalid path.")

        ws = self._registry.get_by_path(str(resolved))
        if ws is None:
            return _deny("Path is outside all registered workspaces.")

        if not ws.get("active", True):
            return _deny("Workspace is inactive.", ws)

        access = ws.get("access", "none")
        if access == "none":
            return _deny("Workspace is blocked (access=none).", ws)

        if operation == "write" and access == "read":
            return _deny("Workspace is read-only.", ws)

        allowed_caps = ws.get("allowed_capabilities", "*")
        if allowed_caps != "*" and capability_id is not None:
            if isinstance(allowed_caps, list) and capability_id not in allowed_caps:
                return _deny(f"Capability '{capability_id}' is not permitted in this workspace.", ws)

        return {"allowed": True, "workspace": deepcopy(ws), "reason": ""}


def _deny(reason: str, ws: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"allowed": False, "workspace": deepcopy(ws) if ws else None, "reason": reason}
