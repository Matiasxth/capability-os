"""
Tests for Componente 2 — UserContext.

Validates:
  1. get_context: returns full dict with all fields.
  2. set/get preferences: custom key-value pairs.
  3. set_language / set_workspace_path: stored and recalled.
  4. learn_from_execution: increments capability usage counter.
  5. refresh_frequent_capabilities: returns top-N sorted.
  6. Language hint detection from runtime state.
  7. Error resilience: learn never raises.
  8. Empty state: fresh context returns defaults.
"""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import Any

from system.core.memory.memory_manager import MemoryManager
from system.core.memory.user_context import UserContext

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "user_ctx"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws / "memories.json"


def _runtime(cap_id: str = "read_file", status: str = "ready", state: dict | None = None) -> dict[str, Any]:
    return {
        "execution_id": "exec_test",
        "capability_id": cap_id,
        "status": status,
        "duration_ms": 100,
        "state": state or {},
        "logs": [],
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:00.100Z",
        "retry_count": 0,
        "error_code": None,
        "error_message": None,
        "last_completed_step": None,
        "failed_step": None,
        "final_output": {},
    }


# ===========================================================================
# 1. get_context — full dict
# ===========================================================================

class TestGetContext(unittest.TestCase):

    def test_fresh_context_has_all_keys(self):
        ctx = UserContext(MemoryManager(_ws("fresh")))
        result = ctx.get_context()
        for key in ("preferred_language", "frequent_capabilities", "last_workspace_path", "custom_preferences"):
            self.assertIn(key, result)

    def test_fresh_context_defaults(self):
        ctx = UserContext(MemoryManager(_ws("defaults")))
        result = ctx.get_context()
        self.assertIsNone(result["preferred_language"])
        self.assertEqual(result["frequent_capabilities"], [])
        self.assertIsNone(result["last_workspace_path"])
        self.assertEqual(result["custom_preferences"], {})

    def test_populated_context(self):
        mm = MemoryManager(_ws("pop"))
        ctx = UserContext(mm)
        ctx.set_language("es")
        ctx.set_workspace_path("/projects")
        ctx.set_preference("theme", "dark")
        result = ctx.get_context()
        self.assertEqual(result["preferred_language"], "es")
        self.assertEqual(result["last_workspace_path"], "/projects")
        self.assertEqual(result["custom_preferences"]["theme"], "dark")


# ===========================================================================
# 2. Preferences
# ===========================================================================

class TestPreferences(unittest.TestCase):

    def test_set_and_get(self):
        ctx = UserContext(MemoryManager(_ws("prefs")))
        ctx.set_preference("editor", "vscode")
        self.assertEqual(ctx.get_preference("editor"), "vscode")

    def test_get_missing_returns_none(self):
        ctx = UserContext(MemoryManager(_ws("pmiss")))
        self.assertIsNone(ctx.get_preference("nonexistent"))

    def test_multiple_preferences(self):
        ctx = UserContext(MemoryManager(_ws("multi")))
        ctx.set_preference("a", 1)
        ctx.set_preference("b", 2)
        self.assertEqual(ctx.get_preference("a"), 1)
        self.assertEqual(ctx.get_preference("b"), 2)

    def test_overwrite_preference(self):
        ctx = UserContext(MemoryManager(_ws("overwrite")))
        ctx.set_preference("x", "old")
        ctx.set_preference("x", "new")
        self.assertEqual(ctx.get_preference("x"), "new")


# ===========================================================================
# 3. Language + workspace
# ===========================================================================

class TestLanguageWorkspace(unittest.TestCase):

    def test_set_language(self):
        ctx = UserContext(MemoryManager(_ws("lang")))
        ctx.set_language("fr")
        self.assertEqual(ctx.get_context()["preferred_language"], "fr")

    def test_set_workspace_path(self):
        ctx = UserContext(MemoryManager(_ws("wspath")))
        ctx.set_workspace_path("/home/user/projects")
        self.assertEqual(ctx.get_context()["last_workspace_path"], "/home/user/projects")


# ===========================================================================
# 4. learn_from_execution — capability usage
# ===========================================================================

class TestLearnFromExecution(unittest.TestCase):

    def test_increments_usage(self):
        mm = MemoryManager(_ws("usage"))
        ctx = UserContext(mm)
        ctx.learn_from_execution(_runtime("read_file"))
        ctx.learn_from_execution(_runtime("read_file"))
        ctx.learn_from_execution(_runtime("write_file"))
        # read_file should be 2, write_file 1
        val = mm.recall("usage:capability:read_file")
        self.assertEqual(val, 2)
        val2 = mm.recall("usage:capability:write_file")
        self.assertEqual(val2, 1)

    def test_missing_capability_id_ignored(self):
        ctx = UserContext(MemoryManager(_ws("nocap")))
        ctx.learn_from_execution({"status": "ready"})  # no capability_id
        # Should not crash
        self.assertEqual(ctx.get_context()["frequent_capabilities"], [])


# ===========================================================================
# 5. refresh_frequent_capabilities
# ===========================================================================

class TestFrequentCapabilities(unittest.TestCase):

    def test_top_n_sorted(self):
        mm = MemoryManager(_ws("topn"))
        ctx = UserContext(mm)
        for _ in range(10):
            ctx.learn_from_execution(_runtime("cap_a"))
        for _ in range(5):
            ctx.learn_from_execution(_runtime("cap_b"))
        for _ in range(3):
            ctx.learn_from_execution(_runtime("cap_c"))
        top = ctx.refresh_frequent_capabilities()
        self.assertEqual(top[0], "cap_a")
        self.assertEqual(top[1], "cap_b")
        self.assertEqual(top[2], "cap_c")

    def test_max_5(self):
        mm = MemoryManager(_ws("max5"))
        ctx = UserContext(mm)
        for i in range(8):
            ctx.learn_from_execution(_runtime(f"cap_{i}"))
        top = ctx.refresh_frequent_capabilities()
        self.assertLessEqual(len(top), 5)

    def test_empty_history(self):
        ctx = UserContext(MemoryManager(_ws("empty")))
        self.assertEqual(ctx.refresh_frequent_capabilities(), [])

    def test_persists_in_context(self):
        mm = MemoryManager(_ws("persist"))
        ctx = UserContext(mm)
        for _ in range(3):
            ctx.learn_from_execution(_runtime("cap_x"))
        ctx.refresh_frequent_capabilities()
        result = ctx.get_context()
        self.assertIn("cap_x", result["frequent_capabilities"])


# ===========================================================================
# 6. Language hint from state
# ===========================================================================

class TestLanguageHint(unittest.TestCase):

    def test_detects_language_field(self):
        mm = MemoryManager(_ws("lhint"))
        ctx = UserContext(mm)
        ctx.learn_from_execution(_runtime(state={"language": "es"}))
        self.assertEqual(ctx.get_context()["preferred_language"], "es")

    def test_detects_locale_field(self):
        mm = MemoryManager(_ws("locale"))
        ctx = UserContext(mm)
        ctx.learn_from_execution(_runtime(state={"locale": "en-US"}))
        self.assertEqual(ctx.get_context()["preferred_language"], "en-US")

    def test_ignores_short_values(self):
        mm = MemoryManager(_ws("short"))
        ctx = UserContext(mm)
        ctx.learn_from_execution(_runtime(state={"language": "x"}))
        # Too short, should not be stored
        self.assertIsNone(ctx.get_context()["preferred_language"])

    def test_no_state_no_crash(self):
        ctx = UserContext(MemoryManager(_ws("nostate")))
        ctx.learn_from_execution(_runtime(state=None))
        # No crash


# ===========================================================================
# 7. Error resilience
# ===========================================================================

class TestErrorResilience(unittest.TestCase):

    def test_learn_never_raises(self):
        ctx = UserContext(MemoryManager(_ws("safe")))
        # Pass garbage — should not raise
        ctx.learn_from_execution(None)
        ctx.learn_from_execution("not a dict")
        ctx.learn_from_execution(42)

    def test_get_context_never_raises(self):
        ctx = UserContext(MemoryManager(_ws("safe2")))
        # Even if memory is somehow broken, returns {}
        result = ctx.get_context()
        self.assertIsInstance(result, dict)


# ===========================================================================
# 8. Persistence across instances
# ===========================================================================

class TestPersistence(unittest.TestCase):

    def test_context_survives_reload(self):
        path = _ws("reload")
        mm1 = MemoryManager(path)
        ctx1 = UserContext(mm1)
        ctx1.set_language("de")
        ctx1.set_preference("key", "val")
        for _ in range(3):
            ctx1.learn_from_execution(_runtime("my_cap"))
        ctx1.refresh_frequent_capabilities()

        mm2 = MemoryManager(path)
        ctx2 = UserContext(mm2)
        result = ctx2.get_context()
        self.assertEqual(result["preferred_language"], "de")
        self.assertEqual(result["custom_preferences"]["key"], "val")
        self.assertIn("my_cap", result["frequent_capabilities"])


if __name__ == "__main__":
    unittest.main()
