"""Tests for session compaction in ExecutionHistory."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from system.core.memory.execution_history import ExecutionHistory


class TestGetCompactableSessions(unittest.TestCase):

    def _create_history(self) -> tuple[ExecutionHistory, Path]:
        tmp = tempfile.mktemp(suffix=".json")
        return ExecutionHistory(tmp), Path(tmp)

    def _old_timestamp(self, hours_ago: int = 48) -> str:
        dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return dt.isoformat().replace("+00:00", "Z")

    def _fresh_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def test_returns_old_sessions_with_many_messages(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        h.upsert_chat(session_id="old_session", intent="test", messages=msgs)
        # Manually set timestamp to old
        with h._lock:
            for e in h._entries:
                if e["execution_id"] == "old_session":
                    e["timestamp"] = self._old_timestamp(48)
            h._save()
        result = h.get_compactable_sessions(max_age_hours=24)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["execution_id"], "old_session")

    def test_ignores_recent_sessions(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        h.upsert_chat(session_id="fresh_session", intent="test", messages=msgs)
        result = h.get_compactable_sessions(max_age_hours=24)
        self.assertEqual(len(result), 0)

    def test_ignores_sessions_with_few_messages(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        h.upsert_chat(session_id="short_session", intent="test", messages=msgs)
        with h._lock:
            for e in h._entries:
                if e["execution_id"] == "short_session":
                    e["timestamp"] = self._old_timestamp(48)
            h._save()
        result = h.get_compactable_sessions(max_age_hours=24)
        self.assertEqual(len(result), 0)

    def test_ignores_already_compacted(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        h.upsert_chat(session_id="compacted_one", intent="test", messages=msgs)
        with h._lock:
            for e in h._entries:
                if e["execution_id"] == "compacted_one":
                    e["timestamp"] = self._old_timestamp(48)
                    e["compacted"] = True
            h._save()
        result = h.get_compactable_sessions(max_age_hours=24)
        self.assertEqual(len(result), 0)


class TestCompactSession(unittest.TestCase):

    def _create_history(self) -> tuple[ExecutionHistory, Path]:
        tmp = tempfile.mktemp(suffix=".json")
        return ExecutionHistory(tmp), Path(tmp)

    def test_compact_replaces_messages_with_summary(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        h.upsert_chat(session_id="to_compact", intent="test", messages=msgs)
        result = h.compact_session("to_compact", "This was a conversation about testing.")
        self.assertTrue(result)
        session = h.get_session("to_compact")
        self.assertEqual(len(session["chat_messages"]), 1)
        self.assertEqual(session["chat_messages"][0]["type"], "summary")
        self.assertIn("testing", session["chat_messages"][0]["content"])
        self.assertTrue(session["compacted"])
        self.assertEqual(session["compacted_from"], 10)

    def test_compact_nonexistent_returns_false(self):
        h, _ = self._create_history()
        result = h.compact_session("nonexistent", "summary")
        self.assertFalse(result)

    def test_compact_persists(self):
        h, path = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(8)]
        h.upsert_chat(session_id="persist_test", intent="test", messages=msgs)
        h.compact_session("persist_test", "Summary text")
        # Reload from disk
        h2 = ExecutionHistory(path)
        session = h2.get_session("persist_test")
        self.assertTrue(session["compacted"])
        self.assertEqual(session["message_count"], 1)

    def test_compacted_session_not_recompactable(self):
        h, _ = self._create_history()
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        h.upsert_chat(session_id="double_compact", intent="test", messages=msgs)
        # Manually age it
        with h._lock:
            for e in h._entries:
                if e["execution_id"] == "double_compact":
                    e["timestamp"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
            h._save()
        # Compact it
        h.compact_session("double_compact", "Summary")
        # Should no longer appear in compactable
        result = h.get_compactable_sessions(max_age_hours=24)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
