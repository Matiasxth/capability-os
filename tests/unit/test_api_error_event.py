"""Tests for API server catch-all error handling and event emission."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch, MagicMock

from system.core.ui_bridge.api_server import (
    CapabilityOSUIBridgeService,
    CapabilityOSRequestHandler,
    APIResponse,
)


class _FakeService(CapabilityOSUIBridgeService):
    """Minimal service stub that raises on a specific route."""

    def __init__(self):
        # Skip parent __init__ entirely — we only need handle()
        from system.core.ui_bridge.router import Router
        self._router = Router()
        self._router.add("GET", "/explode", self._boom)

    @staticmethod
    def _boom(service, payload, **kw):
        raise RuntimeError("kaboom")


class TestApiErrorEvent(unittest.TestCase):
    server: HTTPServer
    port: int

    @classmethod
    def setUpClass(cls):
        svc = _FakeService()
        cls.server = HTTPServer(("127.0.0.1", 0), CapabilityOSRequestHandler)
        cls.server.service = svc  # type: ignore[attr-defined]
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path: str) -> tuple[int, dict]:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_unhandled_exception_returns_500_json(self):
        code, body = self._get("/explode")
        self.assertEqual(code, 500)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "internal_error")

    def test_unhandled_exception_emits_error_event(self):
        emitted = []
        with patch("system.core.ui_bridge.event_bus.event_bus") as mock_bus:
            mock_bus.emit = lambda t, d: emitted.append((t, d))
            self._get("/explode")
        self.assertTrue(any(t == "error" for t, _ in emitted), "Expected 'error' event to be emitted")

    def test_normal_404_still_works(self):
        code, body = self._get("/nonexistent")
        self.assertEqual(code, 404)
        self.assertEqual(body["error_code"], "endpoint_not_found")
