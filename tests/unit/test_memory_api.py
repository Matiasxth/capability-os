"""
Tests for Componente 4 — Memory API.

Validates the 7 memory endpoints through the underlying components
(not HTTP — we test the service methods directly, same as other API tests).

  1. GET /memory/context — returns user context dict.
  2. GET /memory/history — returns recent entries.
  3. GET /memory/history?capability_id=X — filtered.
  4. DELETE /memory/history/{id} — removes entry.
  5. GET /memory/preferences — returns custom prefs.
  6. POST /memory/preferences — updates prefs.
  7. DELETE /memory — clears everything.
  8. Integration: execution → history → context learns.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.core.memory import ExecutionHistory, MemoryManager, UserContext

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "memory_api"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _rt(cap_id: str = "read_file", exec_id: str = "exec_001") -> dict[str, Any]:
    return {
        "execution_id": exec_id,
        "capability_id": cap_id,
        "status": "ready",
        "duration_ms": 100,
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:00.100Z",
        "error_code": None, "error_message": None,
        "failed_step": None, "final_output": {"stdout": "ok"},
        "state": {}, "logs": [], "retry_count": 0,
        "current_step": None, "last_completed_step": None,
    }


# ===========================================================================
# 1. GET /memory/context
# ===========================================================================

class TestMemoryContext(unittest.TestCase):

    def test_fresh_context(self):
        ws = _ws("ctx_fresh")
        mm = MemoryManager(ws / "memories.json")
        ctx = UserContext(mm)
        result = ctx.get_context()
        self.assertIn("preferred_language", result)
        self.assertIn("frequent_capabilities", result)
        self.assertIn("custom_preferences", result)

    def test_context_with_data(self):
        ws = _ws("ctx_data")
        mm = MemoryManager(ws / "memories.json")
        ctx = UserContext(mm)
        ctx.set_language("es")
        ctx.set_preference("theme", "dark")
        result = ctx.get_context()
        self.assertEqual(result["preferred_language"], "es")
        self.assertEqual(result["custom_preferences"]["theme"], "dark")


# ===========================================================================
# 2. GET /memory/history
# ===========================================================================

class TestMemoryHistory(unittest.TestCase):

    def test_recent(self):
        ws = _ws("hist_recent")
        h = ExecutionHistory(ws / "history.json")
        h.record(_rt(exec_id="exec_a"), intent="read file")
        h.record(_rt(exec_id="exec_b"), intent="write file")
        entries = h.get_recent(20)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["execution_id"], "exec_b")

    def test_filtered_by_capability(self):
        ws = _ws("hist_filter")
        h = ExecutionHistory(ws / "history.json")
        h.record(_rt(cap_id="cap_a", exec_id="e1"))
        h.record(_rt(cap_id="cap_b", exec_id="e2"))
        h.record(_rt(cap_id="cap_a", exec_id="e3"))
        results = h.get_by_capability("cap_a")
        self.assertEqual(len(results), 2)


# ===========================================================================
# 3. DELETE /memory/history/{id}
# ===========================================================================

class TestDeleteHistory(unittest.TestCase):

    def test_delete_entry(self):
        ws = _ws("hist_del")
        h = ExecutionHistory(ws / "history.json")
        h.record(_rt(exec_id="exec_del"))
        self.assertTrue(h.delete("exec_del"))
        self.assertEqual(h.count(), 0)

    def test_delete_nonexistent(self):
        ws = _ws("hist_del_ne")
        h = ExecutionHistory(ws / "history.json")
        self.assertFalse(h.delete("ghost"))


# ===========================================================================
# 4. GET/POST /memory/preferences
# ===========================================================================

class TestPreferencesAPI(unittest.TestCase):

    def test_get_empty(self):
        ws = _ws("prefs_empty")
        ctx = UserContext(MemoryManager(ws / "memories.json"))
        prefs = ctx.get_context().get("custom_preferences", {})
        self.assertEqual(prefs, {})

    def test_set_and_get(self):
        ws = _ws("prefs_set")
        ctx = UserContext(MemoryManager(ws / "memories.json"))
        ctx.set_preference("editor", "vim")
        ctx.set_preference("tab_size", 4)
        prefs = ctx.get_context()["custom_preferences"]
        self.assertEqual(prefs["editor"], "vim")
        self.assertEqual(prefs["tab_size"], 4)


# ===========================================================================
# 5. DELETE /memory
# ===========================================================================

class TestClearMemory(unittest.TestCase):

    def test_clears_all(self):
        ws = _ws("clear_all")
        mm = MemoryManager(ws / "memories.json")
        h = ExecutionHistory(ws / "history.json")
        ctx = UserContext(mm)

        ctx.set_language("en")
        ctx.set_preference("key", "val")
        h.record(_rt(), intent="test")

        # Clear history
        h.clear()
        self.assertEqual(h.count(), 0)

        # Clear memories
        for rec in mm.recall_all():
            mm.forget(rec["id"])
        self.assertEqual(mm.count(), 0)

        # Context is now empty
        result = ctx.get_context()
        self.assertIsNone(result["preferred_language"])
        self.assertEqual(result["custom_preferences"], {})


# ===========================================================================
# 6. Integration: execution → history + context learning
# ===========================================================================

class TestIntegrationFlow(unittest.TestCase):

    def test_execution_feeds_both(self):
        ws = _ws("integration")
        mm = MemoryManager(ws / "memories.json")
        h = ExecutionHistory(ws / "history.json")
        ctx = UserContext(mm)

        rt = _rt(cap_id="read_file", exec_id="exec_int")

        # Simulate what ObservationLogger does
        h.record(rt, intent="read my data")
        ctx.learn_from_execution(rt)

        # History has the entry
        self.assertEqual(h.count(), 1)
        self.assertEqual(h.get_recent(1)[0]["intent"], "read my data")

        # UserContext learned the capability usage
        ctx.refresh_frequent_capabilities()
        freq = ctx.get_context()["frequent_capabilities"]
        self.assertIn("read_file", freq)

    def test_multiple_executions_build_profile(self):
        ws = _ws("profile")
        mm = MemoryManager(ws / "memories.json")
        h = ExecutionHistory(ws / "history.json")
        ctx = UserContext(mm)

        for i in range(5):
            rt = _rt(cap_id="create_project", exec_id=f"exec_{i:03d}")
            h.record(rt, intent=f"create project {i}")
            ctx.learn_from_execution(rt)

        for i in range(3):
            rt = _rt(cap_id="read_file", exec_id=f"exec_r{i}")
            h.record(rt)
            ctx.learn_from_execution(rt)

        self.assertEqual(h.count(), 8)
        ctx.refresh_frequent_capabilities()
        freq = ctx.get_context()["frequent_capabilities"]
        self.assertEqual(freq[0], "create_project")  # most used

    def test_persistence_across_restarts(self):
        ws = _ws("restart")
        # Session 1
        mm1 = MemoryManager(ws / "memories.json")
        h1 = ExecutionHistory(ws / "history.json")
        ctx1 = UserContext(mm1)
        h1.record(_rt(exec_id="exec_s1"), intent="session one")
        ctx1.set_preference("theme", "dark")
        ctx1.learn_from_execution(_rt(cap_id="cap_a"))
        ctx1.refresh_frequent_capabilities()

        # Session 2 — new instances, same files
        mm2 = MemoryManager(ws / "memories.json")
        h2 = ExecutionHistory(ws / "history.json")
        ctx2 = UserContext(mm2)

        self.assertEqual(h2.count(), 1)
        self.assertEqual(h2.get_recent(1)[0]["intent"], "session one")
        self.assertEqual(ctx2.get_preference("theme"), "dark")
        self.assertIn("cap_a", ctx2.get_context()["frequent_capabilities"])


if __name__ == "__main__":
    unittest.main()
