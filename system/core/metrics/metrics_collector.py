"""Collects and persists the 4 operational KPIs from spec section 31.1.

KPIs:
  - execution_success_rate   — % of executions that finished successfully
  - avg_execution_time_ms    — mean duration across all recorded executions
  - error_rate_by_capability — error count grouped by capability_id
  - tool_failure_rate        — % of tool invocations that failed

Also persists full execution traces to ``traces_dir`` so that the
``get_execution_trace`` and ``get_error_report`` capabilities can read them.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


_EMPTY_DATA: dict[str, Any] = {
    "total_executions": 0,
    "successful_executions": 0,
    "total_duration_ms": 0,
    "errors_by_capability": {},
    "tool_calls_total": 0,
    "tool_calls_failed": 0,
}


class MetricsCollector:
    """Thread-safe metrics collector with JSON persistence."""

    def __init__(
        self,
        data_path: str | Path,
        traces_dir: str | Path,
    ):
        self.data_path = Path(data_path).resolve()
        self.traces_dir = Path(traces_dir).resolve()
        self._lock = RLock()
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_execution(self, runtime_model: dict[str, Any]) -> None:
        """Record metrics from a completed execution and persist the trace."""
        with self._lock:
            self._data["total_executions"] += 1

            status = runtime_model.get("status")
            capability_id = runtime_model.get("capability_id", "unknown")
            duration_ms = runtime_model.get("duration_ms", 0)

            self._data["total_duration_ms"] += duration_ms

            if status in ("ready", "success"):
                self._data["successful_executions"] += 1
            elif status == "error":
                errors = self._data["errors_by_capability"]
                errors[capability_id] = errors.get(capability_id, 0) + 1

            # Count tool calls from event log
            self._count_tool_calls(runtime_model)

            self._persist_trace(runtime_model)
            self._save_locked()

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, Any]:
        with self._lock:
            total = self._data["total_executions"]
            successful = self._data["successful_executions"]
            total_duration = self._data["total_duration_ms"]
            tool_total = self._data["tool_calls_total"]
            tool_failed = self._data["tool_calls_failed"]

            return {
                "execution_success_rate": round(successful / total * 100, 2) if total > 0 else 0.0,
                "avg_execution_time_ms": round(total_duration / total, 2) if total > 0 else 0.0,
                "error_rate_by_capability": dict(self._data["errors_by_capability"]),
                "tool_failure_rate": round(tool_failed / tool_total * 100, 2) if tool_total > 0 else 0.0,
                "total_executions": total,
                "successful_executions": successful,
                "total_duration_ms": total_duration,
                "tool_calls_total": tool_total,
                "tool_calls_failed": tool_failed,
            }

    def get_trace(self, execution_id: str) -> dict[str, Any] | None:
        trace_path = self.traces_dir / f"{execution_id}.json"
        if not trace_path.exists():
            return None
        try:
            return json.loads(trace_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_traces(self, limit: int = 50) -> list[str]:
        if not self.traces_dir.exists():
            return []
        paths = sorted(self.traces_dir.glob("exec_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in paths[:limit]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_tool_calls(self, runtime_model: dict[str, Any]) -> None:
        """Count tool invocations from event log.

        Only ``step_failed`` events with ``error_code == "tool_execution_error"``
        count as tool failures.  Validation or variable resolution failures that
        happen *before* the tool is invoked are excluded so that
        ``tool_failure_rate`` reflects actual tool problems only.
        """
        logs = runtime_model.get("logs", [])
        for entry in logs:
            event = entry.get("event")
            if event == "step_succeeded":
                self._data["tool_calls_total"] += 1
            elif event == "step_failed":
                payload = entry.get("payload", {})
                error_code = payload.get("error_code", "")
                if error_code == "tool_execution_error":
                    self._data["tool_calls_total"] += 1
                    self._data["tool_calls_failed"] += 1
                # validation/variable errors are NOT counted as tool calls

    def _persist_trace(self, runtime_model: dict[str, Any]) -> None:
        execution_id = runtime_model.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            return
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.traces_dir / f"{execution_id}.json"
        trace_path.write_text(
            json.dumps(deepcopy(runtime_model), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _load(self) -> None:
        with self._lock:
            if self.data_path.exists():
                try:
                    raw = json.loads(self.data_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self._data = {**deepcopy(_EMPTY_DATA), **raw}
                        return
                except (json.JSONDecodeError, OSError):
                    pass
            self._data = deepcopy(_EMPTY_DATA)

    def _save_locked(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
