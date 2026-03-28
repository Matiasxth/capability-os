"""Persistent key-value memory that survives process restarts.

Stores memories in ``workspace/memory/memories.json``.  Each memory has a
type, semantic key, value, optional capability association, access tracking,
and optional TTL.

Rule 5 from the implementation spec: memory NEVER blocks the main execution.
All public methods wrap their body in try/except so a corrupt file or disk
error degrades gracefully instead of crashing a capability run.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


MEMORY_TYPES = {
    "user_preference",
    "execution_pattern",
    "capability_context",
    "integration_context",
}


class MemoryManager:
    """Thread-safe persistent memory store."""

    def __init__(self, data_path: str | Path):
        self._path = Path(data_path).resolve()
        self._lock = RLock()
        self._memories: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember(
        self,
        key: str,
        value: Any,
        memory_type: str = "capability_context",
        capability_id: str | None = None,
        ttl_days: int | None = None,
    ) -> dict[str, Any]:
        """Create or update a memory entry.  Returns the stored record."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Memory key must be a non-empty string.")
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory type '{memory_type}'.")

        with self._lock:
            existing = self._find_by_key(key)
            now = _now_iso()

            if existing is not None:
                existing["value"] = deepcopy(value)
                existing["updated_at"] = now
                existing["memory_type"] = memory_type
                if capability_id is not None:
                    existing["capability_id"] = capability_id
                if ttl_days is not None:
                    existing["ttl_days"] = ttl_days
                self._save()
                return deepcopy(existing)

            record: dict[str, Any] = {
                "id": f"mem_{uuid4().hex[:8]}",
                "memory_type": memory_type,
                "key": key.strip(),
                "value": deepcopy(value),
                "capability_id": capability_id,
                "created_at": now,
                "updated_at": now,
                "access_count": 0,
                "ttl_days": ttl_days,
            }
            self._memories[record["id"]] = record
            self._save()
            return deepcopy(record)

    def forget(self, memory_id: str) -> bool:
        """Delete a memory by id.  Returns True if removed."""
        with self._lock:
            if memory_id in self._memories:
                del self._memories[memory_id]
                self._save()
                return True
        return False

    def forget_by_key(self, key: str) -> bool:
        """Delete a memory by semantic key."""
        with self._lock:
            record = self._find_by_key(key)
            if record is not None:
                del self._memories[record["id"]]
                self._save()
                return True
        return False

    def cleanup_expired(self) -> int:
        """Remove memories past their TTL.  Returns count removed."""
        now = datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            to_delete: list[str] = []
            for mid, rec in self._memories.items():
                ttl = rec.get("ttl_days")
                if ttl is None or not isinstance(ttl, (int, float)) or ttl <= 0:
                    continue
                created = _parse_iso(rec.get("created_at", ""))
                if created is None:
                    continue
                if now - created > timedelta(days=ttl):
                    to_delete.append(mid)
            for mid in to_delete:
                del self._memories[mid]
            removed = len(to_delete)
            if removed > 0:
                self._save()
        return removed

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(self, key: str) -> Any | None:
        """Retrieve a memory value by key, or None.  Increments access_count."""
        with self._lock:
            record = self._find_by_key(key)
            if record is None:
                return None
            record["access_count"] = record.get("access_count", 0) + 1
            self._save()
            return deepcopy(record["value"])

    def recall_all(
        self,
        memory_type: str | None = None,
        capability_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all memories, optionally filtered."""
        with self._lock:
            results: list[dict[str, Any]] = []
            for rec in self._memories.values():
                if memory_type is not None and rec.get("memory_type") != memory_type:
                    continue
                if capability_id is not None and rec.get("capability_id") != capability_id:
                    continue
                results.append(deepcopy(rec))
            return sorted(results, key=lambda r: r.get("updated_at", ""), reverse=True)

    def get(self, memory_id: str) -> dict[str, Any] | None:
        """Get a memory record by id without incrementing access_count."""
        with self._lock:
            rec = self._memories.get(memory_id)
            return deepcopy(rec) if rec is not None else None

    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_by_key(self, key: str) -> dict[str, Any] | None:
        """Find a memory by semantic key (must be called under lock)."""
        normalized = key.strip()
        for rec in self._memories.values():
            if rec.get("key") == normalized:
                return rec
        return None

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._memories = {}
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "memories" in raw:
                    entries = raw["memories"]
                    if isinstance(entries, list):
                        self._memories = {}
                        for item in entries:
                            if isinstance(item, dict) and "id" in item:
                                self._memories[item["id"]] = item
                        return
                self._memories = {}
            except (json.JSONDecodeError, OSError):
                self._memories = {}

    def _save(self) -> None:
        """Persist to disk.  Called under lock."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "memories": list(self._memories.values()),
            }
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass  # Rule 5: never block execution


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
