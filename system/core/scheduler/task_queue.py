"""Task Queue — persistent queue of scheduled tasks.

Tasks are stored in workspace/queue.json and executed by the ProactiveScheduler.
Each task has a schedule (interval or cron-like), an action, and a target channel.
"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


SCHEDULE_INTERVALS = {
    "every_30min": 1800,
    "every_hour": 3600,
    "every_4hours": 14400,
    "daily_09:00": "cron_09:00",
    "daily_18:00": "cron_18:00",
    "daily_21:00": "cron_21:00",
}


class TaskQueue:
    """Persistent task queue with scheduling."""

    def __init__(self, data_path: str | Path, db: Any = None) -> None:
        self._path = Path(data_path).resolve()
        self._lock = RLock()
        self._tasks: dict[str, dict[str, Any]] = {}
        self._repo: Any = None
        if db is not None:
            try:
                from system.infrastructure.repositories.queue_repo import QueueRepository
                self._repo = QueueRepository(db)
            except Exception:
                pass
        self._load()

    def add(
        self,
        description: str,
        schedule: str = "daily_09:00",
        action_type: str = "agent_message",
        action_message: str = "",
        agent_id: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        if not description.strip():
            raise ValueError("Task description required")
        with self._lock:
            task_id = f"task_{uuid4().hex[:8]}"
            task: dict[str, Any] = {
                "id": task_id,
                "description": description.strip(),
                "schedule": schedule,
                "action": {"type": action_type, "message": action_message or description},
                "agent_id": agent_id,
                "channel": channel,
                "enabled": True,
                "last_run": None,
                "next_run": self._calc_next_run(schedule),
                "run_count": 0,
                "last_result": None,
                "created_at": _now(),
            }
            self._tasks[task_id] = task
            self._save()
            return deepcopy(task)

    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Task '{task_id}' not found")
            allowed = {"description", "schedule", "action", "agent_id", "channel", "enabled"}
            for k, v in fields.items():
                if k in allowed:
                    task[k] = v
            if "schedule" in fields:
                task["next_run"] = self._calc_next_run(task["schedule"])
            self._save()
            return deepcopy(task)

    def remove(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._tasks:
                return False
            del self._tasks[task_id]
            self._save()
            return True

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return deepcopy(t) if t else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(t) for t in self._tasks.values()]

    def get_ready(self) -> list[dict[str, Any]]:
        """Return tasks that are ready to execute now."""
        now = _now()
        ready = []
        with self._lock:
            for task in self._tasks.values():
                if not task.get("enabled"):
                    continue
                next_run = task.get("next_run")
                if next_run and next_run <= now:
                    ready.append(deepcopy(task))
        return ready

    def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["last_run"] = _now()
            task["last_result"] = result
            task["run_count"] = task.get("run_count", 0) + 1
            task["next_run"] = self._calc_next_run(task["schedule"])
            self._save()

    def _calc_next_run(self, schedule: str) -> str:
        """Calculate next run time based on schedule."""
        now = datetime.now(timezone.utc)

        # Interval-based
        interval = SCHEDULE_INTERVALS.get(schedule)
        if isinstance(interval, int):
            from datetime import timedelta
            return (now + timedelta(seconds=interval)).isoformat().replace("+00:00", "Z")

        # Cron-like daily
        if isinstance(interval, str) and interval.startswith("cron_"):
            hour_min = interval[5:]
            parts = hour_min.split(":")
            target_hour = int(parts[0])
            target_min = int(parts[1]) if len(parts) > 1 else 0
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            if target <= now:
                from datetime import timedelta
                target += timedelta(days=1)
            return target.isoformat().replace("+00:00", "Z")

        # Unknown schedule — run in 1 hour
        from datetime import timedelta
        return (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    def _load(self) -> None:
        with self._lock:
            # Try DB first
            if self._repo is not None:
                try:
                    rows = self._repo.list_all()
                    if rows:
                        for t in rows:
                            if isinstance(t, dict) and "id" in t:
                                self._tasks[t["id"]] = t
                        return
                except Exception:
                    pass
            # Fallback: JSON file
            if not self._path.exists():
                self._tasks = {}
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for t in raw.get("tasks", []):
                    if isinstance(t, dict) and "id" in t:
                        self._tasks[t["id"]] = t
                # Migrate JSON data into DB
                if self._repo is not None and self._tasks:
                    for task in self._tasks.values():
                        try:
                            self._repo.add(task)
                        except Exception:
                            pass
            except (json.JSONDecodeError, OSError):
                self._tasks = {}

    def _save(self) -> None:
        # Write to DB if available
        if self._repo is not None:
            try:
                for task in self._tasks.values():
                    self._repo.add(task)
            except Exception:
                pass
        # Always write JSON as backup
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"tasks": list(self._tasks.values())}
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
