"""Text embeddings engine using TF-IDF (pure Python, zero external deps).

Strategy:
  1. Primary: TF-IDF with term frequencies and inverse document frequencies
     computed from a fitted corpus.  Vectors are L2-normalized.
  2. Fallback: if the corpus is not fitted, uses raw term frequency on
     the input text alone (bag-of-words).

Vocabulary is persisted to ``vocab_path`` so it survives restarts.
Embeddings are cached in-memory by text hash.

Rule 5: all operations are wrapped so they never block execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from threading import RLock
from typing import Any


_WORD_RE = re.compile(r"[a-z0-9]+")


class EmbeddingsEngine:
    """Generates text embeddings using TF-IDF (no external dependencies)."""

    def __init__(self, vocab_path: str | Path | None = None):
        self._vocab_path = Path(vocab_path).resolve() if vocab_path else None
        self._lock = RLock()
        self._vocab: list[str] = []          # ordered term list
        self._idf: dict[str, float] = {}     # term → IDF weight
        self._cache: dict[str, list[float]] = {}
        self._load_vocab()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, corpus: list[str]) -> None:
        """Build vocabulary + IDF weights from a corpus of texts."""
        if not corpus:
            return
        with self._lock:
            df: dict[str, int] = {}
            for doc in corpus:
                terms = set(_tokenize(doc))
                for t in terms:
                    df[t] = df.get(t, 0) + 1

            n = len(corpus)
            self._idf = {t: math.log((1 + n) / (1 + count)) + 1 for t, count in df.items()}
            self._vocab = sorted(self._idf.keys())
            self._cache.clear()
            self._save_vocab()

    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding vector for *text*."""
        h = _hash(text)
        with self._lock:
            cached = self._cache.get(h)
            if cached is not None:
                return list(cached)

        vec = self._compute(text)
        with self._lock:
            self._cache[h] = vec
        return list(vec)

    @property
    def vocab_size(self) -> int:
        with self._lock:
            return len(self._vocab)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute(self, text: str) -> list[float]:
        tokens = _tokenize(text)
        if not tokens:
            return []

        with self._lock:
            vocab = list(self._vocab)
            idf = dict(self._idf)

        if not vocab:
            # Fallback: raw term frequency vector (no fitted corpus)
            return self._raw_tf_vector(tokens)

        # TF-IDF vector aligned to vocabulary
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        max_tf = max(tf.values()) if tf else 1

        vec: list[float] = []
        for term in vocab:
            tf_val = 0.5 + 0.5 * (tf.get(term, 0) / max_tf)
            idf_val = idf.get(term, 1.0)
            vec.append(tf_val * idf_val)

        return _normalize(vec)

    @staticmethod
    def _raw_tf_vector(tokens: list[str]) -> list[float]:
        """Bag-of-words fallback when no vocabulary is fitted."""
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        terms = sorted(tf.keys())
        total = len(tokens) or 1
        vec = [tf[t] / total for t in terms]
        return _normalize(vec)

    def _load_vocab(self) -> None:
        if self._vocab_path is None or not self._vocab_path.exists():
            return
        try:
            raw = json.loads(self._vocab_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._vocab = raw.get("vocab", [])
                self._idf = raw.get("idf", {})
        except (json.JSONDecodeError, OSError):
            pass

    def _save_vocab(self) -> None:
        if self._vocab_path is None:
            return
        try:
            self._vocab_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"vocab": self._vocab, "idf": self._idf}
            self._vocab_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _normalize(vec: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(x * x for x in vec))
    if magnitude < 1e-10:
        return vec
    return [x / magnitude for x in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(min_len))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0
    return dot / (mag_a * mag_b)
