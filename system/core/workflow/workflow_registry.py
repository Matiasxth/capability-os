"""Thread-safe CRUD registry for visual workflows.

Workflows are persisted as JSON in ``workspace/workflows.json``.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class WorkflowRegistry:
    """Manages workflow definitions with thread-safe persistence."""

    def __init__(self, workspace_root: Path, db: Any = None) -> None:
        self._workspace_root = Path(workspace_root)
        self._file = self._workspace_root / "workflows.json"
        self._lock = RLock()
        self._workflows: dict[str, dict[str, Any]] = {}
        self._repo: Any = None
        if db is not None:
            try:
                from system.infrastructure.repositories.workflow_repo import WorkflowRepository
                self._repo = WorkflowRepository(db)
            except Exception:
                pass
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            # Try DB first
            if self._repo is not None:
                try:
                    rows = self._repo.list_all()
                    if rows:
                        for wf in rows:
                            if isinstance(wf, dict) and "id" in wf:
                                self._workflows[wf["id"]] = wf
                        return
                except Exception:
                    pass
            # Fallback: JSON file
            if self._file.exists():
                try:
                    data = json.loads(self._file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        self._workflows = {w["id"]: w for w in data if "id" in w}
                    elif isinstance(data, dict):
                        self._workflows = data
                    else:
                        self._workflows = {}
                    # Migrate JSON data into DB
                    if self._repo is not None and self._workflows:
                        for wf in self._workflows.values():
                            try:
                                self._repo.add(wf)
                            except Exception:
                                pass
                except Exception:
                    logger.exception("Failed to load workflows from %s", self._file)
                    self._workflows = {}

    def _save(self) -> None:
        # Write to DB if available
        if self._repo is not None:
            try:
                for wf in self._workflows.values():
                    self._repo.add(wf)
            except Exception:
                pass
        # Always write JSON as backup
        with self._lock:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            payload = list(self._workflows.values())
            self._file.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        description: str = "",
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new workflow and return it."""
        wf_id = f"wf_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        workflow: dict[str, Any] = {
            "id": wf_id,
            "name": name,
            "description": description,
            "nodes": nodes or [],
            "edges": edges or [],
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._workflows[wf_id] = workflow
            self._save()
        logger.info("Created workflow %s (%s)", wf_id, name)
        return workflow

    def get(self, wf_id: str) -> dict[str, Any] | None:
        """Return a workflow by id, or None."""
        with self._lock:
            return self._workflows.get(wf_id)

    def list(self) -> list[dict[str, Any]]:
        """Return all workflows sorted by updated_at descending."""
        with self._lock:
            items = list(self._workflows.values())
        items.sort(key=lambda w: w.get("updated_at", ""), reverse=True)
        return items

    def update(self, wf_id: str, **fields: Any) -> dict[str, Any] | None:
        """Update specific fields of a workflow. Returns updated workflow or None."""
        with self._lock:
            wf = self._workflows.get(wf_id)
            if wf is None:
                return None
            allowed = {"name", "description", "nodes", "edges"}
            for key, value in fields.items():
                if key in allowed:
                    wf[key] = value
            wf["updated_at"] = _now_iso()
            self._save()
        logger.info("Updated workflow %s", wf_id)
        return wf

    def delete(self, wf_id: str) -> bool:
        """Delete a workflow. Returns True if it existed."""
        with self._lock:
            if wf_id not in self._workflows:
                return False
            del self._workflows[wf_id]
            self._save()
        logger.info("Deleted workflow %s", wf_id)
        return True

    def save_layout(
        self,
        wf_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Save node positions and edge layout for the visual builder."""
        return self.update(wf_id, nodes=nodes, edges=edges)
