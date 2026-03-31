"""WorkerRegistry — tracks active worker processes and their status.

Usage:
    from system.infrastructure.worker_registry import WorkerRegistry
    registry = WorkerRegistry()
    registry.register("telegram_worker", worker_process)
    registry.get_status()  # {"telegram_worker": {"alive": True, "pid": 1234, ...}}
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """Central registry for all active worker processes."""

    def __init__(self) -> None:
        self._workers: dict[str, Any] = {}

    def register(self, name: str, worker: Any) -> None:
        """Register a worker process."""
        self._workers[name] = worker
        logger.info("Registered worker: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a worker from the registry."""
        self._workers.pop(name, None)

    def get(self, name: str) -> Any | None:
        """Get a worker by name."""
        return self._workers.get(name)

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Return status of all registered workers."""
        result = {}
        for name, worker in self._workers.items():
            try:
                result[name] = worker.get_status()
            except Exception:
                result[name] = {"name": name, "alive": False, "error": "status check failed"}
        return result

    def stop_all(self) -> None:
        """Stop all registered workers."""
        for name, worker in self._workers.items():
            try:
                worker.stop()
                logger.info("Stopped worker: %s", name)
            except Exception as exc:
                logger.error("Failed to stop worker %s: %s", name, exc)
        self._workers.clear()

    def restart(self, name: str) -> bool:
        """Restart a specific worker."""
        worker = self._workers.get(name)
        if not worker:
            return False
        try:
            worker.stop()
            worker.start()
            return True
        except Exception as exc:
            logger.error("Failed to restart worker %s: %s", name, exc)
            return False

    @property
    def count(self) -> int:
        return len(self._workers)

    @property
    def alive_count(self) -> int:
        return sum(1 for w in self._workers.values() if w.is_alive())
