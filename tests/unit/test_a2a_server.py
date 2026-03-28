"""Tests for A2A Server (Componente 2)."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.a2a.a2a_server import A2AServer
from system.core.capability_engine import CapabilityEngine

ROOT = Path(__file__).resolve().parents[2]


def _registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    return reg


def _mock_engine(final_output: dict | None = None) -> CapabilityEngine:
    engine = MagicMock(spec=CapabilityEngine)
    engine.execute.return_value = {
        "execution_id": "exec_test",
        "capability_id": "read_file",
        "status": "success",
        "final_output": final_output or {"content": "file data", "path": "/tmp/f"},
    }
    return engine


class TestA2AServerHappyPath(unittest.TestCase):

    def test_valid_task_executes_and_returns_artifact(self):
        reg = _registry()
        server = A2AServer(reg, _mock_engine())
        result = server.handle_task({
            "skill_id": "read_file",
            "message": {"parts": [{"type": "text", "text": '{"path": "/tmp/test.txt"}'}]},
        })
        self.assertEqual(result["status"]["state"], "completed")
        self.assertTrue(len(result["artifacts"]) >= 1)
        text = result["artifacts"][0]["parts"][0]["text"]
        self.assertIn("file data", text)

    def test_string_message_maps_to_first_required_input(self):
        reg = _registry()
        server = A2AServer(reg, _mock_engine())
        result = server.handle_task({
            "skill_id": "read_file",
            "message": "my_file.txt",
        })
        self.assertEqual(result["status"]["state"], "completed")
        # The engine should have been called with {"path": "my_file.txt"}
        call_args = server._engine.execute.call_args
        inputs = call_args[0][1]  # second positional arg
        self.assertEqual(inputs.get("path"), "my_file.txt")


class TestA2AServerErrors(unittest.TestCase):

    def test_unknown_skill_returns_failed(self):
        reg = _registry()
        server = A2AServer(reg, _mock_engine())
        result = server.handle_task({"skill_id": "nonexistent_skill", "message": "hello"})
        self.assertEqual(result["status"]["state"], "failed")
        self.assertEqual(result["status"]["error"]["code"], "skill_not_found")

    def test_no_engine_returns_failed(self):
        reg = _registry()
        server = A2AServer(reg, capability_engine=None)
        result = server.handle_task({"skill_id": "read_file", "message": "test"})
        self.assertEqual(result["status"]["state"], "failed")
        self.assertEqual(result["status"]["error"]["code"], "no_engine")


class TestA2AServerEvents(unittest.TestCase):

    def test_events_for_completed_task(self):
        reg = _registry()
        server = A2AServer(reg, _mock_engine())
        task = server.handle_task({"skill_id": "read_file", "message": '{"path": "x"}'})
        events = server.list_events(task["id"])
        self.assertIsNotNone(events)
        self.assertTrue(any(e["type"] == "status" for e in events))
        self.assertTrue(any(e["type"] == "artifact" for e in events))

    def test_events_for_unknown_task(self):
        server = A2AServer(_registry())
        self.assertIsNone(server.list_events("nonexistent_task"))


if __name__ == "__main__":
    unittest.main()
