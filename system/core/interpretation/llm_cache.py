"""Thread-safe LRU cache for LLM responses with TTL expiration.

Caches by hash(system_prompt + user_prompt). Same question within
TTL window returns instantly without an API call.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any


class LLMCache:
    """LRU cache with per-entry TTL."""

    def __init__(self, max_entries: int = 200, ttl_seconds: float = 300.0):
        self._max = max(1, max_entries)
        self._ttl = max(0.01, ttl_seconds)
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()  # key → (response, expire_at)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(system_prompt: str, user_prompt: str) -> str:
        raw = (system_prompt + "\x00" + user_prompt).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def get(self, system_prompt: str, user_prompt: str) -> str | None:
        """Return cached response or None if miss/expired."""
        key = self._key(system_prompt, user_prompt)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            response, expire_at = entry
            if time.monotonic() > expire_at:
                del self._cache[key]
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            return response

    def put(self, system_prompt: str, user_prompt: str, response: str) -> None:
        """Store a response in the cache."""
        key = self._key(system_prompt, user_prompt)
        expire_at = time.monotonic() + self._ttl
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (response, expire_at)
            else:
                self._cache[key] = (response, expire_at)
                if len(self._cache) > self._max:
                    self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"size": len(self._cache), "max": self._max, "hits": self._hits, "misses": self._misses, "ttl": self._ttl}
