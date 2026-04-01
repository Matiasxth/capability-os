"""EventBridge — bidirectional bridge between in-process EventBus and Redis pub/sub.

Outbound: EventBus.emit() → Redis publish (per-type channel)
Inbound:  Redis psubscribe("capos:events:*") → EventBus._emit_local()

Supports automatic reconnection on Redis failures.

Usage:
    from system.infrastructure.event_bridge import EventBridge
    bridge = EventBridge(event_bus, queue)
    bridge.start()  # starts listening to Redis events and forwarding to local bus
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_EVENT_PATTERN = "capos:events:*"
RECONNECT_DELAY_S = 3
MAX_RECONNECT_DELAY_S = 30


class EventBridge:
    """Bridges the in-process EventBus to Redis pub/sub.

    - Outbound: EventBus.emit() publishes to Redis via bridge
    - Inbound: Redis pattern subscription forwards events to local EventBus
    - Auto-reconnects on Redis failures with exponential backoff
    """

    def __init__(self, event_bus: Any, queue: Any) -> None:
        self._bus = event_bus
        self._queue = queue
        self._listener_thread: threading.Thread | None = None
        self._running = False
        self._connected = threading.Event()

    def start(self) -> None:
        """Connect EventBus → Redis (outbound) and Redis → EventBus (inbound)."""
        # Outbound: EventBus.emit() also publishes to Redis
        self._bus.set_bridge(self._queue)
        logger.info("EventBridge: outbound connected (EventBus → Redis)")

        # Inbound: listen for events from Redis and emit locally
        if self._queue.is_redis:
            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop_with_reconnect,
                daemon=True,
                name="event-bridge-listener",
            )
            self._listener_thread.start()
            logger.info("EventBridge: inbound listener started (Redis → EventBus)")

    def stop(self) -> None:
        self._running = False
        self._bus.set_bridge(None)
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
            self._listener_thread = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def _listen_loop_with_reconnect(self) -> None:
        """Reconnecting wrapper around the listener loop."""
        delay = RECONNECT_DELAY_S
        while self._running:
            try:
                self._connected.set()
                delay = RECONNECT_DELAY_S  # reset on successful connection
                self._listen_loop()
            except Exception as exc:
                self._connected.clear()
                if not self._running:
                    break
                logger.warning(
                    "EventBridge listener disconnected (%s), reconnecting in %ds",
                    exc, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY_S)
        self._connected.clear()

    def _listen_loop(self) -> None:
        """Subscribe to Redis events via pattern and forward to local EventBus."""
        for event in self._queue.psubscribe(REDIS_EVENT_PATTERN):
            if not self._running:
                break
            if isinstance(event, dict) and "type" in event:
                # Emit locally WITHOUT re-publishing to Redis (avoid infinite loop)
                self._bus._emit_local(event)
