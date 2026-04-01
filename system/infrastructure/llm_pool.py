"""LLM Connection Pool — httpx-based HTTP client with retry and connection reuse.

Replaces raw urllib calls in LLMClient with:
  - Persistent HTTP connections (connection pool reuse)
  - Exponential backoff retry (1s, 2s, 4s, 8s, max 30s)
  - Configurable max concurrent requests via semaphore
  - Graceful fallback to urllib if httpx is not installed
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = int(os.environ.get("CAPOS_LLM_MAX_CONCURRENT", "4"))
_MAX_RETRIES = int(os.environ.get("CAPOS_LLM_MAX_RETRIES", "3"))
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0

# Retry on these HTTP status codes
_RETRIABLE_STATUSES = {429, 500, 502, 503, 504}


class LLMPoolError(RuntimeError):
    """Raised when LLM pool request fails after retries."""


class LLMPool:
    """HTTP connection pool with retry for LLM API calls."""

    def __init__(self, max_concurrent: int = _MAX_CONCURRENT, max_retries: int = _MAX_RETRIES) -> None:
        self._semaphore = threading.Semaphore(max_concurrent)
        self._max_retries = max_retries
        self._client: Any = None
        self._use_httpx = False

        try:
            import httpx
            self._client = httpx.Client(
                timeout=120.0,
                limits=httpx.Limits(
                    max_connections=max_concurrent * 2,
                    max_keepalive_connections=max_concurrent,
                ),
                headers={
                    "User-Agent": "CapabilityOS/1.0",
                    "Accept": "application/json",
                },
            )
            self._use_httpx = True
            logger.info("LLMPool: using httpx (%d concurrent, %d retries)", max_concurrent, max_retries)
        except ImportError:
            logger.info("LLMPool: httpx not installed, using urllib fallback (%d concurrent)", max_concurrent)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        """POST JSON with retry and concurrency limiting. Returns parsed response."""
        self._semaphore.acquire()
        try:
            return self._post_with_retry(url, payload, headers or {}, timeout_sec)
        finally:
            self._semaphore.release()

    def _post_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_sec: float,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._use_httpx:
                    return self._post_httpx(url, payload, headers, timeout_sec)
                else:
                    return self._post_urllib(url, payload, headers, timeout_sec)
            except LLMPoolError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
                    logger.warning(
                        "LLM request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1, self._max_retries + 1, wait, exc,
                    )
                    time.sleep(wait)

        raise LLMPoolError(f"LLM request failed after {self._max_retries + 1} attempts: {last_error}") from last_error

    def _post_httpx(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_sec: float,
    ) -> dict[str, Any]:
        merged_headers = {"Content-Type": "application/json"}
        merged_headers.update(headers)
        resp = self._client.post(
            url,
            json=payload,
            headers=merged_headers,
            timeout=max(1.0, timeout_sec),
        )
        if resp.status_code in _RETRIABLE_STATUSES:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        if resp.status_code >= 400:
            raise LLMPoolError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def _post_urllib(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_sec: float,
    ) -> dict[str, Any]:
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        merged_headers = {
            "Content-Type": "application/json",
            "User-Agent": "CapabilityOS/1.0",
            "Accept": "application/json",
        }
        merged_headers.update(headers)
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=merged_headers, method="POST")
        try:
            with urlopen(req, timeout=max(1.0, timeout_sec)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in _RETRIABLE_STATUSES:
                raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}") from exc
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMPoolError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMPoolError(f"Connection error: {exc.reason}") from exc

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass


# Singleton pool instance — created on first import
_pool: LLMPool | None = None
_pool_lock = threading.Lock()


def get_llm_pool() -> LLMPool:
    """Return the global LLM pool (lazy singleton)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = LLMPool()
    return _pool
