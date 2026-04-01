"""Tests for distributed infrastructure: EventBus, EventBridge, JobQueue, MessageQueue."""
import json
import threading
import time
import unittest
from collections import deque
from unittest.mock import MagicMock, patch

from system.core.ui_bridge.event_bus import EventBus
from system.infrastructure.event_bridge import EventBridge
from system.infrastructure.job_queue import Job, JobQueue, JobStatus
from system.infrastructure.message_queue import InMemoryQueue


class TestEventBusBridge(unittest.TestCase):
    """Test EventBus with Redis bridge integration."""

    def test_emit_publishes_to_bridge(self):
        bus = EventBus()
        mock_queue = MagicMock()
        mock_queue.is_redis = True
        bus.set_bridge(mock_queue)
        bus.emit("test_event", {"key": "value"})
        mock_queue.publish.assert_called_once()
        args = mock_queue.publish.call_args
        self.assertIn("capos:events:test_event", args[0][0])
        payload = args[0][1]
        self.assertEqual(payload["type"], "test_event")
        self.assertEqual(payload["data"]["key"], "value")

    def test_emit_without_bridge_is_local_only(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: received.append(e))
        bus.emit("local_event", {"x": 1})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["type"], "local_event")

    def test_bridge_failure_does_not_crash_emit(self):
        bus = EventBus()
        mock_queue = MagicMock()
        mock_queue.publish.side_effect = ConnectionError("Redis down")
        bus.set_bridge(mock_queue)
        received = []
        bus.subscribe(lambda e: received.append(e))
        # Should not raise
        bus.emit("fail_test", {"a": 1})
        self.assertEqual(len(received), 1)

    def test_emit_local_skips_bridge(self):
        bus = EventBus()
        mock_queue = MagicMock()
        bus.set_bridge(mock_queue)
        received = []
        bus.subscribe(lambda e: received.append(e))
        bus._emit_local({"type": "from_redis", "data": {}})
        self.assertEqual(len(received), 1)
        # Bridge should NOT be called for _emit_local
        mock_queue.publish.assert_not_called()


class TestEventBridge(unittest.TestCase):
    """Test EventBridge reconnection and forwarding."""

    def test_start_connects_outbound(self):
        bus = EventBus()
        queue = MagicMock()
        queue.is_redis = False  # Skip inbound listener
        bridge = EventBridge(bus, queue)
        bridge.start()
        self.assertTrue(bus.has_bridge)
        bridge.stop()
        self.assertFalse(bus.has_bridge)

    def test_stop_disconnects(self):
        bus = EventBus()
        queue = MagicMock()
        queue.is_redis = False
        bridge = EventBridge(bus, queue)
        bridge.start()
        bridge.stop()
        self.assertFalse(bus.has_bridge)


class TestMessageQueuePsubscribe(unittest.TestCase):
    """Test pattern subscription on InMemoryQueue."""

    def test_psubscribe_receives_matching(self):
        q = InMemoryQueue()
        received = []
        stop = threading.Event()

        def listener():
            for msg in q.psubscribe("test:*"):
                received.append(msg)
                if stop.is_set():
                    break

        t = threading.Thread(target=listener, daemon=True)
        t.start()
        time.sleep(0.3)
        q.publish("test:foo", {"event": "hello"})
        time.sleep(0.3)
        stop.set()
        q.publish("test:stop", {"event": "stop"})
        t.join(timeout=3)
        self.assertGreaterEqual(len(received), 1)
        self.assertEqual(received[0]["event"], "hello")


class TestJob(unittest.TestCase):
    """Test Job serialization."""

    def test_to_dict_roundtrip(self):
        job = Job("test_type", {"input": "data"})
        d = job.to_dict()
        self.assertEqual(d["type"], "test_type")
        self.assertEqual(d["status"], "queued")
        restored = Job.from_dict(d)
        self.assertEqual(restored.id, job.id)
        self.assertEqual(restored.type, "test_type")
        self.assertEqual(restored.payload, {"input": "data"})

    def test_status_values(self):
        self.assertEqual(JobStatus.QUEUED.value, "queued")
        self.assertEqual(JobStatus.RUNNING.value, "running")
        self.assertEqual(JobStatus.COMPLETED.value, "completed")
        self.assertEqual(JobStatus.FAILED.value, "failed")


class TestJobQueueLocal(unittest.TestCase):
    """Test JobQueue in local (in-memory) mode."""

    def test_submit_and_execute(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        jq.register_handler("echo", lambda p: {"echoed": p.get("msg")})

        job_id = jq.submit("echo", {"msg": "hello"})
        self.assertIsNotNone(job_id)

        # Wait for async execution
        time.sleep(0.5)
        status = jq.status(job_id)
        self.assertEqual(status, "completed")
        result = jq.result(job_id)
        self.assertEqual(result["echoed"], "hello")

    def test_submit_no_handler(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        job_id = jq.submit("unknown_type", {})
        # No handler, job stays queued in local mode
        status = jq.status(job_id)
        self.assertEqual(status, "queued")

    def test_handler_failure(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        jq.register_handler("fail", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))

        job_id = jq.submit("fail", {})
        time.sleep(0.5)
        status = jq.status(job_id)
        self.assertEqual(status, "failed")
        info = jq.get(job_id)
        self.assertIn("boom", info["error"])

    def test_cancel_queued_job(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        # No handler — stays queued
        job_id = jq.submit("noop", {})
        self.assertTrue(jq.cancel(job_id))
        self.assertEqual(jq.status(job_id), "cancelled")

    def test_cancel_completed_fails(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        jq.register_handler("fast", lambda p: {"done": True})
        job_id = jq.submit("fast", {})
        time.sleep(0.5)
        self.assertFalse(jq.cancel(job_id))

    def test_get_full_info(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        jq.register_handler("info", lambda p: {"result": 42})
        job_id = jq.submit("info", {"x": 1})
        time.sleep(0.5)
        info = jq.get(job_id)
        self.assertEqual(info["type"], "info")
        self.assertEqual(info["status"], "completed")
        self.assertEqual(info["result"]["result"], 42)
        self.assertIsNotNone(info["started_at"])
        self.assertIsNotNone(info["completed_at"])

    def test_is_not_distributed(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        self.assertFalse(jq.is_distributed)

    def test_nonexistent_job(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        self.assertIsNone(jq.status("nonexistent"))
        self.assertIsNone(jq.result("nonexistent"))
        self.assertIsNone(jq.get("nonexistent"))


class TestJobQueueWorkers(unittest.TestCase):
    """Test JobQueue worker thread management."""

    def test_start_stop_workers(self):
        q = InMemoryQueue()
        jq = JobQueue(q)
        jq.start_workers(count=2)
        self.assertEqual(len(jq._workers), 2)
        self.assertTrue(jq._running)
        jq.stop_workers()
        self.assertFalse(jq._running)
        self.assertEqual(len(jq._workers), 0)


if __name__ == "__main__":
    unittest.main()
