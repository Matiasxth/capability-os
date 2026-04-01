"""Tool Execution Pool — dedicated ThreadPoolExecutor for tool calls.

Separates tool execution from the HTTP thread pool so that long-running
tools (browser, file ops, scripts) don't block API request handlers.

Timeouts are enforced per security level:
  - Level 1 (free):      30s
  - Level 2 (confirm):   60s
  - Level 3 (protected): 120s
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Callable

logger = logging.getLogger(__name__)

_POOL_SIZE = int(os.environ.get("CAPOS_TOOL_POOL_SIZE", "8"))

SECURITY_TIMEOUTS: dict[int, float] = {
    1: 30.0,
    2: 60.0,
    3: 120.0,
}
DEFAULT_TIMEOUT = 60.0


class ToolExecutionPool:
    """Dedicated thread pool for tool execution with per-level timeouts."""

    def __init__(self, max_workers: int = _POOL_SIZE) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="tool-exec",
        )
        self._running = True
        logger.info("ToolExecutionPool started (%d workers)", max_workers)

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        security_level: int = 1,
        timeout: float | None = None,
    ) -> Any:
        """Submit a tool call and wait for result with timeout.

        Parameters
        ----------
        fn : callable
            The tool handler to execute.
        *args :
            Arguments passed to the handler.
        security_level : int
            Tool security level (1-3), determines default timeout.
        timeout : float | None
            Override timeout in seconds.
        """
        if not self._running:
            raise RuntimeError("ToolExecutionPool is shut down")

        effective_timeout = timeout or SECURITY_TIMEOUTS.get(security_level, DEFAULT_TIMEOUT)
        future: Future[Any] = self._pool.submit(fn, *args)

        try:
            return future.result(timeout=effective_timeout)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError(
                f"Tool execution timed out after {effective_timeout}s "
                f"(security_level={security_level})"
            )

    def shutdown(self) -> None:
        """Shutdown the pool gracefully."""
        self._running = False
        self._pool.shutdown(wait=False)
        logger.info("ToolExecutionPool shut down")
