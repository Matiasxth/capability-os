"""Tests for Semantic Memory (Componente 3)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.memory.embeddings_engine import EmbeddingsEngine
from system.core.memory.memory_manager import MemoryManager
from system.core.memory.semantic_memory import SemanticMemory
from system.core.memory.vector_store import VectorStore

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "semantic"


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
    # Fit a small corpus for meaningful embeddings
    eng.fit([
        "create a react project",
        "build a vue application",
        "read csv file from disk",
        "send whatsapp message to alice",
        "deploy kubernetes cluster",
        "open browser and navigate",
    ])
    return SemanticMemory(mm, vs, eng)


class TestRememberAndRecall(unittest.TestCase):

    def test_remember_and_recall_by_similarity(self):
        sm = _build("basic")
        sm.remember_semantic("create a react project for the dashboard")
        sm.remember_semantic("deploy kubernetes cluster on production")

        results = sm.recall_semantic("build a react app")
        self.assertTrue(len(results) >= 1)
        # The react-related memory should rank higher
        self.assertIn("react", results[0]["text"].lower())

    def test_semantic_query_not_exact_match(self):
        sm = _build("fuzzy")
        sm.remember_semantic("send a whatsapp message to bob")
        # Query uses different words but same meaning
        results = sm.recall_semantic("whatsapp message send")
        self.assertTrue(len(results) >= 1)
        self.assertIn("whatsapp", results[0]["text"].lower())


class TestForget(unittest.TestCase):

    def test_forget_removes_from_both_stores(self):
        sm = _build("forget")
        rec = sm.remember_semantic("temporary memory")
        self.assertIsNotNone(rec)
        mem_id = rec["id"]
        self.assertTrue(sm.forget_semantic(mem_id))
        # Should not appear in search
        results = sm.recall_semantic("temporary memory")
        ids = [r["memory"]["id"] for r in results]
        self.assertNotIn(mem_id, ids)


class TestFiltering(unittest.TestCase):

    def test_memory_type_filter(self):
        sm = _build("filter")
        sm.remember_semantic("pattern one", memory_type="execution_pattern")
        sm.remember_semantic("preference two", memory_type="user_preference")

        patterns = sm.recall_semantic("pattern", memory_type="execution_pattern")
        for r in patterns:
            self.assertEqual(r["memory"]["memory_type"], "execution_pattern")

    def test_count(self):
        sm = _build("count")
        self.assertEqual(sm.count(), 0)
        sm.remember_semantic("first")
        sm.remember_semantic("second")
        self.assertEqual(sm.count(), 2)


class TestResilience(unittest.TestCase):

    def test_recall_on_empty_returns_empty(self):
        sm = _build("empty")
        self.assertEqual(sm.recall_semantic("anything"), [])

    def test_forget_nonexistent_returns_false(self):
        sm = _build("fne")
        self.assertFalse(sm.forget_semantic("nonexistent"))


if __name__ == "__main__":
    unittest.main()
