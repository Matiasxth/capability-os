"""Simple sliding-window rate limiter for the HTTP server.

Per-IP token bucket. Localhost is exempt by default.
"""
from __future__ import annotations

import threading
import time
from typing import Any


class RateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(
        self,
        max_requests: int = 120,
        window_seconds: float = 60.0,
        exempt_ips: set[str] | None = None,
    ):
        self._max = max_requests
        self._window = window_seconds
        self._exempt = exempt_ips if exempt_ips is not None else {"127.0.0.1", "::1", "localhost"}
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        if ip in self._exempt:
            return True
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._buckets.get(ip)
            if bucket is None:
                self._buckets[ip] = [now]
                return True
            # Prune old entries
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

    def cleanup(self) -> None:
        """Remove empty buckets (call periodically if many IPs)."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            empty = [ip for ip, bucket in self._buckets.items() if not bucket or bucket[-1] <= cutoff]
            for ip in empty:
                del self._buckets[ip]
