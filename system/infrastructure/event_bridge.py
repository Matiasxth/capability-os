"""EventBridge — extends EventBus to publish events to Redis for cross-process delivery.

Usage:
    from system.infrastructure.event_bridge import EventBridge
    bridge = EventBridge(event_bus, queue)
    bridge.start()  # starts listening to Redis events and forwarding to local bus
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

REDIS_EVENT_CHANNEL = "capos:events"


class EventBridge:
    """Bridges the in-process EventBus to Redis pub/sub.

    - When EventBus.emit() fires, the bridge also publishes to Redis
    - When Redis receives events from workers, the bridge emits them locally
    """

    def __init__(self, event_bus: Any, queue: Any) -> None:
        self._bus = event_bus
        self._queue = queue
        self._listener_thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Connect EventBus → Redis (outbound) and Redis → EventBus (inbound)."""
        # Outbound: patch EventBus to also publish to Redis
        self._bus.set_bridge(self._queue)
        logger.info("EventBridge: outbound connected (EventBus → Redis)")

        # Inbound: listen for events from Redis and emit locally
        if self._queue.is_redis:
            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="event-bridge-listener",
            )
            self._listener_thread.start()
            logger.info("EventBridge: inbound listener started (Redis → EventBus)")

    def stop(self) -> None:
        self._running = False
        self._bus.set_bridge(None)
        if self._listener_thread:
            self._listener_thread.join(timeout=3)
            self._listener_thread = None

    def _listen_loop(self) -> None:
        """Subscribe to Redis events channel and forward to local EventBus."""
        try:
            for event in self._queue.subscribe(f"{REDIS_EVENT_CHANNEL}:*"):
                if not self._running:
                    break
                if isinstance(event, dict) and "type" in event:
                    # Emit locally WITHOUT re-publishing to Redis (avoid infinite loop)
                    self._bus._emit_local(event)
        except Exception as exc:
            if self._running:
                logger.error("EventBridge listener error: %s", exc)
