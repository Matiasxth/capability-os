"""Tests for Embeddings Engine (Componente 1)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.memory.embeddings_engine import EmbeddingsEngine, cosine_similarity

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "embeddings"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


class TestEmbeddingsEngine(unittest.TestCase):

    def test_embed_returns_non_empty_vector(self):
        eng = EmbeddingsEngine()
        vec = eng.embed("hello world")
        self.assertIsInstance(vec, list)
        self.assertTrue(len(vec) > 0)
        self.assertTrue(all(isinstance(v, float) for v in vec))

    def test_same_text_same_vector(self):
        eng = EmbeddingsEngine()
        v1 = eng.embed("create a react project")
        v2 = eng.embed("create a react project")
        self.assertEqual(v1, v2)

    def test_similar_texts_high_cosine(self):
        ws = _ws("similar")
        eng = EmbeddingsEngine(vocab_path=ws / "vocab.json")
        corpus = [
            "create a react project",
            "build a react app",
            "deploy kubernetes cluster",
            "read csv file",
        ]
        eng.fit(corpus)
        v1 = eng.embed("create a react project")
        v2 = eng.embed("build a react app")
        sim = cosine_similarity(v1, v2)
        self.assertGreater(sim, 0.3)

    def test_different_texts_low_cosine(self):
        ws = _ws("different")
        eng = EmbeddingsEngine(vocab_path=ws / "vocab.json")
        corpus = [
            "create a react project",
            "read csv file from disk",
            "send whatsapp message to alice",
            "deploy kubernetes cluster on aws",
        ]
        eng.fit(corpus)
        v1 = eng.embed("create a react project")
        v2 = eng.embed("deploy kubernetes cluster on aws")
        sim = cosine_similarity(v1, v2)
        # Different topics — should be less similar than near-identical texts
        v_same = eng.embed("create a react project")
        sim_same = cosine_similarity(v1, v_same)
        self.assertLess(sim, sim_same)

    def test_vocab_persists(self):
        ws = _ws("persist")
        eng1 = EmbeddingsEngine(vocab_path=ws / "vocab.json")
        eng1.fit(["hello world", "foo bar"])
        self.assertGreater(eng1.vocab_size, 0)

        eng2 = EmbeddingsEngine(vocab_path=ws / "vocab.json")
        self.assertEqual(eng2.vocab_size, eng1.vocab_size)

    def test_empty_text_returns_empty(self):
        eng = EmbeddingsEngine()
        vec = eng.embed("")
        self.assertEqual(vec, [])


if __name__ == "__main__":
    unittest.main()
