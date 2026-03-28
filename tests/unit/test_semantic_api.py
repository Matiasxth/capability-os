"""Tests for Semantic Memory API (Componente 5)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.memory.embeddings_engine import EmbeddingsEngine
from system.core.memory.memory_manager import MemoryManager
from system.core.memory.semantic_memory import SemanticMemory
from system.core.memory.vector_store import VectorStore

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "semantic_api"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _build(name: str) -> SemanticMemory:
    ws = _ws(name)
    mm = MemoryManager(ws / "memories.json")
    vs = VectorStore(ws / "vectors.json")
    eng = EmbeddingsEngine(vocab_path=ws / "vocab.json")
    eng.fit(["create project", "read file", "send message", "deploy server"])
    return SemanticMemory(mm, vs, eng)


class TestSearchEndpoint(unittest.TestCase):

    def test_search_returns_results(self):
        sm = _build("search")
        sm.remember_semantic("create a react project for dashboard")
        sm.remember_semantic("deploy server to production")
        results = sm.recall_semantic("create project", top_k=5)
        self.assertTrue(len(results) >= 1)
        # Both should come back; the project one should rank higher
        texts = [r["text"] for r in results]
        self.assertTrue(any("project" in t for t in texts))

    def test_empty_query_returns_empty(self):
        sm = _build("empty_q")
        self.assertEqual(sm.recall_semantic("", top_k=5), [])


class TestPostEndpoint(unittest.TestCase):

    def test_post_saves_memory(self):
        sm = _build("post")
        rec = sm.remember_semantic("user prefers dark theme", memory_type="user_preference")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["memory_type"], "user_preference")
        # Should be searchable
        results = sm.recall_semantic("dark theme")
        self.assertTrue(len(results) >= 1)


class TestDeleteEndpoint(unittest.TestCase):

    def test_delete_removes_memory(self):
        sm = _build("delete")
        rec = sm.remember_semantic("temporary note")
        self.assertIsNotNone(rec)
        mem_id = rec["id"]
        self.assertTrue(sm.forget_semantic(mem_id))
        # Should not appear in search
        results = sm.recall_semantic("temporary note")
        ids = [r["memory"]["id"] for r in results]
        self.assertNotIn(mem_id, ids)

    def test_delete_nonexistent(self):
        sm = _build("del_ne")
        self.assertFalse(sm.forget_semantic("ghost"))


if __name__ == "__main__":
    unittest.main()
