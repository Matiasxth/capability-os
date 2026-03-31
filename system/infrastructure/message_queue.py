"""MessageQueue abstraction — Redis-backed or in-memory fallback.

Usage:
    from system.infrastructure.message_queue import create_queue
    queue = create_queue(settings)  # auto-detects Redis
    queue.push("my_queue", {"task": "process"})
    msg = queue.pop("my_queue", timeout=5)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterator, Protocol

logger = logging.getLogger(__name__)


class MessageQueue(Protocol):
    """Interface for message queue backends."""

    @property
    def is_redis(self) -> bool: ...

    def push(self, queue: str, message: dict) -> None:
        """Add a message to a named queue."""
        ...

    def pop(self, queue: str, timeout: int = 0) -> dict | None:
        """Remove and return a message from a queue. Returns None on timeout."""
        ...

    def publish(self, channel: str, message: dict) -> None:
        """Publish a message to a pub/sub channel."""
        ...

    def subscribe(self, channel: str) -> Iterator[dict]:
        """Subscribe to a pub/sub channel. Yields messages as they arrive."""
        ...

    def health_check(self) -> bool:
        """Return True if the queue backend is healthy."""
        ...


class RedisQueue:
    """Redis-backed message queue. Production-grade, multi-process safe."""

    def __init__(self, client: Any) -> None:
        self._client = client
        logger.info("MessageQueue: Redis connected")

    @property
    def is_redis(self) -> bool:
        return True

    def push(self, queue: str, message: dict) -> None:
        self._client.rpush(queue, json.dumps(message, default=str))

    def pop(self, queue: str, timeout: int = 0) -> dict | None:
        if timeout > 0:
            result = self._client.blpop(queue, timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        result = self._client.lpop(queue)
        if result:
            return json.loads(result)
        return None

    def publish(self, channel: str, message: dict) -> None:
        self._client.publish(channel, json.dumps(message, default=str))

    def subscribe(self, channel: str) -> Iterator[dict]:
        pubsub = self._client.pubsub()
        pubsub.subscribe(channel)
        for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    yield json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue

    def health_check(self) -> bool:
        try:
            return self._client.ping()
        except Exception:
            return False

    def queue_length(self, queue: str) -> int:
        return self._client.llen(queue)


class InMemoryQueue:
    """In-memory fallback when Redis is not available. Single-process only."""

    def __init__(self) -> None:
        self._queues: dict[str, deque] = defaultdict(deque)
        self._channels: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = defaultdict(threading.Event)
        logger.info("MessageQueue: In-memory fallback (no Redis)")

    @property
    def is_redis(self) -> bool:
        return False

    def push(self, queue: str, message: dict) -> None:
        with self._lock:
            self._queues[queue].append(message)
            self._events[queue].set()

    def pop(self, queue: str, timeout: int = 0) -> dict | None:
        if timeout > 0:
            self._events[queue].wait(timeout=timeout)
        with self._lock:
            q = self._queues[queue]
            if q:
                msg = q.popleft()
                if not q:
                    self._events[queue].clear()
                return msg
            self._events[queue].clear()
            return None

    def publish(self, channel: str, message: dict) -> None:
        with self._lock:
            callbacks = list(self._channels.get(channel, []))
        for cb in callbacks:
            try:
                cb(message)
            except Exception:
                pass

    def subscribe(self, channel: str) -> Iterator[dict]:
        q: deque = deque()
        event = threading.Event()

        def _handler(msg: dict) -> None:
            q.append(msg)
            event.set()

        with self._lock:
            self._channels[channel].append(_handler)

        try:
            while True:
                event.wait(timeout=1.0)
                while q:
                    yield q.popleft()
                event.clear()
        finally:
            with self._lock:
                try:
                    self._channels[channel].remove(_handler)
                except ValueError:
                    pass

    def health_check(self) -> bool:
        return True

    def queue_length(self, queue: str) -> int:
        with self._lock:
            return len(self._queues[queue])


def create_queue(settings: dict | None = None) -> MessageQueue:
    """Factory: returns RedisQueue if Redis available, else InMemoryQueue.

    Checks:
    1. settings.redis.url or settings.redis.host
    2. Tries to connect and ping
    3. Falls back to InMemoryQueue on any failure
    """
    settings = settings or {}
    redis_config = settings.get("redis", {})

    if not redis_config.get("enabled", True):
        logger.info("Redis disabled in settings — using in-memory queue")
        return InMemoryQueue()

    try:
        import redis as redis_lib

        url = redis_config.get("url")
        if not url:
            host = redis_config.get("host", "127.0.0.1")
            port = redis_config.get("port", 6379)
            db = redis_config.get("db", 0)
            password = redis_config.get("password")
            url = f"redis://{':{}'.format(password) + '@' if password else ''}{host}:{port}/{db}"

        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=redis_config.get("connect_timeout_s", 3),
        )
        client.ping()
        return RedisQueue(client)
    except ImportError:
        logger.info("redis package not installed — using in-memory queue")
        return InMemoryQueue()
    except Exception as exc:
        if redis_config.get("fallback_to_memory", True):
            logger.warning("Redis connection failed (%s) — using in-memory queue", exc)
            return InMemoryQueue()
        raise
