"""Redis cache layer for accelerating storage operations.

Provides read-through cache for JSON registries and write-behind
for execution history. Does NOT replace file storage — augments it.

Usage:
    from system.infrastructure.redis_cache import RedisCache
    cache = RedisCache(queue)  # queue from create_queue()
    cache.cache_json("history", entries)  # write to Redis
    entries = cache.get_json("history")   # read from Redis (fast)
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 3600  # 1 hour


class RedisCache:
    """Optional Redis cache layer for storage acceleration."""

    def __init__(self, queue: Any) -> None:
        self._queue = queue
        self._available = queue is not None and queue.is_redis

    @property
    def available(self) -> bool:
        return self._available

    def cache_json(self, key: str, data: Any, ttl: int = DEFAULT_TTL) -> bool:
        """Cache a JSON-serializable value in Redis."""
        if not self._available:
            return False
        try:
            self._queue._client.setex(f"capos:cache:{key}", ttl, json.dumps(data, default=str))
            return True
        except Exception:
            return False

    def get_json(self, key: str) -> Any | None:
        """Get a cached value from Redis. Returns None on miss."""
        if not self._available:
            return None
        try:
            raw = self._queue._client.get(f"capos:cache:{key}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def invalidate(self, key: str) -> None:
        """Remove a cached value."""
        if not self._available:
            return
        try:
            self._queue._client.delete(f"capos:cache:{key}")
        except Exception:
            pass

    def cache_hash(self, key: str, mapping: dict[str, str], ttl: int = DEFAULT_TTL) -> bool:
        """Cache a dict as Redis hash."""
        if not self._available:
            return False
        try:
            rkey = f"capos:cache:{key}"
            self._queue._client.hset(rkey, mapping=mapping)
            self._queue._client.expire(rkey, ttl)
            return True
        except Exception:
            return False

    def get_hash(self, key: str) -> dict[str, str] | None:
        """Get a cached hash from Redis."""
        if not self._available:
            return None
        try:
            result = self._queue._client.hgetall(f"capos:cache:{key}")
            return result if result else None
        except Exception:
            return None

    def store_session(self, session_id: str, data: dict, ttl: int = 7200) -> bool:
        """Store an agent session in Redis (survives process restarts)."""
        if not self._available:
            return False
        try:
            self._queue._client.setex(f"capos:session:{session_id}", ttl, json.dumps(data, default=str))
            return True
        except Exception:
            return False

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve an agent session from Redis."""
        if not self._available:
            return None
        try:
            raw = self._queue._client.get(f"capos:session:{session_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def delete_session(self, session_id: str) -> None:
        """Remove an agent session."""
        if not self._available:
            return
        try:
            self._queue._client.delete(f"capos:session:{session_id}")
        except Exception:
            pass
