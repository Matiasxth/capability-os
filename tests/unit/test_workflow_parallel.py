"""Tests for parallel workflow execution."""

import time
from unittest.mock import MagicMock
from system.core.workflow.workflow_executor import WorkflowExecutor


def _mock_runtime(delay=0):
    """Create a ToolRuntime mock that optionally sleeps."""
    rt = MagicMock()
    def execute(tool_id, params):
        if delay:
            time.sleep(delay)
        return {"tool_id": tool_id, "status": "success", **params}
    rt.execute.side_effect = execute
    return rt


class TestParallelExecution:
    def test_parallel_flag_false_runs_sequentially(self):
        rt = _mock_runtime()
        executor = WorkflowExecutor(tool_runtime=rt)
        workflow = {
            "parallel": False,
            "nodes": [
                {"id": "t", "type": "trigger", "data": {}},
                {"id": "a", "type": "tool", "data": {"tool_id": "read", "params": {"x": 1}}},
                {"id": "b", "type": "tool", "data": {"tool_id": "read", "params": {"x": 2}}},
            ],
            "edges": [{"source": "t", "target": "a"}, {"source": "t", "target": "b"}],
        }
        result = executor.execute(workflow)
        assert result["status"] == "success"
        assert "a" in result["results"]
        assert "b" in result["results"]

    def test_parallel_independent_nodes_run_concurrently(self):
        rt = _mock_runtime(delay=0.1)
        executor = WorkflowExecutor(tool_runtime=rt)
        workflow = {
            "parallel": True,
            "nodes": [
                {"id": "t", "type": "trigger", "data": {}},
                {"id": "a", "type": "tool", "data": {"tool_id": "slow_a", "params": {}}},
                {"id": "b", "type": "tool", "data": {"tool_id": "slow_b", "params": {}}},
                {"id": "c", "type": "tool", "data": {"tool_id": "slow_c", "params": {}}},
            ],
            "edges": [
                {"source": "t", "target": "a"},
                {"source": "t", "target": "b"},
                {"source": "t", "target": "c"},
            ],
        }
        t0 = time.monotonic()
        result = executor.execute(workflow)
        elapsed = time.monotonic() - t0

        assert result["status"] == "success"
        assert len(result["results"]) == 4
        # 3 nodes at 0.1s each should take ~0.1s parallel, not 0.3s
        assert elapsed < 0.25, f"Took {elapsed:.2f}s — not parallel"

    def test_parallel_respects_dependencies(self):
        rt = _mock_runtime()
        executor = WorkflowExecutor(tool_runtime=rt)
        workflow = {
            "parallel": True,
            "nodes": [
                {"id": "t", "type": "trigger", "data": {}},
                {"id": "a", "type": "tool", "data": {"tool_id": "first", "params": {}}},
                {"id": "b", "type": "tool", "data": {"tool_id": "second", "params": {}}},
            ],
            "edges": [
                {"source": "t", "target": "a"},
                {"source": "a", "target": "b"},  # b depends on a
            ],
        }
        result = executor.execute(workflow)
        assert result["status"] == "success"
        assert "a" in result["results"]
        assert "b" in result["results"]

    def test_parallel_condition_nodes_run_sequentially(self):
        rt = _mock_runtime()
        executor = WorkflowExecutor(tool_runtime=rt)
        workflow = {
            "parallel": True,
            "nodes": [
                {"id": "t", "type": "trigger", "data": {}},
                {"id": "a", "type": "tool", "data": {"tool_id": "read", "params": {}}},
                {"id": "cond", "type": "condition", "data": {"expression": "True", "source_node": "a"}},
            ],
            "edges": [
                {"source": "t", "target": "a"},
                {"source": "a", "target": "cond"},
            ],
        }
        result = executor.execute(workflow)
        assert result["status"] == "success"
        assert result["results"]["cond"]["branch"] == "true_path"

    def test_parallel_error_stops_execution(self):
        rt = MagicMock()
        rt.execute.side_effect = RuntimeError("boom")
        executor = WorkflowExecutor(tool_runtime=rt)
        workflow = {
            "parallel": True,
            "nodes": [
                {"id": "t", "type": "trigger", "data": {}},
                {"id": "a", "type": "tool", "data": {"tool_id": "fail", "params": {}}},
            ],
            "edges": [{"source": "t", "target": "a"}],
        }
        result = executor.execute(workflow)
        assert result["status"] == "error"
        assert "boom" in result["error"]
