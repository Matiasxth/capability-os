"""Circuit breaker for LLM adapters.

After N consecutive failures, the circuit opens and skips the adapter
for M seconds. After M seconds, allows one probe request (half-open).
"""
from __future__ import annotations

import threading
import time

_STATE_CLOSED = "closed"
_STATE_OPEN = "open"
_STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-adapter circuit breaker."""

    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 60.0):
        self._threshold = max(1, failure_threshold)
        self._recovery = max(0.01, recovery_seconds)
        self._failures = 0
        self._state = _STATE_CLOSED
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == _STATE_OPEN and time.monotonic() - self._opened_at >= self._recovery:
                self._state = _STATE_HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        """Return True if the request should proceed."""
        s = self.state
        return s in (_STATE_CLOSED, _STATE_HALF_OPEN)

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = _STATE_CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._state = _STATE_OPEN
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = _STATE_CLOSED
            self._opened_at = 0.0
