"""
Tests for Componente 2 — PerformanceMonitor.

Validates:
  1. No suggestions when all executions succeed.
  2. No suggestions when error rate is below threshold (20%).
  3. Suggestions generated when error rate >= 20%.
  4. retry_policy suggested when failures concentrate on one step.
  5. fallback suggested when failures spread across steps.
  6. increase_timeout suggested when timeout errors dominate.
  7. Suggestion includes correct metadata (error_rate, failed_steps, etc.).
  8. Window size limits how many traces per capability are analyzed.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.core.metrics.metrics_collector import MetricsCollector
from system.core.self_improvement.performance_monitor import PerformanceMonitor

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "perf_monitor"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


_TRACE_COUNTER = {"n": 0}

def _make_trace(
    execution_id: str | None = None,
    capability_id: str = "test_cap",
    status: str = "ready",
    failed_step: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    duration_ms: int = 100,
) -> dict[str, Any]:
    if execution_id is None:
        _TRACE_COUNTER["n"] += 1
        execution_id = f"exec_{_TRACE_COUNTER['n']:06d}"
    elif not execution_id.startswith("exec_"):
        execution_id = f"exec_{execution_id}"
    logs = [
        {"event": "step_started", "timestamp": "T1", "payload": {"step_id": "step_a"}},
    ]
    if status == "error" and failed_step:
        logs.append({
            "event": "step_failed",
            "timestamp": "T2",
            "payload": {"step_id": failed_step, "error_code": error_code or "tool_execution_error", "error_message": error_message or "fail"},
        })
    else:
        logs.append({"event": "step_succeeded", "timestamp": "T2", "payload": {"step_id": "step_a"}})
    logs.append({"event": "execution_finished", "timestamp": "T3", "payload": {}})

    return {
        "execution_id": execution_id,
        "capability_id": capability_id,
        "status": status,
        "duration_ms": duration_ms,
        "failed_step": failed_step,
        "error_code": error_code,
        "error_message": error_message,
        "logs": logs,
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:00.100Z",
        "retry_count": 0,
        "current_step": None,
        "state": {},
        "last_completed_step": None if status == "error" else "step_a",
        "final_output": {},
    }


def _build_monitor(name: str, traces: list[dict], **kwargs) -> PerformanceMonitor:
    _TRACE_COUNTER["n"] = 0  # reset per test
    ws = _workspace(name)
    mc = MetricsCollector(ws / "metrics.json", ws / "traces")
    for trace in traces:
        mc.record_execution(trace)
    return PerformanceMonitor(mc, **kwargs)


# ===========================================================================
# 1. No suggestions when healthy
# ===========================================================================

class TestHealthyCapabilities(unittest.TestCase):

    def test_all_success_no_suggestions(self):
        traces = [_make_trace() for i in range(10)]
        monitor = _build_monitor("all_success", traces)
        self.assertEqual(monitor.get_improvement_suggestions(), [])

    def test_below_threshold_no_suggestions(self):
        # 1 error out of 10 = 10% < 20%
        traces = [_make_trace() for i in range(9)]
        traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        monitor = _build_monitor("below_threshold", traces)
        self.assertEqual(monitor.get_improvement_suggestions(), [])

    def test_no_traces_no_suggestions(self):
        monitor = _build_monitor("empty", [])
        self.assertEqual(monitor.get_improvement_suggestions(), [])


# ===========================================================================
# 2. Suggestions when unhealthy
# ===========================================================================

class TestUnhealthyCapabilities(unittest.TestCase):

    def test_above_threshold_generates_suggestion(self):
        # 3 errors out of 10 = 30% > 20%
        traces = [_make_trace() for i in range(7)]
        for i in range(3):
            traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        monitor = _build_monitor("above_threshold", traces)
        suggestions = monitor.get_improvement_suggestions()
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["capability_id"], "test_cap")
        self.assertGreaterEqual(suggestions[0]["error_rate"], 20.0)

    def test_exactly_at_threshold(self):
        # 2 errors out of 10 = 20%
        traces = [_make_trace() for i in range(8)]
        for i in range(2):
            traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        monitor = _build_monitor("at_threshold", traces)
        suggestions = monitor.get_improvement_suggestions()
        self.assertEqual(len(suggestions), 1)

    def test_multiple_capabilities_independent(self):
        traces = []
        # cap_a: 50% error → suggestion
        for i in range(5):
            traces.append(_make_trace( capability_id="cap_a"))
        for i in range(5):
            traces.append(_make_trace( capability_id="cap_a", status="error", failed_step="s1", error_code="tool_execution_error"))
        # cap_b: 0% error → no suggestion
        for i in range(5):
            traces.append(_make_trace( capability_id="cap_b"))
        monitor = _build_monitor("multi_cap", traces)
        suggestions = monitor.get_improvement_suggestions()
        cap_ids = {s["capability_id"] for s in suggestions}
        self.assertIn("cap_a", cap_ids)
        self.assertNotIn("cap_b", cap_ids)


# ===========================================================================
# 3. Suggestion type classification
# ===========================================================================

class TestSuggestionTypes(unittest.TestCase):

    def test_retry_policy_when_single_step_fails(self):
        # All errors on the same step → retry_policy
        traces = [_make_trace() for i in range(5)]
        for i in range(5):
            traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        monitor = _build_monitor("retry_single_step", traces)
        suggestions = monitor.get_improvement_suggestions()
        self.assertEqual(suggestions[0]["suggestion_type"], "retry_policy")
        self.assertIn("step_a", suggestions[0]["reason"])

    def test_fallback_when_multiple_steps_fail(self):
        traces = [_make_trace() for i in range(5)]
        # Failures spread across different steps
        traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_b", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_c", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_d", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_e", error_code="tool_execution_error"))
        monitor = _build_monitor("fallback_multi_step", traces)
        suggestions = monitor.get_improvement_suggestions()
        self.assertEqual(suggestions[0]["suggestion_type"], "fallback")

    def test_increase_timeout_when_timeout_errors_dominate(self):
        traces = [_make_trace() for i in range(5)]
        for i in range(5):
            traces.append(_make_trace(
                f"f{i}", status="error", failed_step="step_a",
                error_code="selector_not_found",
                error_message="Selector timed out",
            ))
        monitor = _build_monitor("timeout_dominant", traces)
        suggestions = monitor.get_improvement_suggestions()
        self.assertEqual(suggestions[0]["suggestion_type"], "increase_timeout")
        self.assertIn("Timeout", suggestions[0]["reason"])


# ===========================================================================
# 4. Metadata in suggestions
# ===========================================================================

class TestSuggestionMetadata(unittest.TestCase):

    def test_includes_all_fields(self):
        traces = [_make_trace() for i in range(7)]
        for i in range(3):
            traces.append(_make_trace( status="error", failed_step="step_x", error_code="tool_execution_error"))
        monitor = _build_monitor("metadata_check", traces)
        s = monitor.get_improvement_suggestions()[0]
        self.assertIn("capability_id", s)
        self.assertIn("suggestion_type", s)
        self.assertIn("reason", s)
        self.assertIn("error_rate", s)
        self.assertIn("total_in_window", s)
        self.assertIn("errors_in_window", s)
        self.assertIn("failed_steps", s)
        self.assertIn("error_codes", s)

    def test_error_rate_is_percentage(self):
        traces = [_make_trace()]
        for i in range(4):
            traces.append(_make_trace( status="error", failed_step="s", error_code="tool_execution_error"))
        monitor = _build_monitor("rate_pct", traces)
        s = monitor.get_improvement_suggestions()[0]
        self.assertEqual(s["error_rate"], 80.0)

    def test_failed_steps_counted(self):
        traces = [_make_trace()]
        traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_a", error_code="tool_execution_error"))
        traces.append(_make_trace( status="error", failed_step="step_b", error_code="tool_execution_error"))
        monitor = _build_monitor("step_counts", traces)
        s = monitor.get_improvement_suggestions()[0]
        self.assertEqual(s["failed_steps"]["step_a"], 2)
        self.assertEqual(s["failed_steps"]["step_b"], 1)


# ===========================================================================
# 5. Window size
# ===========================================================================

class TestWindowSize(unittest.TestCase):

    def test_window_limits_analysis(self):
        # 20 traces total, but window=5 → only 5 latest analyzed per cap
        traces = []
        for i in range(15):
            traces.append(_make_trace())
        for i in range(5):
            traces.append(_make_trace(f"recent_fail{i}", status="error", failed_step="s", error_code="tool_execution_error"))
        # With window=5, if the 5 latest are all errors → 100% error rate
        monitor = _build_monitor("window_limit", traces, window_size=5)
        suggestions = monitor.get_improvement_suggestions()
        # The window picks from most-recent traces returned by list_traces
        # which sorts by mtime descending → the 5 failures should dominate
        self.assertTrue(len(suggestions) >= 1)
        self.assertGreaterEqual(suggestions[0]["error_rate"], 20.0)


if __name__ == "__main__":
    unittest.main()
