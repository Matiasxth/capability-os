from __future__ import annotations

import unittest

from system.core.observation import ObservationLogger


class ObservationLoggerTests(unittest.TestCase):
    def test_emits_events_and_updates_runtime_model(self) -> None:
        logger = ObservationLogger()
        runtime = logger.initialize("create_project")
        execution_id = runtime["execution_id"]

        logger.mark_capability_resolved()
        logger.mark_validation_passed()
        logger.mark_step_started("create_project", {"command": "create demo"})
        logger.mark_step_succeeded("create_project", {"project_path": "/tmp/demo"}, {"project_path": "/tmp/demo"})
        finished = logger.finish(
            status="ready",
            final_output={"status": "success"},
            state_snapshot={"project_path": "/tmp/demo", "status": "success"},
        )

        self.assertEqual(finished["execution_id"], execution_id)
        self.assertEqual(finished["status"], "ready")
        self.assertIsNotNone(finished["ended_at"])
        self.assertGreaterEqual(finished["duration_ms"], 0)
        self.assertEqual(finished["final_output"], {"status": "success"})

        events = [entry["event"] for entry in finished["logs"]]
        self.assertEqual(events[0], "execution_started")
        self.assertIn("capability_resolved", events)
        self.assertIn("validation_passed", events)
        self.assertIn("step_started", events)
        self.assertIn("step_succeeded", events)
        self.assertEqual(events[-1], "execution_finished")

    def test_requires_error_code_on_error_finish(self) -> None:
        logger = ObservationLogger()
        logger.initialize("create_project")
        with self.assertRaises(ValueError):
            logger.finish(status="error", final_output={}, state_snapshot={})


if __name__ == "__main__":
    unittest.main()
