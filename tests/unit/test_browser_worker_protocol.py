from __future__ import annotations

import json
import unittest

from system.browser_worker.protocol_handler import (
    BrowserWorkerProtocolError,
    build_error_response,
    build_success_response,
    parse_incoming_line,
)


class BrowserWorkerProtocolTests(unittest.TestCase):
    def test_parse_valid_command_message(self) -> None:
        raw = json.dumps(
            {
                "protocol_version": "1.0",
                "message_type": "command",
                "request_id": "req_1",
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "backend",
                "target": "browser_worker",
                "action": "browser_navigate",
                "session_id": "session_1",
                "payload": {"url": "https://example.org/"},
                "metadata": {"timeout_ms": 15000, "trace_id": "trace_1"},
            }
        )
        parsed = parse_incoming_line(raw)
        self.assertEqual(parsed["message_type"], "command")
        self.assertEqual(parsed["action"], "browser_navigate")

    def test_parse_invalid_message_type(self) -> None:
        raw = json.dumps(
            {
                "protocol_version": "1.0",
                "message_type": "response",
                "request_id": "req_1",
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "backend",
                "target": "browser_worker",
                "action": "browser_navigate",
                "session_id": None,
                "payload": {},
                "metadata": {},
            }
        )
        with self.assertRaises(BrowserWorkerProtocolError):
            parse_incoming_line(raw)

    def test_build_success_and_error_responses(self) -> None:
        request = {
            "protocol_version": "1.0",
            "message_type": "command",
            "request_id": "req_x",
            "timestamp": "2026-01-01T00:00:00Z",
            "source": "backend",
            "target": "browser_worker",
            "action": "browser_open_session",
            "session_id": None,
            "payload": {"headless": True},
            "metadata": {"trace_id": "trace_x"},
        }

        success = build_success_response(
            request,
            result={"status": "success", "session_id": "session_1"},
            duration_ms=9,
        )
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["result"]["session_id"], "session_1")
        self.assertEqual(success["metadata"]["duration_ms"], 9)
        self.assertEqual(success["metadata"]["trace_id"], "trace_x")

        error = build_error_response(
            request,
            error_code="navigation_failed",
            error_message="Navigation failed",
            details={"url": "https://example.org/"},
            duration_ms=12,
        )
        self.assertEqual(error["status"], "error")
        self.assertEqual(error["error"]["error_code"], "navigation_failed")
        self.assertEqual(error["metadata"]["duration_ms"], 12)


if __name__ == "__main__":
    unittest.main()

