"""Tests for the in-memory event bus."""
import threading
import unittest

from system.core.ui_bridge.event_bus import EventBus


class TestEventBus(unittest.TestCase):

    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda evt: received.append(evt))
        bus.emit("test", {"key": "value"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["type"], "test")
        self.assertEqual(received[0]["data"]["key"], "value")
        self.assertIn("timestamp", received[0])

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        unsub = bus.subscribe(lambda evt: received.append(evt))
        bus.emit("a", {})
        self.assertEqual(len(received), 1)
        unsub()
        bus.emit("b", {})
        self.assertEqual(len(received), 1)  # no new events

    def test_multiple_subscribers(self):
        bus = EventBus()
        a, b = [], []
        bus.subscribe(lambda evt: a.append(evt))
        bus.subscribe(lambda evt: b.append(evt))
        bus.emit("x", {})
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)

    def test_bad_subscriber_does_not_block_others(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda evt: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe(lambda evt: received.append(evt))
        bus.emit("safe", {})
        self.assertEqual(len(received), 1)

    def test_emit_with_no_subscribers(self):
        bus = EventBus()
        bus.emit("lonely", {"x": 1})  # should not raise

    def test_subscriber_count(self):
        bus = EventBus()
        self.assertEqual(bus.subscriber_count, 0)
        unsub1 = bus.subscribe(lambda e: None)
        unsub2 = bus.subscribe(lambda e: None)
        self.assertEqual(bus.subscriber_count, 2)
        unsub1()
        self.assertEqual(bus.subscriber_count, 1)
        unsub2()
        self.assertEqual(bus.subscriber_count, 0)

    def test_thread_safety(self):
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def safe_append(evt):
            with lock:
                received.append(evt)

        bus.subscribe(safe_append)

        threads = []
        for i in range(20):
            t = threading.Thread(target=lambda idx=i: bus.emit("t", {"i": idx}))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(received), 20)

    def test_double_unsubscribe_is_safe(self):
        bus = EventBus()
        unsub = bus.subscribe(lambda e: None)
        unsub()
        unsub()  # should not raise
        self.assertEqual(bus.subscriber_count, 0)

    def test_emit_default_data(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda evt: received.append(evt))
        bus.emit("no_data")
        self.assertEqual(received[0]["data"], {})


if __name__ == "__main__":
    unittest.main()
