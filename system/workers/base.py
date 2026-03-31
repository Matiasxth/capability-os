"""Base worker class for subprocess workers.

All workers inherit from this. Provides:
- Redis connection setup
- Graceful shutdown on SIGTERM/SIGINT
- Health reporting heartbeat
- Logging
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseWorker:
    """Base class for CapOS worker processes."""

    worker_name: str = "base"
    pool_size: int = 4

    def __init__(self) -> None:
        self._running = False
        self._pool: ThreadPoolExecutor | None = None
        self._queue: Any = None

    def bootstrap(self) -> None:
        """Initialize the worker: connect to Redis, set up signal handlers."""
        # Project root from env
        project_root = os.environ.get("CAPOS_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Logging
        logging.basicConfig(
            level=logging.INFO,
            format=f"[%(asctime)s] [%(levelname)s] [{self.worker_name}] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Connect to Redis
        redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        try:
            from system.infrastructure.message_queue import RedisQueue
            import redis
            client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
            client.ping()
            self._queue = RedisQueue(client)
            logger.info("Connected to Redis: %s", redis_url)
        except Exception as exc:
            logger.error("Failed to connect to Redis: %s", exc)
            sys.exit(1)

        # Thread pool for parallel message processing
        self._pool = ThreadPoolExecutor(max_workers=self.pool_size, thread_name_prefix=self.worker_name)

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._running = True
        logger.info("Worker initialized (pool_size=%d)", self.pool_size)

    def run(self) -> None:
        """Main loop. Override in subclasses."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Clean shutdown."""
        self._running = False
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=False)
        logger.info("Worker shutdown complete")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        logger.info("Received signal %d — shutting down", signum)
        self.shutdown()

    def heartbeat(self) -> None:
        """Report health to Redis."""
        if self._queue and self._queue.is_redis:
            try:
                self._queue._client.setex(
                    f"capos:worker:{self.worker_name}:heartbeat",
                    30,  # expires in 30s
                    str(int(time.time())),
                )
            except Exception:
                pass

    def load_settings(self) -> dict:
        """Load settings from the project's settings.json."""
        project_root = os.environ.get("CAPOS_PROJECT_ROOT", ".")
        settings_path = Path(project_root) / "system" / "settings.json"
        if settings_path.exists():
            import json
            return json.loads(settings_path.read_text(encoding="utf-8"))
        return {}
