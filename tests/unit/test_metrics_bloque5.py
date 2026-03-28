"""
Tests for Bloque 5 — Metrics Collector and trace persistence.

Validates:
  1. MetricsCollector: record, aggregate, persist, reload.
  2. The 4 KPIs from spec section 31.1:
     - execution_success_rate
     - avg_execution_time_ms
     - error_rate_by_capability
     - tool_failure_rate
  3. Trace persistence: write and read back traces.
  4. ObservationLogger feeds MetricsCollector on finish().
  5. CapabilityEngine passes metrics_collector through to logger.
  6. get_execution_trace capability reads persisted traces.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.core.metrics.metrics_collector import MetricsCollector
from system.core.observation.observation_logger import ObservationLogger
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "bloque5_metrics"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _sample_runtime(
    execution_id: str = "exec_test001",
    capability_id: str = "test_cap",
    status: str = "ready",
    duration_ms: int = 150,
    logs: list | None = None,
    error_code: str | None = None,
) -> dict:
    return {
        "execution_id": execution_id,
        "capability_id": capability_id,
        "status": status,
        "current_step": None,
        "state": {},
        "logs": logs or [
            {"event": "step_started", "timestamp": "T1", "payload": {}},
            {"event": "step_succeeded", "timestamp": "T2", "payload": {}},
            {"event": "execution_finished", "timestamp": "T3", "payload": {}},
        ],
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:00.150Z",
        "duration_ms": duration_ms,
        "retry_count": 0,
        "error_code": error_code,
        "error_message": None,
        "last_completed_step": None,
        "failed_step": None,
        "final_output": {},
    }


# ===========================================================================
# 1. MetricsCollector — basic recording and aggregation
# ===========================================================================

class TestMetricsCollectorBasic(unittest.TestCase):

    def test_fresh_collector_returns_zero_metrics(self):
        ws = _workspace("fresh")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 0)
        self.assertEqual(metrics["execution_success_rate"], 0.0)
        self.assertEqual(metrics["avg_execution_time_ms"], 0.0)
        self.assertEqual(metrics["tool_failure_rate"], 0.0)

    def test_record_successful_execution(self):
        ws = _workspace("success")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime())
        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 1)
        self.assertEqual(metrics["execution_success_rate"], 100.0)

    def test_record_failed_execution(self):
        ws = _workspace("failure")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        rt = _sample_runtime(
            status="error", capability_id="bad_cap",
            logs=[
                {"event": "step_started", "timestamp": "T1", "payload": {}},
                {"event": "step_failed", "timestamp": "T2", "payload": {"error_code": "tool_execution_error"}},
                {"event": "execution_finished", "timestamp": "T3", "payload": {}},
            ],
            error_code="tool_execution_error",
        )
        mc.record_execution(rt)
        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 0)
        self.assertEqual(metrics["execution_success_rate"], 0.0)
        self.assertEqual(metrics["error_rate_by_capability"]["bad_cap"], 1)

    def test_avg_execution_time(self):
        ws = _workspace("avg_time")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(execution_id="e1", duration_ms=100))
        mc.record_execution(_sample_runtime(execution_id="e2", duration_ms=200))
        metrics = mc.get_metrics()
        self.assertEqual(metrics["avg_execution_time_ms"], 150.0)

    def test_tool_failure_rate(self):
        ws = _workspace("tool_rate")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        # 2 succeeded steps, 1 failed step (tool_execution_error)
        mc.record_execution(_sample_runtime(
            execution_id="e1",
            logs=[
                {"event": "step_started", "timestamp": "T1", "payload": {}},
                {"event": "step_succeeded", "timestamp": "T2", "payload": {}},
                {"event": "step_started", "timestamp": "T3", "payload": {}},
                {"event": "step_succeeded", "timestamp": "T4", "payload": {}},
                {"event": "step_started", "timestamp": "T5", "payload": {}},
                {"event": "step_failed", "timestamp": "T6", "payload": {"error_code": "tool_execution_error"}},
                {"event": "execution_finished", "timestamp": "T7", "payload": {}},
            ],
        ))
        metrics = mc.get_metrics()
        self.assertEqual(metrics["tool_calls_total"], 3)
        self.assertEqual(metrics["tool_calls_failed"], 1)
        self.assertAlmostEqual(metrics["tool_failure_rate"], 33.33, places=1)

    def test_validation_failure_not_counted_as_tool_failure(self):
        """step_failed with variable_resolution_error should NOT count as tool failure."""
        ws = _workspace("validation_not_tool")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(
            execution_id="e1",
            logs=[
                {"event": "step_started", "timestamp": "T1", "payload": {}},
                {"event": "step_failed", "timestamp": "T2", "payload": {"error_code": "variable_resolution_error"}},
                {"event": "execution_finished", "timestamp": "T3", "payload": {}},
            ],
        ))
        metrics = mc.get_metrics()
        self.assertEqual(metrics["tool_calls_total"], 0)
        self.assertEqual(metrics["tool_calls_failed"], 0)
        self.assertEqual(metrics["tool_failure_rate"], 0.0)

    def test_multiple_capabilities_error_rate(self):
        ws = _workspace("multi_cap_err")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(execution_id="e1", status="error", capability_id="cap_a",
            logs=[{"event": "step_failed", "timestamp": "T1", "payload": {"error_code": "tool_execution_error"}}]))
        mc.record_execution(_sample_runtime(execution_id="e2", status="error", capability_id="cap_a",
            logs=[{"event": "step_failed", "timestamp": "T1", "payload": {"error_code": "tool_execution_error"}}]))
        mc.record_execution(_sample_runtime(execution_id="e3", status="error", capability_id="cap_b",
            logs=[{"event": "step_failed", "timestamp": "T1", "payload": {"error_code": "tool_execution_error"}}]))
        metrics = mc.get_metrics()
        self.assertEqual(metrics["error_rate_by_capability"]["cap_a"], 2)
        self.assertEqual(metrics["error_rate_by_capability"]["cap_b"], 1)


# ===========================================================================
# 2. Persistence: save, reload, trace files
# ===========================================================================

class TestMetricsCollectorPersistence(unittest.TestCase):

    def test_metrics_persist_and_reload(self):
        ws = _workspace("persist")
        mc1 = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc1.record_execution(_sample_runtime(execution_id="e1"))
        mc1.record_execution(_sample_runtime(execution_id="e2", status="error",
            capability_id="x", logs=[{"event": "step_failed", "timestamp": "T", "payload": {}}]))

        # Reload from disk
        mc2 = MetricsCollector(ws / "metrics.json", ws / "traces")
        metrics = mc2.get_metrics()
        self.assertEqual(metrics["total_executions"], 2)
        self.assertEqual(metrics["successful_executions"], 1)

    def test_trace_file_written(self):
        ws = _workspace("trace_write")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(execution_id="exec_abc123"))
        trace_path = ws / "traces" / "exec_abc123.json"
        self.assertTrue(trace_path.exists())
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        self.assertEqual(data["execution_id"], "exec_abc123")

    def test_get_trace(self):
        ws = _workspace("get_trace")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(execution_id="exec_xyz"))
        trace = mc.get_trace("exec_xyz")
        self.assertIsNotNone(trace)
        self.assertEqual(trace["execution_id"], "exec_xyz")

    def test_get_trace_not_found(self):
        ws = _workspace("trace_404")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        self.assertIsNone(mc.get_trace("nonexistent"))

    def test_list_traces(self):
        ws = _workspace("list_traces")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        mc.record_execution(_sample_runtime(execution_id="exec_001"))
        mc.record_execution(_sample_runtime(execution_id="exec_002"))
        traces = mc.list_traces()
        self.assertIn("exec_001", traces)
        self.assertIn("exec_002", traces)
        self.assertEqual(len(traces), 2)


# ===========================================================================
# 3. ObservationLogger feeds MetricsCollector on finish()
# ===========================================================================

class TestObservationLoggerMetricsFeed(unittest.TestCase):

    def test_logger_calls_collector_on_finish(self):
        ws = _workspace("logger_feed")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        logger = ObservationLogger(metrics_collector=mc)
        logger.initialize("test_cap")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        logger.mark_step_started("step_a", {"cmd": "go"})
        logger.mark_step_succeeded("step_a", {"stdout": "ok"}, {})
        logger.finish(status="ready", final_output={"stdout": "ok"}, state_snapshot={})

        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 1)

    def test_logger_calls_collector_on_error(self):
        ws = _workspace("logger_error")
        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        logger = ObservationLogger(metrics_collector=mc)
        logger.initialize("bad_cap")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        logger.mark_step_started("step_a", {})
        logger.mark_step_failed("step_a", "tool_execution_error", "boom", {})
        logger.finish(
            status="error", final_output={}, state_snapshot={},
            error_code="tool_execution_error", error_message="boom", failed_step="step_a",
        )

        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 0)
        self.assertEqual(metrics["error_rate_by_capability"]["bad_cap"], 1)

    def test_logger_without_collector_still_works(self):
        logger = ObservationLogger()
        logger.initialize("cap")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        model = logger.finish(status="ready", final_output={}, state_snapshot={})
        self.assertEqual(model["status"], "ready")


# ===========================================================================
# 4. CapabilityEngine passes metrics_collector to logger
# ===========================================================================

class TestEngineMetricsIntegration(unittest.TestCase):

    def _build(self, ws: Path):
        cap_reg = CapabilityRegistry()
        tool_reg = ToolRegistry()
        for p in sorted((ROOT / "system" / "tools" / "contracts" / "v1").glob("*.json")):
            tool_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))
        for p in sorted((ROOT / "system" / "capabilities" / "contracts" / "v1").glob("*.json")):
            cap_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))

        mc = MetricsCollector(ws / "metrics.json", ws / "traces")
        tool_runtime = ToolRuntime(tool_reg, workspace_root=ws)
        register_phase3_real_tools(tool_runtime, ws)
        engine = CapabilityEngine(cap_reg, tool_runtime, metrics_collector=mc)
        return engine, cap_reg, mc

    def test_engine_records_success_metric(self):
        ws = _workspace("engine_success")
        engine, cap_reg, mc = self._build(ws)
        f = ws / "test.txt"
        f.write_text("hello", encoding="utf-8-sig")
        contract = cap_reg.get("read_file")
        engine.execute(contract, {"path": str(f)})

        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 1)
        self.assertGreater(metrics["tool_calls_total"], 0)

    def test_engine_records_failure_metric(self):
        ws = _workspace("engine_fail")
        engine, cap_reg, mc = self._build(ws)
        contract = cap_reg.get("read_file")
        with self.assertRaises(CapabilityExecutionError):
            engine.execute(contract, {"path": str(ws / "ghost.txt")})

        metrics = mc.get_metrics()
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 0)
        self.assertEqual(metrics["error_rate_by_capability"].get("read_file"), 1)

    def test_engine_persists_trace_file(self):
        ws = _workspace("engine_trace")
        engine, cap_reg, mc = self._build(ws)
        f = ws / "test.txt"
        f.write_text("hello", encoding="utf-8-sig")
        contract = cap_reg.get("read_file")
        result = engine.execute(contract, {"path": str(f)})

        execution_id = result["execution_id"]
        trace = mc.get_trace(execution_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace["capability_id"], "read_file")


# ===========================================================================
# 5. get_execution_trace capability reads persisted traces
# ===========================================================================

class TestGetExecutionTraceCapability(unittest.TestCase):

    def test_trace_readable_via_capability(self):
        ws = _workspace("trace_cap")
        engine, cap_reg, mc = self._build(ws)

        # First: create a trace by running a capability
        f = ws / "data.txt"
        f.write_text("content", encoding="utf-8-sig")
        exec_result = engine.execute(cap_reg.get("read_file"), {"path": str(f)})
        execution_id = exec_result["execution_id"]

        # Verify the trace file is where get_execution_trace expects it
        trace_path = ws / "artifacts" / "traces" / f"{execution_id}.json"
        self.assertTrue(trace_path.exists())

        # Now use get_execution_trace capability to read it
        trace_contract = cap_reg.get("get_execution_trace")
        trace_result = engine.execute(trace_contract, {"execution_id": execution_id})
        self.assertEqual(trace_result["status"], "success")
        content = trace_result["final_output"].get("content", "")
        self.assertIn(execution_id, content)

    def _build(self, ws: Path):
        cap_reg = CapabilityRegistry()
        tool_reg = ToolRegistry()
        for p in sorted((ROOT / "system" / "tools" / "contracts" / "v1").glob("*.json")):
            tool_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))
        for p in sorted((ROOT / "system" / "capabilities" / "contracts" / "v1").glob("*.json")):
            cap_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))

        mc = MetricsCollector(ws / "metrics.json", ws / "artifacts" / "traces")
        tool_runtime = ToolRuntime(tool_reg, workspace_root=ws)
        register_phase3_real_tools(tool_runtime, ws)
        engine = CapabilityEngine(cap_reg, tool_runtime, metrics_collector=mc)
        return engine, cap_reg, mc


if __name__ == "__main__":
    unittest.main()
