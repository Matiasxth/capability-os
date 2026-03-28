"""Tests for A2A Client (Componente 3)."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from system.core.a2a.a2a_client import A2AClient, A2AClientError, register_a2a_delegate_tool
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime


# ---------------------------------------------------------------------------
# Fake A2A agent HTTP server for tests
# ---------------------------------------------------------------------------

_FAKE_CARD = {
    "name": "Fake Agent",
    "description": "Test",
    "url": "http://localhost",
    "version": "1.0.0",
    "skills": [{"id": "greet", "name": "Greet", "description": "Say hi"}],
}

_FAKE_TASK_RESULT = {
    "id": "task_fake",
    "skill_id": "greet",
    "status": {"state": "completed"},
    "artifacts": [{"parts": [{"type": "text", "text": "Hello!"}]}],
}


class _FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/.well-known/agent.json":
            self._json_response(200, _FAKE_CARD)
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/a2a":
            self._json_response(200, _FAKE_TASK_RESULT)
        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a): pass


class TestA2AClientDiscover(unittest.TestCase):

    server: HTTPServer
    port: int

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_discover_returns_card(self):
        client = A2AClient(f"http://127.0.0.1:{self.port}")
        card = client.discover()
        self.assertEqual(card["name"], "Fake Agent")
        self.assertTrue(len(card["skills"]) >= 1)

    def test_send_task_returns_artifact(self):
        client = A2AClient(f"http://127.0.0.1:{self.port}")
        result = client.send_task("greet", "Hi there")
        self.assertEqual(result["status"]["state"], "completed")
        self.assertEqual(result["artifacts"][0]["parts"][0]["text"], "Hello!")

    def test_unreachable_agent_raises(self):
        client = A2AClient("http://127.0.0.1:1")  # nothing on port 1
        with self.assertRaises(A2AClientError) as ctx:
            client.discover()
        self.assertEqual(ctx.exception.code, "a2a_unreachable")


class TestA2ADelegateTool(unittest.TestCase):

    def test_tool_registers(self):
        reg = ToolRegistry()
        runtime = ToolRuntime(reg)
        register_a2a_delegate_tool(reg, runtime)
        self.assertIsNotNone(reg.get("a2a_delegate_task"))

    def test_schema_accepts_a2a_category(self):
        reg = ToolRegistry()
        from system.core.a2a.a2a_client import _DELEGATE_TOOL_CONTRACT
        reg.register(_DELEGATE_TOOL_CONTRACT, source="test")
        self.assertEqual(reg.get("a2a_delegate_task")["category"], "a2a")


if __name__ == "__main__":
    unittest.main()
