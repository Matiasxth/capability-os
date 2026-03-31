"""WorkerProcess — spawn, monitor, and manage worker subprocesses.

Usage:
    from system.infrastructure.worker_process import WorkerProcess
    worker = WorkerProcess("telegram_worker", queue, script="system/workers/telegram_worker.py")
    worker.start()
    worker.is_alive()  # True
    worker.stop()
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkerProcess:
    """Manages a single worker subprocess with health monitoring and auto-restart."""

    def __init__(
        self,
        name: str,
        queue: Any,
        script: str | None = None,
        env: dict[str, str] | None = None,
        auto_restart: bool = True,
        max_restarts: int = 5,
        restart_delay: float = 3.0,
    ) -> None:
        self.name = name
        self._queue = queue
        self._script = script or f"system/workers/{name}.py"
        self._env = env or {}
        self._auto_restart = auto_restart
        self._max_restarts = max_restarts
        self._restart_delay = restart_delay
        self._process: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._running = False
        self._restart_count = 0
        self._project_root = str(Path(__file__).resolve().parents[2])

    def start(self) -> None:
        """Start the worker subprocess."""
        if self._running:
            return
        self._running = True
        self._restart_count = 0
        self._spawn()
        if self._auto_restart:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name=f"worker-monitor-{self.name}",
            )
            self._monitor_thread.start()
        logger.info("Worker [%s] started (pid=%s)", self.name, self._process.pid if self._process else "?")

    def stop(self) -> None:
        """Stop the worker subprocess gracefully."""
        self._running = False
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception:
                pass
        logger.info("Worker [%s] stopped", self.name)

    def is_alive(self) -> bool:
        """Check if the worker process is running."""
        return self._process is not None and self._process.poll() is None

    def get_status(self) -> dict[str, Any]:
        """Return worker status information."""
        return {
            "name": self.name,
            "alive": self.is_alive(),
            "pid": self._process.pid if self._process else None,
            "restart_count": self._restart_count,
            "script": self._script,
        }

    def _spawn(self) -> None:
        """Spawn the worker subprocess."""
        env = {**os.environ, **self._env}
        env["CAPOS_WORKER_NAME"] = self.name
        env["CAPOS_PROJECT_ROOT"] = self._project_root
        env["PYTHONPATH"] = self._project_root

        # Pass Redis URL if available
        if self._queue.is_redis and hasattr(self._queue, "_client"):
            conn = self._queue._client.connection_pool.connection_kwargs
            host = conn.get("host", "127.0.0.1")
            port = conn.get("port", 6379)
            db = conn.get("db", 0)
            env["REDIS_URL"] = f"redis://{host}:{port}/{db}"

        script_path = os.path.join(self._project_root, self._script)
        self._process = subprocess.Popen(
            [sys.executable, script_path],
            env=env,
            cwd=self._project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _monitor_loop(self) -> None:
        """Monitor worker and auto-restart on crash."""
        while self._running:
            time.sleep(2)
            if not self._running:
                break
            if self._process and self._process.poll() is not None:
                exit_code = self._process.returncode
                if self._running and self._restart_count < self._max_restarts:
                    self._restart_count += 1
                    logger.warning(
                        "Worker [%s] crashed (exit=%s). Restarting (%d/%d)...",
                        self.name, exit_code, self._restart_count, self._max_restarts,
                    )
                    time.sleep(self._restart_delay)
                    if self._running:
                        self._spawn()
                elif self._restart_count >= self._max_restarts:
                    logger.error("Worker [%s] exceeded max restarts (%d). Giving up.", self.name, self._max_restarts)
                    self._running = False
