"""Tests for Vector Store (Componente 2)."""
from __future__ import annotations

import math
import shutil
import unittest
from pathlib import Path

from system.core.memory.vector_store import VectorStore

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "vecstore"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws / "vectors.json"


def _norm(vec: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in vec))
    return [x / mag for x in vec] if mag > 0 else vec


class TestVectorStore(unittest.TestCase):

    def test_add_and_search(self):
        vs = VectorStore(_ws("basic"))
        vs.add("a", _norm([1.0, 0.0, 0.0]), {"label": "x-axis"})
        vs.add("b", _norm([0.0, 1.0, 0.0]), {"label": "y-axis"})
        results = vs.search(_norm([1.0, 0.0, 0.0]), top_k=2)
        self.assertEqual(results[0]["id"], "a")
        self.assertGreater(results[0]["score"], 0.99)

    def test_top_k_limits(self):
        vs = VectorStore(_ws("topk"))
        for i in range(10):
            vs.add(f"v{i}", _norm([float(i), 1.0, 0.0]))
        results = vs.search(_norm([9.0, 1.0, 0.0]), top_k=3)
        self.assertEqual(len(results), 3)

    def test_delete(self):
        vs = VectorStore(_ws("delete"))
        vs.add("x", [1.0, 0.0])
        self.assertTrue(vs.delete("x"))
        self.assertEqual(vs.count(), 0)
        self.assertFalse(vs.delete("x"))

    def test_cosine_correctness(self):
        vs = VectorStore(_ws("cosine"))
        vs.add("same", _norm([1.0, 1.0, 0.0]))
        vs.add("ortho", _norm([0.0, 0.0, 1.0]))
        results = vs.search(_norm([1.0, 1.0, 0.0]), top_k=2)
        # "same" should have score ~1.0, "ortho" ~0.0
        self.assertGreater(results[0]["score"], 0.99)
        self.assertLess(results[1]["score"], 0.1)

    def test_persistence(self):
        path = _ws("persist")
        vs1 = VectorStore(path)
        vs1.add("p1", [0.5, 0.5], {"key": "val"})

        vs2 = VectorStore(path)
        self.assertEqual(vs2.count(), 1)
        entry = vs2.get("p1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["metadata"]["key"], "val")

    def test_clear(self):
        vs = VectorStore(_ws("clear"))
        vs.add("a", [1.0])
        vs.add("b", [2.0])
        vs.clear()
        self.assertEqual(vs.count(), 0)

    def test_empty_query(self):
        vs = VectorStore(_ws("empty"))
        vs.add("a", [1.0, 0.0])
        self.assertEqual(vs.search([], top_k=5), [])


if __name__ == "__main__":
    unittest.main()
