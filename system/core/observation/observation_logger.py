from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


EVENTS = {
    "execution_started",
    "capability_resolved",
    "validation_passed",
    "step_started",
    "step_succeeded",
    "step_failed",
    "execution_finished",
}


class ObservationLogger:
    """Emits spec events and keeps the canonical runtime model in sync."""

    def __init__(self, metrics_collector: Any | None = None, execution_history: Any | None = None, semantic_memory: Any | None = None):
        self.runtime: dict[str, Any] | None = None
        self._metrics_collector = metrics_collector
        self._execution_history = execution_history
        self._semantic_memory = semantic_memory

    def initialize(self, capability_id: str, initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
        self.runtime = {
            "execution_id": f"exec_{uuid4().hex[:12]}",
            "capability_id": capability_id,
            "status": "running",
            "current_step": None,
            "state": deepcopy(initial_state or {}),
            "logs": [],
            "started_at": _now_iso(),
            "ended_at": None,
            "duration_ms": 0,
            "retry_count": 0,
            "error_code": None,
            "error_message": None,
            "last_completed_step": None,
            "failed_step": None,
            "final_output": {},
        }
        self.emit("execution_started", {"capability_id": capability_id})
        return self.get_runtime_model()

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        if event not in EVENTS:
            raise ValueError(f"Unsupported observation event '{event}'.")

        entry = {
            "event": event,
            "timestamp": _now_iso(),
            "payload": deepcopy(payload or {}),
        }
        self.runtime["logs"].append(entry)

    def mark_capability_resolved(self) -> None:
        self.emit("capability_resolved")

    def mark_validation_passed(self) -> None:
        self.emit("validation_passed")

    def mark_step_started(self, step_id: str, resolved_params: dict[str, Any]) -> None:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        self.runtime["current_step"] = step_id
        self.emit("step_started", {"step_id": step_id, "params": deepcopy(resolved_params)})

    def mark_step_succeeded(self, step_id: str, output: Any, state_snapshot: dict[str, Any]) -> None:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        self.runtime["last_completed_step"] = step_id
        self.runtime["state"] = deepcopy(state_snapshot)
        self.emit("step_succeeded", {"step_id": step_id, "output": deepcopy(output)})

    def mark_step_failed(
        self,
        step_id: str,
        error_code: str,
        error_message: str,
        state_snapshot: dict[str, Any],
    ) -> None:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        self.runtime["failed_step"] = step_id
        self.runtime["error_code"] = error_code
        self.runtime["error_message"] = error_message
        self.runtime["state"] = deepcopy(state_snapshot)
        self.emit(
            "step_failed",
            {
                "step_id": step_id,
                "error_code": error_code,
                "error_message": error_message,
            },
        )

    def finish(
        self,
        *,
        status: str,
        final_output: dict[str, Any] | None,
        state_snapshot: dict[str, Any],
        error_code: str | None = None,
        error_message: str | None = None,
        failed_step: str | None = None,
    ) -> dict[str, Any]:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        if status == "error" and not error_code:
            raise ValueError("error_code is required when status is 'error'.")

        ended_at = _now_iso()
        started_at = self.runtime["started_at"]
        duration_ms = _duration_ms(started_at, ended_at)

        self.runtime["status"] = status
        self.runtime["ended_at"] = ended_at
        self.runtime["duration_ms"] = duration_ms
        self.runtime["state"] = deepcopy(state_snapshot)
        self.runtime["final_output"] = deepcopy(final_output or {})
        self.runtime["failed_step"] = failed_step
        self.runtime["error_code"] = error_code
        self.runtime["error_message"] = error_message

        self.emit(
            "execution_finished",
            {
                "status": status,
                "final_output": deepcopy(final_output or {}),
                "error_code": error_code,
                "error_message": error_message,
                "failed_step": failed_step,
            },
        )

        model = self.get_runtime_model()
        if self._metrics_collector is not None:
            try:
                self._metrics_collector.record_execution(model)
            except Exception:
                pass  # metrics failure must not break execution
        if self._execution_history is not None:
            try:
                self._execution_history.record(model)
            except Exception:
                pass  # history failure must not break execution
        if self._semantic_memory is not None and status in ("ready", "success"):
            try:
                cap_id = model.get("capability_id", "")
                intent = f"{cap_id} execution"
                self._semantic_memory.remember_semantic(
                    intent,
                    metadata={"capability_id": cap_id, "execution_id": model.get("execution_id")},
                    memory_type="execution_pattern",
                    capability_id=cap_id,
                )
            except Exception:
                pass  # semantic failure must not break execution
        return model

    def get_runtime_model(self) -> dict[str, Any]:
        if self.runtime is None:
            raise RuntimeError("Observation logger is not initialized.")
        return deepcopy(self.runtime)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(started_at: str, ended_at: str) -> int:
    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    return max(0, int((end - start).total_seconds() * 1000))
