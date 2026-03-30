"""Tests for execution SSE streaming — ObservationLogger event_callback."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

from system.core.observation.observation_logger import ObservationLogger


class TestObservationLoggerCallback(unittest.TestCase):

    def test_callback_receives_events(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("test_capability")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "execution_started")

    def test_callback_receives_step_events(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("test_cap")
        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        logger.mark_step_started("step_1", {"path": "/tmp/test"})
        logger.mark_step_succeeded("step_1", {"status": "ok"}, {})
        event_names = [e["event"] for e in events]
        self.assertEqual(event_names, [
            "execution_started",
            "capability_resolved",
            "validation_passed",
            "step_started",
            "step_succeeded",
        ])

    def test_callback_receives_failure_events(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("test_cap")
        logger.mark_step_started("step_1", {})
        logger.mark_step_failed("step_1", "err_code", "something broke", {})
        failed_events = [e for e in events if e["event"] == "step_failed"]
        self.assertEqual(len(failed_events), 1)
        self.assertEqual(failed_events[0]["payload"]["error_code"], "err_code")

    def test_callback_receives_finish_event(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("test_cap")
        logger.finish(status="ready", final_output={"result": 42}, state_snapshot={})
        finished = [e for e in events if e["event"] == "execution_finished"]
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["payload"]["status"], "ready")

    def test_no_callback_works(self):
        """Logger without callback should work normally."""
        logger = ObservationLogger()
        logger.initialize("test_cap")
        logger.mark_capability_resolved()
        model = logger.get_runtime_model()
        self.assertEqual(len(model["logs"]), 2)

    def test_broken_callback_does_not_crash(self):
        """A callback that raises should not break the logger."""
        def bad_callback(e):
            raise RuntimeError("callback broken")

        logger = ObservationLogger(event_callback=bad_callback)
        logger.initialize("test_cap")
        # Should not raise
        logger.mark_capability_resolved()
        model = logger.get_runtime_model()
        self.assertEqual(len(model["logs"]), 2)

    def test_callback_payload_has_step_id(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("cap")
        logger.mark_step_started("s1", {"key": "val"})
        step_event = events[-1]
        self.assertEqual(step_event["payload"]["step_id"], "s1")
        self.assertEqual(step_event["payload"]["params"]["key"], "val")

    def test_callback_event_has_timestamp(self):
        events: list[dict[str, Any]] = []
        logger = ObservationLogger(event_callback=lambda e: events.append(e))
        logger.initialize("cap")
        self.assertIn("timestamp", events[0])
        self.assertTrue(events[0]["timestamp"].endswith("Z"))


class TestCapabilityEngineEventCallback(unittest.TestCase):
    """Test that CapabilityEngine passes event_callback to ObservationLogger."""

    def test_engine_execute_accepts_event_callback(self):
        from system.core.capability_engine import CapabilityEngine
        import inspect

        sig = inspect.signature(CapabilityEngine.execute)
        self.assertIn("event_callback", sig.parameters)


if __name__ == "__main__":
    unittest.main()
