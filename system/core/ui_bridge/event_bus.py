"""In-memory pub/sub event bus for real-time notifications.

Thread-safe. Emit is fire-and-forget — subscriber errors are silently
caught so emitters are never blocked or crashed.

Usage::

    from system.core.ui_bridge.event_bus import event_bus

    # Subscribe
    unsub = event_bus.subscribe(lambda evt: print(evt))

    # Emit (non-blocking, safe)
    event_bus.emit("telegram_message", {"chat_id": "123", "text": "hello"})

    # Unsubscribe
    unsub()
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable


class EventBus:
    """Thread-safe synchronous pub/sub."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()

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
        """Broadcast an event to all subscribers. Never raises."""
        event: dict[str, Any] = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": data or {},
        }
        with self._lock:
            listeners = list(self._subscribers)
        for cb in listeners:
            try:
                cb(event)
            except Exception:
                pass  # Never let a bad subscriber break the emitter

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# Module-level singleton
event_bus = EventBus()
