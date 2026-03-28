"""
Tests for Componente 3 — ExecutionHistory.

Validates:
  1. record: stores compact entry from runtime model.
  2. get_recent: returns newest first, respects limit.
  3. get_by_capability: filters by capability_id.
  4. search: substring match on intent.
  5. get_stats: success/error counts by capability.
  6. delete: removes by execution_id.
  7. clear: removes all.
  8. FIFO limit: oldest entries dropped when max exceeded.
  9. Persistence: survives reload.
  10. Error resilience: record never raises.
  11. Integration: ObservationLogger feeds history on finish.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.core.memory.execution_history import ExecutionHistory
from system.core.observation.observation_logger import ObservationLogger

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "exec_hist"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws / "history.json"


def _rt(
    execution_id: str = "exec_001",
    capability_id: str = "read_file",
    status: str = "ready",
    duration_ms: int = 100,
    final_output: dict | None = None,
    error_code: str | None = None,
    failed_step: str | None = None,
) -> dict[str, Any]:
    return {
        "execution_id": execution_id,
        "capability_id": capability_id,
        "status": status,
        "duration_ms": duration_ms,
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:00.100Z",
        "error_code": error_code,
        "error_message": None,
        "failed_step": failed_step,
        "final_output": final_output or {"stdout": "hello"},
        "state": {},
        "logs": [],
        "retry_count": 0,
        "current_step": None,
        "last_completed_step": None,
    }


# ===========================================================================
# 1. record
# ===========================================================================

class TestRecord(unittest.TestCase):

    def test_stores_entry(self):
        h = ExecutionHistory(_ws("store"))
        h.record(_rt(), intent="read my file")
        self.assertEqual(h.count(), 1)
        entries = h.get_recent(1)
        self.assertEqual(entries[0]["execution_id"], "exec_001")
        self.assertEqual(entries[0]["capability_id"], "read_file")
        self.assertEqual(entries[0]["intent"], "read my file")
        self.assertEqual(entries[0]["status"], "ready")
        self.assertEqual(entries[0]["duration_ms"], 100)

    def test_key_outputs_scalar_only(self):
        h = ExecutionHistory(_ws("scalar"))
        h.record(_rt(final_output={"text": "hi", "items": [1, 2, 3]}))
        entry = h.get_recent(1)[0]
        self.assertEqual(entry["key_outputs"]["text"], "hi")
        self.assertNotIn("items", entry["key_outputs"])

    def test_no_intent(self):
        h = ExecutionHistory(_ws("nointent"))
        h.record(_rt())
        self.assertIsNone(h.get_recent(1)[0]["intent"])


# ===========================================================================
# 2. get_recent
# ===========================================================================

class TestGetRecent(unittest.TestCase):

    def test_newest_first(self):
        h = ExecutionHistory(_ws("order"))
        h.record(_rt(execution_id="e1"))
        h.record(_rt(execution_id="e2"))
        h.record(_rt(execution_id="e3"))
        entries = h.get_recent(3)
        self.assertEqual(entries[0]["execution_id"], "e3")
        self.assertEqual(entries[2]["execution_id"], "e1")

    def test_respects_limit(self):
        h = ExecutionHistory(_ws("limit"))
        for i in range(10):
            h.record(_rt(execution_id=f"exec_{i:03d}"))
        self.assertEqual(len(h.get_recent(3)), 3)

    def test_empty(self):
        h = ExecutionHistory(_ws("empty"))
        self.assertEqual(h.get_recent(), [])


# ===========================================================================
# 3. get_by_capability
# ===========================================================================

class TestGetByCapability(unittest.TestCase):

    def test_filters(self):
        h = ExecutionHistory(_ws("bycap"))
        h.record(_rt(execution_id="e1", capability_id="read_file"))
        h.record(_rt(execution_id="e2", capability_id="write_file"))
        h.record(_rt(execution_id="e3", capability_id="read_file"))
        results = h.get_by_capability("read_file")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["capability_id"] == "read_file" for r in results))


# ===========================================================================
# 4. search
# ===========================================================================

class TestSearch(unittest.TestCase):

    def test_substring_match(self):
        h = ExecutionHistory(_ws("search"))
        h.record(_rt(execution_id="e1"), intent="create react project")
        h.record(_rt(execution_id="e2"), intent="read a file")
        h.record(_rt(execution_id="e3"), intent="create vue project")
        results = h.search("create")
        self.assertEqual(len(results), 2)

    def test_case_insensitive(self):
        h = ExecutionHistory(_ws("case"))
        h.record(_rt(), intent="Hello World")
        self.assertEqual(len(h.search("hello")), 1)

    def test_no_match(self):
        h = ExecutionHistory(_ws("nomatch"))
        h.record(_rt(), intent="something")
        self.assertEqual(h.search("xyz"), [])


# ===========================================================================
# 5. get_stats
# ===========================================================================

class TestGetStats(unittest.TestCase):

    def test_counts(self):
        h = ExecutionHistory(_ws("stats"))
        h.record(_rt(execution_id="e1", capability_id="cap_a", status="ready"))
        h.record(_rt(execution_id="e2", capability_id="cap_a", status="error"))
        h.record(_rt(execution_id="e3", capability_id="cap_b", status="ready"))
        stats = h.get_stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertEqual(stats["by_capability"]["cap_a"]["success"], 1)
        self.assertEqual(stats["by_capability"]["cap_a"]["error"], 1)
        self.assertEqual(stats["by_capability"]["cap_b"]["success"], 1)


# ===========================================================================
# 6. delete + clear
# ===========================================================================

class TestDeleteClear(unittest.TestCase):

    def test_delete(self):
        h = ExecutionHistory(_ws("del"))
        h.record(_rt(execution_id="e1"))
        h.record(_rt(execution_id="e2"))
        self.assertTrue(h.delete("e1"))
        self.assertEqual(h.count(), 1)

    def test_delete_nonexistent(self):
        h = ExecutionHistory(_ws("delne"))
        self.assertFalse(h.delete("ghost"))

    def test_clear(self):
        h = ExecutionHistory(_ws("clear"))
        h.record(_rt(execution_id="e1"))
        h.record(_rt(execution_id="e2"))
        h.clear()
        self.assertEqual(h.count(), 0)


# ===========================================================================
# 7. FIFO limit
# ===========================================================================

class TestFIFO(unittest.TestCase):

    def test_drops_oldest(self):
        h = ExecutionHistory(_ws("fifo"), max_entries=5)
        for i in range(8):
            h.record(_rt(execution_id=f"exec_{i:03d}"))
        self.assertEqual(h.count(), 5)
        ids = [e["execution_id"] for e in h.get_recent(5)]
        self.assertNotIn("exec_000", ids)
        self.assertIn("exec_007", ids)


# ===========================================================================
# 8. Persistence
# ===========================================================================

class TestPersistence(unittest.TestCase):

    def test_survives_reload(self):
        path = _ws("persist")
        h1 = ExecutionHistory(path)
        h1.record(_rt(execution_id="e_persist"), intent="test persist")
        h2 = ExecutionHistory(path)
        self.assertEqual(h2.count(), 1)
        self.assertEqual(h2.get_recent(1)[0]["intent"], "test persist")

    def test_corrupt_file_recovers(self):
        path = _ws("corrupt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("INVALID", encoding="utf-8")
        h = ExecutionHistory(path)
        self.assertEqual(h.count(), 0)


# ===========================================================================
# 9. Error resilience
# ===========================================================================

class TestResilience(unittest.TestCase):

    def test_record_never_raises(self):
        h = ExecutionHistory(_ws("safe"))
        h.record(None)
        h.record("not a dict")
        h.record(42)
        self.assertEqual(h.count(), 0)


# ===========================================================================
# 10. Integration with ObservationLogger
# ===========================================================================

class TestLoggerIntegration(unittest.TestCase):

    def test_logger_feeds_history(self):
        path = _ws("logger")
        hist = ExecutionHistory(path)
        logger = ObservationLogger(execution_history=hist)
        logger.initialize("test_cap")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        logger.mark_step_started("s1", {})
        logger.mark_step_succeeded("s1", {"stdout": "ok"}, {})
        logger.finish(status="ready", final_output={"stdout": "ok"}, state_snapshot={})
        self.assertEqual(hist.count(), 1)
        entry = hist.get_recent(1)[0]
        self.assertEqual(entry["capability_id"], "test_cap")
        self.assertEqual(entry["status"], "ready")


if __name__ == "__main__":
    unittest.main()
