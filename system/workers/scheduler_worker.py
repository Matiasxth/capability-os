#!/usr/bin/env python3
"""Scheduler worker — runs as separate process.

Executes scheduled tasks from the TaskQueue, runs quick/deep cycles,
and reports results back via Redis. Main process stays responsive.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.base import BaseWorker

    class SchedulerWorker(BaseWorker):
        worker_name = "scheduler_worker"
        pool_size = 4

        def __init__(self) -> None:
            super().__init__()
            self._task_queue: Any = None
            self._scheduler: Any = None

        def run(self) -> None:
            settings = self.load_settings()
            project_root = Path(self._queue._client.get("capos:project_root") or ".") if self._queue.is_redis else Path(".")

            # Create TaskQueue
            try:
                from system.core.scheduler.task_queue import TaskQueue
                import os
                workspace_root = Path(os.environ.get("CAPOS_PROJECT_ROOT", "."))
                self._task_queue = TaskQueue(data_path=workspace_root / "queue.json")
                logger.info("TaskQueue loaded (%d tasks)", len(self._task_queue.list_all()))
            except Exception as exc:
                logger.error("Failed to create TaskQueue: %s", exc)
                return

            # Set up LLM for agent execution
            agent_loop = None
            try:
                from system.core.interpretation.llm_client import LLMClient
                from system.core.agent.agent_loop import AgentLoop
                from system.core.agent.tool_use_adapter import ToolUseAdapter

                llm_config = settings.get("llm", {})
                llm = LLMClient(
                    provider=llm_config.get("provider", "ollama"),
                    base_url=llm_config.get("base_url", "http://localhost:11434"),
                    api_key=llm_config.get("api_key", ""),
                    model=llm_config.get("model", ""),
                    timeout_ms=llm_config.get("timeout_ms", 30000),
                )
                adapter = ToolUseAdapter(llm)
                agent_loop = AgentLoop(adapter=adapter)
                logger.info("Agent loop ready for task execution")
            except Exception as exc:
                logger.warning("Agent loop not available: %s — tasks will be limited", exc)

            # Main scheduler loop
            logger.info("Scheduler worker started (task_check=60s, quick=30m, deep=4h)")
            last_quick = 0.0
            last_deep = 0.0
            QUICK_INTERVAL = 1800   # 30 min
            DEEP_INTERVAL = 14400   # 4 hours

            while self._running:
                now = time.time()
                self.heartbeat()

                # Task checker (every 60s)
                try:
                    ready_tasks = self._task_queue.get_ready()
                    for task in ready_tasks:
                        if not self._running:
                            break
                        self._pool.submit(self._execute_task, task, agent_loop)
                except Exception as exc:
                    logger.error("Task check error: %s", exc)

                # Quick cycle
                if now - last_quick >= QUICK_INTERVAL:
                    last_quick = now
                    self._pool.submit(self._run_cycle, "quick", agent_loop)

                # Deep cycle
                if now - last_deep >= DEEP_INTERVAL:
                    last_deep = now
                    self._pool.submit(self._run_cycle, "deep", agent_loop)

                time.sleep(60)

            logger.info("Scheduler worker stopped")

        def _execute_task(self, task: dict, agent_loop: Any) -> None:
            """Execute a single scheduled task."""
            task_id = task.get("id", "?")
            description = task.get("description", "")
            message = task.get("action_message", description)
            logger.info("Executing task %s: %s", task_id, description[:60])

            try:
                result = {"status": "success", "response": ""}
                if agent_loop and message:
                    agent_result = agent_loop.run(message)
                    # Consume generator
                    final = None
                    for event in agent_result:
                        final = event
                    result["response"] = str(final) if final else "Done"
                else:
                    result["response"] = "No agent available — skipped"

                self._task_queue.mark_executed(task_id, result)

                # Publish completion event
                if self._queue:
                    self._queue.publish("capos:events:scheduler_cycle", {
                        "type": "scheduler_cycle",
                        "data": {"task_id": task_id, "status": "success"},
                    })

                logger.info("Task %s completed", task_id)
            except Exception as exc:
                logger.error("Task %s failed: %s", task_id, exc)
                self._task_queue.mark_executed(task_id, {"status": "error", "error": str(exc)})

        def _run_cycle(self, cycle_name: str, agent_loop: Any) -> None:
            """Run a scheduler cycle (quick/deep)."""
            logger.info("Running %s cycle", cycle_name)
            try:
                ready = self._task_queue.get_ready()
                disabled = [t for t in self._task_queue.list_all() if not t.get("enabled", True)]

                if self._queue:
                    self._queue.publish("capos:events:scheduler_cycle", {
                        "type": "scheduler_cycle",
                        "data": {"cycle": cycle_name, "ready_tasks": len(ready), "disabled_tasks": len(disabled)},
                    })
            except Exception as exc:
                logger.error("%s cycle error: %s", cycle_name, exc)

    worker = SchedulerWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
