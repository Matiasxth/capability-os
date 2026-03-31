"""In-memory pub/sub event bus for real-time notifications.

Thread-safe. Emit is fire-and-forget — subscriber errors are silently
caught so emitters are never blocked or crashed.

Optionally bridges to Redis for cross-process event delivery via
``set_bridge(queue)``. When a bridge is active, events are published
to both local subscribers AND Redis.

Usage::

    from system.core.ui_bridge.event_bus import event_bus

    # Subscribe
    unsub = event_bus.subscribe(lambda evt: print(evt))

    # Emit (non-blocking, safe)
    event_bus.emit("telegram_message", {"chat_id": "123", "text": "hello"})

    # Unsubscribe
    unsub()

    # Optional: bridge to Redis for cross-process events
    event_bus.set_bridge(redis_queue)
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable


class EventBus:
    """Thread-safe synchronous pub/sub with optional Redis bridge."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        self._bridge: Any = None  # Optional MessageQueue for Redis

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe function."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Broadcast an event to all subscribers + Redis bridge. Never raises."""
        event: dict[str, Any] = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": data or {},
        }
        # Local subscribers
        self._emit_local(event)
        # Redis bridge (cross-process)
        if self._bridge is not None:
            try:
                self._bridge.publish(f"capos:events:{event_type}", event)
            except Exception:
                pass  # Redis failure should never break the emitter

    def _emit_local(self, event: dict[str, Any]) -> None:
        """Emit to in-process subscribers only (no Redis). Used by EventBridge to avoid loops."""
        with self._lock:
            listeners = list(self._subscribers)
        for cb in listeners:
            try:
                cb(event)
            except Exception:
                pass

    def set_bridge(self, queue: Any) -> None:
        """Connect a MessageQueue (Redis) for cross-process event delivery.

        Pass ``None`` to disconnect.
        """
        self._bridge = queue

    @property
    def has_bridge(self) -> bool:
        """True if Redis bridge is active."""
        return self._bridge is not None

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# Module-level singleton
event_bus = EventBus()
