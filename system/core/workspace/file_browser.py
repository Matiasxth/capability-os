"""Navigates the file tree within a workspace.

Only reads inside the workspace root — never escapes.
Hides system directories (.git, node_modules, __pycache__, .env).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from system.core.workspace.workspace_registry import WorkspaceRegistry


_HIDDEN = frozenset({
    ".git", "node_modules", "__pycache__", ".env", ".venv",
    ".mypy_cache", ".pytest_cache", ".tox", ".eggs",
    "dist", "build", ".next", ".nuxt",
})

_MAX_ENTRIES = 200


class FileBrowser:
    """Lists directory contents within a workspace."""

    def __init__(self, registry: WorkspaceRegistry):
        self._registry = registry

    def list_directory(
        self,
        workspace_id: str,
        relative_path: str = ".",
    ) -> dict[str, Any]:
        ws = self._registry.get(workspace_id)
        if ws is None:
            raise KeyError(f"Workspace '{workspace_id}' not found.")

        ws_root = Path(ws["path"]).resolve()
        target = (ws_root / relative_path).resolve()

        # Security: must stay inside workspace
        try:
            if not (target == ws_root or target.is_relative_to(ws_root)):
                raise PermissionError("Path is outside the workspace.")
        except (ValueError, TypeError):
            raise PermissionError("Path is outside the workspace.")

        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Directory '{relative_path}' does not exist.")

        entries: list[dict[str, Any]] = []
        try:
            children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            children = []

        for child in children:
            if child.name in _HIDDEN:
                continue
            if child.name.startswith(".") and child.name not in (".gitignore",):
                continue
            if len(entries) >= _MAX_ENTRIES:
                break

            try:
                stat = child.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            except OSError:
                modified = None

            rel = str(child.relative_to(ws_root)).replace("\\", "/")

            if child.is_dir():
                entries.append({
                    "name": child.name,
                    "type": "directory",
                    "path": rel,
                    "size": None,
                    "extension": None,
                    "modified": modified,
                })
            else:
                entries.append({
                    "name": child.name,
                    "type": "file",
                    "path": rel,
                    "size": stat.st_size if modified else 0,
                    "extension": child.suffix or None,
                    "modified": modified,
                })

        return {
            "workspace": {"id": ws["id"], "name": ws["name"], "path": ws["path"]},
            "path": str(target.relative_to(ws_root)).replace("\\", "/") if target != ws_root else ".",
            "entries": entries,
        }
