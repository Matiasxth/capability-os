"""Builds a context dict from the workspace registry for injection into executions.

The CapabilityEngine injects this as ``state["workspaces"]`` so strategies
can reference ``{{state.workspaces.default.path}}`` etc.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from system.core.workspace.workspace_registry import WorkspaceRegistry


class WorkspaceContext:
    """Provides a snapshot of workspace state for execution context."""

    def __init__(self, registry: WorkspaceRegistry):
        self._registry = registry

    def get_context(self) -> dict[str, Any]:
        """Return workspace context for state injection.

        Returns ``{}`` on any internal error (Rule 5).
        """
        try:
            all_ws = self._registry.list()
            active = [w for w in all_ws if w.get("active", True)]
            default = self._registry.get_default()

            by_name: dict[str, dict[str, Any]] = {}
            for w in active:
                summary = _summarize(w)
                by_name[w["name"]] = summary

            return {
                "default": _summarize(default) if default else None,
                "all": [_summarize(w) for w in active],
                "by_name": by_name,
                "count": len(active),
            }
        except Exception:
            return {}


def _summarize(ws: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields useful inside a strategy."""
    return {
        "id": ws.get("id"),
        "name": ws.get("name"),
        "path": ws.get("path"),
        "access": ws.get("access"),
    }
