"""Persistent vector store for semantic search.

Stores (id, vector, metadata) triples in ``vectors.json``.
Search uses cosine similarity computed in pure Python (no numpy required).

Rule 5: all disk operations are wrapped — never blocks execution.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


class VectorStore:
    """Thread-safe persistent vector store with cosine similarity search."""

    def __init__(self, data_path: str | Path):
        self._path = Path(data_path).resolve()
        self._lock = RLock()
        self._entries: dict[str, dict[str, Any]] = {}  # id → {vector, metadata}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, entry_id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        """Add or overwrite a vector entry."""
        with self._lock:
            self._entries[entry_id] = {
                "vector": list(vector),
                "metadata": deepcopy(metadata or {}),
            }
            self._save()

    def delete(self, entry_id: str) -> bool:
        """Remove an entry. Returns True if removed."""
        with self._lock:
            if entry_id in self._entries:
                del self._entries[entry_id]
                self._save()
                return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Return the *top_k* most similar entries sorted by descending cosine score."""
        if not query_vector:
            return []
        with self._lock:
            scored: list[tuple[str, float, dict[str, Any]]] = []
            for eid, entry in self._entries.items():
                vec = entry.get("vector", [])
                if not vec:
                    continue
                score = _cosine(query_vector, vec)
                scored.append((eid, score, entry.get("metadata", {})))
        scored.sort(key=lambda t: t[1], reverse=True)
        return [
            {"id": eid, "score": round(score, 4), "metadata": deepcopy(meta)}
            for eid, score, meta in scored[:max(1, top_k)]
        ]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            return {"id": entry_id, "vector": list(entry["vector"]), "metadata": deepcopy(entry.get("metadata", {}))}

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._entries = {}
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("vectors"), list):
                    self._entries = {}
                    for item in raw["vectors"]:
                        if isinstance(item, dict) and "id" in item and "vector" in item:
                            self._entries[item["id"]] = {
                                "vector": item["vector"],
                                "metadata": item.get("metadata", {}),
                            }
                else:
                    self._entries = {}
            except (json.JSONDecodeError, OSError):
                self._entries = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "vectors": [
                    {"id": eid, "vector": e["vector"], "metadata": e.get("metadata", {})}
                    for eid, e in self._entries.items()
                ]
            }
            self._path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass  # Rule 5


# ---------------------------------------------------------------------------
# Pure-Python cosine similarity
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0
    return dot / (mag_a * mag_b)
