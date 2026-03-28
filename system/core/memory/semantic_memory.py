"""High-level semantic memory: remember/recall by meaning, not exact key.

Combines MemoryManager (structured storage), VectorStore (similarity index),
and EmbeddingsEngine (text → vector) into a single interface.

``remember_semantic``  writes to both stores.
``recall_semantic``    searches by embedding similarity and returns full records.
``forget_semantic``    removes from both stores.

Rule 5: every public method wraps in try/except — never blocks execution.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from system.core.memory.embeddings_engine import EmbeddingsEngine
from system.core.memory.memory_manager import MemoryManager
from system.core.memory.vector_store import VectorStore


class SemanticMemory:
    """Semantic layer over MemoryManager + VectorStore + EmbeddingsEngine."""

    def __init__(
        self,
        memory_manager: MemoryManager,
        vector_store: VectorStore,
        embeddings_engine: EmbeddingsEngine,
    ):
        self._memory = memory_manager
        self._vectors = vector_store
        self._embeddings = embeddings_engine

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember_semantic(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        memory_type: str = "capability_context",
        capability_id: str | None = None,
        ttl_days: int | None = None,
    ) -> dict[str, Any] | None:
        """Store a text memory with semantic indexing.

        Returns the MemoryManager record, or None on failure.
        """
        try:
            mem_id = f"sem_{uuid4().hex[:8]}"
            key = f"semantic:{mem_id}"

            record = self._memory.remember(
                key=key,
                value=text,
                memory_type=memory_type,
                capability_id=capability_id,
                ttl_days=ttl_days,
            )
            mem_id = record["id"]

            vec = self._embeddings.embed(text)
            if vec:
                self._vectors.add(mem_id, vec, metadata={"key": key, "text": text, **(metadata or {})})

            return deepcopy(record)
        except Exception:
            return None

    def forget_semantic(self, memory_id: str) -> bool:
        """Remove from both MemoryManager and VectorStore."""
        try:
            forgotten = self._memory.forget(memory_id)
            self._vectors.delete(memory_id)
            return forgotten
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall_semantic(
        self,
        query: str,
        top_k: int = 5,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories by semantic similarity to *query*.

        Returns a list of ``{memory, score, text}`` dicts ordered by relevance.
        """
        try:
            vec = self._embeddings.embed(query)
            if not vec:
                return []

            hits = self._vectors.search(vec, top_k=max(1, top_k) * 2)  # overfetch for filtering
            results: list[dict[str, Any]] = []

            for hit in hits:
                mem_id = hit["id"]
                record = self._memory.get(mem_id)
                if record is None:
                    continue
                if memory_type is not None and record.get("memory_type") != memory_type:
                    continue
                results.append({
                    "memory": deepcopy(record),
                    "score": hit["score"],
                    "text": hit.get("metadata", {}).get("text", record.get("value", "")),
                })
                if len(results) >= top_k:
                    break

            return results
        except Exception:
            return []

    def count(self) -> int:
        try:
            return self._vectors.count()
        except Exception:
            return 0
