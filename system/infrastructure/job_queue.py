"""Distributed job queue for async task execution.

Redis-backed job queue with status tracking and result storage.
Used for long-running operations: capability execution, agent sessions, LLM calls.

Usage:
    from system.infrastructure.job_queue import JobQueue
    jq = JobQueue(redis_queue)
    job_id = jq.submit("execute_capability", {"capability_id": "fs.read", "inputs": {...}})
    status = jq.status(job_id)   # "queued" | "running" | "completed" | "failed"
    result = jq.result(job_id)   # dict or None
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

JOB_TTL = 3600  # 1 hour result retention
JOB_QUEUE_KEY = "capos:jobs:queue"
JOB_PREFIX = "capos:jobs:"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    """Represents a submitted job."""

    __slots__ = ("id", "type", "payload", "status", "result", "error", "created_at", "started_at", "completed_at")

    def __init__(self, job_type: str, payload: dict, job_id: str | None = None) -> None:
        self.id = job_id or uuid.uuid4().hex[:12]
        self.type = job_type
        self.payload = payload
        self.status = JobStatus.QUEUED
        self.result: dict | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        job = cls(data["type"], data.get("payload", {}), job_id=data["id"])
        job.status = JobStatus(data.get("status", "queued"))
        job.result = data.get("result")
        job.error = data.get("error")
        job.created_at = data.get("created_at", time.time())
        job.started_at = data.get("started_at")
        job.completed_at = data.get("completed_at")
        return job


class JobQueue:
    """Redis-backed async job queue with status tracking.

    Supports both Redis (distributed) and in-memory (single-process) modes.
    """

    def __init__(self, queue: Any) -> None:
        self._queue = queue
        self._is_redis = queue is not None and queue.is_redis
        # In-memory fallback storage
        self._local_jobs: dict[str, Job] = {}
        self._local_lock = threading.Lock()
        # Registered handlers
        self._handlers: dict[str, Callable] = {}
        # Worker threads
        self._workers: list[threading.Thread] = []
        self._running = False

    @property
    def is_distributed(self) -> bool:
        return self._is_redis

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(self, job_type: str, payload: dict | None = None) -> str:
        """Submit a job for async execution. Returns job_id."""
        job = Job(job_type, payload or {})

        if self._is_redis:
            client = self._queue._client
            # Store job metadata
            client.setex(
                f"{JOB_PREFIX}{job.id}",
                JOB_TTL,
                json.dumps(job.to_dict(), default=str),
            )
            # Push to work queue
            self._queue.push(JOB_QUEUE_KEY, {"job_id": job.id})
        else:
            with self._local_lock:
                self._local_jobs[job.id] = job

            # Execute immediately in local mode if handler registered
            handler = self._handlers.get(job_type)
            if handler:
                threading.Thread(
                    target=self._execute_local, args=(job, handler), daemon=True
                ).start()

        logger.debug("Job submitted: %s (type=%s)", job.id, job_type)
        return job.id

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def status(self, job_id: str) -> str | None:
        """Get job status. Returns None if job not found."""
        job = self._get_job(job_id)
        return job.status.value if job else None

    def result(self, job_id: str) -> dict | None:
        """Get job result. Returns None if not completed."""
        job = self._get_job(job_id)
        if job and job.status == JobStatus.COMPLETED:
            return job.result
        return None

    def get(self, job_id: str) -> dict | None:
        """Get full job info as dict."""
        job = self._get_job(job_id)
        return job.to_dict() if job else None

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job. Returns True if cancelled."""
        job = self._get_job(job_id)
        if job and job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            self._save_job(job)
            return True
        return False

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def register_handler(self, job_type: str, handler: Callable[[dict], dict]) -> None:
        """Register a handler function for a job type.

        Handler signature: ``(payload: dict) -> dict`` (returns result).
        Exceptions are caught and stored as job errors.
        """
        self._handlers[job_type] = handler

    def start_workers(self, count: int = 2) -> None:
        """Start worker threads that process jobs from the queue."""
        self._running = True
        for i in range(count):
            t = threading.Thread(
                target=self._worker_loop, daemon=True, name=f"job-worker-{i}"
            )
            t.start()
            self._workers.append(t)
        logger.info("JobQueue: %d workers started (redis=%s)", count, self._is_redis)

    def stop_workers(self) -> None:
        """Stop all worker threads."""
        self._running = False
        for t in self._workers:
            t.join(timeout=5)
        self._workers.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Main worker loop — pops jobs from queue and executes."""
        while self._running:
            try:
                if self._is_redis:
                    msg = self._queue.pop(JOB_QUEUE_KEY, timeout=2)
                    if msg and "job_id" in msg:
                        job = self._get_job(msg["job_id"])
                        if job and job.status == JobStatus.QUEUED:
                            handler = self._handlers.get(job.type)
                            if handler:
                                self._execute_job(job, handler)
                            else:
                                job.status = JobStatus.FAILED
                                job.error = f"No handler for job type: {job.type}"
                                self._save_job(job)
                else:
                    time.sleep(0.5)  # In-memory mode uses direct dispatch
            except Exception as exc:
                logger.error("Job worker error: %s", exc)
                time.sleep(1)

    def _execute_job(self, job: Job, handler: Callable) -> None:
        """Execute a job with status tracking."""
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        self._save_job(job)

        try:
            result = handler(job.payload)
            job.status = JobStatus.COMPLETED
            job.result = result if isinstance(result, dict) else {"result": result}
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)[:500]
            logger.warning("Job %s failed: %s", job.id, exc)
        finally:
            job.completed_at = time.time()
            self._save_job(job)

        # Notify via event bus
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("job_completed", {
                "job_id": job.id,
                "type": job.type,
                "status": job.status.value,
                "duration_ms": int((job.completed_at - (job.started_at or job.created_at)) * 1000),
            })
        except Exception:
            pass

    def _execute_local(self, job: Job, handler: Callable) -> None:
        """Execute a job in local mode (no Redis)."""
        self._execute_job(job, handler)

    def _get_job(self, job_id: str) -> Job | None:
        """Retrieve a job from Redis or local storage."""
        if self._is_redis:
            try:
                raw = self._queue._client.get(f"{JOB_PREFIX}{job_id}")
                if raw:
                    return Job.from_dict(json.loads(raw))
            except Exception:
                pass
            return None
        else:
            with self._local_lock:
                return self._local_jobs.get(job_id)

    def _save_job(self, job: Job) -> None:
        """Persist job state to Redis or local storage."""
        if self._is_redis:
            try:
                self._queue._client.setex(
                    f"{JOB_PREFIX}{job.id}",
                    JOB_TTL,
                    json.dumps(job.to_dict(), default=str),
                )
            except Exception:
                pass
        else:
            with self._local_lock:
                self._local_jobs[job.id] = job
