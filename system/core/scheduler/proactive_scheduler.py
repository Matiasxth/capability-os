"""Proactive Scheduler — executes scheduled tasks and system cycles.

Three cycles:
  - Quick (every 30min): run ready tasks from queue
  - Deep (every 4h): analyze patterns, optimize
  - Daily (configurable): generate summary, prepare next day
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from .task_queue import TaskQueue


class ProactiveScheduler:
    """Runs scheduled tasks and proactive system cycles."""

    def __init__(
        self,
        task_queue: TaskQueue,
        agent_loop: Any = None,
        agent_registry: Any = None,
        whatsapp_manager: Any = None,
    ) -> None:
        self._queue = task_queue
        self._agent_loop = agent_loop
        self._agent_registry = agent_registry
        self._whatsapp = whatsapp_manager
        self._running = False
        self._threads: list[threading.Thread] = []
        self._execution_log: list[dict[str, Any]] = []

    @property
    def running(self) -> bool:
        return self._running

    @property
    def execution_log(self) -> list[dict[str, Any]]:
        return self._execution_log[-30:]

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        cycles = [
            ("quick", 1800),   # every 30 min
            ("deep", 14400),   # every 4 hours
        ]
        for name, interval in cycles:
            t = threading.Thread(target=self._cycle, args=(name, interval), daemon=True, name=f"scheduler-{name}")
            self._threads.append(t)
            t.start()

        # Task checker runs every 60s
        t = threading.Thread(target=self._task_checker, daemon=True, name="scheduler-tasks")
        self._threads.append(t)
        t.start()

        print("[SCHEDULER] Started (quick=30m, deep=4h, tasks=60s)", flush=True)

    def stop(self) -> None:
        self._running = False

    def run_task_now(self, task_id: str) -> dict[str, Any]:
        """Manually trigger a task."""
        task = self._queue.get(task_id)
        if task is None:
            return {"status": "error", "error": "Task not found"}
        return self._execute_task(task)

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "queue_size": len(self._queue.list()),
            "ready_tasks": len(self._queue.get_ready()),
            "total_executions": len(self._execution_log),
        }

    # ------------------------------------------------------------------
    # Cycles
    # ------------------------------------------------------------------

    def _cycle(self, name: str, interval: int) -> None:
        # Initial delay to let system boot
        time.sleep(30)
        while self._running:
            try:
                if name == "quick":
                    self._quick_cycle()
                elif name == "deep":
                    self._deep_cycle()
            except Exception as exc:
                print(f"[SCHEDULER] {name} error: {exc}", flush=True)
            time.sleep(interval)

    def _task_checker(self) -> None:
        """Check and run ready tasks every 60 seconds."""
        time.sleep(10)  # Initial delay
        while self._running:
            try:
                ready = self._queue.get_ready()
                for task in ready:
                    try:
                        result = self._execute_task(task)
                        self._queue.mark_completed(task["id"], result)
                    except Exception as exc:
                        self._queue.mark_completed(task["id"], {"status": "error", "error": str(exc)})
            except Exception:
                pass
            time.sleep(60)

    def _quick_cycle(self) -> None:
        """Quick cycle: run ready tasks (already handled by task_checker)."""
        # Additional quick checks could go here
        pass

    def _deep_cycle(self) -> None:
        """Deep cycle: analyze usage patterns."""
        # Future: analyze execution history, suggest optimizations
        self._log_execution("deep_cycle", "completed", "Deep analysis cycle ran")

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def _execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a single task using the AgentLoop."""
        action = task.get("action", {})
        action_type = action.get("type", "agent_message")
        message = action.get("message", task.get("description", ""))

        print(f"[SCHEDULER] Executing: {task['description'][:50]}", flush=True)

        if action_type == "agent_message" and self._agent_loop:
            # Get agent config if specified
            agent_config = None
            if task.get("agent_id") and self._agent_registry:
                agent_config = self._agent_registry.get(task["agent_id"])

            # Run through agent loop
            final_text = ""
            try:
                gen = self._agent_loop.run(message, agent_config=agent_config)
                for event in gen:
                    if event.get("event") == "agent_response":
                        final_text = event.get("text", "")
            except StopIteration:
                pass
            except Exception as exc:
                final_text = f"Error: {exc}"

            # Send result to channel if configured
            if task.get("channel") and final_text:
                self._send_to_channel(task["channel"], final_text)

            result = {"status": "success", "response": final_text[:500]}
            self._log_execution(task["id"], "success", final_text[:100])
            return result

        return {"status": "error", "error": f"Unknown action type: {action_type}"}

    def _send_to_channel(self, channel: str, text: str) -> None:
        """Send task result to a messaging channel."""
        try:
            if channel == "whatsapp" and self._whatsapp:
                # Send to first configured user or owner
                self._whatsapp.send_message("owner", text[:4000])
            # Future: telegram, slack, discord channels
        except Exception as exc:
            print(f"[SCHEDULER] Channel send error: {exc}", flush=True)

    def _log_execution(self, task_id: str, status: str, detail: str) -> None:
        self._execution_log.append({
            "task_id": task_id,
            "status": status,
            "detail": detail[:200],
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        if len(self._execution_log) > 100:
            self._execution_log = self._execution_log[-50:]
