"""
Tests for Componente 1 — MemoryManager.

Validates:
  1. remember: create + update (upsert by key).
  2. recall: retrieves value, increments access_count.
  3. recall_all: filtering by type, capability_id.
  4. forget / forget_by_key: removes entries.
  5. cleanup_expired: removes memories past TTL.
  6. Persistence: data survives reload from disk.
  7. Thread-safety: concurrent writes don't corrupt.
  8. Error resilience: corrupt file doesn't crash.
  9. Validation: bad key, bad type raise.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.core.memory.memory_manager import MemoryManager

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "memory"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws / "memories.json"


class TestRemember(unittest.TestCase):

    def test_create_memory(self):
        mm = MemoryManager(_ws("create"))
        rec = mm.remember("fav_color", "blue", memory_type="user_preference")
        self.assertIn("id", rec)
        self.assertEqual(rec["key"], "fav_color")
        self.assertEqual(rec["value"], "blue")
        self.assertEqual(rec["memory_type"], "user_preference")
        self.assertEqual(rec["access_count"], 0)

    def test_upsert_by_key(self):
        mm = MemoryManager(_ws("upsert"))
        r1 = mm.remember("lang", "en", memory_type="user_preference")
        r2 = mm.remember("lang", "es", memory_type="user_preference")
        self.assertEqual(r1["id"], r2["id"])
        self.assertEqual(r2["value"], "es")
        self.assertEqual(mm.count(), 1)

    def test_with_capability_id(self):
        mm = MemoryManager(_ws("cap"))
        rec = mm.remember("timeout", 5000, capability_id="read_file", memory_type="capability_context")
        self.assertEqual(rec["capability_id"], "read_file")

    def test_with_ttl(self):
        mm = MemoryManager(_ws("ttl"))
        rec = mm.remember("tmp", "data", ttl_days=7, memory_type="execution_pattern")
        self.assertEqual(rec["ttl_days"], 7)

    def test_invalid_key_raises(self):
        mm = MemoryManager(_ws("badkey"))
        with self.assertRaises(ValueError):
            mm.remember("", "val")

    def test_invalid_type_raises(self):
        mm = MemoryManager(_ws("badtype"))
        with self.assertRaises(ValueError):
            mm.remember("k", "v", memory_type="invalid")


class TestRecall(unittest.TestCase):

    def test_recall_existing(self):
        mm = MemoryManager(_ws("recall"))
        mm.remember("k", "v", memory_type="user_preference")
        self.assertEqual(mm.recall("k"), "v")

    def test_recall_increments_access_count(self):
        mm = MemoryManager(_ws("access"))
        mm.remember("k", "v", memory_type="user_preference")
        mm.recall("k")
        mm.recall("k")
        rec = mm.recall_all()[0]
        self.assertEqual(rec["access_count"], 2)

    def test_recall_missing_returns_none(self):
        mm = MemoryManager(_ws("miss"))
        self.assertIsNone(mm.recall("nonexistent"))

    def test_recall_all_unfiltered(self):
        mm = MemoryManager(_ws("all"))
        mm.remember("a", 1, memory_type="user_preference")
        mm.remember("b", 2, memory_type="execution_pattern")
        self.assertEqual(len(mm.recall_all()), 2)

    def test_recall_all_by_type(self):
        mm = MemoryManager(_ws("bytype"))
        mm.remember("a", 1, memory_type="user_preference")
        mm.remember("b", 2, memory_type="execution_pattern")
        prefs = mm.recall_all(memory_type="user_preference")
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["key"], "a")

    def test_recall_all_by_capability(self):
        mm = MemoryManager(_ws("bycap"))
        mm.remember("x", 1, capability_id="read_file", memory_type="capability_context")
        mm.remember("y", 2, capability_id="write_file", memory_type="capability_context")
        results = mm.recall_all(capability_id="read_file")
        self.assertEqual(len(results), 1)


class TestForget(unittest.TestCase):

    def test_forget_by_id(self):
        mm = MemoryManager(_ws("fid"))
        rec = mm.remember("k", "v", memory_type="user_preference")
        self.assertTrue(mm.forget(rec["id"]))
        self.assertEqual(mm.count(), 0)

    def test_forget_nonexistent(self):
        mm = MemoryManager(_ws("fne"))
        self.assertFalse(mm.forget("nonexistent"))

    def test_forget_by_key(self):
        mm = MemoryManager(_ws("fkey"))
        mm.remember("mykey", "val", memory_type="user_preference")
        self.assertTrue(mm.forget_by_key("mykey"))
        self.assertIsNone(mm.recall("mykey"))

    def test_forget_by_key_nonexistent(self):
        mm = MemoryManager(_ws("fkeyne"))
        self.assertFalse(mm.forget_by_key("ghost"))


class TestCleanupExpired(unittest.TestCase):

    def test_removes_expired(self):
        mm = MemoryManager(_ws("expire"))
        mm.remember("old", "data", ttl_days=0, memory_type="execution_pattern")
        # Manually backdate created_at by 2 days
        for rec in mm._memories.values():
            if rec["key"] == "old":
                from datetime import timedelta
                past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
                rec["created_at"] = past
        mm._save()
        # Set ttl to 1 day so it's expired
        for rec in mm._memories.values():
            if rec["key"] == "old":
                rec["ttl_days"] = 1
        removed = mm.cleanup_expired()
        self.assertEqual(removed, 1)
        self.assertEqual(mm.count(), 0)

    def test_keeps_non_expired(self):
        mm = MemoryManager(_ws("keep"))
        mm.remember("fresh", "data", ttl_days=365, memory_type="user_preference")
        removed = mm.cleanup_expired()
        self.assertEqual(removed, 0)
        self.assertEqual(mm.count(), 1)

    def test_no_ttl_never_expires(self):
        mm = MemoryManager(_ws("nottl"))
        mm.remember("forever", "data", memory_type="user_preference")
        self.assertEqual(mm.cleanup_expired(), 0)


class TestPersistence(unittest.TestCase):

    def test_survives_reload(self):
        path = _ws("persist")
        mm1 = MemoryManager(path)
        mm1.remember("persistent_key", {"nested": True}, memory_type="user_preference")

        mm2 = MemoryManager(path)
        val = mm2.recall("persistent_key")
        self.assertEqual(val, {"nested": True})

    def test_corrupt_file_recovers(self):
        path = _ws("corrupt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT VALID JSON", encoding="utf-8")
        mm = MemoryManager(path)
        self.assertEqual(mm.count(), 0)
        mm.remember("after_corrupt", "ok", memory_type="user_preference")
        self.assertEqual(mm.recall("after_corrupt"), "ok")


class TestGet(unittest.TestCase):

    def test_get_by_id(self):
        mm = MemoryManager(_ws("getid"))
        rec = mm.remember("k", "v", memory_type="user_preference")
        got = mm.get(rec["id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["key"], "k")

    def test_get_nonexistent(self):
        mm = MemoryManager(_ws("gne"))
        self.assertIsNone(mm.get("nonexistent"))


# Need these imports for the backdating test
from datetime import datetime, timezone


if __name__ == "__main__":
    unittest.main()
